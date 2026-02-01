from src.sec_scanner.celery_app import celery_app
from src.sec_scanner.service import run_audit


@celery_app.task(name="sec_scanner.run_audit")
def run_audit_task(audit_id: str, target: str, mode: str) -> None:
    run_audit(audit_id, target, mode)


@celery_app.task(name="sec_scanner.send_notification")
def send_notification_task(org_id: int, event: str, data: dict) -> int:
    """Celery task for sending notifications"""
    from src.sec_scanner.notifications.service import send_notification

    return send_notification(org_id, event, data)
