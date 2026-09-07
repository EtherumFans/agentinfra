"""Tenant-scoped persistent memory with safe semantic/lexical retrieval.

iCoDer Agentic Framework equivalent: memory-expert + Context & Memory management.
Local sentence-transformers are optional and fail closed on known-crashing
Windows native stacks. PHI-bearing fields use the platform encryption service.
"""
import hashlib
import json
import logging
from datetime import datetime, timedelta, UTC
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import ConversationMemory
from app.icoder.agent_runtime.context.context_retrieval import lexical_similarity
from app.services.phi_encryption import decrypt_phi, encrypt_phi
from app.services.llm_service import llm_service
from icoder_runtime.providers.medical_coding.runtime_safety import (
    assess_sentence_transformer_runtime_safety,
)

logger = logging.getLogger(__name__)


def _bounded_context_session_key(value: str) -> str:
    """Preserve short legacy keys and fit long Context keys into VARCHAR(64)."""
    return value if len(value) <= 64 else hashlib.sha256(value.encode("utf-8")).hexdigest()


# Lazy-load embedding model (80MB, CPU-friendly)
_embedding_model = None
_embedding_runtime_reason = "not_assessed"


def _get_embedding_model():
    global _embedding_model, _embedding_runtime_reason
    if _embedding_model is None:
        safety = assess_sentence_transformer_runtime_safety()
        _embedding_runtime_reason = safety.reason
        if not safety.safe:
            logger.error("Memory embeddings disabled: %s", safety.reason)
            _embedding_model = False
            return None
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            _embedding_runtime_reason = "embedding_model_loaded"
            logger.info("Embedding model loaded: paraphrase-multilingual-MiniLM-L12-v2")
        except ImportError:
            logger.warning("sentence-transformers not installed. Falling back to keyword search.")
            _embedding_runtime_reason = "sentence_transformers_not_installed"
            _embedding_model = False
        except Exception as e:
            logger.warning(f"Embedding model load failed: {e}")
            _embedding_runtime_reason = f"embedding_model_load_failed:{type(e).__name__}"
            _embedding_model = False
    return _embedding_model if _embedding_model is not False else None


def _embed(text: str) -> list[float] | None:
    """Generate embedding vector for text."""
    model = _get_embedding_model()
    if model is None:
        return None
    return model.encode(text, normalize_embeddings=True).tolist()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two normalized vectors."""
    if len(a) != len(b) or not a:
        return 0.0
    return float(sum(left * right for left, right in zip(a, b)))


def embedding_runtime_status() -> dict:
    """Expose an auditable status without forcing a native model load."""
    safety = assess_sentence_transformer_runtime_safety()
    loaded = _embedding_model not in (None, False)
    reason = _embedding_runtime_reason if _embedding_model is not None else safety.reason
    return {
        "safe": safety.safe,
        "available": bool(loaded),
        "reason": reason,
        "retrieval_fallback": "LEXICAL_CJK_BIGRAM",
        "torch_version": safety.torch_version,
        "sentence_transformers_version": safety.sentence_transformers_version,
    }

MEMORY_SYSTEM_PROMPT = """You are a Memory Expert. Extract key facts from conversations that should be remembered for future interactions.

For each conversation message, extract:
1. Clinical preferences (e.g., preferred coding systems, common departments)
2. Important patient context (if any)
3. User workflow patterns
4. Key decisions made

Return JSON:
{"key_facts": ["fact1", "fact2", ...], "importance": 0.0-1.0, "summary": "one-line summary"}"""


class MemoryExpert:
    """Persistent memory for cross-conversation context.

    iCoDer's memory-expert stores and retrieves context across sessions.
    This implementation uses ConversationMemory table + LLM for fact extraction.
    """

    async def save(
        self,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        *,
        organization_id: str,
        expert_id: str | None = None,
        agent_id: str | None = None,
        db: AsyncSession | None = None,
        extract_facts: bool = False,
    ) -> ConversationMemory | None:
        """Save encrypted memory; LLM fact extraction is explicit, never hidden."""
        if not organization_id:
            raise ValueError("organization_id is required for memory isolation")
        if not content.strip():
            raise ValueError("content cannot be empty")
        mem = ConversationMemory(
            organization_id=organization_id,
            user_id=user_id,
            expert_id=expert_id,
            agent_id=agent_id,
            session_id=session_id,
            role=role,
            content=encrypt_phi(content[:2000]),
        )
        facts_list = []
        if extract_facts:
            try:
                result = await llm_service.extract_json(
                    prompt=MEMORY_SYSTEM_PROMPT,
                    text=f"Role: {role}\nContent: {content[:500]}",
                    schema_hint="key_facts array and importance score"
                )
                if isinstance(result, dict):
                    facts_list = result.get("key_facts", [])
                    mem.importance = float(result.get("importance", 0.5))
                    mem.summary = encrypt_phi(str(result.get("summary", ""))[:200])
            except Exception as e:
                logger.warning(f"Memory fact extraction failed: {e}")
                facts_list = []

        # Store embedding alongside key facts in a standardized format
        emb = _embed(content[:500])
        mem.key_facts = encrypt_phi(json.dumps({
                "facts": facts_list,
                "_embedding": emb if emb is not None else [],
            }, ensure_ascii=False))

        if db:
            db.add(mem)
            await db.commit()
        return mem

    async def recall(
        self,
        user_id: str,
        organization_id: str,
        query: str,
        limit: int = 10,
        db: AsyncSession | None = None,
        expert_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[dict]:
        """Recall relevant memories for a user query.

        Uses simple recency + importance ranking. Supports scoping by
        expert_id or agent_id for isolation between agents.

        In production, would use embeddings + vector search for semantic relevance.
        """
        if not db:
            return []
        if not organization_id:
            raise ValueError("organization_id is required for memory isolation")

        # Get recent high-importance memories (optionally scoped by expert/agent)
        conditions = [
            ConversationMemory.organization_id == organization_id,
            ConversationMemory.user_id == user_id,
            # TimestampMixin persists naive UTC, not TIMESTAMPTZ. asyncpg
            # rejects an aware bound parameter against this legacy column.
            ConversationMemory.created_at >= (
                datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
            ),
            ConversationMemory.importance >= 0.3,
        ]
        if expert_id:
            conditions.append(ConversationMemory.expert_id == expert_id)
        if agent_id:
            conditions.append(ConversationMemory.agent_id == agent_id)

        result = await db.execute(
            select(ConversationMemory)
            .where(*conditions)
            .order_by(desc(ConversationMemory.importance), desc(ConversationMemory.created_at))
            .limit(limit)
        )
        memories = result.scalars().all()

        # Try semantic search with embeddings first
        query_emb = _embed(query)

        relevant = []
        for m in memories:
            score = 0.0
            retrieval_mode = "LEXICAL_CJK_BIGRAM"
            content = decrypt_phi(m.content) or ""
            summary = decrypt_phi(m.summary) or ""
            try:
                raw_key_facts = decrypt_phi(m.key_facts)
                key_facts = json.loads(raw_key_facts) if raw_key_facts else {}
            except (json.JSONDecodeError, RuntimeError, TypeError, ValueError):
                key_facts = {}
            facts_list = key_facts.get("facts", []) if isinstance(key_facts, dict) else []
            # Semantic similarity (embedding stored in key_facts._embedding)
            if query_emb is not None and isinstance(key_facts, dict):
                mem_emb = key_facts.get("_embedding")
                if isinstance(mem_emb, list) and len(mem_emb) > 10:
                    score = _cosine_similarity(query_emb, mem_emb)
                    if score >= 0.3:
                        retrieval_mode = "LOCAL_EMBEDDING"

            # Safe deterministic fallback, including Chinese text without spaces.
            if score < 0.3:
                score = max(
                    lexical_similarity(query, content),
                    lexical_similarity(query, " ".join(str(f) for f in facts_list)),
                )

            if score > 0:
                relevant.append({
                    "id": m.id,
                    "role": m.role,
                    "content": content[:300],
                    "summary": summary,
                    "key_facts": facts_list,
                    "importance": m.importance,
                    "relevance_score": score,
                    "retrieval_mode": retrieval_mode,
                    "created_at": m.created_at.isoformat(),
                })

        # Sort by combined relevance + importance
        relevant.sort(key=lambda x: x["relevance_score"] + x["importance"], reverse=True)
        return relevant[:limit]

    async def get_session_context(
        self,
        user_id: str,
        organization_id: str,
        session_id: str,
        limit: int = 20,
        db: AsyncSession | None = None,
    ) -> str:
        """Get recent conversation context for an ongoing session."""
        if not db:
            return ""

        result = await db.execute(
            select(ConversationMemory)
            .where(
                ConversationMemory.organization_id == organization_id,
                ConversationMemory.user_id == user_id,
                ConversationMemory.session_id.in_({
                    session_id, _bounded_context_session_key(session_id),
                }),
            )
            .order_by(ConversationMemory.created_at)
            .limit(limit)
        )
        memories = result.scalars().all()

        if not memories:
            return ""

        lines = []
        for m in memories:
            prefix = "用户" if m.role == "user" else "助手" if m.role == "assistant" else "系统"
            lines.append(f"[{prefix}]: {(decrypt_phi(m.content) or '')[:200]}")

        return "\n".join(lines)

    async def ingest_context_messages(
        self,
        context_id: str,
        user_id: str,
        organization_id: str,
        db: AsyncSession,
        agent_id: str | None = None,
    ) -> int:
        """Bridge real Context messages into long-term ConversationMemory rows.

        Called by A1B-AE-R.4.b — wires the persistent memory store to the
        A2A Context. Reads every ContextMessageRow for the given context,
        extracts plain-text content from parts_json, and saves one
        ConversationMemory row per message. Short session keys retain the
        legacy context_id:message_id form; long keys use a SHA-256 digest to
        fit VARCHAR(64), with the original IDs retained in encrypted metadata.

        Returns the number of memories saved. Sequential replays skip messages
        already ingested for this tenant/user. This is not a concurrent upsert.
        """
        from app.icoder.agent_runtime.context.db_models import ContextMessageRow, ContextRow

        context_result = await db.execute(
            select(ContextRow).where(
                ContextRow.id == context_id,
                ContextRow.organization_id == organization_id,
            )
        )
        if context_result.scalar_one_or_none() is None:
            return 0

        result = await db.execute(
            select(ContextMessageRow)
            .where(ContextMessageRow.context_id == context_id)
            .order_by(ContextMessageRow.timestamp)
        )
        messages = result.scalars().all()
        if not messages:
            return 0

        saved = 0
        for m in messages:
            legacy_session_key = f"{context_id}:{m.message_id}"
            session_key = _bounded_context_session_key(legacy_session_key)
            try:
                stored_parts = decrypt_phi(m.parts_json) if m.parts_json else ""
                parts = json.loads(stored_parts) if stored_parts else []
                parse_failed = False
            except (json.JSONDecodeError, TypeError):
                parts = []
                parse_failed = True

            text_parts = []
            if isinstance(parts, list):
                for p in parts:
                    if isinstance(p, dict):
                        text_parts.append(str(p.get("text", "") or p.get("content", "")))
                    elif isinstance(p, str):
                        text_parts.append(p)
            elif isinstance(parts, str):
                text_parts.append(parts)

            # A1B-AE-R.4.b: when parts_json is a plain string (not JSON),
            # fall back to using it verbatim. A2A MessagePart is a dict in
            # the canonical schema, but legacy callers may store raw text.
            if parse_failed and m.parts_json:
                text_parts.append(str(decrypt_phi(m.parts_json) or ""))

            content = " ".join(text_parts).strip()
            if not content:
                continue

            existing = await db.execute(
                select(ConversationMemory)
                .where(
                    ConversationMemory.organization_id == organization_id,
                    ConversationMemory.user_id == user_id,
                    # SQLite historically accepted overlong VARCHAR values.
                    # Recognize those rows as well; do not duplicate them on
                    # the first replay after upgrading the application.
                    ConversationMemory.session_id.in_({session_key, legacy_session_key}),
                )
                .limit(1)
            )
            if existing.scalars().first() is not None:
                continue

            mem = ConversationMemory(
                organization_id=organization_id,
                user_id=user_id,
                agent_id=agent_id,
                session_id=session_key,
                role=(m.role or "user").lower(),
                content=encrypt_phi(content[:2000]),
            )
            emb = _embed(content[:500])
            mem.key_facts = encrypt_phi(json.dumps(
                {
                    "facts": [],
                    "_embedding": emb if emb is not None else [],
                    "source": "context",
                    "context_id": context_id,
                    "message_id": m.message_id,
                    "redacted": m.redacted,
                },
                ensure_ascii=False,
            ))
            mem.importance = 0.4
            db.add(mem)
            saved += 1

        if saved > 0:
            await db.commit()
        return saved

    async def get_user_profile(
        self,
        user_id: str,
        organization_id: str,
        db: AsyncSession | None = None,
    ) -> dict:
        """Build a user profile from accumulated memories."""
        if not db:
            return {}

        result = await db.execute(
            select(func.count(ConversationMemory.id))
            .where(
                ConversationMemory.organization_id == organization_id,
                ConversationMemory.user_id == user_id,
            )
        )
        total = result.scalar() or 0

        result = await db.execute(
            select(ConversationMemory)
            .where(
                ConversationMemory.organization_id == organization_id,
                ConversationMemory.user_id == user_id,
                ConversationMemory.importance >= 0.7,
            )
            .order_by(desc(ConversationMemory.created_at))
            .limit(20)
        )
        high_importance = result.scalars().all()

        all_facts = []
        for m in high_importance:
            if m.key_facts:
                try:
                    raw_key_facts = decrypt_phi(m.key_facts)
                    kf = json.loads(raw_key_facts) if raw_key_facts else {}
                    # Standardized format: {"facts": [...], "_embedding": [...]}
                    facts_list = kf.get("facts", []) if isinstance(kf, dict) else kf
                    all_facts.extend(facts_list)
                except (json.JSONDecodeError, RuntimeError):
                    pass

        return {
            "total_memories": total,
            "high_value_memories": len(high_importance),
            "top_facts": list(set(all_facts))[:10],
            "last_active": high_importance[0].created_at.isoformat() if high_importance else None,
        }


memory_expert = MemoryExpert()
