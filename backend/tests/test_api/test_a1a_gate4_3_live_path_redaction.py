"""Phase A1A Gate 4.3 — Live-path redaction + minimum necessary data.

Closes four threat-model rows from the Gate 4.1 inventory:

- **T-CC-1** ``safe_metadata`` used a blacklist with value-shape
  heuristics; a new emit-site key carrying PHI (e.g.
  ``{"patient_name": "张三"}``) passed through unchallenged.
  Fix: convert to a strict allowlist.
- **T-CC-2** ``audit_log.details`` accepted any JSON from the
  caller; an emit-site ``details={"patient_name": "..."}`` would
  persist PHI to the audit table.
  Fix: top-level allowlist via ``redact_audit_details``.
- **T-CC-3** ``model_input_summary`` / ``model_output_summary``
  accepted arbitrary text; an emit-site passing the full LLM
  transcript would land the whole prompt in the audit row.
  Fix: truncate to 200 chars + pass through fail-closed
  ``redact_for_export``.
- **T-CC-4** ``phi_redactor.redact_for_export`` returned the
  ORIGINAL text on any failure path (disabled / unavailable /
  exception). A single unhandled edge-case would silently leak
  PHI to the export pipeline.
  Fix: fail-closed contract — return ``[REDACTION_FAILED]``
  placeholder on any failure path.
"""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")


# ─────────────────────────────────────────────────────────────────────
# §1 safe_metadata — strict allowlist
# ─────────────────────────────────────────────────────────────────────


def test_safe_metadata_allows_known_key() -> None:
    """Keys in ``_SAFE_KEYS`` pass through unchanged."""
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _redact_safe_metadata,
    )
    src = {
        "agent_id": "medical-coding-agent",
        "stage": "TOOLS_CALL",
        "backend_provider": "deepseek",
        "tool_rounds": 3,
    }
    scrubbed = _redact_safe_metadata(src)
    assert scrubbed == src


def test_safe_metadata_allows_bounded_clinical_catalog_provenance() -> None:
    """Catalog IDs/versions/statuses are fixed identifiers, never patient data."""
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _redact_safe_metadata,
    )

    src = {
        "clinical_asset_ids": "cn.icd10cn.catalog+cn.icd9cm3.catalog",
        "clinical_asset_versions": "observed-local-2026-05-19",
        "clinical_asset_authority_statuses": "source_unverified",
        "clinical_asset_license_statuses": "external_review_required",
        "clinical_asset_integrity_verified": True,
        "semantic_enhancement_used": False,
    }
    assert _redact_safe_metadata(src) == src


def test_safe_metadata_allows_content_free_non_authoritative_cost_attribution() -> None:
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _redact_safe_metadata,
    )

    src = {
        "cost_amount": 0.00066472,
        "cost_currency": "CNY",
        "cost_source": "configured_usage_pricing_estimate",
        "billing_authoritative": False,
    }
    assert _redact_safe_metadata(src) == src


def test_safe_metadata_allows_content_free_provider_failure_diagnostics() -> None:
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _redact_safe_metadata,
    )

    src = {
        "provider_error_category": "rate_limit",
        "provider_http_status": 429,
        "provider_attempt_count": 3,
        "provider_retryable": True,
    }
    assert _redact_safe_metadata(src) == src


def test_safe_metadata_redacts_unknown_key() -> None:
    """Any key not in ``_SAFE_KEYS`` is replaced with ``[REDACTED]``.

    This is the core Gate 4.3 fix: an emit site that accidentally
    writes ``{"patient_name": "张三"}`` no longer leaks the value
    to the audit / trace store.
    """
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _redact_safe_metadata,
    )
    src = {
        "agent_id": "ok",
        "patient_name": "张三",  # not in _SAFE_KEYS
        "input_text": "长文本",  # not in _SAFE_KEYS
    }
    scrubbed = _redact_safe_metadata(src)
    assert scrubbed["agent_id"] == "ok"
    assert scrubbed["patient_name"] == "[REDACTED]"
    assert scrubbed["input_text"] == "[REDACTED]"


def test_safe_metadata_redacts_token_blobs_in_unknown_keys() -> None:
    """Even if a value looks like a JWT, the redaction uses the
    same placeholder — the value never survives to the DB row."""
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _redact_safe_metadata,
    )
    src = {
        "my_custom_secret": "Bearer eyJhbGc.foo.bar",  # not in _SAFE_KEYS
    }
    scrubbed = _redact_safe_metadata(src)
    assert scrubbed["my_custom_secret"] == "[REDACTED]"


def test_safe_metadata_handles_empty() -> None:
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _redact_safe_metadata,
    )
    assert _redact_safe_metadata(None) == {}
    assert _redact_safe_metadata({}) == {}


def test_safe_metadata_does_not_mutate_input() -> None:
    """The redactor returns a new dict; the caller's dict is unchanged."""
    from app.icoder.agent_runtime.orchestrator.run_trace import (
        _redact_safe_metadata,
    )
    src = {"patient_name": "张三", "agent_id": "ok"}
    _redact_safe_metadata(src)
    assert src == {"patient_name": "张三", "agent_id": "ok"}, (
        "input dict must not be mutated"
    )


# ─────────────────────────────────────────────────────────────────────
# §2 audit_log details — top-level allowlist
# ─────────────────────────────────────────────────────────────────────


def test_audit_details_allows_operational_keys() -> None:
    """Operational metadata (run_id, agent_id, status, ...) survives."""
    from app.services.audit_detail_redactor import redact_audit_details
    src = {
        "run_id": "r-1",
        "agent_id": "medical-coding-agent",
        "action": "review.generate",
        "status": "success",
        "tokens_used": 1234,
        "encounter_id": "enc-1",
        "runtime_mode": "a2a_pure_llm",
    }
    assert redact_audit_details(src) == src


def test_audit_details_redacts_known_phi_keys() -> None:
    """PHI-carrying keys are always redacted."""
    from app.services.audit_detail_redactor import redact_audit_details
    src = {
        "run_id": "r-1",
        "patient_name": "张三",
        "mrn": "MRN-12345",
        "input_text": "free-form transcript",
        "model_input": "free-form prompt",
    }
    out = redact_audit_details(src)
    assert out["run_id"] == "r-1"
    assert out["patient_name"] == "[REDACTED]"
    assert out["mrn"] == "[REDACTED]"
    assert out["input_text"] == "[REDACTED]"
    assert out["model_input"] == "[REDACTED]"


def test_audit_details_redacts_unknown_keys_defensively() -> None:
    """Any key not on either allowlist is treated as PHI by default."""
    from app.services.audit_detail_redactor import redact_audit_details
    src = {
        "some_new_field": "value",
        "another_unknown": 42,
    }
    out = redact_audit_details(src)
    assert out["some_new_field"] == "[REDACTED]"
    assert out["another_unknown"] == "[REDACTED]"


def test_audit_details_preserves_none() -> None:
    """None input returns None so the nullable column stays NULL."""
    from app.services.audit_detail_redactor import redact_audit_details
    assert redact_audit_details(None) is None


def test_shadow_job_audit_keeps_safe_metadata_and_redacts_fence_secrets() -> None:
    from app.services.audit_detail_redactor import redact_audit_details

    out = redact_audit_details({
        "job_id": "job-1",
        "binding_id": "binding-1",
        "attempt_count": 2,
        "recovered_after_expiry": True,
        "aggregate_only": True,
        "patient_data_used": False,
        "cancellation_reason": "safety_stop",
        "cancelled_by_user_id": "user-1",
        "lease_token": "must-never-be-retained",
        "idempotency_key": "must-never-be-retained",
        "input_text": "patient content",
    })

    assert out == {
        "job_id": "job-1",
        "binding_id": "binding-1",
        "attempt_count": 2,
        "recovered_after_expiry": True,
        "aggregate_only": True,
        "patient_data_used": False,
        "cancellation_reason": "safety_stop",
        "cancelled_by_user_id": "user-1",
        "lease_token": "[REDACTED]",
        "idempotency_key": "[REDACTED]",
        "input_text": "[REDACTED]",
    }


def test_agent_run_audit_reason_code_drops_free_form_suffix() -> None:
    from app.api.agent_run import _audit_reason_code

    assert _audit_reason_code("connector_graph_failed") == "connector_graph_failed"
    assert _audit_reason_code("ValueError: 张三 13800138000") == "valueerror"
    assert _audit_reason_code("input_safety_blocked:PI-003,PI-001") == (
        "input_safety_blocked"
    )
    assert _audit_reason_code("张三") == "unclassified_error"
    assert _audit_reason_code("") is None


def test_audit_summary_truncates_to_max_len() -> None:
    """Long transcripts are truncated to MAX_SUMMARY_LEN chars
    before redaction, so the audit row stays a preview not a transcript."""
    from app.services.audit_detail_redactor import (
        redact_audit_summary, MAX_SUMMARY_LEN,
    )
    long_text = "x" * (MAX_SUMMARY_LEN * 10)
    out = redact_audit_summary(long_text)
    # The redactor may shorten further; the assertion is that the
    # output is bounded by MAX_SUMMARY_LEN (plus any redaction wrapper).
    assert out is not None
    assert len(out) <= MAX_SUMMARY_LEN + 50  # redaction wrapper allowance


def test_audit_summary_preserves_none() -> None:
    from app.services.audit_detail_redactor import redact_audit_summary
    assert redact_audit_summary(None) is None


# ─────────────────────────────────────────────────────────────────────
# §3 phi_redactor — fail-closed contract
# ─────────────────────────────────────────────────────────────────────


def test_phi_redactor_fail_closed_on_disabled(monkeypatch) -> None:
    """When redaction is disabled WITHOUT bypass, returns placeholder."""
    monkeypatch.setenv("ICODER_PII_REDACTION_REQUIRED", "0")
    monkeypatch.delenv("ICODER_PHI_REDACTION_BYPASS", raising=False)
    # Re-import to pick up env var
    import importlib
    from app.services import phi_redactor
    importlib.reload(phi_redactor)
    out = phi_redactor.redact_for_export("raw PHI text 张三")
    assert out == "[REDACTION_FAILED]"


def test_phi_redactor_bypass_returns_original(monkeypatch) -> None:
    """Local-dev escape hatch: bypass=1 returns original text."""
    monkeypatch.setenv("ICODER_PII_REDACTION_REQUIRED", "0")
    monkeypatch.setenv("ICODER_PHI_REDACTION_BYPASS", "1")
    import importlib
    from app.services import phi_redactor
    importlib.reload(phi_redactor)
    out = phi_redactor.redact_for_export("raw text")
    assert out == "raw text"


def test_phi_redactor_fail_closed_on_exception(monkeypatch) -> None:
    """When the underlying redactor raises, returns placeholder."""
    monkeypatch.setenv("ICODER_PII_REDACTION_REQUIRED", "1")
    monkeypatch.delenv("ICODER_PHI_REDACTION_BYPASS", raising=False)
    import importlib
    from app.services import phi_redactor
    importlib.reload(phi_redactor)

    # Patch _get_redactor to return a broken redactor
    class _Broken:
        def redact(self, _text):
            raise RuntimeError("simulated redactor crash")
    monkeypatch.setattr(phi_redactor, "_get_redactor", lambda: _Broken())
    out = phi_redactor.redact_for_export("raw PHI text")
    assert out == "[REDACTION_FAILED]"


def test_phi_redactor_fail_closed_on_unavailable(monkeypatch) -> None:
    """When the underlying redactor is unavailable, returns placeholder."""
    monkeypatch.setenv("ICODER_PII_REDACTION_REQUIRED", "1")
    monkeypatch.delenv("ICODER_PHI_REDACTION_BYPASS", raising=False)
    import importlib
    from app.services import phi_redactor
    importlib.reload(phi_redactor)
    monkeypatch.setattr(phi_redactor, "_get_redactor", lambda: None)
    out = phi_redactor.redact_for_export("raw PHI text")
    assert out == "[REDACTION_FAILED]"


def test_phi_redactor_empty_input_returns_empty(monkeypatch) -> None:
    """Empty input short-circuits — no placeholder."""
    monkeypatch.setenv("ICODER_PII_REDACTION_REQUIRED", "1")
    import importlib
    from app.services import phi_redactor
    importlib.reload(phi_redactor)
    assert phi_redactor.redact_for_export("") == ""
    assert phi_redactor.redact_for_export(None) == ""


# ─────────────────────────────────────────────────────────────────────
# §4 log_action wiring — details + summary scrubbed at chokepoint
# ─────────────────────────────────────────────────────────────────────


def test_log_action_scrubs_details_phi(client: TestClient) -> None:
    """An emit site that writes PHI to ``details`` must not leak it
    to the audit_log row. The redaction happens in log_action
    before the row is added to the session."""
    import asyncio
    from app.database import AsyncSessionLocal
    from app.middleware.audit import log_action
    from sqlalchemy import select
    from app.models.audit_log import AuditLog as AuditLogModel
    import secrets

    token = secrets.token_hex(4)
    async def _go():
        async with AsyncSessionLocal() as db:
            await log_action(
                db=db,
                user_id="u-test-bypass",
                username="testuser",
                action=f"audit-g43-test-{token}",
                resource_type="test",
                resource_id=None,
                details={
                    "run_id": "r-1",
                    "patient_name": "张三",  # PHI must be redacted
                    "input_text": "free-form",  # PHI must be redacted
                },
                model_input_summary="x" * 500,  # should be truncated
                organization_id="org_default1",
            )
            await db.commit()
            row = (await db.execute(
                select(AuditLogModel).where(
                    AuditLogModel.action == f"audit-g43-test-{token}"
                )
            )).scalar_one_or_none()
            return row
    row = asyncio.run(_go())
    assert row is not None, "audit row was not written"
    assert row.details["run_id"] == "r-1"
    assert row.details["patient_name"] == "[REDACTED]"
    assert row.details["input_text"] == "[REDACTED]"
    # Truncation: the stored value must be well under 500 chars
    assert row.model_input_summary is not None
    assert len(row.model_input_summary) <= 250  # truncate + redaction wrapper

    # Cleanup
    async def _cleanup():
        async with AsyncSessionLocal() as db:
            await db.execute(
                AuditLogModel.__table__.delete().where(
                    AuditLogModel.action == f"audit-g43-test-{token}"
                )
            )
            await db.commit()
    asyncio.run(_cleanup())
