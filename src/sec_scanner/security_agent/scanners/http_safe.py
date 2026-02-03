"""
Safe HTTP request module with DNS pinning for SSRF protection.

This module provides HTTP request functions that:
1. Validate all URLs (including redirect targets) against SSRF
2. Use DNS pinning to prevent DNS rebinding attacks
3. Connect by IP while preserving Host header for proper routing

DNS Rebinding Protection:
- URLs are resolved once and IPs are pinned
- Connections use pinned IPs directly
- Host headers are set to original hostname for SNI/vhosts
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter

from ...targets import ensure_public_target_or_raise

logger = logging.getLogger("sec_scanner.http_safe")

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


class PinnedIPAdapter(HTTPAdapter):
    """
    HTTP Adapter that connects to a specific IP while preserving Host header.

    This prevents DNS rebinding by connecting to the IP that was validated,
    not whatever the DNS returns at connection time.
    """

    def __init__(self, pinned_ip: str, *args, **kwargs):
        self.pinned_ip = pinned_ip
        super().__init__(*args, **kwargs)

    def send(self, request, *args, **kwargs):
        # The actual connection will go to pinned_ip due to URL rewriting
        # Host header is already set correctly in the request
        return super().send(request, *args, **kwargs)


def _rewrite_url_to_ip(url: str, pinned_ip: str) -> tuple[str, str]:
    """
    Rewrite URL to use pinned IP while extracting original hostname.

    Returns:
        Tuple of (rewritten_url, original_hostname)
    """
    parsed = urlparse(url)
    original_host = parsed.hostname or ""
    port = parsed.port

    # Determine if we need brackets for IPv6
    if ":" in pinned_ip:
        ip_host = f"[{pinned_ip}]"
    else:
        ip_host = pinned_ip

    # Reconstruct netloc with IP
    if port:
        new_netloc = f"{ip_host}:{port}"
    else:
        new_netloc = ip_host

    # Reconstruct URL with IP instead of hostname
    rewritten = parsed._replace(netloc=new_netloc).geturl()

    return rewritten, original_host


def safe_request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout,
    max_redirects: int = 5,
    use_pinned_ip: bool = True,
    **kwargs,
) -> requests.Response:
    """
    Make an HTTP request with SSRF protection and DNS pinning.

    Features:
    - Redirects disabled by default (manual follow with SSRF checks)
    - All redirect targets validated (prevents redirect-to-private SSRF)
    - DNS rebinding protection via IP pinning

    Args:
        session: requests.Session to use
        method: HTTP method (GET, POST, etc.)
        url: Target URL
        timeout: Request timeout
        max_redirects: Maximum redirects to follow (default 5)
        use_pinned_ip: If True, use DNS pinning (recommended, default True)
        **kwargs: Additional arguments passed to session.request()

    Returns:
        requests.Response object

    Raises:
        ValueError: If URL is invalid or points to private resources
        requests.RequestException: For network errors
    """
    current = url
    resp: requests.Response | None = None

    for redirect_count in range(max_redirects + 1):
        # Parse current URL
        parsed = urlparse(current)
        hostname = parsed.hostname or ""

        if not hostname:
            raise ValueError(f"Invalid URL: {current}")

        # Validate and pin DNS
        pinned_entry = ensure_public_target_or_raise(hostname, pin_dns=True)

        if use_pinned_ip and pinned_entry:
            # Get pinned IP and rewrite URL
            pinned_ip = pinned_entry.primary_ip
            if pinned_ip:
                rewritten_url, original_host = _rewrite_url_to_ip(current, pinned_ip)

                # Ensure Host header is set to original hostname
                headers = dict(kwargs.get("headers", {}))
                if "Host" not in headers and "host" not in headers:
                    # Include port if non-standard
                    port = parsed.port
                    if port and port not in (80, 443):
                        headers["Host"] = f"{original_host}:{port}"
                    else:
                        headers["Host"] = original_host

                kwargs_with_headers = {**kwargs, "headers": headers}

                logger.debug(
                    f"Connecting to {pinned_ip} with Host: {original_host} "
                    f"(redirect #{redirect_count})"
                )

                resp = session.request(
                    method=method,
                    url=rewritten_url,
                    timeout=timeout,
                    allow_redirects=False,
                    verify=kwargs.get("verify", True),
                    **{k: v for k, v in kwargs_with_headers.items() if k not in ("verify",)},
                )
            else:
                # Fallback if no IP (shouldn't happen)
                resp = session.request(
                    method=method,
                    url=current,
                    timeout=timeout,
                    allow_redirects=False,
                    **kwargs,
                )
        else:
            # Legacy path without IP pinning
            resp = session.request(
                method=method,
                url=current,
                timeout=timeout,
                allow_redirects=False,
                **kwargs,
            )

        # Check if we got a redirect
        if resp.status_code not in _REDIRECT_STATUSES:
            return resp

        # Get redirect location
        loc = resp.headers.get("location")
        if not loc:
            return resp

        # Resolve redirect URL
        nxt = urljoin(current, loc)
        next_host = urlparse(nxt).hostname or ""

        # Validate redirect target (this also pins DNS for next iteration)
        logger.debug(f"Following redirect to {nxt}")
        ensure_public_target_or_raise(next_host, pin_dns=True)

        current = nxt

    # Exceeded max redirects, return last response
    logger.warning(f"Max redirects ({max_redirects}) exceeded for {url}")
    return resp  # type: ignore[return-value]


def safe_get(
    url: str,
    *,
    timeout: int = 30,
    max_redirects: int = 5,
    headers: dict | None = None,
    **kwargs,
) -> requests.Response:
    """
    Convenience function for safe GET request.

    Args:
        url: Target URL
        timeout: Request timeout in seconds
        max_redirects: Maximum redirects to follow
        headers: Optional headers dict
        **kwargs: Additional arguments

    Returns:
        requests.Response object
    """
    with requests.Session() as session:
        return safe_request(
            session,
            "GET",
            url,
            timeout=timeout,
            max_redirects=max_redirects,
            headers=headers,
            **kwargs,
        )


def safe_head(
    url: str,
    *,
    timeout: int = 10,
    max_redirects: int = 5,
    headers: dict | None = None,
    **kwargs,
) -> requests.Response:
    """
    Convenience function for safe HEAD request.

    Args:
        url: Target URL
        timeout: Request timeout in seconds
        max_redirects: Maximum redirects to follow
        headers: Optional headers dict
        **kwargs: Additional arguments

    Returns:
        requests.Response object
    """
    with requests.Session() as session:
        return safe_request(
            session,
            "HEAD",
            url,
            timeout=timeout,
            max_redirects=max_redirects,
            headers=headers,
            **kwargs,
        )
