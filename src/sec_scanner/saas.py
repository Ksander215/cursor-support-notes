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
    pepper = os.getenv("SEC_SCANNER_API_KEY_PEPPER", "").strip()
    if not pepper:
        raise RuntimeError(
            "SEC_SCANNER_API_KEY_PEPPER environment variable must be set in production. "
            'Generate a secure random value: python -c "import secrets; print(secrets.token_urlsafe(32))"'
        )
    return pepper


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
    """Paths that require API key auth: /api/v1/*, /stripe/* and /payments/* except webhooks and public endpoints."""
    if not path:
        return False
    if path.startswith("/api/v1"):
        # Exempt n8n webhooks - they use internal API key or no auth
        if "/leads/webhook/n8n/" in path:
            return False
        return True
    if "/webhook" in path:
        return False  # Stripe/YooKassa webhooks use signature, not API key
    # Public payment endpoints (digital products catalog and purchase)
    if path.startswith("/payments/products"):
        return False  # Public: catalog and purchase endpoints
    if path.startswith("/stripe") or path.startswith("/payments"):
        return True
    return False


def _check_api_key_in_url(request: Request) -> str | None:
    """
    Security check: Detect API keys passed in URL query parameters.

    API keys in URLs are a security risk because:
    - They appear in server access logs
    - They're visible in browser history
    - They can leak via Referer headers
    - They're exposed in monitoring/analytics tools

    Returns error message if API key detected, None otherwise.
    """
    query = request.url.query or ""
    if not query:
        return None

    query_lower = query.lower()

    # Common API key parameter names to block
    dangerous_params = (
        "api_key=",
        "apikey=",
        "api-key=",
        "key=",
        "token=",
        "access_token=",
        "auth_token=",
        "secret=",
        "x-api-key=",
    )

    for param in dangerous_params:
        if param in query_lower:
            # Additional check: ensure it's a parameter (not part of a value)
            # e.g., "redirect_url=https://example.com?key=123" should not trigger
            # but "key=sk_xxx" should
            import re

            # Match parameter at start or after &
            pattern = rf"(^|&){re.escape(param[:-1])}="
            if re.search(pattern, query_lower):
                return (
                    f"API keys must not be passed in URL query parameters. "
                    f"Use the X-API-Key header or Authorization: Bearer <key> instead. "
                    f"Detected parameter: {param[:-1]}"
                )

    return None


async def saas_http_middleware(request: Request, call_next):
    """
    SaaS authentication and rate limiting middleware.

    Features:
    - Rejects API keys in URL query parameters (security)
    - Optional API key auth for /api/v1/*, /stripe/*, /payments/* (except webhooks)
    - If key present: validate, attach tenant context, enforce rpm, record usage
    - If key missing: allow (default) OR reject if SEC_SCANNER_REQUIRE_API_KEY=true
    """
    path = request.url.path or ""

    # Security: Reject API keys in URL parameters
    # This applies to ALL paths, not just protected ones
    url_key_error = _check_api_key_in_url(request)
    if url_key_error:
        return JSONResponse(
            status_code=400,
            content={
                "detail": url_key_error,
                "error_code": "API_KEY_IN_URL",
                "hint": "Pass your API key in the X-API-Key header",
            },
        )

    if not _path_requires_auth(path):
        return await call_next(request)

    raw_key = extract_api_key(request)
    if not raw_key:
        if require_api_key():
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "API key required",
                    "error_code": "API_KEY_REQUIRED",
                    "hint": "Add X-API-Key header or Authorization: Bearer <key>",
                },
            )
        request.state.auth = None
        request.state.tenant_id = None
        request.state.api_key_id = None
        return await call_next(request)

    auth = load_auth_context_or_none(raw_key)
    if not auth:
        return JSONResponse(
            status_code=401,
            content={
                "detail": "Invalid API key",
                "error_code": "INVALID_API_KEY",
                "hint": "Check your API key in Settings → API keys or create a new one",
            },
        )

    request.state.auth = auth
    request.state.tenant_id = auth.tenant_id
    request.state.api_key_id = auth.api_key_id
    request.state.tenant_info = {"org_id": auth.org_id}

    if auth.requests_per_minute is not None:
        try:
            await enforce_rpm_or_raise(auth.api_key_id, auth.requests_per_minute)
        except HTTPException as e:
            content = {"detail": e.detail}
            if e.status_code == 429:
                content["error_code"] = "RATE_LIMIT_EXCEEDED"
                content["hint"] = (
                    "Wait until the next minute or upgrade your plan for higher limits"
                )
            resp = JSONResponse(status_code=e.status_code, content=content)
            if e.status_code == 429:
                resp.headers["Retry-After"] = "60"
            return resp

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
