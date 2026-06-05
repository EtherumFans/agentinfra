# iCoDer - Reviews API Router
import asyncio
import json
import logging
import uuid
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.database import get_db
from app.models.user import User
from app.models.encounter import Encounter
from app.models.review import CodingReview, ReviewJudgment
from app.models.evidence import ClinicalEvidence
from app.models.code_candidate import CodeCandidate
from app.schemas.review import (
    ReviewCreate, ReviewResponse, HumanReviewInput, ReviewCompleteInput,
    ReviewListResponse,
)
from app.middleware.auth import get_current_user, get_current_organization
from app.middleware.audit import log_action
from app.models.organization import Organization
from app.agents.orchestrator import agent_orchestrator
from app.services.task_manager import task_manager
from app.services.runtime import runtime_registry, CaseState, GateOutcome

# ── Feature-flagged routing helper ──


def _get_runtime_review_service():
    """Get ReviewCodingService and runtime config from app state."""
    from app.services.review_coding_service import ReviewCodingService
    try:
        from app.main import app as _app
        rt = _app.state.platform_runtime if hasattr(_app.state, "platform_runtime") else None
        config = _app.state.runtime_config if hasattr(_app.state, "runtime_config") else None
    except Exception:
        rt = None
        config = None
    svc = ReviewCodingService(rt)
    return svc, config


async def _run_review_new_path(encounter_data: dict) -> dict | None:
    """Run review through ReviewCodingService → PlatformRuntime."""
    import logging
    _log = logging.getLogger(__name__)
    try:
        svc, _ = _get_runtime_review_service()
        result = await svc.review(encounter_data)
        _log.info(f"ReviewCodingService result: review_id={result.get('review_id')}, source={result.get('source')}")
        return result
    except Exception as e:
        _log.warning(f"ReviewCodingService failed: {e}")
        return None


async def _run_review_with_routing(encounter_data: dict, progress_callback=None) -> dict:
    """Route review to old or new path based on runtime config."""
    import logging
    _log = logging.getLogger(__name__)
    _, config = _get_runtime_review_service()

    use_new = config and config.should_use_new_path("review") if config else False
    is_shadow = config and config.should_shadow_run("review") if config else False

    # Legacy: always use old path
    if not use_new and not is_shadow:
        # DEPRECATED: direct orchestrator call. See MIGRATION_RUNTIME.md.
        return await agent_orchestrator.run_pipeline(encounter_data, progress_callback=progress_callback)

    # Platform Runtime mode
    if use_new:
        new_result = await _run_review_new_path(encounter_data)
        if new_result:
            return new_result
        if config and config.fallback_to_legacy:
            _log.warning("ReviewCodingService failed, falling back to legacy orchestrator")
            return await agent_orchestrator.run_pipeline(encounter_data, progress_callback=progress_callback)
        raise HTTPException(status_code=500, detail="ReviewCodingService failed and fallback disabled")

    # Shadow mode: run old, fire new in background
    if is_shadow:
        import asyncio as _asyncio
        _asyncio.create_task(_run_review_new_path(encounter_data))
        return await agent_orchestrator.run_pipeline(encounter_data, progress_callback=progress_callback)

    # Shouldn't reach here
    return await agent_orchestrator.run_pipeline(encounter_data, progress_callback=progress_callback)


def _safe_dict(obj, default=None):
    """Return obj if it's a dict, otherwise return default."""
    return obj if isinstance(obj, dict) else (default or {})


def _compute_pipeline_health(errors: list) -> str:
    """Compute pipeline health from error severities.
    - healthy: no errors
    - degraded: warning-level errors only
    - failed: any critical error
    """
    if not errors:
        return "healthy"
    has_critical = any(e.get("severity") == "critical" for e in errors)
    return "failed" if has_critical else "degraded"

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


async def _build_review_response(review: CodingReview, pipeline_result: dict = None, db: AsyncSession = None) -> ReviewResponse:
    """Build ReviewResponse from pipeline result and/or database records."""
    from app.schemas.review import CodeCandidateResponse, EvidenceResponse
    candidates = []
    evidences = []

    if pipeline_result:
        for c in pipeline_result.get("diagnosis_candidates", []) + pipeline_result.get("procedure_candidates", []):
            candidates.append(CodeCandidateResponse(
                id=c.get("id", ""),
                finding=c.get("finding", c.get("procedure_name", "")),
                code_system=c.get("code_system", ""),
                code=c.get("code", ""),
                name=c.get("name", ""),
                score=c.get("score", 0),
                chapter=c.get("chapter"),
                evidence_ids=c.get("evidence_ids", []),
                status=c.get("status", "pending"),
                rule_checks=c.get("rule_checks"),
            ))
        for fact in pipeline_result.get("evidence", {}).get("diagnosis_facts", []):
            evidences.append(EvidenceResponse(
                id="", doc_type="病历", text=fact.get("evidence_text", ""),
                entity_type="diagnosis_evidence", supports_codes=[fact.get("finding", "")],
                certainty=fact.get("certainty", "suspected"),
                negation=fact.get("negation", False), confidence=0.8,
            ))
        for fact in pipeline_result.get("evidence", {}).get("procedure_facts", []):
            evidences.append(EvidenceResponse(
                id="", doc_type="手术记录", text=fact.get("evidence_text", ""),
                entity_type="procedure_evidence", supports_codes=[fact.get("procedure_name", "")],
                certainty="confirmed", negation=False, confidence=0.85,
            ))
    elif db is not None:
        # Load candidates and evidences from database
        from sqlalchemy import select as db_select
        cand_result = await db.execute(
            db_select(CodeCandidate).where(CodeCandidate.review_id == review.id)
        )
        for c in cand_result.scalars().all():
            candidates.append(CodeCandidateResponse(
                id=c.id,
                finding=c.finding,
                code_system=c.code_system,
                code=c.code,
                name=c.name,
                score=c.score,
                chapter=c.chapter,
                evidence_ids=c.evidence_ids or [],
                status=c.status,
                rule_checks=c.rule_checks,
                human_decision=c.human_decision,
                human_reason=c.human_reason,
                modified_code=c.modified_code,
                modified_name=c.modified_name,
            ))

        ev_result = await db.execute(
            db_select(ClinicalEvidence).where(ClinicalEvidence.review_id == review.id)
        )
        for e in ev_result.scalars().all():
            evidences.append(EvidenceResponse(
                id=e.id,
                doc_type=e.doc_type,
                text=e.text,
                entity_type=e.entity_type,
                supports_codes=e.supports_codes or [],
                certainty=e.certainty,
                negation=e.negation,
                confidence=e.confidence,
                start_char=e.start_char,
                end_char=e.end_char,
            ))

    # Build primary diagnosis from pipeline_result or DB record
    if pipeline_result:
        diag = pipeline_result.get("primary_diagnosis") or {}
        proc = pipeline_result.get("main_procedure") or {}
    else:
        diag = {
            "code": review.primary_diagnosis_code,
            "name": review.primary_diagnosis_name or "",
            "confidence": review.primary_diagnosis_confidence or 0,
            "evidence_ids": review.primary_diagnosis_evidence_ids or [],
        }
        proc = {
            "code": review.main_procedure_code,
            "name": review.main_procedure_name or "",
            "confidence": review.main_procedure_confidence or 0,
            "evidence_ids": review.main_procedure_evidence_ids or [],
        }

    return ReviewResponse(
        id=review.id,
        review_id=review.review_id,
        encounter_id=review.encounter_id,
        agent_version=review.agent_version,
        model_used=review.model_used,
        primary_diagnosis={"code": diag.get("code"), "name": diag.get("name", ""), "confidence": diag.get("confidence", 0), "evidence_ids": diag.get("evidence_ids", []), "judgment": "supported" if diag.get("confidence", 0) > 0.7 else "needs_review", "reasoning": pipeline_result.get("primary_diagnosis_reasoning") if pipeline_result else None},
        main_procedure={"code": proc.get("code"), "name": proc.get("name", ""), "confidence": proc.get("confidence", 0), "evidence_ids": proc.get("evidence_ids", []), "judgment": "supported" if proc.get("confidence", 0) > 0.7 else "needs_review"},
        secondary_diagnoses=[{"code": c["code"], "name": c["name"], "score": c["score"]} for c in (pipeline_result.get("secondary_diagnoses", []) if pipeline_result else [])] if pipeline_result else review.secondary_diagnoses or [],
        other_procedures=[{"code": c["code"], "name": c["name"], "score": c["score"]} for c in (pipeline_result.get("other_procedures", []) if pipeline_result else [])] if pipeline_result else review.other_procedures or [],
        diagnosis_analysis=[{"finding": c["finding"], "code": c["code"], "name": c["name"], "score": c["score"]} for c in (pipeline_result.get("diagnosis_candidates", []) if pipeline_result else [])] if pipeline_result else review.diagnosis_analysis or [],
        procedure_analysis=[{"procedure": c.get("procedure_name", ""), "code": c["code"], "name": c["name"], "score": c["score"]} for c in (pipeline_result.get("procedure_candidates", []) if pipeline_result else [])] if pipeline_result else review.procedure_analysis or [],
        documentation_gaps=pipeline_result.get("documentation_gaps", []) if pipeline_result else review.documentation_gaps or [],
        uncodable_items=pipeline_result.get("uncodable_items", []) if pipeline_result else review.uncodable_items or [],
        drg_impact=pipeline_result.get("drg_impact", {}) if pipeline_result else review.drg_impact or {},
        human_checklist=pipeline_result.get("human_checklist", []) if pipeline_result else review.human_checklist or [],
        validation_summary=pipeline_result.get("validation_summary", {}) if pipeline_result else review.validation_summary or {},
        report_markdown=review.report_markdown,
        report_html=review.report_html,
        human_review_status=review.human_review_status,
        reviewed_by=review.reviewed_by,
        reviewer_notes=review.reviewer_notes,
        processing_time_ms=review.processing_time_ms,
        error_message=review.error_message,
        evidence_ranking=pipeline_result.get("evidence_ranking") if pipeline_result else (review.evidence_ranking or None),
        confidence_calibration=pipeline_result.get("confidence_calibration") if pipeline_result else (review.confidence_calibration or None),
        pipeline_health=_compute_pipeline_health(pipeline_result.get("errors", []) if pipeline_result else []),
        candidates=candidates,
        evidences=evidences,
        created_at=review.created_at,
        updated_at=review.updated_at,
    )


@router.post("", status_code=201)
async def create_review(
    data: ReviewCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    async_mode: bool = Query(False, alias="async", description="Run pipeline asynchronously"),
):
    """Run the coding audit pipeline on an encounter.

    Set ?async=true to run in background — returns immediately with task_id.
    Poll GET /reviews/{id}/status or connect WS /ws/reviews/{task_id} for progress.
    """
    # Find encounter with eager-loaded documents
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Encounter)
        .options(selectinload(Encounter.documents))
        .where(
            Encounter.organization_id == current_org.id,
            (Encounter.encounter_id == data.encounter_id) | (Encounter.id == data.encounter_id)
        )
    )
    encounter = result.scalar_one_or_none()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    # Build encounter_data for the agent pipeline
    encounter_data = {
        "encounter_id": encounter.encounter_id,
        "department": encounter.department,
        "patient_id": encounter.patient_id,
        "admission_time": encounter.admission_time.isoformat() if encounter.admission_time else None,
        "discharge_time": encounter.discharge_time.isoformat() if encounter.discharge_time else None,
        "admission_reason": encounter.admission_reason,
        "documents": [
            {"doc_type": d.doc_type, "title": d.title, "content": d.content, "doc_order": d.doc_order}
            for d in encounter.documents
        ],
        "existing_diagnosis_codes": encounter.existing_diagnosis_codes or [],
        "existing_procedure_codes": encounter.existing_procedure_codes or [],
    }

    # Run the agent pipeline (sync or async)
    if async_mode:
        task_id = await task_manager.create_task("coding_review", {
            "encounter_id": encounter.encounter_id,
            "department": encounter.department,
        })

        async def _run_pipeline_background():
            """Execute pipeline + save results in background, reporting progress."""
            from app.database import async_session_factory
            try:
                await task_manager.update_progress(task_id, 5, "启动编码审核管道")

                async def _on_progress(pct, step):
                    await task_manager.update_progress(task_id, pct, step)

                pipeline_result = await _run_review_with_routing(
                    encounter_data, progress_callback=_on_progress,
                )

                await task_manager.update_progress(task_id, 90, "保存审核结果")
                # Use a fresh DB session for background save
                async with async_session_factory() as bg_db:
                    review_id_bg = pipeline_result.get("review_id", task_id)
                    review_bg = CodingReview(
                        organization_id=current_org.id,
                        review_id=review_id_bg,
                        encounter_id=encounter.id,
                        agent_version=pipeline_result.get("agent_version", "1.0.0"),
                        model_used=pipeline_result.get("model_used", "unknown"),
                        primary_diagnosis_code=_safe_dict(pipeline_result.get("primary_diagnosis")).get("code"),
                        primary_diagnosis_name=_safe_dict(pipeline_result.get("primary_diagnosis")).get("name"),
                        primary_diagnosis_confidence=_safe_dict(pipeline_result.get("primary_diagnosis")).get("confidence", 0),
                        primary_diagnosis_evidence_ids=_safe_dict(pipeline_result.get("primary_diagnosis")).get("evidence_ids", []),
                        primary_diagnosis_judgment=ReviewJudgment.SUPPORTED if _safe_dict(pipeline_result.get("primary_diagnosis")).get("confidence", 0) > 0.7 else ReviewJudgment.NEEDS_REVIEW,
                        primary_diagnosis_reasoning=pipeline_result.get("primary_diagnosis_reasoning"),
                        main_procedure_code=_safe_dict(pipeline_result.get("main_procedure")).get("code"),
                        main_procedure_name=_safe_dict(pipeline_result.get("main_procedure")).get("name"),
                        main_procedure_confidence=_safe_dict(pipeline_result.get("main_procedure")).get("confidence", 0),
                        main_procedure_evidence_ids=_safe_dict(pipeline_result.get("main_procedure")).get("evidence_ids", []),
                        main_procedure_judgment=ReviewJudgment.SUPPORTED if _safe_dict(pipeline_result.get("main_procedure")).get("confidence", 0) > 0.7 else ReviewJudgment.NEEDS_REVIEW,
                        secondary_diagnoses=[{"code": c["code"], "name": c["name"], "score": c["score"]} for c in pipeline_result.get("secondary_diagnoses", [])],
                        other_procedures=[{"code": c["code"], "name": c["name"], "score": c["score"]} for c in pipeline_result.get("other_procedures", [])],
                        diagnosis_analysis=[{"finding": c.get("finding", ""), "code": c["code"], "name": c["name"], "score": c["score"], "evidence": c.get("evidence_text", "")} for c in pipeline_result.get("diagnosis_candidates", [])],
                        procedure_analysis=[{"procedure": c.get("procedure_name", ""), "code": c["code"], "name": c["name"], "score": c["score"]} for c in pipeline_result.get("procedure_candidates", [])],
                        documentation_gaps=pipeline_result.get("documentation_gaps", []),
                        uncodable_items=pipeline_result.get("uncodable_items", []),
                        drg_impact=pipeline_result.get("drg_impact", {}),
                        human_checklist=pipeline_result.get("human_checklist", []),
                        validation_summary=pipeline_result.get("validation_summary", {}),
                        report_markdown=pipeline_result.get("report_markdown", ""),
                        report_html=pipeline_result.get("report_html", ""),
                        processing_time_ms=pipeline_result.get("processing_time_ms", 0),
                        error_message="; ".join([e["error"] for e in pipeline_result.get("errors", [])]) if pipeline_result.get("errors") else None,
                    )
                    bg_db.add(review_bg)
                    await bg_db.commit()
                    # --- Runtime persistence: flush async pipeline ---
                    pipeline_id_bg = pipeline_result.get("pipeline_id", "")
                    if pipeline_id_bg:
                        rt_bg = runtime_registry.get(pipeline_id_bg)
                        if rt_bg:
                            rt_bg._total_processing_ms = pipeline_result.get("processing_time_ms", 0)
                            rt_bg._total_errors = len(pipeline_result.get("errors", []))
                            await rt_bg.flush_to_db(bg_db)

                    await bg_db.refresh(review_bg)

                    await task_manager.complete_task(task_id, {
                        "review_id": review_id_bg,
                        "encounter_id": encounter.encounter_id,
                        "primary_diagnosis": pipeline_result.get("primary_diagnosis"),
                        "main_procedure": pipeline_result.get("main_procedure"),
                    })
            except Exception as e:
                logger.exception(f"Async pipeline failed for task {task_id}")
                await task_manager.fail_task(task_id, str(e))

        asyncio.ensure_future(_run_pipeline_background())
        return {
            "task_id": task_id,
            "status": "pending",
            "message": "编码审核管道已启动",
            "review_id": None,
            "encounter_id": encounter.encounter_id,
        }

    # --- Synchronous mode ---
    pipeline_result = await _run_review_with_routing(encounter_data)
    review_id = pipeline_result["review_id"]
    review = CodingReview(
        organization_id=current_org.id,
        review_id=review_id,
        encounter_id=encounter.id,
        agent_version=pipeline_result["agent_version"],
        model_used=pipeline_result["model_used"],
        primary_diagnosis_code=_safe_dict(pipeline_result.get("primary_diagnosis")).get("code"),
        primary_diagnosis_name=_safe_dict(pipeline_result.get("primary_diagnosis")).get("name"),
        primary_diagnosis_confidence=_safe_dict(pipeline_result.get("primary_diagnosis")).get("confidence", 0),
        primary_diagnosis_evidence_ids=_safe_dict(pipeline_result.get("primary_diagnosis")).get("evidence_ids", []),
        primary_diagnosis_judgment=ReviewJudgment.SUPPORTED if _safe_dict(pipeline_result.get("primary_diagnosis")).get("confidence", 0) > 0.7 else ReviewJudgment.NEEDS_REVIEW,
        primary_diagnosis_reasoning=pipeline_result.get("primary_diagnosis_reasoning"),
        main_procedure_code=_safe_dict(pipeline_result.get("main_procedure")).get("code"),
        main_procedure_name=_safe_dict(pipeline_result.get("main_procedure")).get("name"),
        main_procedure_confidence=_safe_dict(pipeline_result.get("main_procedure")).get("confidence", 0),
        main_procedure_evidence_ids=_safe_dict(pipeline_result.get("main_procedure")).get("evidence_ids", []),
        main_procedure_judgment=ReviewJudgment.SUPPORTED if _safe_dict(pipeline_result.get("main_procedure")).get("confidence", 0) > 0.7 else ReviewJudgment.NEEDS_REVIEW,
        secondary_diagnoses=[{"code": c["code"], "name": c["name"], "score": c["score"]} for c in pipeline_result.get("secondary_diagnoses", [])],
        other_procedures=[{"code": c["code"], "name": c["name"], "score": c["score"]} for c in pipeline_result.get("other_procedures", [])],
        diagnosis_analysis=[{"finding": c.get("finding", ""), "code": c["code"], "name": c["name"], "score": c["score"], "evidence": c.get("evidence_text", "")} for c in pipeline_result.get("diagnosis_candidates", [])],
        procedure_analysis=[{"procedure": c.get("procedure_name", ""), "code": c["code"], "name": c["name"], "score": c["score"]} for c in pipeline_result.get("procedure_candidates", [])],
        documentation_gaps=pipeline_result.get("documentation_gaps", []),
        uncodable_items=pipeline_result.get("uncodable_items", []),
        drg_impact=pipeline_result.get("drg_impact", {}),
        human_checklist=pipeline_result.get("human_checklist", []),
        validation_summary=pipeline_result.get("validation_summary", {}),
        report_markdown=pipeline_result.get("report_markdown", ""),
        report_html=pipeline_result.get("report_html", ""),
        processing_time_ms=pipeline_result.get("processing_time_ms", 0),
        error_message="; ".join([e["error"] for e in pipeline_result.get("errors", [])]) if pipeline_result.get("errors") else None,
        evidence_ranking=pipeline_result.get("evidence_ranking"),
        confidence_calibration=pipeline_result.get("confidence_calibration"),
    )
    db.add(review)
    await db.commit()

    # Persist runtime
    pipeline_id = pipeline_result.get("pipeline_id", "")
    if pipeline_id:
        rt = runtime_registry.get(pipeline_id)
        if rt:
            rt._total_processing_ms = pipeline_result.get("processing_time_ms", 0)
            rt._total_errors = len(pipeline_result.get("errors", []))
            await rt.flush_to_db(db)

    await db.refresh(review)
    response = await _build_review_response(review, pipeline_result)
    response.cross_table_view = await _build_cross_table_view(db, pipeline_result)
    return response


class BatchReviewRequest(BaseModel):
    encounter_ids: list[str] = Field(..., min_length=1, max_length=50, description="List of encounter IDs to review")


# ---- Transcripts (async batch audio) ----

class BatchTranscriptRequest(BaseModel):
    audio_urls: list[str] = Field(..., min_length=1, max_length=100)
    language: str = "zh-CN"
    webhook_url: str = ""


@router.post("/transcripts", status_code=201)
async def batch_transcribe(
    body: BatchTranscriptRequest,
    current_user: User = Depends(get_current_user),
):
    """Submit batch audio files for async transcription."""
    task_ids = []
    for i, url in enumerate(body.audio_urls):
        tid = await task_manager.create_task("transcription", {
            "audio_url": url,
            "language": body.language,
            "index": i,
        })
        task_ids.append(tid)
        # In production, queue these for background processing
        asyncio.ensure_future(_process_transcription_task(tid, url, body.language))

    return {
        "tasks_created": len(task_ids),
        "task_ids": task_ids,
        "status": "processing",
        "webhook_url": body.webhook_url,
    }


async def _process_transcription_task(task_id: str, _audio_url: str, language: str):
    """Process a single transcription task (stub — requires ASR integration)."""
    try:
        await task_manager.update_progress(task_id, 10, f"开始转写 (语言: {language})")
        # In production, download audio and call ASR service
        await task_manager.update_progress(task_id, 50, "ASR 处理中...")
        # Simulate completion
        await task_manager.update_progress(task_id, 100, "转写完成")
        await task_manager.complete_task(task_id, {
            "transcript": "[转录文本将由 ASR 引擎生成]",
            "language": language,
        })
    except Exception as e:
        await task_manager.fail_task(task_id, str(e))


@router.post("/batch", status_code=201)
async def create_batch_review(
    body: BatchReviewRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run the coding audit pipeline on multiple encounters in parallel."""
    from sqlalchemy.orm import selectinload

    task_ids = []
    for eid in body.encounter_ids:
        result = await db.execute(
            select(Encounter).options(selectinload(Encounter.documents)).where(
                (Encounter.encounter_id == eid) | (Encounter.id == eid)
            )
        )
        encounter = result.scalar_one_or_none()
        if not encounter:
            continue

        task_id = await task_manager.create_task("coding_review", {
            "encounter_id": encounter.encounter_id,
        })

        encounter_data = {
            "encounter_id": encounter.encounter_id,
            "department": encounter.department,
            "documents": [{"doc_type": d.doc_type, "title": d.title, "content": d.content} for d in encounter.documents],
            "existing_diagnosis_codes": encounter.existing_diagnosis_codes or [],
            "existing_procedure_codes": encounter.existing_procedure_codes or [],
        }

        async def _batch_run(enc_data, tid):
            from app.database import async_session_factory
            try:
                await task_manager.update_progress(tid, 5, "启动批量编码审核")
                async def _on_progress(pct, step):
                    await task_manager.update_progress(tid, min(95, pct), step)
                pipeline_result = await _run_review_with_routing(enc_data, progress_callback=_on_progress)
                await task_manager.update_progress(tid, 95, "保存结果")
                async with async_session_factory() as bg_db:
                    review_id_bg = pipeline_result.get("review_id", tid)
                    await task_manager.complete_task(tid, {
                        "review_id": review_id_bg,
                        "encounter_id": enc_data["encounter_id"],
                        "primary_diagnosis": pipeline_result.get("primary_diagnosis"),
                        "main_procedure": pipeline_result.get("main_procedure"),
                    })
            except Exception as e:
                logger.exception(f"Batch task {tid} failed")
                await task_manager.fail_task(tid, str(e))

        asyncio.ensure_future(_batch_run(encounter_data, task_id))
        task_ids.append(task_id)

    return {
        "batch_size": len(body.encounter_ids),
        "tasks_created": len(task_ids),
        "task_ids": task_ids,
        "status": "processing",
    }


@router.get("", response_model=ReviewListResponse)
async def list_reviews(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    query = select(CodingReview).where(CodingReview.organization_id == current_org.id)
    count_query = select(func.count(CodingReview.id)).where(CodingReview.organization_id == current_org.id)
    if status:
        query = query.where(CodingReview.human_review_status == status)
        count_query = count_query.where(CodingReview.human_review_status == status)

    query = query.order_by(CodingReview.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

    total = (await db.execute(count_query)).scalar()
    reviews = (await db.execute(query)).scalars().all()

    items = []
    for r in reviews:
        items.append(await _build_review_response(r, db=db))

    return ReviewListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    result = await db.execute(
        select(CodingReview).where(
            CodingReview.organization_id == current_org.id,
            (CodingReview.review_id == review_id) | (CodingReview.id == review_id)
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    resp = await _build_review_response(review, db=db)
    # Build cross-table view from stored primary diagnosis
    if review.primary_diagnosis_code:
        resp.cross_table_view = await _build_cross_table_from_code(db, review.primary_diagnosis_code)
    return resp


@router.put("/{review_id}/candidates/{candidate_id}/review", response_model=ReviewResponse)
async def review_candidate(
    review_id: str,
    candidate_id: str,
    data: HumanReviewInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Human reviewer confirms, rejects, or modifies a code candidate."""
    result = await db.execute(
        select(CodingReview).where(CodingReview.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    result = await db.execute(
        select(CodeCandidate).where(CodeCandidate.id == candidate_id)
    )
    candidate = result.scalar_one_or_none()
    if not candidate:
        raise HTTPException(status_code=404, detail="Candidate not found")

    # --- Runtime guard: human review of a code candidate ---
    pipeline_id = _extract_pipeline_id(review.review_id)
    rt = runtime_registry.get_or_create(pipeline_id)
    reviewer_name = current_user.full_name or current_user.username
    rt.check_timeout()  # Gate: review must happen within timeout window
    review_action = f"review_code_{data.decision}"
    gate = rt.guard("confirm_decision", reviewer_name)
    rt.audit.record("code_reviewed", actor=reviewer_name, payload={
        "candidate_id": candidate_id,
        "code": candidate.code,
        "decision": data.decision,
        "reason": data.reason[:200] if data.reason else "",
        "gate": gate.value,
    })
    if gate == GateOutcome.DENY:
        raise HTTPException(status_code=403, detail=f"Runtime guard denied: cannot review codes in state {rt.state.value}")
    if gate == GateOutcome.REVIEW:
        rt.human_confirm("confirm_decision", reviewer=reviewer_name, rationale=f"Reviewed code {candidate.code}: {data.decision}")
        rt.transition(CaseState.DECISION_CONFIRMED, actor=reviewer_name)

    candidate.human_decision = data.decision
    candidate.human_reason = data.reason
    if data.decision == "modified":
        candidate.modified_code = data.modified_code
        candidate.modified_name = data.modified_name

    await log_action(db, current_user.id, current_user.username, "code.review",
                     "code_candidate", candidate.id,
                     details={"decision": data.decision, "reason": data.reason},
                     ip_address=request.client.host if request.client else None)

    # --- Runtime persistence: flush ---
    await rt.flush_to_db(db)

    db.add(candidate)
    await db.refresh(review)
    return await _build_review_response(review, db=db)


@router.put("/{review_id}/complete", response_model=ReviewResponse)
async def complete_review(
    review_id: str,
    data: ReviewCompleteInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a review as completed with reviewer notes."""
    result = await db.execute(
        select(CodingReview).where(CodingReview.id == review_id)
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # --- Runtime guard: complete review ---
    pipeline_id = _extract_pipeline_id(review.review_id)
    rt = runtime_registry.get_or_create(pipeline_id)
    reviewer_name = current_user.full_name or current_user.username
    rt.check_timeout()  # Gate: completion must happen within timeout window
    gate = rt.guard("confirm_decision", reviewer_name)
    rt.audit.record("review_completed", actor=reviewer_name, payload={
        "review_id": review.review_id,
        "status": data.human_review_status,
        "gate": gate.value,
    })
    if gate == GateOutcome.DENY:
        raise HTTPException(status_code=403, detail=f"Runtime guard denied: cannot complete review in state {rt.state.value}")
    if gate == GateOutcome.REVIEW:
        logger.info(f"[Runtime] Review {review.review_id} requires human confirmation to complete")
        rt.human_confirm("confirm_decision", reviewer=reviewer_name, rationale=f"Completing review: {data.human_review_status}")
    rt.transition(CaseState.DECISION_CONFIRMED, actor=reviewer_name)
    rt.transition(CaseState.ARCHIVED, actor=reviewer_name)

    review.human_review_status = data.human_review_status
    review.reviewed_by = current_user.id
    review.reviewer_notes = data.reviewer_notes
    review.reviewed_at = request.headers.get("date", "")

    await log_action(db, current_user.id, current_user.username, "review.complete",
                     "review", review.id,
                     ip_address=request.client.host if request.client else None)

    # --- Runtime persistence: flush ---
    await rt.flush_to_db(db)

    # Update encounter status
    result = await db.execute(select(Encounter).where(Encounter.id == review.encounter_id))
    encounter = result.scalar_one_or_none()
    if encounter:
        encounter.status = "completed"
        db.add(encounter)

    db.add(review)
    await db.refresh(review)
    return await _build_review_response(review, db=db)


@router.get("/{review_id}/report/markdown")
async def get_report_markdown(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CodingReview).where(
            (CodingReview.review_id == review_id) | (CodingReview.id == review_id)
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(content=review.report_markdown or "No report generated", media_type="text/markdown")


@router.get("/{review_id}/report/html")
async def get_report_html(
    review_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CodingReview).where(
            (CodingReview.review_id == review_id) | (CodingReview.id == review_id)
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=review.report_html or "<p>No report generated</p>")


@router.get("/{review_id}/evidence-pack")
async def get_evidence_pack(
    review_id: str,
    format: str = Query("json", enum=["json"], description="Export format (json only; pdf/ofd planned)"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export a complete audit evidence pack for a coding review.

    Returns structured JSON containing:
    - metadata: review_id, agent_version, model_used, processing_time
    - input: encounter summary and codes
    - evidence_items: all extracted clinical evidence
    - code_decisions: per-code decision chain (reasoning, validation, human review)
    - pipeline_health: step-level pipeline status
    - timeline: operation timeline from creation to export
    - integrity: SHA-256 content hash (unsigned — CA signing layer interface)
    """
    from app.services.evidence_pack import build_evidence_pack

    result = await db.execute(
        select(CodingReview).where(
            (CodingReview.review_id == review_id) | (CodingReview.id == review_id)
        )
    )
    review = result.scalar_one_or_none()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    # Eager-load relationships for evidence and candidates
    await db.refresh(review, attribute_names=["evidences", "candidates", "encounter"])

    pack = build_evidence_pack(review)

    if format == "json":
        from fastapi.responses import JSONResponse
        return JSONResponse(
            content=pack,
            headers={
                "Content-Disposition": f'attachment; filename="evidence-pack-{review.review_id}.json"',
                "X-Content-Hash": pack["integrity"]["content_hash"],
            },
        )

    raise HTTPException(status_code=400, detail=f"Unsupported format: {format}. Supported: json")


# ===== Async Task Status & Progress =====

@router.get("/tasks/{task_id}")
async def get_task_status(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Poll the status of an async coding review task."""
    task = task_manager.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    result = task_manager.get_result(task_id)
    return {**task, "result_summary": result}


@router.websocket("/ws/reviews/{task_id}")
async def review_progress_ws(websocket: WebSocket, task_id: str):
    """WebSocket for real-time pipeline progress."""
    await websocket.accept()
    await task_manager.subscribe(task_id, websocket)
    try:
        while True:
            # Keep connection alive — client can send ping
            data = await websocket.receive_text()
            if json.loads(data).get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        await task_manager.unsubscribe(task_id, websocket)


async def _build_cross_table_from_code(db: AsyncSession, code: str) -> dict:
    """Build cross-table view from a single code."""
    from app.models.code_table import CodeTable
    from app.services.code_dictionary import code_dict_service

    result = await db.execute(
        select(CodeTable).where(CodeTable.is_active == True).order_by(CodeTable.is_default.desc())
    )
    tables = result.scalars().all()

    cross_table = {}
    for ct in tables:
        found = await code_dict_service.explore_code(code, ct.code_system)
        cross_table[ct.name] = {
            "table_id": ct.id, "table_name": ct.name,
            "code_system": ct.code_system, "source_type": ct.source_type,
            "institution": ct.institution,
            "code": found.get("code") if found else code,
            "name": found.get("name", "") if found else "",
            "valid": found.get("valid", False) if found else False,
            "is_default": ct.is_default,
        }
    return {"source_code": code, "tables": cross_table}


async def _build_cross_table_view(db: AsyncSession, pipeline_result: dict) -> dict:
    """Map primary diagnosis across all active code tables."""
    from app.models.code_table import CodeTable
    from app.services.code_dictionary import code_dict_service

    primary = pipeline_result.get("primary_diagnosis", {}) if pipeline_result else {}
    primary_code = primary.get("code", "")
    if not primary_code:
        return {"source_code": "", "tables": {}}

    result = await db.execute(
        select(CodeTable).where(CodeTable.is_active == True).order_by(CodeTable.is_default.desc())
    )
    tables = result.scalars().all()

    cross_table = {}
    for ct in tables:
        found = await code_dict_service.explore_code(primary_code, ct.code_system)
        cross_table[ct.name] = {
            "table_id": ct.id,
            "table_name": ct.name,
            "code_system": ct.code_system,
            "source_type": ct.source_type,
            "institution": ct.institution,
            "code": found.get("code") if found else primary_code,
            "name": found.get("name", "") if found else "",
            "valid": found.get("valid", False) if found else False,
            "is_default": ct.is_default,
        }

    # Also map all candidates
    candidates_view = []
    for cand in pipeline_result.get("diagnosis_candidates", [])[:5]:
        code = cand.get("code", "")
        if not code: continue
        tbl_results = {}
        for ct in tables:
            found = await code_dict_service.explore_code(code, ct.code_system)
            tbl_results[ct.name] = {
                "code": found.get("code") if found else code,
                "name": found.get("name", "") if found else "",
                "valid": found.get("valid", False) if found else False,
            }
        candidates_view.append({"code": code, "tables": tbl_results})

    return {
        "source_code": primary_code,
        "source_name": primary.get("name", ""),
        "tables": cross_table,
        "candidates": candidates_view,
    }


def _extract_pipeline_id(review_id: str) -> str:
    """Extract the pipeline_id from a review_id.

    Orchestrator creates review_ids in format 'REV-{pipeline_id}'.
    AgentRunner uses 'AR-{hex}' or 'ARS-{hex}'.
    Falls back to using the review_id directly if no prefix is recognized.
    """
    for prefix in ("REV-", "INT-", "AR-", "ARS-"):
        if review_id.startswith(prefix):
            return review_id[len(prefix):]
    return review_id
