# iCoDer — Evaluation API Router (Phase 10 extended)
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.gold_case import GoldCase
from app.schemas.gold_case import EvaluationResult, EvaluationSummary
from app.middleware.auth import get_current_user
from app.agents.orchestrator import agent_orchestrator

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.post("/run", response_model=EvaluationSummary)
async def run_evaluation(
    gold_case_ids: list[str] | None = None,
    request: Request = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run agent evaluation against gold cases."""
    query = select(GoldCase)
    if gold_case_ids:
        query = query.where(GoldCase.case_id.in_(gold_case_ids) | GoldCase.id.in_(gold_case_ids))

    result = await db.execute(query)
    gold_cases = result.scalars().all()

    if not gold_cases:
        raise HTTPException(status_code=404, detail="No gold cases found")

    per_case_results = []
    total_cases = len(gold_cases)
    primary_diag_matches = 0
    primary_diag_soft_matches = 0
    main_proc_matches = 0
    drg_matches = 0
    secondary_recalls = []
    proc_recalls = []
    reasoning_scores = []

    for gc in gold_cases:
        if not gc.full_case_data:
            continue

        encounter_data = gc.full_case_data
        pipeline_result = await agent_orchestrator.run_pipeline(encounter_data)

        agent_primary_diag = pipeline_result.get("primary_diagnosis", {}).get("code", "")
        agent_main_proc = pipeline_result.get("main_procedure", {}).get("code", "")

        # ── primary diagnosis matching ──
        diag_match = agent_primary_diag == gc.expected_principal_diagnosis

        # Soft match: check acceptable alternatives
        alternatives = gc.acceptable_alternatives or []
        soft_match = diag_match or agent_primary_diag in alternatives
        if soft_match:
            primary_diag_soft_matches += 1
        if diag_match:
            primary_diag_matches += 1

        # ── procedure matching ──
        proc_match = True
        if gc.expected_principal_procedure and agent_main_proc:
            proc_match = agent_main_proc == gc.expected_principal_procedure
        if proc_match:
            main_proc_matches += 1

        # ── DRG matching ──
        drg_match = False
        agent_drg = pipeline_result.get("drg_impact", {}).get("expected_drg", "")
        if gc.expected_drg_group and agent_drg:
            drg_match = agent_drg == gc.expected_drg_group
        if drg_match:
            drg_matches += 1

        # ── secondary diagnosis recall ──
        expected_secondaries = gc.expected_secondary_diagnoses or []
        agent_diag_codes = {c.get("code", "") for c in pipeline_result.get("diagnosis_candidates", [])}
        if expected_secondaries:
            found = sum(1 for es in expected_secondaries if es in agent_diag_codes)
            secondary_recalls.append(found / len(expected_secondaries))

        # ── procedure recall ──
        expected_procs = gc.expected_procedure_codes or []
        agent_proc_codes = {c.get("code", "") for c in pipeline_result.get("procedure_candidates", [])}
        if expected_procs:
            found = sum(1 for ep in expected_procs if ep in agent_proc_codes)
            proc_recalls.append(found / len(expected_procs))

        # ── hallucination detection ──
        agent_codes = set()
        for c in pipeline_result.get("diagnosis_candidates", []) + pipeline_result.get("procedure_candidates", []):
            if c.get("score", 0) > 0.5:
                agent_codes.add(c.get("code", ""))

        gold_codes = {gc.expected_principal_diagnosis}
        if expected_secondaries:
            gold_codes.update(expected_secondaries)
        if gc.expected_principal_procedure:
            gold_codes.add(gc.expected_principal_procedure)
        if expected_procs:
            gold_codes.update(expected_procs)
        hallucinated = list(agent_codes - gold_codes)

        # ── reasoning score ──
        reasoning_report = pipeline_result.get("case_reasoning_report", {})
        reasoning_score = 0.0
        reasoning_expectations_met = []
        if reasoning_report:
            sections_present = sum(1 for s in ("case_overview", "clinical_timeline", "evidence_assessment",
                                                "principal_diagnosis", "disagreement_analysis", "confidence_routing")
                                    if reasoning_report.get(s))
            reasoning_score = sections_present / 6.0
            # Check if reasoning expectations are met
            for exp in (gc.reasoning_expectations or []):
                summary = reasoning_report.get("human_readable_summary", "")
                if any(kw in summary for kw in exp.replace("should cite ", "").replace("should reference ", "").split()):
                    reasoning_expectations_met.append(exp)
        reasoning_scores.append(reasoning_score)

        # ── missing codes ──
        missing_found = []
        if gc.missing_codes:
            for mc in gc.missing_codes:
                mc_code = mc.get("code", "") if isinstance(mc, dict) else mc
                if mc_code in agent_codes:
                    missing_found.append(mc_code)

        # ── evidence completeness ──
        evidence_completeness = pipeline_result.get("verification", {}).get("summary", {}).get("evidence_binding_rate", 0)
        overall_score = round(0.5 * (1 if diag_match else 0) + 0.3 * (1 if proc_match else 0) + 0.2 * evidence_completeness, 2)

        per_case_results.append({
            "case_id": gc.case_id,
            "agent_primary_diag": agent_primary_diag,
            "agent_main_proc": agent_main_proc,
            "primary_diag_match": diag_match,
            "primary_diag_soft_match": soft_match,
            "main_proc_match": proc_match,
            "secondary_diag_recall": round(secondary_recalls[-1], 2) if secondary_recalls else 0.0,
            "procedure_recall": round(proc_recalls[-1], 2) if proc_recalls else 0.0,
            "drg_match": drg_match,
            "reasoning_expectations_met": reasoning_expectations_met,
            "reasoning_score": round(reasoning_score, 2),
            "missing_codes_found": missing_found,
            "unsupported_codes_identified": [],
            "documentation_gaps_found": pipeline_result.get("documentation_gaps", []),
            "hallucinated_codes": hallucinated,
            "evidence_completeness": evidence_completeness,
            "overall_score": overall_score,
        })

        # Update gold case stats
        gc.agent_accuracy = overall_score
        gc.last_evaluated_at = request.headers.get("date", "") if request else ""
        db.add(gc)

    n = max(len(per_case_results), 1)
    diag_accuracy = round(primary_diag_matches / total_cases, 2) if total_cases > 0 else 0
    soft_accuracy = round(primary_diag_soft_matches / total_cases, 2) if total_cases > 0 else 0
    proc_accuracy = round(main_proc_matches / total_cases, 2) if total_cases > 0 else 0
    drg_rate = round(drg_matches / total_cases, 2) if total_cases > 0 else 0
    hallucination_count = sum(len(r.get("hallucinated_codes", [])) for r in per_case_results)
    total_codes = len(per_case_results)

    # Compute missing_code_recall from actual results
    total_expected_missing = 0
    total_missing_found = 0
    for i, gc in enumerate(gold_cases):
        if hasattr(gc, 'missing_codes') and gc.missing_codes:
            expected = len(gc.missing_codes)
            total_expected_missing += expected
            found = len(per_case_results[i].get("missing_codes_found", []))
            total_missing_found += found
    missing_code_recall = round(total_missing_found / total_expected_missing, 2) if total_expected_missing > 0 else 0

    # Compute unsupported_code_precision from actual results
    total_unsupported_flagged = 0
    total_expected_unsupported = 0
    for i, gc in enumerate(gold_cases):
        if hasattr(gc, 'unsupported_codes') and gc.unsupported_codes:
            total_expected_unsupported += len(gc.unsupported_codes)
        unsupported_identified = per_case_results[i].get("unsupported_codes_identified", [])
        total_unsupported_flagged += len(unsupported_identified)
    unsupported_code_precision = round(min(total_unsupported_flagged, total_expected_unsupported) / max(total_unsupported_flagged, 1), 2) if total_unsupported_flagged > 0 else 0

    # Compute documentation_gap_recall from actual results
    total_expected_gaps = 0
    total_gaps_found = 0
    for i, gc in enumerate(gold_cases):
        if hasattr(gc, 'documentation_gaps') and gc.documentation_gaps:
            total_expected_gaps += len(gc.documentation_gaps)
        gaps = per_case_results[i].get("documentation_gaps_found", [])
        total_gaps_found += len(gaps)
    documentation_gap_recall = round(total_gaps_found / total_expected_gaps, 2) if total_expected_gaps > 0 else 0

    return EvaluationSummary(
        total_cases=total_cases,
        primary_diag_accuracy=diag_accuracy,
        primary_diag_soft_accuracy=soft_accuracy,
        main_proc_accuracy=proc_accuracy,
        secondary_diag_recall_avg=round(sum(secondary_recalls) / len(secondary_recalls), 2) if secondary_recalls else 0.0,
        procedure_recall_avg=round(sum(proc_recalls) / len(proc_recalls), 2) if proc_recalls else 0.0,
        drg_match_rate=drg_rate,
        reasoning_score_avg=round(sum(reasoning_scores) / len(reasoning_scores), 2) if reasoning_scores else 0.0,
        missing_code_recall=missing_code_recall,
        unsupported_code_precision=unsupported_code_precision,
        documentation_gap_recall=documentation_gap_recall,
        evidence_completeness_avg=round(sum(r["evidence_completeness"] for r in per_case_results) / n, 2) if per_case_results else 0,
        hallucination_rate=round(hallucination_count / total_codes, 2) if total_codes > 0 else 0,
        avg_overall_score=round(sum(r["overall_score"] for r in per_case_results) / n, 2) if per_case_results else 0,
        per_case_results=per_case_results,
    )


@router.post("/batch")
async def run_batch_evaluation(
    gold_case_ids: list[str] | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run batch evaluation with CaseReasoningReport output.

    Extends /run with per-case reasoning reports and an aggregated summary
    that includes reasoning chain metrics, DRG sensitivity analysis, and
    confidence calibration quality indicators.
    """
    # Fetch gold cases
    query = select(GoldCase)
    if gold_case_ids:
        query = query.where(GoldCase.case_id.in_(gold_case_ids) | GoldCase.id.in_(gold_case_ids))
    result = await db.execute(query)
    gold_cases = result.scalars().all()

    if not gold_cases:
        raise HTTPException(status_code=404, detail="No gold cases found")

    per_case_results = []
    reasoning_details = []
    total_cases = len(gold_cases)
    primary_diag_matches = 0
    drg_impacts = 0
    escalated = 0

    for gc in gold_cases:
        if not gc.full_case_data:
            continue

        pipeline_result = await agent_orchestrator.run_pipeline(gc.full_case_data)

        agent_diag = pipeline_result.get("primary_diagnosis", {}).get("code", "")
        agent_drg = pipeline_result.get("drg_impact", {}).get("expected_drg", "")

        diag_match = agent_diag == gc.expected_principal_diagnosis
        if diag_match:
            primary_diag_matches += 1

        # Extract reasoning report details
        report = pipeline_result.get("case_reasoning_report", {})
        reasoning_details.append({
            "case_id": gc.case_id,
            "human_readable_summary": report.get("human_readable_summary", ""),
            "principal_diagnosis": report.get("principal_diagnosis", {}),
            "confidence_routing": report.get("confidence_routing", {}),
            "audit_trail": report.get("audit_trail", {}),
        })

        # Track DRG sensitivity and escalations
        if pipeline_result.get("drg_impact", {}).get("drg_sensitive"):
            drg_impacts += 1
        if pipeline_result.get("confidence_calibration", {}).get("routing", "") == "escalate":
            escalated += 1

        per_case_results.append({
            "case_id": gc.case_id,
            "agent_primary_diag": agent_diag,
            "primary_diag_match": diag_match,
            "drg_group": agent_drg,
            "routing": pipeline_result.get("confidence_calibration", {}).get("routing", "unknown"),
        })

    return {
        "summary": {
            "total_cases": total_cases,
            "primary_diag_accuracy": round(primary_diag_matches / total_cases, 2) if total_cases > 0 else 0,
            "drg_sensitive_rate": round(drg_impacts / total_cases, 2) if total_cases > 0 else 0,
            "escalation_rate": round(escalated / total_cases, 2) if total_cases > 0 else 0,
        },
        "reasoning_details": reasoning_details,
        "per_case_results": per_case_results,
    }
