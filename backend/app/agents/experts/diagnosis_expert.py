# DEPRECATED (P1.3 Stage 5, 2026-07-02) — Legacy 单体 expert. Phase 2 切换到 app/icoder/agent_runtime/experts/ 后删. 见 docs/architecture/MAINLINE_VS_LEGACY.md §3.1.
# iCoDer - ICD Diagnosis Coding Expert
# Implements iCoDer "Code Like Humans" 4-step methodology:
# Phase A: Clinical Triage (filter non-codable facts)
# Phase B: ICD Index Navigation (tool-guided index lookup)
# Phase C: Specificity Iteration (hierarchical drill-down)
# Phase D: Evidence Binding + Audit Trail
import time
import json
from app.agents.base import BaseExpert
from app.services.code_dictionary import code_dict_service
from app.services.clinical_triage import clinical_triage_service

SYSTEM_PROMPT_NAVIGATOR = """你是中国住院病历ICD-10索引导航专家。
你的任务是通过浏览ICD-10索引为临床发现找到最精准的编码。

Step-by-step navigation:
1. Look at the index entries provided — they show the hierarchical ICD index structure
2. Identify the main term that best matches the clinical finding
3. Check sub-entries (indented) for more specific variants
4. Consider cross-references that may lead to better codes
5. If a .9 (unspecified) code appears, check if sub-entries allow more specificity
6. Select the most specific code supported by the clinical evidence

Key principles:
- Etiology-based codes > symptom-based codes when etiology is known
- Combination codes take priority over separate codes (M80 for osteo+fracture, not M81 + S32)
- Never code from imaging findings without clinical diagnosis
- Chinese clinical modification (.x suffixes) should be considered when available
- If the finding mentions specific anatomy, prefer codes that capture that specificity

Output valid JSON only."""

SYSTEM_PROMPT_SELECTOR = """你是编码选择专家。根据ICD索引导航返回的多个候选编码（不同精度层级），选择最佳编码。

Rules:
1. Select the MOST SPECIFIC code that clinical evidence supports
2. If evidence lacks detail for a specific subcode, choose the parent code and flag it
3. If a .9 code is selected, flag it for documentation improvement
4. Provide a written reasoning chain: index_main_term → sub_entry → final_code
5. Cite the evidence text that supports the code selection

Output valid JSON only."""


class ICDDiagnosisExpert(BaseExpert):
    name = "ICD Diagnosis Expert"
    description = "Generates ICD-10 diagnosis code candidates using Code Like Humans 4-step method"

    async def run(self, context: dict) -> dict:
        start = time.time()
        self._log_step("code-like-humans diagnosis coding", context)

        evidence = context.get("evidence", {})
        all_diagnosis_facts = evidence.get("diagnosis_facts", [])
        existing_codes = context.get("existing_diagnosis_codes", [])
        admission_reason = context.get("admission_reason", "")

        # ---- Phase A: Clinical Triage ----
        # Use pre-triaged data from orchestrator if available, otherwise run triage
        if "codable_diagnosis_facts" in context:
            codable_facts = context["codable_diagnosis_facts"]
            ruled_out = context.get("ruled_out_facts", [])
            history_of = context.get("history_facts", [])
            incidental = context.get("incidental_facts", [])
            self._log_step(
                f"using pre-triaged: {len(codable_facts)} codable, {len(ruled_out)} ruled_out, "
                f"{len(history_of)} history, {len(incidental)} incidental",
                context,
            )
        else:
            full_text = self._build_full_text(context)
            triage_result = clinical_triage_service.triage_all(
                evidence,
                {"full_text": full_text, "admission_reason": admission_reason},
            )
            codable_facts = triage_result["codable_diagnosis_facts"]
            ruled_out = triage_result["ruled_out_facts"]
            history_of = triage_result["history_facts"]
            self._log_step(
                f"triage: {len(codable_facts)} codable, {len(ruled_out)} ruled_out, "
                f"{len(history_of)} history, {len(triage_result['incidental_facts'])} incidental",
                context,
            )

        # ---- Phase B & C: Index Navigation + Specificity Iteration ----
        candidates = []
        coding_traces = []

        for fact in codable_facts:
            finding = fact.get("finding", "")
            if not finding:
                continue

            trace = {
                "finding": finding,
                "phase_b_index": None,
                "phase_c_drill": None,
                "phase_d_selection": None,
            }

            # Phase B: ICD Index Navigation
            index_result = await code_dict_service.lookup_index(finding, "ICD10_CN")
            trace["phase_b_index"] = {
                "main_term": index_result.get("main_term"),
                "match_count": index_result.get("match_count"),
                "top_path": [e for e in index_result.get("entries", [])[:5]],
            }

            # Phase C: For top matches, drill down for specificity
            search_results = index_result.get("search_path", [])
            drill_results = []
            for sr in search_results[:3]:
                drill = await code_dict_service.drill_down(
                    sr["code"], "ICD10_CN",
                    clinical_context={
                        "finding": finding,
                        "body_site": fact.get("body_site", ""),
                        "etiology": fact.get("etiology", ""),
                        "certainty": fact.get("certainty", ""),
                    },
                )
                drill_results.append(drill)
            trace["phase_c_drill"] = [
                {"parent": d["parent_code"], "sub_count": d["sub_code_count"],
                 "top_sub": d["sub_codes"][:3] if d["sub_codes"] else []}
                for d in drill_results
            ]

            # Phase D: Code Selection with reasoning chain
            try:
                selection_input = {
                    "finding": finding,
                    "body_site": fact.get("body_site", ""),
                    "etiology": fact.get("etiology", ""),
                    "certainty": fact.get("certainty", ""),
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
                    f"""Select the best ICD-10 code for this finding using the index navigation data.

Finding: {finding}
Body site: {fact.get('body_site', '')}
Etiology: {fact.get('etiology', '')}
Evidence: {fact.get('evidence_text', '')}

Index entries (hierarchical ICD structure):
{json.dumps(selection_input['index_navigation']['entries'][:12], ensure_ascii=False)}

Drill-down options (more specific subcodes):
{json.dumps(selection_input['drill_options'][:3], ensure_ascii=False)}

Return JSON:
{{
  "recommended_code": "X00.0",
  "recommended_name": "...",
  "rationale": "Index main_term=... → sub_entry=... → final_code=...",
  "confidence": 0.0,
  "specificity_level": "fully_specified|partially_specified|unspecified(.9)",
  "issues": ["..."],
  "alternative_codes": [{{"code": "...", "name": "...", "reason": "..."}}]
}}""",
                    json.dumps(selection_input, ensure_ascii=False),
                )

                trace["phase_d_selection"] = {
                    "code": llm_result.get("recommended_code", ""),
                    "rationale": llm_result.get("rationale", ""),
                    "specificity": llm_result.get("specificity_level", ""),
                }

                candidates.append({
                    "finding": finding,
                    "code_system": "ICD10_CN",
                    "code": llm_result.get("recommended_code", search_results[0]["code"] if search_results else ""),
                    "name": llm_result.get("recommended_name", search_results[0]["name"] if search_results else ""),
                    "score": llm_result.get("confidence", 0.7),
                    "rationale": llm_result.get("rationale", ""),
                    "specificity_level": llm_result.get("specificity_level", "unspecified"),
                    "evidence_text": fact.get("evidence_text", ""),
                    "certainty": fact.get("certainty", "suspected"),
                    "negation": fact.get("negation", False),
                    "issues": llm_result.get("issues", []),
                    "alternative_codes": llm_result.get("alternative_codes", []),
                    "candidates": search_results[:3],
                    "coding_trace": trace,
                })
            except Exception as e:
                self._log_step(f"LLM selection failed for '{finding}': {e}", context)
                candidates.append(self._fallback_candidate(fact, search_results, trace))

        # Include history-of facts with Z-code guidance
        for fact in history_of:
            candidates.append(self._z_code_candidate(fact))

        return self._timed_result(start, {
            "expert": self.name,
            "diagnosis_candidates": candidates,
            "candidate_count": len(candidates),
            "triage_summary": {
                "codable": len(codable_facts),
                "ruled_out": len(ruled_out),
                "history_of": len(history_of),
                "incidental": len(triage_result["incidental_facts"]),
            },
            "method": "code_like_humans_4step",
        })

    # ---- helpers ----

    def _build_full_text(self, context: dict) -> str:
        docs = context.get("documents", [])
        parts = []
        for d in docs:
            content = d.get("content", "")
            if content:
                parts.append(content)
        return "\n".join(parts)

    def _fallback_candidate(self, fact: dict, search_results: list, trace: dict) -> dict:
        return {
            "finding": fact.get("finding", ""),
            "code_system": "ICD10_CN",
            "code": search_results[0]["code"] if search_results else "",
            "name": search_results[0]["name"] if search_results else fact.get("finding", ""),
            "score": search_results[0].get("relevance", 0.3) if search_results else 0.3,
            "rationale": "Dictionary match fallback (LLM unavailable).",
            "specificity_level": "unknown",
            "evidence_text": fact.get("evidence_text", ""),
            "certainty": fact.get("certainty", "suspected"),
            "negation": fact.get("negation", False),
            "issues": ["LLM_UNAVAILABLE"],
            "alternative_codes": [],
            "candidates": search_results[:3],
            "coding_trace": trace,
        }

    def _z_code_candidate(self, fact: dict) -> dict:
        return {
            "finding": fact.get("finding", ""),
            "code_system": "ICD10_CN",
            "code": "Z87.8",
            "name": f"个人史: {fact.get('finding', '')}",
            "score": 0.6,
            "rationale": f"Past history fact classified as '{fact.get('clinical_significance', 'history_of')}': {fact.get('triage_reason', '')}",
            "specificity_level": "history",
            "evidence_text": fact.get("evidence_text", ""),
            "certainty": "history",
            "negation": False,
            "issues": ["PAST_HISTORY_Z_CODE"],
            "alternative_codes": [],
            "candidates": [],
            "coding_trace": {"finding": fact.get("finding"), "note": "history_of → Z-code guidance"},
        }
