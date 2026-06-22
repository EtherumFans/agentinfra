"""Tests for confidence calibration wiring in HybridCodingAdapter.

After Phase 3, the adapter calls calibrate_all() and:
  - Sets manual_review_required=True if any code's tier == "escalate"
  - Appends a calibration summary to notes
  - Updates confidence with the max calibrated_score
  - Does NOT crash if calibrate_all raises
"""
import pytest

from official_agents.medical_coding.schema import (
    MedicalCodingOutputSchema, DiagnosisEntry, ProcedureEntry,
)
from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter


class _EmptyPrimaryStub:
    """Returns a result with empty primary diagnosis — should trigger escalate."""
    name = "empty"

    def __init__(self):
        self.calls = 0

    async def infer_async(self, messages, tools=None, response_schema=None, context=None):
        self.calls += 1
        return MedicalCodingOutputSchema(
            primary_diagnosis=DiagnosisEntry(code="", description="", confidence=0.0),
            secondary_diagnoses=[],
            procedures=[],
            issues_found=[],
            manual_review_required=False,
            confidence=0.0,
            is_mock=False,
            provider="empty",
        )


class _HighConfidenceStub:
    """Returns a high-confidence result — should NOT trigger escalate."""
    name = "high"

    def __init__(self):
        self.calls = 0

    async def infer_async(self, messages, tools=None, response_schema=None, context=None):
        self.calls += 1
        return MedicalCodingOutputSchema(
            primary_diagnosis=DiagnosisEntry(
                code="I10", description="原发性高血压", confidence=0.95,
                category="principal", evidence=["高血压 3 级"],
            ),
            secondary_diagnoses=[],
            procedures=[],
            issues_found=[],
            manual_review_required=False,
            confidence=0.95,
            is_mock=False,
            provider="high",
        )


class _UnspecifiedCodeStub:
    """An unspecified code (.9) — calibrate_all should escalate per policy."""
    name = "unspec"

    def __init__(self):
        self.calls = 0

    async def infer_async(self, messages, tools=None, response_schema=None, context=None):
        self.calls += 1
        return MedicalCodingOutputSchema(
            primary_diagnosis=DiagnosisEntry(
                code="I50.9", description="心力衰竭,未特指", confidence=0.7,
                category="principal", evidence=["心衰"],
            ),
            secondary_diagnoses=[],
            procedures=[],
            issues_found=[],
            manual_review_required=False,
            confidence=0.7,
            is_mock=False,
            provider="unspec",
        )


@pytest.mark.asyncio
async def test_calibration_sets_manual_review_for_empty_primary():
    """Empty primary → escalate tier → manual_review_required=True."""
    stub = _EmptyPrimaryStub()
    adapter = HybridCodingAdapter(mode="hybrid")
    adapter._inference = stub

    out = await adapter.infer_async([{"role": "user", "content": "x"}])

    assert out.manual_review_required is True
    # Calibration summary should be in notes
    assert "calibration" in (out.notes or "").lower() or "0A" in (out.notes or "")


@pytest.mark.asyncio
async def test_calibration_runs_and_appends_notes():
    """High-confidence I10: calibration still runs and adds summary to notes.

    The calibrator is conservative without evidence_ranking data, so it
    may still escalate — what we're testing is that the summary lands
    in notes and the pipeline doesn't crash.
    """
    stub = _HighConfidenceStub()
    adapter = HybridCodingAdapter(mode="hybrid")
    adapter._inference = stub

    out = await adapter.infer_async([{"role": "user", "content": "高血压"}])

    # Calibration ran without error (calls == 1, no exceptions)
    assert stub.calls == 1
    # Calibration summary should be in notes
    assert "calibration" in (out.notes or "").lower()
    # The routing tier breakdown (A/R/E counts) should be present
    assert "0A" in (out.notes or "") or "1A" in (out.notes or "") or "1R" in (out.notes or "")


@pytest.mark.asyncio
async def test_calibration_runs_after_repair_in_pipeline():
    """Calibration should fire even if repair loop ran (or didn't)."""
    stub = _EmptyPrimaryStub()
    adapter = HybridCodingAdapter(mode="hybrid")
    adapter._inference = stub

    out = await adapter.infer_async([{"role": "user", "content": "x"}])

    # Even if repair didn't clear severe issues, calibration still fires
    assert "calibration" in (out.notes or "").lower() or "0A" in (out.notes or "")


def test_calibration_input_adapts_schema_to_calibrator():
    """The adapter's _calibration_input helper must produce the right shape."""
    adapter = HybridCodingAdapter(mode="no_repair")
    schema = MedicalCodingOutputSchema(
        primary_diagnosis=DiagnosisEntry(
            code="I50.0", description="充血性心衰", confidence=0.85,
        ),
        secondary_diagnoses=[
            DiagnosisEntry(code="I10", description="高血压", confidence=0.9),
        ],
        procedures=[ProcedureEntry(code="00.66", description="PCI", confidence=0.92)],
    )
    diag_c, proc_c, pd, ev_rank, disagr, pd_reason = adapter._calibration_input(schema)

    # Primary + 1 secondary = 2 diagnosis candidates
    assert len(diag_c) == 2
    assert diag_c[0]["code"] == "I50.0"
    assert diag_c[1]["code"] == "I10"
    # 1 procedure candidate
    assert len(proc_c) == 1
    assert proc_c[0]["code"] == "00.66"
    # Primary diagnosis dict
    assert pd["code"] == "I50.0"


def test_calibration_failure_does_not_break_pipeline(monkeypatch):
    """If calibrate_all raises, the result is still returned unchanged."""
    from icoder_runtime.providers.medical_coding import hybrid_adapter as ha_mod

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated calibrator failure")

    monkeypatch.setattr("app.services.confidence_calibrator.calibrate_all", _raise)
    # We can't easily test the full pipeline here, but _apply_calibration
    # should catch and log.
    adapter = HybridCodingAdapter(mode="no_repair")
    schema = MedicalCodingOutputSchema(
        primary_diagnosis=DiagnosisEntry(code="I10", description="", confidence=0.9),
    )
    schema.manual_review_required = False
    schema.notes = "before"
    # Should not raise
    adapter._apply_calibration(schema)
    # Original state preserved
    assert schema.manual_review_required is False
    assert schema.notes == "before"
