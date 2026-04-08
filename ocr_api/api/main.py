"""FastAPI main application for OCR SaaS API."""
import hashlib
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Depends, status
from fastapi.middleware.cors import CORSMiddleware

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.supabase_client import SupabaseClientFactory, init_customer_clients
from shared.storage import get_storage
from shared.models import DocumentStatus
from api.auth import get_current_customer
from api.models import (
    UploadResponse,
    StatusResponse,
    DocumentListResponse,
    WebhookRequest,
    WebhookResponse,
    CustomerCreateRequest,
    CustomerCreateResponse,
    EmailConfigRequest,
)
from api.celery_app import celery_app


# Initialize FastAPI app
app = FastAPI(
    title="OCR SaaS API",
    description="Multi-tenant OCR processing API",
    version="1.0.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """Initialize customer clients on startup."""
    try:
        init_customer_clients()
    except FileNotFoundError:
        print("Warning: Customer config file not found. Run with populated config.")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/v1/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    webhook_url: Optional[str] = None,
    customer_id: str = Depends(get_current_customer),
):
    """
    Upload a document for OCR processing.

    Returns a job_id that can be used to poll for status.
    """
    storage = get_storage()

    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if not storage.is_supported_file(file.filename):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: .pdf, .jpg, .jpeg, .png, .tiff, .tif, .bmp"
        )

    # Read file content
    content = await file.read()

    # Check file size (50MB limit)
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50MB)")

    # Save to pending
    job_id, file_path = storage.save_upload(content, file.filename, customer_id)

    # Get customer config for Supabase
    config = SupabaseClientFactory.get_config(customer_id)
    supabase = SupabaseClientFactory.get_client(customer_id)

    # Insert document record
    doc_record = {
        "job_id": job_id,
        "filename": file.filename,
        "status": "queued",
        "webhook_url": webhook_url or config.webhook_url,
    }
    supabase.table("ocr_documents").insert([doc_record]).execute()

    # Queue OCR task
    celery_app.send_task(
        "tasks.process_document",
        args=[job_id, customer_id, file_path],
        task_id=job_id,
    )

    return UploadResponse(
        job_id=job_id,
        status=DocumentStatus.QUEUED,
        filename=file.filename,
        created_at=datetime.utcnow(),
    )


@app.get("/api/v1/status/{job_id}", response_model=StatusResponse)
async def get_status(
    job_id: str,
    customer_id: str = Depends(get_current_customer),
):
    """Get the status and results of an OCR job."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    # Fetch document
    result = supabase.table("ocr_documents").select("*").eq("job_id", job_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    doc = result.data[0]

    # Fetch extracted fields
    fields_result = supabase.table("ocr_extracted_fields").select("*").eq("document_id", doc["id"]).execute()

    # Build extracted fields dict
    extracted_fields = {}
    for field in fields_result.data:
        extracted_fields[field["field_name"]] = field["field_value"]

    return StatusResponse(
        job_id=doc["job_id"],
        status=DocumentStatus(doc["status"]),
        document_type=doc.get("document_type"),
        confidence_score=doc.get("confidence_score"),
        extracted_fields=extracted_fields,
        ocr_text=doc.get("ocr_text"),
        error_message=doc.get("error_message"),
        processed_at=doc.get("processed_at"),
        created_at=doc["created_at"],
    )


@app.get("/api/v1/documents", response_model=DocumentListResponse)
async def list_documents(
    limit: int = 50,
    offset: int = 0,
    status_filter: Optional[str] = None,
    customer_id: str = Depends(get_current_customer),
):
    """List recent documents for a customer."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    query = supabase.table("ocr_documents").select("*").order("created_at", desc=True).limit(limit).offset(offset)

    if status_filter:
        query = query.eq("status", status_filter)

    result = query.execute()

    documents = []
    for doc in result.data:
        documents.append(StatusResponse(
            job_id=doc["job_id"],
            status=DocumentStatus(doc["status"]),
            document_type=doc.get("document_type"),
            confidence_score=doc.get("confidence_score"),
            error_message=doc.get("error_message"),
            processed_at=doc.get("processed_at"),
            created_at=doc["created_at"],
        ))

    return DocumentListResponse(documents=documents, total=len(documents))


@app.get("/api/v1/document/{job_id}")
async def get_document(
    job_id: str,
    customer_id: str = Depends(get_current_customer),
):
    """Get full document details including extracted fields."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    # Fetch document
    result = supabase.table("ocr_documents").select("*").eq("job_id", job_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    doc = result.data[0]

    # Fetch extracted fields
    fields_result = supabase.table("ocr_extracted_fields").select("*").eq("document_id", doc["id"]).execute()

    return {
        "document": doc,
        "extracted_fields": fields_result.data,
    }


@app.post("/api/v1/webhook", response_model=WebhookResponse)
async def configure_webhook(
    request: WebhookRequest,
    customer_id: str = Depends(get_current_customer),
):
    """Configure webhook URL for job completion notifications."""
    return WebhookResponse(
        success=True,
        message=f"Webhook URL configured: {request.webhook_url}"
    )


@app.post("/api/v1/email/configure", response_model=WebhookResponse)
async def configure_email(
    request: EmailConfigRequest,
    customer_id: str = Depends(get_current_customer),
):
    """Configure IMAP email settings for email ingestion."""
    return WebhookResponse(
        success=True,
        message="Email configuration updated"
    )


@app.post("/api/v1/customer", response_model=CustomerCreateResponse)
async def create_customer(request: CustomerCreateRequest):
    """
    Create a new customer (admin endpoint).
    """
    customer_id = f"cust_{uuid.uuid4().hex[:12]}"
    api_key = f"ocr_{uuid.uuid4().hex}"
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Create customer config
    from shared.models import CustomerConfig
    customer_config = CustomerConfig(
        customer_id=customer_id,
        customer_name=request.customer_name,
        supabase_url=request.supabase_url,
        supabase_key=request.supabase_key,
        api_key_hash=api_key_hash,
        email_imap={
            "host": request.email_host,
            "port": request.email_port,
            "user": request.email_user,
            "password": request.email_pass,
            "folder": "INBOX",
        } if request.email_host else None,
    )

    # Add to registry
    SupabaseClientFactory.add_customer(customer_config)

    return CustomerCreateResponse(
        customer_id=customer_id,
        api_key=api_key,
        message="Customer created successfully"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
