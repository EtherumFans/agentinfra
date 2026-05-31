# Tests for Code Dictionary Service
import pytest
from app.services.code_dictionary import CodeDictionaryService


@pytest.fixture
def service():
    return CodeDictionaryService()


@pytest.mark.asyncio
async def test_search_codes_by_name(service):
    results = await service.search_codes("骨质疏松伴病理性骨折", "ICD10_CN")
    assert len(results) > 0
    assert any("M80" in r["code"] for r in results)


@pytest.mark.asyncio
async def test_search_codes_by_code(service):
    results = await service.search_codes("M80.900", "ICD10_CN")
    assert len(results) > 0
    assert results[0]["code"] == "M80.900"


@pytest.mark.asyncio
async def test_search_codes_empty_query(service):
    results = await service.search_codes("不存在的疾病名称xyz123", "ICD10_CN")
    # Should return results but with low scores
    assert isinstance(results, list)


@pytest.mark.asyncio
async def test_explore_code_found(service):
    result = await service.explore_code("M80.900", "ICD10_CN")
    assert result is not None
    assert result["code"] == "M80.900"
    assert "chapter" in result


@pytest.mark.asyncio
async def test_explore_code_not_found(service):
    result = await service.explore_code("Z99.999", "ICD10_CN")
    assert result is None


@pytest.mark.asyncio
async def test_validate_code_valid(service):
    result = await service.validate_code("M80.900", "ICD10_CN")
    assert result["valid"] is True
    assert result["code"] == "M80.900"


@pytest.mark.asyncio
async def test_validate_code_invalid(service):
    result = await service.validate_code("INVALID", "ICD10_CN")
    assert result["valid"] is False


@pytest.mark.asyncio
async def test_get_all_systems(service):
    systems = await service.get_all_systems()
    assert len(systems) >= 5
    system_ids = [s["id"] for s in systems]
    assert "ICD10_CN" in system_ids
    assert "ICD9_CM3" in system_ids


@pytest.mark.asyncio
async def test_search_procedure_codes(service):
    results = await service.search_codes("椎体", "ICD9_CM3")
    assert len(results) > 0
    assert any("80.99" in r["code"] for r in results) or any("81." in r["code"] for r in results)
