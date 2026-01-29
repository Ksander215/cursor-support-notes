import logging
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from . import db
from .security_agent import SecurityAgentV2
from .targets import normalize_target


logger = logging.getLogger("sec_scanner")

_executor: Optional[ThreadPoolExecutor] = None


def get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=4)
    return _executor


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
        
        agent = SecurityAgentV2(mode=mode)
        
        # Run SSL scan with progress tracking
        db.update_scan_progress_step(
            audit_id=audit_id,
            step_name="ssl",
            step_status="running",
            step_progress=0,
            step_message="Scanning SSL certificate...",
        )
        ssl_results = agent.scanners["ssl"].scan(host)
        db.update_scan_progress_step(
            audit_id=audit_id,
            step_name="ssl",
            step_status="completed",
            step_progress=100,
            step_message="SSL scan completed",
        )
        
        # Run Headers scan with progress tracking
        db.update_scan_progress_step(
            audit_id=audit_id,
            step_name="headers",
            step_status="running",
            step_progress=0,
            step_message="Scanning security headers...",
        )
        headers_results = agent.scanners["headers"].scan(host)
        db.update_scan_progress_step(
            audit_id=audit_id,
            step_name="headers",
            step_status="completed",
            step_progress=100,
            step_message="Security headers scan completed",
        )
        
        # Run Port scan if needed
        port_results = None
        if mode in ["normal", "full"]:
            db.update_scan_progress_step(
                audit_id=audit_id,
                step_name="ports",
                step_status="running",
                step_progress=0,
                step_message="Scanning open ports...",
            )
            port_results = agent.scanners["ports"].scan(host)
            db.update_scan_progress_step(
                audit_id=audit_id,
                step_name="ports",
                step_status="completed",
                step_progress=100,
                step_message="Port scan completed",
            )
        
        # Run Web Vulnerability scan if needed
        web_results = None
        if mode == "full":
            db.update_scan_progress_step(
                audit_id=audit_id,
                step_name="web_vulnerabilities",
                step_status="running",
                step_progress=0,
                step_message="Scanning web vulnerabilities...",
            )
            web_results = agent.scanners["web"].light_scan(host)
            db.update_scan_progress_step(
                audit_id=audit_id,
                step_name="web_vulnerabilities",
                step_status="completed",
                step_progress=100,
                step_message="Web vulnerability scan completed",
            )
        
        # Build results similar to SecurityAgentV2.audit_domain
        results = {
            "audit_id": f"{host}_{audit_id}",
            "domain": host,
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "categories": {},
        }
        
        results["categories"]["ssl"] = {
            "scanner": "AdvancedSSLScanner",
            "results": ssl_results,
            "score": agent.calculate_ssl_score(ssl_results),
        }
        
        results["categories"]["headers"] = {
            "scanner": "SecurityHeadersScanner",
            "results": headers_results,
            "score": (
                headers_results.get("security_score", 0)
                if headers_results.get("success")
                else 0
            ),
        }
        
        if mode in ["normal", "full"]:
            results["categories"]["ports"] = {
                "scanner": "SafePortScanner",
                "results": port_results,
                "score": (
                    port_results.get("security_score", 0)
                    if port_results and port_results.get("success")
                    else 0
                ),
            }
        else:
            results["categories"]["ports"] = {
                "scanner": "SafePortScanner",
                "skipped": "Port scanning disabled in safe mode",
                "score": 50,
            }
        
        if mode == "full":
            results["categories"]["web_vulnerabilities"] = {
                "scanner": "WebVulnerabilityScanner",
                "results": web_results,
                "score": (
                    web_results.get("security_score", 0) if web_results and web_results.get("success") else 0
                ),
            }
        else:
            results["categories"]["web_vulnerabilities"] = {
                "scanner": "WebVulnerabilityScanner",
                "skipped": f"Web vulnerability scanning requires full mode (current: {mode})",
                "score": 50,
            }
        
        results["overall_score"] = agent.calculate_overall_score(results["categories"])
        results["risk_level"] = agent.determine_risk_level(results["overall_score"])
        results["critical_issues"] = agent.find_critical_issues(results["categories"])
        results["recommendations"] = agent.generate_recommendations(results["categories"])
        
        # Generate report with progress tracking
        db.update_scan_progress_step(
            audit_id=audit_id,
            step_name="report",
            step_status="running",
            step_progress=0,
            step_message="Generating report...",
        )
        results["report_md"] = agent.generate_comprehensive_report(results)
        db.update_scan_progress_step(
            audit_id=audit_id,
            step_name="report",
            step_status="completed",
            step_progress=100,
            step_message="Report generated",
        )

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

        # Trigger notifications if tenant_id is present
        if tenant_id:
            _trigger_scan_notifications(tenant_id, audit_id, target, results)
    except Exception as e:  # noqa: B110
        logger.exception("Audit failed: %s", audit_id)
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


def _trigger_scan_notifications(tenant_id: int, audit_id: str, target: str, result: Dict[str, Any]) -> None:
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
            send_notification_task.delay(tenant_id, "critical_vulnerability_found", vulnerability_data)
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
    tenant_id: Optional[int] = None,
    created_by_api_key_id: Optional[str] = None,
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

