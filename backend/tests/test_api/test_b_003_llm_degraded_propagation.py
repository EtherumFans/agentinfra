"""B-003 — LLM degraded false-success cascade (6-layer propagation).

Pre-B-003: when DeepSeek API key was missing or HTTP 4xx/5xx happened,
LLMGateway._mock_fallback_response returned a degraded envelope tagged
``degraded=True, is_mock=True, degraded_reason=<why>`` — but the downstream
parse/render chain ignored these flags, so empty ICD-10 codes were surfaced
to the user as a green "通过" badge. Medically dangerous on a compliance
product.

B-003 fix (6 layers):
  Layer 1: LLMGateway._mock_fallback_response (NO change — already correct)
  Layer 2: DeepSeekCodingAdapter._parse_response propagates gateway_mock
  Layer 2b: _error_schema accepts is_mock / degraded_reason kwargs
  Layer 3: CodingResult adds degraded + degraded_reason fields
  Layer 4: FastCodingRuntime.predict short-circuits on schema.is_mock
  Layer 4b: MedCoderRuntime.predict same short-circuit
  Layer 5: _map_coding_result forces AgentRunResponse(error=True) on degraded
  Layer 6: Frontend (NO change — existing red-banner path)

Tests (7):
  §1 LLMGateway mock envelope markers
  §2 DeepSeekCodingAdapter._parse_response propagates is_mock
  §2b _error_schema accepts is_mock / degraded_reason kwargs
  §3 CodingResult accepts degraded=True
  §4 FastCodingRuntime.predict short-circuits on schema.is_mock
  §4b MedCoderRuntime.predict short-circuits on schema.is_mock
  §5 _map_coding_result forces error=True on result.degraded=True
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ─────────────────────────────────────────────────────────────────────
# §1 LLMGateway mock envelope markers
# ─────────────────────────────────────────────────────────────────────


def test_llm_gateway_mock_envelope_has_degraded_markers() -> None:
    """The gateway's _mock_fallback_response stamps degraded markers.

    Without these markers, downstream layers cannot detect the mock path.
    This test guards the contract — any future refactor that drops the
    markers will break B-003 layer 2 propagation.
    """
    from icoder_runtime.core.llm_gateway import _mock_fallback_response

    envelope = _mock_fallback_response("no_api_key")
    assert envelope.get("degraded") is True
    assert envelope.get("is_mock") is True
    assert envelope.get("degraded_reason") == "no_api_key"
    assert envelope.get("provider") == "mock"
    # The marker also appears inside the JSON content payload's `notes`
    # field (so the schema parser picks it up via MedicalCodingOutputSchema).
    content = envelope.get("content", "")
    assert "[DeepSeek degraded] no_api_key" in content


# ─────────────────────────────────────────────────────────────────────
# §2 DeepSeekCodingAdapter._parse_response propagates is_mock
# ─────────────────────────────────────────────────────────────────────


def test_parse_response_propagates_gateway_mock_to_schema() -> None:
    """A gateway envelope with degraded=True produces a schema with is_mock=True.

    Pre-B-003: schema.is_mock was hardcoded False, losing the marker.
    Post-B-003: schema.is_mock reflects gateway_mock, so layer 4 can branch.
    """
    from icoder_runtime.providers.medical_coding.deepseek_coding_adapter import (
        DeepSeekCodingAdapter,
    )

    adapter = DeepSeekCodingAdapter.__new__(DeepSeekCodingAdapter)
    # Build a mock gateway envelope (no real LLM call) with degraded markers.
    fake_gateway_envelope = {
        "content": '{"review_conclusion": "PASS", "extracted_diagnoses": []}',
        "degraded": True,
        "is_mock": True,
        "degraded_reason": "no_api_key",
        "provider": "mock",
    }

    schema = adapter._parse_response(fake_gateway_envelope)
    assert getattr(schema, "is_mock", False) is True, (
        "B-003 layer 2: schema must carry is_mock=True when gateway envelope is degraded"
    )


# ─────────────────────────────────────────────────────────────────────
# §2b _error_schema accepts is_mock / degraded_reason kwargs
# ─────────────────────────────────────────────────────────────────────


def test_error_schema_accepts_is_mock_and_degraded_reason_kwargs() -> None:
    """The _error_schema helper propagates is_mock / degraded_reason to notes.

    Without the kwargs, callers receiving a gateway mock could not flag the
    error schema as mock — losing the marker before layer 4 short-circuit.
    """
    from icoder_runtime.providers.medical_coding.deepseek_coding_adapter import (
        DeepSeekCodingAdapter,
    )

    adapter = DeepSeekCodingAdapter.__new__(DeepSeekCodingAdapter)
    schema = adapter._error_schema(
        "parse failure",
        is_mock=True,
        degraded_reason="provider_http_500",
    )
    assert getattr(schema, "is_mock", False) is True
    notes = getattr(schema, "notes", "") or ""
    assert "provider_http_500" in notes
    assert "[DeepSeek degraded]" in notes


# ─────────────────────────────────────────────────────────────────────
# §3 CodingResult accepts degraded=True (dataclass field exists)
# ─────────────────────────────────────────────────────────────────────


def test_coding_result_accepts_degraded_fields() -> None:
    """CodingResult has degraded + degraded_reason fields (B-003 layer 3)."""
    from app.coding_runtime.base import CodingResult

    # Default values are False / empty.
    default = CodingResult(codes=[])
    assert default.degraded is False
    assert default.degraded_reason == ""

    # Explicit set works.
    flagged = CodingResult(
        codes=[],
        degraded=True,
        degraded_reason="no_api_key",
        error=True,
        error_reason="llm_degraded",
    )
    assert flagged.degraded is True
    assert flagged.degraded_reason == "no_api_key"


# ─────────────────────────────────────────────────────────────────────
# §4 FastCodingRuntime.predict short-circuits on schema.is_mock
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fast_runtime_short_circuits_on_schema_is_mock(monkeypatch) -> None:
    """FastCodingRuntime.predict returns a degraded CodingResult when schema.is_mock.

    Pre-B-003: a mock schema was processed through the success branch,
    producing empty codes that the frontend rendered as "通过".
    Post-B-003: the runtime short-circuits to an error CodingResult.
    """
    from app.coding_runtime.fast_runtime import FastCodingRuntime
    from app.coding_runtime.base import CodingRequest, RuntimeMode

    runtime = FastCodingRuntime()

    # Build a mock schema with is_mock=True (simulating gateway fallback).
    class _FakeIssue:
        code = ""
        message = ""
        suggestion = ""

    class _FakeSchema:
        is_mock = True
        review_conclusion = "PASS"
        issues_found = []
        extracted_diagnoses = []
        procedures = []
        model = "deepseek-chat"
        notes = "[DeepSeek degraded] no_api_key. Mock response, not a real LLM call."

    async def _fake_infer_async(self, messages, *, context=None):
        return _FakeSchema()

    # Patch the DeepSeekCodingAdapter.infer_async on the class.
    from icoder_runtime.providers.medical_coding.deepseek_coding_adapter import (
        DeepSeekCodingAdapter,
    )
    monkeypatch.setattr(DeepSeekCodingAdapter, "infer_async", _fake_infer_async, raising=False)

    request = CodingRequest(text="患者男，65岁，冠状动脉粥样硬化性心脏病。", mode=RuntimeMode.CORTI_LIKE_FAST)
    result = await runtime.predict(request)

    assert result.degraded is True
    assert result.error is True
    assert result.error_reason == "llm_degraded"
    assert "no_api_key" in result.degraded_reason
    assert "降级" in result.summary
    assert result.codes == []


# ─────────────────────────────────────────────────────────────────────
# §4b MedCoderRuntime.predict same short-circuit
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_medcoder_runtime_short_circuits_on_schema_is_mock(monkeypatch) -> None:
    """MedCoderRuntime.predict returns a degraded CodingResult when schema.is_mock."""
    from app.coding_runtime.medcoder_runtime import MedCoderRuntime
    from app.coding_runtime.base import CodingRequest, RuntimeMode

    runtime = MedCoderRuntime()

    class _FakeSchema:
        is_mock = True
        method_stage_trace = []
        extracted_diagnoses = []
        procedures = []
        notes = "[DeepSeek degraded] provider_http_429. Mock response, not a real LLM call."

    # Patch HybridCodingAdapter.infer_async to return the mock schema.
    class _FakeHybridAdapter:
        def __init__(self, *args, **kwargs):
            pass

        async def infer_async(self, messages):
            return _FakeSchema()

    import sys
    fake_module = type(sys)("icoder_runtime.providers.medical_coding")
    fake_module.HybridCodingAdapter = _FakeHybridAdapter
    monkeypatch.setitem(sys.modules, "icoder_runtime.providers.medical_coding", fake_module)

    request = CodingRequest(text="患者男，65岁，冠状动脉粥样硬化性心脏病。", mode=RuntimeMode.MEDCODER_DEEP)
    result = await runtime.predict(request)

    assert result.degraded is True
    assert result.error is True
    assert result.error_reason == "llm_degraded"
    assert "provider_http_429" in result.degraded_reason
    assert "降级" in result.summary
    assert result.codes == []


# ─────────────────────────────────────────────────────────────────────
# §5 _map_coding_result forces error=True on result.degraded
# ─────────────────────────────────────────────────────────────────────


def test_map_coding_result_forces_error_on_degraded() -> None:
    """_map_coding_result surfaces result.degraded as AgentRunResponse(error=True).

    Defensive check (B-003 layer 5): if a future runtime sets degraded=True
    without also setting error=True, _map_coding_result still surfaces the
    degradation. Per Charter §二十六.24 ZERO TOLERANCE for false-success UI.
    """
    from app.api.agent_run import _map_coding_result
    from app.coding_runtime.base import CodingResult
    from datetime import datetime, timezone

    t0 = 0.0
    degraded_result = CodingResult(
        codes=[],  # empty codes — without layer 5, this would render as "通过"
        summary="LLM 提供方降级 (no_api_key)。",
        runtime_mode="corti_like_fast",
        latency_ms=42,
        llm_provider="mock",
        trace_id="trace-test-b-003",
        run_id="run-test-b-003",
        # NOTE: error=False here is intentional — we are testing that
        # _map_coding_result catches degraded=True even when error=False
        # (defensive layer for future runtimes).
        error=False,
        error_reason="",
        degraded=True,
        degraded_reason="no_api_key",
    )

    response = _map_coding_result(
        agent_id="medical-coding-agent",
        run_id="run-test-b-003",
        trace_id="trace-test-b-003",
        result=degraded_result,
        include_trace=True,
        include_evidence=True,
        t0=t0,
    )

    assert response.error is True, (
        "B-003 layer 5: degraded result MUST surface as error=True end-to-end"
    )
    assert response.error_reason == "no_api_key"
    assert response.manual_review_required is True
    assert response.result == {"contract_output_suppressed": True}
    assert response.evidence == []
    assert response.warnings == []
    # Summary preserved (user-visible signal).
    assert "降级" in response.summary
