"""Unit tests for StructuredOutputProjector (Phase 5 Track C Gate 1).

Covers:
- JSON fence + bare JSON extraction
- Per-contract extractors (NoteCompleteness, DrgAnalyzer, Procedure,
  Discharge, etc.)
- Defensive behavior (empty input, parse errors never raise)
- Markdown-table fallback for note-completeness
"""

from __future__ import annotations

import pytest

from icoder_runtime.backends.structured_output_projector import (
    StructuredProjection,
    project,
    project_or_empty,
)


# ── Defensive behavior ─────────────────────────────────────────────────


def test_project_empty_markdown_returns_warnings():
    """Empty markdown should return an empty result with a warning."""
    proj = project("", "icoder/NoteCompleteness/v1", "test")
    assert proj.result == {}
    assert proj.extraction_method == "none"
    assert "empty markdown" in proj.parse_warnings


def test_project_unknown_contract_falls_back_to_json_block():
    """Unknown contract still extracts JSON block if present."""
    md = '```json\n{"foo": "bar"}\n```'
    proj = project(md, "icoder/Unknown/v1", "test")
    assert proj.result == {"foo": "bar"}
    assert proj.extraction_method == "json_block"


def test_project_never_raises_on_malformed_input():
    """Malformed markdown must not raise — returns empty + warnings."""
    proj = project("}{not valid json}{", "icoder/DrgAnalyzer/v1", "test")
    assert proj.result == {}
    assert proj.extraction_method in ("none", "section_header")


def test_project_or_empty_returns_dict():
    """project_or_empty convenience returns just the dict."""
    md = '```json\n{"risk_points": ["x"]}\n```'
    result = project_or_empty(md, "icoder/DrgAnalyzer/v1", "test")
    assert isinstance(result, dict)
    assert result.get("risk_points") == ["x"]


def test_project_does_not_mutate_input():
    """The input markdown must not be modified."""
    md = '```json\n{"a": 1}\n```'
    original = md
    project(md, "icoder/Unknown/v1", "test")
    assert md == original


# ── Per-contract extractors ─────────────────────────────────────────────


def test_drg_analyzer_json_block():
    md = """Here is the analysis:
```json
{
  "risk_points": [
    {"risk_type": "downcoding", "code": "J15.9", "severity": "high"}
  ],
  "drg_dip_rule_reservation_note": "考虑添加并发症编码"
}
```"""
    proj = project(md, "icoder/DrgAnalyzer/v1", "drg-analyzer")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["risk_points"]) == 1
    assert proj.result["risk_points"][0]["code"] == "J15.9"
    assert proj.result["drg_dip_rule_reservation_note"].startswith("考虑")


def test_note_completeness_markdown_table():
    """Note completeness fallback parses ❌ **缺失** table rows."""
    md = """### 评估
| 章节 | 状态 | 说明 |
| :--- | :--- | :--- |
| **主诉** | ❌ **缺失** | 未提供。 |
| **现病史** | ❌ **缺失** | 未提供。 |
| **诊断** | ⚠️ **部分缺失** | 提供了部分。 |

| 指标 | 值 |
| :--- | :--- |
| **Completeness Score** | **2 / 10** (20%) |
"""
    proj = project(md, "icoder/NoteCompleteness/v1", "note-completeness")
    assert "missing_fields" in proj.result
    assert "主诉" in proj.result["missing_fields"]
    assert "现病史" in proj.result["missing_fields"]
    assert "completeness_score" in proj.result
    assert proj.result["completeness_score"] == 2.0


def test_note_completeness_json_block():
    md = '```json\n{"missing_fields": ["主诉", "现病史"], "completeness_score": 0.5}\n```'
    proj = project(md, "icoder/NoteCompleteness/v1", "note-completeness")
    assert proj.extraction_method == "json_block"
    assert proj.result["missing_fields"] == ["主诉", "现病史"]
    assert proj.result["completeness_score"] == 0.5


def test_procedure_extractor_json_block():
    md = """```json
{
  "procedures": [
    {"text": "后路椎体成形术", "code": "81.6500"}
  ],
  "total_count": 1
}
```"""
    proj = project(md, "icoder/ProcedureExtractor/v1", "procedure-extractor")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["procedures"]) == 1
    assert proj.result["total_count"] == 1


def test_discharge_summary_bare_json():
    """Discharge summary accepts bare JSON envelope without fence."""
    md = """{
  "diagnoses": [
    {"text": "T12椎体压缩性骨折", "primary": true}
  ],
  "procedures": [
    {"text": "后路椎体成形术"}
  ],
  "treatment_summary": "术后恢复良好"
}"""
    proj = project(md, "icoder/DischargeSummary/v1", "discharge-summary-structuring")
    assert proj.extraction_method == "json_block"
    ss = proj.result["structured_sections"]
    assert "diagnoses" in ss
    assert "procedures" in ss
    assert ss["treatment_summary"].startswith("术后")


def test_compliance_guardrail_json_block():
    md = """```json
{
  "risk_points": ["x"],
  "violations": [{"rule": "R001"}],
  "risk_level": "high",
  "compliant": false
}
```"""
    proj = project(md, "icoder/ComplianceGuardrail/v1", "compliance-guardrail")
    assert proj.extraction_method == "json_block"
    assert proj.result["risk_level"] == "high"
    assert proj.result["compliant"] is False


def test_evidence_extractor_json_block():
    md = """```json
{
  "coded_evidence": [{"code": "I21.9", "strength": "high"}],
  "overall_strength": 0.85
}
```"""
    proj = project(md, "icoder/EvidenceExtractor/v1", "evidence-extractor")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["coded_evidence"]) == 1
    assert proj.result["overall_strength"] == 0.85


def test_principal_dx_json_block():
    md = """```json
{
  "principal_dx": "I21.9",
  "conflict": false,
  "rationale": "急性心梗为入院主因"
}
```"""
    proj = project(md, "icoder/PrincipalDxReview/v1", "principal-diagnosis-review")
    assert proj.extraction_method == "json_block"
    assert proj.result["principal_dx"] == "I21.9"
    assert proj.result["rationale"].startswith("急性")


def test_code_validation_json_block():
    md = """```json
{
  "validation_results": [{"code": "I21.19", "valid": true}],
  "overall_valid": true
}
```"""
    proj = project(md, "icoder/CodeValidation/v1", "code-validation-agent")
    assert proj.extraction_method == "json_block"
    assert proj.result["overall_valid"] is True


# ── Structural assertions ───────────────────────────────────────────────


def test_structured_projection_dataclass_defaults():
    sp = StructuredProjection(result={}, raw_markdown="x")
    assert sp.parse_warnings == []
    assert sp.contract == ""
    assert sp.extraction_method == "none"
