"""Phase A1A Gate 4.5 — Provider egress + regional residency policy.

Closes T-CC-5 from the Gate 4.1 threat model: a CN tenant's PHI
could egress to a US-region LLM provider because the policy had
no region field and the provider registry had no per-provider
region metadata.

Coverage:
  - ``RuntimeDataPolicy.region`` + ``egress_policy`` fields.
  - ``PROVIDER_REGIONS`` per-provider metadata.
  - ``can_use_provider`` enforces residency in ``strict`` mode.
  - ``best_effort`` mode logs and allows.
  - ``off`` mode skips the check entirely.
  - Operator override via ``ICODER_PROVIDER_REGION_{NAME}`` env var.
"""
from __future__ import annotations

import os

import pytest


# ─────────────────────────────────────────────────────────────────────
# §1 Provider region registry
# ─────────────────────────────────────────────────────────────────────


def test_known_provider_regions() -> None:
    """Each known provider has a documented default region."""
    from icoder_runtime.core.data_policy import PROVIDER_REGIONS, get_provider_region
    assert PROVIDER_REGIONS["deepseek"] == "cn"
    assert PROVIDER_REGIONS["openai_compat"] == "us"
    assert PROVIDER_REGIONS["mock"] == "cn"
    assert PROVIDER_REGIONS["local"] == "cn"
    assert get_provider_region("deepseek") == "cn"


def test_unknown_provider_defaults_us() -> None:
    """Unknown providers default to ``us`` (conservative for compliance)."""
    from icoder_runtime.core.data_policy import get_provider_region
    assert get_provider_region("totally_unknown_provider") == "us"


def test_operator_env_override(monkeypatch) -> None:
    """Operator can override a provider's region via env var.

    Useful when a deployment-specific endpoint (e.g. self-hosted
    OpenAI-compatible gateway) keeps data in a different region
    than the public provider.
    """
    monkeypatch.setenv("ICODER_PROVIDER_REGION_OPENAI_COMPAT", "cn")
    from icoder_runtime.core import data_policy
    # get_provider_region reads the deployment override on every call. Reloading
    # this module changes the RuntimeDataPolicy class identity held by already
    # imported API modules and contaminates later full-suite isinstance checks.
    assert data_policy.get_provider_region("openai_compat") == "cn"


# ─────────────────────────────────────────────────────────────────────
# §2 Strict egress — deny cross-region
# ─────────────────────────────────────────────────────────────────────


def test_strict_egress_denies_cross_region_cn_to_us() -> None:
    """CN tenant + US provider + strict policy → deny."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="strict",
    )
    allowed, reason = policy.can_use_provider("openai_compat")
    assert not allowed
    assert "openai_compat" in reason
    assert "us" in reason
    assert "cn" in reason


def test_strict_egress_allows_same_region_cn_to_cn() -> None:
    """CN tenant + CN provider + strict policy → allow."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="strict",
    )
    allowed, reason = policy.can_use_provider("deepseek")
    assert allowed
    assert reason == ""


def test_strict_egress_allows_same_region_us_to_us() -> None:
    """US tenant + US provider + strict policy → allow."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="us",
        egress_policy="strict",
    )
    allowed, _ = policy.can_use_provider("openai_compat")
    assert allowed


def test_external_llm_gate_runs_before_region_check() -> None:
    """If allow_external_llm=False, the deny reason names the
    external-LLM gate, not the region mismatch."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy(
        allow_external_llm=False,
        region="cn",
        egress_policy="strict",
    )
    allowed, reason = policy.can_use_provider("openai_compat")
    assert not allowed
    assert "allow_external_llm=false" in reason


# ─────────────────────────────────────────────────────────────────────
# §3 Best-effort egress — log and allow
# ─────────────────────────────────────────────────────────────────────


def test_best_effort_egress_allows_cross_region(caplog) -> None:
    """best_effort mode logs a warning and allows the call.

    Operators use this during a migration window when a CN tenant
    needs temporary access to a US provider before a CN-region
    alternative is provisioned.
    """
    import logging
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="best_effort",
    )
    with caplog.at_level(logging.WARNING, logger="icoder_runtime.core.data_policy"):
        allowed, reason = policy.can_use_provider("openai_compat")
    assert allowed
    assert reason == ""  # no surface reason; logged only
    assert any(
        "egress" in rec.getMessage() and "openai_compat" in rec.getMessage()
        for rec in caplog.records
    )


# ─────────────────────────────────────────────────────────────────────
# §4 Off mode — skip check entirely (backwards-compat)
# ─────────────────────────────────────────────────────────────────────


def test_off_egress_skips_region_check() -> None:
    """off mode preserves pre-Gate-4.5 behaviour for deployments
    that have not yet pinned a region."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="off",
    )
    allowed, _ = policy.can_use_provider("openai_compat")
    assert allowed


# ─────────────────────────────────────────────────────────────────────
# §5 from_env wiring
# ─────────────────────────────────────────────────────────────────────


def test_from_env_reads_region_and_egress_policy(monkeypatch) -> None:
    """``ICODER_REGION`` + ``ICODER_EGRESS_POLICY`` populate the
    policy from env. This is the canonical wiring for cloud mode
    where the deployment region is fixed at provisioning time."""
    monkeypatch.setenv("ICODER_REGION", "eu")
    monkeypatch.setenv("ICODER_EGRESS_POLICY", "best_effort")
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "true")
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy.from_env()
    assert policy.region == "eu"
    assert policy.egress_policy == "best_effort"
    assert policy.allow_external_llm is True


def test_invalid_region_falls_back_to_cn(monkeypatch) -> None:
    """Invalid region env value falls back to ``cn`` (the product's
    primary market) rather than raising — a typo should not brick
    the deployment."""
    monkeypatch.setenv("ICODER_REGION", "tokyo")
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy.from_env()
    assert policy.region == "cn"


def test_invalid_egress_policy_falls_back_to_strict(monkeypatch) -> None:
    """Invalid egress env value falls back to ``strict`` — fail
    closed when the operator's intent is ambiguous."""
    monkeypatch.setenv("ICODER_EGRESS_POLICY", "permissive")
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    policy = RuntimeDataPolicy.from_env()
    assert policy.egress_policy == "strict"


# ─────────────────────────────────────────────────────────────────────
# §6 to_dict serialisation
# ─────────────────────────────────────────────────────────────────────


def test_to_dict_includes_new_fields() -> None:
    """``to_dict`` exposes the new fields for the diagnostic UI
    and for the agent_run response's data_policy snapshot."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy
    d = RuntimeDataPolicy().to_dict()
    assert "region" in d
    assert "egress_policy" in d
    assert d["region"] == "cn"
    assert d["egress_policy"] == "strict"
