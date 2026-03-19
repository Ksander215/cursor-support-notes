"""
Config router — white-label and configuration endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..saas import AuthContext
from ..schemas import WhiteLabelConfigResponse, WhiteLabelConfigUpdate

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["config"])


@router.get("/config/whitelabel", response_model=WhiteLabelConfigResponse)
def get_whitelabel_config(request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    config = db.get_white_label_config(auth.org_id)
    return WhiteLabelConfigResponse(**config)


@router.put("/config/whitelabel", response_model=WhiteLabelConfigResponse)
def update_whitelabel_config(req: WhiteLabelConfigUpdate, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    config = db.update_white_label_config(
        org_id=auth.org_id,
        logo_url=req.logo_url,
        primary_color=req.primary_color,
        company_name=req.company_name,
        custom_domain=req.custom_domain,
        enabled=req.enabled,
    )

    return WhiteLabelConfigResponse(**config)
