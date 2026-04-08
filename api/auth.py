"""API key authentication for OCR SaaS."""
import hashlib
import os
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from shared.supabase import SupabaseClientFactory


API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def hash_api_key(api_key: str) -> str:
    """Hash an API key using SHA256."""
    return hashlib.sha256(api_key.encode()).hexdigest()


def verify_api_key(api_key: str) -> str:
    """
    Verify an API key and return the customer_id.

    Returns customer_id if valid, raises HTTPException if invalid.
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key",
        )

    api_key_hash = hash_api_key(api_key)

    # Check against all customer configs
    for customer_id in SupabaseClientFactory.list_customers():
        config = SupabaseClientFactory.get_config(customer_id)
        if config.api_key_hash == api_key_hash:
            return customer_id

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key",
    )


async def get_current_customer(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Dependency to get the current customer ID from API key."""
    return verify_api_key(api_key)
