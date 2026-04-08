"""Celery application configuration."""
import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery(
    "ocr_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["worker.tasks"],
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
    worker_prefetch_multiplier=1,  # Prevent worker from grabbing too many tasks
    task_acks_late=True,  # Acknowledge after task completion
    task_reject_on_worker_lost=True,
)

# Task routes for per-customer routing (future use)
celery_app.conf.task_routes = {}

# Beat schedule for periodic tasks (email polling, etc.)
celery_app.conf.beat_schedule = {
    "check-email-accounts": {
        "task": "api.email_consumer.check_all_customers",
        "schedule": 60.0,  # Every 60 seconds
    },
}
