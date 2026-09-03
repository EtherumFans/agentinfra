"""pytest plugin: Gate 4R node filter.

Loads a stable node-ID list from a file (env var GATE4R_NODE_FILTER_FILE)
and restricts collection to nodes whose IDs appear in that file.

Usage:
    GATE4R_NODE_FILTER_FILE=gate4r_diff/common_nodeids.txt \\
        pytest -p scripts.audit.gate4r_node_filter backend/tests

The plugin is intentionally minimal: it does NOT do any test selection
based on outcome, only on node ID. The node-ID file is the only input.
The plugin is read-only with respect to the filesystem — it opens the
filter file once at conftest collect time and never writes.

This module is invoked via `-p scripts.audit.gate4r_node_filter`, so
the path scripts/audit/gate4r_node_filter.py must be importable from
the pytest rootdir. It is designed to be hermetic: no environment
mutation, no network, no globals beyond the single module-level filter
set.
"""

from __future__ import annotations

import os
from typing import Set


def _load_filter(path: str) -> Set[str]:
    nodes: Set[str] = set()
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            s = raw.strip()
            if s and "::" in s:
                nodes.add(s)
    return nodes


def pytest_collection_modifyitems(session, config, items):
    """Keep only items whose node ID is in the filter file.

    If GATE4R_NODE_FILTER_FILE is unset, this plugin is a no-op (so the
    same conftest can ship in the tree without breaking normal runs).
    """
    path = os.environ.get("GATE4R_NODE_FILTER_FILE")
    if not path or not os.path.isfile(path):
        return
    allowed = _load_filter(path)
    selected = [item for item in items if item.nodeid in allowed]
    deselected = [item for item in items if item.nodeid not in allowed]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
    items[:] = selected
