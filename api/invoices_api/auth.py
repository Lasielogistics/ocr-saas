"""Auth endpoints: login, register, me, switch tenant."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from shared.auth import (
    create_access_token,
    decode_token,
    get_db,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request/Response models ────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    tenant_name: Optional[str] = None  # if creating a new tenant
    tenant_slug: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    role: str
    tenant_id: str
    tenant_name: str


class UserResponse(BaseModel):
    user_id: str
    email: str
    full_name: str
    is_super_admin: bool
    tenants: list[dict]


class SwitchTenantRequest(BaseModel):
    tenant_id: str


# ── Auth dependencies ───────────────────────────────────────────────

def get_current_user(request: Request) -> dict:
    """Extract and validate the JWT from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid authorization header")
    token = auth_header[7:]
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def require_auth(request: Request) -> dict:
    """Alias for get_current_user — use this as a dependency."""
    return get_current_user(request)


# ── Endpoints ───────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest):
    """Log in with email + password. Returns JWT."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, email, password_hash, full_name, is_super_admin FROM users WHERE email = %s AND is_active = TRUE",
        (data.email,)
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user_id, email, password_hash, full_name, is_super_admin = row

    if not verify_password(data.password, password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Get user's tenants
    if is_super_admin:
        cur.execute("SELECT id, name, slug FROM tenants WHERE is_active = TRUE")
    else:
        cur.execute("""
            SELECT t.id, t.name, t.slug
            FROM tenants t
            JOIN user_tenant_roles utr ON utr.tenant_id = t.id
            WHERE utr.user_id = %s AND t.is_active = TRUE
        """, (user_id,))
    tenant_rows = cur.fetchall()
    conn.close()

    if not tenant_rows:
        raise HTTPException(status_code=403, detail="No active tenant access")

    # Default to first tenant
    tenant_id, tenant_name, tenant_slug = tenant_rows[0]
    role = "admin" if is_super_admin else "accounting"

    if not is_super_admin:
        cur = conn.cursor()
        conn = get_db()
        cur.execute("SELECT role FROM user_tenant_roles WHERE user_id = %s AND tenant_id = %s", (user_id, tenant_id))
        r = cur.fetchone()
        if r:
            role = r[0]
        conn.close()

    # Log audit
    _audit_login(user_id, tenant_id)

    token = create_access_token(user_id, email, tenant_id, role)
    return TokenResponse(
        access_token=token,
        user_id=user_id,
        email=email,
        role=role,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
    )


@router.post("/register", response_model=TokenResponse)
def register(data: RegisterRequest):
    """Register a new user. If tenant_name/slug provided, creates a new tenant too."""
    conn = get_db()
    cur = conn.cursor()

    # Check email uniqueness
    cur.execute("SELECT id FROM users WHERE email = %s", (data.email,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Email already registered")

    # Validate slug format
    import re
    if data.tenant_slug and not re.match(r"^[a-z0-9-]+$", data.tenant_slug):
        raise HTTPException(status_code=400, detail="Tenant slug must be lowercase letters, numbers, and hyphens only")

    tenant_id = None
    tenant_name = None

    if data.tenant_name and data.tenant_slug:
        # Create new tenant
        import uuid
        tenant_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO tenants (id, name, slug) VALUES (%s, %s, %s) RETURNING name",
            (tenant_id, data.tenant_name, data.tenant_slug)
        )
        tenant_name = data.tenant_name
    elif data.tenant_slug:
        # Join existing tenant by slug
        cur.execute("SELECT id, name FROM tenants WHERE slug = %s AND is_active = TRUE", (data.tenant_slug,))
        row = cur.fetchone()
        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="Tenant not found")
        tenant_id, tenant_name = row
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="tenant_slug required to join an existing tenant")

    # Create user
    import uuid
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(data.password)
    cur.execute(
        "INSERT INTO users (id, email, password_hash, full_name) VALUES (%s, %s, %s, %s)",
        (user_id, data.email, pw_hash, data.full_name)
    )

    # Assign admin role for new tenant, viewer for existing
    role = "admin" if data.tenant_name else "viewer"
    cur.execute(
        "INSERT INTO user_tenant_roles (user_id, tenant_id, role) VALUES (%s, %s, %s)",
        (user_id, tenant_id, role)
    )

    conn.commit()
    conn.close()

    _audit_login(user_id, tenant_id)

    token = create_access_token(user_id, data.email, tenant_id, role)
    return TokenResponse(
        access_token=token,
        user_id=user_id,
        email=data.email,
        role=role,
        tenant_id=tenant_id,
        tenant_name=tenant_name,
    )


@router.get("/me", response_model=UserResponse)
def get_me(user: dict = Depends(require_auth)):
    """Get current user info and their tenants."""
    conn = get_db()
    cur = conn.cursor()

    cur.execute(
        "SELECT id, email, full_name, is_super_admin FROM users WHERE id = %s",
        (user["sub"],)
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    user_id, email, full_name, is_super_admin = row

    if is_super_admin:
        cur.execute("SELECT id, name, slug FROM tenants WHERE is_active = TRUE")
    else:
        cur.execute("""
            SELECT t.id, t.name, t.slug
            FROM tenants t
            JOIN user_tenant_roles utr ON utr.tenant_id = t.id
            WHERE utr.user_id = %s AND t.is_active = TRUE
        """, (user_id,))
    tenant_rows = cur.fetchall()
    conn.close()

    tenants = [{"id": str(r[0]), "name": r[1], "slug": r[2]} for r in tenant_rows]

    return UserResponse(
        user_id=str(user_id),
        email=email,
        full_name=full_name,
        is_super_admin=is_super_admin,
        tenants=tenants,
    )


@router.post("/switch-tenant", response_model=TokenResponse)
def switch_tenant(data: SwitchTenantRequest, user: dict = Depends(require_auth)):
    """Switch to a different tenant the user has access to."""
    conn = get_db()
    cur = conn.cursor()

    # Verify access
    cur.execute("""
        SELECT utr.role, t.name
        FROM user_tenant_roles utr
        JOIN tenants t ON t.id = utr.tenant_id
        WHERE utr.user_id = %s AND utr.tenant_id = %s AND t.is_active = TRUE
    """, (user["sub"], data.tenant_id))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Access denied to this tenant")

    role, tenant_name = row
    token = create_access_token(user["sub"], user["email"], data.tenant_id, role)
    conn.close()

    return TokenResponse(
        access_token=token,
        user_id=user["sub"],
        email=user["email"],
        role=role,
        tenant_id=data.tenant_id,
        tenant_name=tenant_name,
    )


def _audit_login(user_id: str, tenant_id: str):
    """Record login in audit log."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_log (tenant_id, user_id, action) VALUES (%s, %s, 'login')",
            (tenant_id, user_id)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass  # non-critical
