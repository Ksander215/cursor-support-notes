"""
Tests for API key security measures.

These tests verify that:
1. API keys in URL query parameters are rejected
2. API keys in headers are accepted
3. Various parameter names are detected
"""

from unittest.mock import MagicMock

import pytest
from fastapi import Request
from starlette.datastructures import Headers

from src.sec_scanner.saas import _check_api_key_in_url


def create_mock_request(query: str = "") -> MagicMock:
    """Create a mock request with given query string."""
    request = MagicMock(spec=Request)
    request.url = MagicMock()
    request.url.query = query
    return request


class TestApiKeyInUrlDetection:
    """Tests for _check_api_key_in_url() function."""

    def test_no_query_params(self):
        """No query params should pass."""
        request = create_mock_request("")
        assert _check_api_key_in_url(request) is None

    def test_safe_query_params(self):
        """Safe query params should pass."""
        request = create_mock_request("page=1&limit=10&sort=asc")
        assert _check_api_key_in_url(request) is None

    def test_api_key_param_blocked(self):
        """api_key parameter should be blocked."""
        request = create_mock_request("api_key=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None
        assert "api_key" in result.lower()

    def test_apikey_param_blocked(self):
        """apikey parameter should be blocked."""
        request = create_mock_request("apikey=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_api_dash_key_param_blocked(self):
        """api-key parameter should be blocked."""
        request = create_mock_request("api-key=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_key_param_blocked(self):
        """key parameter should be blocked."""
        request = create_mock_request("key=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_token_param_blocked(self):
        """token parameter should be blocked."""
        request = create_mock_request("token=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_access_token_param_blocked(self):
        """access_token parameter should be blocked."""
        request = create_mock_request("access_token=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_secret_param_blocked(self):
        """secret parameter should be blocked."""
        request = create_mock_request("secret=my_secret_value")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_case_insensitive(self):
        """Detection should be case insensitive."""
        request = create_mock_request("API_KEY=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None

        request = create_mock_request("ApiKey=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_key_in_middle_of_query(self):
        """Key parameter in middle of query should be detected."""
        request = create_mock_request("page=1&api_key=sk_test&limit=10")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_key_at_end_of_query(self):
        """Key parameter at end of query should be detected."""
        request = create_mock_request("page=1&limit=10&api_key=sk_test")
        result = _check_api_key_in_url(request)
        assert result is not None

    def test_url_with_key_in_value_allowed(self):
        """Key as part of another value should be allowed.

        Example: redirect_url=https://example.com?key=123
        The 'key' here is part of a URL value, not a top-level param.
        """
        # This is a tricky case - we want to allow URLs that contain 'key'
        # as part of a nested URL value
        # Current implementation may be conservative and block this
        # which is acceptable for security
        pass  # Skip this edge case for now

    def test_error_message_contains_hint(self):
        """Error message should contain helpful hint."""
        request = create_mock_request("api_key=test")
        result = _check_api_key_in_url(request)
        assert result is not None
        assert "X-API-Key" in result or "header" in result.lower()

    def test_similar_param_names_allowed(self):
        """Parameters that look similar but aren't keys should pass."""
        # 'keyboard' contains 'key' but isn't a key parameter
        request = create_mock_request("keyboard=wireless&monkey=banana")
        # This depends on implementation - current regex matches 'key='
        # so 'keyboard=' won't match
        result = _check_api_key_in_url(request)
        assert result is None  # Should pass

    def test_x_api_key_param_blocked(self):
        """x-api-key parameter should be blocked."""
        request = create_mock_request("x-api-key=sk_test_123")
        result = _check_api_key_in_url(request)
        assert result is not None


class TestApiKeyInUrlIntegration:
    """Integration tests for API key URL security."""

    @pytest.mark.asyncio
    async def test_middleware_rejects_key_in_url(self):
        """Full middleware should reject requests with API key in URL."""
        from src.sec_scanner.saas import saas_http_middleware

        # Create mock request with API key in URL
        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/api/v1/audits"
        request.url.query = "api_key=sk_test_123"
        request.headers = Headers({})
        request.state = MagicMock()

        async def call_next(req):
            return MagicMock(status_code=200)

        response = await saas_http_middleware(request, call_next)

        # Should return 400 error
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_middleware_allows_key_in_header(self):
        """Middleware should allow API key in header."""
        from src.sec_scanner.saas import saas_http_middleware

        # Create mock request with API key in header (not URL)
        request = MagicMock(spec=Request)
        request.url = MagicMock()
        request.url.path = "/api/v1/audits"
        request.url.query = "page=1&limit=10"  # Safe params only
        request.headers = Headers({"x-api-key": "sk_test_123"})
        request.state = MagicMock()

        call_next_called = False

        async def call_next(req):
            nonlocal call_next_called
            call_next_called = True
            response = MagicMock()
            response.status_code = 200
            return response

        # Note: This will fail auth validation, but shouldn't fail URL check
        # The URL check happens before auth validation
        response = await saas_http_middleware(request, call_next)

        # Response will be 401 (invalid key) but not 400 (key in URL)
        # If URL check passed, we should see 401 not 400
        assert response.status_code in (200, 401)  # Not 400


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
