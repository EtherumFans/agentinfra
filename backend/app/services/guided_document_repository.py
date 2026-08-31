"""Encrypted repository for generated Guided Documents."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.guided_document import GuidedDocumentRecord
from app.services.phi_encryption import decrypt_phi, encrypt_phi


def _json_encrypt(value: Any) -> str:
    return encrypt_phi(json.dumps(value, ensure_ascii=False, separators=(",", ":"))) or ""


def _json_decrypt(value: str | None, default: Any) -> Any:
    raw = decrypt_phi(value)
    if not raw:
        return default
    return json.loads(raw)


class GuidedDocumentRepository:
    @staticmethod
    def _scope(organization_id: str, owner_id: str):
        return (
            GuidedDocumentRecord.organization_id == organization_id,
            GuidedDocumentRecord.owner_id == owner_id,
        )

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        owner_id: str,
        interaction_id: str | None,
        name: str,
        template_id: str,
        template_version_id: str,
        language: str,
        string_document: dict[str, str],
        structured_document: dict[str, Any] | None,
        labels: list[dict[str, str]],
        credits_consumed: float,
        is_stream: bool = False,
        classic_sections: list[dict[str, Any]] | None = None,
    ) -> GuidedDocumentRecord:
        row = GuidedDocumentRecord(
            organization_id=organization_id,
            owner_id=owner_id,
            interaction_id=interaction_id,
            document_id=str(uuid.uuid4()),
            name=name,
            template_id=template_id,
            template_version_id=template_version_id,
            language=language,
            encrypted_string_document_json=_json_encrypt(string_document),
            encrypted_structured_document_json=(
                _json_encrypt(structured_document) if structured_document is not None else None
            ),
            encrypted_labels_json=_json_encrypt(labels),
            encrypted_classic_sections_json=_json_encrypt(
                classic_sections
                if classic_sections is not None
                else [
                    {
                        "key": key,
                        "name": key.replace("-", " ").replace("_", " ").title(),
                        "text": text,
                        "sort": index,
                    }
                    for index, (key, text) in enumerate(string_document.items())
                ]
            ),
            credits_consumed=credits_consumed,
            is_stream=is_stream,
        )
        db.add(row)
        await db.flush()
        return row

    async def list_for_interaction(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        owner_id: str,
        interaction_id: str,
    ) -> list[GuidedDocumentRecord]:
        result = await db.scalars(
            select(GuidedDocumentRecord).where(
                *self._scope(organization_id, owner_id),
                GuidedDocumentRecord.interaction_id == interaction_id,
            ).order_by(GuidedDocumentRecord.id)
        )
        return list(result.all())

    async def get(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        owner_id: str,
        document_id: str,
    ) -> GuidedDocumentRecord | None:
        return await db.scalar(select(GuidedDocumentRecord).where(
            *self._scope(organization_id, owner_id),
            GuidedDocumentRecord.document_id == document_id,
        ))

    async def get_for_interaction(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        owner_id: str,
        interaction_id: str,
        document_id: str,
    ) -> GuidedDocumentRecord | None:
        return await db.scalar(select(GuidedDocumentRecord).where(
            *self._scope(organization_id, owner_id),
            GuidedDocumentRecord.interaction_id == interaction_id,
            GuidedDocumentRecord.document_id == document_id,
        ))

    async def update_classic(
        self,
        db: AsyncSession,
        row: GuidedDocumentRecord,
        *,
        name: str | None,
        sections: list[dict[str, Any]] | None,
    ) -> GuidedDocumentRecord:
        if name is not None:
            row.name = name
        if sections is not None:
            ordered = sorted(sections, key=lambda item: item["sort"])
            row.encrypted_classic_sections_json = _json_encrypt(ordered)
            row.encrypted_string_document_json = _json_encrypt({
                item["key"]: item["text"] for item in ordered
            })
        row.updated_at = datetime.now(timezone.utc)
        await db.flush()
        return row

    async def delete(self, db: AsyncSession, row: GuidedDocumentRecord) -> None:
        await db.delete(row)
        await db.flush()

    @staticmethod
    def string_document(row: GuidedDocumentRecord) -> dict[str, str]:
        value = _json_decrypt(row.encrypted_string_document_json, {})
        return value if isinstance(value, dict) else {}

    @staticmethod
    def structured_document(row: GuidedDocumentRecord) -> dict[str, Any] | None:
        value = _json_decrypt(row.encrypted_structured_document_json, None)
        return value if isinstance(value, dict) else None

    @staticmethod
    def labels(row: GuidedDocumentRecord) -> list[dict[str, str]]:
        value = _json_decrypt(row.encrypted_labels_json, [])
        return value if isinstance(value, list) else []

    @staticmethod
    def classic_sections(row: GuidedDocumentRecord) -> list[dict[str, Any]]:
        value = _json_decrypt(row.encrypted_classic_sections_json, None)
        if isinstance(value, list):
            return value
        return [
            {
                "key": key,
                "name": key.replace("-", " ").replace("_", " ").title(),
                "text": text,
                "sort": index,
            }
            for index, (key, text) in enumerate(
                GuidedDocumentRepository.string_document(row).items()
            )
        ]


guided_document_repository = GuidedDocumentRepository()
