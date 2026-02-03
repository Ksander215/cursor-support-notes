"""
DNS Pinning Module - Protection against DNS Rebinding attacks.

DNS Rebinding Attack:
1. Attacker controls DNS for evil.com
2. First DNS query returns attacker's IP (passes validation)
3. Second DNS query returns internal IP (e.g., 169.254.169.254)
4. Application connects to internal resource thinking it's evil.com

Solution:
- Resolve DNS once and cache ("pin") the IP addresses
- Use pinned IPs for all subsequent connections
- Connect by IP but set Host header to original hostname (for SNI/vhosts)
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger("sec_scanner.dns_pinning")

# Default TTL for pinned DNS entries (seconds)
DEFAULT_PIN_TTL = int(os.getenv("SEC_SCANNER_DNS_PIN_TTL", "300"))  # 5 minutes

# Maximum cache size
MAX_CACHE_SIZE = int(os.getenv("SEC_SCANNER_DNS_CACHE_SIZE", "10000"))


@dataclass
class PinnedDNSEntry:
    """Cached DNS resolution result with TTL."""

    hostname: str
    ipv4_addresses: tuple[str, ...]
    ipv6_addresses: tuple[str, ...]
    resolved_at: float
    ttl: int

    @property
    def all_addresses(self) -> tuple[str, ...]:
        """Return all resolved IP addresses (IPv4 first, then IPv6)."""
        return self.ipv4_addresses + self.ipv6_addresses

    @property
    def primary_ip(self) -> str | None:
        """Return primary IP (prefer IPv4 for compatibility)."""
        if self.ipv4_addresses:
            return self.ipv4_addresses[0]
        if self.ipv6_addresses:
            return self.ipv6_addresses[0]
        return None

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return time.time() > (self.resolved_at + self.ttl)


@dataclass
class DNSPinningCache:
    """Thread-safe DNS pinning cache with TTL and size limits."""

    _cache: dict[str, PinnedDNSEntry] = field(default_factory=dict)
    _lock: threading.RLock = field(default_factory=threading.RLock)
    _max_size: int = MAX_CACHE_SIZE
    _default_ttl: int = DEFAULT_PIN_TTL

    def get(self, hostname: str) -> PinnedDNSEntry | None:
        """Get cached entry if exists and not expired."""
        hostname = hostname.lower().strip()
        with self._lock:
            entry = self._cache.get(hostname)
            if entry is None:
                return None
            if entry.is_expired():
                del self._cache[hostname]
                return None
            return entry

    def set(self, entry: PinnedDNSEntry) -> None:
        """Store entry in cache, evicting oldest if at capacity."""
        hostname = entry.hostname.lower().strip()
        with self._lock:
            # Evict expired entries if at capacity
            if len(self._cache) >= self._max_size:
                self._evict_expired()

            # If still at capacity, evict oldest
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].resolved_at)
                del self._cache[oldest_key]

            self._cache[hostname] = entry

    def invalidate(self, hostname: str) -> None:
        """Remove entry from cache."""
        hostname = hostname.lower().strip()
        with self._lock:
            self._cache.pop(hostname, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()

    def _evict_expired(self) -> None:
        """Remove all expired entries (must hold lock)."""
        now = time.time()
        expired = [k for k, v in self._cache.items() if now > (v.resolved_at + v.ttl)]
        for k in expired:
            del self._cache[k]


# Global cache instance
_dns_cache = DNSPinningCache()


def is_public_ip(ip: str) -> bool:
    """
    Check if IP address is globally routable (public).

    Blocks:
    - Loopback (127.0.0.0/8, ::1)
    - Private (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
    - Link-local (169.254.0.0/16, fe80::/10)
    - Multicast
    - Reserved
    - CGNAT (100.64.0.0/10)
    - Cloud metadata (169.254.169.254)
    """
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False

    # Hard block common metadata endpoint
    if str(addr) == "169.254.169.254":
        return False

    # Block CGNAT range explicitly (some Python versions may not flag it)
    if isinstance(addr, ipaddress.IPv4Address):
        cgnat = ipaddress.ip_network("100.64.0.0/10")
        if addr in cgnat:
            return False

    # Block multicast (is_global can be True for multicast in some Python versions)
    if getattr(addr, "is_multicast", False):
        return False

    return bool(getattr(addr, "is_global", False))


def resolve_hostname(hostname: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """
    Resolve hostname to IPv4 and IPv6 addresses.

    Returns:
        Tuple of (ipv4_addresses, ipv6_addresses)

    Raises:
        ValueError: If hostname cannot be resolved
    """
    ipv4: list[str] = []
    ipv6: list[str] = []

    try:
        for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        ):
            ip = sockaddr[0]
            if family == socket.AF_INET:
                if ip not in ipv4:
                    ipv4.append(ip)
            elif family == socket.AF_INET6:
                if ip not in ipv6:
                    ipv6.append(ip)
    except socket.gaierror as e:
        raise ValueError(f"DNS resolution failed for {hostname}: {e}") from e
    except Exception as e:
        raise ValueError(f"Failed to resolve {hostname}: {e}") from e

    if not ipv4 and not ipv6:
        raise ValueError(f"No addresses found for {hostname}")

    return tuple(ipv4), tuple(ipv6)


def resolve_and_pin(
    hostname: str,
    *,
    ttl: int | None = None,
    force_refresh: bool = False,
    validate_public: bool = True,
) -> PinnedDNSEntry:
    """
    Resolve hostname and cache (pin) the IP addresses.

    This is the main entry point for DNS pinning. It:
    1. Checks cache for existing valid entry
    2. Resolves DNS if not cached or expired
    3. Validates all IPs are public (if validate_public=True)
    4. Caches the result for future use

    Args:
        hostname: The hostname to resolve
        ttl: Optional TTL override (seconds)
        force_refresh: If True, ignore cache and re-resolve
        validate_public: If True, raise error if any IP is private

    Returns:
        PinnedDNSEntry with resolved and validated IP addresses

    Raises:
        ValueError: If hostname cannot be resolved or contains private IPs
    """
    hostname = hostname.lower().strip()

    if not hostname:
        raise ValueError("Hostname is empty")

    # Check if hostname is already an IP address
    try:
        addr = ipaddress.ip_address(hostname)
        # It's an IP literal, validate and return directly
        if validate_public and not is_public_ip(hostname):
            raise ValueError(f"Private IP address not allowed: {hostname}")

        if isinstance(addr, ipaddress.IPv4Address):
            return PinnedDNSEntry(
                hostname=hostname,
                ipv4_addresses=(hostname,),
                ipv6_addresses=(),
                resolved_at=time.time(),
                ttl=ttl or _dns_cache._default_ttl,
            )
        else:
            return PinnedDNSEntry(
                hostname=hostname,
                ipv4_addresses=(),
                ipv6_addresses=(hostname,),
                resolved_at=time.time(),
                ttl=ttl or _dns_cache._default_ttl,
            )
    except ValueError:
        # Not an IP literal, continue with DNS resolution
        pass

    # Check cache
    if not force_refresh:
        cached = _dns_cache.get(hostname)
        if cached is not None:
            logger.debug(f"DNS cache hit for {hostname}: {cached.all_addresses}")
            return cached

    # Resolve DNS
    logger.debug(f"Resolving DNS for {hostname}")
    ipv4, ipv6 = resolve_hostname(hostname)

    # Validate all IPs are public
    if validate_public:
        for ip in ipv4 + ipv6:
            if not is_public_ip(ip):
                raise ValueError(f"Private IP address not allowed: {ip} (resolved from {hostname})")

    # Create entry and cache
    entry = PinnedDNSEntry(
        hostname=hostname,
        ipv4_addresses=ipv4,
        ipv6_addresses=ipv6,
        resolved_at=time.time(),
        ttl=ttl or _dns_cache._default_ttl,
    )

    _dns_cache.set(entry)
    logger.debug(f"DNS pinned for {hostname}: IPv4={ipv4}, IPv6={ipv6}")

    return entry


def get_pinned_ip(hostname: str, *, prefer_ipv4: bool = True) -> str:
    """
    Get a pinned IP for hostname, resolving and caching if needed.

    Args:
        hostname: The hostname to get pinned IP for
        prefer_ipv4: If True, prefer IPv4 addresses over IPv6

    Returns:
        A pinned IP address string

    Raises:
        ValueError: If hostname cannot be resolved or IPs are private
    """
    entry = resolve_and_pin(hostname)

    if prefer_ipv4 and entry.ipv4_addresses:
        return entry.ipv4_addresses[0]
    if entry.ipv6_addresses:
        return entry.ipv6_addresses[0]
    if entry.ipv4_addresses:
        return entry.ipv4_addresses[0]

    raise ValueError(f"No valid IP found for {hostname}")


def validate_and_pin_target(target: str) -> tuple[str, str, PinnedDNSEntry]:
    """
    Validate target and pin DNS for SSRF protection.

    Args:
        target: Domain, IP, or URL

    Returns:
        Tuple of (hostname, display_target, pinned_entry)

    Raises:
        ValueError: If target is invalid or resolves to private IPs
    """
    from urllib.parse import urlparse

    target = (target or "").strip()
    if not target:
        raise ValueError("Target is empty")

    # Parse URL if present
    if "://" in target:
        parsed = urlparse(target)
        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            raise ValueError("Invalid URL target")
        display_target = target
    else:
        # Assume it's host/IP (strip port and path)
        hostname = target.split("/")[0].split(":")[0].strip().lower()
        display_target = hostname

    if not hostname:
        raise ValueError("Target hostname is empty")

    # Block obvious private targets
    if hostname in ("localhost",) or hostname.endswith((".local", ".internal")):
        raise ValueError("Private targets are not allowed")

    # Check if private targets are allowed via env
    allow_private = os.getenv("SEC_SCANNER_ALLOW_PRIVATE_TARGETS", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "y",
        "on",
    )

    # Resolve and pin
    entry = resolve_and_pin(hostname, validate_public=not allow_private)

    return hostname, display_target, entry


def invalidate_pinned_dns(hostname: str) -> None:
    """Remove hostname from DNS pin cache."""
    _dns_cache.invalidate(hostname)


def clear_dns_cache() -> None:
    """Clear entire DNS pin cache."""
    _dns_cache.clear()


def get_cache_stats() -> dict:
    """Get DNS cache statistics (for monitoring)."""
    with _dns_cache._lock:
        total = len(_dns_cache._cache)
        expired = sum(1 for e in _dns_cache._cache.values() if e.is_expired())
        return {
            "total_entries": total,
            "expired_entries": expired,
            "active_entries": total - expired,
            "max_size": _dns_cache._max_size,
            "default_ttl": _dns_cache._default_ttl,
        }
