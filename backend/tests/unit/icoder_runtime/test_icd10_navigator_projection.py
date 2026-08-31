from __future__ import annotations

from icoder_runtime.backends.structured_output_projector import project


CONTRACT = "icoder/Icd10NavigatorOutput/v1"


def test_without_catalog_version_fails_closed() -> None:
    markdown = """```json
{
  "query_interpretation": "肾功能异常，病因及急慢性不明确",
  "index_terms": ["肾功能异常"],
  "candidate_codes": [{"code": "N19", "display": "unverified memory"}],
  "hierarchy_notes": [],
  "inclusion_exclusion_notes": [],
  "source_version": "未提供",
  "manual_review_required": false
}
```"""

    projection = project(markdown, CONTRACT, "icd10-navigator")

    assert projection.result["candidate_codes"] == []
    assert projection.result["hierarchy_notes"]
    assert projection.result["inclusion_exclusion_notes"]
    assert projection.result["manual_review_required"] is True
    assert "人工核对" in projection.result["inclusion_exclusion_notes"][0]


def test_verified_catalog_output_is_preserved() -> None:
    markdown = """{
  "query_interpretation": "verified input",
  "index_terms": ["term"],
  "candidate_codes": [{"code": "N18.3", "display": "verified"}],
  "hierarchy_notes": ["verified hierarchy"],
  "inclusion_exclusion_notes": ["verified note"],
  "source_version": "ICD-10-CN 2024 hospital catalog",
  "manual_review_required": true
}"""

    projection = project(markdown, CONTRACT, "icd10-navigator")

    assert projection.result["candidate_codes"][0]["code"] == "N18.3"
    assert projection.result["inclusion_exclusion_notes"] == ["verified note"]
