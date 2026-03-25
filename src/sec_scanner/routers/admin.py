"""
Admin router — admin-only endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Query, Request

from .. import db
from ..audit_log import AuditAction, AuditStatus, log_event
from ..saas import AuthContext
from ..schemas import AuditLogEntry, AuditLogListResponse

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["admin"])


@router.get(
    "/admin/audit-logs",
    response_model=AuditLogListResponse,
    summary="Get audit logs (admin)",
    description="Retrieve security audit logs. Requires admin privileges.",
)
def get_audit_logs(
    request: Request,
    action: str | None = Query(None, description="Filter by action type"),
    actor_id: str | None = Query(None, description="Filter by actor ID"),
    resource_type: str | None = Query(None, description="Filter by resource type"),
    resource_id: str | None = Query(None, description="Filter by resource ID"),
    status: str | None = Query(None, description="Filter by status"),
    org_id: int | None = Query(None, description="Filter by organization ID"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin API key required")

    log_event(
        request=request,
        action=AuditAction.ADMIN_ACCESS,
        resource_type="audit_logs",
        details={"filters": {"action": action, "org_id": org_id, "limit": limit, "offset": offset}},
        status=AuditStatus.SUCCESS,
    )

    logs, total = db.get_audit_logs(
        org_id=org_id,
        action=action,
        actor_id=actor_id,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        limit=limit,
        offset=offset,
    )

    return AuditLogListResponse(
        items=[AuditLogEntry(**log) for log in logs],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(logs)) < total,
    )
