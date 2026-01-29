import os
import logging
from contextlib import asynccontextmanager
from typing import Iterable, Tuple

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.sec_scanner import db as sec_db
from src.sec_scanner.api import router as sec_scanner_router
from src.sec_scanner.saas import saas_http_middleware


APP_NAME = os.getenv("APP_NAME", "sec-scanner.pro API")
WEB_CHECK_BASE_URL = os.getenv("WEB_CHECK_BASE_URL", "http://web-check:3000")

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

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
        allow_headers=["Content-Type", "X-API-Key", "Authorization"],
        max_age=600,
    )

# SaaS scaffold: optional API key auth + usage/rate-limit hooks for /api/v1/*
app.middleware("http")(saas_http_middleware)

# attach sec-scanner API
app.include_router(sec_scanner_router)


@app.get("/")
def root():
    # UX: landing redirect for api.sec-scanner.pro/
    return RedirectResponse(url="/docs", status_code=302)


@app.api_route("/healthz", methods=["GET", "HEAD"])
def healthz(request: Request):
    if request.method == "HEAD":
        return Response(status_code=200)
    return {"ok": True}


@app.get("/web-check")
def web_check_root():
    # Convenience redirect so /web-check opens the UI
    return RedirectResponse(url="/web-check/")


def _filter_hop_by_hop_headers(headers: Iterable[Tuple[str, str]]) -> dict:
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


@app.api_route("/web-check/{path:path}", methods=["GET", "HEAD", "OPTIONS"])
async def web_check_proxy(path: str, request: Request):
    """
    Reverse-proxy to Web-Check service (port 3000).
    This allows exposing Web-Check under the same domain via a single ingress / reverse proxy.
    """
    if request.method == "OPTIONS":
        return Response(status_code=204)

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

