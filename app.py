import ipaddress
import logging
import os
import socket
import uuid
from collections.abc import Iterable
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.sec_scanner import db as sec_db
from src.sec_scanner.api import router as sec_scanner_router
from src.sec_scanner.api_payments import router as payments_router
from src.sec_scanner.api_stripe import router as stripe_router
from src.sec_scanner.logging_config import set_request_id, setup_structured_logging
from src.sec_scanner.saas import saas_http_middleware

APP_NAME = os.getenv("APP_NAME", "sec-scanner.pro API")
WEB_CHECK_BASE_URL = os.getenv("WEB_CHECK_BASE_URL", "http://web-check:3000")

# Setup structured logging (JSON format if LOG_FORMAT=json, otherwise standard)
use_json_logging = os.getenv("LOG_FORMAT", "json").lower() == "json"
setup_structured_logging(use_json=use_json_logging)

logger = logging.getLogger("sec_scanner")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # init local sqlite (for audit history)
    sec_db.init_db()
    yield


app = FastAPI(title=APP_NAME, lifespan=lifespan)

# Host header hardening (prevents Host-header attacks)
_allowed_hosts_raw = os.getenv("SEC_SCANNER_ALLOWED_HOSTS", "").strip()
allowed_hosts = (
    [h.strip() for h in _allowed_hosts_raw.split(",") if h.strip()]
    if _allowed_hosts_raw
    else ["api.sec-scanner.pro", "sec-scanner.pro", "localhost", "127.0.0.1"]
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)

# CORS (restricted; UI is served same-origin via /web-check/)
_cors_origins_raw = os.getenv("SEC_SCANNER_CORS_ORIGINS", "").strip()
cors_origins = (
    [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
    if _cors_origins_raw
    else ["https://api.sec-scanner.pro", "https://sec-scanner.pro"]
)
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )


# Request ID middleware (must be before other middleware)
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """
    Generate and attach request ID to each request.
    Adds X-Request-ID header to response.
    """
    # Get or generate request ID
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    set_request_id(request_id)

    # Process request
    response = await call_next(request)

    # Add request ID to response headers
    response.headers["X-Request-ID"] = request_id

    return response


# SaaS scaffold: optional API key auth + usage/rate-limit hooks for /api/v1/*
app.middleware("http")(saas_http_middleware)

# attach sec-scanner API
app.include_router(sec_scanner_router)

# attach Stripe API (payment processing) - legacy, kept for backward compatibility
app.include_router(stripe_router)

# attach Payments API (supports multiple providers: Stripe, YooKassa)
app.include_router(payments_router)


@app.get("/")
def root():
    # UX: landing redirect for api.sec-scanner.pro/
    return RedirectResponse(url="/docs", status_code=302)


@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz(request: Request):
    """
    Basic health check endpoint.
    Returns 200 if the service is running (does not check dependencies).
    """
    if request.method == "HEAD":
        return Response(status_code=200)
    return {"ok": True}


@app.api_route("/readyz", methods=["GET", "HEAD"])
async def readyz(request: Request):
    """
    Readiness check endpoint.
    Returns 200 if all dependencies (PostgreSQL, Redis) are available.
    Returns 503 if any dependency is unavailable.
    """
    if request.method == "HEAD":
        # For HEAD requests, just return status code
        try:
            await _check_readiness()
            return Response(status_code=200)
        except Exception:
            return Response(status_code=503)

    try:
        await _check_readiness()
        return {"ok": True, "status": "ready"}
    except Exception as e:
        return JSONResponse(
            status_code=503, content={"ok": False, "status": "not_ready", "error": str(e)}
        )


async def _check_readiness() -> None:
    """
    Check readiness of all dependencies.
    Raises exception if any dependency is unavailable.
    """
    # Check PostgreSQL
    try:
        engine = sec_db.get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()  # Ensure query executes
            conn.commit()
    except Exception as e:
        raise Exception(f"PostgreSQL unavailable: {e}") from e

    # Check Redis (if configured)
    redis_url = os.getenv("SEC_SCANNER_REDIS_URL", "").strip()
    if redis_url:
        try:
            import redis.asyncio as redis  # type: ignore

            r = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
            await r.ping()
            await r.aclose()
        except Exception as e:
            raise Exception(f"Redis unavailable: {e}") from e


@app.get("/web-check")
def web_check_root():
    # Convenience redirect so /web-check opens the UI
    return RedirectResponse(url="/web-check/")


def _filter_hop_by_hop_headers(headers: Iterable[tuple[str, str]]) -> dict:
    # RFC 7230 hop-by-hop headers must not be forwarded by proxies
    hop_by_hop = {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailers",
        "transfer-encoding",
        "upgrade",
        "host",
    }
    out: dict = {}
    for k, v in headers:
        if k.lower() in hop_by_hop:
            continue
        out[k] = v
    return out


def _is_public_ip(ip: str) -> bool:
    """
    SSRF guard: allow only globally-routable IPs by default.
    Blocks loopback/private/link-local/multicast/reserved/CGNAT/etc.
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False

    # Hard block common metadata endpoint even if classification changes
    if str(addr) == "169.254.169.254":
        return False

    return bool(getattr(addr, "is_global", False))


def _resolve_all_ips(host: str) -> set[str]:
    """Resolve hostname to all IP addresses."""
    ips: set[str] = set()
    try:
        for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(host, None):
            if family == socket.AF_INET or family == socket.AF_INET6:
                ips.add(sockaddr[0])
    except Exception:
        return set()
    return ips


def _validate_url_for_ssrf(raw_url: str, allow_private: bool = False) -> None:
    """
    Validate URL to prevent SSRF attacks.
    Raises HTTPException if URL is invalid or points to private resources.
    """
    if not raw_url or not raw_url.strip():
        raise HTTPException(status_code=400, detail="URL is required")

    # Normalize URL
    url_str = raw_url.strip()
    if not url_str.startswith(("http://", "https://")):
        url_str = f"https://{url_str}"

    try:
        parsed = urlparse(url_str)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    # Check protocol
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http and https protocols are allowed")

    # Check for credentials in URL
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Credentials in URL are not allowed")

    # Extract hostname
    hostname = (parsed.hostname or "").strip().lower()
    if not hostname:
        raise HTTPException(status_code=400, detail="Invalid URL hostname")

    if allow_private:
        return

    # Check for localhost/local domains
    if hostname in ("localhost",) or hostname.endswith((".local", ".internal")):
        raise HTTPException(status_code=400, detail="Private targets are not allowed")

    # Check if hostname is an IP address
    try:
        ip_addr = ipaddress.ip_address(hostname)
        if not _is_public_ip(str(ip_addr)):
            raise HTTPException(status_code=400, detail="Private targets are not allowed")
        return
    except ValueError:
        # Not an IP, resolve DNS
        pass

    # Resolve DNS and check all IPs
    ips = _resolve_all_ips(hostname)
    if not ips:
        raise HTTPException(status_code=400, detail="Failed to resolve hostname")

    for ip in ips:
        if not _is_public_ip(ip):
            raise HTTPException(status_code=400, detail="Private targets are not allowed")


@app.api_route("/web-check/{path:path}", methods=["GET", "HEAD", "OPTIONS"])
async def web_check_proxy(path: str, request: Request):
    """
    Reverse-proxy to Web-Check service (port 3000).
    This allows exposing Web-Check under the same domain via a single ingress / reverse proxy.

    SSRF Protection: Validates URLs in query parameters before proxying to prevent SSRF attacks.
    """
    if request.method == "OPTIONS":
        return Response(status_code=204)

    # Extract and validate URL from query parameters (web-check uses ?url=...)
    allow_private = os.getenv("WC_ALLOW_PRIVATE_TARGETS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )

    if request.url.query:
        query_params = parse_qs(request.url.query)
        # Check for 'url' parameter (web-check API uses this)
        if query_params.get("url"):
            url_to_check = query_params["url"][0]
            try:
                _validate_url_for_ssrf(url_to_check, allow_private=allow_private)
            except HTTPException as e:
                return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

        # Also check for other common URL parameters that might be used
        for param_name in ["target", "domain", "host"]:
            if query_params.get(param_name):
                url_to_check = query_params[param_name][0]
                # Only validate if it looks like a URL
                if "://" in url_to_check or "." in url_to_check:
                    try:
                        _validate_url_for_ssrf(url_to_check, allow_private=allow_private)
                    except HTTPException as e:
                        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

    upstream_url = f"{WEB_CHECK_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    if request.url.query:
        upstream_url = f"{upstream_url}?{request.url.query}"

    headers = _filter_hop_by_hop_headers(request.headers.items())

    async with httpx.AsyncClient(
        follow_redirects=False,
        timeout=httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0),
    ) as client:
        upstream = await client.request(
            method=request.method,
            url=upstream_url,
            headers=headers,
            content=None,
        )

    response_headers = _filter_hop_by_hop_headers(upstream.headers.items())
    media_type = upstream.headers.get("content-type")

    # Stream response to support large payloads
    return StreamingResponse(
        content=iter([upstream.content]),
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=media_type,
    )
