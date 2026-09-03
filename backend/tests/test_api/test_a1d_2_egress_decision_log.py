"""A1D.2 — A1C-B-012 egress decision EXPLICIT log.

Predecessor state (Phase A1A Gate 4.5): ``RuntimeDataPolicy.can_use_provider``
returns ``(allowed, reason)`` and the *reason* string implicitly encodes the
egress decision. Phase A1C.9 blocker A1C-B-012 (Charter §4 PDF) asks for an
EXPLICIT decision log: a structured record of tenant_region / provider_region /
egress_policy / decision / reason emitted for every egress check, so a
compliance auditor can ``grep`` the egress decisions out of the audit trail
without parsing prose reason strings.

This module covers the new ``egress_decision()`` pure function and the
``egress_decision_log()`` side-effecting helper.
"""
from __future__ import annotations

import logging

import pytest


# ─────────────────────────────────────────────────────────────────────
# §1 egress_decision() — pure structured record
# ─────────────────────────────────────────────────────────────────────


def test_egress_decision_returns_structured_record_for_deny() -> None:
    """CN tenant + US provider + strict → record has all required keys + decision='deny'."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy

    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="strict",
    )
    record = policy.egress_decision("openai_compat")
    assert record["tenant_region"] == "cn"
    assert record["provider_name"] == "openai_compat"
    assert record["provider_region"] == "us"
    assert record["egress_policy"] == "strict"
    assert record["decision"] == "deny"
    assert "openai_compat" in record["reason"]
    assert record["timestamp"]  # ISO-8601


def test_egress_decision_returns_structured_record_for_allow() -> None:
    """CN tenant + CN provider + strict → decision='allow' with empty reason."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy

    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="strict",
    )
    record = policy.egress_decision("deepseek")
    assert record["tenant_region"] == "cn"
    assert record["provider_name"] == "deepseek"
    assert record["provider_region"] == "cn"
    assert record["egress_policy"] == "strict"
    assert record["decision"] == "allow"
    assert record["reason"] == ""


def test_egress_decision_best_effort_cross_region_returns_allow_with_warning_reason(
    caplog,
) -> None:
    """best_effort mode allows cross-region; egress_decision logs the violation.

    Predecessor contract: ``can_use_provider`` returns ``(True, "")`` for
    best_effort cross-region — the violation is logged at WARNING but the
    reason string is empty (``test_best_effort_egress_allows_cross_region``
    asserts this). ``egress_decision`` honors the same contract for its
    ``reason`` field, but the structured record's ``decision='allow'`` plus
    a captured WARNING log makes the egress decision grep-able for auditors.
    """
    import logging as _logging

    from icoder_runtime.core.data_policy import RuntimeDataPolicy

    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="best_effort",
    )
    with caplog.at_level(_logging.WARNING, logger="icoder_runtime.core.data_policy"):
        record = policy.egress_decision("openai_compat")
    assert record["decision"] == "allow"
    assert record["egress_policy"] == "best_effort"
    # The WARNING log carries the violation explanation even though reason=""
    assert any(
        "openai_compat" in r.message and "does not match" in r.message
        for r in caplog.records
    )


def test_egress_decision_off_policy_skips_region_check() -> None:
    """egress_policy='off' skips region check; decision='allow', reason empty."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy

    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="off",
    )
    record = policy.egress_decision("openai_compat")
    assert record["decision"] == "allow"
    assert record["reason"] == ""


def test_egress_decision_blocked_by_allow_external_llm_flag() -> None:
    """allow_external_llm=False → decision='deny' for deepseek/openai_compat."""
    from icoder_runtime.core.data_policy import RuntimeDataPolicy

    policy = RuntimeDataPolicy(
        allow_external_llm=False,
        region="cn",
        egress_policy="strict",
    )
    record = policy.egress_decision("deepseek")
    assert record["decision"] == "deny"
    assert "allow_external_llm" in record["reason"]


# ─────────────────────────────────────────────────────────────────────
# §2 egress_decision_log() — emits structured log line
# ─────────────────────────────────────────────────────────────────────


def test_egress_decision_log_emits_warning_on_deny(caplog) -> None:
    """Deny decisions are surfaced at WARNING level (compliance auditor grep target)."""
    from icoder_runtime.core.data_policy import (
        RuntimeDataPolicy,
        egress_decision_log,
    )

    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="strict",
    )
    with caplog.at_level(logging.WARNING, logger="icoder_runtime.core.data_policy"):
        record = egress_decision_log(policy, "openai_compat")
    assert record["decision"] == "deny"
    deny_logs = [r for r in caplog.records if "deny" in r.message.lower()]
    assert deny_logs, "expected a WARNING log mentioning deny"


def test_egress_decision_log_emits_info_on_allow(caplog) -> None:
    """Allow decisions are surfaced at INFO level."""
    from icoder_runtime.core.data_policy import (
        RuntimeDataPolicy,
        egress_decision_log,
    )

    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="strict",
    )
    with caplog.at_level(logging.INFO, logger="icoder_runtime.core.data_policy"):
        record = egress_decision_log(policy, "deepseek")
    assert record["decision"] == "allow"
    allow_logs = [r for r in caplog.records if "allow" in r.message.lower()]
    assert allow_logs, "expected an INFO log mentioning allow"


def test_egress_decision_log_returns_same_record_as_egress_decision() -> None:
    """The log helper returns the same structured record as the pure method."""
    from icoder_runtime.core.data_policy import (
        RuntimeDataPolicy,
        egress_decision_log,
    )

    policy = RuntimeDataPolicy(
        allow_external_llm=True,
        region="cn",
        egress_policy="best_effort",
    )
    pure = policy.egress_decision("openai_compat")
    logged = egress_decision_log(policy, "openai_compat")
    # Compare ignoring timestamp (ISO string may differ by microseconds)
    pure.pop("timestamp")
    logged.pop("timestamp")
    assert pure == logged
