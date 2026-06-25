"""Conftest for app/api unit tests.

Monkey-patches the FastAPI/starlette version mismatch in this env
(fastapi 0.115.0 still passes ``on_startup`` to starlette 1.3.1's
Router, which removed the kwarg). Without the patch, every ``APIRouter()``
instantiation raises ``TypeError`` and we cannot import modules like
``app.api.icoder_coding_methods`` that build an APIRouter at module
load.

Production code never constructs an APIRouter during normal operation
— only FastAPI's include_router() does, and that is patched too.
Mirrors the pattern from ``tests/integration/icoder/a2a/conftest.py``.
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