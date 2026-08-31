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

    Behaviour matrix (Phase A1A Gate 4.2 — authoritative source = JWT):

    The authoritative tenant derivation is now ALWAYS the JWT ``org_id``
    claim, never the header. The header is a non-authoritative hint
    used only for log scoping. This closes GATE3R_011 (frontend did
    not send Tenant-Name) and removes the local-dev silent-bypass risk.

    * **JWT present** — ``request.state.tenant_name`` is set to the JWT
      ``org_id`` claim. Header value, if sent, is recorded separately
      on ``request.state.tenant_header_hint`` for audit log scoping.
      If the header disagrees with the JWT → 400 ``tenant_header_mismatch``.
    * **JWT absent + cloud mode** — 400 ``tenant_header_required`` (cloud
      requires authentication, and authentication carries the org claim).
    * **JWT absent + local mode + ``ICODER_SINGLE_TENANT_ORG_ID`` set** —
      ``request.state.tenant_name`` is set to the configured single-tenant
      org. Header is ignored if present (with a warning logged if it
      disagrees).
    * **JWT absent + local mode + no single-tenant config** — 400
      ``tenant_context_required``. Silent pass-through is no longer
      permitted (was the GATE3R_011 leak vector).
    * **Tenant-exempt paths** (``/api/health``, ``/docs``, ``/api/oauth/``)
      — pass-through as before; no org derivation.

    The ``get_request_tenant`` accessor still returns
    ``request.state.tenant_name``. Existing call sites (e.g. the console
    trace path) now read the JWT-derived value, not a missing header.
    """

    async def dispatch(self, request: Request, call_next):
        header_hint = _read_tenant_header(request)
        request.state.tenant_header_hint = header_hint

        if _is_tenant_exempt(request.url.path):
            request.state.tenant_name = header_hint
            return await call_next(request)

        # ── Authoritative org derivation ──────────────────────────
        # JWT org_id wins. Header is hint-only.
        auth_header = request.headers.get("authorization", "")
        jwt_org_id: Optional[str] = None
        if auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1].strip()
            jwt_org_id = _peek_jwt_org_id(token)

        authoritative_org: Optional[str] = None
        rejection: Optional[tuple[str, str]] = None

        if jwt_org_id:
            # Header (if present) must agree with JWT.
            if header_hint and header_hint != jwt_org_id:
                rejection = (
                    "tenant_header_mismatch",
                    (
                        f"X-Tenant/Tenant-Name header ({header_hint!r}) does not "
                        f"match the tenant claim in the bearer JWT ({jwt_org_id!r}). "
                        "The JWT org_id is authoritative; the header is a hint."
                    ),
                )
            authoritative_org = jwt_org_id
        else:
            # No JWT. Cloud mode requires authentication — reject.
            if settings.ICODER_DEPLOYMENT_MODE == "cloud":
                rejection = (
                    "tenant_header_required",
                    (
                        "Cloud mode requires an authenticated bearer token; the "
                        "tenant context is derived from the token's org_id claim."
                    ),
                )
            else:
                # Local mode: fall back to explicit single-tenant config.
                single_tenant_org = _single_tenant_org_id()
                if single_tenant_org:
                    authoritative_org = single_tenant_org
                    if header_hint and header_hint != single_tenant_org:
                        logger.warning(
                            "Tenant-Name hint %r disagrees with "
                            "ICODER_SINGLE_TENANT_ORG_ID=%r; using the latter.",
                            header_hint, single_tenant_org,
                        )
                else:
                    rejection = (
                        "tenant_context_required",
                        (
                            "No authenticated tenant context. Set "
                            "ICODER_SINGLE_TENANT_ORG_ID for local single-tenant "
                            "mode, or supply a bearer token with an org_id claim."
                        ),
                    )

        if rejection is not None:
            detail, message = rejection
            return JSONResponse(
                status_code=400,
                content={"detail": detail, "message": message},
            )

        request.state.tenant_name = authoritative_org
        from app.services.tenant_model_routing import (
            bind_request_tenant,
            reset_request_tenant,
        )

        routing_token = bind_request_tenant(authoritative_org)
        try:
            return await call_next(request)
        finally:
            reset_request_tenant(routing_token)


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


def _single_tenant_org_id() -> Optional[str]:
    """Local-dev fallback org for unauthenticated requests.

    Returns ``settings.ICODER_SINGLE_TENANT_ORG_ID`` stripped of
    whitespace. Empty string → ``None`` (treated as unset). This is
    ONLY consulted when no bearer JWT is present, and ONLY in local
    deployment mode — cloud mode rejects unauthenticated requests
    earlier in the dispatch matrix.

    Reading from Settings (not os.environ directly) means tests can
    monkey-patch the value via the ``ICODER_SINGLE_TENANT_ORG_ID`` env
    var or by overriding the field on the singleton.
    """
    value = (settings.ICODER_SINGLE_TENANT_ORG_ID or "").strip()
    return value or None


def _peek_jwt_org_id(token: str) -> Optional[str]:
    """Decoded-only JWT body lookup (no signature verification).

    Used purely for cross-check logging; the actual auth middleware still
    verifies signatures. Defends against malformed tokens by returning
    ``None`` instead of raising.
    """
    try:
        # Decode body without verification — we only want the org_id claim.
        import jwt
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_exp": False},
        )
        org_id = claims.get("org_id")
        return org_id if isinstance(org_id, str) and org_id else None
    except Exception:
        return None
