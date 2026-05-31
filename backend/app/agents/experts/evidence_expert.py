# iCoDer - Evidence Extraction Expert
import time
import json
from app.agents.base import BaseExpert

SYSTEM_PROMPT = """You are an expert clinical evidence extraction system for Chinese inpatient medical records.
Your task is to extract structured clinical facts from medical record text.

Extract the following entities:
1. **chief_complaint**: 主诉 (main reason for admission)
2. **diagnosis_facts**: List of diagnostic findings with:
   - finding: the clinical fact
   - body_site: anatomical location
   - etiology: cause/origin
   - negation: true if the finding is ruled out/denied
   - certainty: "confirmed", "probable", "suspected", or "ruled_out"
   - evidence_text: exact text from the record supporting this finding
3. **procedure_facts**: List of surgical/procedural facts with:
   - procedure_name: name of procedure
   - body_site: anatomical location
   - approach: surgical approach
   - device_material: implants, devices, materials used
   - evidence_text: exact text supporting this
4. **negated_findings**: findings explicitly ruled out
5. **timing_facts**: temporal information (duration, onset, course)
6. **documentation_overview**: summary of available documents

Output ONLY valid JSON. Do not add explanations outside the JSON."""


class EvidenceExtractionExpert(BaseExpert):
    name = "Evidence Extraction Expert"
    description = "Extracts clinical facts from medical records: diagnoses, procedures, anatomy, etiology, negation, timing"

    async def run(self, context: dict) -> dict:
        start = time.time()
        encounter_id = context.get("encounter_id", "unknown")
        self._log_step("extracting evidence", context)

        documents = context.get("documents", [])
        combined_text = self._build_combined_text(documents)

        schema_hint = """{
  "chief_complaint": "string",
  "diagnosis_facts": [
    {"finding": "...", "body_site": "...", "etiology": "...", "negation": false, "certainty": "confirmed|probable|suspected|ruled_out", "evidence_text": "..."}
  ],
  "procedure_facts": [
    {"procedure_name": "...", "body_site": "...", "approach": "...", "device_material": "...", "evidence_text": "..."}
  ],
  "negated_findings": ["..."],
  "timing_facts": {"onset": "...", "duration": "...", "course": "..."},
  "documentation_overview": {"doc_types": ["..."], "completeness": "complete|partial|minimal"}
}"""

        try:
            result = await self.llm.extract_json(
                "Extract all clinical facts from the following Chinese inpatient medical record. Output valid JSON only.",
                combined_text,
                schema_hint,
            )
        except Exception as e:
            self._log_step(f"LLM extraction failed: {e}", context)
            result = self._fallback_extraction(combined_text)

        return self._timed_result(start, {
            "expert": self.name,
            "evidence": {
                "chief_complaint": result.get("chief_complaint", ""),
                "diagnosis_facts": result.get("diagnosis_facts", []),
                "procedure_facts": result.get("procedure_facts", []),
                "negated_findings": result.get("negated_findings", []),
                "timing_facts": result.get("timing_facts", {}),
                "documentation_overview": result.get("documentation_overview", {}),
            },
            "raw_text_length": len(combined_text),
            "doc_count": len(documents),
        })

    def _build_combined_text(self, documents: list[dict]) -> str:
        parts = []
        for i, doc in enumerate(documents):
            doc_type = doc.get("doc_type", "unknown")
            title = doc.get("title", "")
            content = doc.get("content", "")
            parts.append(f"--- Document {i+1}: {doc_type} {title} ---\n{content}")
        return "\n\n".join(parts)

    def _fallback_extraction(self, text: str) -> dict:
        """Simple regex-based fallback when LLM is unavailable."""
        import re
        findings = []
        # Extract common diagnosis patterns
        diag_patterns = [
            (r"(出院诊断[：:]?\s*)([^\n]+)", "diagnosis_fact"),
            (r"(入院诊断[：:]?\s*)([^\n]+)", "diagnosis_fact"),
            (r"(主诉[：:]?\s*)([^\n]+)", "chief_complaint"),
        ]
        chief = ""
        for pattern, ptype in diag_patterns:
            m = re.search(pattern, text)
            if m:
                if ptype == "chief_complaint":
                    chief = m.group(2).strip()
                else:
                    diag_text = m.group(2).strip()
                    for d in re.split(r'[;；]', diag_text):
                        d = d.strip()
                        if d:
                            findings.append({
                                "finding": d,
                                "body_site": "",
                                "etiology": "",
                                "negation": False,
                                "certainty": "confirmed",
                                "evidence_text": d,
                            })

        return {
            "chief_complaint": chief,
            "diagnosis_facts": findings,
            "procedure_facts": [],
            "negated_findings": [],
            "timing_facts": {},
            "documentation_overview": {"doc_types": [], "completeness": "minimal"},
        }
