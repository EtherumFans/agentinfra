"""A2A integration test conftest.

Monkey-patches the FastAPI/starlette version mismatch in this env
(fastapi 0.115.0 still passes ``on_startup`` to starlette 1.3.1's
Router, which removed the kwarg). Without the patch, every ``APIRouter()``
instantiation raises ``TypeError`` and TestClient cannot mount routers.

The patch is test-only — production code never constructs an APIRouter
at module load, so it is unaffected. Phase-1 routes do not use
on_startup/on_shutdown at all.
"""

from __future__ import annotations

import starlette.routing as _sr

_orig_router_init = _sr.Router.__init__


def _patched_router_init(self, *args, **kwargs):
    """Drop ``on_startup`` / ``on_shutdown`` kwargs before delegating."""
    for k in ("on_startup", "on_shutdown"):
        kwargs.pop(k, None)
    return _orig_router_init(self, *args, **kwargs)


_sr.Router.__init__ = _patched_router_init

# FastAPI 0.115.0's APIRouter no longer carries on_startup/on_shutdown
# attributes (they were removed); restore them as empty lists so
# ``fastapi.applications.include_router`` can iterate ``router.on_startup``.
import fastapi.routing as _fr  # noqa: E402

_fr.APIRouter.on_startup = []
_fr.APIRouter.on_shutdown = []