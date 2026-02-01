import logging
import os

from celery import Celery
from celery.signals import task_postrun, task_prerun

from .logging_config import set_request_id

# Setup logging for Celery worker
logger = logging.getLogger("sec_scanner.celery")


def get_redis_url() -> str:
    return os.getenv("SEC_SCANNER_REDIS_URL", "redis://localhost:6379/0")


celery_app = Celery(
    "sec_scanner",
    broker=get_redis_url(),
    backend=get_redis_url(),
    include=["src.sec_scanner.tasks"],
)
# Tasks are auto-discovered from src.sec_scanner.tasks module

celery_app.conf.update(
    task_track_started=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, **kwargs):
    """Set request ID for Celery task (use task_id as request_id)."""
    if task_id:
        set_request_id(f"celery-{task_id}")


@task_postrun.connect
def task_postrun_handler(sender=None, task_id=None, **kwargs):
    """Clear request ID after task completion."""
    set_request_id(None)
