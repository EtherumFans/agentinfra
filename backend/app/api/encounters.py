# iCoDer - Encounters API Router
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.encounter import Encounter, Document
from app.schemas.encounter import (
    EncounterCreate, EncounterTextInput, EncounterResponse,
    EncounterListResponse, DocumentResponse,
)
from app.middleware.auth import get_current_user, get_current_organization
from app.middleware.audit import log_action
from app.services.tenant_scoper import set_org_context, scope_query
from app.models.organization import Organization

router = APIRouter(prefix="/api/encounters", tags=["encounters"])


@router.post("", response_model=EncounterResponse, status_code=201)
async def create_encounter(
    data: EncounterCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Create a new encounter with documents and existing codes."""
    from datetime import datetime
    import uuid
    # Phase A1A Gate 4.4 — encrypt high-PHI fields at write time.
    # encrypt_phi returns plaintext when no key is configured (local-dev
    # fallback); cloud mode refuses to boot without a key so the cloud
    # path is always encrypted.
    from app.services.phi_encryption import encrypt_phi

    encounter_id = f"ENC-{uuid.uuid4().hex[:12].upper()}"

    encounter = Encounter(
        organization_id=current_org.id,
        encounter_id=encounter_id,
        patient_id=data.patient_id,
        department=data.department,
        admission_time=datetime.fromisoformat(data.admission_time) if data.admission_time else None,
        discharge_time=datetime.fromisoformat(data.discharge_time) if data.discharge_time else None,
        admission_reason=encrypt_phi(data.admission_reason) if data.admission_reason else None,
        existing_diagnosis_codes=[c.model_dump() for c in data.existing_diagnosis_codes],
        existing_procedure_codes=[c.model_dump() for c in data.existing_procedure_codes],
        submitted_by=current_user.id,
    )
    db.add(encounter)
    await db.flush()

    for i, doc in enumerate(data.documents):
        document = Document(
            organization_id=current_org.id,
            encounter_id=encounter.id,
            doc_type=doc.doc_type,
            title=doc.title,
            content=encrypt_phi(doc.content),
            doc_order=i,
        )
        db.add(document)

    await log_action(db, current_user.id, current_user.username, "encounter.create",
                     "encounter", encounter.id,
                     ip_address=request.client.host if request.client else None)

    await db.refresh(encounter)
    return EncounterResponse.from_encounter(encounter, data.documents)


@router.post("/text", response_model=EncounterResponse, status_code=201)
async def create_encounter_from_text(
    data: EncounterTextInput,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    """Create encounter from raw text paste (simplified input)."""
    import uuid
    from app.services.phi_encryption import encrypt_phi

    encounter_id = f"ENC-{uuid.uuid4().hex[:12].upper()}"
    encounter = Encounter(
        organization_id=current_org.id,
        encounter_id=encounter_id,
        patient_id=data.patient_id,
        department=data.department,
        existing_diagnosis_codes=[c.model_dump() for c in data.existing_diagnosis_codes],
        existing_procedure_codes=[c.model_dump() for c in data.existing_procedure_codes],
        submitted_by=current_user.id,
    )
    db.add(encounter)
    await db.flush()

    # Parse raw text into documents (simple split by common separators)
    text = data.raw_text
    if "入院记录" in text or "出院记录" in text or "手术记录" in text:
        # Already structured
        doc = Document(
            organization_id=current_org.id,
            encounter_id=encounter.id,
            doc_type="住院病历",
            title="完整病历",
            content=encrypt_phi(text),
            doc_order=0,
        )
        db.add(doc)
    else:
        doc = Document(
            organization_id=current_org.id,
            encounter_id=encounter.id,
            doc_type="出院小结",
            title="病历文本",
            content=encrypt_phi(text),
            doc_order=0,
        )
        db.add(doc)

    await log_action(db, current_user.id, current_user.username, "encounter.create_text",
                     "encounter", encounter.id,
                     ip_address=request.client.host if request.client else None)

    await db.refresh(encounter)
    return EncounterResponse.from_encounter(encounter, [doc])


@router.get("", response_model=EncounterListResponse)
async def list_encounters(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    query = select(Encounter).where(Encounter.organization_id == current_org.id)
    count_query = select(func.count(Encounter.id)).where(Encounter.organization_id == current_org.id)

    if status:
        query = query.where(Encounter.status == status)
        count_query = count_query.where(Encounter.status == status)

    query = query.order_by(Encounter.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

    total = (await db.execute(count_query)).scalar()
    encounters = (await db.execute(query)).scalars().all()

    return EncounterListResponse(
        items=[EncounterResponse.from_encounter(e, []) for e in encounters],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{encounter_id}", response_model=EncounterResponse)
async def get_encounter(
    encounter_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    # Try by encounter_id string first, then by internal id
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(Encounter)
        .options(selectinload(Encounter.documents))
        .where(
            Encounter.organization_id == current_org.id,
            (Encounter.encounter_id == encounter_id) | (Encounter.id == encounter_id)
        )
    )
    encounter = result.scalar_one_or_none()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")
    return EncounterResponse.from_encounter(encounter, encounter.documents)


@router.delete("/{encounter_id}", status_code=204)
async def delete_encounter(
    encounter_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
):
    result = await db.execute(
        select(Encounter).where(
            Encounter.id == encounter_id,
            Encounter.organization_id == current_org.id,
        )
    )
    encounter = result.scalar_one_or_none()
    if not encounter:
        raise HTTPException(status_code=404, detail="Encounter not found")

    await log_action(db, current_user.id, current_user.username, "encounter.delete",
                     "encounter", encounter.id,
                     ip_address=request.client.host if request.client else None)

    await db.delete(encounter)
    return None
