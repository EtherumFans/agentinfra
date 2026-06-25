"""Shared fixtures for the methods unit tests.

All methods tests share the GLOBAL_REGISTRY singleton, so we install an
autouse session-scope fixture that snapshots state at start and restores
it after each test. Individual tests can also clear() if they need a
truly empty registry.
"""

from __future__ import annotations

import pytest

from icoder_runtime.methods.registry import GLOBAL_REGISTRY


@pytest.fixture(autouse=True)
def _isolate_global_registry():
    """Snapshot registry before each test, restore after.

    Avoids the "leftover from prior test" failure mode where helper
    tests that don't explicitly clean up leave stub methods behind.
    """
    saved = list(GLOBAL_REGISTRY.list())
    try:
        yield
    finally:
        # Clear + restore — last-writer-wins re-register so the
        # builtin methods retain their original identity.
        GLOBAL_REGISTRY.clear()
        for m in saved:
            GLOBAL_REGISTRY.register(m)