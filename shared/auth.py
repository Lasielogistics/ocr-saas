"""Multi-tenant authentication and authorization."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from passlib.context import CryptContext

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://tms:tms_secret_password@tms-postgres:5432/tms_main"
)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = int(os.getenv("ACCESS_TOKEN_EXPIRE_HOURS", "12"))
JWT_SECRET = os.getenv("JWT_SECRET", "CHANGE_ME_IN_PRODUCTION")

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_ctx.verify(password, hashed)


def create_access_token(
    user_id: str,
    email: str,
    tenant_id: str,
    role: str,
    expires_delta: timedelta = timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS),
) -> str:
    """Create a JWT access token."""
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT. Returns None if invalid/expired."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def require_permission(token_payload: dict, resource: str, action: str) -> bool:
    """
    Check if the user's role has the given permission.
    Super admins can do anything.
    """
    if token_payload.get("role") == "admin":
        return True
    # Query permission from DB
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM role_permissions rp
        JOIN permissions p ON p.id = rp.permission_id
        JOIN user_tenant_roles utr ON utr.role = rp.role
        WHERE utr.user_id = %s
          AND utr.tenant_id = %s
          AND p.resource = %s
          AND p.action = %s
        LIMIT 1
    """, (token_payload["sub"], token_payload["tenant_id"], resource, action))
    result = cur.fetchone()
    conn.close()
    return result is not None


def require_role(token_payload: dict, allowed_roles: list[str]) -> bool:
    """Check if the user's role is in the allowed list. Admin bypasses."""
    if token_payload.get("role") == "admin":
        return True
    return token_payload.get("role") in allowed_roles


def get_db():
    """Get a fresh psycopg2 connection."""
    import psycopg2
    return psycopg2.connect(DATABASE_URL)
