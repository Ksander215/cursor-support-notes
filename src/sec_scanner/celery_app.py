import os

from celery import Celery


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

