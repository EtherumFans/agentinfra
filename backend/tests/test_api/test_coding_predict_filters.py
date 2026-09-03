"""Medical Coding v1 filter contract for the Chinese product workbench."""

from __future__ import annotations

import pytest

from app.coding_runtime import CodingResult, CodingResultCode
from app.services.coding_filter import code_allowed_by_filter


class _Dispatcher:
    async def dispatch(self, request):
        del request
        return CodingResult(
            codes=[
                CodingResultCode(
                    code="S22.089A",
                    display="胸椎骨折",
                    type="primary_diagnosis",
                    confidence=0.91,
                    evidence="T12 椎体压缩性骨折",
                    alternatives=[{"code": "S22.080A", "display": "其他胸椎骨折"}],
                ),
                CodingResultCode(
                    code="E11.9",
                    display="2型糖尿病",
                    type="secondary_diagnosis",
                    confidence=0.86,
                    evidence="2型糖尿病史",
                    alternatives=[{"code": "E11.8", "display": "其他糖尿病"}],
                ),
                CodingResultCode(
                    code="I10",
                    display="高血压",
                    type="secondary_diagnosis",
                    confidence=0.88,
                    evidence="高血压病史",
                ),
                CodingResultCode(
                    code="81.62",
                    system="ICD-9-CM-3-CN",
                    display="经皮椎体成形术",
                    type="procedure",
                    confidence=0.84,
                    evidence="行 T12 经皮椎体成形术",
                ),
            ],
            summary="three supported codes",
            raw_schema={
                "primary_diagnosis": {
                    "code": "S22.089A",
                    "description": "胸椎骨折",
                    "evidence": ["T12 压缩性骨折"],
                },
                "secondary_diagnoses": [
                    {
                        "code": "E11.9",
                        "description": "2型糖尿病",
                        "supporting_evidence": [{"text": "糖尿病史"}],
                    },
                    {"code": "I10", "description": "高血压"},
                ],
                "procedures": [
                    {
                        "code": "81.62",
                        "description": "经皮椎体成形术",
                        "evidence": ["行 T12 经皮椎体成形术"],
                    }
                ],
                "method_stage_trace": [{"stage": "extract"}],
            },
            trace_events=[{"step": "return", "status": "ok", "metadata": {}}],
        )


@pytest.mark.asyncio
async def test_v1_filter_expand_true_enforces_category_on_every_code_surface(
    client, monkeypatch
):
    from app.api import coding_predict as api_module

    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-filter-contract")
    monkeypatch.setattr(api_module, "get_dispatcher", lambda: _Dispatcher())

    response = await client.post(
        "/api/v1/coding/predict",
        json={
            "text": "患者有2型糖尿病史。",
            "coding_system": "icd10cn",
            "filter": {"include": ["E11"], "exclude": [], "expand": True},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["code"] for item in payload["codes"]] == ["E11.9"]
    assert [item["code"] for item in payload["codes"][0]["alternatives"]] == [
        "E11.8"
    ]
    assert payload["filter_applied"] == {
        "include": ["E11"],
        "exclude": [],
        "expand": True,
    }
    assert payload["raw_schema"]["secondary_diagnoses"][0]["code"] == "E11.9"
    assert "primary_diagnosis" not in payload["raw_schema"]
    filter_event = payload["trace_events"][-1]
    assert filter_event["step"] == "code_filter"
    assert filter_event["metadata"]["input_code_count"] == 4
    assert filter_event["metadata"]["returned_code_count"] == 1


@pytest.mark.asyncio
async def test_v1_filter_expand_false_uses_exact_matching(client, monkeypatch):
    from app.api import coding_predict as api_module

    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-filter-contract")
    monkeypatch.setattr(api_module, "get_dispatcher", lambda: _Dispatcher())

    response = await client.post(
        "/api/v1/coding/predict",
        json={
            "text": "患者有2型糖尿病史。",
            "filter": {"include": ["E11"], "expand": False},
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["codes"] == []
    assert payload["raw_schema"]["secondary_diagnoses"] == []


@pytest.mark.asyncio
async def test_v1_filter_rejects_unbounded_or_empty_entries(client):
    too_many = await client.post(
        "/api/v1/coding/predict",
        json={
            "text": "去标识病历",
            "filter": {"include": [f"A{index}" for index in range(101)]},
        },
    )
    empty = await client.post(
        "/api/v1/coding/predict",
        json={"text": "去标识病历", "filter": {"exclude": ["   "]}},
    )

    assert too_many.status_code == 422
    assert empty.status_code == 422


@pytest.mark.asyncio
async def test_v1_rejects_unknown_mode_and_coding_system_before_llm(client):
    unknown_mode = await client.post(
        "/api/v1/coding/predict",
        json={"text": "去标识病历", "mode": "unknown"},
    )
    unknown_system = await client.post(
        "/api/v1/coding/predict",
        json={"text": "去标识病历", "coding_system": "icd10"},
    )

    assert unknown_mode.status_code == 422
    assert unknown_system.status_code == 422


@pytest.mark.asyncio
async def test_v1_multi_system_projects_diagnoses_and_procedures(client, monkeypatch):
    from app.api import coding_predict as api_module

    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-system-contract")
    monkeypatch.setattr(api_module, "get_dispatcher", lambda: _Dispatcher())

    response = await client.post(
        "/api/v1/coding/predict",
        json={
            "text": "去标识病历",
            "coding_systems": ["icd10cn", "icd9cm3"],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["coding_systems_applied"] == ["icd10cn", "icd9cm3"]
    assert {item["system"] for item in payload["codes"]} == {
        "icd10cn",
        "icd9cm3",
    }
    assert len(payload["codes"]) == 4
    assert payload["raw_schema"]["primary_diagnosis"]["code"] == "S22.089A"
    assert payload["raw_schema"]["procedures"][0]["code"] == "81.62"
    system_event = next(
        event for event in payload["trace_events"]
        if event["step"] == "coding_system_projection"
    )
    assert system_event["metadata"]["systems"] == ["icd10cn", "icd9cm3"]


@pytest.mark.asyncio
async def test_v1_single_procedure_system_excludes_diagnoses_everywhere(
    client, monkeypatch
):
    from app.api import coding_predict as api_module

    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-system-contract")
    monkeypatch.setattr(api_module, "get_dispatcher", lambda: _Dispatcher())

    response = await client.post(
        "/api/v1/coding/predict",
        json={"text": "去标识病历", "coding_systems": ["icd9cm3"]},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [item["code"] for item in payload["codes"]] == ["81.62"]
    assert payload["codes"][0]["system"] == "icd9cm3"
    assert "primary_diagnosis" not in payload["raw_schema"]
    assert "secondary_diagnoses" not in payload["raw_schema"]
    assert payload["raw_schema"]["procedures"][0]["code"] == "81.62"


@pytest.mark.asyncio
async def test_v1_rejects_ambiguous_or_duplicate_system_selection(client):
    ambiguous = await client.post(
        "/api/v1/coding/predict",
        json={
            "text": "去标识病历",
            "coding_system": "icd10cn",
            "coding_systems": ["icd9cm3"],
        },
    )
    duplicate = await client.post(
        "/api/v1/coding/predict",
        json={
            "text": "去标识病历",
            "coding_systems": ["icd10cn", "icd10cn"],
        },
    )

    assert ambiguous.status_code == 422
    assert duplicate.status_code == 422


@pytest.mark.asyncio
async def test_v1_response_controls_scrub_raw_evidence_and_trace(client, monkeypatch):
    from app.api import coding_predict as api_module

    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-filter-contract")
    monkeypatch.setattr(api_module, "get_dispatcher", lambda: _Dispatcher())

    response = await client.post(
        "/api/v1/coding/predict",
        json={
            "text": "去标识病历",
            "include_evidence": False,
            "include_trace": False,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert all(item["evidence"] == "" for item in payload["codes"])
    assert payload["trace_events"] == []
    raw_text = str(payload["raw_schema"]).lower()
    assert "evidence" not in raw_text
    assert "trace" not in raw_text


def test_shared_filter_exclusion_wins_and_expand_is_explicit():
    assert code_allowed_by_filter(
        "E11.9", include=["E11"], exclude=["E11.9"], expand=True
    ) is False
    assert code_allowed_by_filter(
        "E11.9", include=["E11"], exclude=[], expand=True
    ) is True
    assert code_allowed_by_filter(
        "E11.9", include=["E11"], exclude=[], expand=False
    ) is False
