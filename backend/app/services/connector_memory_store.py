"""Consent-bound, encrypted persistent memory for the Registry Connector."""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.icoder.agent_runtime.a2a.input_safety import detect_prompt_injection
from app.icoder.agent_runtime.context.context_retrieval import lexical_similarity
from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload
from app.models.memory import ConversationMemory, MemoryConsent
from app.services.connector_executor import ConnectorExecutionError, ConnectorInvocation
from app.services.phi_encryption import (
    decrypt_phi,
    encrypt_phi,
    is_encryption_enabled,
)


MEMORY_PURPOSES = frozenset({
    "treatment", "healthcare_operations", "quality_improvement",
})


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _truthy(value: str | None) -> bool:
    return (value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _embedding_metadata(row: ConversationMemory) -> dict[str, Any]:
    try:
        raw = decrypt_phi(row.key_facts)
        value = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, RuntimeError, TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _embedding_document(embedding: Any | None) -> dict[str, Any]:
    if embedding is None:
        return {"facts": [], "_embedding": []}
    return {
        "facts": [],
        "_embedding": list(embedding.vector),
        "_embedding_model": embedding.model,
        "_embedding_version": embedding.model_version,
        "_embedding_dimensions": embedding.dimensions,
    }


def _compatible_vector(metadata: dict[str, Any], query_embedding: Any) -> list[float] | None:
    vector = metadata.get("_embedding")
    if (
        metadata.get("_embedding_model") != query_embedding.model
        or metadata.get("_embedding_version") != query_embedding.model_version
        or metadata.get("_embedding_dimensions") != query_embedding.dimensions
        or not isinstance(vector, list)
        or len(vector) != query_embedding.dimensions
    ):
        return None
    output: list[float] = []
    for value in vector:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            return None
        output.append(float(value))
    norm = math.sqrt(sum(value * value for value in output))
    if not math.isfinite(norm) or norm <= 1e-12:
        return None
    return [value / norm for value in output]


class GovernedMemoryStore:
    """Persistent memory whose subject and authority are server-owned."""

    def __init__(
        self,
        *,
        semantic_provider: Any | None = None,
        semantic_required: bool | None = None,
    ) -> None:
        self._semantic_provider = semantic_provider
        self._semantic_required = (
            semantic_required
            if semantic_required is not None
            else _truthy(os.environ.get("ICODER_MEMORY_SEMANTIC_REQUIRED"))
        )

    async def grant(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: str,
        agent_id: str,
        purpose_of_use: str,
        retention_days: int,
        expires_in_days: int,
    ) -> MemoryConsent:
        if purpose_of_use not in MEMORY_PURPOSES:
            raise ValueError("MEMORY_PURPOSE_NOT_ALLOWED")
        now = _utcnow()
        consent = (
            await db.execute(
                select(MemoryConsent).where(
                    MemoryConsent.organization_id == organization_id,
                    MemoryConsent.user_id == user_id,
                    MemoryConsent.agent_id == agent_id,
                    MemoryConsent.purpose_of_use == purpose_of_use,
                ).with_for_update()
            )
        ).scalar_one_or_none()
        if consent is None:
            consent = MemoryConsent(
                organization_id=organization_id,
                user_id=user_id,
                agent_id=agent_id,
                purpose_of_use=purpose_of_use,
                created_by=user_id,
                expires_at=now + timedelta(days=expires_in_days),
                retention_days=retention_days,
            )
            db.add(consent)
        else:
            consent.status = "active"
            consent.revoked_at = None
            consent.expires_at = now + timedelta(days=expires_in_days)
            consent.retention_days = retention_days
            consent.created_by = user_id
        await db.flush()
        return consent

    async def get(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: str,
        agent_id: str,
        purpose_of_use: str,
    ) -> MemoryConsent | None:
        consent = (
            await db.execute(
                select(MemoryConsent).where(
                    MemoryConsent.organization_id == organization_id,
                    MemoryConsent.user_id == user_id,
                    MemoryConsent.agent_id == agent_id,
                    MemoryConsent.purpose_of_use == purpose_of_use,
                )
            )
        ).scalar_one_or_none()
        if consent is not None and (
            consent.status == "active"
            and _as_aware(consent.expires_at) <= _utcnow()
        ):
            consent.status = "expired"
        return consent

    async def revoke(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_id: str,
        agent_id: str,
        purpose_of_use: str,
    ) -> tuple[MemoryConsent | None, int]:
        consent = await self.get(
            db,
            organization_id=organization_id,
            user_id=user_id,
            agent_id=agent_id,
            purpose_of_use=purpose_of_use,
        )
        if consent is None:
            return None, 0
        result = await db.execute(
            delete(ConversationMemory).where(
                ConversationMemory.organization_id == organization_id,
                ConversationMemory.user_id == user_id,
                ConversationMemory.agent_id == agent_id,
                ConversationMemory.consent_id == consent.id,
            )
        )
        consent.status = "revoked"
        consent.revoked_at = _utcnow()
        return consent, int(result.rowcount or 0)

    async def invoke(
        self,
        db: AsyncSession,
        invocation: ConnectorInvocation,
    ) -> dict[str, Any]:
        if invocation.actor_type != "user" or not invocation.actor_id:
            raise ConnectorExecutionError("CONNECTOR_MEMORY_USER_ACTOR_REQUIRED")
        if invocation.purpose_of_use not in MEMORY_PURPOSES:
            raise ConnectorExecutionError("CONNECTOR_MEMORY_PURPOSE_NOT_ALLOWED")
        if invocation.operation == "forget":
            return await self._forget(db, invocation)
        consent = await self.get(
            db,
            organization_id=invocation.organization_id,
            user_id=invocation.actor_id,
            agent_id=invocation.agent_id,
            purpose_of_use=invocation.purpose_of_use,
        )
        if consent is None or consent.status != "active":
            raise ConnectorExecutionError("CONNECTOR_MEMORY_CONSENT_REQUIRED")
        if invocation.operation == "remember":
            return await self._remember(db, invocation, consent)
        if invocation.operation == "recall":
            return await self._recall(db, invocation, consent)
        raise ConnectorExecutionError("CONNECTOR_REGISTRY_OPERATION_NOT_ALLOWED")

    async def _remember(
        self,
        db: AsyncSession,
        invocation: ConnectorInvocation,
        consent: MemoryConsent,
    ) -> dict[str, Any]:
        content = invocation.arguments.get("content")
        role = invocation.arguments.get("role", "user")
        if (
            not isinstance(content, str) or not content.strip()
            or len(content) > 2000 or role not in {"user", "assistant"}
            or invocation.data_classification not in {"non_phi", "deidentified"}
        ):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        try:
            redaction = redact_payload(content)
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_DEIDENTIFICATION_FAILED"
            ) from exc
        safe_content = str(redaction.value).strip()
        if detect_prompt_injection(safe_content):
            raise ConnectorExecutionError("CONNECTOR_MEMORY_CONTENT_SAFETY_BLOCKED")
        digest = hashlib.sha256(
            f"{invocation.actor_id}\0{invocation.agent_id}\0{safe_content}".encode("utf-8")
        ).hexdigest()
        existing = (
            await db.execute(
                select(ConversationMemory).where(
                    ConversationMemory.organization_id == invocation.organization_id,
                    ConversationMemory.user_id == invocation.actor_id,
                    ConversationMemory.agent_id == invocation.agent_id,
                    ConversationMemory.consent_id == consent.id,
                    ConversationMemory.content_digest == digest,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            embedding = None
            semantic_reason = "already_indexed"
            metadata = _embedding_metadata(existing)
            if not metadata.get("_embedding"):
                embedding, semantic_reason = await self._embed(safe_content)
                if embedding is not None:
                    existing.key_facts = encrypt_phi(json.dumps(
                        _embedding_document(embedding),
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ))
            return {
                "memory_id": existing.id,
                "status": (
                    "deduplicated_reindexed" if embedding is not None
                    else "deduplicated"
                ),
                "redaction_applied": redaction.redaction_applied,
                "semantic_index_status": (
                    "indexed" if metadata.get("_embedding") or embedding is not None
                    else "degraded"
                ),
                "semantic_degraded_reason": (
                    None if metadata.get("_embedding") or embedding is not None
                    else semantic_reason
                ),
            }
        embedding, semantic_reason = await self._embed(safe_content)
        now = _utcnow()
        retention_until = min(
            now + timedelta(days=consent.retention_days),
            _as_aware(consent.expires_at),
        )
        row = ConversationMemory(
            organization_id=invocation.organization_id,
            user_id=invocation.actor_id,
            agent_id=invocation.agent_id,
            session_id=f"connector:{consent.id}:{digest[:24]}",
            role=role,
            content=encrypt_phi(safe_content),
            key_facts=encrypt_phi(json.dumps(
                _embedding_document(embedding),
                ensure_ascii=False,
                separators=(",", ":"),
            )),
            consent_id=consent.id,
            actor_type="user",
            actor_id=invocation.actor_id,
            purpose_of_use=invocation.purpose_of_use,
            retention_until=retention_until,
            content_digest=digest,
        )
        db.add(row)
        await db.flush()
        return {
            "memory_id": row.id,
            "status": "remembered",
            "redaction_applied": redaction.redaction_applied,
            "retention_until": retention_until.isoformat(),
            "semantic_index_status": "indexed" if embedding is not None else "degraded",
            "semantic_degraded_reason": None if embedding is not None else semantic_reason,
        }

    async def _recall(
        self,
        db: AsyncSession,
        invocation: ConnectorInvocation,
        consent: MemoryConsent,
    ) -> dict[str, Any]:
        query = invocation.arguments.get("query")
        top_k = invocation.arguments.get("top_k", 5)
        if (
            not isinstance(query, str) or not query.strip() or len(query) > 500
            or not isinstance(top_k, int) or isinstance(top_k, bool)
            or not 1 <= top_k <= 20
            or invocation.data_classification not in {"non_phi", "deidentified"}
        ):
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        try:
            redaction = redact_payload(query)
        except Exception as exc:
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_DEIDENTIFICATION_FAILED"
            ) from exc
        safe_query = str(redaction.value).strip()
        now = _utcnow()
        rows = (
            await db.execute(
                select(ConversationMemory).where(
                    ConversationMemory.organization_id == invocation.organization_id,
                    ConversationMemory.user_id == invocation.actor_id,
                    ConversationMemory.agent_id == invocation.agent_id,
                    ConversationMemory.consent_id == consent.id,
                    ConversationMemory.purpose_of_use == invocation.purpose_of_use,
                    ConversationMemory.retention_until > now,
                ).order_by(ConversationMemory.created_at.desc()).limit(100)
            )
        ).scalars().all()
        if not rows:
            return {
                "memories": [],
                "returned": 0,
                "retrieval_mode": "NO_MEMORY_CANDIDATES",
                "semantic_coverage": 1.0,
                "semantic_degraded": False,
                "semantic_degraded_reason": None,
                "query_redaction_applied": redaction.redaction_applied,
                "authoritative": False,
                "manual_review_required": True,
                "content_trust": "user_memory_untrusted",
            }
        query_embedding, semantic_reason = await self._embed(safe_query)
        scored: list[tuple[float, ConversationMemory, str]] = []
        semantic_compatible = 0
        lexical_scored = 0
        for row in rows:
            content = decrypt_phi(row.content) or ""
            score = 0.0
            if query_embedding is not None:
                vector = _compatible_vector(
                    _embedding_metadata(row), query_embedding,
                )
                if vector is not None:
                    semantic_compatible += 1
                    score = sum(
                        left * right
                        for left, right in zip(query_embedding.vector, vector)
                    )
                    score = max(-1.0, min(1.0, float(score)))
                    if score < 0.2:
                        score = 0.0
                elif not self._semantic_required:
                    score = lexical_similarity(safe_query, content)
                    lexical_scored += 1
            else:
                score = lexical_similarity(safe_query, content)
                lexical_scored += 1
            if score > 0:
                scored.append((score, row, content))
        if (
            self._semantic_required
            and query_embedding is not None
            and semantic_compatible != len(rows)
        ):
            raise ConnectorExecutionError(
                "CONNECTOR_MEMORY_SEMANTIC_INDEX_INCOMPLETE"
            )
        scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
        memories = [
            {
                "memory_id": row.id,
                "role": row.role,
                "content": content[:500],
                "relevance_score": round(score, 6),
                "created_at": row.created_at.isoformat(),
            }
            for score, row, content in scored[:top_k]
        ]
        if semantic_compatible and lexical_scored:
            retrieval_mode = "PERSISTENT_ENCRYPTED_SEMANTIC_LEXICAL_HYBRID"
        elif semantic_compatible:
            retrieval_mode = "PERSISTENT_ENCRYPTED_REMOTE_SEMANTIC"
        else:
            retrieval_mode = "PERSISTENT_ENCRYPTED_LEXICAL_CJK_BIGRAM"
        coverage = round(semantic_compatible / len(rows), 6)
        degraded_reason = semantic_reason
        if query_embedding is not None and semantic_compatible != len(rows):
            degraded_reason = "semantic_index_incomplete"
        return {
            "memories": memories,
            "returned": len(memories),
            "retrieval_mode": retrieval_mode,
            "semantic_model": query_embedding.model if query_embedding is not None else None,
            "semantic_model_version": (
                query_embedding.model_version if query_embedding is not None else None
            ),
            "semantic_coverage": coverage,
            "semantic_degraded": bool(degraded_reason),
            "semantic_degraded_reason": degraded_reason,
            "query_redaction_applied": redaction.redaction_applied,
            "authoritative": False,
            "manual_review_required": True,
            "content_trust": "user_memory_untrusted",
        }

    async def _embed(self, text: str) -> tuple[Any | None, str | None]:
        if self._semantic_provider is None:
            if self._semantic_required:
                raise ConnectorExecutionError(
                    "CONNECTOR_MEMORY_SEMANTIC_REQUIRED"
                )
            return None, "semantic_provider_not_configured"
        try:
            embedding = await self._semantic_provider.embed(text)
            return embedding, None
        except ConnectorExecutionError as exc:
            if self._semantic_required:
                raise
            return None, exc.code
        except Exception as exc:
            if self._semantic_required:
                raise ConnectorExecutionError(
                    "CONNECTOR_MEMORY_SEMANTIC_UNAVAILABLE",
                    retryable=True,
                ) from exc
            return None, "CONNECTOR_MEMORY_SEMANTIC_UNAVAILABLE"

    async def _forget(
        self,
        db: AsyncSession,
        invocation: ConnectorInvocation,
    ) -> dict[str, Any]:
        memory_id = invocation.arguments.get("memory_id")
        if not isinstance(memory_id, str) or not 1 <= len(memory_id) <= 12:
            raise ConnectorExecutionError("CONNECTOR_REGISTRY_ARGUMENTS_INVALID")
        result = await db.execute(
            delete(ConversationMemory).where(
                ConversationMemory.id == memory_id,
                ConversationMemory.organization_id == invocation.organization_id,
                ConversationMemory.user_id == invocation.actor_id,
                ConversationMemory.agent_id == invocation.agent_id,
                ConversationMemory.actor_type == "user",
                ConversationMemory.actor_id == invocation.actor_id,
                ConversationMemory.consent_id.is_not(None),
            )
        )
        return {"memory_id": memory_id, "deleted": bool(result.rowcount)}

    def status(self) -> dict[str, Any]:
        provider_status = (
            self._semantic_provider.status()
            if self._semantic_provider is not None
            else {"configured": False}
        )
        return {
            "semantic_required": self._semantic_required,
            "semantic_provider": provider_status,
            "lexical_fallback_available": not self._semantic_required,
            "encrypted_vectors_at_rest": is_encryption_enabled(),
            "encryption_required_in_cloud": True,
            "patient_phi_storage_allowed": False,
            "authority_class": "authenticated_user_self_service",
            "patient_authority_verified": False,
        }


__all__ = ["GovernedMemoryStore", "MEMORY_PURPOSES"]
