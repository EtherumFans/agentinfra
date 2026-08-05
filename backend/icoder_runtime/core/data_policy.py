"""RuntimeDataPolicy — hospital privacy and data residency controls.

Controls whether external LLM APIs can be called, whether PII must be redacted,
whether full input text is persisted, marketplace sync mode, and (Phase A1A
Gate 4.5) regional data residency.

Gate 4.5 closes the regional-residency gap flagged in the Gate 4.1
threat model (T-CC-5): a CN tenant's PHI could egress to a US-region
LLM provider because the policy had no region field and the provider
registry had no per-provider region metadata. The new policy adds:

- ``region`` — the tenant's data-residency region (``eu`` / ``us`` / ``cn``)
- ``egress_policy`` — ``strict`` (deny cross-region) | ``best_effort``
  (warn + allow) | ``off`` (skip check, backwards-compat)
- ``can_use_provider`` now consults the provider's region metadata
  via the ``PROVIDER_REGIONS`` table below.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

_logger = logging.getLogger(__name__)

MarketplaceSyncMode = Literal["offline", "online", "mirror"]
EgressPolicy = Literal["strict", "best_effort", "off"]
Region = Literal["eu", "us", "cn"]


# ── Phase A1A Gate 4.5 — provider region registry ────────────────────
#
# The canonical source of truth for which region each LLM provider
# stores user data in. The values reflect the provider's published
# data-residency stance as of 2026-07-20. Update this table when a
# provider publishes a new region or a tenant's compliance team
# accepts a new cross-region arrangement.
#
# - ``deepseek`` → ``cn`` (DeepSeek is operated from China; data
#   stays in mainland China by policy)
# - ``openai_compat`` → ``us`` (the OpenAI-compatible endpoint
#   pattern typically points at a US-hosted gateway; specific
#   deployments may override via env var)
# - ``mock`` → ``cn`` (test-only; inherits CN residency by default
#   so CN-region test tenants do not false-positive on egress)
# - ``local`` → ``cn`` (the bundled Ollama-style local provider
#   runs in the tenant's own region by definition; default CN for
#   parity with the product's primary market)
PROVIDER_REGIONS: dict[str, Region] = {
    "deepseek": "cn",
    "openai_compat": "us",
    "mock": "cn",
    "local": "cn",
}


def get_provider_region(provider_name: str) -> Region:
    """Resolve the data-residency region for a provider.

    Reads ``ICODER_PROVIDER_REGION_{NAME}`` env var if set (operator
    override for a deployment-specific endpoint); otherwise falls
    back to ``PROVIDER_REGIONS``. Unknown providers default to
    ``us`` (the conservative default for compliance — the operator
    must explicitly whitelist a CN provider).
    """
    env_key = f"ICODER_PROVIDER_REGION_{provider_name.upper()}"
    env_val = os.environ.get(env_key, "").strip().lower()
    if env_val in ("eu", "us", "cn"):
        return env_val  # type: ignore[return-value]
    return PROVIDER_REGIONS.get(provider_name, "us")


@dataclass
class RuntimeDataPolicy:
    """Controls data residency, external API access, and PII handling.

    Default: strictest (hospital internal deployment safe).

    Phase A1A Gate 4.5 adds ``region`` + ``egress_policy``:
      - ``region`` is the tenant's data-residency region.
      - ``egress_policy`` controls how ``can_use_provider`` reacts
        when a provider's region differs from the tenant's region.
        ``strict`` (default) denies the call; ``best_effort`` logs
        a warning and allows; ``off`` skips the check entirely
        (backwards-compat with pre-Gate-4.5 deployments).
    """

    allow_external_llm: bool = False
    allow_telemetry_upload: bool = False
    pii_redaction_required: bool = True
    marketplace_sync_mode: MarketplaceSyncMode = "offline"
    audit_log_local_only: bool = True
    persist_full_input: bool = False
    region: Region = "cn"
    egress_policy: EgressPolicy = "strict"

    @classmethod
    def from_env(cls) -> "RuntimeDataPolicy":
        return cls(
            allow_external_llm=os.environ.get("ICODER_ALLOW_EXTERNAL_LLM", "false").lower() == "true",
            allow_telemetry_upload=os.environ.get("ICODER_ALLOW_TELEMETRY_UPLOAD", "false").lower() == "true",
            pii_redaction_required=os.environ.get("ICODER_PII_REDACTION_REQUIRED", "true").lower() == "true",
            marketplace_sync_mode=_valid_sync_mode(os.environ.get("ICODER_MARKETPLACE_SYNC_MODE", "offline")),
            audit_log_local_only=os.environ.get("ICODER_AUDIT_LOG_LOCAL_ONLY", "true").lower() == "true",
            persist_full_input=os.environ.get("ICODER_PERSIST_FULL_INPUT", "false").lower() == "true",
            region=_valid_region(os.environ.get("ICODER_REGION", "cn")),
            egress_policy=_valid_egress_policy(os.environ.get("ICODER_EGRESS_POLICY", "strict")),
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
            region=_valid_region(dp.get("region", os.environ.get("ICODER_REGION", "cn"))),
            egress_policy=_valid_egress_policy(dp.get("egress_policy", "strict")),
        )

    def can_use_provider(self, provider_name: str) -> tuple[bool, str]:
        """Check if a named provider is allowed under this policy.

        Returns (allowed, reason).

        Two checks run in sequence:
          1. ``allow_external_llm`` gate (existing).
          2. **Phase A1A Gate 4.5** — regional residency check.
             The provider's region must equal the tenant's region
             when ``egress_policy="strict"``.
        """
        if provider_name in ("deepseek", "openai_compat") and not self.allow_external_llm:
            return False, f"External LLM provider '{provider_name}' blocked by data_policy (allow_external_llm=false)"

        # ── Phase A1A Gate 4.5 — regional residency ──
        provider_region = get_provider_region(provider_name)
        if self.egress_policy == "off":
            return True, ""
        if provider_region != self.region:
            msg = (
                f"Provider '{provider_name}' region={provider_region!r} does not "
                f"match tenant region={self.region!r}; egress_policy={self.egress_policy!r}"
            )
            if self.egress_policy == "strict":
                return False, msg
            # best_effort: log + allow. Reason returned to caller is empty
            # (matches pre-A1D.2 contract; the structured ``egress_decision``
            # method exposes the violation text via the warning log instead).
            logging.getLogger(__name__).warning(
                "data_policy egress %s: %s", self.egress_policy, msg,
            )
        return True, ""

    def egress_decision(self, provider_name: str) -> dict:
        """Phase A1D.2 (A1C-B-012) — produce a STRUCTURED egress decision record.

        Predecessor state: ``can_use_provider`` returned ``(allowed, reason)``
        with the decision encoded only inside the prose reason string. Phase
        A1C.9 blocker A1C-B-012 (Charter §4 PDF) asked for an EXPLICIT
        decision log so a compliance auditor can ``grep`` egress decisions
        out of the audit trail without parsing prose.

        Returns a dict with the following keys (all JSON-serializable):

        - ``tenant_region`` — this policy's region (``eu`` / ``us`` / ``cn``)
        - ``provider_name`` — the provider being checked
        - ``provider_region`` — provider's residency region
        - ``egress_policy`` — ``strict`` / ``best_effort`` / ``off``
        - ``decision`` — ``allow`` or ``deny``
        - ``reason`` — empty for plain allow; explanation otherwise
        - ``timestamp`` — ISO-8601 UTC

        Pure function — no side effect. Use ``egress_decision_log`` to also
        emit a structured log line.
        """
        allowed, reason = self.can_use_provider(provider_name)
        provider_region = get_provider_region(provider_name)
        return {
            "tenant_region": self.region,
            "provider_name": provider_name,
            "provider_region": provider_region,
            "egress_policy": self.egress_policy,
            "decision": "allow" if allowed else "deny",
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

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
            "region": self.region,
            "egress_policy": self.egress_policy,
        }


def _valid_sync_mode(val: str) -> MarketplaceSyncMode:
    if val in ("offline", "online", "mirror"):
        return val  # type: ignore[return-value]
    return "offline"


def egress_decision_log(policy: "RuntimeDataPolicy", provider_name: str) -> dict:
    """Phase A1D.2 (A1C-B-012) — emit a structured egress decision log line.

    Calls ``policy.egress_decision(provider_name)`` and emits the record to
    ``icoder_runtime.core.data_policy`` logger:
      - ``WARNING`` for deny decisions (compliance auditor grep target)
      - ``INFO`` for allow decisions

    Returns the same structured dict as ``egress_decision`` so callers can
    chain the call.
    """
    record = policy.egress_decision(provider_name)
    msg = (
        f"egress_decision tenant_region={record['tenant_region']!r} "
        f"provider={record['provider_name']!r} "
        f"provider_region={record['provider_region']!r} "
        f"policy={record['egress_policy']!r} "
        f"decision={record['decision']!r}"
    )
    if record["decision"] == "deny":
        _logger.warning("%s reason=%r", msg, record["reason"])
    else:
        _logger.info("%s", msg)
    return record


def _valid_region(val: str) -> Region:
    if val in ("eu", "us", "cn"):
        return val  # type: ignore[return-value]
    return "cn"


def _valid_egress_policy(val: str) -> EgressPolicy:
    if val in ("strict", "best_effort", "off"):
        return val  # type: ignore[return-value]
    return "strict"
