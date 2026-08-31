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

from datetime import datetime, timezone
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import select, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_user, get_current_organization
from app.models.template import (
    Template, TemplateVersion, TemplateCategory, TemplateLanguage, TemplateScope,
)
from app.models.organization import Organization
from app.models.user import User
from app.middleware.audit import log_action
from app.services.guided_template_catalog import template_generation

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
    published_version_count: int = 0
    published_version: Optional["TemplateVersionOut"] = None


class TemplateVersionOut(BaseModel):
    id: str
    template_id: str
    version_number: int
    generation: dict
    published_by_user_id: Optional[str] = None
    created_at: Optional[str] = None


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

    @field_validator("name")
    @classmethod
    def _name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("template name must not be blank")
        return value


class TemplateUpdateIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    description: Optional[str] = Field(default=None, max_length=1024)
    content: Optional[str] = Field(default=None, max_length=65536)
    category: Optional[TemplateCategory] = None
    language: Optional[TemplateLanguage] = None
    scope: Optional[TemplateScope] = None

    @field_validator("name")
    @classmethod
    def _updated_name_must_not_be_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            raise ValueError("template name must not be null")
        value = value.strip()
        if not value:
            raise ValueError("template name must not be blank")
        return value

    @model_validator(mode="after")
    def _require_change(self) -> "TemplateUpdateIn":
        if not self.model_fields_set:
            raise ValueError("at least one template field must be provided")
        if any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("template update fields must not be null")
        return self


def _version_to_out(version: TemplateVersion) -> TemplateVersionOut:
    return TemplateVersionOut(
        id=version.id,
        template_id=version.template_id,
        version_number=version.version_number,
        generation=json.loads(version.generation_json),
        published_by_user_id=version.published_by_user_id,
        created_at=version.created_at.isoformat() if version.created_at else None,
    )


def _to_out(
    t: Template,
    versions: list[TemplateVersion] | None = None,
) -> TemplateOut:
    versions = versions or []
    latest = max(versions, key=lambda row: row.version_number, default=None)
    # Product-managed built-ins are shipped as version 0 even though they do
    # not consume tenant-authored publication rows.
    version_count = len(versions) if not t.is_builtin else max(1, len(versions))
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
        published_version_count=version_count,
        published_version=_version_to_out(latest) if latest else None,
    )


async def _versions_by_template(
    db: AsyncSession,
    *,
    organization_id: str,
    template_ids: list[str],
) -> dict[str, list[TemplateVersion]]:
    if not template_ids:
        return {}
    rows = list((await db.scalars(
        select(TemplateVersion).where(
            TemplateVersion.organization_id == organization_id,
            TemplateVersion.template_id.in_(template_ids),
        ).order_by(TemplateVersion.version_number.desc())
    )).all())
    result: dict[str, list[TemplateVersion]] = {}
    for row in rows:
        result.setdefault(row.template_id, []).append(row)
    return result


@router.get("", response_model=TemplateListOut)
async def list_templates(
    search: str = Query("", description="Search name/description"),
    category: str = Query("", description="Filter by category"),
    language: str = Query("", description="Filter by language (zh-CN / en-US)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TemplateListOut:
    q = select(Template).where(
        Template.organization_id == current_org.id,
        Template.deleted_at.is_(None),
    )
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
    version_map = await _versions_by_template(
        db,
        organization_id=str(current_org.id),
        template_ids=[row.id for row in rows],
    )
    return TemplateListOut(
        templates=[_to_out(t, version_map.get(t.id)) for t in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=TemplateOut, status_code=201)
async def create_template(
    body: TemplateCreateIn,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    t = Template(
        organization_id=current_org.id,
        name=body.name.strip(),
        description=body.description.strip(),
        content=body.content,
        category=body.category,
        language=body.language,
        scope=body.scope,
        is_builtin=False,
    )
    db.add(t)
    await db.flush()
    await log_action(
        db,
        str(user.id),
        user.username,
        "template.create",
        "template",
        str(t.id),
        organization_id=str(current_org.id),
    )
    await db.commit()
    await db.refresh(t)
    return _to_out(t)


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(
    template_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    t = (await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.organization_id == current_org.id,
            Template.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if not t:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TEMPLATE_NOT_FOUND", "template_id": template_id},
        )
    versions = await _versions_by_template(
        db, organization_id=str(current_org.id), template_ids=[t.id]
    )
    return _to_out(t, versions.get(t.id))


@router.patch("/{template_id}", response_model=TemplateOut)
async def update_template(
    template_id: str,
    body: TemplateUpdateIn,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    """Update a tenant-owned custom template used by the local Builder."""
    t = (await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.organization_id == current_org.id,
            Template.deleted_at.is_(None),
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
                "message": "Built-in templates cannot be updated.",
            },
        )
    changes = body.model_dump(exclude_unset=True)
    if "name" in changes:
        changes["name"] = changes["name"].strip()
    if "description" in changes:
        changes["description"] = changes["description"].strip()
    for field, value in changes.items():
        setattr(t, field, value)
    await log_action(
        db,
        str(user.id),
        user.username,
        "template.update",
        "template",
        str(t.id),
        organization_id=str(current_org.id),
    )
    await db.commit()
    await db.refresh(t)
    versions = await _versions_by_template(
        db, organization_id=str(current_org.id), template_ids=[t.id]
    )
    return _to_out(t, versions.get(t.id))


@router.post("/{template_id}/publish", response_model=TemplateVersionOut, status_code=201)
async def publish_template(
    template_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TemplateVersionOut:
    """Append an immutable snapshot of the current tenant-owned draft."""
    template = (await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.organization_id == current_org.id,
            Template.deleted_at.is_(None),
        ).with_for_update()
    )).scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TEMPLATE_NOT_FOUND", "template_id": template_id},
        )
    if template.is_builtin:
        raise HTTPException(
            status_code=403,
            detail={
                "error_code": "TEMPLATE_BUILTIN_PROTECTED",
                "message": "Built-in template versions are product-managed.",
            },
        )
    latest_number = (await db.scalar(
        select(func.max(TemplateVersion.version_number)).where(
            TemplateVersion.organization_id == current_org.id,
            TemplateVersion.template_id == template.id,
        )
    ))
    generation = template_generation(template)
    snapshot = {
        "name": template.name,
        "description": template.description,
        "content": template.content,
        "category": getattr(template.category, "value", str(template.category)),
        "language": getattr(template.language, "value", str(template.language)),
        "scope": getattr(template.scope, "value", str(template.scope)),
    }
    version = TemplateVersion(
        organization_id=str(current_org.id),
        template_id=template.id,
        version_number=0 if latest_number is None else latest_number + 1,
        generation_json=json.dumps(generation, ensure_ascii=False, separators=(",", ":")),
        snapshot_json=json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        published_by_user_id=str(user.id),
    )
    db.add(version)
    await db.flush()
    await log_action(
        db,
        str(user.id),
        user.username,
        "template.publish",
        "template_version",
        str(version.id),
        organization_id=str(current_org.id),
    )
    await db.commit()
    await db.refresh(version)
    return _version_to_out(version)


@router.get("/{template_id}/versions", response_model=list[TemplateVersionOut])
async def list_template_versions(
    template_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> list[TemplateVersionOut]:
    template = (await db.execute(select(Template.id).where(
        Template.id == template_id,
        Template.organization_id == current_org.id,
        Template.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if template is None:
        raise HTTPException(
            status_code=404,
            detail={"error_code": "TEMPLATE_NOT_FOUND", "template_id": template_id},
        )
    versions = await _versions_by_template(
        db, organization_id=str(current_org.id), template_ids=[template_id]
    )
    return [_version_to_out(row) for row in versions.get(template_id, [])]


@router.get(
    "/{template_id}/versions/{version_id}", response_model=TemplateVersionOut
)
async def get_template_version(
    template_id: str,
    version_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TemplateVersionOut:
    version = (await db.execute(
        select(TemplateVersion)
        .join(Template, Template.id == TemplateVersion.template_id)
        .where(
            TemplateVersion.id == version_id,
            TemplateVersion.template_id == template_id,
            TemplateVersion.organization_id == current_org.id,
            Template.organization_id == current_org.id,
            Template.deleted_at.is_(None),
        )
    )).scalar_one_or_none()
    if version is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error_code": "TEMPLATE_VERSION_NOT_FOUND",
                "template_id": template_id,
                "version_id": version_id,
            },
        )
    return _version_to_out(version)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: str,
    user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    t = (await db.execute(
        select(Template).where(
            Template.id == template_id,
            Template.organization_id == current_org.id,
            Template.deleted_at.is_(None),
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
    await log_action(
        db,
        str(user.id),
        user.username,
        "template.delete",
        "template",
        str(t.id),
        organization_id=str(current_org.id),
    )
    t.deleted_at = datetime.now(timezone.utc)
    t.updated_at = t.deleted_at
    await db.commit()


__all__ = ["router"]
