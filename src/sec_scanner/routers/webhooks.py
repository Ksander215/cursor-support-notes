"""
Webhooks router — webhook endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..audit_log import log_event
from ..saas import AuthContext
from ..schemas import (
    WebhookCreate,
    WebhookListResponse,
    WebhookResponse,
    WebhookUpdate,
)

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["webhooks"])


@router.get("/webhooks", response_model=WebhookListResponse)
def list_webhooks(request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    webhooks = db.get_webhooks(org_id=auth.tenant_id)
    return WebhookListResponse(items=webhooks, total=len(webhooks))


@router.post("/webhooks", response_model=WebhookResponse)
def create_webhook(req: WebhookCreate, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    webhook = db.create_webhook(
        org_id=auth.tenant_id,
        url=req.url,
        events=[e.value if hasattr(e, "value") else e for e in req.events],
        secret=req.secret,
        enabled=req.enabled,
    )

    log_event(
        request=request,
        action="webhook.created",
        resource_type="webhook",
        resource_id=str(webhook["id"]),
        org_id=auth.tenant_id,
        details={"url": req.url},
    )

    return WebhookResponse(**webhook)


@router.get("/webhooks/{webhook_id}", response_model=WebhookResponse)
def get_webhook(webhook_id: int, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    webhook = db.get_webhook_by_id(webhook_id=webhook_id, org_id=auth.tenant_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return WebhookResponse(**webhook)


@router.patch("/webhooks/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    webhook_id: int,
    req: WebhookUpdate,
    request: Request,
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    webhook = db.get_webhook_by_id(webhook_id=webhook_id, org_id=auth.tenant_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    updated = db.update_webhook(
        webhook_id=webhook_id,
        org_id=auth.tenant_id,
        url=req.url,
        events=[e.value if hasattr(e, "value") else e for e in req.events]
        if req.events is not None
        else None,
        secret=req.secret,
        enabled=req.enabled,
    )

    return WebhookResponse(**updated)


@router.delete("/webhooks/{webhook_id}")
def delete_webhook(webhook_id: int, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    success = db.delete_webhook(webhook_id=webhook_id, org_id=auth.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return {"detail": "Webhook deleted"}
