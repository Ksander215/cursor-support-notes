import ipaddress
import os
import re
import socket
from urllib.parse import urlparse

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-zA-Z0-9-]{1,63}\.)+[a-zA-Z]{2,63}$")
_IPV4_RE = re.compile(r"^(\d{1,3}\.){3}\d{1,3}$")


def _bool_env(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "y", "on")


def _is_public_ip(ip: str) -> bool:
    """
    Minimal SSRF guard: allow only globally-routable IPs by default.
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
    ips: set[str] = set()
    try:
        for family, _type, _proto, _canon, sockaddr in socket.getaddrinfo(host, None):
            if family == socket.AF_INET or family == socket.AF_INET6:
                ips.add(sockaddr[0])
    except Exception:
        return set()
    return ips


def ensure_public_target_or_raise(host: str) -> None:
    """
    Enforces "public internet only" by default.
    Rollback switch: set SEC_SCANNER_ALLOW_PRIVATE_TARGETS=true.
    """
    if _bool_env("SEC_SCANNER_ALLOW_PRIVATE_TARGETS", default=False):
        return

    h = (host or "").strip().lower()
    if not h:
        raise ValueError("target is empty")
    if h in ("localhost",):
        raise ValueError("private targets are not allowed")
    if h.endswith(".local") or h.endswith(".internal"):
        raise ValueError("private targets are not allowed")

    # If host is an IP literal
    if _IPV4_RE.match(h) or ":" in h:
        if not _is_public_ip(h):
            raise ValueError("private targets are not allowed")
        return

    # Resolve DNS and verify all answers are public
    ips = _resolve_all_ips(h)
    if not ips:
        raise ValueError("failed to resolve target")
    if any(not _is_public_ip(ip) for ip in ips):
        raise ValueError("private targets are not allowed")


def normalize_target(target: str) -> tuple[str, str]:
    """
    Returns (host, display_target).
    Accepts domain, IPv4, or URL. Strips scheme/path.
    """
    t = (target or "").strip()
    if not t:
        raise ValueError("target is empty")

    # If it's a URL, parse it
    if "://" in t:
        parsed = urlparse(t)
        host = (parsed.hostname or "").strip()
        if not host:
            raise ValueError("invalid URL target")
        ensure_public_target_or_raise(host)
        return host, t

    # Otherwise assume it's host/IP
    host = t.split("/")[0].split(":")[0].strip()
    if _IPV4_RE.match(host):
        ensure_public_target_or_raise(host)
        return host, host
    if _HOST_RE.match(host):
        ensure_public_target_or_raise(host)
        return host, host

    raise ValueError("target must be a valid domain, IPv4, or URL")
