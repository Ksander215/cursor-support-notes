"""
Tests for SaaS middleware: rate limit (429) and Retry-After header.

Verifies that when rate limit is exceeded, the response includes
Retry-After header for client guidance.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from src.sec_scanner.saas import API_KEY_HEADER, AuthContext, saas_http_middleware


def _make_request(
    path: str = "/api/v1/audits",
    headers: dict | None = None,
    query: str = "",
) -> MagicMock:
    request = MagicMock()
    request.url = MagicMock()
    request.url.path = path
    request.url.query = query
    request.headers = Headers(headers or {})
    request.state = MagicMock()
    return request


@pytest.mark.asyncio
async def test_429_response_includes_retry_after_header():
    """When middleware catches HTTPException(429), response must include Retry-After header."""

    async def raise_429(*args, **kwargs):
        raise HTTPException(status_code=429, detail="rate limit exceeded")

    request = _make_request(path="/api/v1/audits", headers={API_KEY_HEADER: "sk_test_123"})
    request.url.path = "/api/v1/audits"

    with patch("src.sec_scanner.saas.load_auth_context_or_none") as load_ctx:
        load_ctx.return_value = AuthContext(
            org_id=1,
            tenant_id=1,
            api_key_id="key_1",
            api_key_prefix="sk_",
            plan_code="starter",
            requests_per_minute=60,
            monthly_audits_quota=100,
            concurrency_limit=2,
            is_admin=False,
        )
        with patch("src.sec_scanner.saas.enforce_rpm_or_raise", side_effect=raise_429):
            call_next = AsyncMock(return_value=MagicMock(status_code=200))
            response = await saas_http_middleware(request, call_next)

    assert response.status_code == 429
    assert response.headers.get("retry-after") == "60"
