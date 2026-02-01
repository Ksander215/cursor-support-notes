import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from . import db

API_KEY_HEADER = "x-api-key"


@dataclass(frozen=True)
class AuthContext:
    org_id: int
    tenant_id: int
    api_key_id: str
    api_key_prefix: str
    plan_code: str
    requests_per_minute: int | None
    monthly_audits_quota: int | None
    concurrency_limit: int | None
    is_admin: bool


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


def static_api_key() -> str:
    """
    Optional static API key for the whole API (quick protection).
    If set, we accept exactly this key in X-API-Key / Authorization: Bearer.
    """
    return os.getenv("SEC_SCANNER_API_KEY", "").strip()


def require_api_key() -> bool:
    # When true, /api/v1/* becomes API-key protected.
    if static_api_key():
        return True
    return _bool_env("SEC_SCANNER_REQUIRE_API_KEY", default=False)


def api_key_pepper() -> str:
    # IMPORTANT: set in production; dev default is intentionally weak.
    return os.getenv("SEC_SCANNER_API_KEY_PEPPER", "dev-insecure-pepper")


def extract_api_key(request: Request) -> str | None:
    # Preferred: X-API-Key
    raw = request.headers.get(API_KEY_HEADER)
    if raw:
        return raw.strip()

    # Also support Authorization: Bearer <key>
    auth = request.headers.get("authorization")
    if auth:
        parts = auth.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1].strip()
    return None


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256((api_key_pepper() + raw_key).encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str, str, str]:
    """
    Returns: (plain_key, hashed_key, prefix, last4)
    """
    plain = f"sk_{secrets.token_urlsafe(32)}"
    return plain, hash_api_key(plain), plain[:12], plain[-4:]


def month_bucket_start(now: datetime | None = None) -> datetime:
    n = now or datetime.now(UTC)
    return datetime(n.year, n.month, 1, tzinfo=UTC)


_REDIS = None


def _get_async_redis():
    global _REDIS
    if _REDIS is not None:
        return _REDIS
    url = os.getenv("SEC_SCANNER_REDIS_URL", "").strip()
    if not url:
        return None
    try:
        import redis.asyncio as redis  # type: ignore

        _REDIS = redis.from_url(url, encoding="utf-8", decode_responses=True)
        return _REDIS
    except Exception:
        # If redis isn't available, we skip rate limiting (still enforce DB quotas).
        return None


async def enforce_rpm_or_raise(api_key_id: str, limit: int) -> None:
    if limit <= 0:
        return
    r = _get_async_redis()
    if r is None:
        return
    window = int(time.time() // 60)
    k = f"rl:{api_key_id}:{window}"
    try:
        n = await r.incr(k)
        if n == 1:
            await r.expire(k, 70)
        if n > limit:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
    except HTTPException:
        raise
    except Exception:
        # Redis errors shouldn't take down the API.
        return


def load_auth_context_or_none(raw_key: str) -> AuthContext | None:
    # Static key mode (no DB needed)
    sk = static_api_key()
    if sk:
        if hmac.compare_digest(sk, raw_key):
            # Minimal context; quotas are not enforced in static mode.
            return AuthContext(
                org_id=0,
                tenant_id=0,
                api_key_id="static",
                api_key_prefix="static",
                plan_code="static",
                requests_per_minute=None,
                monthly_audits_quota=None,
                concurrency_limit=None,
                is_admin=True,
            )
        return None

    ctx = db.get_api_key_context_by_hash(hash_api_key(raw_key))
    if not ctx:
        return None
    return AuthContext(**ctx)


def _path_requires_auth(path: str) -> bool:
    """Paths that require API key auth: /api/v1/*, /stripe/* and /payments/* except webhooks."""
    if not path:
        return False
    if path.startswith("/api/v1"):
        return True
    if "/webhook" in path:
        return False  # Stripe/YooKassa webhooks use signature, not API key
    if path.startswith("/stripe") or path.startswith("/payments"):
        return True
    return False


async def saas_http_middleware(request: Request, call_next):
    """
    - Optional API key auth for /api/v1/*, /stripe/*, /payments/* (except webhook paths).
    - If key present: validate, attach tenant context, enforce rpm, record request usage.
    - If key missing:
        - allow (default) OR reject if SEC_SCANNER_REQUIRE_API_KEY=true
    """
    path = request.url.path or ""
    if not _path_requires_auth(path):
        return await call_next(request)

    raw_key = extract_api_key(request)
    if not raw_key:
        if require_api_key():
            return JSONResponse(status_code=401, content={"detail": "API key required"})
        request.state.auth = None
        request.state.tenant_id = None
        request.state.api_key_id = None
        return await call_next(request)

    auth = load_auth_context_or_none(raw_key)
    if not auth:
        return JSONResponse(status_code=401, content={"detail": "invalid API key"})

    request.state.auth = auth
    request.state.tenant_id = auth.tenant_id
    request.state.api_key_id = auth.api_key_id
    request.state.tenant_info = {"org_id": auth.org_id}

    if auth.requests_per_minute is not None:
        try:
            await enforce_rpm_or_raise(auth.api_key_id, auth.requests_per_minute)
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

    # Record monthly request usage (best-effort)
    try:
        db.increment_usage(
            org_id=auth.org_id,
            api_key_id=auth.api_key_id,
            metric="requests",
            bucket_start=month_bucket_start(),
            amount=1,
        )
    except Exception:
        pass

    return await call_next(request)
