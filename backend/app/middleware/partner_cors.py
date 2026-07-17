"""Phase 7 Gate 6 §11.1 — per-client Allowed Origins enforcement.

The existing CORSMiddleware (in main.py) uses a static allowlist from
``settings.CORS_ORIGINS`` — appropriate for the Console (one known
origin) but not for partners (each partner brings their own Origin).

This middleware adds a second layer for partner-facing routes:

  /api/v1/agents/{id}/run
  /api/v1/runs/{id}
  /api/v1/runs/{id}/cancel
  /api/embedded/*

When the request's ``Origin`` header matches any OAuthClient's
``allowed_origins`` (Phase 7 Gate 5), we add the appropriate
``Access-Control-Allow-Origin`` response header. When the Origin
doesn't match ANY allowlist (Console static OR any client dynamic),
we reject with 403 for non-preflight and a CORS error for preflight.

§11.1 requirements:
  - Exact Origin match (no wildcard when client_credentials is enabled)
  - No '*' with Client Credentials
  - Localhost whitelist supported for dev
  - Origin mismatch → reject
  - Preflight correct
  - Errors don't leak Secret / internal info

Design note: rather than replace CORSMiddleware (which would risk
breaking Console auth), we add this as a layer that runs BEFORE it
on partner routes. The static CORSMiddleware still owns the Console
path. This keeps §4 "no parallel implementations" happy — we're
augmenting, not duplicating.
"""
from __future__ import annotations

import logging
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = logging.getLogger(__name__)


# Routes where partner CORS enforcement kicks in. We're intentionally
# narrow — Console routes keep the static allowlist.
_PARTNER_ROUTE_PREFIXES = (
    "/api/v1/agents/",       # POST /api/v1/agents/{id}/run
    "/api/v1/runs/",         # GET/POST runs + cancel
    "/api/embedded/",        # Phase 6 widget handshakes
    "/examples/",            # Phase 7 Gate 1 demo static assets
)


def _is_partner_route(path: str) -> bool:
    return any(path.startswith(p) for p in _PARTNER_ROUTE_PREFIXES)


async def _all_partner_origins() -> set[str]:
    """Read all OAuthClient.allowed_origins from the DB.

    Cached for 60s to avoid hitting the DB on every preflight.
    """
    import time
    now = time.time()
    cache = _all_partner_origins._cache  # type: ignore[attr-defined]
    if cache is not None and cache["expires_at"] > now:
        return cache["origins"]

    try:
        from app.database import AsyncSessionLocal
        from sqlalchemy import select, text
        origins: set[str] = set()
        async with AsyncSessionLocal() as db:
            # JSON column → flatten in Python (portable across SQLite + PG).
            stmt = select(text("allowed_origins")).select_from(text("oauth_clients"))
            result = await db.execute(stmt)
            for (raw,) in result.fetchall():
                if not raw:
                    continue
                try:
                    if isinstance(raw, str):
                        import json
                        raw = json.loads(raw)
                    if isinstance(raw, list):
                        origins.update(o for o in raw if isinstance(o, str))
                except Exception:
                    continue
        _all_partner_origins._cache = {"origins": origins, "expires_at": now + 60}  # type: ignore[attr-defined]
        return origins
    except Exception as e:
        logger.warning("partner_cors: failed to load origins from DB: %s", e)
        # On DB failure, deny by default (don't silently allow unknown origins).
        return set()


# Static cache attribute
_all_partner_origins._cache = None  # type: ignore[attr-defined]


class PartnerCORSMiddleware(BaseHTTPMiddleware):
    """Per-client Allowed Origins enforcement (Phase 7 §11.1).

    Layered on top of the existing static CORS middleware. For partner
    routes, we add an explicit ``Access-Control-Allow-Origin`` echo
    when the Origin is on the partner allowlist. For preflight OPTIONS
    requests, we short-circuit with a 403 if the Origin isn't allowed.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        origin = request.headers.get("origin") or ""
        path = request.url.path

        # Only enforce on partner routes; Console routes use the static
        # CORSMiddleware allowlist.
        if not _is_partner_route(path):
            return await call_next(request)

        # If no Origin header, this is a same-origin request — let it
        # through (CORS doesn't apply).
        if not origin:
            return await call_next(request)

        # Phase 7 Gate 10 fix: same-origin requests (Origin matches the
        # request's own Host) are NOT cross-origin from a CORS perspective.
        # The demos at /examples/* load /api/embedded/assistant.js from
        # the same host:port, so the browser sends an Origin header but
        # the request is not actually cross-origin. Skip enforcement in
        # this case — otherwise we'd block the demo's own widget load.
        host_header = request.headers.get("host") or ""
        if host_header:
            request_base = f"{request.url.scheme}://{host_header}"
            if origin.rstrip("/") == request_base.rstrip("/"):
                return await call_next(request)

        # Build the full allowlist: static (Console) + dynamic (partners).
        from app.config import settings
        static_origins = set(getattr(settings, "CORS_ORIGINS", []) or [])
        partner_origins = await _all_partner_origins()
        allowed = static_origins | partner_origins

        if origin not in allowed:
            # Preflight OPTIONS: respond with 403 + a clear CORS error.
            if request.method == "OPTIONS":
                return JSONResponse(
                    status_code=403,
                    content={
                        "code": "ORIGIN_NOT_ALLOWED",
                        "message": (
                            "Origin not in allowed_origins for any configured "
                            "API Client. Contact your iCoDer tenant admin."
                        ),
                    },
                    headers={
                        # Still emit CORS headers so the browser surfaces a
                        # CORS error (not a generic network error).
                        "Access-Control-Allow-Origin": "null",
                        "Cache-Control": "no-store",
                    },
                )
            # Non-preflight from disallowed origin: also reject. The
            # browser will surface a CORS error.
            return JSONResponse(
                status_code=403,
                content={
                    "code": "ORIGIN_NOT_ALLOWED",
                    "message": "Origin not allowed.",
                },
                headers={
                    "Access-Control-Allow-Origin": "null",
                    "Cache-Control": "no-store",
                },
            )

        # Origin allowed.
        #
        # For OPTIONS preflight we MUST short-circuit here. If we let the
        # request reach the underlying static CORSMiddleware, it'll see a
        # partner Origin not in settings.CORS_ORIGINS and return 400
        # "Disallowed CORS origin" — even though the Origin is in fact
        # permitted via the per-client allowlist. So we own the preflight
        # response entirely on partner routes.
        is_preflight = (
            request.method == "OPTIONS"
            and "access-control-request-method" in request.headers
        )
        if is_preflight:
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Methods": (
                        "GET, POST, PUT, PATCH, DELETE, OPTIONS"
                    ),
                    "Access-Control-Allow-Headers": (
                        "Authorization, Content-Type, X-Request-Id, "
                        "Idempotency-Key, X-Tenant, X-Tenant-Name, "
                        "X-iCoDer-Demo-Version, X-Attempt, Accept"
                    ),
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Max-Age": "600",
                    "Vary": "Origin",
                    "Cache-Control": "no-store",
                },
            )

        # Non-preflight with allowed origin — let the route handler proceed
        # and tag the response. The static CORSMiddleware won't add a CORS
        # header (partner Origin isn't in CORS_ORIGINS) but it also won't
        # strip ours since we're the outer layer on the response path.
        response = await call_next(request)
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        return response
