"""Stateless bearer-token auth seam.

The host (HIS/EMR/portal) injects a token; the widget never owns credentials. For the
thin slice any non-empty bearer is accepted and the role is read from a ``demo:<role>``
token. Production decodes a host-injected JWT and reads role claims (coder/admin/...).
"""
from __future__ import annotations

from fastapi import Header, HTTPException


def require_auth(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="empty bearer token")
    role = "coder"
    if ":" in token:  # slice convenience: "demo:<role>"
        role = token.split(":", 1)[1] or "coder"
    return {"token": token, "role": role}
