"""
Notifications router — notification settings endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..audit_log import log_event
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
    if not auth or auth.api_key_id == "static" or auth.tenant_id is None:
        raise HTTPException(
            status_code=404,
            detail="notification settings not available (requires organization API key)",
        )

    settings_list = db.get_notification_settings(org_id=auth.tenant_id)
    return [
        NotificationSettingsResponse(
            id=s["id"],
            org_id=s["org_id"],
            channel=s["channel"],
            events=s["events"],
            enabled=s["enabled"],
            config=s["config"],
            created_at="",
            updated_at="",
        )
        for s in settings_list
    ]


@router.post("/notifications", response_model=NotificationSettingsResponse)
def create_notification_settings(
    req: NotificationSettingsCreate,
    request: Request,
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static" or auth.tenant_id is None:
        raise HTTPException(
            status_code=404,
            detail="notification settings not available (requires organization API key)",
        )

    from ..notifications.service import NotificationService

    provider = NotificationService.get_provider(req.channel)
    if not provider:
        raise HTTPException(status_code=400, detail=f"Unknown notification channel: {req.channel}")

    is_valid, error = provider.validate_config(req.config)
    if not is_valid:
        raise HTTPException(status_code=400, detail=f"Invalid configuration: {error}")

    settings_id = db.create_notification_settings(
        org_id=auth.tenant_id,
        channel=req.channel,
        events=req.events,
        enabled=req.enabled,
        config=req.config,
    )

    settings_list = db.get_notification_settings(org_id=auth.tenant_id)
    settings = next((s for s in settings_list if s["id"] == settings_id), None)
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    log_event(
        request=request,
        action="notification.created",
        resource_type="notification_settings",
        resource_id=str(settings_id),
        org_id=auth.tenant_id,
        details={"channel": str(req.channel)},
    )

    return NotificationSettingsResponse(
        id=settings["id"],
        org_id=settings["org_id"],
        channel=settings["channel"],
        events=settings["events"],
        enabled=settings["enabled"],
        config=settings["config"],
        created_at="",
        updated_at="",
    )


@router.patch("/notifications/{settings_id}", response_model=NotificationSettingsResponse)
def update_notification_settings(
    settings_id: int,
    req: NotificationSettingsUpdate,
    request: Request,
):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static" or auth.tenant_id is None:
        raise HTTPException(
            status_code=404,
            detail="notification settings not available (requires organization API key)",
        )

    settings_list = db.get_notification_settings(org_id=auth.tenant_id)
    if not any(s["id"] == settings_id for s in settings_list):
        raise HTTPException(status_code=404, detail="Settings not found")

    if req.config is not None:
        existing = next((s for s in settings_list if s["id"] == settings_id), None)
        if existing:
            from ..notifications.service import NotificationService

            provider = NotificationService.get_provider(existing["channel"])
            if provider:
                is_valid, error = provider.validate_config(req.config)
                if not is_valid:
                    raise HTTPException(status_code=400, detail=f"Invalid configuration: {error}")

    db.update_notification_settings(
        settings_id=settings_id,
        events=req.events,
        enabled=req.enabled,
        config=req.config,
    )

    settings_list = db.get_notification_settings(org_id=auth.tenant_id)
    settings = next((s for s in settings_list if s["id"] == settings_id), None)
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    return NotificationSettingsResponse(
        id=settings["id"],
        org_id=settings["org_id"],
        channel=settings["channel"],
        events=settings["events"],
        enabled=settings["enabled"],
        config=settings["config"],
        created_at="",
        updated_at="",
    )


@router.delete("/notifications/{settings_id}")
def delete_notification_settings(settings_id: int, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static" or auth.tenant_id is None:
        raise HTTPException(
            status_code=404,
            detail="notification settings not available (requires organization API key)",
        )

    settings_list = db.get_notification_settings(org_id=auth.tenant_id)
    if not any(s["id"] == settings_id for s in settings_list):
        raise HTTPException(status_code=404, detail="Settings not found")

    db.delete_notification_settings(settings_id=settings_id)

    log_event(
        request=request,
        action="notification.deleted",
        resource_type="notification_settings",
        resource_id=str(settings_id),
        org_id=auth.tenant_id,
    )

    return {"message": "Notification settings deleted"}
