"""Phase 3-B2 Loop 3 — Markdown generator for MedicalCodingAgentOutputV2.

Renders the Corti-style 8-field output as a 6-section Markdown document
with tables, suitable for human review in a chat UI. Each section maps
to a Corti field group:

  1. Encounter Summary        (field 1)
  2. Documentation Analysis   (field 2 — 4 evidence buckets)
  3. Code Assignment          (field 3 — primary + secondary + procedures)
  4. Documentation Gaps &     (fields 4 + 5 — gaps + uncodable items)
     Uncodable Items
  5. Validation Summary       (field 6)
  6. Human Review & Trace     (fields 7 + 8 — review conclusion + run trace)

Contract: every section's table header is always rendered (even when the
section has zero rows), so a reviewer can see at a glance that a section
was processed but produced no items. This is the Loop 3 acceptance
criterion: "模板表头完整性".

Degradation: the generator is defensive — every field is read via
``.get(...)`` with defaults, so a partial v2 dict (or even an empty
dict) still produces a valid Markdown document, just with empty rows.
This lets the frontend fall back to "auto-generate Markdown from JSON"
when the backend didn't pre-render one (Loop 3 §3 降级处理).
"""
from __future__ import annotations

from typing import Any


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown table with the given headers and rows.

    Always emits the header + separator line, even when rows is empty,
    so consumers can verify template completeness (Loop 3 acceptance).
    """
    line1 = "| " + " | ".join(headers) + " |"
    line2 = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([line1, line2, *body])


def _cell(value: Any, fallback: str = "—") -> str:
    """Render any value as a Markdown cell. None / empty → fallback.

    Pipes (``|``) are always escaped to ``\\|`` so they don't break the
    table column layout. Newlines collapse to spaces for the same reason.
    """
    if value is None:
        return fallback
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, dict)):
        if not value:
            return fallback
        s = str(value)
    else:
        s = str(value).strip()
        if not s:
            return fallback
    return s.replace("|", "\\|").replace("\n", " ")


def _evidence_text(item: Any) -> str:
    """Extract the text field from an EvidenceSpan-shaped dict."""
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return item.get("text") or item.get("evidence_text") or "—"
    return "—"


def generate_markdown(v2: dict[str, Any]) -> str:
    """Render a MedicalCodingAgentOutputV2 dict as a 6-section Markdown doc.

    The input is the ``data`` payload from
    ``result.parts[0].data`` of the A2A response. The output is a single
    Markdown string with headers + tables for each of the 6 sections.
    """
    if not isinstance(v2, dict):
        return "# 医学编码智能体输出\n\n_No structured output available._"

    sections: list[str] = ["# 医学编码智能体输出"]

    # ── Section 1: Encounter Summary ──
    es = v2.get("encounter_summary") or {}
    sections.append("## 1. Encounter Summary")
    sections.append(_md_table(
        ["Field", "Value"],
        [
            ["Chief Complaint", _cell(es.get("chief_complaint"))],
            ["Treatment Course", _cell(es.get("treatment_course"))],
            ["Key Findings", _cell(es.get("key_findings"))],
            ["Document Sources", _cell(es.get("document_sources"))],
            ["Encounter Date", _cell(es.get("encounter_date"))],
        ],
    ))

    # ── Section 2: Documentation Analysis ──
    da = v2.get("documentation_analysis") or {}
    sections.append("## 2. Documentation Analysis")
    sections.append(_md_table(
        ["Evidence Bucket", "Count", "Sample Text"],
        [
            ["Diagnosis Evidence", _cell(len(da.get("diagnosis_evidence") or [])),
             _cell(_evidence_text((da.get("diagnosis_evidence") or [None])[0]) if da.get("diagnosis_evidence") else "—")],
            ["Procedure Evidence", _cell(len(da.get("procedure_evidence") or [])),
             _cell(_evidence_text((da.get("procedure_evidence") or [None])[0]) if da.get("procedure_evidence") else "—")],
            ["Negated Findings", _cell(len(da.get("negated_findings") or [])),
             _cell(_evidence_text((da.get("negated_findings") or [None])[0]) if da.get("negated_findings") else "—")],
            ["Historical Conditions", _cell(len(da.get("historical_conditions") or [])),
             _cell(_evidence_text((da.get("historical_conditions") or [None])[0]) if da.get("historical_conditions") else "—")],
        ],
    ))

    # ── Section 3: Code Assignment ──
    ca = v2.get("code_assignment") or {}
    primary = ca.get("primary_diagnosis") or {}
    secondary = ca.get("secondary_diagnoses") or []
    procedures = ca.get("procedures") or []
    sections.append("## 3. Code Assignment")
    sections.append("### Primary Diagnosis")
    sections.append(_md_table(
        ["Code", "Description", "Confidence", "Category", "Evidence"],
        [[
            _cell(primary.get("code")),
            _cell(primary.get("description")),
            _cell(primary.get("confidence")),
            _cell(primary.get("category")),
            _cell(len(primary.get("evidence") or [])),
        ]],
    ))
    sections.append("### Secondary Diagnoses")
    sections.append(_md_table(
        ["Code", "Description", "Confidence", "Category", "Evidence"],
        [
            [
                _cell(d.get("code") if isinstance(d, dict) else d),
                _cell(d.get("description") if isinstance(d, dict) else ""),
                _cell(d.get("confidence") if isinstance(d, dict) else ""),
                _cell(d.get("category") if isinstance(d, dict) else ""),
                _cell(len(d.get("evidence") or []) if isinstance(d, dict) else 0),
            ]
            for d in secondary
        ],
    ))
    sections.append("### Procedures")
    sections.append(_md_table(
        ["Code", "Description", "Confidence", "Category", "Evidence"],
        [
            [
                _cell(p.get("code") if isinstance(p, dict) else p),
                _cell(p.get("description") if isinstance(p, dict) else ""),
                _cell(p.get("confidence") if isinstance(p, dict) else ""),
                _cell(p.get("category") if isinstance(p, dict) else ""),
                _cell(len(p.get("evidence") or []) if isinstance(p, dict) else 0),
            ]
            for p in procedures
        ],
    ))

    # ── Section 4: Documentation Gaps & Uncodable Items ──
    gaps = v2.get("documentation_gaps") or []
    uncodable = v2.get("uncodable_items") or []
    sections.append("## 4. Documentation Gaps & Uncodable Items")
    sections.append("### Documentation Gaps")
    sections.append(_md_table(
        ["Gap Type", "Description", "Related Code", "Suggestion"],
        [
            [
                _cell(g.get("gap_type") if isinstance(g, dict) else g),
                _cell(g.get("description") if isinstance(g, dict) else ""),
                _cell(g.get("related_code") if isinstance(g, dict) else ""),
                _cell(g.get("suggestion") if isinstance(g, dict) else ""),
            ]
            for g in gaps
        ],
    ))
    sections.append("### Uncodable Items")
    sections.append(_md_table(
        ["Item Type", "Text", "Reason"],
        [
            [
                _cell(i.get("item_type") if isinstance(i, dict) else i),
                _cell(i.get("text") if isinstance(i, dict) else ""),
                _cell(i.get("reason") if isinstance(i, dict) else ""),
            ]
            for i in uncodable
        ],
    ))

    # ── Section 5: Validation Summary ──
    vs = v2.get("validation_summary") or {}
    issues = vs.get("issues_found") or []
    sections.append("## 5. Validation Summary")
    sections.append(_md_table(
        ["Passed", "Issues", "Manual Review Required", "Rule Set", "Fired Rules"],
        [[
            _cell(vs.get("passed")),
            _cell(len(issues)),
            _cell(vs.get("manual_review_required")),
            _cell(vs.get("rule_set")),
            _cell(", ".join(vs.get("fired_rules") or []) or "—"),
        ]],
    ))
    if issues:
        sections.append("### Issues Found")
        sections.append(_md_table(
            ["Code", "Severity", "Message", "Category"],
            [
                [
                    _cell(i.get("code") if isinstance(i, dict) else i),
                    _cell(i.get("severity") if isinstance(i, dict) else ""),
                    _cell(i.get("message") if isinstance(i, dict) else ""),
                    _cell(i.get("category") if isinstance(i, dict) else ""),
                ]
                for i in issues
            ],
        ))

    # ── Section 6: Human Review & Trace Refs ──
    hr = v2.get("human_review") or {}
    tr = v2.get("trace_refs") or {}
    sections.append("## 6. Human Review & Trace Refs")
    sections.append(_md_table(
        ["Review Conclusion", "Review Required", "Run ID", "Method", "Provider/Model"],
        [[
            _cell(hr.get("review_conclusion")),
            _cell(hr.get("review_required")),
            _cell(tr.get("run_id")),
            _cell(tr.get("method_id")),
            f"{_cell(tr.get('provider'))} / {_cell(tr.get('model'))}",
        ]],
    ))
    if hr.get("review_focus"):
        sections.append("### Review Focus")
        sections.append(_md_table(
            ["Item"],
            [[_cell(item)] for item in hr["review_focus"]],
        ))

    return "\n\n".join(sections) + "\n"


# ── Phase 3-D2 Task 4 — per-agent markdown generators ──────────────


def generate_code_validation_markdown(result: dict[str, Any]) -> str:
    """Render a CodeValidationOutput dict as a 5-section Markdown doc.

    Sections (per Phase 3-D2 PDF spec):
      1. Review Conclusion
      2. Fired Rules
      3. Issue Codes
      4. Modification Suggestions
      5. Manual Review Advice
    """
    if not isinstance(result, dict):
        return "# 编码校验智能体输出\n\n_No structured output available._"

    sections: list[str] = ["# 编码校验智能体输出"]

    # ── Section 1: Review Conclusion ──
    conclusion = result.get("review_conclusion") or "—"
    manual_review = result.get("manual_review_required")
    rule_set = result.get("rule_set") or "—"
    sections.append("## 1. Review Conclusion")
    sections.append(_md_table(
        ["Conclusion", "Manual Review Required", "Rule Set"],
        [[_cell(conclusion), _cell(manual_review), _cell(rule_set)]],
    ))

    # ── Section 2: Fired Rules ──
    fired = result.get("fired_rules") or []
    sections.append("## 2. Fired Rules")
    sections.append(_md_table(
        ["#", "Rule ID"],
        [[str(i + 1), _cell(r)] for i, r in enumerate(fired)] or [["—", "—"]],
    ))

    # ── Section 3: Issue Codes ──
    issues = result.get("issues_found") or []
    sections.append("## 3. Issue Codes")
    sections.append(_md_table(
        ["#", "Rule ID", "Severity", "Code", "Message"],
        [
            [
                str(idx + 1),
                _cell(iss.get("rule_id") if isinstance(iss, dict) else iss),
                _cell(iss.get("severity") if isinstance(iss, dict) else ""),
                _cell(iss.get("code") if isinstance(iss, dict) else ""),
                _cell(iss.get("message") if isinstance(iss, dict) else ""),
            ]
            for idx, iss in enumerate(issues)
        ],
    ))

    # ── Section 4: Modification Suggestions ──
    sections.append("## 4. Modification Suggestions")
    suggestions = [
        {
            "code": (iss.get("code") if isinstance(iss, dict) else "") or "—",
            "suggestion": (iss.get("suggestion") if isinstance(iss, dict) else "") or "—",
        }
        for iss in issues
        if isinstance(iss, dict) and iss.get("suggestion")
    ]
    sections.append(_md_table(
        ["#", "Code", "Suggestion"],
        [
            [str(i + 1), _cell(s["code"]), _cell(s["suggestion"])]
            for i, s in enumerate(suggestions)
        ],
    ))

    # ── Section 5: Manual Review Advice ──
    sections.append("## 5. Manual Review Advice")
    if manual_review:
        advice = (
            "该编码集存在 critical/high 级别问题或 review_conclusion=FAIL，"
            "建议人工复核后再行 DRG 分组。重点核查：主诊断是否完整、"
            "编码格式是否符合 ICD-10/ICD-9-CM-3 标准、是否存在重复编码、"
            "证据与编码的匹配度。"
        )
    else:
        advice = (
            "该编码集通过所有规则校验，可进入下一阶段（DRG 分组 / "
            "结算合规）。如有特殊场景，仍建议抽样复核。"
        )
    sections.append(advice)

    # Trace ref footer
    tr = result.get("trace_refs") or {}
    sections.append("---")
    sections.append(_md_table(
        ["Run ID", "Agent Ref"],
        [[_cell(tr.get("run_id")), _cell(tr.get("agent_ref"))]],
    ))

    return "\n\n".join(sections) + "\n"


def generate_compliance_guardrail_markdown(result: dict[str, Any]) -> str:
    """Render a ComplianceGuardrailOutput dict as a 5-section Markdown doc.

    Sections (per Phase 3-D2 PDF spec):
      1. Risk Conclusion
      2. DRG/DIP Sensitive Items
      3. Compliance Checks
      4. Risk Level
      5. Audit Advice
    """
    if not isinstance(result, dict):
        return "# 合规护栏智能体输出\n\n_No structured output available._"

    sections: list[str] = ["# 合规护栏智能体输出"]

    # ── Section 1: Risk Conclusion ──
    conclusion = result.get("review_conclusion") or "—"
    manual_review = result.get("manual_review_required")
    drg_suggestion = result.get("drg_suggestion") or "—"
    sections.append("## 1. Risk Conclusion")
    sections.append(_md_table(
        ["Conclusion", "Manual Review Required", "DRG Suggestion"],
        [[_cell(conclusion), _cell(manual_review), _cell(drg_suggestion)]],
    ))

    # ── Section 2: DRG/DIP Sensitive Items ──
    issues = result.get("issues_found") or []
    drg_dip_items = [
        iss for iss in issues
        if isinstance(iss, dict) and (
            "DRG" in (iss.get("message") or "")
            or "DIP" in (iss.get("message") or "")
            or "drg" in (iss.get("rule_id") or "").lower()
            or "dip" in (iss.get("rule_id") or "").lower()
            or iss.get("severity") in ("critical", "high")
        )
    ]
    sections.append("## 2. DRG/DIP Sensitive Items")
    sections.append(_md_table(
        ["#", "Rule ID", "Severity", "Code", "Message"],
        [
            [
                str(idx + 1),
                _cell(iss.get("rule_id")),
                _cell(iss.get("severity")),
                _cell(iss.get("code")),
                _cell(iss.get("message")),
            ]
            for idx, iss in enumerate(drg_dip_items)
        ],
    ))

    # ── Section 3: Compliance Checks ──
    checks = result.get("compliance_checks") or []
    sections.append("## 3. Compliance Checks")
    sections.append(_md_table(
        ["#", "Check ID", "Passed", "Severity", "Detail"],
        [
            [
                str(idx + 1),
                _cell(c.get("check_id") if isinstance(c, dict) else c),
                _cell(c.get("passed") if isinstance(c, dict) else ""),
                _cell(c.get("severity") if isinstance(c, dict) else ""),
                _cell(c.get("detail") if isinstance(c, dict) else ""),
            ]
            for idx, c in enumerate(checks)
        ],
    ))

    # ── Section 4: Risk Level ──
    if conclusion == "FAIL":
        risk_level = "HIGH"
    elif conclusion == "WARNING":
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    sections.append("## 4. Risk Level")
    sections.append(_md_table(
        ["Risk Level", "Issue Count", "Critical/High Count"],
        [[
            risk_level,
            _cell(len(issues)),
            _cell(len([i for i in issues if isinstance(i, dict) and i.get("severity") in ("critical", "high")])),
        ]],
    ))

    # ── Section 5: Audit Advice ──
    sections.append("## 5. Audit Advice")
    if manual_review:
        advice = (
            "存在 DRG/DIP 敏感风险项，建议提交审计部门复核。"
            "重点核查：高码权 DRG 跳跃、DIP 病种分值异常、"
            "主诊断与手术操作一致性、并发症对分组结果的影响。"
        )
    else:
        advice = (
            "未发现显著合规风险，可进入结算流程。建议定期抽查"
            "以确保持续合规。"
        )
    sections.append(advice)

    # Trace ref footer
    tr = result.get("trace_refs") or {}
    sections.append("---")
    sections.append(_md_table(
        ["Run ID", "Agent Ref"],
        [[_cell(tr.get("run_id")), _cell(tr.get("agent_ref"))]],
    ))

    return "\n\n".join(sections) + "\n"


def generate_note_completeness_markdown(result: dict[str, Any]) -> str:
    """Render a NoteCompletenessOutput dict as a 5-section Markdown doc.

    Sections (per Phase 3-D2 PDF spec):
      1. Completeness Score
      2. Missing Sections
      3. Present Sections
      4. Supplement Suggestions
      5. Coding/DRG/DIP Impact
    """
    if not isinstance(result, dict):
        return "# 病历完整性智能体输出\n\n_No structured output available._"

    sections: list[str] = ["# 病历完整性智能体输出"]

    # ── Section 1: Completeness Score ──
    score = result.get("completeness_score")
    conclusion = result.get("review_conclusion") or "—"
    manual_review = result.get("manual_review_required")
    is_surgical = result.get("is_surgical_case")
    sections.append("## 1. Completeness Score")
    sections.append(_md_table(
        ["Score", "Conclusion", "Manual Review Required", "Surgical Case"],
        [[
            _cell(f"{score:.1%}" if isinstance(score, (int, float)) else "—"),
            _cell(conclusion),
            _cell(manual_review),
            _cell(is_surgical),
        ]],
    ))

    # ── Section 2: Missing Sections ──
    missing = result.get("missing_sections") or []
    sections.append("## 2. Missing Sections")
    sections.append(_md_table(
        ["#", "Section"],
        [[str(i + 1), _cell(s)] for i, s in enumerate(missing)] or [["—", "—"]],
    ))

    # ── Section 3: Present Sections ──
    present = result.get("present_sections") or []
    sections.append("## 3. Present Sections")
    sections.append(_md_table(
        ["#", "Section"],
        [[str(i + 1), _cell(s)] for i, s in enumerate(present)] or [["—", "—"]],
    ))

    # ── Section 4: Supplement Suggestions ──
    gaps = result.get("documentation_gaps") or []
    sections.append("## 4. Supplement Suggestions")
    sections.append(_md_table(
        ["#", "Section", "Gap Type", "Suggestion"],
        [
            [
                str(idx + 1),
                _cell(g.get("section") if isinstance(g, dict) else ""),
                _cell(g.get("gap_type") if isinstance(g, dict) else ""),
                _cell(g.get("suggestion") if isinstance(g, dict) else ""),
            ]
            for idx, g in enumerate(gaps)
        ],
    ))

    # ── Section 5: Coding/DRG/DIP Impact ──
    sections.append("## 5. Coding/DRG/DIP Impact")
    if missing:
        impact = (
            f"病历缺少 {len(missing)} 个必填章节（"
            f"{', '.join(missing[:5])}{'...' if len(missing) > 5 else ''}"
            "），将影响：\n\n"
            "- 编码准确性：主诉/现病史缺失导致主诊断依据不足\n"
            "- DRG 分组：查体/诊断/手术章节缺失导致 ADRG 落入错误组\n"
            "- DIP 病种分值：辅助检查/治疗章节缺失导致核心病种识别失败\n"
            "- 合规审计：缺少必备章节可能触发医保稽核扣分\n\n"
            "**建议：退回主管医师补齐病历后再行编码。**"
        )
    else:
        impact = (
            "病历章节完整，对编码 / DRG / DIP 流程无阻断影响。"
            "可进入下一阶段。"
        )
    sections.append(impact)

    # Trace ref footer
    tr = result.get("trace_refs") or {}
    sections.append("---")
    sections.append(_md_table(
        ["Run ID", "Agent Ref"],
        [[_cell(tr.get("run_id")), _cell(tr.get("agent_ref"))]],
    ))

    return "\n\n".join(sections) + "\n"


def generate_markdown_for(agent_id: str, result: dict[str, Any]) -> str:
    """Dispatch to the per-agent markdown generator based on agent_id.

    Phase 3-D2 Task 4 — backend pre-renders markdown at agent-run time
    (matches the medical-coding-agent pattern via ``generate_markdown(v2)``).
    Frontend ``RenderedMarkdown`` parses markdown tables/headings — no
    frontend rendering change needed.
    """
    if agent_id == "code-validation-agent":
        return generate_code_validation_markdown(result)
    if agent_id == "compliance-guardrail-agent":
        return generate_compliance_guardrail_markdown(result)
    if agent_id == "note-completeness-agent":
        return generate_note_completeness_markdown(result)
    # Unknown agent_id — fall back to a generic JSON dump markdown
    return f"# Agent Output\n\n```json\n{_safe_json(result)}\n```"


def _safe_json(value: Any) -> str:
    """Render a value as JSON for the fallback markdown."""
    import json as _json
    try:
        return _json.dumps(value, ensure_ascii=False, indent=2)
    except Exception:
        return str(value)
