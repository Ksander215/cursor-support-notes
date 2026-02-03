"""
Tests for target validation (normalize_target) — edge cases.

Verifies that invalid or private targets are rejected with clear
ValueError messages before any scan is enqueued.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.sec_scanner.targets import ensure_public_target_or_raise, normalize_target


class TestNormalizeTargetEdgeCases:
    """Edge cases for normalize_target (no network required)."""

    def test_empty_target_raises(self):
        """Empty or whitespace target must raise with clear message."""
        with pytest.raises(ValueError, match="empty"):
            normalize_target("")
        with pytest.raises(ValueError, match="empty"):
            normalize_target("   ")

    def test_localhost_rejected(self):
        """localhost must be rejected (private target)."""
        with pytest.raises(ValueError, match="private"):
            normalize_target("localhost")
        with pytest.raises(ValueError, match="private"):
            normalize_target("http://localhost/")

    def test_dot_local_rejected(self):
        """*.local and *.internal must be rejected."""
        with pytest.raises(ValueError, match="private"):
            normalize_target("myservice.local")
        with pytest.raises(ValueError, match="private"):
            normalize_target("myservice.internal")

    def test_invalid_url_no_host_raises(self):
        """URL without host must raise invalid URL."""
        with pytest.raises(ValueError, match="invalid URL"):
            normalize_target("http:///path")
        with pytest.raises(ValueError, match="invalid URL"):
            normalize_target("https://")

    def test_private_ipv4_rejected(self):
        """Private IPv4 must be rejected (ensure_public_target_or_raise)."""
        with pytest.raises(ValueError, match="private"):
            ensure_public_target_or_raise("127.0.0.1", pin_dns=False)
        with pytest.raises(ValueError, match="private"):
            ensure_public_target_or_raise("192.168.1.1", pin_dns=False)
        with pytest.raises(ValueError, match="private"):
            ensure_public_target_or_raise("10.0.0.1", pin_dns=False)

    @patch("src.sec_scanner.targets.resolve_and_pin")
    def test_public_domain_accepted(self, mock_resolve):
        """Valid public domain with mocked DNS returns (host, display)."""
        mock_entry = MagicMock()
        mock_entry.all_addresses = ["93.184.216.34"]
        mock_resolve.return_value = mock_entry
        host, display = normalize_target("example.com")
        assert host == "example.com"
        assert display == "example.com"
        mock_resolve.assert_called_once()

    @patch("src.sec_scanner.targets.resolve_and_pin")
    def test_public_url_accepted(self, mock_resolve):
        """Valid URL with mocked DNS returns (host, display)."""
        mock_entry = MagicMock()
        mock_entry.all_addresses = ["93.184.216.34"]
        mock_resolve.return_value = mock_entry
        host, display = normalize_target("https://example.com/path")
        assert host == "example.com"
        assert display == "https://example.com/path"
        mock_resolve.assert_called_once()
