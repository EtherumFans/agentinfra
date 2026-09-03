from __future__ import annotations

from dataclasses import dataclass

import pytest

from official_agents.code_validation import catalog_validation as catalog


@dataclass(frozen=True)
class _Entry:
    code: str
    name_cn: str
    is_generated_category: bool = False


class _Loader:
    def __init__(self, entries: list[_Entry]) -> None:
        self._entries = {item.code: item for item in entries}

    def get(self, code: str):
        return self._entries.get(code)

    def all_codes(self):
        return list(self._entries.values())


def _governance(system: str) -> dict:
    return {
        "asset_id": (
            catalog.ICD9_ASSET_ID
            if system == "ICD-9-CM-3"
            else catalog.ICD10_ASSET_ID
        ),
        "version": "test-v1",
        "asset_type": "clinical_code_catalog",
        "jurisdiction": "CN_GENERIC_DEVELOPMENT",
        "authority_status": "source_unverified",
        "license_status": "external_review_required",
        "effective_from": None,
        "effective_to": None,
        "billing_authoritative": False,
        "manual_review_required": True,
        "use_restriction": "development_only",
    }


@pytest.fixture
def fake_catalogs(monkeypatch):
    icd10 = _Loader([
        _Entry("I50.900", "心力衰竭"),
        _Entry("I25", "慢性缺血性心脏病", True),
        _Entry("I25.100", "动脉粥样硬化性心脏病"),
        _Entry("E11.201+N08.3*", "2型糖尿病性肾病"),
    ])
    icd9 = _Loader([_Entry("81.0100", "寰枢椎融合")])

    def resolve(system: str):
        return _governance(system), icd9 if system == "ICD-9-CM-3" else icd10

    monkeypatch.setattr(catalog, "_governance_and_loader", resolve)
    return icd10, icd9


def test_text_extraction_keeps_compound_code_and_does_not_create_decimal_subcode():
    unique, duplicates = catalog.extract_code_requests(
        "待校验 E11.201+N08.3* 与 81.0100"
    )
    assert [(item.code, item.code_system) for item in unique] == [
        ("E11.201+N08.3*", "ICD-10-CN"),
        ("81.0100", "ICD-9-CM-3"),
    ]
    assert duplicates == []


def test_structured_extraction_preserves_role_system_and_duplicate_evidence():
    unique, duplicates = catalog.extract_code_requests(
        "ignored",
        structured_input={
            "primary_diagnosis": {"code": "i50.900"},
            "secondary_diagnoses": [{"code": "I50.900"}],
            "procedures": [{"code": "81.0100"}],
        },
    )
    assert [(item.code, item.code_system, item.role) for item in unique] == [
        ("I50.900", "ICD-10-CN", "primary"),
        ("81.0100", "ICD-9-CM-3", "procedure"),
    ]
    assert [item.code for item in duplicates] == ["I50.900"]


@pytest.mark.asyncio
async def test_local_baseline_distinguishes_assignable_category_and_unknown(
    fake_catalogs,
):
    result = await catalog.run_governed_catalog_validation(
        "待校验 I50.900、I25、Z99.99999",
        run_id="run-catalog",
    )
    assert result["review_conclusion"] == "FAIL"
    assert result["manual_review_required"] is True
    assert result["catalog_governance"]["integrity_verified"] is True
    by_code = {item["code"]: item for item in result["validated_codes"]}
    assert by_code["I50.900"]["status"] == "valid"
    assert by_code["I50.900"]["assignable"] is True
    assert by_code["I25"]["in_catalog"] is True
    assert by_code["I25"]["assignable"] is False
    assert by_code["Z99.99999"]["in_catalog"] is False
    assert all(
        issue["manual_review_required"] is True
        for issue in result["cross_code_issues"]
    )


@pytest.mark.asyncio
async def test_all_catalog_hits_still_warning_due_to_unverified_source(fake_catalogs):
    result = await catalog.run_governed_catalog_validation(
        "待校验 I50.900 与 E11.201+N08.3*",
    )
    assert result["review_conclusion"] == "WARNING"
    assert all(item["status"] == "valid" for item in result["validated_codes"])
    assert "source_unverified" in result["markdown"]
    assert "external_review_required" in result["markdown"]


@pytest.mark.asyncio
async def test_catalog_integrity_or_policy_failure_fails_closed(monkeypatch):
    def unavailable(_system: str):
        raise RuntimeError("tampered")

    monkeypatch.setattr(catalog, "_governance_and_loader", unavailable)
    result = await catalog.run_governed_catalog_validation("待校验 I50.900")
    assert result["review_conclusion"] == "FAIL"
    assert result["validated_codes"] == []
    assert result["runtime_mode"] == "catalog_governance_unavailable"
    assert result["catalog_governance"]["integrity_verified"] is False


@pytest.mark.asyncio
async def test_default_agent_path_never_calls_llm(monkeypatch, fake_catalogs):
    from official_agents.code_validation import agent

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("LLM path must not run by default")

    monkeypatch.setattr(agent, "run_llm_enhanced", forbidden)
    monkeypatch.delenv("ICODER_CODE_VALIDATION_ENABLE_LLM_SEMANTIC_ENHANCEMENT", raising=False)
    result = await agent.run("待校验 I50.900")
    assert result["runtime_mode"] == catalog.LOCAL_RUNTIME_MODE
    assert result["validated_codes"][0]["status"] == "valid"


@pytest.mark.asyncio
async def test_optional_llm_cannot_override_catalog_facts(monkeypatch, fake_catalogs):
    from official_agents.code_validation import agent

    async def enhanced(*_args, **_kwargs):
        return {
            "review_conclusion": "PASS",
            "validated_codes": [{
                "code": "Z99.99999",
                "status": "PASS",
                "in_catalog": True,
                "assignable": True,
                "catalog_name": "invented",
                "issue": "",
                "suggested_replacement": "",
            }],
            "cross_code_issues": [{
                "code": "Z99.99999",
                "issue": "model observation",
                "severity": "info",
                "manual_review_required": False,
            }],
            "manual_review_required": False,
            "summary": "model says pass",
            "markdown": "model output",
            "trace_refs": {"tool_calls_count": 2},
        }

    monkeypatch.setattr(agent, "run_llm_enhanced", enhanced)
    monkeypatch.setenv("ICODER_ALLOW_EXTERNAL_LLM", "true")
    monkeypatch.setenv("ICODER_CREDENTIAL_LLM", "test-placeholder-not-a-real-key")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    result = await agent.run(
        "待校验 Z99.99999",
        allow_semantic_enhancement=True,
    )
    validated = result["validated_codes"][0]
    assert validated["in_catalog"] is False
    assert validated["assignable"] is False
    assert validated["status"] == "invalid"
    assert result["review_conclusion"] == "FAIL"
    assert result["manual_review_required"] is True
    assert result["trace_refs"]["semantic_enhancement_used"] is True
