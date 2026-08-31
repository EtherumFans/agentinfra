"""Durable encrypted repository for interaction-scoped clinical facts."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clinical_fact import ClinicalFactRecord
from app.services.phi_encryption import decrypt_phi, encrypt_phi


FACT_GROUP_NAMESPACE = uuid.UUID("5b3d4f7e-1c2a-4b8d-9e6f-0a1b2c3d4e5f")


def fact_group_id(group_key: str) -> str:
    return str(uuid.uuid5(FACT_GROUP_NAMESPACE, f"icoder.factgroup.{group_key}"))


class ClinicalFactRepository:
    @staticmethod
    def _where(scope: dict[str, str]):
        return (
            ClinicalFactRecord.organization_id == scope["organization_id"],
            ClinicalFactRecord.owner_id == scope["owner_id"],
            ClinicalFactRecord.interaction_id == scope["interaction_id"],
        )

    async def list(self, db: AsyncSession, **scope: str) -> list[ClinicalFactRecord]:
        result = await db.execute(
            select(ClinicalFactRecord)
            .where(*self._where(scope))
            .order_by(ClinicalFactRecord.id)
        )
        return list(result.scalars())

    async def get(
        self,
        db: AsyncSession,
        *,
        fact_id: str,
        **scope: str,
    ) -> ClinicalFactRecord | None:
        return await db.scalar(
            select(ClinicalFactRecord).where(
                *self._where(scope),
                ClinicalFactRecord.fact_id == fact_id,
            )
        )

    async def create(
        self,
        db: AsyncSession,
        *,
        text: str,
        group_key: str,
        source: str,
        fact_id: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        **scope: str,
    ) -> ClinicalFactRecord:
        row = ClinicalFactRecord(
            **scope,
            fact_id=fact_id or str(uuid.uuid4()),
            group_id=fact_group_id(group_key),
            group_key=group_key,
            source=source,
            is_discarded=False,
            encrypted_text=encrypt_phi(text) or "",
            encrypted_evidence_json=(
                encrypt_phi(json.dumps(evidence, ensure_ascii=False))
                if evidence
                else None
            ),
        )
        db.add(row)
        await db.flush()
        return row

    async def update(
        self,
        db: AsyncSession,
        row: ClinicalFactRecord,
        *,
        text: str | None = None,
        group_key: str | None = None,
        source: str | None = None,
        is_discarded: bool | None = None,
    ) -> ClinicalFactRecord:
        if text is not None:
            row.encrypted_text = encrypt_phi(text) or ""
        if group_key is not None:
            row.group_key = group_key
            row.group_id = fact_group_id(group_key)
        if source is not None:
            row.source = source
        if is_discarded is not None:
            row.is_discarded = is_discarded
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return row

    @staticmethod
    def text(row: ClinicalFactRecord) -> str:
        return decrypt_phi(row.encrypted_text) or ""

    @staticmethod
    def evidence(row: ClinicalFactRecord) -> list[dict[str, Any]]:
        raw = decrypt_phi(row.encrypted_evidence_json)
        if not raw:
            return []
        value = json.loads(raw)
        return value if isinstance(value, list) else []


clinical_fact_repository = ClinicalFactRepository()
