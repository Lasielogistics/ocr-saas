"""Invoice PDF generation using fpdf2."""
from io import BytesIO
from fpdf import FPDF

# ── Constants ────────────────────────────────────────────────────────────────

PAGE_WIDTH = 210  # A4 width in mm
MARGIN = 15
COL_CONTENT = PAGE_WIDTH - 2 * MARGIN

# ── Helpers ─────────────────────────────────────────────────────────────────

def _format_currency(amount: float) -> str:
    return f"${amount:,.2f}"


def _clamp(val, lo, hi):
    return max(lo, min(hi, val))


# ── Invoice PDF ───────────────────────────────────────────────────────────────

def generate_invoice_pdf(inv: dict) -> bytes:
    """
    Generate a professional invoice PDF for a single invoice dict.
    inv must have: invoice_number, issue_date, due_date, client_account_id,
                  shipment_type, status, subtotal, notes, line_items (list)
    Returns raw PDF bytes.
    """
    pdf = FPDF(format='A4')
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # ── Header band ───────────────────────────────────────────────────────
    pdf.set_fill_color(31, 111, 235)   # primary blue
    pdf.rect(0, 0, PAGE_WIDTH, 42, 'F')

    pdf.set_y(10)
    pdf.set_x(MARGIN)
    pdf.set_font('Helvetica', 'B', 22)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(80, 10, 'INVOICE', align='L', ln=False)

    pdf.set_font('Helvetica', '', 10)
    pdf.set_x(PAGE_WIDTH - MARGIN - 80)
    pdf.cell(80, 6, 'Land Air Sea TMS', align='R', ln=True)
    pdf.set_x(PAGE_WIDTH - MARGIN - 80)
    pdf.cell(80, 6, ' logistics@tms.com', align='R', ln=True)

    pdf.set_y(28)
    pdf.set_x(MARGIN)
    pdf.set_font('Helvetica', '', 9)
    pdf.set_text_color(220, 235, 255)
    pdf.cell(80, 5, f"Invoice #{inv.get('invoice_number', 'N/A')}", align='L', ln=True)
    pdf.set_x(MARGIN)
    if inv.get('qb_invoice_num'):
        pdf.cell(80, 5, f"QB Ref: {inv['qb_invoice_num']}", align='L', ln=True)

    # ── Reset text color ──────────────────────────────────────────────────
    pdf.set_text_color(13, 17, 23)

    # ── Meta cards ────────────────────────────────────────────────────────
    y = pdf.get_y() + 10

    def meta_card(x, label, value, w=56):
        pdf.set_fill_color(246, 248, 250)
        pdf.rect(x, y, w, 18, 'F')
        pdf.set_font('Helvetica', '', 7)
        pdf.set_fill_color(31, 111, 235)
        pdf.rect(x, y, w, 6, 'F')
        pdf.set_xy(x + 2, y + 1)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(w - 4, 5, label.upper(), align='L')
        pdf.set_text_color(13, 17, 23)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.set_xy(x + 2, y + 7)
        pdf.cell(w - 4, 8, str(value), align='L')

    meta_card(MARGIN, 'Issue Date', inv.get('issue_date') or 'N/A')
    meta_card(MARGIN + 60, 'Due Date', inv.get('due_date') or 'N/A')
    meta_card(MARGIN + 120, 'Status', (inv.get('status') or 'N/A').upper())
    y += 22

    # ── Client & Shipment ──────────────────────────────────────────────────
    pdf.set_y(y + 4)
    pdf.set_x(MARGIN)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(87, 96, 106)
    pdf.cell(40, 5, 'Bill To / Client Account:', ln=False)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(13, 17, 23)
    client = inv.get('client_account_id') or 'N/A'
    pdf.cell(COL_CONTENT - 40, 5, client, ln=True)

    pdf.set_x(MARGIN)
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(87, 96, 106)
    pdf.cell(40, 5, 'Shipment Type:', ln=False)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(13, 17, 23)
    pdf.cell(COL_CONTENT - 40, 5, (inv.get('shipment_type') or 'N/A').capitalize(), ln=True)

    if inv.get('container_id'):
        pdf.set_x(MARGIN)
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(87, 96, 106)
        pdf.cell(40, 5, 'Container:', ln=False)
        pdf.set_font('Helvetica', 'B', 9)
        pdf.set_text_color(13, 17, 23)
        pdf.cell(COL_CONTENT - 40, 5, inv['container_id'], ln=True)

    y = pdf.get_y() + 6

    # ── Line items table ──────────────────────────────────────────────────
    # Header
    pdf.set_fill_color(220, 223, 228)
    pdf.rect(MARGIN, y, COL_CONTENT, 8, 'F')
    pdf.set_font('Helvetica', 'B', 8)
    pdf.set_text_color(87, 96, 106)
    col_desc = COL_CONTENT * 0.50
    col_qty  = COL_CONTENT * 0.12
    col_rate = COL_CONTENT * 0.18
    col_amt  = COL_CONTENT * 0.20
    x = MARGIN + 2
    pdf.cell(col_desc, 8, 'DESCRIPTION', border=0, ln=False)
    pdf.cell(col_qty,  8, 'QTY',        border=0, align='C', ln=False)
    pdf.cell(col_rate, 8, 'RATE',       border=0, align='R', ln=False)
    pdf.cell(col_amt,  8, 'AMOUNT',     border=0, align='R', ln=True)
    y += 8

    # Rows
    line_items = inv.get('line_items', []) or []
    if not line_items:
        pdf.set_font('Helvetica', 'I', 9)
        pdf.set_text_color(87, 96, 106)
        pdf.set_x(MARGIN + 2)
        pdf.cell(COL_CONTENT, 12, '(No line items)', align='C', ln=True)
        y += 12
    else:
        for i, li in enumerate(line_items):
            fill = (i % 2 == 0)
            if fill:
                pdf.set_fill_color(246, 248, 250)
                pdf.rect(MARGIN, y, COL_CONTENT, 8, 'F')
            pdf.set_font('Helvetica', '', 8)
            pdf.set_text_color(13, 17, 23)
            x = MARGIN + 2
            desc = li.get('description', '') or ''
            pdf.cell(col_desc, 8, desc[:60], border=0, ln=False)
            pdf.cell(col_qty,  8, str(li.get('quantity', 0)),   border=0, align='C', ln=False)
            pdf.cell(col_rate, 8, _format_currency(li.get('rate', 0)), border=0, align='R', ln=False)
            pdf.cell(col_amt,  8, _format_currency(li.get('amount', 0)), border=0, align='R', ln=True)
            y += 8

    y += 4

    # ── Totals ────────────────────────────────────────────────────────────
    subtotal = float(inv.get('subtotal') or 0)
    tax_rate = 0.0
    tax_amount = subtotal * tax_rate
    total = subtotal + tax_amount

    # Subtotal row
    pdf.set_fill_color(220, 223, 228)
    pdf.rect(MARGIN + col_desc + col_qty, y, col_rate + col_amt, 8, 'F')
    pdf.set_font('Helvetica', '', 8)
    pdf.set_text_color(87, 96, 106)
    pdf.set_xy(MARGIN + col_desc + col_qty + 2, y + 1)
    pdf.cell(col_rate, 7, 'Subtotal', border=0, align='R', ln=False)
    pdf.set_font('Helvetica', 'B', 9)
    pdf.set_text_color(13, 17, 23)
    pdf.cell(col_amt - 2, 7, _format_currency(subtotal), border=0, align='R', ln=True)
    y += 10

    # Grand total
    pdf.set_fill_color(31, 111, 235)
    pdf.rect(MARGIN + col_desc + col_qty, y, col_rate + col_amt, 12, 'F')
    pdf.set_font('Helvetica', 'B', 11)
    pdf.set_text_color(255, 255, 255)
    pdf.set_xy(MARGIN + col_desc + col_qty + 2, y + 2)
    pdf.cell(col_rate, 9, 'TOTAL DUE', border=0, align='R', ln=False)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(col_amt - 2, 9, _format_currency(total), border=0, align='R', ln=True)
    y += 16

    # ── Notes ─────────────────────────────────────────────────────────────
    if inv.get('notes'):
        pdf.set_font('Helvetica', 'B', 8)
        pdf.set_text_color(87, 96, 106)
        pdf.set_x(MARGIN)
        pdf.cell(40, 5, 'Notes:', ln=True)
        pdf.set_font('Helvetica', '', 8)
        pdf.set_text_color(13, 17, 23)
        pdf.set_x(MARGIN)
        pdf.multi_cell(COL_CONTENT, 5, inv['notes'], ln=True)
        y = pdf.get_y() + 4

    # ── Footer ─────────────────────────────────────────────────────────────
    pdf.set_y(-20)
    pdf.set_font('Helvetica', '', 7)
    pdf.set_text_color(180, 180, 180)
    pdf.cell(PAGE_WIDTH - 2 * MARGIN, 4, 'Land Air Sea Import Export Logistics LLC  |  Generated by TMS', align='C', ln=True)
    pdf.cell(PAGE_WIDTH - 2 * MARGIN, 4, f'Invoice {inv.get("invoice_number", "")}  |  Page 1 of 1', align='C', ln=True)

    buf = BytesIO()
    buf.write(pdf.output())
    buf.seek(0)
    return buf.read()
