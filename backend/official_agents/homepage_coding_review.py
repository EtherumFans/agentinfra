"""iCoDer M3-0 — 病案首页编码审核 Agent (Python import alias).

This module re-exports the constants from the actual package at
`official_agents/homepage-coding-review/__init__.py` so that Python can
import them via the underscore-named path (Python doesn't allow hyphens
in module names).

The hyphen-named directory `homepage-coding-review/` matches the
agent_ref convention used elsewhere in iCoDer (e.g. `medical-coding`,
`cdi-review`, `code-reconciler`).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

# Load the hyphen-named package via importlib
_HYPHEN_PKG = "homepage-coding-review"
_module = None
try:
    _module = importlib.import_module(f"official_agents.{_HYPHEN_PKG}")
except Exception:
    # Fallback: import via path
    _pkg_path = Path(__file__).resolve().parent / _HYPHEN_PKG / "__init__.py"
    if _pkg_path.exists():
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            f"official_agents.{_HYPHEN_PKG}", _pkg_path,
        )
        if spec and spec.loader:
            _module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = _module
            spec.loader.exec_module(_module)

if _module is None:
    raise ImportError(
        f"Could not import official_agents.{_HYPHEN_PKG}; "
        f"check that official_agents/homepage-coding-review/__init__.py exists"
    )

# Re-export all public symbols
AGENT_REF = _module.AGENT_REF
AGENT_CATEGORY = _module.AGENT_CATEGORY
AGENT_SUBCATEGORY = _module.AGENT_SUBCATEGORY
AGENT_DIR = _module.AGENT_DIR
AGENT_PACK_JSON = _module.AGENT_PACK_JSON
PIPELINE_STAGES = _module.PIPELINE_STAGES
PRIORITY_HIGH_RISK_CODES = _module.PRIORITY_HIGH_RISK_CODES
ALLOWED_HUMAN_DECISIONS = _module.ALLOWED_HUMAN_DECISIONS
ALLOWED_HUMAN_ACTIONS = _module.ALLOWED_HUMAN_ACTIONS
PIPELINE_VALIDATION_DISCLAIMER = _module.PIPELINE_VALIDATION_DISCLAIMER
load_agent_pack = _module.load_agent_pack

__all__ = [
    "AGENT_REF",
    "AGENT_CATEGORY",
    "AGENT_SUBCATEGORY",
    "AGENT_DIR",
    "AGENT_PACK_JSON",
    "PIPELINE_STAGES",
    "PRIORITY_HIGH_RISK_CODES",
    "ALLOWED_HUMAN_DECISIONS",
    "ALLOWED_HUMAN_ACTIONS",
    "PIPELINE_VALIDATION_DISCLAIMER",
    "load_agent_pack",
]
