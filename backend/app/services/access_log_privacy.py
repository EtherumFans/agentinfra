"""Fail-safe redaction for request targets emitted by Uvicorn access logs.

Reverse proxies must also omit query strings, but direct Uvicorn execution is
common in development and CI.  This filter removes every query/fragment and
redacts the actor-bound Artifact download grant locator before formatting the
request line.  It never inspects headers or bodies.
"""

from __future__ import annotations

import logging
import re


_DOWNLOAD_GRANT_PATH = re.compile(
    r"(?P<prefix>/api/v2/agentic/artifact-objects/download/)"
    r"grant-[0-9A-Fa-f-]{36}"
)
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]+")


def redact_request_target(target: object) -> str:
    """Return a log-safe path without query values, fragments, or grant IDs."""

    value = str(target or "/")
    value = _CONTROL_CHARACTERS.sub("", value)
    value = value.split("#", 1)[0].split("?", 1)[0] or "/"
    return _DOWNLOAD_GRANT_PATH.sub(r"\g<prefix>[grant-redacted]", value)


class UvicornAccessLogPrivacyFilter(logging.Filter):
    """Redact the request-target argument used by Uvicorn's AccessFormatter."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3:
            sanitized = list(args)
            sanitized[2] = redact_request_target(sanitized[2])
            record.args = tuple(sanitized)
        return True


def install_uvicorn_access_log_privacy() -> None:
    """Install exactly once after Uvicorn has configured its loggers."""

    access_logger = logging.getLogger("uvicorn.access")
    if any(isinstance(item, UvicornAccessLogPrivacyFilter) for item in access_logger.filters):
        return
    access_logger.addFilter(UvicornAccessLogPrivacyFilter())


__all__ = [
    "UvicornAccessLogPrivacyFilter",
    "install_uvicorn_access_log_privacy",
    "redact_request_target",
]
