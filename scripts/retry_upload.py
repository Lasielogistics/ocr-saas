#!/usr/bin/env python3
"""Retry uploading all remaining files in pending folder."""
import os
import sys
import time
from pathlib import Path

import requests

API_BASE = "http://localhost:3000/api/v1"
CUSTOMER_ID = "cust_test_001"
API_KEY = "ocr_test_key_123"
PENDING_DIR = Path("/data/ocr/pending")


def upload_file(filepath: Path, timeout=120) -> dict:
    """Upload a single file to the OCR API."""
    filesize = filepath.stat().st_size / (1024*1024)
    print(f"  Uploading {filepath.name} ({filesize:.1f} MB)...")
    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f)}
        headers = {"X-API-Key": API_KEY}
        response = requests.post(
            f"{API_BASE}/upload",
            files=files,
            headers=headers,
            timeout=timeout
        )
    return response.json()


def main():
    # Find all PDF files in pending directory and subdirectories
    files = []
    for ext in ("*.pdf", "*.jpg", "*.jpeg", "*.png", "*.tiff", "*.tif", "*.bmp"):
        files.extend(PENDING_DIR.glob(ext))
        for subdir in PENDING_DIR.iterdir():
            if subdir.is_dir():
                files.extend(subdir.glob(ext))

    # Deduplicate
    files = sorted(set(files))
    total = len(files)

    print(f"Found {total} files in pending folder")
    print(f"Uploading to {API_BASE}")
    print("-" * 50)

    success = 0
    failed = 0
    skipped = 0

    for i, filepath in enumerate(files, 1):
        try:
            result = upload_file(filepath, timeout=120)
            if "job_id" in result:
                print(f"[{i}/{total}] OK: {filepath.name} -> job_id={result['job_id']}")
                success += 1
            else:
                print(f"[{i}/{total}] FAIL: {filepath.name} -> {result}")
                failed += 1
        except Exception as e:
            print(f"[{i}/{total}] ERROR: {filepath.name} -> {e}")
            failed += 1

        # Small delay to avoid overwhelming the API
        if i % 10 == 0:
            time.sleep(0.5)

    print("-" * 50)
    print(f"Done: {success} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
