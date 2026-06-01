"""Invoice API endpoints with multi-tenant + RBAC."""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel

from shared.auth import decode_token, get_db, require_permission, require_role
from .pdf_gen import generate_invoice_pdf

router = APIRouter(prefix="/invoices", tags=["invoices"])


# ── Auth dependency ─────────────────────────────────────────────────

def get_user(request: Request) -> dict:
    """Extract and validate JWT from Authorization header."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing authorization")
    payload = decode_token(auth[7:])
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def require_invoice_read(user: dict = Depends(get_user)) -> dict:
    if not require_permission(user, "invoices", "read"):
        raise HTTPException(status_code=403, detail="Invoices: read access denied")
    return user


def require_invoice_write(user: dict = Depends(get_user)) -> dict:
    if not require_permission(user, "invoices", "write"):
        raise HTTPException(status_code=403, detail="Invoices: write access denied")
    return user


def require_invoice_delete(user: dict = Depends(get_user)) -> dict:
    if not require_permission(user, "invoices", "delete"):
        raise HTTPException(status_code=403, detail="Invoices: delete access denied")
    return user


# ── Request/Response models ─────────────────────────────────────────

class LineItemCreate(BaseModel):
    description: str
    quantity: float = 1.0
    rate: float
    line_type: str = "manual"  # "rate_sheet" or "manual"
    rate_sheet_id: Optional[str] = None

class LineItemUpdate(BaseModel):
    description: Optional[str] = None
    quantity: Optional[float] = None
    rate: Optional[float] = None
    line_type: Optional[str] = None
    rate_sheet_id: Optional[str] = None

class InvoiceCreate(BaseModel):
    client_account_id: Optional[str] = None
    container_id: Optional[str] = None
    shipment_type: str = "import"
    issue_date: Optional[str] = None  # YYYY-MM-DD
    due_date: Optional[str] = None
    notes: Optional[str] = None
    line_items: list[LineItemCreate] = []

class InvoiceUpdate(BaseModel):
    client_account_id: Optional[str] = None
    container_id: Optional[str] = None
    shipment_type: Optional[str] = None
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None

class StatusUpdate(BaseModel):
    status: str  # draft|sent|paid|overdue|voided
    notes: Optional[str] = None

class LineItemResponse(BaseModel):
    id: str; description: str; quantity: float; rate: float
    amount: float; line_type: str; rate_sheet_id: Optional[str]; sort_order: int

class InvoiceResponse(BaseModel):
    id: str; invoice_number: str; invoice_number_int: int; qb_invoice_num: Optional[int]
    client_account_id: Optional[str]; container_id: Optional[str]
    shipment_type: Optional[str]; status: str
    issue_date: Optional[date]; due_date: Optional[date]
    subtotal: float; notes: Optional[str]; voided_at: Optional[str]; voided_reason: Optional[str]
    created_at: str; line_items: list[LineItemResponse] = []


# ── Helpers ─────────────────────────────────────────────────────────

def _invoice_row_to_dict(row, cur) -> dict:
    return {
        "id": str(row[0]),
        "invoice_number": row[1],
        "invoice_number_int": row[2],
        "qb_invoice_num": row[3],
        "client_account_id": str(row[4]) if row[4] else None,
        "container_id": str(row[5]) if row[5] else None,
        "shipment_type": row[6],
        "status": row[7],
        "issue_date": str(row[8]) if row[8] else None,
        "due_date": str(row[9]) if row[9] else None,
        "subtotal": float(row[10]) if row[10] else 0,
        "notes": row[11],
        "voided_at": str(row[12]) if row[12] else None,
        "voided_reason": row[13],
        "created_at": str(row[14]) if row[14] else None,
    }

def _get_line_items(conn, invoice_id: str) -> list:
    cur = conn.cursor()
    cur.execute("""
        SELECT id, description, quantity, rate, amount, line_type, rate_sheet_id, sort_order
        FROM invoice_line_items WHERE invoice_id = %s ORDER BY sort_order
    """, (invoice_id,))
    return [
        {
            "id": str(r[0]), "description": r[1], "quantity": float(r[2]),
            "rate": float(r[3]), "amount": float(r[4]), "line_type": r[5],
            "rate_sheet_id": str(r[6]) if r[6] else None, "sort_order": r[7]
        }
        for r in cur.fetchall()
    ]

def _get_client_account_name(conn, account_id: str) -> Optional[str]:
    cur = conn.cursor()
    cur.execute("SELECT account_name FROM client_accounts WHERE id = %s", (account_id,))
    r = cur.fetchone()
    return r[0] if r else None

def _recalc_subtotal(conn, invoice_id: str) -> float:
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(amount),0) FROM invoice_line_items WHERE invoice_id = %s", (invoice_id,))
    return float(cur.fetchone()[0])

def _audit(conn, tenant_id: str, user_id: str, action: str, resource: str, resource_id: str, details: dict = None):
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO audit_log (tenant_id, user_id, action, resource, resource_id, details)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (tenant_id, user_id, action, resource, resource_id, str(details or {})))
    except Exception:
        pass

# ── Endpoints ───────────────────────────────────────────────────────

@router.get("", response_model=list[InvoiceResponse])
def list_invoices(
    status: Optional[str] = None,
    client_account_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(require_invoice_read),
):
    """List invoices for the current tenant, newest first."""
    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT id, invoice_number, invoice_number_int, qb_invoice_num,
               client_account_id, container_id, shipment_type, status,
               issue_date, due_date, subtotal, notes, voided_at, voided_reason, created_at
        FROM invoices
        WHERE tenant_id = %s
    """
    params = [user["tenant_id"]]

    if status:
        query += " AND status = %s"
        params.append(status)
    if client_account_id:
        query += " AND client_account_id = %s"
        params.append(client_account_id)
    if from_date:
        query += " AND issue_date >= %s"
        params.append(from_date)
    if to_date:
        query += " AND issue_date <= %s"
        params.append(to_date)

    query += " ORDER BY invoice_number_int DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])

    cur.execute(query, tuple(params))
    rows = cur.fetchall()

    result = []
    for row in rows:
        inv = _invoice_row_to_dict(row, cur)
        inv["line_items"] = _get_line_items(conn, inv["id"])
        result.append(inv)

    conn.close()
    return result


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: str, user: dict = Depends(require_invoice_read)):
    """Get a single invoice with line items."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, invoice_number, invoice_number_int, qb_invoice_num,
               client_account_id, container_id, shipment_type, status,
               issue_date, due_date, subtotal, notes, voided_at, voided_reason, created_at
        FROM invoices WHERE id = %s AND tenant_id = %s
    """, (invoice_id, user["tenant_id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    inv = _invoice_row_to_dict(row, cur)
    inv["line_items"] = _get_line_items(conn, inv["id"])
    conn.close()
    return inv


@router.post("", response_model=InvoiceResponse)
def create_invoice(data: InvoiceCreate, user: dict = Depends(require_invoice_write)):
    """Create a new invoice with line items."""
    conn = get_db()
    cur = conn.cursor()

    # Get next invoice number
    cur.execute("SELECT get_next_invoice_number()")
    next_num = cur.fetchone()[0]
    invoice_number = f"INV-{next_num}"

    # Parse dates
    issue_date = data.issue_date or str(date.today())
    due_date = data.due_date or str(date.today())

    # Insert invoice
    cur.execute("""
        INSERT INTO invoices (
            invoice_number, invoice_number_int, tenant_id,
            client_account_id, container_id, shipment_type, status,
            issue_date, due_date, subtotal, notes
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING id, invoice_number, invoice_number_int, qb_invoice_num,
                  client_account_id, container_id, shipment_type, status,
                  issue_date, due_date, subtotal, notes, voided_at, voided_reason, created_at
    """, (
        invoice_number, next_num, user["tenant_id"],
        data.client_account_id, data.container_id, data.shipment_type, "draft",
        issue_date, due_date, 0, data.notes or None,
    ))
    row = cur.fetchone()
    invoice_id = row[0]

    # Insert line items
    subtotal = 0.0
    for i, li in enumerate(data.line_items):
        amount = li.quantity * li.rate
        subtotal += amount
        cur.execute("""
            INSERT INTO invoice_line_items
            (invoice_id, description, quantity, rate, amount, line_type, rate_sheet_id, sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (invoice_id, li.description, li.quantity, li.rate, amount, li.line_type, li.rate_sheet_id, i))

    # Update subtotal
    cur.execute("UPDATE invoices SET subtotal = %s WHERE id = %s", (subtotal, invoice_id))

    # Audit event
    cur.execute("""
        INSERT INTO invoice_events (invoice_id, event_type, notes)
        VALUES (%s, 'created', %s)
    """, (invoice_id, f"Created by {user['email']}"))

    _audit(conn, user["tenant_id"], user["sub"], "create_invoice", "invoices", invoice_id)

    conn.commit()

    inv = _invoice_row_to_dict(row, cur)
    inv["line_items"] = _get_line_items(conn, invoice_id)
    conn.close()
    return inv


@router.patch("/{invoice_id}", response_model=InvoiceResponse)
def update_invoice(invoice_id: str, data: InvoiceUpdate, user: dict = Depends(require_invoice_write)):
    """Update invoice fields (not status, not line items)."""
    conn = get_db()
    cur = conn.cursor()

    # Verify ownership
    cur.execute("SELECT id, status FROM invoices WHERE id = %s AND tenant_id = %s", (invoice_id, user["tenant_id"]))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    fields = []
    params = []
    if data.client_account_id is not None:
        fields.append("client_account_id = %s"); params.append(data.client_account_id)
    if data.container_id is not None:
        fields.append("container_id = %s"); params.append(data.container_id)
    if data.shipment_type is not None:
        fields.append("shipment_type = %s"); params.append(data.shipment_type)
    if data.issue_date is not None:
        fields.append("issue_date = %s"); params.append(data.issue_date)
    if data.due_date is not None:
        fields.append("due_date = %s"); params.append(data.due_date)
    if data.notes is not None:
        fields.append("notes = %s"); params.append(data.notes)

    if fields:
        params.append(invoice_id)
        cur.execute(f"UPDATE invoices SET {', '.join(fields)} WHERE id = %s", tuple(params))
        conn.commit()

    # Fetch updated row
    cur.execute("""
        SELECT id, invoice_number, invoice_number_int, qb_invoice_num,
               client_account_id, container_id, shipment_type, status,
               issue_date, due_date, subtotal, notes, voided_at, voided_reason, created_at
        FROM invoices WHERE id = %s
    """, (invoice_id,))
    row = cur.fetchone()
    inv = _invoice_row_to_dict(row, cur)
    inv["line_items"] = _get_line_items(conn, invoice_id)
    _audit(conn, user["tenant_id"], user["sub"], "update_invoice", "invoices", invoice_id)
    conn.close()
    return inv


@router.patch("/{invoice_id}/status", response_model=InvoiceResponse)
def update_status(invoice_id: str, data: StatusUpdate, user: dict = Depends(require_invoice_write)):
    """Transition invoice status (draft→sent, sent→paid, etc.). Admin can void anything."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, status FROM invoices WHERE id = %s AND tenant_id = %s
    """, (invoice_id, user["tenant_id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    current_status = row[1]
    new_status = data.status

    # Validate transitions
    valid_transitions = {
        "draft": ["sent"],
        "sent": ["paid", "overdue", "voided"],
        "paid": ["voided"],
        "overdue": ["paid", "voided"],
        "voided": [],  # terminal state
    }

    if new_status == "voided":
        # Admin can void any invoice
        pass
    elif new_status not in valid_transitions.get(current_status, []):
        conn.close()
        raise HTTPException(status_code=400, detail=f"Cannot transition from {current_status} to {new_status}")

    # Apply update
    voided_at = "now()" if new_status == "voided" else "NULL"
    voided_reason = f"Voided: {data.notes}" if new_status == "voided" else "NULL"

    cur.execute(f"""
        UPDATE invoices
        SET status = %s, voided_at = {voided_at}, voided_reason = {voided_reason}
        WHERE id = %s
    """, (new_status, invoice_id))

    # Record event
    cur.execute("""
        INSERT INTO invoice_events (invoice_id, event_type, notes)
        VALUES (%s, %s, %s)
    """, (invoice_id, new_status, data.notes or f"Status changed by {user['email']}"))

    _audit(conn, user["tenant_id"], user["sub"], f"status_{new_status}", "invoices", invoice_id)

    conn.commit()

    cur.execute("""
        SELECT id, invoice_number, invoice_number_int, qb_invoice_num,
               client_account_id, container_id, shipment_type, status,
               issue_date, due_date, subtotal, notes, voided_at, voided_reason, created_at
        FROM invoices WHERE id = %s
    """, (invoice_id,))
    row = cur.fetchone()
    inv = _invoice_row_to_dict(row, cur)
    inv["line_items"] = _get_line_items(conn, invoice_id)
    conn.close()
    return inv


@router.post("/{invoice_id}/line-items", response_model=InvoiceResponse)
def add_line_item(invoice_id: str, item: LineItemCreate, user: dict = Depends(require_invoice_write)):
    """Add a line item to an existing invoice."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, status FROM invoices WHERE id = %s AND tenant_id = %s", (invoice_id, user["tenant_id"]))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    amount = item.quantity * item.rate
    cur.execute("""
        INSERT INTO invoice_line_items
        (invoice_id, description, quantity, rate, amount, line_type, rate_sheet_id, sort_order)
        VALUES (%s,%s,%s,%s,%s,%s,%s,
            (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM invoice_line_items WHERE invoice_id = %s))
        RETURNING id
    """, (invoice_id, item.description, item.quantity, item.rate, amount, item.line_type, item.rate_sheet_id, invoice_id))

    # Recalc subtotal
    new_subtotal = _recalc_subtotal(conn, invoice_id)
    cur.execute("UPDATE invoices SET subtotal = %s WHERE id = %s", (new_subtotal, invoice_id))
    _audit(conn, user["tenant_id"], user["sub"], "add_line_item", "invoices", invoice_id)
    conn.commit()

    cur.execute("""
        SELECT id, invoice_number, invoice_number_int, qb_invoice_num,
               client_account_id, container_id, shipment_type, status,
               issue_date, due_date, subtotal, notes, voided_at, voided_reason, created_at
        FROM invoices WHERE id = %s
    """, (invoice_id,))
    row = cur.fetchone()
    inv = _invoice_row_to_dict(row, cur)
    inv["line_items"] = _get_line_items(conn, invoice_id)
    conn.close()
    return inv


@router.delete("/{invoice_id}", response_model=dict)
def delete_invoice(invoice_id: str, user: dict = Depends(require_invoice_delete)):
    """Hard delete an invoice. Only allowed for status='draft' and only by admin."""
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Only admin can delete invoices")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT id, status FROM invoices WHERE id = %s AND tenant_id = %s", (invoice_id, user["tenant_id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")
    if row[1] != "draft":
        conn.close()
        raise HTTPException(status_code=400, detail="Only draft invoices can be deleted")

    cur.execute("DELETE FROM invoices WHERE id = %s", (invoice_id,))
    _audit(conn, user["tenant_id"], user["sub"], "delete_invoice", "invoices", invoice_id)
    conn.commit()
    conn.close()
    return {"deleted": True, "id": invoice_id}


@router.get("/{invoice_id}/events")
def get_invoice_events(invoice_id: str, user: dict = Depends(require_invoice_read)):
    """Get audit trail for an invoice."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id FROM invoices WHERE id = %s AND tenant_id = %s", (invoice_id, user["tenant_id"]))
    if not cur.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    cur.execute("""
        SELECT id, event_type, notes, created_at
        FROM invoice_events WHERE invoice_id = %s ORDER BY created_at
    """, (invoice_id,))
    events = [{"id": str(r[0]), "event_type": r[1], "notes": r[2], "created_at": str(r[3])} for r in cur.fetchall()]
    conn.close()
    return events


@router.get("/{invoice_id}/pdf")
def get_invoice_pdf(invoice_id: str, user: dict = Depends(require_invoice_read)):
    """Generate and return a PDF version of the invoice."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, invoice_number, invoice_number_int, qb_invoice_num,
               client_account_id, container_id, shipment_type, status,
               issue_date, due_date, subtotal, notes, voided_at, voided_reason, created_at
        FROM invoices WHERE id = %s AND tenant_id = %s
    """, (invoice_id, user["tenant_id"]))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invoice not found")

    inv = _invoice_row_to_dict(row, cur)
    inv["line_items"] = _get_line_items(conn, invoice_id)
    conn.close()

    pdf_bytes = generate_invoice_pdf(inv)
    filename = f"Invoice-{inv['invoice_number']}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={filename}"}
    )
