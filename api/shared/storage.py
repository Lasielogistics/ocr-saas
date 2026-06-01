"""File storage utilities for OCR SaaS."""
import hashlib
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional, List

from PIL import Image
from pdf2image import convert_from_path


class FileStorage:
    """Handles file storage operations for OCR processing."""

    def __init__(self, base_path: str = "/data/ocr"):
        self.base_path = Path(base_path)
        self.pending_path = self.base_path / "pending"
        self.temp_path = self.base_path / "temp"
        self.processed_path = self.base_path / "processed"
        self.review_path = self.base_path / "review"

    def ensure_directories(self) -> None:
        """Ensure all storage directories exist."""
        for path in [self.pending_path, self.temp_path, self.processed_path, self.review_path]:
            path.mkdir(parents=True, exist_ok=True)

    def save_upload(self, file_content: bytes, filename: str, customer_id: str) -> tuple[str, str]:
        """
        Save uploaded file to pending directory.

        Returns:
            tuple of (job_id, file_path)
        """
        job_id = str(uuid.uuid4())[:12]
        customer_pending = self.pending_path / customer_id
        customer_pending.mkdir(parents=True, exist_ok=True)

        ext = Path(filename).suffix.lower()
        stored_filename = f"{job_id}{ext}"
        file_path = customer_pending / stored_filename

        with open(file_path, "wb") as f:
            f.write(file_content)

        return job_id, str(file_path)

    def move_to_temp(self, file_path: str, job_id: str) -> str:
        """Move file to temp directory for processing."""
        source = Path(file_path)
        ext = source.suffix
        dest = self.temp_path / f"{job_id}{ext}"
        shutil.move(str(source), str(dest))
        return str(dest)

    def move_to_processed(self, file_path: str, job_id: str) -> str:
        """Move processed file to completed directory."""
        source = Path(file_path)
        ext = source.suffix
        dest = self.processed_path / f"{job_id}{ext}"

        # If source doesn't exist, file may have already been moved
        if not source.exists():
            if dest.exists():
                return str(dest)
            raise FileNotFoundError(f"Source file not found: {source}")

        shutil.move(str(source), str(dest))
        return str(dest)

    def move_to_review(self, file_path: str, job_id: str, error_type: str) -> str:
        """Move failed file to review directory with error prefix."""
        source = Path(file_path)
        ext = source.suffix
        dest = self.review_path / f"{error_type}_{job_id}{ext}"

        # If source doesn't exist, file may have already been moved (e.g., from a retry)
        if not source.exists():
            # Check if it's already in review
            if dest.exists():
                return str(dest)
            raise FileNotFoundError(f"Source file not found: {source}")

        shutil.move(str(source), str(dest))
        return str(dest)

    def compute_hash(self, file_path: str) -> str:
        """Compute SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def get_file_extension(self, filename: str) -> str:
        """Get lowercase file extension."""
        return Path(filename).suffix.lower()

    def is_supported_file(self, filename: str) -> bool:
        """Check if file type is supported for OCR."""
        supported_extensions = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
        return self.get_file_extension(filename) in supported_extensions

    def split_pdf(self, file_path: str, customer_id: str) -> List[dict]:
        """
        Split a multi-page PDF into individual page files.

        Args:
            file_path: Path to the multi-page PDF
            customer_id: Customer ID for directory structure

        Returns:
            List of dicts with 'job_id' and 'file_path' for each page
        """
        source_path = Path(file_path)
        if source_path.suffix.lower() != ".pdf":
            return [{"job_id": source_path.stem, "file_path": str(source_path)}]

        # Convert PDF to images
        images = convert_from_path(str(source_path), dpi=200)
        page_count = len(images)

        if page_count <= 1:
            return [{"job_id": source_path.stem, "file_path": str(source_path)}]

        # Create customer pending directory
        customer_pending = self.pending_path / customer_id
        customer_pending.mkdir(parents=True, exist_ok=True)

        pages = []
        for page_num in range(page_count):
            # Create unique job_id for each page
            job_id = f"{source_path.stem[:8]}_p{page_num + 1:03d}"

            # Save individual page as PNG (better quality for OCR)
            page_path = customer_pending / f"{job_id}.png"
            images[page_num].save(page_path, "PNG")

            pages.append({
                "job_id": job_id,
                "file_path": str(page_path),
                "page_number": page_num + 1,
                "total_pages": page_count,
            })

        return pages

    def save_page_from_pdf(self, pdf_path: str, page_num: int, customer_id: str) -> tuple:
        """
        Save a single page from a multi-page PDF.

        Args:
            pdf_path: Path to the source PDF
            page_num: 0-indexed page number
            customer_id: Customer ID for directory structure

        Returns:
            tuple of (job_id, file_path)
        """
        source_path = Path(pdf_path)
        images = convert_from_path(str(source_path), dpi=200)

        if page_num >= len(images):
            raise ValueError(f"Page {page_num} does not exist in PDF (has {len(images)} pages)")

        # Create job_id
        job_id = f"{source_path.stem[:8]}_p{page_num + 1:03d}"

        # Create customer pending directory
        customer_pending = self.pending_path / customer_id
        customer_pending.mkdir(parents=True, exist_ok=True)

        # Save as PNG
        page_path = customer_pending / f"{job_id}.png"
        images[page_num].save(page_path, "PNG")

        return job_id, str(page_path)


# Global storage instance
_storage: Optional[FileStorage] = None


def get_storage() -> FileStorage:
    """Get global storage instance."""
    global _storage
    if _storage is None:
        _storage = FileStorage()
        _storage.ensure_directories()
    return _storage
