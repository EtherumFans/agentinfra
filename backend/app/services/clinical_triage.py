# iCoDer - Clinical Significance Triage
# iCoDer "Code Like Humans" Step 1: classify each fact by clinical significance
# before any code lookup. This prevents coding ruled-out conditions,
# family history, or incidental imaging findings.
import logging
import re
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

CATEGORIES = ["codable", "history_of", "family_history", "ruled_out", "incidental"]

RULED_OUT_PATTERNS = [
    r"否认", r"排除", r"未见明显", r"未见异常", r"无异常",
    r"不考虑", r"可排除", r"已排除", r"已愈", r"无.*证据",
    r"不提示", r"不支持",
]

PAST_HISTORY_PATTERNS = [
    r"既往史", r"既往有", r"曾有", r".*病史", r".*术后",
    r"陈旧性", r"既往诊断", r".*年前.*诊断",
]

FAMILY_HISTORY_PATTERNS = [
    r"家族史", r"遗传", r"亲属.*患", r"家系", r"父母.*有",
    r"家族性",
]

INCIDENTAL_PATTERNS = [
    r"影像.*提示", r"CT.*示", r"MRI.*示", r"B超.*示",
    r"偶然发现", r"附见", r"附带",
]


class ClinicalTriageService:
    """Classify each clinical fact by coding significance.

    Categories:
    - codable: current history, should be coded
    - history_of: past medical history, code as Z-prefix
    - family_history: family history, code as Z80-Z84
    - ruled_out: explicitly excluded, do NOT code
    - incidental: imaging-only finding without clinical diagnosis, do NOT code
    """

    def triage_fact(self, fact: dict, context: dict) -> dict:
        """Classify a single fact using deterministic rules.

        Returns the fact dict with added 'clinical_significance', 'triage_reason',
        and 'triage_confidence' keys.
        """
        finding = fact.get("finding", "")
        body_site = fact.get("body_site", "")
        etiology = fact.get("etiology", "")
        evidence_text = fact.get("evidence_text", "")
        negation = fact.get("negation", False)
        certainty = fact.get("certainty", "")
        combined = f"{finding} {body_site} {etiology} {evidence_text}"

        result = dict(fact)
        result["clinical_significance"] = "codable"
        result["triage_reason"] = ""
        result["triage_confidence"] = 0.5

        # Rule 1: Explicit negation flags
        if negation or certainty == "ruled_out":
            result["clinical_significance"] = "ruled_out"
            result["triage_reason"] = "fact is negated or ruled out"
            result["triage_confidence"] = 0.95
            return result

        # Rule 2: Ruled-out language patterns
        for pattern in RULED_OUT_PATTERNS:
            if re.search(pattern, combined):
                result["clinical_significance"] = "ruled_out"
                result["triage_reason"] = f"ruled-out pattern matched: {pattern}"
                result["triage_confidence"] = 0.85
                return result

        # Rule 3: Family history patterns
        for pattern in FAMILY_HISTORY_PATTERNS:
            if re.search(pattern, combined):
                result["clinical_significance"] = "family_history"
                result["triage_reason"] = f"family history pattern matched: {pattern}"
                result["triage_confidence"] = 0.85
                return result

        # Rule 4: Past history patterns
        for pattern in PAST_HISTORY_PATTERNS:
            if re.search(pattern, combined):
                result["clinical_significance"] = "history_of"
                result["triage_reason"] = f"past history pattern matched: {pattern}"
                result["triage_confidence"] = 0.80
                return result

        # Rule 5: Imaging-only incidental findings
        imaging_hits = sum(1 for p in INCIDENTAL_PATTERNS if re.search(p, combined))
        # Check if there's a clinical diagnosis backing the finding
        has_clinical_diag = bool(
            re.search(r"(出院诊断|入院诊断|临床诊断|确诊|明确诊断)", context.get("full_text", ""))
            and finding in context.get("full_text", "")
        )
        if imaging_hits >= 1 and not has_clinical_diag:
            result["clinical_significance"] = "incidental"
            result["triage_reason"] = "imaging-only finding without clinical confirmation"
            result["triage_confidence"] = 0.70
            return result

        # Default: codable
        result["triage_reason"] = "appears to be current history finding"
        result["triage_confidence"] = 0.60
        return result

    def triage_all(self, evidence: dict, context: dict) -> dict:
        """Classify all diagnosis and procedure facts from evidence output.

        Args:
            evidence: output from EvidenceExtractionExpert
            context: additional context (full_text, admission_reason, etc.)

        Returns:
            dict with 'diagnosis_facts_triaged', 'procedure_facts_triaged',
            and summary counts.
        """
        diagnosis_facts = evidence.get("diagnosis_facts", [])
        procedure_facts = evidence.get("procedure_facts", [])

        triaged_diag = [self.triage_fact(f, context) for f in diagnosis_facts]
        triaged_proc = [self.triage_fact(f, context) for f in procedure_facts]

        counts = {cat: 0 for cat in CATEGORIES}
        for f in triaged_diag:
            counts[f["clinical_significance"]] = counts.get(f["clinical_significance"], 0) + 1
        proc_counts = {cat: 0 for cat in CATEGORIES}
        for f in triaged_proc:
            proc_counts[f["clinical_significance"]] = proc_counts.get(f["clinical_significance"], 0) + 1

        logger.info(
            "Triage complete: diag=%s, proc=%s",
            {k: v for k, v in counts.items() if v > 0},
            {k: v for k, v in proc_counts.items() if v > 0},
        )

        return {
            "diagnosis_facts_triaged": triaged_diag,
            "procedure_facts_triaged": triaged_proc,
            "diagnosis_summary": counts,
            "procedure_summary": proc_counts,
            "codable_diagnosis_facts": [f for f in triaged_diag if f["clinical_significance"] == "codable"],
            "codable_procedure_facts": [f for f in triaged_proc if f["clinical_significance"] == "codable"],
            "history_facts": [f for f in triaged_diag if f["clinical_significance"] == "history_of"],
            "ruled_out_facts": [f for f in triaged_diag if f["clinical_significance"] == "ruled_out"],
            "incidental_facts": [f for f in triaged_diag if f["clinical_significance"] == "incidental"],
        }

    async def triage_ambiguous_llm(self, facts: list[dict], context: dict) -> list[dict]:
        """For facts with low deterministic confidence, use LLM to re-classify.

        Only called for facts where triage_confidence < 0.75.
        """
        low_conf = [f for f in facts if f.get("triage_confidence", 0) < 0.75]
        if not low_conf:
            return facts

        prompt = f"""Classify each clinical finding into one of:
- codable: part of the current illness, should be coded
- history_of: past medical history (code as Z prefix)
- family_history: family history (code as Z80-Z84)
- ruled_out: explicitly excluded, do NOT code
- incidental: imaging-only finding, do NOT code

Medical record context: {context.get('admission_reason', '')}

Findings to classify:
{chr(10).join(f'{i+1}. finding={f["finding"]}, evidence="{f.get("evidence_text","")}", certainty={f.get("certainty","")}'
             for i, f in enumerate(low_conf))}

Return JSON: {{"results": [{{"index": 0, "clinical_significance": "...", "reason": "..."}}]}}"""

        try:
            result = await llm_service.extract_json(prompt, "", None)
            corrections = {r["index"]: r for r in result.get("results", [])}

            for i, f in enumerate(low_conf):
                if i in corrections:
                    f["clinical_significance"] = corrections[i]["clinical_significance"]
                    f["triage_reason"] = corrections[i]["reason"]
                    f["triage_confidence"] = 0.90
        except Exception as e:
            logger.warning("LLM triage failed, keeping deterministic results: %s", e)

        return facts


clinical_triage_service = ClinicalTriageService()
