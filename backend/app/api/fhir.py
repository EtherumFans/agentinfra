"""FHIR R4 Endpoint — EHR interoperability prototype.

Exposes encounter and review data as FHIR R4 resources:
- Patient
- Encounter (with diagnosis + procedure)
- Condition (diagnosis codes)
- Procedure (surgery/procedure codes)

FHIR R4 spec: https://hl7.org/fhir/R4/
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.database import get_db
from app.models.user import User
from app.models.encounter import Encounter
from app.models.review import CodingReview
from app.models.organization import Organization
from app.middleware.auth import get_current_user, get_current_organization

router = APIRouter(prefix="/api/fhir", tags=["fhir"])

FHIR_BASE = "http://localhost:8000/api/fhir"


def _fhir_ref(resource_type: str, id_: str, display: str = "") -> dict:
    ref = {"reference": f"{resource_type}/{id_}"}
    if display:
        ref["display"] = display
    return ref


def _fhir_coding(system: str, code: str, display: str = "") -> dict:
    c = {"system": system, "code": code}
    if display:
        c["display"] = display
    return c


def _iso(dt) -> str:
    if dt is None:
        return ""
    return dt.isoformat()


# ── Patient ──────────────────────────────────────────────────────────────

@router.get("/Patient")
async def fhir_patient_list(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """FHIR Patient search — one Patient per distinct patient_id in encounters."""
    result = await db.execute(
        select(Encounter.patient_id, Encounter.department, Encounter.admission_reason)
        .where(Encounter.organization_id == org.id)
        .distinct()
    )
    rows = result.all()
    entries = []
    for patient_id, department, reason in rows:
        entries.append({
            "resourceType": "Patient",
            "id": patient_id,
            "meta": {"lastUpdated": _iso(datetime.now(timezone.utc))},
            "identifier": [{"system": f"{FHIR_BASE}/Patient", "value": patient_id}],
            "active": True,
        })
    return {"resourceType": "Bundle", "type": "searchset", "total": len(entries), "entry": [{"resource": e} for e in entries]}


@router.get("/Patient/{patient_id}")
async def fhir_patient_get(
    patient_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    result = await db.execute(
        select(Encounter).where(
            Encounter.patient_id == patient_id,
            Encounter.organization_id == org.id,
        ).limit(1)
    )
    enc = result.scalar_one_or_none()
    if not enc:
        raise HTTPException(status_code=404, detail="Patient not found")

    return {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {"lastUpdated": _iso(enc.updated_at)},
        "identifier": [{"system": f"{FHIR_BASE}/Patient", "value": patient_id}],
        "active": True,
        "managingOrganization": {"display": org.name},
    }


# ── Encounter ────────────────────────────────────────────────────────────

def _encounter_to_fhir(enc: Encounter, org_name: str) -> dict:
    diagnoses = []
    procedures = []
    if enc.existing_diagnosis_codes:
        for i, d in enumerate(enc.existing_diagnosis_codes if isinstance(enc.existing_diagnosis_codes, list) else []):
            if isinstance(d, dict):
                diagnoses.append({
                    "condition": {"reference": f"#{d.get('code', f'diag-{i}')}"},
                    "use": {"coding": [_fhir_coding(
                        "http://terminology.hl7.org/CodeSystem/diagnosis-role", "AD", "Admission diagnosis"
                    )]},
                    "rank": i + 1,
                })
    if enc.existing_procedure_codes:
        for i, p in enumerate(enc.existing_procedure_codes if isinstance(enc.existing_procedure_codes, list) else []):
            if isinstance(p, dict):
                procedures.append({
                    "procedure": {"reference": f"#{p.get('code', f'proc-{i}')}"},
                    "rank": i + 1,
                })

    resource = {
        "resourceType": "Encounter",
        "id": enc.encounter_id,
        "meta": {"lastUpdated": _iso(enc.updated_at)},
        "identifier": [{"system": f"{FHIR_BASE}/Encounter", "value": enc.encounter_id}],
        "status": "finished" if enc.status == "completed" else "in-progress",
        "class": {
            "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
            "code": "IMP",
            "display": "inpatient encounter",
        },
        "subject": _fhir_ref("Patient", enc.patient_id),
        "period": {"start": _iso(enc.admission_time), "end": _iso(enc.discharge_time)},
        "serviceProvider": {"display": org_name},
        "reasonCode": [{"text": enc.admission_reason}] if enc.admission_reason else [],
        "diagnosis": diagnoses if diagnoses else None,
    }
    if procedures:
        resource["extension"] = [{
            "url": "http://hl7.org/fhir/StructureDefinition/encounter-procedure",
            "extension": [{"url": "procedure", "valueReference": p["procedure"]} for p in procedures],
        }]
    return resource


@router.get("/Encounter")
async def fhir_encounter_list(
    patient: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    q = select(Encounter).where(Encounter.organization_id == org.id).order_by(Encounter.admission_time.desc())
    if patient:
        q = q.where(Encounter.patient_id == patient)
    result = await db.execute(q)
    encounters = result.scalars().all()
    entries = [{"resource": _encounter_to_fhir(e, org.name)} for e in encounters]
    return {"resourceType": "Bundle", "type": "searchset", "total": len(entries), "entry": entries}


@router.get("/Encounter/{encounter_id}")
async def fhir_encounter_get(
    encounter_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    result = await db.execute(
        select(Encounter).where(
            Encounter.encounter_id == encounter_id,
            Encounter.organization_id == org.id,
        )
    )
    enc = result.scalar_one_or_none()
    if not enc:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return _encounter_to_fhir(enc, org.name)


# ── Condition (Diagnosis) ────────────────────────────────────────────────

@router.get("/Condition")
async def fhir_condition_list(
    patient: str = Query(""),
    encounter: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    q = (
        select(CodingReview, Encounter)
        .join(Encounter, Encounter.id == CodingReview.encounter_id)
        .where(CodingReview.organization_id == org.id)
        .order_by(CodingReview.created_at.desc())
    )
    if patient:
        q = q.where(Encounter.patient_id == patient)
    if encounter:
        q = q.where(Encounter.encounter_id == encounter)
    result = await db.execute(q)
    rows = result.all()
    entries = []
    for review, enc in rows:
        diag_code = review.primary_diagnosis_code
        diag_name = review.primary_diagnosis_name or ""
        if diag_code:
            entries.append({"resource": {
                "resourceType": "Condition",
                "id": f"cond-{review.id}",
                "meta": {"lastUpdated": _iso(review.updated_at)},
                "clinicalStatus": {"coding": [_fhir_coding(
                    "http://terminology.hl7.org/CodeSystem/condition-clinical", "active"
                )]},
                "code": {"coding": [_fhir_coding(
                    "http://hl7.org/fhir/sid/icd-10-cn", diag_code, diag_name
                )]},
                "subject": _fhir_ref("Patient", enc.patient_id),
                "encounter": _fhir_ref("Encounter", enc.encounter_id),
                "recordedDate": _iso(review.created_at),
            }})
    return {"resourceType": "Bundle", "type": "searchset", "total": len(entries), "entry": entries}


# ── Procedure ────────────────────────────────────────────────────────────

@router.get("/Procedure")
async def fhir_procedure_list(
    patient: str = Query(""),
    encounter: str = Query(""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    q = (
        select(CodingReview, Encounter)
        .join(Encounter, Encounter.id == CodingReview.encounter_id)
        .where(CodingReview.organization_id == org.id)
        .order_by(CodingReview.created_at.desc())
    )
    if patient:
        q = q.where(Encounter.patient_id == patient)
    if encounter:
        q = q.where(Encounter.encounter_id == encounter)
    result = await db.execute(q)
    rows = result.all()
    entries = []
    for review, enc in rows:
        proc_code = review.main_procedure_code
        proc_name = review.main_procedure_name or ""
        if proc_code:
            entries.append({"resource": {
                "resourceType": "Procedure",
                "id": f"proc-{review.id}",
                "meta": {"lastUpdated": _iso(review.updated_at)},
                "status": "completed",
                "code": {"coding": [_fhir_coding(
                    "http://hl7.org/fhir/sid/icd-9-cm-3", proc_code, proc_name
                )]},
                "subject": _fhir_ref("Patient", enc.patient_id),
                "encounter": _fhir_ref("Encounter", enc.encounter_id),
                "performedDateTime": _iso(review.created_at),
            }})
    return {"resourceType": "Bundle", "type": "searchset", "total": len(entries), "entry": entries}


# ── Metadata ─────────────────────────────────────────────────────────────

@router.get("/metadata")
async def fhir_metadata():
    """FHIR CapabilityStatement — declares supported resources."""
    return {
        "resourceType": "CapabilityStatement",
        "status": "draft",
        "date": "2026-05-29",
        "kind": "instance",
        "software": {"name": "iCoDer FHIR Gateway", "version": "1.0.0"},
        "fhirVersion": "4.0.1",
        "format": ["json"],
        "rest": [{
            "mode": "server",
            "resource": [
                {"type": "Patient", "interaction": [{"code": "read"}, {"code": "search-type"}]},
                {"type": "Encounter", "interaction": [{"code": "read"}, {"code": "search-type"}]},
                {"type": "Condition", "interaction": [{"code": "search-type"}, {"code": "create"}]},
                {"type": "Procedure", "interaction": [{"code": "search-type"}, {"code": "create"}]},
            ],
        }],
    }


# ── HIS Push Endpoints (POST) ─────────────────────────────────────────

@router.post("/Condition")
async def fhir_condition_create(
    body: dict,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
):
    """HIS pushes a Condition → auto-trigger coding review."""
    resource = body.get("resource", body)
    patient_id = resource.get("subject", {}).get("reference", "").replace("Patient/", "")
    coding = (resource.get("code", {}).get("coding", [{}])[0] or {})
    code = coding.get("code", "")
    name = coding.get("display", "")
    if not code:
        raise HTTPException(status_code=400, detail="Condition.code is required")

    enc = Encounter(
        patient_id=patient_id or f"his-{uuid.uuid4().hex[:8]}",
        department="HIS",
        organization_id=org.id,
        admission_reason=name,
        existing_diagnosis_codes=[{"code": code, "name": name}],
    )
    db.add(enc)
    await db.flush()

    from app.services.review_coding_service import ReviewCodingService
    from app.main import app as _app
    rt = getattr(_app.state, "platform_runtime", None)
    svc = ReviewCodingService(rt)
    review_id = ""
    try:
        result = await svc.review({"encounter_id": enc.id})
        review_id = result.get("review_id", "")
    except Exception:
        pass

    return {
        "resourceType": "Condition", "id": enc.id,
        "code": {"coding": [_fhir_coding("http://hl7.org/fhir/sid/icd-10-cn", code, name)]},
        "subject": _fhir_ref("Patient", enc.patient_id),
        "_review_id": review_id,
    }


@router.post("/Procedure")
async def fhir_procedure_create(
    body: dict,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
):
    """HIS pushes a Procedure → triggers surgical coding review."""
    resource = body.get("resource", body)
    patient_id = resource.get("subject", {}).get("reference", "").replace("Patient/", "")
    coding = (resource.get("code", {}).get("coding", [{}])[0] or {})
    code = coding.get("code", "")
    name = coding.get("display", "")
    if not code:
        raise HTTPException(status_code=400, detail="Procedure.code is required")

    enc = Encounter(
        patient_id=patient_id or f"his-{uuid.uuid4().hex[:8]}",
        department="SURGERY", organization_id=org.id,
        existing_procedure_codes=[{"code": code, "name": name}],
    )
    db.add(enc)
    await db.flush()

    from app.services.review_coding_service import ReviewCodingService
    from app.main import app as _app
    rt = getattr(_app.state, "platform_runtime", None)
    svc = ReviewCodingService(rt)
    review_id = ""
    try:
        result = await svc.review({"encounter_id": enc.id})
        review_id = result.get("review_id", "")
    except Exception:
        pass

    return {
        "resourceType": "Procedure", "id": enc.id,
        "code": {"coding": [_fhir_coding("http://hl7.org/fhir/sid/icd-9-cm-3", code, name)]},
        "subject": _fhir_ref("Patient", enc.patient_id),
        "_review_id": review_id,
    }


# ── Batch FHIR Push ───────────────────────────────────────────────────

@router.post("/Bundle")
async def fhir_bundle_create(
    body: dict,
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
):
    """HIS pushes a FHIR Bundle (multiple resources) → batch processing."""
    entries = body.get("entry", [])
    if not entries:
        raise HTTPException(status_code=400, detail="Bundle.entry is required")

    results = []
    for entry in entries:
        resource = entry.get("resource", {})
        rtype = resource.get("resourceType", "")
        if rtype in ("Condition", "Procedure"):
            endpoint = fhir_condition_create if rtype == "Condition" else fhir_procedure_create
            try:
                r = await endpoint({"resource": resource}, db=db, org=org)
                results.append({"type": rtype, "status": "created", "id": r["id"]})
            except Exception:
                results.append({"type": rtype, "status": "failed"})
        else:
            results.append({"type": rtype, "status": "skipped"})

    return {"resourceType": "Bundle", "type": "transaction-response", "entry": [{"response": r} for r in results]}


# ── Webhook Registry ──────────────────────────────────────────────────

webhook_registry: dict[str, list[str]] = {}


@router.post("/webhook/register")
async def fhir_webhook_register(
    body: dict,
    org: Organization = Depends(get_current_organization),
):
    url = body.get("url", "")
    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    webhook_registry.setdefault(org.id, []).append(url)
    return {"status": "registered", "url": url}
