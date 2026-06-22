"""Integration test conftest: enable pytest-asyncio auto mode."""

from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config, items):
    """Auto-mark async tests/fixtures so they run under pytest-asyncio."""
    asyncio_mode = getattr(config, "asyncio_mode", "strict")
    if asyncio_mode == "auto":
        return
    for item in items:
        if "asyncio" not in item.keywords and getattr(item, "obj", None) is not None:
            if item.get_closest_marker("asyncio") is None:
                item.add_marker(pytest.mark.asyncio)