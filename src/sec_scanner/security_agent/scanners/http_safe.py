from __future__ import annotations

from urllib.parse import urljoin, urlparse

import requests

from ...targets import ensure_public_target_or_raise

_REDIRECT_STATUSES = {301, 302, 303, 307, 308}


def safe_request(
    session: requests.Session,
    method: str,
    url: str,
    *,
    timeout,
    max_redirects: int = 5,
    **kwargs,
) -> requests.Response:
    """
    Make an HTTP request with:
    - redirects disabled by default (manual follow with SSRF checks)
    - redirect target validated (prevents redirect-to-private/metadata SSRF)
    """
    current = url
    resp: requests.Response | None = None
    for _ in range(max_redirects + 1):
        resp = session.request(
            method=method,
            url=current,
            timeout=timeout,
            allow_redirects=False,
            **kwargs,
        )
        if resp.status_code not in _REDIRECT_STATUSES:
            return resp

        loc = resp.headers.get("location")
        if not loc:
            return resp

        nxt = urljoin(current, loc)
        host = urlparse(nxt).hostname or ""
        ensure_public_target_or_raise(host)
        current = nxt

    # Shouldn't happen, but return the last response if redirect loop
    return resp  # type: ignore[return-value]
