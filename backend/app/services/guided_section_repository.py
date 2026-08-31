"""Tenant-scoped storage for dynamic Guided Section resources."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guided_document import GuidedSectionRecord
from app.services.phi_encryption import decrypt_phi, encrypt_phi


class GuidedSectionRepository:
    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        owner_id: str,
        language: str,
        definition: dict[str, Any],
        auto_generated: bool = True,
        source: str = "project",
    ) -> GuidedSectionRecord:
        section_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        stored_definition = dict(definition)
        stored_definition["sectionId"] = section_id
        stored_definition["sectionVersionId"] = version_id
        row = GuidedSectionRecord(
            organization_id=organization_id,
            owner_id=owner_id,
            section_id=section_id,
            version_id=version_id,
            name=str(definition["heading"]),
            language=language,
            encrypted_definition_json=encrypt_phi(
                json.dumps(stored_definition, ensure_ascii=False, separators=(",", ":"))
            ) or "",
            auto_generated=auto_generated,
            source=source,
        )
        db.add(row)
        await db.flush()
        return row

    async def list(
        self, db: AsyncSession, *, organization_id: str
    ) -> list[GuidedSectionRecord]:
        result = await db.scalars(select(GuidedSectionRecord).where(
            GuidedSectionRecord.organization_id == organization_id,
            GuidedSectionRecord.deleted_at.is_(None),
        ).order_by(GuidedSectionRecord.id))
        return list(result.all())

    async def get(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        section_id: str,
    ) -> GuidedSectionRecord | None:
        return await db.scalar(select(GuidedSectionRecord).where(
            GuidedSectionRecord.organization_id == organization_id,
            GuidedSectionRecord.section_id == section_id,
            GuidedSectionRecord.deleted_at.is_(None),
        ))

    async def update(
        self,
        db: AsyncSession,
        row: GuidedSectionRecord,
        *,
        language: str,
        definition: dict[str, Any],
    ) -> GuidedSectionRecord:
        version_id = str(uuid.uuid4())
        stored_definition = dict(definition)
        stored_definition["sectionId"] = row.section_id
        stored_definition["sectionVersionId"] = version_id
        row.version_id = version_id
        row.name = str(stored_definition["heading"])
        row.language = language
        row.encrypted_definition_json = encrypt_phi(
            json.dumps(stored_definition, ensure_ascii=False, separators=(",", ":"))
        ) or ""
        row.auto_generated = False
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return row

    async def soft_delete(
        self, db: AsyncSession, row: GuidedSectionRecord
    ) -> None:
        row.deleted_at = datetime.now(timezone.utc)
        row.updated_at = row.deleted_at
        await db.flush()

    async def resolve(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        section_id: str,
        version_id: str | None,
    ) -> dict[str, Any] | None:
        row = await db.scalar(select(GuidedSectionRecord).where(
            GuidedSectionRecord.organization_id == organization_id,
            GuidedSectionRecord.section_id == section_id,
            GuidedSectionRecord.deleted_at.is_(None),
        ))
        if row is None or (version_id is not None and version_id != row.version_id):
            return None
        return self.definition(row)

    @staticmethod
    def definition(row: GuidedSectionRecord) -> dict[str, Any]:
        raw = decrypt_phi(row.encrypted_definition_json) or "{}"
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}


guided_section_repository = GuidedSectionRepository()
