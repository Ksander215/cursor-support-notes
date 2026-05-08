import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any

from . import db
from .security_agent import SecurityAgentV2
from .targets import normalize_target
from .telegram_alerts import telegram_alerts
from .websocket_manager import notify_progress, notify_scan_complete

logger = logging.getLogger("sec_scanner")

_executor: ThreadPoolExecutor | None = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4)
    return _executor


def _make_progress_callback(audit_id: str, steps: list[str]):
    """Create progress callback for SecurityAgentV2.audit_domain()"""
    completed_steps = [0]
    total = len(steps)
    
    def on_progress(
        step_name: str,
        step_status: str,
        step_progress: int | None = None,
        step_message: str | None = None,
        total_steps: int | None = None,
        completed_steps: int | None = None,
    ):
        ts = total_steps if total_steps is not None else total
        cs = completed_steps if completed_steps is not None else completed_steps[0]
        
        _update_progress(
            audit_id, step_name, step_status,
            step_progress=step_progress,
            step_message=step_message,
            total_steps=ts,
            completed_steps=cs,
        )
        
        if step_status == "completed":
            completed_steps[0] += 1
    
    return on_progress


def _update_progress(
    audit_id: str,
    step_name: str,
    step_status: str,
    step_progress: int | None = None,
    step_message: str | None = None,
    step_error: str | None = None,
    total_steps: int = 5,
    completed_steps: int = 0,
) -> None:
    """
    Update progress in both database and WebSocket.
    This ensures both polling clients and WebSocket clients receive updates.
    """
    # Update database first (authoritative source)
    if step_error:
        db.update_scan_progress_step(
            audit_id=audit_id,
            step_name=step_name,
            step_status=step_status,
            step_error=step_error,
        )
    else:
        db.update_scan_progress_step(
            audit_id=audit_id,
            step_name=step_name,
            step_status=step_status,
            step_progress=step_progress,
            step_message=step_message,
        )

    # Calculate overall progress
    if step_status == "completed":
        base_progress = ((completed_steps + 1) / total_steps) * 100
    elif step_status == "running" and step_progress is not None:
        base_progress = (completed_steps / total_steps) * 100 + (step_progress / total_steps)
    else:
        base_progress = (completed_steps / total_steps) * 100

    overall_progress = min(int(base_progress), 100)

    # Notify WebSocket clients (fire-and-forget, non-blocking)
    try:
        notify_progress(
            audit_id=audit_id,
            step_name=step_name,
            step_status=step_status,
            step_progress=step_progress,
            message=step_message or step_error,
            overall_progress=overall_progress,
        )
    except Exception as e:
        logger.debug(f"Failed to notify WebSocket: {e}")


def run_audit(audit_id: str, target: str, mode: str) -> None:
    try:
        host, _display = normalize_target(target)
        db.mark_started(audit_id)

        logger.info("Audit started: %s target=%s mode=%s", audit_id, host, mode)

        # Initialize progress steps based on mode
        steps = ["ssl", "headers"]
        if mode in ["normal", "full"]:
            steps.append("ports")
        if mode == "full":
            steps.append("web_vulnerabilities")
        steps.append("report")

        # Initialize all steps as pending
        for step_name in steps:
            db.create_scan_progress(
                audit_id=audit_id,
                step_name=step_name,
                step_status="pending",
            )

        # Create agent and run audit with progress callback
        agent = SecurityAgentV2(mode=mode)
        callback = _make_progress_callback(audit_id, steps)
        results = agent.audit_domain(host, on_progress=callback)
        results["audit_id"] = f"{host}_{audit_id}"

        # Get audit row to find tenant_id
        audit_row = db.get_audit(audit_id)
        tenant_id = audit_row.get("tenant_id") if audit_row else None

        db.mark_completed(
            audit_id,
            overall_score=results.get("overall_score"),
            risk_level=results.get("risk_level"),
            result=results,
            report_md=results.get("report_md"),
        )
        logger.info("Audit completed: %s score=%s", audit_id, results.get("overall_score"))

        # Notify WebSocket clients that scan is complete
        try:
            notify_scan_complete(
                audit_id=audit_id,
                status="completed",
                score=results.get("overall_score"),
            )
        except Exception as e:
            logger.debug(f"Failed to notify WebSocket completion: {e}")

        # Send Telegram alert for scan completion (sync wrapper)
        try:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(
                telegram_alerts.send_scan_complete(
                    audit_id=audit_id,
                    target=target,
                    risk_level=results.get("risk_level", "UNKNOWN"),
                    score=results.get("overall_score"),
                )
            )
        except Exception as e:
            logger.warning(f"Failed to send Telegram alert: {e}")

        # Trigger notifications if tenant_id is present
        if tenant_id:
            _trigger_scan_notifications(tenant_id, audit_id, target, results)
    except Exception as e:
        logger.exception("Audit failed: %s", audit_id)

        # Send Telegram alert for critical error (sync wrapper)
        try:
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(
                telegram_alerts.send_error(
                    error=f"Audit scan failed: {audit_id}",
                    details={
                        "audit_id": audit_id,
                        "target": target,
                        "mode": mode,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    },
                    critical=True,
                )
            )
        except Exception as alert_error:
            logger.warning(f"Failed to send Telegram alert: {alert_error}")

        # Mark current running step as failed
        try:
            progress_steps = db.get_scan_progress(audit_id)
            running_step = next((s for s in progress_steps if s["step_status"] == "running"), None)
            if running_step:
                db.update_scan_progress_step(
                    audit_id=audit_id,
                    step_name=running_step["step_name"],
                    step_status="failed",
                    step_error=str(e),
                )
        except Exception:
            pass  # Don't fail if progress update fails
        db.mark_failed(audit_id, str(e))

        # Notify WebSocket clients that scan failed
        try:
            notify_scan_complete(
                audit_id=audit_id,
                status="failed",
                score=None,
            )
        except Exception:
            pass  # Don't fail if WebSocket notification fails


def _trigger_scan_notifications(
    tenant_id: int, audit_id: str, target: str, result: dict[str, Any]
) -> None:
    """Trigger notifications for scan completion and vulnerabilities"""
    import os

    overall_score = result.get("overall_score")
    risk_level = result.get("risk_level", "").upper()
    critical_issues = result.get("critical_issues", [])
    critical_issues_count = len(critical_issues) if isinstance(critical_issues, list) else 0

    # Build report URL (assuming API base URL from env or default)
    api_base = os.getenv("SEC_SCANNER_API_BASE_URL", "https://api.sec-scanner.pro")
    report_url = f"{api_base}/app/audits?id={audit_id}"

    # Base notification data
    base_data = {
        "audit_id": audit_id,
        "target": target,
        "overall_score": overall_score,
        "risk_level": risk_level,
        "report_url": report_url,
    }

    # Check if Redis/Celery is available for async notifications
    redis_url = os.getenv("SEC_SCANNER_REDIS_URL", "").strip()

    if redis_url:
        # Async path: use Celery task
        from .tasks import send_notification_task

        # Send scan_completed notification
        send_notification_task.delay(tenant_id, "scan_completed", base_data)

        # Send vulnerability notifications if found
        if critical_issues_count > 0:
            vulnerability_data = {
                **base_data,
                "vulnerability_count": critical_issues_count,
                "critical_issues": critical_issues[:5],  # Limit to first 5
            }
            send_notification_task.delay(
                tenant_id, "critical_vulnerability_found", vulnerability_data
            )
        elif risk_level == "HIGH":
            send_notification_task.delay(tenant_id, "high_vulnerability_found", base_data)
    else:
        # Sync path: send directly (for dev/testing)
        from .notifications.service import send_notification

        send_notification(tenant_id, "scan_completed", base_data)

        if critical_issues_count > 0:
            vulnerability_data = {
                **base_data,
                "vulnerability_count": critical_issues_count,
                "critical_issues": critical_issues[:5],
            }
            send_notification(tenant_id, "critical_vulnerability_found", vulnerability_data)
        elif risk_level == "HIGH":
            send_notification(tenant_id, "high_vulnerability_found", base_data)


def enqueue_audit(
    target: str,
    mode: str,
    *,
    tenant_id: int | None = None,
    created_by_api_key_id: str | None = None,
) -> str:
    audit_id = db.create_audit(
        target=target, mode=mode, tenant_id=tenant_id, created_by_api_key_id=created_by_api_key_id
    )
    redis_url = os.getenv("SEC_SCANNER_REDIS_URL", "").strip()
    if redis_url:
        # async path (production): celery task
        from .tasks import run_audit_task

        run_audit_task.delay(audit_id, target, mode)
    else:
        # dev fallback
        get_executor().submit(run_audit, audit_id, target, mode)
    return audit_id
