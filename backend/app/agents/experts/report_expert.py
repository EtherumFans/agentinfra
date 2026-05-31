# iCoDer - Report Generation Expert
import time
from datetime import datetime
from app.agents.base import BaseExpert
from jinja2 import Template

REPORT_TEMPLATE = """# Coding Review Report

**Review ID**: {{ review_id }}
**Generated**: {{ generated_at }}
**Agent Version**: {{ agent_version }}
**Model**: {{ model_used }}

---

## 1. Encounter Summary

| Field | Value |
|---|---|
| Patient ID | {{ encounter.patient_id }} |
| Department | {{ encounter.department }} |
| Admission | {{ encounter.admission_time or 'N/A' }} |
| Discharge | {{ encounter.discharge_time or 'N/A' }} |
| Chief Complaint | {{ chief_complaint }} |
| Documents Reviewed | {{ doc_count }} |

---

## 2. Existing Code Review

| Existing Code | Claimed Description | Agent Judgment | Evidence | Action |
|---|---|---|---|---|
{% for item in existing_diag_review %}
| {{ item.existing_code }} | {{ item.claimed_name }} | {{ item.agent_judgment }} | {{ item.evidence_found[:60] if item.evidence_found else 'None' }} | {{ 'Confirm' if item.agent_judgment == 'supported' else 'Review' }} |
{% endfor %}
{% for item in existing_proc_review %}
| {{ item.existing_code }} | {{ item.claimed_name }} | {{ item.agent_judgment }} | {{ item.evidence_found[:60] if item.evidence_found else 'None' }} | {{ 'Confirm' if item.agent_judgment == 'supported' else 'Review' }} |
{% endfor %}

---

## 3. Diagnosis and Finding Analysis

| Finding | Documentation Evidence | Suggested Code | Status | Confidence |
|---|---|---|---|---|
{% for c in diagnosis_candidates %}
| {{ c.finding }} | {{ c.evidence_text[:80] if c.evidence_text else 'No evidence' }} | {{ c.code }} {{ c.name }} | {{ c.status if c.status else 'proposed' }} | {{ '%.2f' % c.score }} |
{% endfor %}

---

## 4. Procedure and Service Analysis

| Procedure | Documentation Evidence | Suggested Code | Status | Confidence |
|---|---|---|---|---|
{% for c in procedure_candidates %}
| {{ c.get('procedure_name', c.get('finding', '')) }} | {{ c.evidence_text[:80] if c.evidence_text else 'No evidence' }} | {{ c.code }} {{ c.name }} | {{ c.status if c.status else 'proposed' }} | {{ '%.2f' % c.score }} |
{% endfor %}

---

## 5. Recommended Code Assignment

### Primary Diagnosis
- **Code**: {{ primary_diag.code if primary_diag else 'Not determined' }}
- **Description**: {{ primary_diag.name if primary_diag else '' }}
- **Rationale**: {{ primary_diag.rationale if primary_diag else '' }}
- **Evidence**: {{ primary_diag.evidence_text if primary_diag else '' }}

### Secondary Diagnoses
{% for sd in secondary_diag %}
- **{{ sd.code }}** {{ sd.name }} (Confidence: {{ '%.2f' % sd.score }}) — {{ sd.evidence_text[:80] }}
{% endfor %}

### Main Procedure
- **Code**: {{ main_proc.code if main_proc else 'Not determined' }}
- **Description**: {{ main_proc.name if main_proc else '' }}
- **Rationale**: {{ main_proc.rationale if main_proc else '' }}
- **Evidence**: {{ main_proc.evidence_text if main_proc else '' }}

### Other Procedures
{% for op in other_proc %}
- **{{ op.code }}** {{ op.name }} (Confidence: {{ '%.2f' % op.score }}) — {{ op.evidence_text[:80] }}
{% endfor %}

---

## 5b. Coding Trace (Index Navigation → Code Selection)

_Each code shows the path through the ICD index: from the main index term → sub-entry → final code, following the "Code Like Humans" methodology._

{% for c in diagnosis_candidates %}
{% if c.coding_trace %}
### {{ c.code }} — {{ c.name }}

| Step | Description |
|---|---|
| Finding | {{ c.finding }} |
{% if c.coding_trace.phase_b_index %}
| Index Main Term | {{ c.coding_trace.phase_b_index.main_term }} ({{ c.coding_trace.phase_b_index.match_count }} matches) |
{% endif %}
{% if c.coding_trace.phase_c_drill %}
{% for drill in c.coding_trace.phase_c_drill[:1] %}
| Drill-down Parent | {{ drill.parent }} ({{ drill.sub_count }} sub-codes available) |
{% if drill.top_sub %}
| Top Sub-codes | {% for sub in drill.top_sub %}{{ sub.code }} {{ sub.name }}; {% endfor %} |
{% endif %}
{% endfor %}
{% endif %}
{% if c.coding_trace.phase_d_selection %}
| Final Selection | {{ c.coding_trace.phase_d_selection.code }} |
| Rationale | {{ c.coding_trace.phase_d_selection.rationale }} |
| Specificity | {{ c.coding_trace.phase_d_selection.specificity }} |
{% endif %}
| Evidence | {{ c.evidence_text[:120] if c.evidence_text else 'No evidence bound' }} |

{% endif %}
{% endfor %}

{% for c in procedure_candidates %}
{% if c.coding_trace %}
### {{ c.code }} — {{ c.name }}

| Step | Description |
|---|---|
| Procedure | {{ c.procedure_name }} |
{% if c.coding_trace.phase_b_index %}
| Index Main Term | {{ c.coding_trace.phase_b_index.main_term }} ({{ c.coding_trace.phase_b_index.match_count }} matches) |
{% endif %}
{% if c.coding_trace.phase_c_drill %}
{% for drill in c.coding_trace.phase_c_drill[:1] %}
| Drill-down Parent | {{ drill.parent }} ({{ drill.sub_count }} sub-codes available) |
{% endfor %}
{% endif %}
{% if c.coding_trace.phase_d_selection %}
| Final Selection | {{ c.coding_trace.phase_d_selection.code }} |
| Rationale | {{ c.coding_trace.phase_d_selection.rationale }} |
| Approach Match | {{ c.coding_trace.phase_d_selection.approach_match }} |
{% endif %}
| Evidence | {{ c.evidence_text[:120] if c.evidence_text else 'No evidence bound' }} |

{% endif %}
{% endfor %}

---

## 6. Documentation Gaps

{% if documentation_gaps %}
{% for gap in documentation_gaps %}
- **[{{ gap.severity }}] {{ gap.type }}**: {{ gap.description }}
  - Suggestion: {{ gap.suggestion }}
{% endfor %}
{% else %}
No significant documentation gaps identified.
{% endif %}

---

## 7. Uncodable or Should-Not-Code Items

{% if uncodable_items %}
{% for item in uncodable_items %}
- **{{ item.finding }}**: {{ item.reason }} (Evidence: {{ item.evidence_text[:80] }})
{% endfor %}
{% else %}
No uncodable items identified.
{% endif %}

---

## 8. DRG/DIP or Payment Impact

{% if drg_risks %}
{% for risk in drg_risks %}
- **[{{ risk.severity }}] {{ risk.type }}**: {{ risk.description }}
{% endfor %}
{% endif %}

{% if drg_recommendations %}
{% for rec in drg_recommendations %}
- {{ rec }}
{% endfor %}
{% endif %}

**Estimated DRG Group**: {{ estimated_group.group if estimated_group else 'N/A' }}

---

## 9. Human Review Checklist

{% if human_checklist %}
{% for item in human_checklist %}
- [ ] {{ item }}
{% endfor %}
{% endif %}
- [ ] Confirm primary diagnosis selection
- [ ] Verify evidence spans for each supported code
- [ ] Review codes marked "needs_review"
- [ ] Address documentation gaps before finalizing
- [ ] Confirm DRG/DIP impact assessment

---

## 10. Validation Summary

| Category | Count |
|---|---|
| Supported Codes | {{ validation.supported }} |
| Needs Review | {{ validation.needs_review }} |
| Unsupported Codes | {{ validation.unsupported }} |
| Documentation Gaps | {{ doc_gap_count }} |
| DRG Risks | {{ drg_risk_count }} |
| Overall Confidence | {{ '%.1f%%' % (validation.evidence_binding_rate * 100) }} |

---

*Report generated by iCoDer Medical Coding Agent V{{ agent_version }}. All conclusions require human review before clinical use.*
"""


class ReportExpert(BaseExpert):
    name = "Report Expert"
    description = "Generates structured Coding Review Report in Markdown and HTML"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("generating report", context)

        encounter = context.get("encounter", {})
        evidence = context.get("evidence", {})
        primary_diag = context.get("primary_diagnosis", {})
        main_proc = context.get("main_procedure", {})
        diagnosis_candidates = context.get("diagnosis_candidates", [])
        procedure_candidates = context.get("procedure_candidates", [])
        existing_diag_review = context.get("existing_diagnosis_review", [])
        existing_proc_review = context.get("existing_procedure_review", [])
        secondary_diag = context.get("secondary_diagnoses", [])
        other_proc = context.get("other_procedures", [])
        documentation_gaps = context.get("documentation_gaps", [])
        drg_result = context.get("drg_impact", {})
        verification = context.get("verification", {})
        verification_summary = verification.get("summary", {"supported": 0, "needs_review": 0, "unsupported": 0, "evidence_binding_rate": 0})

        # Generate human checklist
        human_checklist = []
        for c in diagnosis_candidates + procedure_candidates:
            if c.get("certainty") == "suspected":
                human_checklist.append(f"Confirm finding: {c.get('finding', '')} (currently suspected)")
            if c.get("score", 0) < 0.7:
                human_checklist.append(f"Low confidence code ({c.get('score', 0):.2f}): {c.get('code', '')} {c.get('name', '')}")
        for gap in documentation_gaps:
            if gap.get("severity") == "high":
                human_checklist.append(f"CRITICAL: {gap.get('description', '')}")

        # Identify uncodable items from triage data in candidates
        uncodable_items = []
        for c in diagnosis_candidates + procedure_candidates:
            if c.get("certainty") == "ruled_out":
                uncodable_items.append({
                    "finding": c.get("finding", ""),
                    "reason": "Finding ruled out in documentation.",
                    "evidence_text": c.get("evidence_text", ""),
                })
            if c.get("certainty") == "history":
                uncodable_items.append({
                    "finding": c.get("finding", ""),
                    "reason": "Past history — coded as Z-prefix for personal history.",
                    "evidence_text": c.get("evidence_text", ""),
                })
            if c.get("specificity_level") == "unspecified(.9)":
                uncodable_items.append({
                    "finding": c.get("finding", ""),
                    "reason": f".9 unspecified code used: {c.get('code', '')} — clinical documentation may support more specific coding.",
                    "evidence_text": c.get("evidence_text", ""),
                })

        # Assign status to candidates
        for c in diagnosis_candidates:
            for v in verification.get("verifications", []):
                if v.get("code") == c.get("code"):
                    c["status"] = v.get("status", "proposed")
        for c in procedure_candidates:
            for v in verification.get("verifications", []):
                if v.get("code") == c.get("code"):
                    c["status"] = v.get("status", "proposed")

        template = Template(REPORT_TEMPLATE)
        markdown = template.render(
            review_id=context.get("review_id", "PENDING"),
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            agent_version=context.get("agent_version", "1.0.0"),
            model_used=context.get("model_used", ""),
            encounter=encounter,
            chief_complaint=evidence.get("chief_complaint", ""),
            doc_count=len(encounter.get("documents", [])),
            existing_diag_review=existing_diag_review,
            existing_proc_review=existing_proc_review,
            diagnosis_candidates=diagnosis_candidates,
            procedure_candidates=procedure_candidates,
            primary_diag=primary_diag if isinstance(primary_diag, dict) else {},
            secondary_diag=secondary_diag,
            main_proc=main_proc if isinstance(main_proc, dict) else {},
            other_proc=other_proc,
            documentation_gaps=documentation_gaps,
            uncodable_items=uncodable_items,
            drg_risks=drg_result.get("drg_risks", []),
            drg_recommendations=drg_result.get("recommendations", []),
            estimated_group=drg_result.get("potential_group", {}),
            human_checklist=human_checklist,
            validation=verification_summary,
            doc_gap_count=len(documentation_gaps),
            drg_risk_count=len(drg_result.get("drg_risks", [])),
        )

        # Simple HTML conversion
        html = self._markdown_to_html(markdown)

        return self._timed_result(start, {
            "expert": self.name,
            "report_markdown": markdown,
            "report_html": html,
            "uncodable_items": uncodable_items,
            "human_checklist": human_checklist,
        })

    def _markdown_to_html(self, md: str) -> str:
        """Basic markdown to HTML conversion."""
        import re
        html = md
        # Headers
        html = re.sub(r'^#### (.+)$', r'<h4>\1</h4>', html, flags=re.MULTILINE)
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        # Bold
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)
        # Separator
        html = html.replace('---', '<hr>')
        # Tables (simple)
        html = '<div class="report-content">\n' + html + '\n</div>'
        return html
