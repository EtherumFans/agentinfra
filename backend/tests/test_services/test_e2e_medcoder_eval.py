"""Tests for e2e_medcoder_validation.py — F1@K reporter + 4-variant ablation."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from scripts import e2e_medcoder_validation as em  # noqa: E402


# ── F1@K metric ──


class TestF1AtK:
    def test_perfect_match_at_1(self):
        assert em.f1_at_k({"I50.9"}, ["I50.900"], k=1) == 1.0

    def test_perfect_match_at_2(self):
        # Gold in top-2 but not top-1: recall=1.0, precision=1/2 → F1≈0.667
        # (proper F1 penalizes extra wrong predictions, not just recall)
        f1 = em.f1_at_k({"I50.9"}, ["I21.0", "I50.900"], k=2)
        assert f1 == pytest.approx(2 / 3, abs=0.01)

    def test_pure_top1_with_no_extras(self):
        # If the top-K is exactly the gold set, F1=1
        assert em.f1_at_k({"I50.9"}, ["I50.900"], k=2) == 1.0

    def test_no_match(self):
        assert em.f1_at_k({"I50.9"}, ["I21.0"], k=5) == 0.0

    def test_empty_inputs(self):
        assert em.f1_at_k(set(), [], k=1) == 1.0
        assert em.f1_at_k({"I50.9"}, [], k=5) == 0.0
        assert em.f1_at_k(set(), ["anything"], k=5) == 0.0

    def test_subdivision_tolerant(self):
        # I50.900 normalizes to I50.9; expected = I50.9 → match
        assert em.f1_at_k({"I50.9"}, ["I50.900"], k=1) == 1.0
        # I50.9 normalizes to I50.9; predicted = I50.900 → match
        assert em.f1_at_k({"I50.900"}, ["I50.9"], k=1) == 1.0

    def test_partial_overlap(self):
        # expected = {A, B, C}, predicted = [A, D, E] at k=3 → tp=1, p=1/3, r=1/3
        f1 = em.f1_at_k({"A", "B", "C"}, ["A", "D", "E"], k=3)
        assert f1 == pytest.approx(1 / 3, abs=0.01)

    def test_x_placeholder_stripped(self):
        # I50.x00 → I50 (both normalize the same)
        assert em.f1_at_k({"I50"}, ["I50.x00"], k=1) == 1.0

    def test_truncates_at_k(self):
        # Gold = A, predicted = [D, E, A] at k=2 → A not in top-2 → F1=0
        assert em.f1_at_k({"A"}, ["D", "E", "A"], k=2) == 0.0
        # Same predicted at k=3 → A in top-3 → recall=1, precision=1/3 → F1=0.5
        f1 = em.f1_at_k({"A"}, ["D", "E", "A"], k=3)
        assert f1 == pytest.approx(0.5, abs=0.01)


# ── Gold code extraction ──


class TestExtractGoldCodes:
    def test_principal_only(self):
        case = {"expected_principal_diagnosis": "I50.900"}
        assert em.extract_gold_codes(case) == {"I50.900"}

    def test_with_secondary_and_procedures(self):
        case = {
            "expected_principal_diagnosis": "I50.900",
            "expected_secondary_diagnoses": ["I10", "E11.900"],
            "expected_procedure_codes": ["00.66"],
        }
        assert em.extract_gold_codes(case) == {"I50.900", "I10", "E11.900", "00.66"}

    def test_missing_principal(self):
        case = {"expected_secondary_diagnoses": ["I10"]}
        assert em.extract_gold_codes(case) == {"I10"}

    def test_empty_case(self):
        assert em.extract_gold_codes({}) == set()

    def test_icoder_201_nested_format(self):
        """iCoDer 201 fixture uses {expected: {primary_diagnosis: {code}}}."""
        case = {
            "id": "GC0001",
            "encounter_text": "...",
            "expected": {
                "primary_diagnosis": {"code": "Z51.102", "description": ""},
                "secondary_diagnoses": [
                    {"code": "Z45.800x012"},
                    {"code": "C20.x00"},
                ],
                "primary_procedure": {"code": "99.2503"},
            },
        }
        codes = em.extract_gold_codes(case)
        # Includes principal + secondary + primary_procedure
        assert "Z51.102" in codes
        assert "Z45.800x012" in codes
        assert "C20.x00" in codes
        assert "99.2503" in codes

    def test_text_field_uses_encounter_text_fallback(self):
        """_get_case_text should fall back to encounter_text if text missing."""
        from scripts import e2e_medcoder_validation as em
        assert em._get_case_text({"text": "from text"}) == "from text"
        assert em._get_case_text({"encounter_text": "from encounter"}) == "from encounter"
        # text wins if both present
        assert em._get_case_text({"text": "t", "encounter_text": "e"}) == "t"
        assert em._get_case_text({}) == ""


# ── Variant dispatch ──


class TestVariantDispatch:
    def test_full_variant_uses_adapter(self):
        from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter
        from unittest.mock import MagicMock, patch
        adapter = HybridCodingAdapter(mode="medcoder", retriever=None)
        # Use a stub that returns predictable extracted_diagnoses
        case = {
            "text": "患者心衰",
            "expected_principal_diagnosis": "I50.900",
        }
        # Patch infer_async to return a controlled output
        from official_agents.medical_coding.schema import (
            MedicalCodingOutputSchema, ExtractedDiagnosis, CandidateCode,
        )
        async def _stub(*args, **kwargs):
            return MedicalCodingOutputSchema(
                mode="medcoder",
                extracted_diagnoses=[
                    ExtractedDiagnosis(
                        disease_text="心衰",
                        final_top_k=[CandidateCode(code="I50.900", name="心衰", score=0.9, source="rerank")],
                        final_confidence=0.9,
                    ),
                ],
            )
        adapter.infer_async = _stub
        result = em._full_topk(case, adapter)
        assert result == ["I50.900"]

    def test_full_variant_empty_text(self):
        from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter
        adapter = HybridCodingAdapter(mode="medcoder")
        assert em._full_topk({}, adapter) == []
        assert em._full_topk({"text": ""}, adapter) == []


# ── Aggregate runner ──


class TestRunEvaluation:
    def test_smoke_run_with_prompt_variant(self, tmp_path):
        """Run the prompt variant on a tiny fixture; verify report shape."""
        fixture = tmp_path / "gold.json"
        fixture.write_text(json.dumps([
            {"encounter_id": "c1", "text": "患者胸闷", "expected_principal_diagnosis": "I50.900"},
            {"encounter_id": "c2", "text": "患者头痛", "expected_principal_diagnosis": "R51"},
        ]), encoding="utf-8")

        cases = em.load_gold_cases(str(fixture))
        assert len(cases) == 2

        # Mock gateway that returns I50.900 for chest-pain text
        class _G:
            async def generate(self, messages, *, provider=""):
                user = messages[-1].get("content", "")
                if "胸" in user:
                    return {"content": '[{"disease_text": "心衰", "supporting_evidence": "胸闷", "llm_initial_code": "I50.900"}]'}
                return {"content": '[{"disease_text": "头痛", "supporting_evidence": "头痛", "llm_initial_code": "R51"}]'}

        result = em.run_evaluation(cases, variant="prompt", gateway=_G())
        assert "summary" in result
        assert "per_case" in result
        assert result["summary"]["variant"] == "prompt"
        assert result["summary"]["n_cases"] == 2
        # Mock returns the gold code for both → F1@1 should be 1.0 for both
        assert result["summary"]["f1_at_1"] == 1.0
        assert result["summary"]["f1_at_2"] == 1.0
        assert result["summary"]["f1_at_5"] == 1.0

    def test_full_variant_completes_with_mock_adapter(self, tmp_path):
        """C6: --variant full must complete (no raise) even on a tiny fixture.

        Uses a mock adapter that returns a synthetic ExtractedDiagnosis
        matching the gold code. The point of this test is the
        defense-in-depth: a pipeline exception (e.g., worker died)
        must NOT crash the eval loop.
        """
        fixture = tmp_path / "gold.json"
        fixture.write_text(json.dumps([
            {"encounter_id": "c1", "text": "患者胸闷", "expected_principal_diagnosis": "I50.900"},
        ]), encoding="utf-8")

        cases = em.load_gold_cases(str(fixture))
        assert len(cases) == 1

        # Build a fake adapter whose infer_async returns one diagnosis
        # carrying the gold code.
        from official_agents.medical_coding.schema import (
            MedicalCodingOutputSchema, ExtractedDiagnosis, DiagnosisEntry, CandidateCode,
        )
        out = MedicalCodingOutputSchema(
            review_conclusion="PASS",
            primary_diagnosis=DiagnosisEntry(code="I50.900", description="心衰", confidence=0.9),
            mode="medcoder",
        )
        out.extracted_diagnoses = [
            ExtractedDiagnosis(
                disease_text="心衰",
                supporting_evidence=[],
                llm_initial_code="I50.900",
                final_top_k=[CandidateCode(code="I50.900", name="心衰", score=0.9, chapter="")],
                final_confidence=0.9,
            )
        ]
        class _Adapter:
            async def infer_async(self, messages, **kwargs):
                return out
        result = em.run_evaluation(cases, variant="full", adapter=_Adapter(), gateway=None)
        assert result["summary"]["variant"] == "full"
        assert result["summary"]["n_cases"] == 1
        # F1@1 is 1.0 because the gold code is in top-1.
        assert result["summary"]["f1_at_1"] == 1.0
        # No exception escaped the run_evaluation loop.

    def test_full_variant_handles_silent_adapter_failure(self, tmp_path):
        """C6: if the adapter raises, _full_topk's internal try/except
        returns [] rather than crashing. The eval loop completes with
        F1=0 for that case (no codes predicted), not an unhandled exception.
        """
        fixture = tmp_path / "gold.json"
        fixture.write_text(json.dumps([
            {"encounter_id": "c1", "text": "患者胸闷", "expected_principal_diagnosis": "I50.900"},
        ]), encoding="utf-8")

        cases = em.load_gold_cases(str(fixture))
        assert len(cases) == 1

        class _FailingAdapter:
            async def infer_async(self, messages, **kwargs):
                raise RuntimeError("simulated worker death")

        result = em.run_evaluation(
            cases, variant="full", adapter=_FailingAdapter(), gateway=None,
        )
        assert result["summary"]["variant"] == "full"
        assert result["summary"]["n_cases"] == 1
        # _full_topk returned []; F1 is 0, but the eval didn't crash.
        assert result["summary"]["f1_at_1"] == 0.0
        # The case is still recorded in per_case.
        assert len(result["per_case"]) == 1
        assert result["per_case"][0]["predicted_top_5"] == []


# ── Sanity: script is importable ──


class TestScriptIsImportable:
    def test_main_module_attribute(self):
        assert hasattr(em, "main")
        assert hasattr(em, "VARIANTS")
        assert hasattr(em, "f1_at_k")
        assert em.VARIANTS == ("full", "prompt", "retrieve", "prompt+retrieve")

    def test_cli_runs_with_prompt_variant(self, tmp_path):
        """End-to-end CLI smoke test on a 2-case fixture."""
        fixture = tmp_path / "mini.json"
        fixture.write_text(json.dumps([
            {"encounter_id": "c1", "text": "患者心衰", "expected_principal_diagnosis": "I50.900"},
            {"encounter_id": "c2", "text": "患者头痛", "expected_principal_diagnosis": "R51"},
        ]), encoding="utf-8")
        out = tmp_path / "report.json"

        # Run the script as a subprocess
        script = Path(em.__file__)
        result = subprocess.run(
            [sys.executable, str(script),
             "--cases", str(fixture),
             "--variant", "prompt",
             "--limit", "2",
             "--out", str(out)],
            capture_output=True, text=True, timeout=60,
            cwd=str(_BACKEND_ROOT),
        )
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "F1@1:" in result.stdout

        # Verify the report file was written
        assert out.exists()
        report = json.loads(out.read_text(encoding="utf-8"))
        assert "summary" in report
        assert "per_case" in report
        assert report["summary"]["variant"] == "prompt"
        assert report["summary"]["n_cases"] == 2
