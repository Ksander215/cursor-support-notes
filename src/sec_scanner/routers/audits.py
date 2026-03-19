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
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: str | None = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
):
    auth: AuthContext | None = getattr(request.state, "auth", None)

    if auth and auth.api_key_id != "static":
        items, total = db.list_audits(
            tenant_id=auth.tenant_id,
            limit=limit,
            offset=offset,
            status=status,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    else:
        items, total = db.list_audits(
            tenant_id=None,
            limit=limit,
            offset=offset,
            status=status,
            sort_by=sort_by,
            sort_order=sort_order,
        )

    return AuditListResponse(
        items=[_row_to_summary(r) for r in items],
        total=total,
        limit=limit,
        offset=offset,
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
    format: str = Query("json", pattern="^(json|markdown|pdf)$"),
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    row = db.get_audit(audit_id)
    if not row:
        raise HTTPException(status_code=404, detail="Audit not found")

    if auth and auth.api_key_id != "static":
        if row.get("tenant_id") and row.get("tenant_id") != auth.tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")

    export_format = ExportFormat.JSON
    if format == "markdown":
        export_format = ExportFormat.MARKDOWN
    elif format == "pdf":
        export_format = ExportFormat.PDF

    try:
        return export_audit_report(row, export_format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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

    quota = db.get_quota_info(auth.tenant_id)

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


def _check_fail_conditions(
    mode: str,
    tenant_id: int | None,
    created_by_api_key_id: str | None,
    target: str,
) -> None:
    """Check fail conditions for audit creation."""
    if mode not in ("safe", "fast", "full"):
        raise HTTPException(status_code=400, detail="Invalid scan mode")

    if not target:
        raise HTTPException(status_code=400, detail="Target is required")

    if tenant_id is None:
        return

    def fetch():
        return db.get_quota_info(tenant_id)

    quota = get_cached_audit_history(tenant_id, None, 1, fetch)
    if not quota:
        return

    if quota.get("monthly_audits_used", 0) >= (quota.get("monthly_audits_quota") or 0):
        raise HTTPException(
            status_code=429,
            detail="Monthly audit quota exceeded. Upgrade your plan for more audits.",
        )

    active_audits = db.count_running_audits(tenant_id)
    concurrency_limit = quota.get("concurrency_limit") or 1
    if active_audits >= concurrency_limit:
        raise HTTPException(
            status_code=429,
            detail=f"Concurrency limit reached ({active_audits}/{concurrency_limit}). "
            "Wait for current scans to complete.",
        )


@router.post("/ci/scan", response_model=CIScanResponse)
def ci_scan(req: CIScanRequest, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    tenant_id: int | None = None
    created_by_api_key_id: str | None = None
    if auth and auth.api_key_id != "static":
        tenant_id = auth.tenant_id
        created_by_api_key_id = auth.api_key_id

    _check_fail_conditions(req.mode, tenant_id, created_by_api_key_id, req.target)

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

    return CIScanResponse(
        audit_id=audit_id,
        status="queued",
        message="Audit queued. Poll /audits/{audit_id}/progress for status.",
    )
