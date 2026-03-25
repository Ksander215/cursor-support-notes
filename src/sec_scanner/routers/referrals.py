"""
Referrals router — referral system endpoints.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from .. import db
from ..saas import AuthContext
from ..schemas import ReferralStatsResponse

logger = logging.getLogger("sec_scanner")

router = APIRouter(prefix="/api/v1", tags=["referrals"])


@router.get("/referrals/stats", response_model=ReferralStatsResponse)
def get_referral_stats(request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    stats = db.get_referral_stats(auth.tenant_id)
    return ReferralStatsResponse(
        referral_code=stats.get("referral_code", ""),
        total_referrals=stats.get("total_referrals", 0),
        total_commission=stats.get("total_commission", 0.0),
        pending_commission=stats.get("pending_commission", 0.0),
        paid_commission=stats.get("paid_commission", 0.0),
    )


@router.post("/referrals/generate-code")
def generate_referral_code_endpoint(request: Request):
    auth: AuthContext | None = getattr(request.state, "auth", None)
    if not auth or auth.api_key_id == "static":
        raise HTTPException(status_code=401, detail="API key required")

    code = db.set_referral_code(auth.tenant_id)
    return {"referral_code": code, "message": "Referral code generated successfully"}
