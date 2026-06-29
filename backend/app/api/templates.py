"""iCoDer Templates API — Corti parity for /templates (Beta) page.

Corti /templates IA:
- list pre-built + custom content templates for structured doc generation
- search by name / description
- filter by category / language
- create custom (Template builder)
- delete custom (built-in protected)

Endpoints
---------
* ``GET    /api/templates``           — list (search + category + language + paginate)
* ``POST   /api/templates``           — create custom
* ``GET    /api/templates/{id}``      — get one
* ``DELETE /api/templates/{id}``      — delete (custom only)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user
from app.models.template import (
    Template, TemplateCategory, TemplateLanguage, TemplateScope,
)
from app.models.user import User

router = APIRouter(prefix="/api/templates", tags=["templates"])


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str
    content: str
    category: str
    language: str
    is_builtin: bool
    scope: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class TemplateListOut(BaseModel):
    templates: list[TemplateOut]
    total: int
    page: int
    page_size: int


class TemplateCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    description: str = Field(default="", max_length=1024)
    content: str = Field(default="", max_length=65536)
    category: TemplateCategory = TemplateCategory.CUSTOM
    language: TemplateLanguage = TemplateLanguage.ZH_CN
    scope: TemplateScope = TemplateScope.ALL_CUSTOMERS


def _to_out(t: Template) -> TemplateOut:
    return TemplateOut(
        id=t.id,
        name=t.name,
        description=t.description,
        content=t.content,
        category=t.category.value if hasattr(t.category, "value") else str(t.category),
        language=t.language.value if hasattr(t.language, "value") else str(t.language),
        is_builtin=t.is_builtin,
        scope=t.scope.value if hasattr(t.scope, "value") else str(t.scope),
        created_at=t.created_at.isoformat() if t.created_at else None,
        updated_at=t.updated_at.isoformat() if t.updated_at else None,
    )


@router.get("", response_model=TemplateListOut)
async def list_templates(
    search: str = Query("", description="Search name/description"),
    category: str = Query("", description="Filter by category"),
    language: str = Query("", description="Filter by language (zh-CN / en-US)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateListOut:
    q = select(Template).where(Template.organization_id == user.organization_id)
    if search:
        like = f"%{search}%"
        q = q.where(
            or_(
                Template.name.ilike(like),
                Template.description.ilike(like),
            )
        )
    if category:
        try:
            q = q.where(Template.category == TemplateCategory(category))
        except ValueError:
            pass
    if language:
        try:
            q = q.where(Template.language == TemplateLanguage(language))
        except ValueError:
            pass
    total = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    q = q.order_by(Template.is_builtin.desc(), Template.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()
    return TemplateListOut(
        templates=[_to_out(t) for t in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    t = Template(
        organization_id=user.organization_id,
        name=body.name.strip(),
        description=body.description.strip(),
        content=body.content,
        category=body.category,
        language=body.language,
        scope=body.scope,
        is_builtin=False,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _to_out(t)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    t = (await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TEMPLATE_NOT_FOUND", "template_id": template_id},
        )
    return _to_out(t)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    t = (await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TEMPLATE_NOT_FOUND", "template_id": template_id},
        )
    if t.is_builtin:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "TEMPLATE_BUILTIN_PROTECTED",
                "message": "Built-in templates cannot be deleted.",
            },
        )
    await db.delete(t)
    await db.commit()


__all__ = ["router"]