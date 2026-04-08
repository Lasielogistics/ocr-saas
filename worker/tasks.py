"""OCR processing tasks for Celery worker."""
import logging
import os
import sys
from pathlib import Path
from typing import Optional

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from celery import Task
from celery_app import celery_app
from processor import OCRProcessor

logger = logging.getLogger(__name__)


class CallbackTask(Task):
    """Task with callback support for status updates."""

    def on_success(self, retval, task_id, args, kwargs):
        """Called on task success."""
        logger.info(f"Task {task_id} succeeded with result: {retval}")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called on task failure."""
        logger.error(f"Task {task_id} failed: {exc}")


@celery_app.task(
    bind=True,
    base=CallbackTask,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def process_document(self, job_id: str, customer_id: str, file_path: str) -> dict:
    """
    Main OCR processing task.

    Args:
        job_id: Unique job identifier
        customer_id: Customer identifier for Supabase routing
        file_path: Path to the document file

    Returns:
        dict with processing results
    """
    from shared.supabase import SupabaseClientFactory
    from shared.storage import get_storage

    logger.info(f"Processing job {job_id} for customer {customer_id}")

    # Initialize customer clients if not already done
    try:
        init_customer_clients()
    except Exception:
        pass  # Already initialized

    # Get customer Supabase client
    supabase = SupabaseClientFactory.get_client(customer_id)

    # Update status to processing
    supabase.table("ocr_documents").update({"status": "processing"}).eq("job_id", job_id).execute()

    try:
        # Process the document
        processor = OCRProcessor()
        result = processor.process(job_id, file_path)

        # Update with results
        update_data = {
            "status": "completed",
            "document_type": result["document_type"],
            "ocr_text": result["ocr_text"],
            "page_count": result["page_count"],
            "confidence_score": result["confidence_score"],
            "processed_at": "now()",
        }
        supabase.table("ocr_documents").update(update_data).eq("job_id", job_id).execute()

        # Insert extracted fields
        if result["extracted_fields"]:
            fields_to_insert = [
                {
                    "document_id": get_document_id(supabase, job_id),
                    "field_name": field["name"],
                    "field_value": field["value"],
                    "confidence": field["confidence"],
                    "page_number": field.get("page"),
                    "bbox": field.get("bbox"),
                }
                for field in result["extracted_fields"]
            ]
            supabase.table("ocr_extracted_fields").insert(fields_to_insert).execute()

        # Call webhook if configured
        doc = supabase.table("ocr_documents").select("webhook_url").eq("job_id", job_id).execute()
        if doc.data and doc.data[0].get("webhook_url"):
            call_webhook(doc.data[0]["webhook_url"], result)

        # Move file to processed
        storage = get_storage()
        storage.move_to_processed(file_path, job_id)

        logger.info(f"Job {job_id} completed successfully")
        return result

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")

        # Update status to failed
        supabase.table("ocr_documents").update({
            "status": "failed",
            "error_message": str(e),
        }).eq("job_id", job_id).execute()

        # Move file to review
        storage = get_storage()
        storage.move_to_review(file_path, job_id, "failed")

        raise


def get_document_id(supabase, job_id: str) -> str:
    """Get document UUID by job_id."""
    result = supabase.table("ocr_documents").select("id").eq("job_id", job_id).execute()
    if result.data:
        return result.data[0]["id"]
    raise ValueError(f"Document not found for job_id: {job_id}")


def call_webhook(webhook_url: str, result: dict) -> None:
    """Call webhook with result."""
    import httpx
    try:
        httpx.post(webhook_url, json=result, timeout=10)
    except Exception as e:
        logger.warning(f"Webhook call failed: {e}")


def init_customer_clients():
    """Initialize customer clients from config file."""
    from shared.supabase import SupabaseClientFactory
    import json
    from pathlib import Path

    # Try multiple paths for the config file
    config_paths = [
        Path(__file__).parent.parent / "shared" / "customers.json",
        Path("/app/shared/customers.json"),
        Path("/app/worker/customers.json"),
    ]

    for config_path in config_paths:
        if config_path.exists():
            SupabaseClientFactory.load_customers_from_file(str(config_path))
            return

    raise FileNotFoundError("Could not find customers.json config file")
