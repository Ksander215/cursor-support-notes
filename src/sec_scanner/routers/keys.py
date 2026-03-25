"""
API Keys router — API key management endpoints.
"""

import logging
import uuid

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


@router.get("/api-keys", response_model=ApiKeyListResponse)
def list_api_keys(request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    keys_data = db.get_api_keys_by_org(auth.tenant_id)
    return ApiKeyListResponse(
        keys=[
            ApiKeyInfo(
                id=k["id"],
                name=k["name"],
                prefix=k["prefix"],
                last4=k["last4"],
                is_admin=k["is_admin"],
                created_at=k["created_at"],
            )
            for k in keys_data
        ]
    )


@router.delete("/api-keys/{key_id}")
def revoke_api_key(key_id: str, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    success = db.revoke_api_key(key_id, auth.tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")

    log_api_key_revoked(
        request=request,
        api_key_id=key_id,
        org_id=auth.tenant_id,
    )
    return {"detail": "API key revoked"}


@router.post("/api-keys", response_model=ApiKeyCreateResponse)
def create_api_key(req: ApiKeyCreateRequest, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth:
        raise HTTPException(status_code=401, detail="API key required")

    org_id: int

    if auth.api_key_id == "static" or auth.tenant_id is None or auth.tenant_id == 0:
        plan_id = db.upsert_plan(
            code="free",
            name="Free",
            requests_per_minute=None,
            monthly_audits_quota=None,
            concurrency_limit=None,
        )
        org_id = db.get_or_create_org(name="My Organization", plan_id=plan_id)
        if req.referral_code:
            db.register_referral(client_org_id=org_id, referral_code=req.referral_code)
    else:
        org_id = auth.tenant_id

    org_info = db.get_org_by_id(org_id)
    if not org_info:
        raise HTTPException(status_code=404, detail="Organization not found")

    plain, hashed, prefix, last4 = generate_api_key()
    api_key_id = str(uuid.uuid4())

    db.insert_api_key(
        api_key_id=api_key_id,
        org_id=org_id,
        name=req.key_name,
        prefix=prefix,
        last4=last4,
        hashed_key=hashed,
        is_admin=False,
    )

    log_api_key_created(
        request=request,
        api_key_id=api_key_id,
        org_id=org_id,
        key_name=req.key_name,
        is_admin=False,
    )

    return ApiKeyCreateResponse(
        api_key=plain,
        api_key_id=api_key_id,
        prefix=prefix,
        last4=last4,
        key_name=req.key_name,
    )


@router.post("/admin/api-keys", response_model=AdminApiKeyCreateResponse)
def admin_create_api_key(req: AdminApiKeyCreateRequest, request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or not auth.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    plan_id = db.upsert_plan(
        code=req.plan_code,
        name=req.plan_name,
        requests_per_minute=req.requests_per_minute,
        monthly_audits_quota=req.monthly_audits_quota,
        concurrency_limit=req.concurrency_limit,
    )
    org_id = db.get_or_create_org(name=req.org_name, plan_id=plan_id)

    plain, hashed, prefix, last4 = generate_api_key()
    api_key_id = str(uuid.uuid4())

    db.insert_api_key(
        api_key_id=api_key_id,
        org_id=org_id,
        name=req.key_name,
        prefix=prefix,
        last4=last4,
        hashed_key=hashed,
        is_admin=req.is_admin,
    )

    log_api_key_created(
        request=request,
        api_key_id=api_key_id,
        org_id=org_id,
        key_name=req.key_name,
        is_admin=req.is_admin,
    )

    return AdminApiKeyCreateResponse(
        api_key=plain,
        api_key_id=api_key_id,
        prefix=prefix,
        last4=last4,
        org_id=org_id,
        org_name=req.org_name,
        plan_code=req.plan_code,
    )
