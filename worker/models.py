"""Shared Pydantic models for OCR SaaS."""
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    REVIEW = "review"


class DocumentType(str, Enum):
    POD = "pod"
    INVOICE = "invoice"
    RECEIPT = "receipt"
    RATE_CONFIRMATION = "rate_confirmation"
    FUEL_RECEIPT = "fuel_receipt"
    SCALE_TICKET = "scale_ticket"
    EIR = "eir"
    GATE_TICKET = "gate_ticket"
    LOAD_CONFIRMATION = "load_confirmation"
    TERMINAL_PAPERWORK = "terminal_paperwork"
    APPOINTMENT_CONFIRMATION = "appointment_confirmation"
    CONTAINER_PICKUP = "container_pickup"
    CONTAINER_DROPOFF = "container_dropoff"
    CHASSIS_PAPERWORK = "chassis_paperwork"
    YARD_TICKET = "yard_ticket"
    REFERENCE_SHEET = "reference_sheet"
    UNKNOWN = "unknown"


class ExtractedField(BaseModel):
    field_name: str
    field_value: str
    confidence: float = Field(ge=0.0, le=1.0)
    page_number: Optional[int] = None
    bbox: Optional[dict] = None


class OCRDocument(BaseModel):
    id: Optional[str] = None
    job_id: str
    filename: str
    document_type: Optional[DocumentType] = None
    ocr_text: Optional[str] = None
    page_count: int = 1
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    file_hash: Optional[str] = None
    status: DocumentStatus = DocumentStatus.PENDING
    error_message: Optional[str] = None
    webhook_url: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    extracted_fields: list[ExtractedField] = Field(default_factory=list)


class UploadResponse(BaseModel):
    job_id: str
    status: DocumentStatus
    filename: str
    created_at: datetime


class StatusResponse(BaseModel):
    job_id: str
    status: DocumentStatus
    document_type: Optional[DocumentType] = None
    confidence_score: Optional[float] = None
    extracted_fields: dict[str, str] = Field(default_factory=dict)
    ocr_text: Optional[str] = None
    error_message: Optional[str] = None
    processed_at: Optional[datetime] = None
    created_at: datetime


class WebhookConfig(BaseModel):
    webhook_url: str


class CustomerConfig(BaseModel):
    customer_id: str
    customer_name: str
    supabase_url: str
    supabase_key: str
    api_key_hash: str
    email_imap: Optional[dict] = None
    created_at: Optional[datetime] = None


class CustomerCreate(BaseModel):
    customer_name: str
    supabase_url: str
    supabase_key: str
    webhook_url: Optional[str] = None
    email_host: Optional[str] = None
    email_port: Optional[int] = None
    email_user: Optional[str] = None
    email_pass: Optional[str] = None


class EmailConfig(BaseModel):
    host: str
    port: int = 993
    user: str
    password: str
    folder: str = "INBOX"
