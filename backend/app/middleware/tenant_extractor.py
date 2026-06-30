"""Corti-style tenant header middleware.

Implements the ``Tenant-Name`` / ``X-Tenant`` header pattern documented at
docs.corti-reverse-engineered/SUMMARY.md §13.2 — every API call carries the
tenant context (e.g. ``base`` for default, or a custom hospital slug). In
local development the header is OPTIONAL; in cloud mode it is MANDATORY and
must match the ``org_id`` claim embedded in the bearer JWT.

Usage:

    from app.middleware.tenant_extractor import (
        TenantHeaderMiddleware, get_request_tenant,
    )

    app.add_middleware(TenantHeaderMiddleware)

    @app.get("/foo")
    async def foo(request: Request):
        tenant = get_request_tenant(request)
        ...
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings

logger = logging.getLogger(__name__)

# Standard tenant header names. ``Tenant-Name`` matches the Corti auth spec;
# ``X-Tenant`` is a vendor-friendly alias (some proxies strip Mintlify-style
# headers without warning).
TENANT_HEADERS: tuple[str, ...] = ("tenant-name", "x-tenant")

# Paths where the tenant header is irrelevant (docs, health, OAuth itself).
# OAuth is exempt because the *token-issuing* call must succeed even when a
# caller has not yet been authenticated (otherwise no client could ever
# bootstrap). Authorization Code flows carry the tenant via the
# ``/api/oauth/realms/{realm}/token`` path instead.
_TENANT_EXEMPT_PREFIXES: tuple[str, ...] = (
    "/api/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/oauth/",
)


def _is_tenant_exempt(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in _TENANT_EXEMPT_PREFIXES)


class TenantHeaderMiddleware(BaseHTTPMiddleware):
    """Parse and validate the ``Tenant-Name`` header.

    Behaviour matrix:

    * **Local mode + no header + no JWT** — pass-through (single-tenant dev).
    * **Local mode + header + JWT** — header must match JWT ``org_id`` else
      400 ``tenant_header_mismatch``.
    * **Local mode + header + no JWT** — header is recorded on ``request.state``
      so the handler can use it for log scoping; no error.
    * **Cloud mode + missing header (authed call)** — 400 ``tenant_header_required``.
    * **Cloud mode + header mismatch with JWT ``org_id``** — 400 ``tenant_header_mismatch``.
    """

    async def dispatch(self, request: Request, call_next):
        request.state.tenant_name = _read_tenant_header(request)

        if _is_tenant_exempt(request.url.path):
            return await call_next(request)

        tenant_state = request.state.tenant_name

        # If a bearer token is attached, peek at its ``org_id`` claim so we
        # can cross-check without forcing every middleware consumer to also
        # decode the JWT.
        auth_header = request.headers.get("authorization", "")
        jwt_org_id: Optional[str] = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            jwt_org_id = _peek_jwt_org_id(token)

        # Cross-check when both pieces are present.
        if tenant_state and jwt_org_id and tenant_state != jwt_org_id:
            return JSONResponse(
                status_code=400,
                content={
                    "detail": "tenant_header_mismatch",
                    "message": (
                        f"X-Tenant/Tenant-Name header ({tenant_state!r}) does not match "
                        f"the tenant claim in the bearer JWT ({jwt_org_id!r})."
                    ),
                },
            )

        # Cloud mode: require a tenant header for any authenticated path.
        if settings.ICODER_DEPLOYMENT_MODE == "cloud":
            if not tenant_state:
                return JSONResponse(
                    status_code=400,
                    content={
                        "detail": "tenant_header_required",
                        "message": (
                            "Cloud mode requires Tenant-Name (or X-Tenant) header "
                            "on all authenticated API calls."
                        ),
                    },
                )

        return await call_next(request)


def get_request_tenant(request: Request) -> Optional[str]:
    """Return the tenant header value resolved earlier by the middleware.

    Returns ``None`` if the caller did not send a tenant header (local-dev
    behaviour). Handlers must NOT assume a tenant is present.
    """
    return getattr(request.state, "tenant_name", None)


def _read_tenant_header(request: Request) -> Optional[str]:
    for header in TENANT_HEADERS:
        value = request.headers.get(header)
        if value:
            return value.strip()
    return None


def _peek_jwt_org_id(token: str) -> Optional[str]:
    """Decoded-only JWT body lookup (no signature verification).

    Used purely for cross-check logging; the actual auth middleware still
    verifies signatures. Defends against malformed tokens by returning
    ``None`` instead of raising.
    """
    try:
        # Decode body without verification — we only want the org_id claim.
        from jose import jwt
        claims = jwt.get_unverified_claims(token)
        org_id = claims.get("org_id")
        return org_id if isinstance(org_id, str) and org_id else None
    except Exception:
        return None
