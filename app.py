import ipaddress
import logging
import os
import uuid
from collections.abc import Iterable
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy import text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.sec_scanner import db as sec_db
from src.sec_scanner.api_metrics import router as metrics_router
from src.sec_scanner.api_payments import router as payments_router
from src.sec_scanner.api_stripe import router as stripe_router
from src.sec_scanner.logging_config import set_request_id, setup_structured_logging
from src.sec_scanner.routers import (
    audits_router,
    config_router,
    keys_router,
    leads_router,
    notifications_router,
    referrals_router,
    webhooks_router,
)
from src.sec_scanner.saas import saas_http_middleware
from src.sec_scanner.security_headers import add_security_headers_middleware
from src.sec_scanner.websocket_manager import manager as ws_manager

APP_NAME = os.getenv("APP_NAME", "sec-scanner.pro API")
WEB_CHECK_BASE_URL = os.getenv("WEB_CHECK_BASE_URL", "http://web-check:3000")

# Setup structured logging (JSON format if LOG_FORMAT=json, otherwise standard)
use_json_logging = os.getenv("LOG_FORMAT", "json").lower() == "json"
setup_structured_logging(use_json=use_json_logging)

logger = logging.getLogger("sec_scanner")

# Sentry — error tracking and performance monitoring.
# Set SENTRY_DSN in .env.production to enable. No-op if unset.
_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if _sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=_sentry_dsn,
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
        profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0")),
        environment=os.getenv("ENVIRONMENT", "production"),
        integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        send_default_pii=False,
    )
    logger.info("Sentry initialized (env=%s)", os.getenv("ENVIRONMENT", "production"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Validate required security settings
    _check_security_config()

    # init local sqlite (for audit history)
    sec_db.init_db()

    # Start WebSocket manager for real-time progress updates
    try:
        await ws_manager.start_listener()
        logger.info("WebSocket manager started")
    except Exception as e:
        logger.warning(f"WebSocket manager failed to start: {e}")

    yield

    # Stop WebSocket manager
    try:
        await ws_manager.stop_listener()
        logger.info("WebSocket manager stopped")
    except Exception as e:
        logger.warning(f"WebSocket manager failed to stop: {e}")


def _check_security_config() -> None:
    """Validate critical security configuration at startup."""
    from src.sec_scanner.saas import api_key_pepper

    try:
        pepper = api_key_pepper()
        # Check pepper length (minimum 16 chars for security)
        if len(pepper) < 16:
            logger.warning(
                "SEC_SCANNER_API_KEY_PEPPER is too short. "
                "Use at least 16 characters for better security. "
                'Generate: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )
    except RuntimeError:
        # Pepper not set - this is expected in development
        pass


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
    else [
        "https://api.sec-scanner.pro",
        "https://sec-scanner.pro",
        # Development origins
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:4321",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:3001",
        "http://127.0.0.1:4321",
    ]
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

# Security headers middleware (fallback for development when not behind Nginx)
# In production, Nginx handles CSP and other security headers
add_security_headers_middleware(app)


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

# attach sec-scanner API routers
app.include_router(audits_router)
app.include_router(keys_router)
app.include_router(notifications_router)
app.include_router(webhooks_router)
app.include_router(referrals_router)
app.include_router(leads_router)
app.include_router(config_router)

# attach Stripe API (payment processing) - legacy, kept for backward compatibility
app.include_router(stripe_router)

# attach Payments API (supports multiple providers: Stripe, YooKassa)
app.include_router(payments_router)

# attach admin metrics API (requires admin API key)
app.include_router(metrics_router)


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


def _validate_url_for_ssrf(raw_url: str, allow_private: bool = False) -> None:
    """
    Validate URL to prevent SSRF attacks using DNS pinning.

    This function uses the dns_pinning module for DNS rebinding protection.
    DNS is resolved and pinned, preventing attackers from changing
    DNS records between validation and actual connection.

    Raises HTTPException if URL is invalid or points to private resources.
    """
    from src.sec_scanner.dns_pinning import is_public_ip, resolve_and_pin

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
        if not is_public_ip(str(ip_addr)):
            raise HTTPException(status_code=400, detail="Private targets are not allowed")
        return
    except ValueError:
        # Not an IP, resolve DNS with pinning
        pass

    # Resolve DNS with pinning and validate all IPs are public
    # This pins the DNS resolution to prevent DNS rebinding attacks
    try:
        entry = resolve_and_pin(hostname, validate_public=True)
        logger.debug(f"DNS pinned for {hostname}: {entry.all_addresses}")
    except ValueError as e:
        if "private" in str(e).lower():
            raise HTTPException(status_code=400, detail="Private targets are not allowed")
        if "resolve" in str(e).lower() or "DNS" in str(e):
            raise HTTPException(status_code=400, detail="Failed to resolve hostname")
        raise HTTPException(status_code=400, detail=str(e))


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


# --- WebSocket endpoint for real-time progress ---


@app.websocket("/ws/audits/{audit_id}/progress")
async def websocket_audit_progress(websocket: WebSocket, audit_id: str):
    """
    WebSocket endpoint for real-time audit progress updates.

    Connect to receive live progress updates for a specific audit.
    Messages are JSON with the following structure:

    Progress update:
    {
        "type": "progress",
        "audit_id": "...",
        "step_name": "ssl_scan",
        "step_status": "running",
        "step_progress": 45,
        "overall_progress": 30,
        "message": "Checking SSL certificate...",
        "timestamp": "2026-02-01T12:00:00Z"
    }

    Scan complete:
    {
        "type": "complete",
        "audit_id": "...",
        "status": "completed",
        "score": 85,
        "timestamp": "2026-02-01T12:05:00Z"
    }

    Connection will be closed when:
    - Scan completes (after sending 'complete' message)
    - Client disconnects
    - Server shuts down
    """
    # Validate audit_id format (basic UUID check)
    if not audit_id or len(audit_id) < 8:
        await websocket.close(code=4000, reason="Invalid audit_id")
        return

    # Check if audit exists
    audit = sec_db.get_audit(audit_id)
    if not audit:
        await websocket.close(code=4004, reason="Audit not found")
        return

    # Accept connection and register
    await ws_manager.connect(websocket, audit_id)

    try:
        # Send initial state if audit is already in progress
        if audit.get("status") == "running":
            progress_steps = sec_db.get_scan_progress(audit_id)
            if progress_steps:
                # Calculate overall progress
                total_steps = len(progress_steps)
                completed_steps = sum(1 for s in progress_steps if s["step_status"] == "completed")
                running_step = next(
                    (s for s in progress_steps if s["step_status"] == "running"), None
                )

                if running_step:
                    step_prog = running_step.get("step_progress") or 0
                    overall = int((completed_steps / total_steps) * 100 + (step_prog / total_steps))
                else:
                    overall = int((completed_steps / total_steps) * 100) if total_steps else 0

                # Send current state
                await websocket.send_json(
                    {
                        "type": "initial_state",
                        "audit_id": audit_id,
                        "status": audit.get("status"),
                        "steps": progress_steps,
                        "overall_progress": overall,
                    }
                )
        elif audit.get("status") in ("completed", "failed"):
            # Audit already finished, send complete message and close
            await websocket.send_json(
                {
                    "type": "complete",
                    "audit_id": audit_id,
                    "status": audit.get("status"),
                    "score": audit.get("score"),
                }
            )
            await websocket.close(code=1000, reason="Audit already completed")
            return

        # Keep connection alive and wait for messages from client
        # (mainly pings or disconnect signals)
        while True:
            try:
                # Wait for any message from client (ping/pong handling)
                data = await websocket.receive_text()
                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for audit {audit_id}: {e}")
    finally:
        ws_manager.disconnect(websocket, audit_id)
