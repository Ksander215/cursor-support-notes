"""
Notifications router — notification settings endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..audit_log import AuditAction, log_event
from ..saas import AuthContext
from ..schemas import (
    NotificationSettingsCreate,
    NotificationSettingsResponse,
    NotificationSettingsUpdate,
)

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["notifications"])


@router.get("/notifications", response_model=list[NotificationSettingsResponse])
def list_notification_settings(request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    settings = db.list_notification_settings(auth.tenant_id)
    return [NotificationSettingsResponse.model_validate(s) for s in settings]


@router.post("/notifications", response_model=NotificationSettingsResponse)
def create_notification_settings(
    req: NotificationSettingsCreate,
    request: Request,
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    settings = db.create_notification_settings(
        tenant_id=auth.tenant_id,
        provider=req.provider,
        events=[e.value if hasattr(e, "value") else e for e in req.events],
        config=req.config,
    )

    log_event(
        action=AuditAction.NOTIFICATION_SETTINGS_CREATED,
        tenant_id=auth.tenant_id,
        api_key_id=auth.api_key_id,
        details={"provider": req.provider},
    )

    return NotificationSettingsResponse.model_validate(settings)


@router.patch("/notifications/{settings_id}", response_model=NotificationSettingsResponse)
def update_notification_settings(
    settings_id: int,
    req: NotificationSettingsUpdate,
    request: Request,
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    settings = db.get_notification_settings(settings_id, auth.tenant_id)
    if not settings:
        raise HTTPException(status_code=404, detail="Notification settings not found")

    updated = db.update_notification_settings(
        settings_id=settings_id,
        tenant_id=auth.tenant_id,
        events=[e.value if hasattr(e, "value") else e for e in req.events]
        if req.events is not None
        else None,
        config=req.config,
        enabled=req.enabled,
    )

    return NotificationSettingsResponse.model_validate(updated)


@router.delete("/notifications/{settings_id}")
def delete_notification_settings(settings_id: int, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    success = db.delete_notification_settings(settings_id, auth.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification settings not found")

    return {"status": "deleted"}
