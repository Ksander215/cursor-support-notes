"""
Tests for DNS Pinning module - SSRF and DNS Rebinding protection.

These tests verify that:
1. Public IPs are correctly identified
2. Private/reserved IPs are blocked
3. DNS resolution is cached (pinned)
4. Cache expiration works correctly
5. SSRF attacks via DNS rebinding are prevented
"""

import time
from unittest.mock import patch

import pytest

from src.sec_scanner.dns_pinning import (
    DNSPinningCache,
    PinnedDNSEntry,
    clear_dns_cache,
    is_public_ip,
    resolve_and_pin,
    validate_and_pin_target,
)


class TestIsPublicIP:
    """Tests for is_public_ip() function."""

    def test_public_ipv4(self):
        """Public IPv4 addresses should be allowed."""
        assert is_public_ip("8.8.8.8") is True
        assert is_public_ip("1.1.1.1") is True
        assert is_public_ip("93.184.216.34") is True  # example.com

    def test_private_ipv4(self):
        """Private IPv4 addresses should be blocked."""
        # RFC 1918 private ranges
        assert is_public_ip("10.0.0.1") is False
        assert is_public_ip("10.255.255.255") is False
        assert is_public_ip("172.16.0.1") is False
        assert is_public_ip("172.31.255.255") is False
        assert is_public_ip("192.168.0.1") is False
        assert is_public_ip("192.168.255.255") is False

    def test_loopback_ipv4(self):
        """Loopback addresses should be blocked."""
        assert is_public_ip("127.0.0.1") is False
        assert is_public_ip("127.255.255.255") is False

    def test_link_local_ipv4(self):
        """Link-local addresses should be blocked."""
        assert is_public_ip("169.254.0.1") is False
        assert is_public_ip("169.254.255.255") is False

    def test_metadata_endpoint(self):
        """Cloud metadata endpoint should be explicitly blocked."""
        assert is_public_ip("169.254.169.254") is False

    def test_cgnat_range(self):
        """CGNAT range (100.64.0.0/10) should be blocked."""
        assert is_public_ip("100.64.0.1") is False
        assert is_public_ip("100.127.255.255") is False

    def test_multicast(self):
        """Multicast addresses should be blocked."""
        assert is_public_ip("224.0.0.1") is False
        assert is_public_ip("239.255.255.255") is False

    def test_public_ipv6(self):
        """Public IPv6 addresses should be allowed."""
        assert is_public_ip("2607:f8b0:4004:800::200e") is True  # Google

    def test_private_ipv6(self):
        """Private IPv6 addresses should be blocked."""
        assert is_public_ip("::1") is False  # Loopback
        assert is_public_ip("fe80::1") is False  # Link-local
        assert is_public_ip("fc00::1") is False  # Unique local

    def test_invalid_ip(self):
        """Invalid IP strings should return False."""
        assert is_public_ip("invalid") is False
        assert is_public_ip("") is False
        assert is_public_ip("256.256.256.256") is False


class TestPinnedDNSEntry:
    """Tests for PinnedDNSEntry dataclass."""

    def test_all_addresses(self):
        """all_addresses should return IPv4 then IPv6."""
        entry = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=("2606:2800:220:1:248:1893:25c8:1946",),
            resolved_at=time.time(),
            ttl=300,
        )
        assert entry.all_addresses == (
            "93.184.216.34",
            "2606:2800:220:1:248:1893:25c8:1946",
        )

    def test_primary_ip_prefers_ipv4(self):
        """primary_ip should prefer IPv4."""
        entry = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=("2606:2800:220:1:248:1893:25c8:1946",),
            resolved_at=time.time(),
            ttl=300,
        )
        assert entry.primary_ip == "93.184.216.34"

    def test_primary_ip_ipv6_only(self):
        """primary_ip should return IPv6 if no IPv4."""
        entry = PinnedDNSEntry(
            hostname="ipv6only.example.com",
            ipv4_addresses=(),
            ipv6_addresses=("2606:2800:220:1:248:1893:25c8:1946",),
            resolved_at=time.time(),
            ttl=300,
        )
        assert entry.primary_ip == "2606:2800:220:1:248:1893:25c8:1946"

    def test_is_expired(self):
        """is_expired should correctly detect expired entries."""
        # Not expired
        entry = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=(),
            resolved_at=time.time(),
            ttl=300,
        )
        assert entry.is_expired() is False

        # Expired
        entry_expired = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=(),
            resolved_at=time.time() - 400,  # 400 seconds ago
            ttl=300,
        )
        assert entry_expired.is_expired() is True


class TestDNSPinningCache:
    """Tests for DNSPinningCache class."""

    def test_get_set(self):
        """Basic get/set operations."""
        cache = DNSPinningCache()
        entry = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=(),
            resolved_at=time.time(),
            ttl=300,
        )
        cache.set(entry)
        result = cache.get("example.com")
        assert result is not None
        assert result.hostname == "example.com"

    def test_get_expired(self):
        """Expired entries should not be returned."""
        cache = DNSPinningCache()
        entry = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=(),
            resolved_at=time.time() - 400,
            ttl=300,
        )
        cache.set(entry)
        result = cache.get("example.com")
        assert result is None

    def test_invalidate(self):
        """Invalidated entries should be removed."""
        cache = DNSPinningCache()
        entry = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=(),
            resolved_at=time.time(),
            ttl=300,
        )
        cache.set(entry)
        cache.invalidate("example.com")
        result = cache.get("example.com")
        assert result is None

    def test_clear(self):
        """Clear should remove all entries."""
        cache = DNSPinningCache()
        for i in range(5):
            entry = PinnedDNSEntry(
                hostname=f"example{i}.com",
                ipv4_addresses=(f"93.184.216.{i}",),
                ipv6_addresses=(),
                resolved_at=time.time(),
                ttl=300,
            )
            cache.set(entry)
        cache.clear()
        for i in range(5):
            assert cache.get(f"example{i}.com") is None


class TestResolveAndPin:
    """Tests for resolve_and_pin() function."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_dns_cache()

    @patch("src.sec_scanner.dns_pinning.resolve_hostname")
    def test_caches_result(self, mock_resolve):
        """Results should be cached."""
        mock_resolve.return_value = (("93.184.216.34",), ())

        # First call resolves
        entry1 = resolve_and_pin("example.com")
        assert mock_resolve.call_count == 1

        # Second call uses cache
        entry2 = resolve_and_pin("example.com")
        assert mock_resolve.call_count == 1  # Still 1

        assert entry1.hostname == entry2.hostname

    @patch("src.sec_scanner.dns_pinning.resolve_hostname")
    def test_validates_public_ips(self, mock_resolve):
        """Private IPs should raise ValueError."""
        mock_resolve.return_value = (("192.168.1.1",), ())

        with pytest.raises(ValueError, match="Private IP"):
            resolve_and_pin("evil.com", validate_public=True)

    @patch("src.sec_scanner.dns_pinning.resolve_hostname")
    def test_allows_private_when_disabled(self, mock_resolve):
        """Private IPs should be allowed when validation disabled."""
        mock_resolve.return_value = (("192.168.1.1",), ())

        entry = resolve_and_pin("internal.local", validate_public=False)
        assert entry.ipv4_addresses == ("192.168.1.1",)

    def test_ip_literal(self):
        """IP literals should be handled directly."""
        entry = resolve_and_pin("8.8.8.8")
        assert entry.ipv4_addresses == ("8.8.8.8",)

    def test_private_ip_literal(self):
        """Private IP literals should raise ValueError."""
        with pytest.raises(ValueError, match="Private IP"):
            resolve_and_pin("192.168.1.1")

    @patch("src.sec_scanner.dns_pinning.resolve_hostname")
    def test_force_refresh(self, mock_resolve):
        """force_refresh should bypass cache."""
        mock_resolve.return_value = (("93.184.216.34",), ())

        resolve_and_pin("example.com")
        assert mock_resolve.call_count == 1

        resolve_and_pin("example.com", force_refresh=True)
        assert mock_resolve.call_count == 2


class TestValidateAndPinTarget:
    """Tests for validate_and_pin_target() function."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_dns_cache()

    @patch("src.sec_scanner.dns_pinning.resolve_and_pin")
    def test_domain_target(self, mock_resolve):
        """Domain targets should be resolved and pinned."""
        mock_entry = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=(),
            resolved_at=time.time(),
            ttl=300,
        )
        mock_resolve.return_value = mock_entry

        hostname, display, entry = validate_and_pin_target("example.com")
        assert hostname == "example.com"
        assert display == "example.com"
        assert entry.ipv4_addresses == ("93.184.216.34",)

    @patch("src.sec_scanner.dns_pinning.resolve_and_pin")
    def test_url_target(self, mock_resolve):
        """URL targets should extract hostname."""
        mock_entry = PinnedDNSEntry(
            hostname="example.com",
            ipv4_addresses=("93.184.216.34",),
            ipv6_addresses=(),
            resolved_at=time.time(),
            ttl=300,
        )
        mock_resolve.return_value = mock_entry

        hostname, display, entry = validate_and_pin_target("https://example.com/path")
        assert hostname == "example.com"
        assert display == "https://example.com/path"

    def test_localhost_blocked(self):
        """localhost should be blocked."""
        with pytest.raises(ValueError, match="Private targets"):
            validate_and_pin_target("localhost")

    def test_local_domain_blocked(self):
        """*.local domains should be blocked."""
        with pytest.raises(ValueError, match="Private targets"):
            validate_and_pin_target("server.local")

    def test_empty_target(self):
        """Empty targets should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            validate_and_pin_target("")


class TestDNSRebindingProtection:
    """Integration tests for DNS rebinding attack prevention."""

    def setup_method(self):
        """Clear cache before each test."""
        clear_dns_cache()

    @patch("src.sec_scanner.dns_pinning.resolve_hostname")
    def test_rebinding_attack_prevented(self, mock_resolve):
        """
        Simulate DNS rebinding attack:
        1. First resolution returns public IP (passes validation)
        2. Attacker changes DNS to private IP
        3. Second resolution should use cached (pinned) IP
        """
        # First call: attacker's DNS returns public IP
        mock_resolve.return_value = (("93.184.216.34",), ())
        entry1 = resolve_and_pin("evil.com")
        assert entry1.primary_ip == "93.184.216.34"

        # Attacker changes DNS to private IP
        mock_resolve.return_value = (("192.168.1.1",), ())

        # Second call should use cached IP (not call DNS again)
        entry2 = resolve_and_pin("evil.com")
        assert entry2.primary_ip == "93.184.216.34"  # Still public IP

        # DNS was only called once (for first resolution)
        assert mock_resolve.call_count == 1

    @patch("src.sec_scanner.dns_pinning.resolve_hostname")
    def test_rebinding_blocked_on_refresh(self, mock_resolve):
        """
        After TTL expires, re-resolution should validate again.
        """
        # First call: public IP
        mock_resolve.return_value = (("93.184.216.34",), ())
        entry1 = resolve_and_pin("evil.com", ttl=1)  # 1 second TTL

        # Wait for expiration
        time.sleep(1.1)

        # Attacker changed DNS to private IP
        mock_resolve.return_value = (("192.168.1.1",), ())

        # Should fail validation on refresh
        with pytest.raises(ValueError, match="Private IP"):
            resolve_and_pin("evil.com")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
