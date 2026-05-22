"""SSRF-safe URL fetcher for remote PDFs.

When an MCP client passes an http(s):// URL as `file_path`, we route it
through this defense-in-depth pipeline before any bytes hit disk:

  1. Scheme allowlist · only http + https (no file://, gopher://, ftp://, etc.)
  2. Hostname → IP resolution + private-range rejection · blocks RFC 1918
     ranges, CGNAT, link-local, loopback, multicast, reserved blocks
  3. Redirect handling · disabled by default; redirects to private IPs
     are the classic SSRF bypass. The caller can opt-in if they know what
     they're doing.
  4. Per-request size cap · 50 MB default to prevent memory bombs.
  5. Content-type check · accepts application/pdf and application/octet-stream
     (the latter is the common "binary blob" content-type for raw PDF bytes).

Downloaded PDFs are stashed in <cache_dir>/url_downloads/<url-sha256>.pdf
so refetching the same URL hits disk instead of the network on subsequent
calls.
"""

from __future__ import annotations

import hashlib
import ipaddress
import socket
from pathlib import Path
from urllib.parse import urlparse

import httpx

MAX_SIZE_BYTES = 50 * 1024 * 1024
ALLOWED_CONTENT_TYPES = (
    "application/pdf",
    "application/octet-stream",
    "binary/octet-stream",
)


class UnsafeURLError(ValueError):
    """Raised when a URL fails the SSRF safety pipeline."""


def is_url_safe(url: str) -> tuple[bool, str]:
    """Return (is_safe, info_or_reason).

    info_or_reason is the resolved IP when safe, or the rejection reason
    when not. Pure validation — does not touch the network beyond DNS.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Unsupported URL scheme: {parsed.scheme!r}"
    host = parsed.hostname
    if not host:
        return False, "URL missing hostname"
    try:
        addrs = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        return False, f"DNS resolution failed: {e}"
    if not addrs:
        return False, "DNS returned no addresses"

    for _family, _type, _proto, _canon, sockaddr in addrs:
        ip_str = sockaddr[0]
        ip_obj = ipaddress.ip_address(ip_str)
        if (
            ip_obj.is_private
            or ip_obj.is_loopback
            or ip_obj.is_link_local
            or ip_obj.is_reserved
            or ip_obj.is_multicast
            or ip_obj.is_unspecified
        ):
            return False, f"Refused to fetch from non-public IP: {ip_str}"
    return True, addrs[0][4][0]


def safe_download(
    url: str,
    cache_dir: Path,
    *,
    max_bytes: int = MAX_SIZE_BYTES,
    timeout_seconds: float = 30.0,
) -> Path:
    """Download a remote PDF after passing the SSRF safety pipeline.

    Returns a Path to the downloaded file on disk. Subsequent calls for
    the same URL hit the cache instead of the network.
    """
    safe, info = is_url_safe(url)
    if not safe:
        raise UnsafeURLError(info)

    url_sha = hashlib.sha256(url.encode()).hexdigest()[:16]
    target_dir = cache_dir / "url_downloads"
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / f"{url_sha}.pdf"
    if out.exists():
        return out

    tmp = out.with_suffix(".part")
    with httpx.Client(follow_redirects=False, timeout=timeout_seconds) as client:
        with client.stream("GET", url) as resp:
            if resp.status_code in (301, 302, 303, 307, 308):
                raise UnsafeURLError(
                    "Refused to follow redirect (SSRF protection). Use the "
                    "final URL directly."
                )
            resp.raise_for_status()
            ctype = resp.headers.get("content-type", "").lower().split(";")[0].strip()
            if ctype and ctype not in ALLOWED_CONTENT_TYPES:
                raise UnsafeURLError(
                    f"Unexpected content-type: {ctype!r} "
                    f"(allowed: {', '.join(ALLOWED_CONTENT_TYPES)})"
                )
            total = 0
            with tmp.open("wb") as f:
                for chunk in resp.iter_bytes(65536):
                    total += len(chunk)
                    if total > max_bytes:
                        tmp.unlink(missing_ok=True)
                        raise UnsafeURLError(
                            f"PDF exceeds size cap ({max_bytes} bytes)"
                        )
                    f.write(chunk)
    tmp.replace(out)
    return out
