"""
Audits router — security audit endpoints.
"""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from .. import db
from ..cache import (
    get_cached_audit,
    get_cached_audit_history,
    invalidate_on_new_audit,
)
from ..exporters import ExportFormat, export_audit_report
from ..saas import AuthContext
from ..schemas import (
    AuditCreateRequest,
    AuditCreateResponse,
    AuditDetails,
    AuditHistoryItem,
    AuditHistoryResponse,
    AuditListResponse,
    AuditSummary,
    CIScanRequest,
    CIScanResponse,
    QuotaLimits,
    QuotaResponse,
    QuotaUsage,
    ScanProgressResponse,
    ScanProgressStep,
)
from ..service import enqueue_audit
from ..targets import normalize_target

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["audits"])


def _row_to_summary(row: dict[str, Any]) -> AuditSummary:
    return AuditSummary(
        id=row["id"],
        target=row["target"],
        mode=row["mode"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        overall_score=row.get("overall_score"),
        risk_level=row.get("risk_level"),
        error=row.get("error"),
    )


@router.post("/audits", response_model=AuditCreateResponse)
def create_audit(req: AuditCreateRequest, request: Request):
    try:
        normalize_target(req.target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    auth: AuthContext | None = getattr(request.state, "auth", None)
    tenant_id: int | None = None
    created_by_api_key_id: str | None = None
    if auth and auth.api_key_id != "static":
        tenant_id = auth.tenant_id
        created_by_api_key_id = auth.api_key_id

    audit_id = enqueue_audit(
        req.target,
        req.mode,
        tenant_id=tenant_id,
        created_by_api_key_id=created_by_api_key_id,
    )
    invalidate_on_new_audit(tenant_id)
    return AuditCreateResponse(audit_id=audit_id, status="queued")


@router.get("/audits", response_model=AuditListResponse)
def list_audits(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    include_total: bool = Query(False),
    status: str | None = None,
    target: str | None = None,
    mode: str | None = None,
    sort: str = Query("created_at"),
    order: str = Query("desc"),
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    tenant_id = (
        auth.tenant_id if auth and (auth.api_key_id != "static") and (not auth.is_admin) else None
    )

    items_list, has_more, total = db.list_audits(
        limit=limit,
        tenant_id=tenant_id,
        include_total=include_total,
        status=status,
        target=target,
        mode=mode,
        sort=sort,
        order=order,
    )

    return AuditListResponse(
        items=[_row_to_summary(r) for r in items_list],
        limit=limit,
        has_more=has_more,
        total=total,
    )


@router.get("/audits/{audit_id}", response_model=AuditDetails)
def get_audit(
    audit_id: str,
    request: Request,
    include_result: bool = False,
    include_report: bool = False,
):
    auth: AuthContext | None = getattr(request.state, "auth", None)

    def fetch():
        return db.get_audit(audit_id)

    row = get_cached_audit(audit_id, fetch) if include_result else fetch()
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")

    if auth and auth.api_key_id != "static":
        if row.get("tenant_id") and row.get("tenant_id") != auth.tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")

    details = AuditDetails(
        id=row["id"],
        target=row["target"],
        mode=row["mode"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row.get("started_at"),
        completed_at=row.get("completed_at"),
        overall_score=row.get("overall_score"),
        risk_level=row.get("risk_level"),
        critical_issues_count=row.get("critical_issues_count"),
        error=row.get("error"),
    )

    if include_result and row.get("status") == "completed":
        details.result = row.get("result")
        details.report_markdown = row.get("report_markdown")

    return details


@router.get("/audits/{audit_id}/report")
def get_audit_report(audit_id: str, request: Request):
    row = db.get_audit(audit_id)
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")

    auth: AuthContext | None = getattr(request.state, "auth", None)
    if auth and auth.api_key_id != "static":
        if row.get("tenant_id") and row.get("tenant_id") != auth.tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")

    if row.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Audit not completed yet")

    markdown = row.get("report_markdown") or "Report not available"
    return {"audit_id": audit_id, "report": markdown}


@router.get("/audits/{audit_id}/export")
def export_audit(
    audit_id: str,
    request: Request,
    format: str = Query("markdown", pattern="^(pdf|json|markdown)$"),
):
    from fastapi import Response

    auth: AuthContext | None = getattr(request.state, "auth", None)
    row = db.get_audit(audit_id)
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")

    if auth and auth.api_key_id != "static" and not auth.is_admin:
        if row.get("tenant_id") and row.get("tenant_id") != auth.tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")

    if row.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Audit not completed yet")

    result_data = None
    if row.get("result_json") and isinstance(row.get("result_json"), dict):
        result_data = row["result_json"]

    report_md = row.get("report_md")

    white_label_config = None
    if auth and auth.tenant_id:
        org_info = db.get_org_by_id(auth.tenant_id)
        if org_info and org_info.get("white_label_config"):
            white_label_config = org_info["white_label_config"]

    export_format = ExportFormat.JSON
    if format == "markdown":
        export_format = ExportFormat.MARKDOWN
    elif format == "pdf":
        export_format = ExportFormat.PDF

    try:
        content_bytes, content_type = export_audit_report(
            audit_data=row,
            result_data=result_data,
            report_md=report_md,
            format=export_format,
            white_label_config=white_label_config,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    target = row.get("target", "audit").replace(".", "_").replace("/", "_")
    extension = format.lower()
    filename = f"security_audit_{target}_{audit_id[:8]}.{extension}"

    return Response(
        content=content_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/targets/{target}/history", response_model=AuditHistoryResponse)
def get_audit_history(
    target: str,
    request: Request,
    limit: int = Query(50, ge=1, le=500),
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    tenant_id = auth.tenant_id if auth and auth.api_key_id != "static" else None

    def fetch():
        return db.get_audit_history(target, limit=limit)

    history = get_cached_audit_history(target, tenant_id, limit, fetch)

    return AuditHistoryResponse(
        target=target,
        items=[AuditHistoryItem(**item) for item in history],
    )


@router.get("/audits/{audit_id}/progress", response_model=ScanProgressResponse)
def get_audit_progress(audit_id: str, request: Request):
    row = db.get_audit(audit_id)
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")

    auth: AuthContext | None = getattr(request.state, "auth", None)
    if auth and auth.api_key_id != "static":
        if row.get("tenant_id") and row.get("tenant_id") != auth.tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")

    steps = db.get_scan_progress(audit_id)
    total_steps = len(steps)
    completed_steps = sum(1 for s in steps if s["step_status"] == "completed")

    running_step = next((s for s in steps if s["step_status"] == "running"), None)
    if running_step:
        step_prog = running_step.get("step_progress") or 0
        overall = int((completed_steps / total_steps) * 100 + (step_prog / total_steps))
    else:
        overall = int((completed_steps / total_steps) * 100) if total_steps else 0

    return ScanProgressResponse(
        audit_id=audit_id,
        status=row["status"],
        overall_progress=overall,
        steps=[ScanProgressStep(**s) for s in steps],
    )


@router.get("/quota", response_model=QuotaResponse)
def get_quota(request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    quota = db.get_quota_info(tenant_id=auth.tenant_id)

    return QuotaResponse(
        org_id=auth.org_id,
        org_name="",
        plan_code=auth.plan_code,
        plan_name="",
        limits=QuotaLimits(
            requests_per_minute=auth.requests_per_minute,
            monthly_audits_quota=auth.monthly_audits_quota,
            concurrency_limit=auth.concurrency_limit,
        ),
        usage=QuotaUsage(
            requests=quota.get("requests_this_minute", 0) if quota else 0,
            audits_created=quota.get("monthly_audits_used", 0) if quota else 0,
            month_start=quota.get("month_start", "") if quota else "",
        ),
    )


def _check_quota_limits(
    mode: str,
    tenant_id: int | None,
    target: str,
) -> None:
    """Check quota limits for audit creation."""
    if mode not in ("safe", "fast", "full"):
        raise HTTPException(status_code=400, detail="Invalid scan mode")

    if not target:
        raise HTTPException(status_code=400, detail="Target is required")

    if tenant_id is None:
        return

    quota = db.get_quota_info(tenant_id=tenant_id)
    if not quota:
        return

    if quota.get("monthly_audits_used", 0) >= (quota.get("monthly_audits_quota") or 0):
        raise HTTPException(
            status_code=429,
            detail="Monthly audit quota exceeded. Upgrade your plan for more audits.",
        )

    active_audits = db.count_running_audits(tenant_id=tenant_id)
    concurrency_limit = quota.get("concurrency_limit") or 1
    if active_audits >= concurrency_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Concurrency limit reached ({active_audits}/{concurrency_limit}). "
            "Wait for current scans to complete.",
        )


def _check_ci_fail_conditions(
    audit_result: dict[str, Any], fail_on: list[str]
) -> tuple[bool, str | None]:
    """Check if audit result should fail CI/CD based on fail_on rules."""
    if not fail_on:
        return False, None

    overall_score = audit_result.get("overall_score")
    risk_level = audit_result.get("risk_level", "").upper()
    critical_issues = audit_result.get("critical_issues", [])
    critical_issues_count = len(critical_issues) if isinstance(critical_issues, list) else 0

    for rule in fail_on:
        rule_lower = rule.lower().strip()

        if rule_lower.startswith("score"):
            try:
                if "<=" in rule_lower:
                    threshold = float(rule_lower.split("<=")[1].strip())
                    if overall_score is not None and overall_score <= threshold:
                        return (
                            True,
                            f"Security score {overall_score:.1f} is below threshold {threshold}",
                        )
                elif "<" in rule_lower:
                    threshold = float(rule_lower.split("<")[1].strip())
                    if overall_score is not None and overall_score < threshold:
                        return (
                            True,
                            f"Security score {overall_score:.1f} is below threshold {threshold}",
                        )
            except (ValueError, IndexError):
                logger.warning("Invalid score threshold rule: %s", rule)
                continue

        elif rule_lower == "critical":
            if risk_level == "CRITICAL" or critical_issues_count > 0:
                return (
                    True,
                    f"Critical risk level detected (risk_level={risk_level}, critical_issues={critical_issues_count})",
                )
        elif rule_lower == "high":
            if risk_level in ["CRITICAL", "HIGH"]:
                return True, f"High or critical risk level detected (risk_level={risk_level})"
        elif rule_lower == "medium":
            if risk_level in ["CRITICAL", "HIGH", "MEDIUM"]:
                return True, f"Medium or higher risk level detected (risk_level={risk_level})"

    return False, None


@router.post("/ci/scan", response_model=CIScanResponse)
def ci_scan(req: CIScanRequest, request: Request):
    import time

    auth: AuthContext | None = getattr(request.state, "auth", None)
    tenant_id: int | None = None
    created_by_api_key_id: str | None = None
    if auth and auth.api_key_id != "static":
        tenant_id = auth.tenant_id
        created_by_api_key_id = auth.api_key_id

    _check_quota_limits(req.mode, tenant_id, req.target)

    try:
        normalize_target(req.target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_id = enqueue_audit(
        req.target,
        req.mode,
        tenant_id=tenant_id,
        created_by_api_key_id=created_by_api_key_id,
    )
    invalidate_on_new_audit(tenant_id)

    if not req.wait:
        return CIScanResponse(
            audit_id=audit_id,
            status="queued",
            passed=True,
            report_url=f"/app/audits?id={audit_id}",
        )

    timeout = req.timeout or 300
    start_time = time.time()
    poll_interval = 2

    while time.time() - start_time < timeout:
        audit_row = db.get_audit(audit_id)
        if not audit_row:
            raise HTTPException(status_code=404, detail="Audit not found")

        status = audit_row.get("status")
        if status == "completed":
            audit_details = db.get_audit(audit_id)
            if not audit_details:
                raise HTTPException(status_code=404, detail="Audit not found")

            result_json = audit_details.get("result_json")
            if not result_json or not isinstance(result_json, dict):
                return CIScanResponse(
                    audit_id=audit_id,
                    status="completed",
                    passed=True,
                    overall_score=audit_details.get("overall_score"),
                    risk_level=audit_details.get("risk_level"),
                    report_url=f"/app/audits?id={audit_id}",
                )

            should_fail, reason = _check_ci_fail_conditions(result_json, req.fail_on or [])
            critical_issues = result_json.get("critical_issues", [])
            critical_issues_count = len(critical_issues) if isinstance(critical_issues, list) else 0

            return CIScanResponse(
                audit_id=audit_id,
                status="completed",
                passed=not should_fail,
                overall_score=result_json.get("overall_score"),
                risk_level=result_json.get("risk_level"),
                critical_issues_count=critical_issues_count,
                failure_reason=reason,
                report_url=f"/app/audits?id={audit_id}",
            )
        elif status == "failed":
            return CIScanResponse(
                audit_id=audit_id,
                status="failed",
                passed=False,
                failure_reason=audit_row.get("error") or "Scan failed",
                report_url=f"/app/audits?id={audit_id}",
            )

        time.sleep(poll_interval)

    return CIScanResponse(
        audit_id=audit_id,
        status="running",
        passed=False,
        failure_reason=f"Scan timeout after {timeout} seconds",
        report_url=f"/app/audits?id={audit_id}",
    )
