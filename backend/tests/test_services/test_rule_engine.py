# Tests for Rule Engine Service
import pytest
from app.services.rule_engine import RuleEngineService


@pytest.fixture
def service():
    return RuleEngineService()


@pytest.mark.asyncio
async def test_retrieve_rules_by_topic(service):
    results = await service.retrieve_rules("骨质疏松伴病理性骨折 主诊断选择")
    assert len(results) > 0
    # Should find relevant rules about main diagnosis selection
    assert any("主诊断" in r["title"] or "M80" in r["content"] for r in results)


@pytest.mark.asyncio
async def test_retrieve_rules_with_rule_sets(service):
    results = await service.retrieve_rules(
        "主要手术",
        rule_sets=["住院病案首页数据填写质量规范"],
    )
    assert len(results) > 0
    assert all(r["rule_set"] == "住院病案首页数据填写质量规范" for r in results)


@pytest.mark.asyncio
async def test_retrieve_rules_empty_topic(service):
    results = await service.retrieve_rules("")
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_get_all_rule_sets(service):
    sets = await service.get_all_rule_sets()
    assert len(sets) >= 6
    rule_set_names = [s["name"] for s in sets]
    assert "住院病案首页数据填写质量规范" in rule_set_names
    assert "ICD10编码规则" in rule_set_names


@pytest.mark.asyncio
async def test_check_code_against_rules(service):
    checks = await service.check_code_against_rules(
        "M80.900", "未特指骨质疏松伴病理性骨折", {}
    )
    assert len(checks) > 0
    # All checks should have required fields
    for c in checks:
        assert "rule_id" in c
        assert "status" in c
        assert "message" in c
