"""Phase 3-A Section E — Runtime Integration tests.

Verifies the v1 → v2 projection wired in `app/api/runtime_platform.py`:
- `/api/runtime/agents/{agent_ref}/run` is RESTORED for the Medical Coding
  Agent (icoder/medical-coding-agent@2.0.0) and returns v2 Corti-style
  8 fields hoisted to the top level.
- Other agent_refs still get 410 Gone (Phase 2.1-A deprecation preserved).
- `/api/runtime/medical-coding/test` also projects v1 → v2 (consistency).
- The v2 fields are always present (Corti contract: no field omitted).
"""
from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-p11")


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app, raise_server_exceptions=False)


def _make_stub_v1() -> Any:
    """Build a stub MedicalCodingOutputSchema for the patched adapter."""
    from official_agents.medical_coding.schema import (
        CodingIssue,
        DiagnosisEntry,
        EvidenceSpan,
        MedicalCodingOutputSchema,
        ProcedureEntry,
    )
    return MedicalCodingOutputSchema(
        review_conclusion="WARNING",
        primary_diagnosis=DiagnosisEntry(
            code="I21.0",
            description="急性前壁心肌梗死",
            confidence=0.92,
            category="principal",
            evidence=[EvidenceSpan(text="前壁心肌梗死", char_start=0, char_end=6)],
        ),
        procedures=[
            ProcedureEntry(
                code="00.66",
                description="经皮冠状动脉介入",
                confidence=0.88,
                category="therapeutic",
            )
        ],
        issues_found=[
            CodingIssue(
                severity="high",
                code="R005",
                message="证据不足",
                suggestion="补充手术记录",
            )
        ],
        manual_review_required=True,
        confidence=0.85,
        provider="hybrid_adapter",
        model="stub-model",
    )


@pytest.fixture
def stub_adapter(monkeypatch):
    """Inject a stub HybridCodingAdapter returning a fixed v1 schema.

    Patches ``HybridCodingAdapter`` on the module where runtime_platform.py
    imports it (the function does `from icoder_runtime.providers.medical_coding
    import HybridCodingAdapter` inside the route handler, so patching the
    module attribute is sufficient).
    """
    import icoder_runtime.providers.medical_coding as mc_pkg

    class _StubAdapter:
        def __init__(self, *args, **kwargs):
            pass

        async def infer_async(self, messages):
            return _make_stub_v1()

    monkeypatch.setattr(mc_pkg, "HybridCodingAdapter", _StubAdapter)

    # Also patch app.state.platform_gateway + m2a_recorder so the route
    # can fetch them at request-time.
    from app.main import app

    class _StubGateway:
        async def generate(self, messages, provider="default"):
            return {"content": ""}

        def list_providers(self):
            return {
                "medical_coding": {"mode": "real", "engine": {"model": "stub"}},
                "deepseek": {"status": "configured", "model": "stub-model"},
            }

    class _StubDataPolicy:
        allow_external_llm = True
        pii_redaction_required = False

        def to_dict(self):
            return {"allow_external_llm": True}

    class _StubM2aRecorder:
        def is_active(self):
            return False

    app.state.platform_gateway = _StubGateway()
    app.state.data_policy = _StubDataPolicy()
    app.state.m2a_recorder = _StubM2aRecorder()


V2_FIELDS = [
    "review_conclusion",
    "manual_review_required",
    "encounter_summary",
    "documentation_gaps",
    "uncodable_items",
    "corti_validation_summary",
    "human_review",
    "trace_refs",
]


class TestMedicalCodingAgentRunRestored:
    """Section E: /agents/{ref}/run restored for medical-coding-agent@2.0.0."""

    def test_medical_coding_agent_run_returns_v2_fields(self, client, stub_adapter):
        r = client.post(
            "/api/runtime/agents/icoder%2Fmedical-coding-agent%402.0.0/run",
            json={"input": "患者前壁心肌梗死, 行 PCI 治疗"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # v1 fields preserved
        assert body["agent_ref"] == "icoder/medical-coding-agent@2.0.0"
        assert body["status"] == "success"
        assert body["primary_diagnosis"]["code"] == "I21.0"
        # v2 fields hoisted
        for field in V2_FIELDS:
            assert field in body, f"missing v2 field: {field}"
        # v2 field sanity
        assert body["review_conclusion"] == "WARNING"
        assert body["manual_review_required"] is True
        assert body["corti_validation_summary"]["passed"] is False
        assert len(body["corti_validation_summary"]["issues_found"]) == 1
        assert body["human_review"]["review_required"] is True
        assert body["trace_refs"]["run_id"]

    def test_other_agents_still_410(self, client):
        r = client.post(
            "/api/runtime/agents/some-other-agent%401.0.0/run",
            json={"input": "test"},
        )
        assert r.status_code == 410
        assert "Phase 2.1-A" in r.json()["detail"]

    def test_empty_input_400(self, client, stub_adapter):
        r = client.post(
            "/api/runtime/agents/icoder%2Fmedical-coding-agent%402.0.0/run",
            json={"input": "   "},
        )
        assert r.status_code == 400


class TestMedicalCodingTestV2Projection:
    """Section E: /medical-coding/test also projects v1 → v2."""

    def test_medical_coding_test_returns_v2_fields(self, client, stub_adapter):
        r = client.post(
            "/api/runtime/medical-coding/test",
            json={"encounter_text": "患者前壁心肌梗死, 行 PCI 治疗"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # v1 fields preserved
        assert body["primary_diagnosis"]["code"] == "I21.0"
        # v2 fields projected
        for field in V2_FIELDS:
            assert field in body, f"missing v2 field: {field}"
        assert body["review_conclusion"] == "WARNING"
        assert body["manual_review_required"] is True


class TestV2ProjectionContract:
    """Corti contract: every field present, even when empty (no field omitted)."""

    def test_v2_fields_always_present(self, client, stub_adapter):
        r = client.post(
            "/api/runtime/agents/icoder%2Fmedical-coding-agent%402.0.0/run",
            json={"input": "无问题病例"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        # All 8 v2 fields must be present with correct sub-shape
        assert isinstance(body["encounter_summary"], dict)
        assert "chief_complaint" in body["encounter_summary"]
        assert isinstance(body["documentation_gaps"], list)
        assert isinstance(body["uncodable_items"], list)
        assert isinstance(body["corti_validation_summary"], dict)
        assert "issues_found" in body["corti_validation_summary"]
        assert "fired_rules" in body["corti_validation_summary"]
        assert isinstance(body["human_review"], dict)
        assert "review_conclusion" in body["human_review"]
        assert "review_required" in body["human_review"]
        assert isinstance(body["trace_refs"], dict)
        assert "run_id" in body["trace_refs"]
        assert "method_id" in body["trace_refs"]
