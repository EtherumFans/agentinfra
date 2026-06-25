"""CodingMethod base class + MethodResult dataclass tests (~12 cases).

Covers:
  - MethodFamily / MethodCapability enum values
  - MethodStageTraceEntry.to_dict round-trip
  - MethodResult.to_dict serialization
  - CodingMethod subclass metadata contract
  - CodingMethod.capabilities_check (missing/present/extra)
  - CodingMethod.to_meta shape
"""

from __future__ import annotations

import pytest

from icoder_runtime.methods.base import (
    CodingMethod,
    MethodCapability,
    MethodFamily,
    MethodResult,
    MethodStageTraceEntry,
)


# ── Enums ──


class TestEnums:
    def test_method_family_values(self):
        assert MethodFamily.MEDCODER.value == "medcoder"
        assert MethodFamily.LEGACY.value == "legacy"
        assert MethodFamily.NOOP.value == "noop"

    def test_method_capability_values(self):
        assert MethodCapability.LLM.value == "llm"
        assert MethodCapability.RETRIEVER.value == "retriever"
        assert MethodCapability.RULE_SET.value == "rule_set"

    def test_method_capability_iterable(self):
        # All three capabilities must be present.
        names = {c.value for c in MethodCapability}
        assert names == {"llm", "retriever", "rule_set"}


# ── MethodStageTraceEntry ──


class TestMethodStageTraceEntry:
    def test_default_values(self):
        e = MethodStageTraceEntry()
        d = e.to_dict()
        assert d == {
            "stage_name": "",
            "status": "ok",
            "latency_ms": 0,
            "output_size": 0,
            "notes": "",
        }

    def test_custom_values(self):
        e = MethodStageTraceEntry(
            stage_name="extract",
            status="ok",
            latency_ms=420,
            output_size=3,
            notes="3 diseases extracted",
        )
        assert e.to_dict()["stage_name"] == "extract"
        assert e.to_dict()["latency_ms"] == 420
        assert e.to_dict()["output_size"] == 3


# ── MethodResult ──


class TestMethodResult:
    def test_default_ok_shape(self):
        r = MethodResult(method_id="m1", method_name="M1", method_family="medcoder")
        d = r.to_dict()
        assert d["status"] == "ok"
        assert d["method_id"] == "m1"
        assert d["stage_trace"] == []
        assert d["secondary_codes"] == []
        assert d["procedure_codes"] == []
        assert d["issues"] == []
        assert d["manual_review_required"] is False
        assert d["processing_time_ms"] == 0

    def test_unavailable_shape(self):
        r = MethodResult(
            method_id="m2",
            method_name="M2",
            method_family="medcoder",
            status="unavailable",
            reason="missing required capabilities: ['retriever']",
        )
        d = r.to_dict()
        assert d["status"] == "unavailable"
        assert "missing required capabilities" in d["reason"]

    def test_trace_round_trip(self):
        r = MethodResult(
            method_id="m3",
            method_name="M3",
            method_family="medcoder",
            stage_trace=[
                MethodStageTraceEntry(stage_name="s1", latency_ms=100, output_size=5),
                MethodStageTraceEntry(stage_name="s2", latency_ms=200, output_size=1),
            ],
            processing_time_ms=300,
        )
        d = r.to_dict()
        assert len(d["stage_trace"]) == 2
        assert d["stage_trace"][0]["stage_name"] == "s1"
        assert d["stage_trace"][1]["latency_ms"] == 200
        assert d["processing_time_ms"] == 300

    def test_full_schema_preserved(self):
        # full_schema is intentionally NOT in to_dict() — preserved as raw attr.
        r = MethodResult(
            method_id="m4",
            method_name="M4",
            method_family="legacy",
            full_schema={"mode": "deepseek", "extra": 1},
        )
        assert r.full_schema == {"mode": "deepseek", "extra": 1}
        assert "full_schema" not in r.to_dict()


# ── CodingMethod ABC contract ──


class _DummyMethod(CodingMethod):
    """Minimal concrete subclass for ABC tests."""

    method_id = "test.dummy"
    method_name = "Test Dummy"
    method_family = "legacy"
    stage_count = 1
    required_capabilities = (MethodCapability.LLM,)
    description = "dummy method for ABC tests"

    async def run(self, emr_text, ctx=None):
        return MethodResult(
            method_id=self.method_id,
            method_name=self.method_name,
            method_family=self.method_family,
            primary_code="I50.900",
            primary_name="心力衰竭",
            confidence=0.8,
        )


class TestCodingMethodContract:
    def test_metadata_class_attrs(self):
        m = _DummyMethod()
        assert m.method_id == "test.dummy"
        assert m.method_family == "legacy"
        assert m.stage_count == 1
        assert m.required_capabilities == (MethodCapability.LLM,)

    def test_capabilities_check_present(self):
        m = _DummyMethod()
        caps = m.capabilities_check({"llm": True, "retriever": False, "rule_set": True})
        assert caps == {"llm": True}

    def test_capabilities_check_missing(self):
        m = _DummyMethod()
        caps = m.capabilities_check({"retriever": True})  # llm missing
        assert caps == {"llm": False}

    def test_capabilities_check_default_empty(self):
        m = _DummyMethod()
        caps = m.capabilities_check()  # nothing passed
        assert caps == {"llm": False}

    def test_to_meta_shape(self):
        m = _DummyMethod()
        meta = m.to_meta()
        assert meta["method_id"] == "test.dummy"
        assert meta["method_family"] == "legacy"
        assert meta["required_capabilities"] == ["llm"]
        assert meta["stage_count"] == 1
        assert meta["description"] == "dummy method for ABC tests"

    @pytest.mark.asyncio
    async def test_run_returns_method_result(self):
        m = _DummyMethod()
        r = await m.run("心力衰竭")
        assert isinstance(r, MethodResult)
        assert r.method_id == "test.dummy"
        assert r.primary_code == "I50.900"