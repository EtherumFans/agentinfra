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
    # §7.6 contract: missing_sections + incomplete_sections (separate tiers).
    assert "missing_sections" in proj.result
    assert "主诉" in proj.result["missing_sections"]
    assert "现病史" in proj.result["missing_sections"]
    # "诊断" should be in incomplete_sections (部分缺失), not missing_sections.
    assert "诊断" not in proj.result["missing_sections"]
    assert any(s["section"] == "诊断" for s in proj.result.get("incomplete_sections", []))
    assert "completeness_score" in proj.result
    assert proj.result["completeness_score"] == 2.0


def test_note_completeness_json_block():
    md = """```json
{
  "required_sections": ["主诉","现病史","既往史"],
  "missing_sections": ["主诉", "现病史"],
  "incomplete_sections": [],
  "conflicts": [],
  "completeness_score": 0.33,
  "review_conclusion": "missing 2 of 3"
}
```"""
    proj = project(md, "icoder/NoteCompleteness/v1", "note-completeness")
    assert proj.extraction_method == "json_block"
    assert proj.result["missing_sections"] == ["主诉", "现病史"]
    assert proj.result["completeness_score"] == 0.33
    assert proj.result["review_conclusion"].startswith("missing")


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


# ── Phase 5 Track C Gate 2 contracts ────────────────────────────────────


def test_procedure_extractor_status_gate_split():
    """§7.3: status=performed → procedures; others → non_billable_mentions."""
    md = """```json
{
  "procedures": [
    {"code": "81.0100", "display": "椎体成形术", "status": "performed", "evidence_text": "行椎体成形术"},
    {"code": "00.00",   "display": "PCI",        "status": "planned",    "evidence_text": "拟行 PCI"}
  ],
  "non_billable_mentions": [],
  "manual_review_required": true
}
```"""
    proj = project(md, "icoder/ProcedureExtractor/v1", "procedure-extractor")
    assert proj.extraction_method == "json_block"
    # Only performed remains in procedures.
    assert len(proj.result["procedures"]) == 1
    assert proj.result["procedures"][0]["code"] == "81.0100"
    # PCI moved to non_billable_mentions.
    assert len(proj.result["non_billable_mentions"]) == 1
    assert proj.result["non_billable_mentions"][0]["status"] == "planned"
    assert proj.result["total_count"] == 1


def test_evidence_extractor_tier_classification():
    """§7.4 + §7.1: supported/uncertain/rejected tiers."""
    md = """```json
{
  "supported_codes": [
    {"code": "S22.000", "evidence_strength": "direct", "confidence": 0.92}
  ],
  "uncertain_candidates": [
    {"code": "J15.9", "evidence_strength": "suspected", "confidence": 0.5}
  ],
  "rejected_candidates": [
    {"code": "I50.9", "evidence_strength": "negated", "confidence": 0.1}
  ],
  "review_summary": "1 supported, 1 uncertain, 1 rejected"
}
```"""
    proj = project(md, "icoder/EvidenceExtractor/v1", "evidence-extractor")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["supported_codes"]) == 1
    assert len(proj.result["uncertain_candidates"]) == 1
    assert len(proj.result["rejected_candidates"]) == 1


def test_principal_dx_conflict_gate():
    """§7.5: coding_draft_consistent + manual_review_required."""
    md = """```json
{
  "candidates": [{"code": "S22.000", "recommended": true}],
  "recommended": {"code": "S22.000", "display": "T12 骨折"},
  "not_recommended": [{"code": "M80.900", "reason": "慢性合并症"}],
  "coding_draft_consistent": false,
  "conflict_reason": "draft=M80.900 but recommended=S22.000",
  "manual_review_required": true,
  "rationale": "S22.000 是主诊断因为..."
}
```"""
    proj = project(md, "icoder/PrincipalDxReview/v1", "principal-diagnosis-review")
    assert proj.extraction_method == "json_block"
    assert proj.result["coding_draft_consistent"] is False
    assert proj.result["manual_review_required"] is True
    assert "draft=M80.900" in proj.result["conflict_reason"]


def test_note_completeness_full_contract():
    """§7.6: full structured contract via JSON block."""
    md = """```json
{
  "required_sections": ["主诉","现病史","既往史","体格检查","辅助检查","诊断","治疗经过"],
  "present_sections": ["诊断","治疗经过"],
  "missing_sections": ["主诉","现病史","既往史","体格检查","辅助检查"],
  "incomplete_sections": [{"section": "诊断", "deficit_note": "缺少入院诊断与出院诊断区分"}],
  "conflicts": [],
  "completeness_score": 0.25,
  "review_conclusion": "病历严重不完整, 必填章节缺失 5/7。",
  "corrected_draft": ""
}
```"""
    proj = project(md, "icoder/NoteCompleteness/v1", "note-completeness")
    assert proj.extraction_method == "json_block"
    assert len(proj.result["required_sections"]) == 7
    assert len(proj.result["missing_sections"]) == 5
    assert proj.result["completeness_score"] == 0.25
    assert proj.result["review_conclusion"].startswith("病历严重不完整")
