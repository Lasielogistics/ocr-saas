"""API Pydantic models for OCR SaaS."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from shared.models import DocumentStatus, DocumentType, ExtractedField


class UploadRequest(BaseModel):
    """Request model for document upload (optional metadata)."""
    webhook_url: Optional[str] = None


class UploadResponse(BaseModel):
    """Response model for document upload."""
    job_id: str
    status: DocumentStatus
    filename: str
    created_at: datetime


class StatusResponse(BaseModel):
    """Response model for job status."""
    job_id: str
    status: DocumentStatus
    document_type: Optional[str] = None
    confidence_score: Optional[float] = None
    extracted_fields: dict[str, str] = Field(default_factory=dict)
    container_number: Optional[str] = None
    company: Optional[str] = None
    ocr_text: Optional[str] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime


class DocumentListResponse(BaseModel):
    """Response model for document list."""
    documents: list[StatusResponse]
    total: int


class WebhookRequest(BaseModel):
    """Request model for webhook configuration."""
    webhook_url: str


class WebhookResponse(BaseModel):
    """Response model for webhook configuration."""
    success: bool
    message: str


class CustomerCreateRequest(BaseModel):
    """Request model for customer creation (admin only)."""
    customer_name: str
    supabase_url: str
    supabase_key: str
    webhook_url: Optional[str] = None
    email_host: Optional[str] = None
    email_port: Optional[int] = None
    email_user: Optional[str] = None
    email_pass: Optional[str] = None


class CustomerCreateResponse(BaseModel):
    """Response model for customer creation."""
    customer_id: str
    api_key: str  # New API key to give to customer
    message: str


class EmailConfigRequest(BaseModel):
    """Request model for email IMAP configuration."""
    host: str
    port: int = Field(default=993, ge=1, le=65535)
    user: str
    password: str
    folder: str = "INBOX"


class ErrorResponse(BaseModel):
    """Standard error response."""
    detail: str
