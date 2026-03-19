"""
API Keys router — API key management endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..audit_log import log_api_key_created, log_api_key_revoked
from ..saas import AuthContext, generate_api_key
from ..schemas import (
    AdminApiKeyCreateRequest,
    AdminApiKeyCreateResponse,
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyInfo,
    ApiKeyListResponse,
)

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["api-keys"])


def _key_to_info(key_row: dict) -> ApiKeyInfo:
    return ApiKeyInfo(
        id=key_row["id"],
        prefix=key_row["prefix"],
        name=key_row.get("name", ""),
        created_at=key_row["created_at"],
        last_used_at=key_row.get("last_used_at"),
        revoked_at=key_row.get("revoked_at"),
    )


@router.get("/api-keys", response_model=ApiKeyListResponse)
def list_api_keys(request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    keys = db.list_api_keys_for_tenant(auth.tenant_id)
    return ApiKeyListResponse(
        items=[_key_to_info(k) for k in keys],
    )


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: str, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    success = db.revoke_api_key(key_id, auth.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    log_api_key_revoked(key_id, auth.tenant_id, auth.api_key_id)
    return {"status": "revoked", "key_id": key_id}


@router.post("/api-keys", response_model=ApiKeyCreateResponse)
def create_api_key(req: ApiKeyCreateRequest, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    plain_key, hashed_key, prefix, last4 = generate_api_key()

    db.create_api_key(
        tenant_id=auth.tenant_id,
        hashed_key=hashed_key,
        prefix=prefix,
        name=req.name or "",
    )

    log_api_key_created(prefix, auth.tenant_id, auth.api_key_id)

    return ApiKeyCreateResponse(
        api_key=plain_key,
        id=prefix,
        name=req.name or "",
        message="Store this key securely. It will not be shown again.",
    )


@router.post("/admin/api-keys", response_model=AdminApiKeyCreateResponse)
def admin_create_api_key(req: AdminApiKeyCreateRequest, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    plain_key, hashed_key, prefix, last4 = generate_api_key()

    org_id = db.get_or_create_org(name=req.org_name, plan_id=req.plan_id)

    db.create_api_key(
        tenant_id=org_id,
        hashed_key=hashed_key,
        prefix=prefix,
        name=req.name or f"Key for {req.org_name}",
    )

    return AdminApiKeyCreateResponse(
        api_key=plain_key,
        id=prefix,
        name=req.name or f"Key for {req.org_name}",
        org_id=org_id,
        message="Store this key securely. It will not be shown again.",
    )
