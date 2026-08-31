"""Governed local Rule Explainer Agent."""

from .agent import (
    AGENT_REF,
    ASSET_ID,
    LOCAL_RUNTIME_MODE,
    OUTPUT_CONTRACT_REF,
    explain_code,
    extract_code,
    to_pack_output,
    verify_rule_explainer_health,
)

__all__ = [
    "AGENT_REF",
    "ASSET_ID",
    "LOCAL_RUNTIME_MODE",
    "OUTPUT_CONTRACT_REF",
    "explain_code",
    "extract_code",
    "to_pack_output",
    "verify_rule_explainer_health",
]
