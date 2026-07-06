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
        return "# Medical Coding Agent Output\n\n_No structured output available._"

    sections: list[str] = ["# Medical Coding Agent Output"]

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
