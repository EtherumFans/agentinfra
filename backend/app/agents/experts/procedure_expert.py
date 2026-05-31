# iCoDer - Procedure Coding Expert (ICD-9-CM-3)
# Implements iCoDer "Code Like Humans" methodology adapted for procedure codes:
# Phase A: Triage (filter non-codable proc facts)
# Phase B: ICD-9-CM-3 Index Navigation
# Phase C: Specificity drill-down (approach, laterality, device)
# Phase D: Evidence Binding + Audit Trail
import time
import json
from app.agents.base import BaseExpert
from app.services.code_dictionary import code_dict_service
from app.services.clinical_triage import clinical_triage_service

SYSTEM_PROMPT_NAVIGATOR = """You are an ICD-9-CM-3 procedure code navigator for Chinese inpatient records.
Your job is to browse the ICD-9-CM-3 index to find the most specific procedure code.

Navigation steps:
1. Identify the main procedure term from the clinical description
2. Browse index entries to find matching procedure categories
3. Refine by approach (endoscopic/open/percutaneous), body site, and device
4. Check sub-entries for more specific variants (e.g., with/without implant)
5. Select the most specific code matching the procedure description

Key ICD-9-CM-3 principles:
- Bilateral procedures are coded separately when applicable
- Radical/definitive procedures take priority over exploratory
- Endoscopic approach codes differ from open approach codes
- Device/material (e.g., drug-eluting vs bare-metal stent) affects code selection
- Percutaneous vertebral augmentation codes differ by level count

Output valid JSON only."""

SYSTEM_PROMPT_SELECTOR = """You are a procedure code selector. Given ICD-9-CM-3 index navigation
results, select the best code for the procedure described.

Rules:
1. Match the approach first (endoscopic=54.21 vs open=54.11 for laparoscopy/laparotomy)
2. Match the body site
3. Match device/material if specified (drug-eluting stent vs bare-metal)
4. Select the MOST SPECIFIC code that the procedure documentation supports
5. If documentation lacks approach/site detail, flag it
6. Cite the evidence text

Output valid JSON only."""


class ProcedureCodingExpert(BaseExpert):
    name = "Procedure Coding Expert"
    description = "Generates ICD-9-CM-3 procedure code candidates using Code Like Humans 4-step method"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("code-like-humans procedure coding", context)

        evidence = context.get("evidence", {})
        all_procedure_facts = evidence.get("procedure_facts", [])

        # ---- Phase A: Triage ----
        # Use pre-triaged data from orchestrator if available
        if "codable_procedure_facts" in context:
            codable_procs = context["codable_procedure_facts"]
            self._log_step(
                f"using pre-triaged: {len(codable_procs)} codable procedures",
                context,
            )
        else:
            full_text = self._build_full_text(context)
            triage_result = clinical_triage_service.triage_all(
                evidence,
                {"full_text": full_text, "admission_reason": context.get("admission_reason", "")},
            )
            codable_procs = triage_result["codable_procedure_facts"]
            self._log_step(
                f"triage: {len(codable_procs)} codable procedures, "
                f"{len(triage_result['ruled_out_facts'])} ruled_out",
                context,
            )

        # ---- Phase B & C: Index Navigation + Drill-down ----
        candidates = []

        for fact in codable_procs:
            proc_name = fact.get("procedure_name", "")
            if not proc_name:
                continue

            trace = {
                "procedure_name": proc_name,
                "phase_b_index": None,
                "phase_c_drill": None,
                "phase_d_selection": None,
            }

            # Phase B: ICD-9-CM-3 Index Navigation
            index_result = await code_dict_service.lookup_index(proc_name, "ICD9_CM3")
            trace["phase_b_index"] = {
                "main_term": index_result.get("main_term"),
                "match_count": index_result.get("match_count"),
                "top_path": [e for e in index_result.get("entries", [])[:5]],
            }

            # Phase C: For top matches, drill down considering approach/site/device
            search_results = index_result.get("search_path", [])
            drill_results = []
            for sr in search_results[:3]:
                drill = await code_dict_service.drill_down(
                    sr["code"], "ICD9_CM3",
                    clinical_context={
                        "procedure_name": proc_name,
                        "body_site": fact.get("body_site", ""),
                        "approach": fact.get("approach", ""),
                        "device_material": fact.get("device_material", ""),
                    },
                )
                drill_results.append(drill)
            trace["phase_c_drill"] = [
                {"parent": d["parent_code"], "sub_count": d["sub_code_count"],
                 "top_sub": d["sub_codes"][:3] if d["sub_codes"] else []}
                for d in drill_results
            ]

            # Phase D: Code Selection
            try:
                selection_input = {
                    "procedure_name": proc_name,
                    "body_site": fact.get("body_site", ""),
                    "approach": fact.get("approach", ""),
                    "device_material": fact.get("device_material", ""),
                    "evidence_text": fact.get("evidence_text", ""),
                    "index_navigation": {
                        "entries": index_result.get("entries", [])[:15],
                        "cross_refs": index_result.get("cross_references", []),
                    },
                    "drill_options": [
                        {
                            "parent_code": d["parent_code"],
                            "parent_name": d["parent_name"],
                            "sub_codes": d["sub_codes"][:5],
                            "specificity_gains": d["specificity_gains"][:5],
                        }
                        for d in drill_results
                    ],
                }

                llm_result = await self.llm.extract_json(
                    f"""Select the best ICD-9-CM-3 code for this procedure.

Procedure: {proc_name}
Body site: {fact.get('body_site', '')}
Approach: {fact.get('approach', '')}
Device/Material: {fact.get('device_material', '')}
Evidence: {fact.get('evidence_text', '')}

Index entries:
{json.dumps(selection_input['index_navigation']['entries'][:12], ensure_ascii=False)}

Drill-down options:
{json.dumps(selection_input['drill_options'][:3], ensure_ascii=False)}

Return JSON:
{{
  "recommended_code": "00.00",
  "recommended_name": "...",
  "rationale": "Index main_term=... → sub_entry=... → final_code=...",
  "confidence": 0.0,
  "approach_match": "exact|partial|missing",
  "issues": ["..."],
  "alternative_codes": [{{"code": "...", "name": "...", "reason": "..."}}]
}}""",
                    json.dumps(selection_input, ensure_ascii=False),
                )

                trace["phase_d_selection"] = {
                    "code": llm_result.get("recommended_code", ""),
                    "rationale": llm_result.get("rationale", ""),
                    "approach_match": llm_result.get("approach_match", ""),
                }

                candidates.append({
                    "procedure_name": proc_name,
                    "code_system": "ICD9_CM3",
                    "code": llm_result.get("recommended_code", search_results[0]["code"] if search_results else ""),
                    "name": llm_result.get("recommended_name", search_results[0]["name"] if search_results else ""),
                    "score": llm_result.get("confidence", 0.7),
                    "rationale": llm_result.get("rationale", ""),
                    "approach_match": llm_result.get("approach_match", "unknown"),
                    "body_site": fact.get("body_site", ""),
                    "approach": fact.get("approach", ""),
                    "device_material": fact.get("device_material", ""),
                    "evidence_text": fact.get("evidence_text", ""),
                    "issues": llm_result.get("issues", []),
                    "alternative_codes": llm_result.get("alternative_codes", []),
                    "candidates": search_results[:3],
                    "coding_trace": trace,
                })
            except Exception as e:
                self._log_step(f"LLM selection failed for '{proc_name}': {e}", context)
                candidates.append(self._fallback_candidate(fact, search_results, trace))

        return self._timed_result(start, {
            "expert": self.name,
            "procedure_candidates": candidates,
            "candidate_count": len(candidates),
            "triage_summary": {
                "codable_procedures": len(codable_procs),
            },
            "method": "code_like_humans_4step",
        })

    def _build_full_text(self, context: dict) -> str:
        docs = context.get("documents", [])
        return "\n".join(d.get("content", "") for d in docs if d.get("content"))

    def _fallback_candidate(self, fact: dict, search_results: list, trace: dict) -> dict:
        return {
            "procedure_name": fact.get("procedure_name", ""),
            "code_system": "ICD9_CM3",
            "code": search_results[0]["code"] if search_results else "",
            "name": search_results[0]["name"] if search_results else fact.get("procedure_name", ""),
            "score": search_results[0].get("relevance", 0.3) if search_results else 0.3,
            "rationale": "Dictionary match fallback (LLM unavailable).",
            "approach_match": "unknown",
            "body_site": fact.get("body_site", ""),
            "approach": fact.get("approach", ""),
            "device_material": fact.get("device_material", ""),
            "evidence_text": fact.get("evidence_text", ""),
            "issues": ["LLM_UNAVAILABLE"],
            "alternative_codes": [],
            "candidates": search_results[:3],
            "coding_trace": trace,
        }
