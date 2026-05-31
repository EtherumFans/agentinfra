# iCoDer - Agent Orchestrator
# Fixed pipeline: Evidence → Diagnosis/Procedure → Homepage → Rules → Verify → DRG → Report → Human Review
import logging
import time
import uuid
from typing import Optional

from app.config import settings
from app.services.llm_service import llm_service
from app.services.code_dictionary import code_dict_service
from app.services.rule_engine import rule_engine_service
from app.services.llm_planner import llm_planner, FIXED_PIPELINE_STEPS
from app.services.context_scoper import context_scoper
from app.services.guardrails import guardrails
from app.services.clinical_triage import clinical_triage_service
from app.agents.experts.evidence_expert import EvidenceExtractionExpert
from app.agents.experts.timeline_expert import TimelineReconstructionExpert
from app.agents.experts.diagnosis_expert import ICDDiagnosisExpert
from app.agents.experts.procedure_expert import ProcedureCodingExpert
from app.agents.experts.homepage_expert import MedicalRecordHomepageExpert
from app.agents.experts.drg_expert import DRGDIPExpert, DocumentationGapExpert, EvidenceVerificationExpert
from app.agents.experts.report_expert import ReportExpert
from app.agents.experts.cdi_expert import CDIExpert
from app.agents.experts.denial_expert import DenialManagementExpert
from app.agents.experts.audit_expert import AuditTrailExpert
from app.agents.experts.hcc_expert import HCCRiskAdjustmentExpert
from app.services.runtime import DeterministicRuntime, CaseState, GateOutcome, runtime_registry
from app.services.evidence_ranker import rank_all_evidence
from app.services.disagreement_analyzer import analyze_disagreements
from app.services.confidence_calibrator import calibrate_all
from app.services.reasoning_report_builder import build_case_reasoning_report

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrates the fixed 9-step coding audit pipeline.

    Pipeline (per PRD section 10.2):
    Step 1: Evidence Extraction Expert
    Step 2: ICD Diagnosis Expert / Procedure Coding Expert
    Step 3: Medical Record Homepage Expert
    Step 4: Code Dictionary Tool (integrated into diagnosis/procedure experts)
    Step 5: Coding Rule Tool (integrated into homepage expert)
    Step 6: Evidence Verification Expert
    Step 7: DRG/DIP Expert + Documentation Gap Expert
    Step 8: Report Expert
    Step 9: Human Review (separate, triggered by API)
    """

    def __init__(self):
        self.evidence_expert = EvidenceExtractionExpert()
        self.timeline_expert = TimelineReconstructionExpert()
        self.diagnosis_expert = ICDDiagnosisExpert()
        self.procedure_expert = ProcedureCodingExpert()
        self.homepage_expert = MedicalRecordHomepageExpert()
        self.drg_expert = DRGDIPExpert()
        self.doc_gap_expert = DocumentationGapExpert()
        self.evidence_verify_expert = EvidenceVerificationExpert()
        self.report_expert = ReportExpert()
        self.cdi_expert = CDIExpert()
        self.denial_expert = DenialManagementExpert()
        self.audit_expert = AuditTrailExpert()
        self.hcc_expert = HCCRiskAdjustmentExpert()

    async def run_pipeline(self, encounter_data: dict,
                           progress_callback=None) -> dict:
        """Execute the full coding audit pipeline for an encounter.

        Args:
            encounter_data: dict with encounter info, documents, and existing codes
            progress_callback: optional async fn(pct: int, step: str) for progress updates

        Returns:
            Complete review result with all expert outputs, evidence, candidates, and report
        """
        pipeline_id = uuid.uuid4().hex[:12]
        encounter_id = encounter_data.get("encounter_id", pipeline_id)
        overall_start = time.time()

        # Initialize deterministic runtime for this pipeline
        rt = runtime_registry.get_or_create(pipeline_id)
        rt.pipeline_id = pipeline_id
        rt.execution_path = "orchestrator"
        rt.review_id = f"REV-{pipeline_id}"
        rt.transition(CaseState.INGESTED, actor="orchestrator")

        logger.info(f"[Pipeline {pipeline_id}] Starting for encounter {encounter_id}")
        logger.info(f"[Pipeline {pipeline_id}] Docs: {len(encounter_data.get('documents', []))}, "
                     f"Existing diag codes: {len(encounter_data.get('existing_diagnosis_codes', []))}, "
                     f"Existing proc codes: {len(encounter_data.get('existing_procedure_codes', []))}")

        context = {
            "pipeline_id": pipeline_id,
            "encounter_id": encounter_id,
            "encounter": encounter_data,
            "documents": encounter_data.get("documents", []),
            "admission_reason": encounter_data.get("admission_reason", ""),
            "existing_diagnosis_codes": encounter_data.get("existing_diagnosis_codes", []),
            "existing_procedure_codes": encounter_data.get("existing_procedure_codes", []),
            "agent_version": settings.APP_VERSION,
            "model_used": settings.LLM_MODEL,
        }

        errors = []
        use_scoping = context.get("context_scoping", True)

        # Guardrails: validate input before processing
        input_text = " ".join(d.get("content", "") for d in context.get("documents", []))
        if input_text:
            input_check = await guardrails.validate_input(input_text)
            if not input_check["valid"]:
                logger.warning(f"[Pipeline {pipeline_id}] Guardrails blocked input: {input_check['violations']}")
                errors.extend([{"step": "guardrails_input", "error": v["message"]} for v in input_check["violations"] if v["severity"] == "error"])
                if any(v["severity"] == "error" and v["rule"] in ("blocked_term",) for v in input_check["violations"]):
                    rt.transition(CaseState.FAILED, actor="guardrails")
                    return self._build_result(pipeline_id, encounter_id, context, errors, 0)

        # Runtime: INGESTED → CONTEXT_READY (input validated, context built)
        rt.check_timeout()
        rt.transition(CaseState.CONTEXT_READY, actor="orchestrator")

        # Runtime: CONTEXT_READY → FACTS_EXTRACTED (evidence extraction begins)
        rt.check_timeout()
        rt.transition(CaseState.FACTS_EXTRACTED, actor="evidence_expert")

        # Step 1: Evidence Extraction
        if progress_callback: await progress_callback(10, "提取临床证据")
        logger.info(f"[Pipeline {pipeline_id}] Step 1: Evidence Extraction")
        try:
            scoped = context_scoper.scope_for("EvidenceExtractionExpert", context) if use_scoping else context
            evidence_result = await self.evidence_expert.run(scoped)
            rt.guard_post(evidence_result)  # Post-guard: validate evidence output
            context["evidence"] = evidence_result.get("evidence", {})
            context["raw_text_length"] = evidence_result.get("raw_text_length", 0)
            logger.info(f"[Pipeline {pipeline_id}] Evidence extracted: "
                        f"{len(context['evidence'].get('diagnosis_facts', []))} diagnosis facts, "
                        f"{len(context['evidence'].get('procedure_facts', []))} procedure facts")
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Evidence extraction failed: {e}")
            errors.append({"step": "evidence_extraction", "error": str(e), "severity": "critical"})
            context["evidence"] = {"diagnosis_facts": [], "procedure_facts": [], "chief_complaint": "", "timing_facts": {}}

        # Step 2: Timeline Reconstruction
        if progress_callback: await progress_callback(20, "重建临床时间线")
        logger.info(f"[Pipeline {pipeline_id}] Step 2: Timeline Reconstruction")
        try:
            scoped = context_scoper.scope_for("TimelineReconstructionExpert", context) if use_scoping else context
            timeline_result = await self.timeline_expert.run(scoped)
            context["timeline"] = timeline_result.get("timeline", {})
            logger.info(f"[Pipeline {pipeline_id}] Timeline reconstructed: "
                        f"{timeline_result.get('event_count', 0)} events, "
                        f"{timeline_result.get('unresolved_count', 0)} unresolved")
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Timeline reconstruction failed: {e}")
            errors.append({"step": "timeline_reconstruction", "error": str(e), "severity": "warning"})
            context["timeline"] = {"encounter_id": encounter_id, "events": [], "unresolved_events": [], "timeline_summary": ""}

        # Step 1b: Clinical Triage (iCoDer "Code Like Humans" Step 1)
        if progress_callback: await progress_callback(25, "临床意义分类")
        logger.info(f"[Pipeline {pipeline_id}] Step 1b: Clinical Triage")
        try:
            full_text = " ".join(d.get("content", "") for d in context.get("documents", []))
            triage_result = clinical_triage_service.triage_all(
                context.get("evidence", {}),
                {"full_text": full_text, "admission_reason": context.get("admission_reason", "")},
            )
            context["clinical_triage"] = triage_result
            # Pass pre-triaged codable facts to experts
            context["codable_diagnosis_facts"] = triage_result["codable_diagnosis_facts"]
            context["codable_procedure_facts"] = triage_result["codable_procedure_facts"]
            context["history_facts"] = triage_result["history_facts"]
            context["ruled_out_facts"] = triage_result["ruled_out_facts"]
            context["incidental_facts"] = triage_result["incidental_facts"]
            logger.info(f"[Pipeline {pipeline_id}] Triage: "
                        f"{len(triage_result['codable_diagnosis_facts'])} codable diag, "
                        f"{len(triage_result['codable_procedure_facts'])} codable proc, "
                        f"{len(triage_result['history_facts'])} history, "
                        f"{len(triage_result['ruled_out_facts'])} ruled_out, "
                        f"{len(triage_result['incidental_facts'])} incidental")
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Clinical triage failed: {e}")
            errors.append({"step": "clinical_triage", "error": str(e), "severity": "warning"})
            context["clinical_triage"] = {}
            context["codable_diagnosis_facts"] = context.get("evidence", {}).get("diagnosis_facts", [])
            context["codable_procedure_facts"] = context.get("evidence", {}).get("procedure_facts", [])

        # Step 3a: ICD Diagnosis Coding
        if progress_callback: await progress_callback(30, "ICD诊断编码")
        logger.info(f"[Pipeline {pipeline_id}] Step 3a: Diagnosis Coding")
        try:
            scoped = context_scoper.scope_for("ICDDiagnosisExpert", context) if use_scoping else context
            diag_result = await self.diagnosis_expert.run(scoped)
            rt.guard_post(diag_result)
            diag_candidates = diag_result.get("diagnosis_candidates", [])
            context["diagnosis_candidates"] = [c for c in diag_candidates if isinstance(c, dict)]
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Diagnosis coding failed: {e}")
            errors.append({"step": "diagnosis_coding", "error": str(e), "severity": "critical"})
            context["diagnosis_candidates"] = []

        # Step 3b: Procedure Coding
        if progress_callback: await progress_callback(40, "手术操作编码")
        logger.info(f"[Pipeline {pipeline_id}] Step 3b: Procedure Coding")
        try:
            scoped = context_scoper.scope_for("ProcedureCodingExpert", context) if use_scoping else context
            proc_result = await self.procedure_expert.run(scoped)
            rt.guard_post(proc_result)
            proc_candidates = proc_result.get("procedure_candidates", [])
            context["procedure_candidates"] = [c for c in proc_candidates if isinstance(c, dict)]
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Procedure coding failed: {e}")
            errors.append({"step": "procedure_coding", "error": str(e), "severity": "critical"})
            context["procedure_candidates"] = []

        # Runtime: candidates generated → CANDIDATES_READY → RULES_VALIDATED
        rt.check_timeout()
        rt.transition(CaseState.CANDIDATES_READY, actor="diagnosis_expert")
        rt.transition(CaseState.RULES_VALIDATED, actor="homepage_expert")

        # Step 4-6: Homepage Expert (also covers Code Dict & Rule checks)
        if progress_callback: await progress_callback(50, "首页编码+规则校验")
        logger.info(f"[Pipeline {pipeline_id}] Step 4-6: Homepage + Rules Validation")
        try:
            scoped = context_scoper.scope_for("MedicalRecordHomepageExpert", context) if use_scoping else context
            homepage_result = await self.homepage_expert.run(scoped)
            context["primary_diagnosis"] = homepage_result.get("primary_diagnosis") or {}
            context["primary_diagnosis_reasoning"] = homepage_result.get("primary_diagnosis_reasoning") or {}
            context["main_procedure"] = homepage_result.get("main_procedure") or {}
            context["secondary_diagnoses"] = homepage_result.get("secondary_diagnoses", [])
            context["other_procedures"] = homepage_result.get("other_procedures", [])
            context["existing_diagnosis_review"] = homepage_result.get("existing_diagnosis_review", [])
            context["existing_procedure_review"] = homepage_result.get("existing_procedure_review", [])
        except Exception as e:
            import traceback
            tb_str = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            logger.error(f"[Pipeline {pipeline_id}] Homepage validation failed: {e}\n{tb_str}")
            errors.append({"step": "homepage", "error": str(e), "severity": "critical"})
            context.update({
                "primary_diagnosis": {}, "primary_diagnosis_reasoning": {},
                "main_procedure": {},
                "secondary_diagnoses": [], "other_procedures": [],
                "existing_diagnosis_review": [], "existing_procedure_review": [],
            })

        # Step 7: Evidence Verification
        if progress_callback: await progress_callback(60, "证据验证")
        logger.info(f"[Pipeline {pipeline_id}] Step 7: Evidence Verification")
        try:
            verify_result = await self.evidence_verify_expert.run(context)
            context["verification"] = verify_result
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Evidence verification failed: {e}")
            errors.append({"step": "evidence_verification", "error": str(e), "severity": "warning"})
            context["verification"] = {"verifications": [], "summary": {}}

        # Step 7b: Evidence Ranking
        if progress_callback: await progress_callback(68, "证据排名与冲突检测")
        logger.info(f"[Pipeline {pipeline_id}] Step 7b: Evidence Ranking")
        try:
            evidence_ranking = rank_all_evidence(
                diagnosis_candidates=context.get("diagnosis_candidates", []),
                procedure_candidates=context.get("procedure_candidates", []),
                evidence_facts=context.get("evidence", {}).get("diagnosis_facts", []),
                procedure_facts=context.get("evidence", {}).get("procedure_facts", []),
                admission_reason=context.get("admission_reason", ""),
                timeline=context.get("timeline", {}),
                primary_diagnosis=context.get("primary_diagnosis", {}),
                existing_diagnosis_codes=context.get("existing_diagnosis_codes", []),
            )
            context["evidence_ranking"] = evidence_ranking
            # Runtime audit: flag unsupported codes
            for uc in evidence_ranking.get("unsupported_codes", []):
                gate = rt.guard("flag_unsupported_code", "evidence_ranker")
                if gate != GateOutcome.DENY:
                    rt.audit.record("unsupported_code_flagged", actor="evidence_ranker", payload={
                        "code": uc["code"], "name": uc["name"],
                        "reason": uc.get("reason", ""),
                        "strength_best": uc.get("strength_best", 0),
                    })
            # Runtime audit: record conflicts
            for conflict in evidence_ranking.get("conflicts", []):
                gate = rt.guard("resolve_evidence_conflict", "evidence_ranker")
                if gate != GateOutcome.DENY:
                    rt.audit.record("evidence_conflict_detected", actor="evidence_ranker", payload={
                        "conflict_type": conflict.get("conflict_type", ""),
                        "conflict_summary": conflict.get("conflict_summary", ""),
                        "affected_codes": conflict.get("affected_codes", []),
                    })
            logger.info(f"[Pipeline {pipeline_id}] Evidence ranked: "
                        f"{len(evidence_ranking.get('top_supporting_evidence', []))} strong, "
                        f"{len(evidence_ranking.get('unsupported_codes', []))} unsupported, "
                        f"{len(evidence_ranking.get('conflicts', []))} conflicts")
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Evidence ranking failed: {e}")
            errors.append({"step": "evidence_ranking", "error": str(e), "severity": "warning"})
            context["evidence_ranking"] = {}

        # Step 7c: Disagreement Analysis
        if progress_callback: await progress_callback(72, "分歧分析与修正建模")
        logger.info(f"[Pipeline {pipeline_id}] Step 7c: Disagreement Analysis")
        try:
            gold_codes = encounter_data.get("gold_diagnosis_codes", [])
            gold_procs = encounter_data.get("gold_procedure_codes", [])
            # Build rule_matches from primary diagnosis reasoning
            reasoning = context.get("primary_diagnosis_reasoning", {})
            rule_matches = {}
            if reasoning:
                for rule_id in reasoning.get("rule_basis", []):
                    pd_code = context.get("primary_diagnosis", {}).get("code", "")
                    if pd_code:
                        rule_matches.setdefault(pd_code, []).append(rule_id)

            disagreement_result = analyze_disagreements(
                diagnosis_candidates=context.get("diagnosis_candidates", []),
                procedure_candidates=context.get("procedure_candidates", []),
                primary_diagnosis=context.get("primary_diagnosis", {}),
                evidence_ranking=context.get("evidence_ranking", {}),
                gold_diagnosis_codes=gold_codes,
                gold_procedure_codes=gold_procs,
                existing_diagnosis_codes=context.get("existing_diagnosis_codes", []),
                existing_procedure_codes=context.get("existing_procedure_codes", []),
                admission_reason=context.get("admission_reason", ""),
                drg_impact=context.get("drg_impact", {}),
                rule_matches=rule_matches,
            )
            context["disagreement_analysis"] = disagreement_result
            # Runtime audit
            for corr in disagreement_result.get("corrections", []):
                rt.audit.record("disagreement_analyzed", actor="disagreement_analyzer", payload={
                    "code_ai": corr.get("code_ai", ""),
                    "code_correct": corr.get("code_correct", ""),
                    "disagreement_type": corr.get("disagreement_type", ""),
                    "drg_impacted": corr.get("drg_impacted", False),
                })
                if corr.get("drg_impacted"):
                    rt.audit.record("drg_impact_correction", actor="disagreement_analyzer", payload={
                        "code_ai": corr.get("code_ai"),
                        "code_correct": corr.get("code_correct"),
                        "drg_before": corr.get("drg_before"),
                        "drg_after": corr.get("drg_after"),
                    })
            logger.info(f"[Pipeline {pipeline_id}] Disagreement analysis: "
                        f"{disagreement_result.get('summary', {}).get('disagreements', 0)} disagreements, "
                        f"{disagreement_result.get('summary', {}).get('drg_impacted_count', 0)} DRG-impacted")
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Disagreement analysis failed: {e}")
            errors.append({"step": "disagreement_analysis", "error": str(e), "severity": "warning"})
            context["disagreement_analysis"] = {}

        # Step 7d: Confidence Calibration
        if progress_callback: await progress_callback(74, "置信度校准与自动分流")
        logger.info(f"[Pipeline {pipeline_id}] Step 7d: Confidence Calibration")
        try:
            calibration_result = calibrate_all(
                diagnosis_candidates=context.get("diagnosis_candidates", []),
                procedure_candidates=context.get("procedure_candidates", []),
                primary_diagnosis=context.get("primary_diagnosis", {}),
                evidence_ranking=context.get("evidence_ranking", {}),
                disagreement_analysis=context.get("disagreement_analysis", {}),
                primary_diag_reasoning=context.get("primary_diagnosis_reasoning", {}),
                gold_diagnosis_codes=encounter_data.get("gold_diagnosis_codes", []),
                gold_procedure_codes=encounter_data.get("gold_procedure_codes", []),
            )
            context["confidence_calibration"] = calibration_result
            # Runtime audit
            for rd in calibration_result.get("routing_decisions", []):
                rt.audit.record("confidence_calibrated", actor="confidence_calibrator", payload={
                    "code": rd.get("code"),
                    "calibrated_score": rd.get("calibrated_score"),
                    "tier": rd.get("tier"),
                })
                if rd.get("override_reason"):
                    rt.audit.record("routing_decision", actor="confidence_calibrator", payload={
                        "code": rd.get("code"),
                        "tier": rd.get("tier"),
                        "risk_factors": rd.get("risk_factors"),
                        "override_reason": rd.get("override_reason"),
                    })
            logger.info(f"[Pipeline {pipeline_id}] Confidence calibrated: "
                        f"auto={calibration_result.get('metrics', {}).get('auto_count', 0)}, "
                        f"review={calibration_result.get('metrics', {}).get('review_count', 0)}, "
                        f"escalate={calibration_result.get('metrics', {}).get('escalate_count', 0)}")
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Confidence calibration failed: {e}")
            errors.append({"step": "confidence_calibration", "error": str(e), "severity": "warning"})
            context["confidence_calibration"] = {}

        # Step 8a: DRG/DIP Analysis
        if progress_callback: await progress_callback(75, "DRG/DIP分析")
        logger.info(f"[Pipeline {pipeline_id}] Step 8a: DRG/DIP Analysis")
        try:
            drg_result = await self.drg_expert.run(context)
            rt.guard_post(drg_result)
            context["drg_impact"] = drg_result
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] DRG analysis failed: {e}")
            errors.append({"step": "drg_analysis", "error": str(e), "severity": "warning"})
            context["drg_impact"] = {"drg_risks": [], "recommendations": []}

        # Runtime: rules validated → risk identified → review required
        rt.check_timeout()
        rt.transition(CaseState.RISK_IDENTIFIED, actor="drg_expert")

        # All coding review cases require human review before decision
        rt.transition(CaseState.REVIEW_REQUIRED, actor="orchestrator")
        has_risks = bool(context.get("drg_impact", {}).get("drg_risks", []))
        has_unsupported = bool(context.get("evidence_ranking", {}).get("unsupported_codes", []))
        if has_risks or has_unsupported:
            logger.info(f"[Pipeline {pipeline_id}] Elevated review: risks={has_risks}, unsupported={has_unsupported}")

        # Step 8b: Documentation Gap Analysis
        if progress_callback: await progress_callback(87, "文书缺口分析")
        logger.info(f"[Pipeline {pipeline_id}] Step 8b: Documentation Gap Analysis")
        try:
            doc_gap_result = await self.doc_gap_expert.run(context)
            context["documentation_gaps"] = doc_gap_result.get("documentation_gaps", [])
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Doc gap analysis failed: {e}")
            errors.append({"step": "doc_gap_analysis", "error": str(e), "severity": "warning"})
            context["documentation_gaps"] = []

        # Runtime guard: before report, check primary diagnosis finalization
        rt.check_timeout()
        gate = rt.guard("finalize_principal_diagnosis", "orchestrator")
        if gate == GateOutcome.DENY:
            logger.warning(f"[Pipeline {pipeline_id}] DUC: diagnosis finalization denied")
            errors.append({"step": "runtime_guard", "error": "主要诊断确认被安全门拒绝"})
        elif gate == GateOutcome.REVIEW:
            logger.info(f"[Pipeline {pipeline_id}] DUC: diagnosis requires human review")

        # Runtime: decision confirmed
        rt.transition(CaseState.DECISION_CONFIRMED, actor="orchestrator")

        # Step 9: Report Generation
        if progress_callback: await progress_callback(95, "生成审核报告")
        logger.info(f"[Pipeline {pipeline_id}] Step 9: Report Generation")
        context["review_id"] = f"REV-{pipeline_id}"
        try:
            report_result = await self.report_expert.run(context)
            rt.guard_post(report_result)
            context["report_markdown"] = report_result.get("report_markdown", "")
            context["report_html"] = report_result.get("report_html", "")
            context["uncodable_items"] = report_result.get("uncodable_items", [])
            context["human_checklist"] = report_result.get("human_checklist", [])
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Report generation failed: {e}")
            errors.append({"step": "report_generation", "error": str(e), "severity": "warning"})
            context["report_markdown"] = "# Report Generation Failed"
            context["report_html"] = "<p>Report generation failed</p>"

        # Build unified Case Reasoning Report (aggregates 9A-9E)
        try:
            context["case_reasoning_report"] = build_case_reasoning_report(context)
            rt.audit.record("case_reasoning_report_built", actor="orchestrator", payload={
                "encounter_id": context.get("encounter_id"),
                "sections": ["timeline", "evidence", "principal_diagnosis", "disagreement", "confidence"],
            })
            logger.info(f"[Pipeline {pipeline_id}] Case Reasoning Report built")
        except Exception as e:
            logger.error(f"[Pipeline {pipeline_id}] Case reasoning report failed: {e}")
            context["case_reasoning_report"] = {}

        total_time_ms = int((time.time() - overall_start) * 1000)

        # Runtime: pipeline complete → ARCHIVED
        rt.check_timeout()
        rt.transition(CaseState.ARCHIVED, actor="orchestrator")
        logger.info(f"[Pipeline {pipeline_id}] Runtime: {rt.status()}")

        # Guardrails: validate output before returning
        report_text = context.get("report_markdown", "")
        if report_text:
            output_check = await guardrails.validate_output(report_text)
            if output_check.get("requires_disclaimer") and not output_check.get("valid"):
                context["report_markdown"] = report_text + "\n\n---\n*AI辅助编码建议，请结合临床判断。*"
            if not output_check["valid"]:
                logger.warning(f"[Pipeline {pipeline_id}] Guardrails flagged output: {output_check['violations']}")
                errors.extend([{"step": "guardrails_output", "error": v["message"]} for v in output_check["violations"] if v["severity"] == "error"])

        # Build validation summary
        verification_summary = context.get("verification", {}).get("summary", {})
        validation_summary = {
            "total_codes": verification_summary.get("total_codes", 0),
            "supported": verification_summary.get("supported", 0),
            "needs_review": verification_summary.get("needs_review", 0),
            "unsupported": verification_summary.get("unsupported", 0),
            "evidence_binding_rate": verification_summary.get("evidence_binding_rate", 0),
            "documentation_gaps": len(context.get("documentation_gaps", [])),
            "drg_risks": len(context.get("drg_impact", {}).get("drg_risks", [])),
            "pipeline_errors": len(errors),
        }

        logger.info(f"[Pipeline {pipeline_id}] Pipeline complete in {total_time_ms}ms. "
                     f"Errors: {len(errors)}, Supported codes: {validation_summary['supported']}")

        return {
            "pipeline_id": pipeline_id,
            "review_id": context["review_id"],
            "encounter_id": encounter_id,
            "agent_version": settings.APP_VERSION,
            "model_used": settings.LLM_MODEL,
            "processing_time_ms": total_time_ms,
            "errors": errors,
            # Core outputs
            "evidence": context.get("evidence", {}),
            "timeline": context.get("timeline", {}),
            "diagnosis_candidates": context.get("diagnosis_candidates", []),
            "procedure_candidates": context.get("procedure_candidates", []),
            "primary_diagnosis": context.get("primary_diagnosis") or {},
            "primary_diagnosis_reasoning": context.get("primary_diagnosis_reasoning", {}),
            "main_procedure": context.get("main_procedure", {}),
            "secondary_diagnoses": context.get("secondary_diagnoses", []),
            "other_procedures": context.get("other_procedures", []),
            "existing_diagnosis_review": context.get("existing_diagnosis_review", []),
            "existing_procedure_review": context.get("existing_procedure_review", []),
            "verification": context.get("verification", {}),
            "evidence_ranking": context.get("evidence_ranking", {}),
            "disagreement_analysis": context.get("disagreement_analysis", {}),
            "confidence_calibration": context.get("confidence_calibration", {}),
            "drg_impact": context.get("drg_impact", {}),
            "documentation_gaps": context.get("documentation_gaps", []),
            "uncodable_items": context.get("uncodable_items", []),
            "human_checklist": context.get("human_checklist", []),
            "validation_summary": validation_summary,
            # Reports
            "report_markdown": context.get("report_markdown", ""),
            "report_html": context.get("report_html", ""),
            "case_reasoning_report": context.get("case_reasoning_report", {}),
        }


    async def run_intelligent_pipeline(self, encounter_data: dict) -> dict:
        """Execute a dynamically-planned pipeline using the LLM Planner.

        Unlike run_pipeline() which always executes all 9 steps, this method:
        1. Sends the encounter text to the LLM Planner
        2. The planner analyzes the content and decides which experts are needed
        3. Only the selected experts are executed
        4. Falls back to the fixed pipeline if planning fails

        All execution is gated by DeterministicRuntime.
        """
        pipeline_id = f"INT-{uuid.uuid4().hex[:8]}"
        encounter_id = encounter_data.get("encounter_id", pipeline_id)
        overall_start = time.time()

        # --- Runtime: create instance ---
        rt = runtime_registry.get_or_create(pipeline_id)
        rt.transition(CaseState.INGESTED, actor="orchestrator")

        # Extract text for the planner
        all_text = " ".join(
            d.get("content", "") for d in encounter_data.get("documents", [])
        )
        if not all_text:
            logger.warning(f"[Intelligent Pipeline {pipeline_id}] No text found, using fixed plan")
            return await self.run_pipeline(encounter_data)

        # Guardrails: validate input
        input_check = await guardrails.validate_input(all_text)
        if not input_check["valid"]:
            logger.warning(f"[Intelligent Pipeline {pipeline_id}] Guardrails blocked input")
            rt.audit.record("guardrails_blocked", actor="orchestrator",
                payload={"violations": input_check.get("violations", [])})
            if any(v["severity"] == "error" and v["rule"] in ("blocked_term",) for v in input_check.get("violations", [])):
                rt.transition(CaseState.FAILED, actor="orchestrator")
                return self._build_result(pipeline_id, encounter_id, {}, [
                    {"step": "guardrails_input", "error": v["message"]}
                    for v in input_check["violations"] if v["severity"] == "error"
                ], 0)

        # Step 0: LLM plans the pipeline
        logger.info(f"[Intelligent Pipeline {pipeline_id}] Requesting dynamic plan...")
        plan = await llm_planner.plan(all_text, {
            "department": encounter_data.get("department", ""),
            "existing_diagnosis_codes": encounter_data.get("existing_diagnosis_codes", []),
            "existing_procedure_codes": encounter_data.get("existing_procedure_codes", []),
        })

        # --- Runtime: context ready ---
        rt.transition(CaseState.CONTEXT_READY, actor="orchestrator")
        rt.audit.record("dynamic_plan_generated", actor="orchestrator", payload={
            "planned_steps": [s.get("step") for s in plan.get("steps", [])],
            "fallback": plan.get("fallback", False),
        })

        is_fallback = plan.get("fallback", False)
        planned_steps = plan.get("steps", [])
        skipped_steps = len(FIXED_PIPELINE_STEPS) - len(planned_steps)

        logger.info(
            f"[Intelligent Pipeline {pipeline_id}] "
            f"Plan: {len(planned_steps)} steps ({skipped_steps} skipped)"
            f"{' [FALLBACK]' if is_fallback else ''}"
            f" — {plan.get('reasoning', '')[:80]}"
        )

        # Set up context (same as fixed pipeline)
        context = {
            "pipeline_id": pipeline_id,
            "encounter_id": encounter_id,
            "encounter": encounter_data,
            "documents": encounter_data.get("documents", []),
            "admission_reason": encounter_data.get("admission_reason", ""),
            "existing_diagnosis_codes": encounter_data.get("existing_diagnosis_codes", []),
            "existing_procedure_codes": encounter_data.get("existing_procedure_codes", []),
            "agent_version": settings.APP_VERSION,
            "model_used": settings.LLM_MODEL,
            "plan": plan,  # Store the plan for auditing
            "context_scoping": True,  # Enable context scoping for experts
        }

        errors = []

        # Execute only the planned steps (in the planned order), gated by Runtime
        for planned_step in planned_steps:
            step_name = planned_step["step"]
            priority = planned_step.get("priority", "required")

            if priority == "skip":
                logger.info(f"[Intelligent Pipeline {pipeline_id}] Skipping {step_name}")
                continue

            # --- Runtime: guard step execution ---
            action = f"execute_{step_name}"
            gate = rt.guard(action, "orchestrator")
            rt.audit.record("step_start", actor="orchestrator", payload={
                "step": step_name, "priority": priority, "gate": gate.value,
            })
            if gate == GateOutcome.DENY:
                logger.warning(f"[Intelligent Pipeline {pipeline_id}] Step {step_name} denied by runtime")
                errors.append({"step": step_name, "error": f"Runtime guard denied in state {rt.state.value}"})
                continue

            logger.info(
                f"[Intelligent Pipeline {pipeline_id}] "
                f"Step: {step_name} ({priority})"
            )

            try:
                await self._execute_step(step_name, context)
                rt.audit.record("step_complete", actor="orchestrator",
                    payload={"step": step_name, "success": True})
            except Exception as e:
                logger.error(f"[Intelligent Pipeline {pipeline_id}] {step_name} failed: {e}")
                errors.append({"step": step_name, "error": str(e)})
                rt.audit.record("step_failed", actor="orchestrator",
                    payload={"step": step_name, "error": str(e)})

        total_time_ms = int((time.time() - overall_start) * 1000)

        # Guardrails: validate output
        report_text = context.get("report_markdown", "")
        if report_text:
            output_check = await guardrails.validate_output(report_text)
            if not output_check["valid"]:
                logger.warning(f"[Intelligent Pipeline {pipeline_id}] Output flagged by guardrails")
                errors.extend([{"step": "guardrails_output", "error": v["message"]}
                               for v in output_check.get("violations", []) if v["severity"] == "error"])

        # --- Runtime: complete ---
        rt.transition(CaseState.ARCHIVED, actor="orchestrator")
        logger.info(f"[Intelligent Pipeline {pipeline_id}] Runtime: {rt.status()}")

        # Build result (same format as fixed pipeline)
        return self._build_result(pipeline_id, encounter_id, context, errors, total_time_ms)

    async def _execute_step(self, step_name: str, context: dict):
        """Execute a single pipeline step and update context with its results.

        Routes step_name to the correct expert, awaits its execution,
        and stores the result in the shared context dict.
        """
        use_scoping = context.get("context_scoping", True)

        if step_name == "evidence_extraction":
            scoped = context_scoper.scope_for("EvidenceExtractionExpert", context) if use_scoping else context
            result = await self.evidence_expert.run(scoped)
            context["evidence"] = result.get("evidence", {})
            context["raw_text_length"] = result.get("raw_text_length", 0)
            logger.info(f"[Pipeline {context.get('pipeline_id')}] Evidence extracted: "
                        f"{len(context['evidence'].get('diagnosis_facts', []))}D + "
                        f"{len(context['evidence'].get('procedure_facts', []))}P")

        elif step_name == "timeline_reconstruction":
            scoped = context_scoper.scope_for("TimelineReconstructionExpert", context) if use_scoping else context
            result = await self.timeline_expert.run(scoped)
            context["timeline"] = result.get("timeline", {})
            logger.info(f"[Pipeline {context.get('pipeline_id')}] Timeline reconstructed: "
                        f"{result.get('event_count', 0)} events")

        elif step_name == "diagnosis_coding":
            scoped = context_scoper.scope_for("ICDDiagnosisExpert", context) if use_scoping else context
            result = await self.diagnosis_expert.run(scoped)
            context["diagnosis_candidates"] = [c for c in result.get("diagnosis_candidates", []) if isinstance(c, dict)]

        elif step_name == "procedure_coding":
            scoped = context_scoper.scope_for("ProcedureCodingExpert", context) if use_scoping else context
            result = await self.procedure_expert.run(scoped)
            context["procedure_candidates"] = [c for c in result.get("procedure_candidates", []) if isinstance(c, dict)]

        elif step_name == "homepage_ranking":
            scoped = context_scoper.scope_for("MedicalRecordHomepageExpert", context) if use_scoping else context
            result = await self.homepage_expert.run(scoped)
            context["primary_diagnosis"] = result.get("primary_diagnosis") or {}
            context["primary_diagnosis_reasoning"] = result.get("primary_diagnosis_reasoning") or {}
            context["main_procedure"] = result.get("main_procedure") or {}
            context["secondary_diagnoses"] = result.get("secondary_diagnoses", [])
            context["other_procedures"] = result.get("other_procedures", [])
            context["existing_diagnosis_review"] = result.get("existing_diagnosis_review", [])
            context["existing_procedure_review"] = result.get("existing_procedure_review", [])

        elif step_name == "evidence_verification":
            result = await self.evidence_verify_expert.run(context)
            context["verification"] = result

        elif step_name == "evidence_ranking":
            result = rank_all_evidence(
                diagnosis_candidates=context.get("diagnosis_candidates", []),
                procedure_candidates=context.get("procedure_candidates", []),
                evidence_facts=context.get("evidence", {}).get("diagnosis_facts", []),
                procedure_facts=context.get("evidence", {}).get("procedure_facts", []),
                admission_reason=context.get("admission_reason", ""),
                timeline=context.get("timeline", {}),
                primary_diagnosis=context.get("primary_diagnosis", {}),
                existing_diagnosis_codes=context.get("existing_diagnosis_codes", []),
            )
            context["evidence_ranking"] = result

        elif step_name == "disagreement_analysis":
            reasoning = context.get("primary_diagnosis_reasoning", {})
            rule_matches = {}
            if reasoning:
                pd_code = context.get("primary_diagnosis", {}).get("code", "")
                if pd_code:
                    rule_matches[pd_code] = reasoning.get("rule_basis", [])
            result = analyze_disagreements(
                diagnosis_candidates=context.get("diagnosis_candidates", []),
                procedure_candidates=context.get("procedure_candidates", []),
                primary_diagnosis=context.get("primary_diagnosis", {}),
                evidence_ranking=context.get("evidence_ranking", {}),
                gold_diagnosis_codes=context.get("encounter", {}).get("gold_diagnosis_codes", []),
                gold_procedure_codes=context.get("encounter", {}).get("gold_procedure_codes", []),
                existing_diagnosis_codes=context.get("existing_diagnosis_codes", []),
                existing_procedure_codes=context.get("existing_procedure_codes", []),
                admission_reason=context.get("admission_reason", ""),
                drg_impact=context.get("drg_impact", {}),
                rule_matches=rule_matches,
            )
            context["disagreement_analysis"] = result

        elif step_name == "confidence_calibration":
            result = calibrate_all(
                diagnosis_candidates=context.get("diagnosis_candidates", []),
                procedure_candidates=context.get("procedure_candidates", []),
                primary_diagnosis=context.get("primary_diagnosis", {}),
                evidence_ranking=context.get("evidence_ranking", {}),
                disagreement_analysis=context.get("disagreement_analysis", {}),
                primary_diag_reasoning=context.get("primary_diagnosis_reasoning", {}),
            )
            context["confidence_calibration"] = result

        elif step_name == "drg_analysis":
            result = await self.drg_expert.run(context)
            context["drg_impact"] = result

        elif step_name == "doc_gap_analysis":
            result = await self.doc_gap_expert.run(context)
            context["documentation_gaps"] = result.get("documentation_gaps", [])

        elif step_name == "report_generation":
            context["review_id"] = f"REV-{context.get('pipeline_id', 'INT')}"
            result = await self.report_expert.run(context)
            context["report_markdown"] = result.get("report_markdown", "")
            context["report_html"] = result.get("report_html", "")
            context["uncodable_items"] = result.get("uncodable_items", [])
            context["human_checklist"] = result.get("human_checklist", [])

        elif step_name == "cdi_review":
            result = await self.cdi_expert.run(context)
            context["cdi_recommendations"] = result.get("recommendations", [])

        elif step_name == "denial_analysis":
            result = await self.denial_expert.run(context)
            context["denial_analysis"] = result.get("denial_analysis", [])

        elif step_name == "audit_trail":
            result = await self.audit_expert.run(context)
            context["audit_trail"] = result.get("audit_trail", [])

        elif step_name == "hcc_risk_adjustment":
            result = await self.hcc_expert.run(context)
            context["hcc_mappings"] = result.get("hcc_mappings", [])

        else:
            logger.warning(f"[Pipeline {context.get('pipeline_id')}] Unknown step: {step_name}")

    def _build_result(self, pipeline_id: str, encounter_id: str, context: dict, errors: list, total_time_ms: int) -> dict:
        """Build the standardized pipeline result dict."""
        verification_summary = context.get("verification", {}).get("summary", {})
        return {
            "pipeline_id": pipeline_id,
            "review_id": context.get("review_id", f"REV-{pipeline_id}"),
            "encounter_id": encounter_id,
            "agent_version": settings.APP_VERSION,
            "model_used": settings.LLM_MODEL,
            "processing_time_ms": total_time_ms,
            "errors": errors,
            "evidence": context.get("evidence", {}),
            "timeline": context.get("timeline", {}),
            "diagnosis_candidates": context.get("diagnosis_candidates", []),
            "procedure_candidates": context.get("procedure_candidates", []),
            "primary_diagnosis": context.get("primary_diagnosis") or {},
            "primary_diagnosis_reasoning": context.get("primary_diagnosis_reasoning", {}),
            "main_procedure": context.get("main_procedure", {}),
            "secondary_diagnoses": context.get("secondary_diagnoses", []),
            "other_procedures": context.get("other_procedures", []),
            "existing_diagnosis_review": context.get("existing_diagnosis_review", []),
            "existing_procedure_review": context.get("existing_procedure_review", []),
            "verification": context.get("verification", {}),
            "evidence_ranking": context.get("evidence_ranking", {}),
            "disagreement_analysis": context.get("disagreement_analysis", {}),
            "confidence_calibration": context.get("confidence_calibration", {}),
            "drg_impact": context.get("drg_impact", {}),
            "documentation_gaps": context.get("documentation_gaps", []),
            "uncodable_items": context.get("uncodable_items", []),
            "human_checklist": context.get("human_checklist", []),
            "validation_summary": {
                "total_codes": verification_summary.get("total_codes", 0),
                "supported": verification_summary.get("supported", 0),
                "needs_review": verification_summary.get("needs_review", 0),
                "unsupported": verification_summary.get("unsupported", 0),
                "evidence_binding_rate": verification_summary.get("evidence_binding_rate", 0),
                "documentation_gaps": len(context.get("documentation_gaps", [])),
                "drg_risks": len(context.get("drg_impact", {}).get("drg_risks", [])),
                "pipeline_errors": len(errors),
            },
            "report_markdown": context.get("report_markdown", ""),
            "report_html": context.get("report_html", ""),
        }


# Singleton
agent_orchestrator = AgentOrchestrator()
