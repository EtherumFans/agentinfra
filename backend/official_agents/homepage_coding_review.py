"""iCoDer M3-0 — 病案首页编码审核 Agent (Python import alias).

DEPRECATED 2026-06-22 → M2b
===========================

This 14-stage cosmetic pipeline has been superseded by MedCodER's 5-stage
pipeline exposed via ``icoder/medcoder-coding-review-agent@1.0.0`` (M0+M1).
New code MUST use the MedCodER Coding Review Agent (see
``official_agents/medcoder-coding-review/agent_pack.json`` and
``MedCodERStrategy.run_variant`` via ``CodingExpert``).

This module is retained for back-compat with the 7 call sites listed
below; it will be **deleted in M2b** after the 4 ``e2e_product`` tests
are rewritten to exercise the MedCodER 5-stage trace:

  - icoder_runtime/reports/coding_review_report.py:43
  - app/api/icoder_coding_review.py:60
  - tests/test_api/test_icoder_coding_review_no_key.py:26
  - tests/e2e_product/test_high_risk_priority_codes.py:22
  - tests/e2e_product/test_report_disclaimer_visible.py:56
  - tests/e2e_product/test_pipeline_validation_full_flow.py:24
  - tests/e2e_product/test_run_trace_14_stages.py:14

Replacement: ``icoder/medcoder-coding-review-agent@1.0.0`` (MCP tools at
``POST /mcp/v1/tools/{list,call}``).
"""

from __future__ import annotations

import importlib
import sys
import warnings
from pathlib import Path

# Emit a DeprecationWarning at import time so callers (tests + reports)
# notice the migration window. ``stacklevel=2`` makes the warning point
# at the importer, not this module.
warnings.warn(
    "official_agents.homepage_coding_review is deprecated since 2026-06-22; "
    "use the MedCodER Coding Review Agent "
    "(icoder/medcoder-coding-review-agent@1.0.0) instead. "
    "This module will be removed in M2b.",
    DeprecationWarning,
    stacklevel=2,
)

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
