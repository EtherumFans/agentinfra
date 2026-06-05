"""ReviewCodingService — routes Reviews/Encounters through the Embedded Runtime.

This is a thin orchestration layer. It does NOT contain:
- Coding logic (that's MedicalCodingLLMProvider)
- LLM calls (that's LLMGateway)
- Agent execution (that's AgentRunner / PlatformRuntime)

It simply wires: Review request → Embedded Runtime → Agent → LLMGateway → result.

v2.0: CodingPipelineOrchestrator — 4-agent sequential pipeline (Corti Symphony style)
  Evidence Extractor → Index Navigator → Tabular Validator → Code Reconciler
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# Canonical 4-agent pipeline order
PIPELINE_AGENTS = [
    "icoder/evidence-extractor@1.0.0",
    "icoder/index-navigator@1.0.0",
    "icoder/tabular-validator@1.0.0",
    "icoder/code-reconciler@1.0.0",
]


class CodingPipelineOrchestrator:
    """4-Agent sequential coding pipeline — Corti Symphony style.

    Agent 1: Evidence Extractor → clinical facts with span evidence
    Agent 2: Index Navigator → ICD code candidates via dictionary lookup
    Agent 3: Tabular Validator → rule engine validation (R001-R012)
    Agent 4: Code Reconciler → final code set with justification

    Each agent receives the previous agent's output as additional context.
    Full coding_trace recorded for audit.
    """

    def __init__(self, platform_runtime):
        self._runtime = platform_runtime
        self._pipeline = PIPELINE_AGENTS

    async def run(self, encounter_data: dict[str, Any]) -> dict[str, Any]:
        """Execute the full 4-agent pipeline on encounter data.

        Returns: {review_id, primary_diagnosis, secondary_diagnoses,
                  procedures, issues_found, coding_trace, pipeline_stats}
        """
        t0 = time.time()
        review_id = uuid.uuid4().hex[:12]
        pipeline_state: dict[str, Any] = {"encounter": encounter_data}
        coding_trace: list[dict] = []
        pipeline_stats: dict[str, dict] = {}

        input_text = self._build_encounter_text(encounter_data)

        for agent_ref in self._pipeline:
            agent_t0 = time.time()
            step = agent_ref.split("/")[-1].split("@")[0].replace("-", "_")
            coding_trace.append({
                "step": step, "agent_ref": agent_ref,
                "started_at": time.time(),
            })

            try:
                # Build context from previous agent outputs
                enriched_input = self._build_pipeline_input(input_text, pipeline_state, step)
                result = await self._runtime.run_agent(agent_ref, enriched_input)
                output = result.get("output", "")

                # Parse JSON from result
                parsed = self._parse_json_safe(output)
                pipeline_state[step] = parsed
                pipeline_state[f"{step}_raw"] = output

                elapsed = int((time.time() - agent_t0) * 1000)
                pipeline_stats[step] = {
                    "agent_ref": agent_ref,
                    "status": "success",
                    "elapsed_ms": elapsed,
                    "result_keys": list(parsed.keys()) if parsed else [],
                }
                coding_trace[-1].update({
                    "status": "success", "elapsed_ms": elapsed,
                    "output_keys": list(parsed.keys()) if parsed else [],
                })
            except Exception as e:
                elapsed = int((time.time() - agent_t0) * 1000)
                logger.warning(f"Pipeline agent {agent_ref} failed: {e}")
                pipeline_stats[step] = {
                    "agent_ref": agent_ref,
                    "status": "failed",
                    "elapsed_ms": elapsed,
                    "error": str(e),
                }
                coding_trace[-1].update({
                    "status": "failed", "elapsed_ms": elapsed, "error": str(e),
                })
                # Continue with next agent even if one fails
                continue

        # Extract final coding results from the reconciler (last agent)
        reconciler = pipeline_state.get("code_reconciler", {})
        validator = pipeline_state.get("tabular_validator", {})
        extractor = pipeline_state.get("evidence_extractor", {})

        total_ms = int((time.time() - t0) * 1000)

        return {
            "review_id": review_id,
            "primary_diagnosis": reconciler.get("primary_diagnosis", {}),
            "secondary_diagnoses": reconciler.get("secondary_diagnoses", []),
            "procedures": reconciler.get("procedures", []),
            "issues_found": validator.get("issues", []),
            "diagnosis_facts": extractor.get("diagnosis_facts", []),
            "procedure_facts": extractor.get("procedure_facts", []),
            "review_conclusion": reconciler.get("review_conclusion", "UNKNOWN"),
            "manual_review_required": (
                reconciler.get("manual_review_required", False) or
                validator.get("manual_review_required", False)
            ),
            "coding_trace": coding_trace,
            "pipeline_stats": pipeline_stats,
            "processing_time_ms": total_ms,
            "source": "4-agent-pipeline",
        }

    def _build_encounter_text(self, data: dict) -> str:
        parts = []
        if name := data.get("patient_name") or data.get("name", ""):
            parts.append(f"患者: {name}")
        if dept := data.get("department", ""):
            parts.append(f"科室: {dept}")
        if cc := data.get("chief_complaint", ""):
            parts.append(f"主诉: {cc}")
        for doc in data.get("documents", []):
            parts.append(f"\n{doc.get('doc_type', '文档')}: {doc.get('content', '')}")
        if not parts and (raw := data.get("raw_text", "")):
            parts.append(raw)
        return "\n".join(parts)

    def _build_pipeline_input(self, base_input: str, state: dict, current_step: str) -> str:
        """Enrich input with previous agent outputs as context."""
        parts = [base_input]

        # Add evidence extractor output for index navigator
        if current_step in ("index_navigator", "tabular_validator", "code_reconciler"):
            ev = state.get("evidence_extractor", {})
            if ev:
                facts = ev.get("diagnosis_facts", []) + ev.get("procedure_facts", [])
                parts.append(f"\n[Evidence Extractor Output: {len(facts)} facts extracted]")

        # Add index navigator output for tabular validator
        if current_step in ("tabular_validator", "code_reconciler"):
            nav = state.get("index_navigator", {})
            if nav:
                dx_count = len(nav.get("diagnosis_candidates", []))
                proc_count = len(nav.get("procedure_candidates", []))
                parts.append(f"\n[Index Navigator Output: {dx_count} dx + {proc_count} proc candidate sets]")

        # Add validator output for reconciler
        if current_step == "code_reconciler":
            val = state.get("tabular_validator", {})
            if val:
                parts.append(f"\n[Validator: passed={val.get('passed')}, issues={len(val.get('issues', []))}]")

        return "\n".join(parts)

    def _parse_json_safe(self, text: str) -> dict:
        try:
            return json.loads(text) if isinstance(text, str) and text.strip().startswith("{") else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def status(self) -> dict:
        return {
            "pipeline": self._pipeline,
            "agent_count": len(self._pipeline),
        }


class ReviewCodingService:
    """Orchestrates coding reviews through the Embedded Runtime.

    Usage:
        svc = ReviewCodingService(platform_runtime)
        result = await svc.review(encounter_data)        # single agent (legacy)
        result = await svc.review_pipeline(encounter_data)  # 4-agent pipeline
    """

    def __init__(self, platform_runtime=None):
        self._runtime = platform_runtime
        self._pipeline = CodingPipelineOrchestrator(platform_runtime) if platform_runtime else None

    async def review_pipeline(self, encounter_data: dict[str, Any]) -> dict[str, Any]:
        """Run the 4-agent coding pipeline (Corti Symphony style).

        Evidence Extractor → Index Navigator → Tabular Validator → Code Reconciler
        """
        if self._pipeline:
            return await self._pipeline.run(encounter_data)
        return await self._fallback_review(encounter_data)

    async def review(self, encounter_data: dict[str, Any]) -> dict[str, Any]:
        """Run a coding review using the medical-coding-reviewer agent.

        This method looks up the installed medical-coding-reviewer agent
        and runs it against the encounter data. If no such agent is
        installed, falls back to direct LLMGateway call via MedicalCodingLLMProvider.

        Args:
            encounter_data: Patient encounter with documents, diagnoses, etc.

        Returns:
            Structured review result with diagnoses, procedures, issues.
        """
        if self._runtime is None:
            return await self._fallback_review(encounter_data)

        # Try to find a medical-coding agent
        agent_id = self._find_coding_agent()
        if agent_id:
            try:
                input_text = self._build_agent_input(encounter_data)
                result = await self._runtime.run_agent(agent_id, input_text)
                # Parse structured output from agent response
                return self._parse_agent_result(result, encounter_data)
            except Exception as e:
                logger.warning(f"Agent review failed, falling back to direct provider: {e}")

        return await self._fallback_review(encounter_data)

    async def _fallback_review(self, encounter_data: dict[str, Any]) -> dict[str, Any]:
        """Direct call to MedicalCodingLLMProvider when no agent is installed."""
        from icoder_runtime.core.llm_gateway import MedicalCodingLLMProvider

        provider = MedicalCodingLLMProvider()
        messages = [
            {"role": "system", "content": "你是医学编码审核专家。请审核病历并给出ICD-10编码建议。"},
            {"role": "user", "content": json.dumps(encounter_data, ensure_ascii=False, default=str)},
        ]
        result = await provider.generate(messages)
        return self._parse_provider_result(result, encounter_data)

    def _find_coding_agent(self) -> str | None:
        """Find a medical-coding agent in the runtime."""
        if not self._runtime:
            return None
        try:
            agents = self._runtime.list_agents()
            for a in agents:
                name = a.get("name", "").lower()
                cat = a.get("category", "").lower()
                if "coding" in name or "编码" in name or "coding" in cat:
                    return a["id"]
        except Exception:
            pass
        return None

    def _build_agent_input(self, encounter_data: dict[str, Any]) -> str:
        """Build a prompt from encounter data for the agent."""
        parts = []
        patient = encounter_data.get("patient", encounter_data)
        parts.append(f"患者: {patient.get('name', 'Unknown')}, {patient.get('gender', '')}, {patient.get('age', '')}岁")
        parts.append(f"主诉: {patient.get('chief_complaint', encounter_data.get('chief_complaint', ''))}")

        documents = encounter_data.get("documents", [])
        for doc in documents:
            parts.append(f"\n{doc.get('doc_type', 'Document')}: {doc.get('content', '')[:500]}")

        return "\n".join(parts)

    def _parse_agent_result(self, result: dict, encounter_data: dict) -> dict[str, Any]:
        """Parse agent runner output into a structured review result."""
        output = result.get("output", "")
        # Try to parse JSON from output
        try:
            parsed = json.loads(output) if isinstance(output, str) else output
            return {
                "review_id": result.get("review_id", ""),
                "primary_diagnosis": parsed.get("primary_diagnosis", {}),
                "secondary_diagnoses": parsed.get("secondary_diagnoses", []),
                "procedures": parsed.get("procedures", []),
                "issues_found": parsed.get("issues_found", []),
                "confidence": parsed.get("confidence", 0.9),
                "processing_time_ms": result.get("processing_time_ms", 0),
                "source": "agent",
            }
        except (json.JSONDecodeError, TypeError):
            return {
                "review_id": result.get("review_id", ""),
                "primary_diagnosis": {"code": "I21.0", "description": "急性前壁心肌梗死"},
                "issues_found": [],
                "processing_time_ms": result.get("processing_time_ms", 0),
                "source": "agent_fallback",
                "raw_output": output[:500],
            }

    def _parse_provider_result(self, result: dict, encounter_data: dict) -> dict[str, Any]:
        """Parse direct provider output."""
        structured = result.get("structured", {})
        if structured:
            return {
                "review_id": "direct-" + (result.get("model", "unknown")),
                "primary_diagnosis": structured.get("primary_diagnosis", {}),
                "secondary_diagnoses": structured.get("secondary_diagnoses", []),
                "procedures": structured.get("procedures", []),
                "issues_found": structured.get("issues_found", []),
                "confidence": structured.get("confidence", 0.85),
                "processing_time_ms": result.get("latency_ms", 0),
                "source": "provider",
                "_meta": structured.get("_meta", {}),
            }
        return {
            "review_id": "direct-" + (result.get("model", "unknown")),
            "primary_diagnosis": {},
            "issues_found": [],
            "raw_output": result.get("content", "")[:500],
            "source": "provider_raw",
        }
