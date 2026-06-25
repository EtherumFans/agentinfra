"""Built-in CodingMethod tests (~16 cases).

Covers:
  - All 10 builtin methods are registered with correct metadata
  - MedCodER variants have correct variant_name + stage_count
  - Legacy variants have correct mode_value + stage_count
  - Noop method always returns unavailable
  - Code Like Humans (CLH) method has correct metadata + capability
  - _schema_to_method_result flattens correctly (codes / issues / procedures)
  - _stage helper builds trace entries with monotonic timing
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from icoder_runtime.methods.base import (
    MethodCapability,
    MethodFamily,
    MethodResult,
)
from icoder_runtime.methods.builtin import (
    LegacyDeepSeekMethod,
    LegacyHybridMethod,
    LegacyNoRepairMethod,
    LegacyPromptLLMMethod,
    MedCodERCodeLikeHumansMethod,
    MedCodERFullMethod,
    MedCodERPromptMethod,
    MedCodERPromptRetrieveMethod,
    MedCodERRetrieveMethod,
    NoopUnavailableMethod,
    _CLHMethodBase,
    _schema_to_method_result,
    _stage,
    register_builtin_methods,
)
from icoder_runtime.methods.registry import GLOBAL_REGISTRY
from official_agents.medical_coding.schema import (
    CodingIssue,
    DiagnosisEntry,
    MedicalCodingOutputSchema,
    ProcedureEntry,
)
from official_agents.medical_coding.modes import Mode


@pytest.fixture
def empty_registry():
    """Clear registry for tests that want a truly empty slate."""
    GLOBAL_REGISTRY.clear()
    yield GLOBAL_REGISTRY


# ── Builtin registration ──


class TestBuiltinRegistration:
    def test_all_ten_registered(self, empty_registry):
        register_builtin_methods()
        ids = GLOBAL_REGISTRY.method_ids()
        expected = {
            "medcoder.full",
            "medcoder.prompt",
            "medcoder.retrieve",
            "medcoder.prompt+retrieve",
            "medcoder.code_like_humans",
            "legacy.deepseek",
            "legacy.prompt_llm",
            "legacy.hybrid",
            "legacy.no_repair",
            "noop.unavailable",
        }
        assert expected.issubset(set(ids))
        assert len(ids) == 10

    def test_idempotent(self, empty_registry):
        n1 = register_builtin_methods()
        n2 = register_builtin_methods()
        assert n1 == 10
        assert n2 == 10  # returns 10 (the count attempted), not 0
        # Registry should still have 10 (last-writer-wins on same id)
        medcoder_ids = [i for i in GLOBAL_REGISTRY.method_ids() if i.startswith("medcoder.")]
        assert len(medcoder_ids) == 5  # 4 NAACL variants + CLH


# ── MedCodER variants ──


class TestMedCodERVariants:
    @pytest.mark.parametrize(
        "cls,expected_variant,expected_stages",
        [
            (MedCodERFullMethod, "full", 5),
            (MedCodERPromptMethod, "prompt", 1),
            (MedCodERRetrieveMethod, "retrieve", 1),
            (MedCodERPromptRetrieveMethod, "prompt+retrieve", 2),
        ],
    )
    def test_variant_metadata(self, cls, expected_variant, expected_stages):
        m = cls()
        assert m.method_family == "medcoder"
        assert m.variant_name == expected_variant
        assert m.stage_count == expected_stages
        assert m.required_capabilities == (
            MethodCapability.LLM,
            MethodCapability.RETRIEVER,
            MethodCapability.RULE_SET,
        )

    def test_full_method_id(self):
        assert MedCodERFullMethod.method_id == "medcoder.full"
        assert MedCodERFullMethod.method_name  # non-empty

    def test_empty_emr_returns_unavailable(self):
        m = MedCodERFullMethod()
        # Synchronous: skip asyncio.run for the empty path by directly
        # constructing; we still need a strategy call though. Use the
        # strategy shortcut: empty emr is handled before any LLM call.
        import asyncio
        result = asyncio.run(m.run(""))
        assert result.status == "unavailable"
        assert "empty emr_text" in result.reason


# ── Legacy variants ──


class TestLegacyVariants:
    @pytest.mark.parametrize(
        "cls,expected_mode",
        [
            (LegacyDeepSeekMethod, Mode.DEEPSEEK),
            (LegacyPromptLLMMethod, Mode.PROMPT_LLM),
            (LegacyHybridMethod, Mode.HYBRID),
            (LegacyNoRepairMethod, Mode.NO_REPAIR),
        ],
    )
    def test_legacy_mode_metadata(self, cls, expected_mode):
        m = cls()
        assert m.method_family == "legacy"
        assert m.mode_value == expected_mode
        assert m.stage_count == 2
        assert m.required_capabilities == (
            MethodCapability.LLM,
            MethodCapability.RULE_SET,
        )

    def test_deepseek_method_id(self):
        assert LegacyDeepSeekMethod.method_id == "legacy.deepseek"

    def test_legacy_empty_emr(self):
        m = LegacyHybridMethod()
        import asyncio
        result = asyncio.run(m.run(""))
        assert result.status == "unavailable"


# ── Noop method ──


class TestNoopMethod:
    @pytest.mark.asyncio
    async def test_always_unavailable(self):
        m = NoopUnavailableMethod()
        result = await m.run("any text")
        assert result.status == "unavailable"
        assert result.method_family == "noop"
        assert "empty or invalid" in result.reason or "no coding method" in result.reason

    def test_no_required_capabilities(self):
        m = NoopUnavailableMethod()
        assert m.required_capabilities == ()


# ── Helper functions ──


class TestSchemaToMethodResult:
    def test_flattens_diagnosis_codes(self):
        schema = MedicalCodingOutputSchema(
            primary_diagnosis=DiagnosisEntry(
                code="I21.001", description="急性心肌梗死", confidence=0.95,
            ),
            secondary_diagnoses=[
                DiagnosisEntry(code="I10", description="高血压", confidence=0.88, category="comorbidity"),
            ],
        )
        # Build a fake method instance for the helper
        method = MagicMock()
        method.method_id = "test.flatten"
        method.method_name = "Test"
        method.method_family = "legacy"
        result = _schema_to_method_result(method, schema, [], 100)
        assert result.primary_code == "I21.001"
        assert result.primary_name == "急性心肌梗死"
        assert result.primary_confidence == 0.95
        assert result.confidence == 0.0  # not set on schema
        assert len(result.secondary_codes) == 1
        assert result.secondary_codes[0]["code"] == "I10"

    def test_flattens_procedures(self):
        schema = MedicalCodingOutputSchema(
            primary_diagnosis=DiagnosisEntry(code="I21.001", description="x"),
            procedures=[
                ProcedureEntry(code="00.66", description="PCI", confidence=0.92),
            ],
        )
        method = MagicMock()
        method.method_id = "test"
        method.method_name = "Test"
        method.method_family = "legacy"
        result = _schema_to_method_result(method, schema, [], 50)
        assert len(result.procedure_codes) == 1
        assert result.procedure_codes[0]["code"] == "00.66"

    def test_flattens_issues(self):
        schema = MedicalCodingOutputSchema(
            primary_diagnosis=DiagnosisEntry(code="I21.001", description="x"),
            issues_found=[
                CodingIssue(severity="high", code="R001", message="code invalid", suggestion="use I21.0"),
            ],
        )
        method = MagicMock()
        method.method_id = "test"
        method.method_name = "Test"
        method.method_family = "legacy"
        result = _schema_to_method_result(method, schema, [], 50)
        assert len(result.issues) == 1
        assert result.issues[0]["severity"] == "high"
        assert result.issues[0]["suggestion"] == "use I21.0"

    def test_status_override(self):
        schema = MedicalCodingOutputSchema(
            primary_diagnosis=DiagnosisEntry(code="I21.001", description="x"),
        )
        method = MagicMock()
        method.method_id = "test"
        method.method_name = "Test"
        method.method_family = "legacy"
        result = _schema_to_method_result(
            method, schema, [], 0, status="unavailable", reason="missing llm"
        )
        assert result.status == "unavailable"
        assert result.reason == "missing llm"

    def test_preserves_full_schema(self):
        schema = MedicalCodingOutputSchema(
            primary_diagnosis=DiagnosisEntry(code="I21.001", description="x"),
            mode=Mode.DEEPSEEK,
        )
        method = MagicMock()
        method.method_id = "test"
        method.method_name = "Test"
        method.method_family = "legacy"
        result = _schema_to_method_result(method, schema, [], 0)
        assert result.full_schema is not None
        assert result.full_schema["mode"] == "deepseek"


class TestStageHelper:
    def test_stage_timing(self):
        t0 = time.monotonic() - 0.05  # backdate 50ms
        e = _stage("test_stage", t0)
        assert e.stage_name == "test_stage"
        assert e.latency_ms >= 40  # allow scheduler slop
        assert e.status == "ok"
        assert e.output_size == 0

    def test_stage_custom_attrs(self):
        t0 = time.monotonic()
        e = _stage(
            "extract", t0,
            status="failed", output_size=3, notes="3 diseases",
        )
        assert e.status == "failed"
        assert e.output_size == 3


# ── Code Like Humans (CLH) method — Phase C ──


class TestCLHMethod:
    def test_metadata(self):
        m = MedCodERCodeLikeHumansMethod()
        assert m.method_id == "medcoder.code_like_humans"
        assert m.method_name == "MedCodER Code Like Humans"
        assert m.method_family == MethodFamily.MEDCODER.value
        assert m.stage_count == 4

    def test_capability_does_not_require_retriever(self):
        # CLH uses code_dict_service + LLM, NOT BGE-M3+FAISS
        caps = {c.value for c in MedCodERCodeLikeHumansMethod().required_capabilities}
        assert caps == {"llm", "rule_set"}
        assert "retriever" not in caps

    @pytest.mark.asyncio
    async def test_empty_emr_returns_unavailable(self):
        m = MedCodERCodeLikeHumansMethod()
        result = await m.run("")
        assert result.status == "unavailable"
        assert "empty emr_text" in result.reason
        assert result.stage_trace and result.stage_trace[0].stage_name == "input_validation"

    @pytest.mark.asyncio
    async def test_run_aggregates_candidates_into_schema(self):
        # Mock both experts to return controlled candidates.
        # Secondary dx has score 0.55 (< LOW_CONF_FLOOR 0.7) → manual_review_required=True.
        fake_dx = {
            "candidate_count": 2,
            "diagnosis_candidates": [
                {"code": "I50.900", "name": "心力衰竭", "score": 0.92,
                 "evidence_text": "EF 35%", "issues": []},
                {"code": "I10.x00", "name": "高血压", "score": 0.55,
                 "evidence_text": "BP 160/100", "issues": ["LOW_CONFIDENCE"]},
            ],
            "triage_summary": {"category": "cardiovascular"},
            "method": "code_like_humans_4step",
        }
        fake_px = {
            "candidate_count": 1,
            "procedure_candidates": [
                {"code": "00.6600", "name": "PCI", "score": 0.88,
                 "evidence_text": "支架植入", "issues": []},
            ],
            "method": "code_like_humans_4step",
        }

        m = MedCodERCodeLikeHumansMethod()
        # Inject mocks — bypass lazy import
        m._diagnosis_expert = MagicMock()
        m._diagnosis_expert.run = AsyncMock(return_value=fake_dx)
        m._procedure_expert = MagicMock()
        m._procedure_expert.run = AsyncMock(return_value=fake_px)

        result = await m.run("冠心病 PCI 术后", ctx={})
        assert result.status == "ok"
        assert result.method_id == "medcoder.code_like_humans"
        assert result.method_family == "medcoder"
        assert result.primary_code == "I50.900"  # highest dx score
        assert result.primary_name == "心力衰竭"
        assert result.primary_confidence == pytest.approx(0.92)
        # 1 secondary dx (I10.x00) + 1 procedure
        assert len(result.secondary_codes) == 1
        assert result.secondary_codes[0]["code"] == "I10.x00"
        assert len(result.procedure_codes) == 1
        assert result.procedure_codes[0]["code"] == "00.6600"
        # Low-score secondary dx (0.55 < 0.7) triggers manual_review + WARNING
        assert result.manual_review_required is True
        assert result.full_schema["review_conclusion"] == "WARNING"
        assert any("LOW_CONFIDENCE" in (i.get("code") or "") for i in result.issues)
        # 3 stages (no input_validation since emr_text is non-empty)
        stage_names = [s.stage_name for s in result.stage_trace]
        assert "phase_a_clinical_triage" in stage_names
        assert "phase_bcd_index_drill_evidence" in stage_names
        assert "phase_e_aggregation" in stage_names
        # full_schema is preserved
        assert result.full_schema is not None
        assert result.full_schema["mode"] == Mode.MEDCODER_CODE_LIKE_HUMANS.value

    def test_build_expert_context_wraps_raw_text(self):
        ctx = _CLHMethodBase._build_expert_context(
            "冠心病 PCI",
            {"admission_reason": "胸痛", "existing_diagnosis_codes": ["I20.000"]},
        )
        assert ctx["documents"] == [{"content": "冠心病 PCI", "doc_id": "input", "doc_type": "free_text"}]
        assert ctx["admission_reason"] == "胸痛"
        assert ctx["existing_diagnosis_codes"] == ["I20.000"]
        assert "diagnosis_facts" in ctx["evidence"]
        assert "procedure_facts" in ctx["evidence"]

    def test_aggregate_to_schema_empty_candidates(self):
        schema = _CLHMethodBase._aggregate_to_schema(
            {"diagnosis_candidates": [], "candidate_count": 0},
            {"procedure_candidates": [], "candidate_count": 0},
        )
        assert isinstance(schema, MedicalCodingOutputSchema)
        assert schema.primary_diagnosis.code == ""
        assert schema.secondary_diagnoses == []
        assert schema.procedures == []
        assert schema.manual_review_required is False
        assert schema.review_conclusion == "PASS"
        assert schema.mode == Mode.MEDCODER_CODE_LIKE_HUMANS

    def test_aggregate_to_schema_all_high_conf_no_review(self):
        schema = _CLHMethodBase._aggregate_to_schema(
            {"diagnosis_candidates": [
                {"code": "I50.900", "name": "心力衰竭", "score": 0.95, "evidence_text": "EF 30%"},
            ], "candidate_count": 1},
            {"procedure_candidates": [
                {"code": "00.6600", "name": "PCI", "score": 0.93, "evidence_text": "stent"},
            ], "candidate_count": 1},
        )
        assert schema.primary_diagnosis.code == "I50.900"
        assert schema.primary_diagnosis.confidence == pytest.approx(0.95)
        assert schema.manual_review_required is False
        assert schema.review_conclusion == "PASS"
        assert len(schema.procedures) == 1
        assert schema.procedures[0].code == "00.6600"
        assert schema.procedures[0].category == "principal"