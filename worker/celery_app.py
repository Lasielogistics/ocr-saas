"""Celery worker configuration and tasks."""
import os
import sys
from pathlib import Path

# Add parent directory to path so 'worker' module can be found
sys.path.insert(0, str(Path(__file__).parent.parent))

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "ocr_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

# Celery configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # 9 minutes soft limit
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
