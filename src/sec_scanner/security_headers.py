"""
Security Headers Middleware for FastAPI.

This module provides CSP and other security headers as a fallback
when Nginx is not in front of the application (e.g., local development).

In production, Nginx handles security headers. This middleware ensures
security even in development or when accessed directly.
"""

import os
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


# CSP for API endpoints (permissive for Swagger UI)
CSP_API = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net https://js.stripe.com; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https: blob:; "
    "font-src 'self' data: https://cdn.jsdelivr.net; "
    "connect-src 'self' https://api.stripe.com; "
    "frame-src https://js.stripe.com https://hooks.stripe.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self';"
)

# CSP for frontend (stricter)
CSP_FRONTEND = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://js.stripe.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: https:; "
    "font-src 'self' data:; "
    "connect-src 'self' https://api.stripe.com; "
    "frame-src https://js.stripe.com https://hooks.stripe.com; "
    "frame-ancestors 'none'; "
    "base-uri 'self'; "
    "form-action 'self' https://checkout.stripe.com;"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to responses.

    Headers added:
    - Content-Security-Policy (configurable)
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: restricted features

    In production with Nginx, these headers are set by Nginx.
    This middleware serves as a fallback for development.
    """

    def __init__(
        self,
        app: ASGIApp,
        csp_policy: str = CSP_API,
        enable_csp: bool = True,
        enable_hsts: bool = False,  # HSTS should only be set via HTTPS
    ):
        super().__init__(app)
        self.csp_policy = csp_policy
        self.enable_csp = enable_csp
        self.enable_hsts = enable_hsts

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Skip for certain paths (webhooks, health checks)
        path = request.url.path
        if path in ("/healthz", "/readyz"):
            return response

        # Add security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        # CSP
        if self.enable_csp and "Content-Security-Policy" not in response.headers:
            response.headers["Content-Security-Policy"] = self.csp_policy

        # HSTS (only enable if you're sure about HTTPS)
        if self.enable_hsts:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response


def add_security_headers_middleware(app, enable_in_dev: bool = True):
    """
    Add security headers middleware to FastAPI app.

    Args:
        app: FastAPI application
        enable_in_dev: If True, enable even when SEC_SCANNER_SECURITY_HEADERS=false

    Usage:
        from src.sec_scanner.security_headers import add_security_headers_middleware
        add_security_headers_middleware(app)
    """
    # Check if explicitly disabled
    if not enable_in_dev and not _bool_env("SEC_SCANNER_SECURITY_HEADERS", default=True):
        return

    # Don't add if Nginx is expected to handle headers
    if _bool_env("SEC_SCANNER_BEHIND_NGINX", default=False):
        return

    app.add_middleware(
        SecurityHeadersMiddleware,
        csp_policy=CSP_API,
        enable_csp=True,
        enable_hsts=False,  # Let Nginx handle HSTS
    )


# Report-Only mode for testing CSP without breaking things
CSP_REPORT_ONLY_HEADER = "Content-Security-Policy-Report-Only"


def get_csp_report_uri() -> str:
    """Get CSP report URI from environment."""
    return os.getenv("SEC_SCANNER_CSP_REPORT_URI", "").strip()


def build_csp_with_report(base_csp: str) -> str:
    """Add report-uri directive to CSP if configured."""
    report_uri = get_csp_report_uri()
    if report_uri:
        return f"{base_csp} report-uri {report_uri};"
    return base_csp
