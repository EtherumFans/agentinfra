"""RuntimeDataPolicy — hospital privacy and data residency controls.

Controls whether external LLM APIs can be called, whether PII must be redacted,
whether full input text is persisted, and marketplace sync mode.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

MarketplaceSyncMode = Literal["offline", "online", "mirror"]


@dataclass
class RuntimeDataPolicy:
    """Controls data residency, external API access, and PII handling.

    Default: strictest (hospital internal deployment safe).
    """

    allow_external_llm: bool = False
    allow_telemetry_upload: bool = False
    pii_redaction_required: bool = True
    marketplace_sync_mode: MarketplaceSyncMode = "offline"
    audit_log_local_only: bool = True
    persist_full_input: bool = False

    @classmethod
    def from_env(cls) -> "RuntimeDataPolicy":
        return cls(
            allow_external_llm=os.environ.get("ICODER_ALLOW_EXTERNAL_LLM", "false").lower() == "true",
            allow_telemetry_upload=os.environ.get("ICODER_ALLOW_TELEMETRY_UPLOAD", "false").lower() == "true",
            pii_redaction_required=os.environ.get("ICODER_PII_REDACTION_REQUIRED", "true").lower() == "true",
            marketplace_sync_mode=_valid_sync_mode(os.environ.get("ICODER_MARKETPLACE_SYNC_MODE", "offline")),
            audit_log_local_only=os.environ.get("ICODER_AUDIT_LOG_LOCAL_ONLY", "true").lower() == "true",
            persist_full_input=os.environ.get("ICODER_PERSIST_FULL_INPUT", "false").lower() == "true",
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "RuntimeDataPolicy":
        path = Path(path)
        if not path.exists():
            return cls.from_env()
        try:
            import yaml
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except ImportError:
            import json
            with open(path, encoding="utf-8") as f:
                data = json.load(f) or {}
        dp = data.get("data_policy", data)
        return cls(
            allow_external_llm=dp.get("allow_external_llm", False),
            allow_telemetry_upload=dp.get("allow_telemetry_upload", False),
            pii_redaction_required=dp.get("pii_redaction_required", True),
            marketplace_sync_mode=_valid_sync_mode(dp.get("marketplace_sync_mode", "offline")),
            audit_log_local_only=dp.get("audit_log_local_only", True),
            persist_full_input=dp.get("persist_full_input", False),
        )

    def can_use_provider(self, provider_name: str) -> tuple[bool, str]:
        """Check if a named provider is allowed under this policy.

        Returns (allowed, reason).
        """
        if provider_name in ("deepseek", "openai_compat") and not self.allow_external_llm:
            return False, f"External LLM provider '{provider_name}' blocked by data_policy (allow_external_llm=false)"
        return True, ""

    def check_agent_requirements(self, llm_capabilities: dict) -> tuple[bool, str]:
        """Check if an agent's LLM requirements are compatible with the data policy.

        Returns (allowed, reason).
        """
        required_models = llm_capabilities.get("required_models", [])
        if not self.allow_external_llm and required_models:
            model_names = [m.get("name", "unknown") for m in required_models if isinstance(m, dict)]
            if model_names:
                return False, f"Agent requires external LLM models {model_names} but allow_external_llm=false"
        return True, ""

    def to_dict(self) -> dict:
        return {
            "allow_external_llm": self.allow_external_llm,
            "allow_telemetry_upload": self.allow_telemetry_upload,
            "pii_redaction_required": self.pii_redaction_required,
            "marketplace_sync_mode": self.marketplace_sync_mode,
            "audit_log_local_only": self.audit_log_local_only,
            "persist_full_input": self.persist_full_input,
        }


def _valid_sync_mode(val: str) -> MarketplaceSyncMode:
    if val in ("offline", "online", "mirror"):
        return val  # type: ignore[return-value]
    return "offline"
