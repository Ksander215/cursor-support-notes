"""
Target validation and normalization with DNS pinning for SSRF protection.

This module provides secure target handling that:
1. Validates targets are publicly accessible (blocks private IPs)
2. Pins DNS resolutions to prevent DNS rebinding attacks
3. Normalizes various target formats (domain, IP, URL)

DNS Rebinding Protection:
- DNS is resolved once and cached ("pinned")
- All subsequent operations use the pinned IP
- Prevents attackers from changing DNS records between validation and use
"""

from __future__ import annotations

import os
import re
from urllib.parse import urlparse

from .dns_pinning import (
    PinnedDNSEntry,
    get_pinned_ip,
    is_public_ip,
    resolve_and_pin,
    validate_and_pin_target,
)

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9-]{1,63}\.)+[a-zA-Z]{2,63}$")
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


# Legacy function - kept for backward compatibility
# New code should use dns_pinning.is_public_ip() directly
def _is_public_ip(ip: str) -> bool:
    """
    Minimal SSRF guard: allow only globally-routable IPs by default.
    Blocks loopback/private/link-local/multicast/reserved/CGNAT/etc.

    DEPRECATED: Use dns_pinning.is_public_ip() for new code.
    """
    return is_public_ip(ip)


# Legacy function - kept for backward compatibility
def _resolve_all_ips(host: str) -> set[str]:
    """
    Resolve hostname to all IP addresses.

    DEPRECATED: Use dns_pinning.resolve_and_pin() for new code
    to get DNS rebinding protection.
    """
    try:
        entry = resolve_and_pin(host, validate_public=False)
        return set(entry.all_addresses)
    except ValueError:
        return set()


def ensure_public_target_or_raise(host: str, *, pin_dns: bool = True) -> PinnedDNSEntry | None:
    """
    Enforces "public internet only" by default with DNS pinning.

    This function validates that the target resolves to public IPs only
    and pins the DNS resolution to prevent DNS rebinding attacks.

    Args:
        host: Hostname or IP address to validate
        pin_dns: If True (default), pin DNS resolution for later use

    Returns:
        PinnedDNSEntry if pin_dns=True and validation passes, None otherwise

    Raises:
        ValueError: If target is private or cannot be resolved

    Rollback switch: set SEC_SCANNER_ALLOW_PRIVATE_TARGETS=true
    """
    allow_private = _bool_env("SEC_SCANNER_ALLOW_PRIVATE_TARGETS", default=False)

    h = (host or "").strip().lower()
    if not h:
        raise ValueError("target is empty")
    if h in ("localhost",):
        raise ValueError("private targets are not allowed")
    if h.endswith(".local") or h.endswith(".internal"):
        raise ValueError("private targets are not allowed")

    # Use DNS pinning for resolution and validation
    if pin_dns:
        try:
            entry = resolve_and_pin(h, validate_public=not allow_private)
            return entry
        except ValueError as e:
            # Re-raise with consistent error message
            if "private" in str(e).lower():
                raise ValueError("private targets are not allowed") from e
            raise
    else:
        # Legacy path without pinning (not recommended)
        if _IPV4_RE.match(h) or ":" in h:
            if not allow_private and not is_public_ip(h):
                raise ValueError("private targets are not allowed")
            return None

        # Resolve and validate without pinning
        try:
            entry = resolve_and_pin(h, validate_public=not allow_private)
            return None  # Don't return entry when pin_dns=False
        except ValueError as e:
            if "private" in str(e).lower():
                raise ValueError("private targets are not allowed") from e
            if "resolve" in str(e).lower() or "DNS" in str(e):
                raise ValueError("failed to resolve target") from e
            raise

    return None


def normalize_target(target: str) -> tuple[str, str]:
    """
    Normalize and validate target with DNS pinning.

    Returns (host, display_target) after validating the target
    is publicly accessible and pinning DNS resolution.

    Args:
        target: Domain, IPv4, or URL to normalize

    Returns:
        Tuple of (hostname, display_target)
        - hostname: The extracted hostname or IP
        - display_target: Original or normalized target for display

    Raises:
        ValueError: If target is invalid or resolves to private IPs

    Note:
        This function pins DNS resolution. To get the pinned IP for
        subsequent connections, use:

            from .dns_pinning import get_pinned_ip
            pinned_ip = get_pinned_ip(hostname)
    """
    t = (target or "").strip()
    if not t:
        raise ValueError("target is empty")

    # Reject localhost and private hostnames before format checks
    h_lower = t.lower()
    if h_lower in ("localhost",):
        raise ValueError("private targets are not allowed")
    if h_lower.endswith(".local") or h_lower.endswith(".internal"):
        raise ValueError("private targets are not allowed")
    # For URL, extract host first then check
    if "://" in t:
        parsed = urlparse(t)
        host_for_private = (parsed.hostname or "").strip().lower()
        if (
            host_for_private in ("localhost",)
            or host_for_private.endswith(".local")
            or host_for_private.endswith(".internal")
        ):
            raise ValueError("private targets are not allowed")

    # If it's a URL, parse it
    if "://" in t:
        parsed = urlparse(t)
        host = (parsed.hostname or "").strip()
        if not host:
            raise ValueError("invalid URL target")
        ensure_public_target_or_raise(host, pin_dns=True)
        return host, t

    # Otherwise assume it's host/IP
    host = t.split("/")[0].split(":")[0].strip()
    if _IPV4_RE.match(host):
        ensure_public_target_or_raise(host, pin_dns=True)
        return host, host
    if _HOST_RE.match(host):
        ensure_public_target_or_raise(host, pin_dns=True)
        return host, host

    raise ValueError("target must be a valid domain, IPv4, or URL")


def normalize_target_with_pinned_ip(target: str) -> tuple[str, str, str]:
    """
    Normalize target and return pinned IP for direct connection.

    This is the recommended function for SSRF-safe HTTP connections.
    It validates the target, pins DNS, and returns the IP to use
    for the actual connection.

    Args:
        target: Domain, IPv4, or URL to normalize

    Returns:
        Tuple of (hostname, display_target, pinned_ip)
        - hostname: The extracted hostname (use for Host header)
        - display_target: Original or normalized target for display
        - pinned_ip: The IP address to connect to

    Raises:
        ValueError: If target is invalid or resolves to private IPs

    Example:
        hostname, display, ip = normalize_target_with_pinned_ip("example.com")
        # Connect to `ip`, set Host header to `hostname`
    """
    hostname, display_target = normalize_target(target)
    pinned_ip = get_pinned_ip(hostname)
    return hostname, display_target, pinned_ip


# Re-export for convenience
__all__ = [
    "normalize_target",
    "normalize_target_with_pinned_ip",
    "ensure_public_target_or_raise",
    "PinnedDNSEntry",
    "get_pinned_ip",
    "resolve_and_pin",
    "validate_and_pin_target",
    "is_public_ip",
]
