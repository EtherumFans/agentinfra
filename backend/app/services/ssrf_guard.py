"""SSRF Guard — block requests to internal / loopback / metadata endpoints.

A1B-AE-R.3 §3 (2026-07-23): wraps every outbound MCP / Expert HTTP call
with a pre-flight host check that rejects URLs pointing at:

- RFC1918 private ranges (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)
- Loopback (127.0.0.0/8, ::1)
- Link-local (169.254.0.0/16, fe80::/10)
- Cloud metadata endpoints (169.254.169.254 most importantly)
- Carrier-grade NAT (100.64.0.0/10)
- Unique-local IPv6 (fc00::/7)
- Any host that resolves to one of the above (DNS rebinding defence)

The guard is intentionally synchronous and cheap — it short-circuits
BEFORE httpx.AsyncClient opens a connection. Charter §6 region-routing
still applies on top of this (CN/EU/US allowlist) and is enforced by
the External-Expert Gate, not here.
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse


class SSRFError(Exception):
    """Raised when a URL targets a blocked host."""

    def __init__(self, host: str, reason: str) -> None:
        self.host = host
        self.reason = reason
        super().__init__(f"SSRF blocked: host={host!r} reason={reason}")


# Network ranges that are ALWAYS blocked. Any resolved IP landing in
# these ranges triggers SSRFError before any TCP connect.
BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]

# Cloud metadata endpoints — also always blocked (covered by 169.254.0.0/16
# for AWS/GCP; Azure uses a different IP and host-header scheme).
CLOUD_METADATA_HOSTS = frozenset(
    {
        "169.254.169.254",  # AWS / GCP
        "metadata.google.internal",  # GCP DNS name
        "metadata.azure.com",  # Azure
        "169.254.169.254",  # duplicate on purpose for clarity
    }
)


@dataclass
class SSRFCheckResult:
    permitted: bool
    host: str
    reason: str = ""


def _is_blocked_ip(ip_str: str) -> tuple[bool, str]:
    """Return (blocked, reason) for a single IP literal."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True, f"unparseable IP literal {ip_str!r}"
    for net in BLOCKED_NETWORKS:
        if ip in net:
            return True, f"{ip} in blocked network {net}"
    return False, ""


def _resolve_host(host: str) -> list[str]:
    """Resolve a hostname to IPv4 + IPv6 literals. Empty list on failure."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return []
    return list({info[4][0] for info in infos})


def check_url(url: str) -> SSRFCheckResult:
    """Pre-flight check a URL. Returns SSRFCheckResult.

    ``permitted=False`` means the caller MUST NOT open a connection.
    """
    if not url or not url.strip():
        return SSRFCheckResult(permitted=False, host="", reason="empty URL")

    try:
        parsed = urlparse(url)
    except Exception as e:
        return SSRFCheckResult(
            permitted=False, host="", reason=f"URL parse error: {e}"
        )

    scheme = (parsed.scheme or "").lower()
    if scheme not in {"http", "https"}:
        return SSRFCheckResult(
            permitted=False,
            host=parsed.hostname or "",
            reason=f"scheme {scheme!r} not allowed (http/https only)",
        )

    host = parsed.hostname or ""
    if not host:
        return SSRFCheckResult(
            permitted=False, host="", reason="no hostname in URL"
        )

    # Cloud metadata hostnames
    if host.lower() in CLOUD_METADATA_HOSTS:
        return SSRFCheckResult(
            permitted=False,
            host=host,
            reason=f"{host} is a cloud metadata endpoint",
        )

    # If host is already an IP literal, check directly
    try:
        ipaddress.ip_address(host)
        blocked, reason = _is_blocked_ip(host)
        if blocked:
            return SSRFCheckResult(permitted=False, host=host, reason=reason)
    except ValueError:
        # Host is a DNS name — resolve and check each record
        # (DNS rebinding defence)
        ips = _resolve_host(host)
        if not ips:
            # Resolution failed — fail CLOSED (block). Callers that
            # need to allow unresolved hosts must opt in explicitly.
            return SSRFCheckResult(
                permitted=False,
                host=host,
                reason=f"DNS resolution returned no records for {host!r}",
            )
        for ip_str in ips:
            blocked, reason = _is_blocked_ip(ip_str)
            if blocked:
                return SSRFCheckResult(
                    permitted=False,
                    host=host,
                    reason=f"{host} resolves to {reason}",
                )

    return SSRFCheckResult(permitted=True, host=host)


def assert_url_safe(url: str) -> None:
    """Raise SSRFError if the URL is not safe. Otherwise no-op."""
    result = check_url(url)
    if not result.permitted:
        raise SSRFError(host=result.host, reason=result.reason)


__all__ = [
    "SSRFError",
    "SSRFCheckResult",
    "BLOCKED_NETWORKS",
    "CLOUD_METADATA_HOSTS",
    "check_url",
    "assert_url_safe",
]
