"""Test config for orchestrator tests.

Skips FastAPI-based route tests when the installed fastapi/starlette
combination is broken (pre-existing env issue: ``FastAPI()`` raises
``TypeError: Router.__init__() got an unexpected keyword argument
'on_startup'`` because starlette removed that kwarg in 0.40+).
"""

from __future__ import annotations

import pytest


try:
    from fastapi import FastAPI  # noqa: F401

    _FastAPI_OK = True
    try:
        _app = FastAPI()
    except TypeError:
        _FastAPI_OK = False
except Exception:
    _FastAPI_OK = False


_fastapi_broken_reason = (
    "fastapi/starlette env mismatch (Router.__init__ got 'on_startup')"
    if not _FastAPI_OK
    else None
)


def pytest_collection_modifyitems(config, items):
    if _FastAPI_OK:
        return
    skip_marker = pytest.mark.skip(reason=_fastapi_broken_reason)
    for item in items:
        if "route" in item.keywords or "fastapi" in item.keywords:
            item.add_marker(skip_marker)