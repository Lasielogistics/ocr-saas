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
from pydantic import BaseModel

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


class StatsResponse(BaseModel):
    """Response for document stats endpoint."""
    review: int
    failed: int
    ocr: int
    verified: int
    total: int
    linked: int
    unlinked: int
    linked_percent: float


@app.get("/api/v1/documents/stats", response_model=StatsResponse)
async def get_document_stats(
    customer_id: str = Depends(get_current_customer),
):
    """Get document counts by status - lightweight endpoint for dashboard."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    # Get all documents with their fields
    result = supabase.table("ocr_documents").select("id,job_id,status").execute()

    counts = {"review": 0, "failed": 0, "ocr": 0, "verified": 0, "total": len(result.data)}
    linked = 0
    unlinked = 0

    # Get extracted fields to check container_number
    doc_ids = [doc["id"] for doc in result.data]
    if doc_ids:
        fields_result = supabase.table("ocr_extracted_fields").select("document_id,field_name,field_value").in_(
            "document_id", doc_ids
        ).execute()

        # Build a map of document_id (UUID) -> container_number
        container_by_doc = {}
        for f in fields_result.data:
            if f["field_name"] == "container_number" and f["field_value"]:
                container_by_doc[f["document_id"]] = f["field_value"]

        # Count linked vs unlinked
        for doc in result.data:
            status = doc.get("status")
            if status in counts:
                counts[status] += 1

            doc_uuid = doc["id"]
            if doc_uuid in container_by_doc and container_by_doc[doc_uuid]:
                linked += 1
            else:
                unlinked += 1
    else:
        for doc in result.data:
            status = doc.get("status")
            if status in counts:
                counts[status] += 1

    linked_percent = (linked / counts["total"] * 100) if counts["total"] > 0 else 0.0

    return StatsResponse(
        review=counts["review"],
        failed=counts["failed"],
        ocr=counts["ocr"],
        verified=counts["verified"],
        total=counts["total"],
        linked=linked,
        unlinked=unlinked,
        linked_percent=round(linked_percent, 1),
    )


class UploadResponse(BaseModel):
    job_id: str
    status: DocumentStatus
    filename: str
    created_at: datetime
    page_count: Optional[int] = 1
    parent_job_id: Optional[str] = None


class MultiUploadResponse(BaseModel):
    """Response for multi-page PDF upload."""
    job_ids: list[str]
    page_count: int
    filename: str
    created_at: datetime
    parent_job_id: Optional[str] = None


@app.post("/api/v1/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    webhook_url: Optional[str] = None,
    customer_id: str = Depends(get_current_customer),
):
    """
    Upload a document for OCR processing.

    For multi-page PDFs, each page is split into a separate document.
    Returns the primary job_id - use /api/v1/status/{job_id} to check status.

    For multi-page PDFs, use /api/v1/upload/multi to get all page job_ids.
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

    # Check if PDF has multiple pages
    is_multi_page = file.filename.lower().endswith('.pdf')
    page_count = 1
    parent_job_id = None
    final_job_id = job_id

    if is_multi_page:
        # Split PDF into individual pages
        from pdf2image import convert_from_path
        images = convert_from_path(file_path, dpi=200)
        page_count = len(images)

        if page_count > 1:
            # Multi-page PDF - will create separate jobs for each page
            parent_job_id = job_id

            # Get customer pending directory for split pages
            customer_pending = storage.pending_path / customer_id
            customer_pending.mkdir(parents=True, exist_ok=True)

            # Process pages
            page_job_ids = []
            for page_num in range(page_count):
                # Create page job_id
                page_job_id = f"{job_id[:8]}_p{page_num + 1:03d}"

                # Save individual page as PNG
                from PIL import Image
                page_path = customer_pending / f"{page_job_id}.png"
                images[page_num].save(page_path, "PNG")

                # Insert document record for this page
                doc_record = {
                    "job_id": page_job_id,
                    "filename": f"{Path(file.filename).stem}_page_{page_num + 1}.png",
                    "status": "queued",
                    "webhook_url": webhook_url or config.webhook_url,
                    "page_count": 1,
                    "parent_job_id": parent_job_id,
                }
                supabase.table("ocr_documents").insert([doc_record]).execute()

                # Queue OCR task for this page
                celery_app.send_task(
                    "tasks.process_document",
                    args=[page_job_id, customer_id, str(page_path)],
                    task_id=page_job_id,
                )
                page_job_ids.append(page_job_id)

            # Mark original as parent (completed splitting)
            supabase.table("ocr_documents").update({
                "status": "ocr",
                "page_count": page_count,
            }).eq("job_id", job_id).execute()

            # Return first page job_id as primary
            final_job_id = page_job_ids[0]

            return UploadResponse(
                job_id=final_job_id,
                status=DocumentStatus.QUEUED,
                filename=f"{Path(file.filename).stem}_page_1.png",
                created_at=datetime.utcnow(),
                page_count=page_count,
                parent_job_id=parent_job_id,
            )

    # Single page document
    doc_record = {
        "job_id": job_id,
        "filename": file.filename,
        "status": "queued",
        "webhook_url": webhook_url or config.webhook_url,
        "page_count": 1,
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
        page_count=1,
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
        filename=doc.get("filename"),
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

    if not result.data:
        return DocumentListResponse(documents=[], total=0)

    doc_ids = [doc["id"] for doc in result.data]

    # Batch fetch all extracted fields for all documents
    fields_result = supabase.table("ocr_extracted_fields").select("*").in_("document_id", doc_ids).execute()
    fields_by_doc = {}
    for f in fields_result.data:
        doc_id = f["document_id"]
        if doc_id not in fields_by_doc:
            fields_by_doc[doc_id] = {}
        fields_by_doc[doc_id][f["field_name"]] = f["field_value"]

    # Get all container numbers and batch fetch companies
    container_numbers = set()
    for doc in result.data:
        fields = fields_by_doc.get(doc["id"], {})
        cn = fields.get("container_number")
        if cn:
            container_numbers.add(cn)

    # Batch fetch containers
    company_by_container = {}
    if container_numbers:
        containers_result = supabase.table("containers").select('container_number,"Company"').in_(
            "container_number", list(container_numbers)
        ).execute()
        for c in containers_result.data:
            company_by_container[c["container_number"]] = c.get("Company")

    documents = []
    for doc in result.data:
        extracted_fields = fields_by_doc.get(doc["id"], {})
        container_number = extracted_fields.get("container_number")
        company = company_by_container.get(container_number) if container_number else None

        documents.append(StatusResponse(
            job_id=doc["job_id"],
            filename=doc.get("filename"),
            status=DocumentStatus(doc["status"]),
            document_type=doc.get("document_type"),
            confidence_score=doc.get("confidence_score"),
            extracted_fields=extracted_fields,
            container_number=container_number,
            company=company,
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


class DocumentUpdateRequest(BaseModel):
    document_type: Optional[str] = None
    ocr_text: Optional[str] = None
    extracted_fields: Optional[dict[str, str]] = None


class DocumentUpdateResponse(BaseModel):
    success: bool
    message: str


@app.post("/api/v1/documents/{job_id}", response_model=DocumentUpdateResponse)
async def update_document(
    job_id: str,
    request: DocumentUpdateRequest,
    customer_id: str = Depends(get_current_customer),
):
    """Update document metadata."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    # Check document exists
    result = supabase.table("ocr_documents").select("id").eq("job_id", job_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    # Build update data
    update_data = {}
    if request.document_type:
        update_data["document_type"] = request.document_type
    if request.ocr_text is not None:
        update_data["ocr_text"] = request.ocr_text
    if request.extracted_fields:
        update_data["status"] = "completed"

    if update_data:
        supabase.table("ocr_documents").update(update_data).eq("job_id", job_id).execute()

    return DocumentUpdateResponse(success=True, message=f"Document {job_id} updated")


@app.post("/api/v1/documents/{job_id}/review")
async def update_document_review(
    job_id: str,
    document_type: Optional[str] = None,
    customer_id: str = Depends(get_current_customer),
):
    """Update document for review - set document_type or mark for review."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    # Fetch document
    result = supabase.table("ocr_documents").select("*").eq("job_id", job_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    doc = result.data[0]

    # Update fields
    update_data = {"status": "review"}
    if document_type:
        update_data["document_type"] = document_type

    supabase.table("ocr_documents").update(update_data).eq("job_id", job_id).execute()

    return {"success": True, "message": f"Document {job_id} updated"}


@app.get("/api/v1/review/documents", response_model=DocumentListResponse)
async def get_review_documents(
    limit: int = 50,
    offset: int = 0,
    customer_id: str = Depends(get_current_customer),
):
    """Get all documents in review status."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    result = supabase.table("ocr_documents").select("*")\
        .eq("status", "review")\
        .order("created_at", desc=True)\
        .limit(limit)\
        .offset(offset)\
        .execute()

    if not result.data:
        return DocumentListResponse(documents=[], total=0)

    doc_ids = [doc["id"] for doc in result.data]

    # Batch fetch all extracted fields
    fields_result = supabase.table("ocr_extracted_fields").select("*").in_("document_id", doc_ids).execute()
    fields_by_doc = {}
    for f in fields_result.data:
        doc_id = f["document_id"]
        if doc_id not in fields_by_doc:
            fields_by_doc[doc_id] = {}
        fields_by_doc[doc_id][f["field_name"]] = f["field_value"]

    # Get all container numbers and batch fetch companies
    container_numbers = set()
    for doc in result.data:
        fields = fields_by_doc.get(doc["id"], {})
        cn = fields.get("container_number")
        if cn:
            container_numbers.add(cn)

    company_by_container = {}
    if container_numbers:
        containers_result = supabase.table("containers").select('container_number,"Company"').in_(
            "container_number", list(container_numbers)
        ).execute()
        for c in containers_result.data:
            company_by_container[c["container_number"]] = c.get("Company")

    documents = []
    for doc in result.data:
        extracted_fields = fields_by_doc.get(doc["id"], {})
        container_number = extracted_fields.get("container_number")
        company = company_by_container.get(container_number) if container_number else None

        documents.append(StatusResponse(
            job_id=doc["job_id"],
            filename=doc.get("filename"),
            status=DocumentStatus(doc["status"]),
            document_type=doc.get("document_type"),
            confidence_score=doc.get("confidence_score"),
            extracted_fields=extracted_fields,
            container_number=container_number,
            company=company,
            ocr_text=doc.get("ocr_text"),
            error_message=doc.get("error_message"),
            processed_at=doc.get("processed_at"),
            created_at=doc["created_at"],
        ))

    return DocumentListResponse(documents=documents, total=len(documents))


@app.get("/api/v1/failed/documents", response_model=DocumentListResponse)
async def get_failed_documents(
    limit: int = 50,
    offset: int = 0,
    customer_id: str = Depends(get_current_customer),
):
    """Get all documents in failed status."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    result = supabase.table("ocr_documents").select("*")\
        .eq("status", "failed")\
        .order("created_at", desc=True)\
        .limit(limit)\
        .offset(offset)\
        .execute()

    if not result.data:
        return DocumentListResponse(documents=[], total=0)

    doc_ids = [doc["id"] for doc in result.data]

    # Batch fetch all extracted fields
    fields_result = supabase.table("ocr_extracted_fields").select("*").in_("document_id", doc_ids).execute()
    fields_by_doc = {}
    for f in fields_result.data:
        doc_id = f["document_id"]
        if doc_id not in fields_by_doc:
            fields_by_doc[doc_id] = {}
        fields_by_doc[doc_id][f["field_name"]] = f["field_value"]

    # Get all container numbers and batch fetch companies
    container_numbers = set()
    for doc in result.data:
        fields = fields_by_doc.get(doc["id"], {})
        cn = fields.get("container_number")
        if cn:
            container_numbers.add(cn)

    company_by_container = {}
    if container_numbers:
        containers_result = supabase.table("containers").select('container_number,"Company"').in_(
            "container_number", list(container_numbers)
        ).execute()
        for c in containers_result.data:
            company_by_container[c["container_number"]] = c.get("Company")

    documents = []
    for doc in result.data:
        extracted_fields = fields_by_doc.get(doc["id"], {})
        container_number = extracted_fields.get("container_number")
        company = company_by_container.get(container_number) if container_number else None

        documents.append(StatusResponse(
            job_id=doc["job_id"],
            filename=doc.get("filename"),
            status=DocumentStatus(doc["status"]),
            document_type=doc.get("document_type"),
            confidence_score=doc.get("confidence_score"),
            extracted_fields=extracted_fields,
            container_number=container_number,
            company=company,
            ocr_text=doc.get("ocr_text"),
            error_message=doc.get("error_message"),
            processed_at=doc.get("processed_at"),
            created_at=doc["created_at"],
        ))

    return DocumentListResponse(documents=documents, total=len(documents))


@app.get("/api/v1/documents/{job_id}/file")
async def get_document_file(
    job_id: str,
    customer_id: str = Depends(get_current_customer),
):
    """Serve the original document file."""
    from fastapi.responses import FileResponse, StreamingResponse
    from shared.storage import get_storage

    storage = get_storage()

    # Check processed first, then pending
    processed_path = storage.processed_path / f"{job_id}.pdf"
    if processed_path.exists():
        return FileResponse(
            path=str(processed_path),
            filename=f"{job_id}.pdf",
            media_type="application/pdf"
        )

    # Check pending (customer subdirectory)
    for cust_dir in storage.pending_path.iterdir():
        if cust_dir.is_dir():
            pending_file = cust_dir / f"{job_id}.pdf"
            if pending_file.exists():
                return FileResponse(
                    path=str(pending_file),
                    filename=f"{job_id}.pdf",
                    media_type="application/pdf"
                )

    raise HTTPException(status_code=404, detail="File not found")


@app.get("/api/v1/containers/search")
async def search_containers(
    q: str = "",
    limit: int = 10,
    customer_id: str = Depends(get_current_customer),
):
    """Search containers by container number or other fields."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    if not q or len(q) < 2:
        return {"containers": [], "total": 0}

    # Search by container number (partial match)
    result = supabase.table("containers").select("*").ilike(
        "container_number", f"%{q}%"
    ).limit(limit).execute()

    return {"containers": result.data, "total": len(result.data)}


class DocumentSaveRequest(BaseModel):
    document_type: Optional[str] = None
    container_number: Optional[str] = None
    chassis_number: Optional[str] = None
    terminal: Optional[str] = None
    seal_number: Optional[str] = None
    vessel_voyage: Optional[str] = None
    driver_name: Optional[str] = None
    gate_in: Optional[str] = None
    gate_out: Optional[str] = None
    notes: Optional[str] = None
    ocr_text: Optional[str] = None
    # Additional fields for various document types
    invoice_number: Optional[str] = None
    amount: Optional[str] = None
    company: Optional[str] = None
    receipt_number: Optional[str] = None
    reference_number: Optional[str] = None
    rate: Optional[str] = None
    fuel_type: Optional[str] = None
    location: Optional[str] = None
    weight: Optional[str] = None
    load_number: Optional[str] = None
    pickup_location: Optional[str] = None
    delivery_location: Optional[str] = None
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    yard_location: Optional[str] = None
    time: Optional[str] = None


@app.post("/api/v1/documents/{job_id}/save")
async def save_document_review(
    job_id: str,
    request: DocumentSaveRequest,
    customer_id: str = Depends(get_current_customer),
):
    """Save reviewed document data including extracted fields."""
    supabase = SupabaseClientFactory.get_client(customer_id)

    # Check document exists
    result = supabase.table("ocr_documents").select("id").eq("job_id", job_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Job not found")

    doc_id = result.data[0]["id"]

    # Update document
    update_data = {
        "status": "verified",
        "document_type": request.document_type,
        "ocr_text": request.ocr_text,
    }
    supabase.table("ocr_documents").update(update_data).eq("job_id", job_id).execute()

    # Save extracted fields
    fields_to_save = {
        "container_number": request.container_number,
        "chassis_number": request.chassis_number,
        "terminal": request.terminal,
        "seal_number": request.seal_number,
        "vessel_voyage": request.vessel_voyage,
        "driver_name": request.driver_name,
        "gate_in": request.gate_in,
        "gate_out": request.gate_out,
        "notes": request.notes,
        "invoice_number": request.invoice_number,
        "amount": request.amount,
        "company": request.company,
        "receipt_number": request.receipt_number,
        "reference_number": request.reference_number,
        "rate": request.rate,
        "fuel_type": request.fuel_type,
        "location": request.location,
        "weight": request.weight,
        "load_number": request.load_number,
        "pickup_location": request.pickup_location,
        "delivery_location": request.delivery_location,
        "appointment_date": request.appointment_date,
        "appointment_time": request.appointment_time,
        "yard_location": request.yard_location,
        "time": request.time,
    }

    # Remove None values
    fields_to_save = {k: v for k, v in fields_to_save.items() if v is not None}

    # Delete existing fields for this document
    supabase.table("ocr_extracted_fields").delete().eq("document_id", doc_id).execute()

    # Insert new fields
    for field_name, field_value in fields_to_save.items():
        supabase.table("ocr_extracted_fields").insert([{
            "document_id": doc_id,
            "field_name": field_name,
            "field_value": str(field_value),
            "confidence": 1.0,  # Manual entry = 100% confidence
        }]).execute()

    return {"success": True, "message": f"Document {job_id} saved"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=9000)
