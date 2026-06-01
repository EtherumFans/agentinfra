"""Evidence Pack Builder — assemble auditable evidence packs from Review data."""

import hashlib
import json
from datetime import datetime, timezone

from app.models.review import CodingReview
from app.models.evidence import ClinicalEvidence
from app.models.code_candidate import CodeCandidate


def _judgment(j) -> str:
    """Extract judgment string from enum or raw value."""
    if j is None:
        return ""
    if hasattr(j, "value"):
        return j.value
    return str(j)


def _safe(obj):
    """Return obj if truthy, else None."""
    return obj if obj else None


def _iso(ts) -> str:
    """Format datetime to ISO string."""
    if ts is None:
        return ""
    if isinstance(ts, str):
        return ts
    return ts.isoformat()


def _hash_content(content: dict) -> str:
    """SHA-256 hash of canonical JSON content."""
    raw = json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def build_evidence_pack(review: CodingReview) -> dict:
    """Build a complete evidence pack for a coding review.

    Returns a dict with:
      - metadata: review_id, exported_at, agent_version, model_used
      - input: encounter summary and raw text (if available)
      - evidence_items: all extracted clinical evidence
      - code_decisions: per-candidate coding decision chain
      - pipeline_health: step-by-step pipeline status
      - timeline: complete operation timeline
      - integrity: content hash and export info (CA signature interface)
    """
    now = datetime.now(timezone.utc)

    # ── Metadata ──
    metadata = {
        "review_id": review.review_id,
        "encounter_id": review.encounter_id,
        "agent_version": review.agent_version,
        "model_used": review.model_used,
        "exported_at": _iso(now),
        "processing_time_ms": review.processing_time_ms,
    }

    # ── Input ──
    encounter = review.encounter if hasattr(review, "encounter") and review.encounter else None
    input_data = {
        "encounter_id": review.encounter_id,
        "department": encounter.department if encounter else "",
        "admission_reason": encounter.admission_reason if encounter else "",
        "discharge_summary": encounter.discharge_summary if encounter else "",
        "existing_diagnosis_codes": encounter.existing_diagnosis_codes if encounter else [],
        "existing_procedure_codes": encounter.existing_procedure_codes if encounter else [],
    }

    # ── Evidence Items ──
    evidence_items = []
    if hasattr(review, "evidences") and review.evidences:
        for ev in review.evidences:
            evidence_items.append({
                "id": ev.id,
                "doc_type": ev.doc_type or "",
                "text": ev.text or "",
                "entity_type": ev.entity_type or "",
                "supports_codes": ev.supports_codes or [],
                "certainty": ev.certainty or "",
                "negation": ev.negation if ev.negation is not None else False,
                "confidence": ev.confidence if ev.confidence is not None else 0,
            })

    # ── Code Decisions ──
    code_decisions = []

    # Primary diagnosis
    if review.primary_diagnosis_code:
        code_decisions.append({
            "code": review.primary_diagnosis_code,
            "name": review.primary_diagnosis_name or "",
            "type": "primary_diagnosis",
            "confidence": review.primary_diagnosis_confidence or 0,
            "judgment": _judgment(review.primary_diagnosis_judgment),
            "evidence_ids": review.primary_diagnosis_evidence_ids or [],
            "reasoning": review.primary_diagnosis_reasoning or {},
        })

    # Main procedure
    if review.main_procedure_code:
        code_decisions.append({
            "code": review.main_procedure_code,
            "name": review.main_procedure_name or "",
            "type": "main_procedure",
            "confidence": review.main_procedure_confidence or 0,
            "judgment": _judgment(review.main_procedure_judgment),
            "evidence_ids": review.main_procedure_evidence_ids or [],
        })

    # Secondary diagnoses
    for item in (review.secondary_diagnoses or []):
        if isinstance(item, dict):
            code_decisions.append({
                "code": item.get("code", ""),
                "name": item.get("name", ""),
                "type": "secondary_diagnosis",
                "score": item.get("score", 0),
            })

    # Other procedures
    for item in (review.other_procedures or []):
        if isinstance(item, dict):
            code_decisions.append({
                "code": item.get("code", ""),
                "name": item.get("name", ""),
                "type": "other_procedure",
                "score": item.get("score", 0),
            })

    # Candidates with human decisions
    if hasattr(review, "candidates") and review.candidates:
        for c in review.candidates:
            cd = {
                "code": c.code,
                "name": c.name,
                "type": "candidate",
                "finding": c.finding or "",
                "score": c.score or 0,
                "status": c.status or "",
                "evidence_ids": c.evidence_ids or [],
                "rule_checks": c.rule_checks or [],
            }
            if c.human_decision:
                cd["human_review"] = {
                    "decision": c.human_decision,
                    "reason": c.human_reason or "",
                    "modified_code": c.modified_code or "",
                    "modified_name": c.modified_name or "",
                }
            code_decisions.append(cd)

    # ── Human Review ──
    human_review = {
        "status": review.human_review_status or "pending",
        "reviewed_by": review.reviewed_by or "",
        "reviewed_at": review.reviewed_at or "",
        "notes": review.reviewer_notes or "",
    }

    # ── Validation ──
    validation = review.validation_summary or {}

    # ── Evidence Ranking ──
    evidence_ranking = review.evidence_ranking or {}

    # ── Confidence Calibration ──
    confidence_calibration = review.confidence_calibration or {}

    # ── Pipeline Health ──
    errors = []
    if review.error_message:
        for err_text in review.error_message.split("; "):
            if err_text.strip():
                errors.append({"error": err_text.strip()})

    has_errors = bool(errors)
    pipeline_health = {
        "status": "failed" if has_errors else "healthy",
        "errors": errors,
    }

    # ── Timeline ──
    timeline = [
        {"step": "review_created", "timestamp": _iso(review.created_at)},
    ]
    if review.reviewed_at:
        timeline.append({"step": "human_review_completed", "timestamp": review.reviewed_at})
    timeline.append({"step": "evidence_pack_exported", "timestamp": _iso(now)})

    # ── Assemble pack ──
    pack_content = {
        "metadata": metadata,
        "input": input_data,
        "evidence_items": evidence_items,
        "code_decisions": code_decisions,
        "human_review": human_review,
        "validation": validation,
        "evidence_ranking": evidence_ranking,
        "confidence_calibration": confidence_calibration,
        "pipeline_health": pipeline_health,
        "timeline": timeline,
    }

    # ── Integrity ──
    content_hash = _hash_content(pack_content)

    return {
        **pack_content,
        "integrity": {
            "content_hash": f"sha256:{content_hash}",
            "exported_at": _iso(now),
            "unsigned_hash": content_hash,  # Reserved for CA signing layer
        },
    }
