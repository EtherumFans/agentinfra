"""Integration test conftest: enable pytest-asyncio auto mode.

Phase 3-D0 Task 3 (2026-07-06): only auto-mark ``async def`` test
functions. The previous version marked EVERY collected item (sync
or async), which triggered ``PytestWarning: asyncio mark on
non-async function`` on every sync test under ``tests/integration/``.
"""

from __future__ import annotations

import inspect

import pytest


def pytest_collection_modifyitems(config, items):
    """Auto-mark async tests/fixtures so they run under pytest-asyncio."""
    asyncio_mode = getattr(config, "asyncio_mode", "strict")
    if asyncio_mode == "auto":
        return
    for item in items:
        if "asyncio" in item.keywords:
            continue
        obj = getattr(item, "obj", None)
        if obj is None:
            continue
        # Only auto-mark async def functions — sync tests must NOT carry
        # the asyncio mark (it raises PytestWarning + doesn't help).
        if not inspect.iscoroutinefunction(obj):
            continue
        if item.get_closest_marker("asyncio") is None:
            item.add_marker(pytest.mark.asyncio)