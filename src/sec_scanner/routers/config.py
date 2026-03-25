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
    if not auth or auth.api_key_id == "static" or auth.tenant_id is None:
        raise HTTPException(
            status_code=404,
            detail="white-label config not available (requires organization API key)",
        )

    org_info = db.get_org_by_id(auth.tenant_id)
    if not org_info:
        raise HTTPException(status_code=404, detail="Organization not found")

    white_label_config = org_info.get("white_label_config") or {}

    return WhiteLabelConfigResponse(
        company_name=white_label_config.get("company_name"),
        logo_url=white_label_config.get("logo_url"),
        primary_color=white_label_config.get("primary_color"),
    )


@router.put("/config/whitelabel", response_model=WhiteLabelConfigResponse)
def update_whitelabel_config(req: WhiteLabelConfigUpdate, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static" or auth.tenant_id is None:
        raise HTTPException(
            status_code=404,
            detail="white-label config not available (requires organization API key)",
        )

    if auth.plan_code != "enterprise":
        raise HTTPException(
            status_code=403,
            detail="White-label configuration is available only for Enterprise plan",
        )

    org_info = db.get_org_by_id(auth.tenant_id)
    if not org_info:
        raise HTTPException(status_code=404, detail="Organization not found")

    current_config = org_info.get("white_label_config") or {}

    new_config = {**current_config}
    if req.company_name is not None:
        new_config["company_name"] = req.company_name
    if req.logo_url is not None:
        new_config["logo_url"] = req.logo_url
    if req.primary_color is not None:
        new_config["primary_color"] = req.primary_color

    db.update_org_whitelabel_config(org_id=auth.tenant_id, config=new_config)

    return WhiteLabelConfigResponse(
        company_name=new_config.get("company_name"),
        logo_url=new_config.get("logo_url"),
        primary_color=new_config.get("primary_color"),
    )
