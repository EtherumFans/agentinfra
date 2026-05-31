# iCoDer — Code Tables API Router
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.user import User
from app.models.code_table import CodeTable, CodeMapping
from app.middleware.auth import get_current_user
from app.services.code_dictionary import code_dict_service

router = APIRouter(prefix="/api/code-tables", tags=["code_tables"])


@router.get("")
async def list_tables(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(CodeTable).order_by(CodeTable.is_default.desc(), CodeTable.name))
    tables = result.scalars().all()
    return {"tables": [
        {
            "id": t.id, "name": t.name, "description": t.description,
            "code_system": t.code_system, "version": t.version,
            "is_active": t.is_active, "is_default": t.is_default,
            "source_type": t.source_type, "institution": t.institution,
            "total_codes": t.total_codes, "config": t.config,
        }
        for t in tables
    ]}


@router.post("", status_code=201)
async def create_table(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ct = CodeTable(
        name=data["name"],
        description=data.get("description", ""),
        code_system=data.get("code_system", "ICD10_CN"),
        version=data.get("version", "1.0"),
        source_type=data.get("source_type", "standard"),
        institution=data.get("institution", ""),
        config=data.get("config", {}),
    )
    db.add(ct)
    await db.commit()
    await db.refresh(ct)
    return {"id": ct.id, "name": ct.name}


@router.get("/{table_id}")
async def get_table(
    table_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(CodeTable).where(CodeTable.id == table_id))
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(404, "Table not found")
    return {
        "id": ct.id, "name": ct.name, "description": ct.description,
        "code_system": ct.code_system, "version": ct.version,
        "source_type": ct.source_type, "institution": ct.institution,
        "total_codes": ct.total_codes, "config": ct.config,
    }


@router.delete("/{table_id}", status_code=204)
async def delete_table(
    table_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(CodeTable).where(CodeTable.id == table_id))
    ct = result.scalar_one_or_none()
    if not ct:
        raise HTTPException(404, "Table not found")
    # Also delete related mappings
    await db.execute(delete(CodeMapping).where(
        (CodeMapping.source_table_id == table_id) | (CodeMapping.target_table_id == table_id)
    ))
    await db.delete(ct)
    await db.commit()
    return None


# ── Cross-table mapping ──

@router.post("/map")
async def map_code_across_tables(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Map a code across all configured code tables. Returns the code representation in each table."""
    code = data["code"]
    code_system = data.get("code_system", "ICD10_CN")
    tables_result = await db.execute(
        select(CodeTable).where(CodeTable.is_active == True).order_by(CodeTable.is_default.desc())
    )
    tables = tables_result.scalars().all()

    results = {}
    for ct in tables:
        if ct.code_system == code_system:
            # Search this specific table's code dict
            from app.services.code_dictionary import code_dict_service
            found = await code_dict_service.explore_code(code, ct.code_system)
            results[ct.name] = {
                "table_id": ct.id,
                "table_name": ct.name,
                "source_type": ct.source_type,
                "code": found.get("code", code) if found else code,
                "name": found.get("name", "") if found else "",
                "valid": found.get("valid", False) if found else False,
                "is_default": ct.is_default,
            }

    return {"query_code": code, "results": results}


@router.get("/mappings/{table_id}")
async def list_mappings(
    table_id: str,
    target_table: str = Query(""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(CodeMapping).where(CodeMapping.source_table_id == table_id)
    if target_table:
        query = query.where(CodeMapping.target_table_id == target_table)
    result = await db.execute(query.order_by(CodeMapping.source_code))
    mappings = result.scalars().all()
    return {
        "mappings": [
            {
                "id": m.id, "source_code": m.source_code, "target_code": m.target_code,
                "target_name": m.target_name, "confidence": m.confidence,
                "mapping_type": m.mapping_type,
            }
            for m in mappings
        ],
        "total": len(mappings),
    }


@router.post("/mappings", status_code=201)
async def create_mapping(
    data: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mapping = CodeMapping(
        source_table_id=data["source_table_id"],
        target_table_id=data["target_table_id"],
        source_code=data["source_code"],
        target_code=data["target_code"],
        target_name=data.get("target_name", ""),
        confidence=data.get("confidence", 1.0),
        mapping_type=data.get("mapping_type", "exact"),
    )
    db.add(mapping)
    await db.commit()
    await db.refresh(mapping)
    return {"id": mapping.id, "source_code": mapping.source_code, "target_code": mapping.target_code}
