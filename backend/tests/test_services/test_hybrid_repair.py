"""Tests for the in-process repair loop in HybridCodingAdapter.

Repair loop semantics:
  - Triggered when any rule issue has severity in (critical, high)
  - Bounded at 1 retry (no infinite loop)
  - Skipped for is_mock=True outputs (mock returns already-pass cases)
  - Skipped when mode="no_repair"
  - repair_success=True iff the retry clears all severe issues
"""
import pytest

from icoder_runtime.core.coding_schema import (
    MedicalCodingOutputSchema, DiagnosisEntry, CodingIssue,
)
from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter
from icoder_runtime.providers.medical_coding.rule_engine_adapter import RuleEngineAdapter


class _StubInference:
    """Stub that returns different outputs on successive calls.

    call 1: bad result (R002 invalid format, R007 low confidence) → severe
    call 2: good result (passes rules) → no severe
    """
    name = "stub_inference"

    def __init__(self):
        self.calls = 0
        self.last_messages = None
        # Bad first call: short code + no evidence
        self.bad = MedicalCodingOutputSchema(
            review_conclusion="WARNING",
            primary_diagnosis=DiagnosisEntry(
                code="I21",  # too short → R002 invalid format (critical)
                description="AMI",
                confidence=0.4,  # → R007 low confidence (high)
                category="principal",
                evidence=[],
            ),
            secondary_diagnoses=[],
            procedures=[],
            issues_found=[],
            manual_review_required=False,
            confidence=0.4,
            is_mock=False,
            provider="stub",
        )
        # Good second call: complete, correct
        self.good = MedicalCodingOutputSchema(
            review_conclusion="PASS",
            primary_diagnosis=DiagnosisEntry(
                code="I21.0",
                description="急性ST段抬高型心肌梗死",
                confidence=0.95,
                category="principal",
                evidence=["前壁心肌梗死"],
            ),
            secondary_diagnoses=[],
            procedures=[],
            issues_found=[],
            manual_review_required=False,
            confidence=0.95,
            is_mock=False,
            provider="stub",
        )

    async def infer_async(self, messages, tools=None, response_schema=None, context=None):
        self.calls += 1
        self.last_messages = list(messages)
        return self.bad if self.calls == 1 else self.good


class _AlwaysBadInference:
    """Stub that always returns severe issues — repair must fail gracefully."""
    name = "always_bad"

    def __init__(self):
        self.calls = 0

    async def infer_async(self, messages, tools=None, response_schema=None, context=None):
        self.calls += 1
        return MedicalCodingOutputSchema(
            review_conclusion="WARNING",
            primary_diagnosis=DiagnosisEntry(
                code="I21",  # still bad
                description="AMI",
                confidence=0.4,
                category="principal",
                evidence=[],
            ),
            secondary_diagnoses=[],
            procedures=[],
            issues_found=[],
            manual_review_required=False,
            confidence=0.4,
            is_mock=False,
            provider="always_bad",
        )


@pytest.mark.asyncio
async def test_repair_fires_and_succeeds_when_severe_issues_cleared():
    """First call has severe issues, second call clears them → repair_success=True."""
    stub = _StubInference()
    # mode="hybrid" enables repair; we'll inject the stub
    adapter = HybridCodingAdapter(mode="hybrid")
    adapter._inference = stub

    out = await adapter.infer_async([{"role": "user", "content": "急性前壁心梗"}])

    # Repair must have fired exactly once (cap = 1)
    assert stub.calls == 2
    assert out.repair_attempted is True
    assert out.repair_success is True
    assert out.repair_rounds == 1
    # The repaired output's primary code is the good one
    assert out.primary_diagnosis.code == "I21.0"
    assert out.review_conclusion in ("PASS", "WARNING")


@pytest.mark.asyncio
async def test_repair_disabled_in_no_repair_mode():
    """When mode='no_repair', even severe issues don't trigger a second call."""
    stub = _StubInference()
    adapter = HybridCodingAdapter(mode="no_repair")
    adapter._inference = stub

    out = await adapter.infer_async([{"role": "user", "content": "x"}])

    assert stub.calls == 1
    assert out.repair_attempted is False
    assert out.repair_success is False


@pytest.mark.asyncio
async def test_repair_does_not_double_call_when_no_severe_issues():
    """If the first call already passes rules (no severe), no repair runs."""
    class _AlreadyGoodStub:
        name = "good"
        def __init__(self):
            self.calls = 0
        async def infer_async(self, messages, tools=None, response_schema=None, context=None):
            self.calls += 1
            return MedicalCodingOutputSchema(
                primary_diagnosis=DiagnosisEntry(
                    code="I10", description="高血压", confidence=0.95,
                    category="principal", evidence=["高血压 3 级"],
                ),
                confidence=0.95,
                is_mock=False,
                provider="good",
            )

    stub = _AlreadyGoodStub()
    adapter = HybridCodingAdapter(mode="no_repair")
    adapter._inference = stub

    out = await adapter.infer_async([{"role": "user", "content": "高血压"}])
    assert stub.calls == 1
    assert out.repair_attempted is False


@pytest.mark.asyncio
async def test_repair_failure_keeps_original_result():
    """When the retry still has severe issues, the original is kept and
    repair_success is False."""
    stub = _AlwaysBadInference()
    adapter = HybridCodingAdapter(mode="hybrid")
    adapter._inference = stub

    out = await adapter.infer_async([{"role": "user", "content": "x"}])

    # Two calls: original + 1 repair retry
    assert stub.calls == 2
    assert out.repair_attempted is True
    assert out.repair_success is False


@pytest.mark.asyncio
async def test_repair_skipped_for_mock_output():
    """is_mock=True outputs skip the repair loop (mock is already the fallback)."""
    class _MockStub:
        name = "mock"
        def __init__(self):
            self.calls = 0
        async def infer_async(self, messages, tools=None, response_schema=None, context=None):
            self.calls += 1
            r = MedicalCodingOutputSchema.mock_result()
            # Inject severe issues to make sure repair WOULD fire if not skipped
            r.is_mock = True
            r.issues_found = [
                CodingIssue(severity="critical", code="R002",
                            message="forced", suggestion="x")
            ]
            return r

    stub = _MockStub()
    adapter = HybridCodingAdapter(mode="hybrid")
    adapter._inference = stub

    out = await adapter.infer_async([{"role": "user", "content": "x"}])
    assert stub.calls == 1  # No repair
    assert out.repair_attempted is False


@pytest.mark.asyncio
async def test_repair_messages_contain_violation_text():
    """The follow-up message must include the rule violation text."""
    stub = _StubInference()
    adapter = HybridCodingAdapter(mode="hybrid")
    adapter._inference = stub

    await adapter.infer_async([{"role": "user", "content": "急性前壁心梗"}])

    # The second call's messages should include the repair user message
    assert stub.calls == 2
    last_call_msgs = stub.last_messages
    # Find the repair user message (last one, with the violation text)
    last_msg = last_call_msgs[-1]
    assert last_msg["role"] == "user"
    assert "规则违规" in last_msg["content"] or "违规" in last_msg["content"]


def test_repair_field_roundtrip_in_to_from_dict():
    """Schema fields must serialize/deserialize cleanly for the e2e script."""
    out = MedicalCodingOutputSchema(
        primary_diagnosis=DiagnosisEntry(code="I21.0", confidence=0.9),
        repair_attempted=True,
        repair_success=True,
        repair_rounds=1,
    )
    d = out.to_dict()
    assert d["repair_attempted"] is True
    assert d["repair_success"] is True
    assert d["repair_rounds"] == 1

    rebuilt = MedicalCodingOutputSchema.from_dict(d, provider="t", is_mock=False)
    assert rebuilt.repair_attempted is True
    assert rebuilt.repair_success is True
    assert rebuilt.repair_rounds == 1

    # Default values when not provided
    bare = MedicalCodingOutputSchema.from_dict({}, provider="t")
    assert bare.repair_attempted is False
    assert bare.repair_success is False
    assert bare.repair_rounds == 0
