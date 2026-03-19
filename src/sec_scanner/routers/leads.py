"""
Leads router — lead capture endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..audit_log import AuditAction, log_event
from ..schemas import (
    LeadChecklistRequest,
    LeadChecklistResponse,
    LeadFreeScanRequest,
    LeadFreeScanResponse,
    LeadFreeScanStatusResponse,
)
from ..service import enqueue_audit
from ..targets import normalize_target

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["leads"])


@router.post("/leads/free-scan", response_model=LeadFreeScanResponse)
def lead_free_scan(req: LeadFreeScanRequest, request: Request):
    try:
        normalize_target(req.target)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit_id = enqueue_audit(req.target, "safe", tenant_id=None, created_by_api_key_id=None)

    db.create_lead(
        email=req.email,
        source="free_scan",
        target=req.target,
        audit_id=audit_id,
        metadata={"company": req.company, "role": req.role},
    )

    log_event(
        action=AuditAction.AUDIT_CREATED,
        tenant_id=None,
        api_key_id=None,
        details={"audit_id": audit_id, "target": req.target, "email": req.email},
    )

    return LeadFreeScanResponse(
        audit_id=audit_id,
        message="Free scan started. We'll notify you at your email when it's ready.",
    )


@router.get("/leads/free-scan/{audit_id}/status", response_model=LeadFreeScanStatusResponse)
def lead_free_scan_status(audit_id: str, request: Request):
    audit = db.get_audit(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return LeadFreeScanStatusResponse(
        audit_id=audit_id,
        status=audit["status"],
        overall_score=audit.get("overall_score"),
        risk_level=audit.get("risk_level"),
    )


@router.post("/leads/checklist", response_model=LeadChecklistResponse)
def lead_checklist(req: LeadChecklistRequest, request: Request):
    db.create_lead(
        email=req.email,
        source="checklist",
        metadata={
            "company": req.company,
            "role": req.role,
            "checklist_items": req.checklist_items,
        },
    )

    log_event(
        action=AuditAction.LEAD_CREATED,
        tenant_id=None,
        api_key_id=None,
        details={"email": req.email, "source": "checklist"},
    )

    return LeadChecklistResponse(
        message="Thank you! Check your email for the security checklist PDF.",
    )
