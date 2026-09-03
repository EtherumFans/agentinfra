"""Memory Expert compatibility API and governed persistent retrieval adapter.

Corti public docs describe the Memory Expert as a RAG pipeline that provides
semantic retrieval over long-term memory. ``retrieve`` remains a deterministic
non-persistent thread compatibility helper. ``retrieve_persistent_async`` uses
the consent-bound encrypted Connector Memory store and its configured remote
semantic embedding service.

The live path never imports native ML into the API process. Missing semantic
infrastructure is explicitly disclosed as lexical fallback in development or
fails closed when ``ICODER_MEMORY_SEMANTIC_REQUIRED=true``.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.connector_executor import ConnectorInvocation

logger = logging.getLogger(__name__)


# Corti public §3.2 — 9 canonical Expert keys. 'memory' is key 1 of 9.
MEMORY_EXPERT_CANONICAL_KEY = "memory"
MEMORY_EXPERT_NAME = "Memory Expert"
MEMORY_EXPERT_DESCRIPTION = (
    "Consent-bound encrypted persistent memory with optional governed remote "
    "semantic retrieval; synchronous thread compatibility remains lexical."
)


@dataclass
class MemoryRetrievalResult:
    """Result of a Memory Expert retrieval call."""

    query: str
    matches: list[dict[str, Any]] = field(default_factory=list)
    retrieval_mode: str = "LEXICAL_ONLY"
    notes: str = ""


def retrieve(
    query: str,
    thread_messages: list[dict[str, Any]] | None = None,
    top_k: int = 5,
) -> MemoryRetrievalResult:
    """Lexical-only retrieval over the thread's prior messages.

    This is NOT semantic RAG. It is a token-overlap scorer over the
    caller-supplied thread history. The caller is responsible for
    passing in the thread messages — the Memory Expert does NOT
    persist anything.

    A real semantic retriever (BGE-M3 + FAISS, per the MedCodER
    pipeline pattern) is a future enhancement target.
    """
    thread_messages = thread_messages or []
    query_terms = {t.lower() for t in (query or "").split() if len(t) >= 2}
    if not query_terms:
        return MemoryRetrievalResult(
            query=query,
            matches=[],
            notes="empty query after tokenization",
        )

    scored: list[tuple[float, dict[str, Any]]] = []
    for msg in thread_messages:
        text = ""
        for part in msg.get("parts") or []:
            if part.get("kind") == "text":
                text += " " + (part.get("text") or "")
        if not text:
            continue
        text_terms = {t.lower() for t in text.split() if len(t) >= 2}
        overlap = len(query_terms & text_terms)
        if overlap == 0:
            continue
        score = overlap / max(len(query_terms), 1)
        scored.append((score, msg))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_k]

    return MemoryRetrievalResult(
        query=query,
        matches=[{"score": s, "message": m} for s, m in top],
        retrieval_mode="LEXICAL_ONLY",
        notes=(
            "Lexical token overlap only; no embedding index. "
            "Corti public §3.2 'memory' Expert is CORTI_REFERENCE; "
            "iCoDer does NOT claim semantic RAG parity."
        ),
    )


async def retrieve_persistent_async(
    query: str,
    *,
    db: AsyncSession,
    store: Any,
    organization_id: str,
    user_id: str,
    agent_id: str,
    purpose_of_use: str = "treatment",
    top_k: int = 5,
) -> MemoryRetrievalResult:
    """Retrieve encrypted persistent Memory through the governed store."""

    output = await store.invoke(db, ConnectorInvocation(
        organization_id=organization_id,
        agent_id=agent_id,
        connector_id="memory",
        operation="recall",
        arguments={"query": query, "top_k": top_k},
        data_classification="deidentified",
        purpose_of_use=purpose_of_use,
        actor_type="user",
        actor_id=user_id,
    ))
    memories = output.get("memories")
    if not isinstance(memories, list):
        raise RuntimeError("CONNECTOR_RESPONSE_INVALID")
    return MemoryRetrievalResult(
        query=query,
        matches=memories,
        retrieval_mode=str(output.get("retrieval_mode") or "UNKNOWN"),
        notes=(
            "Governed persistent Memory; encrypted at rest, consent and "
            "retention bound, non-authoritative and manual review required."
        ),
    )


__all__ = [
    "MEMORY_EXPERT_CANONICAL_KEY",
    "MEMORY_EXPERT_NAME",
    "MEMORY_EXPERT_DESCRIPTION",
    "MemoryRetrievalResult",
    "retrieve",
    "retrieve_persistent_async",
]
