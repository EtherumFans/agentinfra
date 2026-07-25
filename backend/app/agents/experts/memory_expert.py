"""Memory Expert — Corti public §3.2 key 1 of 9 (A1B-AE.5 stub).

Corti public docs describe the Memory Expert as a RAG pipeline that
provides semantic retrieval over long-term memory. iCoDer's baseline
memory capability is LEXICAL_ONLY (strictly weaker — no embedding
index) per A1B-AE.1 §3.2.

A1B-AE.5 ships a STUB that:

1. Registers the Memory Expert in the Expert Registry with
   ``origin=CLEAN_ROOM_PUBLIC``, ``canonical_key='memory'``,
   ``corti_alignment='CORTI_REFERENCE'``. A1B-AE.1 §3.2 documents
   this as a known parity gap (iCoDer CORTI_ADVANTAGE = NONE;
   iCoDer DEFICIENCY = no semantic retrieval).

2. Returns a deterministic lexical-only retrieval result from the
   thread's prior messages. This is NOT semantic — there is no
   embedding index. The implementation is explicitly a placeholder
   so the Expert Registry has a row for 'memory' that consumers can
   route to; A1B-AE.6 or later may add a real semantic retriever.

The stub must NOT claim parity with Corti's RAG pipeline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Corti public §3.2 — 9 canonical Expert keys. 'memory' is key 1 of 9.
MEMORY_EXPERT_CANONICAL_KEY = "memory"
MEMORY_EXPERT_NAME = "Memory Expert"
MEMORY_EXPERT_DESCRIPTION = (
    "Lexical-only thread memory retrieval. "
    "iCoDer baseline; semantic RAG deferred (A1B-AE.1 §3.2 documents "
    "this as a known CORTI_REFERENCE parity gap)."
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


__all__ = [
    "MEMORY_EXPERT_CANONICAL_KEY",
    "MEMORY_EXPERT_NAME",
    "MEMORY_EXPERT_DESCRIPTION",
    "MemoryRetrievalResult",
    "retrieve",
]
