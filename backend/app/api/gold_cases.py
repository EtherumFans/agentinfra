# DEPRECATED (P1.3 Stage 5, 2026-07-02) — F1 评估非 Corti 方向. Phase 2 删. 见 docs/backlog/PRODUCT_BACKLOG.md §5.
# iCoDer - Gold Cases API Router
import uuid
from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.gold_case import GoldCase
from app.schemas.gold_case import GoldCaseCreate, GoldCaseResponse, EvaluationSummary
from app.middleware.auth import get_current_user
from app.middleware.audit import log_action

router = APIRouter(prefix="/api/gold-cases", tags=["gold_cases"])


@router.post("", response_model=GoldCaseResponse, status_code=201)
async def create_gold_case(
    data: GoldCaseCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    case_id = f"GC-{uuid.uuid4().hex[:12].upper()}"
    gold_case = GoldCase(
        case_id=case_id,
        department=data.department,
        diagnosis_group=data.diagnosis_group,
        original_primary_diagnosis=data.original_primary_diagnosis,
        original_primary_diag_name=data.original_primary_diag_name,
        original_main_procedure=data.original_main_procedure,
        original_main_proc_name=data.original_main_proc_name,
        expected_principal_diagnosis=data.expected_principal_diagnosis,
        expected_principal_diag_name=data.expected_principal_diag_name,
        expected_principal_procedure=data.expected_principal_procedure,
        expected_principal_proc_name=data.expected_principal_proc_name,
        expected_secondary_diagnoses=data.expected_secondary_diagnoses,
        expected_procedure_codes=data.expected_procedure_codes,
        expected_drg_group=data.expected_drg_group,
        acceptable_alternatives=data.acceptable_alternatives,
        reasoning_expectations=data.reasoning_expectations,
        missing_codes=data.missing_codes,
        unsupported_codes=data.unsupported_codes,
        documentation_gaps=data.documentation_gaps,
        evidence_spans=data.evidence_spans,
        full_case_data=data.full_case_data,
        difficulty=data.difficulty,
        specialty=data.specialty,
        risk_tags=data.risk_tags,
        source=data.source,
        reviewer=current_user.id,
        review_time=str(request.headers.get("date", "")),
    )
    db.add(gold_case)
    await log_action(db, current_user.id, current_user.username, "gold_case.create",
                     "gold_case", gold_case.id,
                     ip_address=request.client.host if request.client else None)
    await db.refresh(gold_case)
    return GoldCaseResponse.model_validate(gold_case)


@router.get("")
async def list_gold_cases(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    department: str = Query(""),
    diagnosis_group: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(GoldCase)
    count_query = select(func.count(GoldCase.id))
    if department:
        query = query.where(GoldCase.department == department)
        count_query = count_query.where(GoldCase.department == department)
    if diagnosis_group:
        query = query.where(GoldCase.diagnosis_group == diagnosis_group)
        count_query = count_query.where(GoldCase.diagnosis_group == diagnosis_group)

    query = query.order_by(GoldCase.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    total = (await db.execute(count_query)).scalar()
    cases = (await db.execute(query)).scalars().all()

    return {
        "items": [GoldCaseResponse.model_validate(c) for c in cases],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{case_id}", response_model=GoldCaseResponse)
async def get_gold_case(case_id: str, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    result = await db.execute(
        select(GoldCase).where((GoldCase.case_id == case_id) | (GoldCase.id == case_id))
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Gold case not found")
    return GoldCaseResponse.model_validate(case)


@router.put("/{case_id}", response_model=GoldCaseResponse)
async def update_gold_case(
    case_id: str,
    data: GoldCaseCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(GoldCase).where((GoldCase.case_id == case_id) | (GoldCase.id == case_id))
    )
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Gold case not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(case, key, value)

    await log_action(db, current_user.id, current_user.username, "gold_case.update",
                     "gold_case", case.id,
                     ip_address=request.client.host if request.client else None)
    db.add(case)
    await db.refresh(case)
    return GoldCaseResponse.model_validate(case)


@router.delete("/{case_id}", status_code=204)
async def delete_gold_case(
    case_id: str, request: Request, db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(GoldCase).where(GoldCase.id == case_id))
    case = result.scalar_one_or_none()
    if not case:
        raise HTTPException(status_code=404, detail="Gold case not found")
    await log_action(db, current_user.id, current_user.username, "gold_case.delete",
                     "gold_case", case.id,
                     ip_address=request.client.host if request.client else None)
    await db.delete(case)
    return None
