"""Memory Expert — persistent context with semantic vector search.

iCoDer Agentic Framework equivalent: memory-expert + Context & Memory management.
Uses sentence-transformers for local embedding-based semantic search.
"""
import json
import logging
import numpy as np
from datetime import datetime, timedelta, UTC
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.memory import ConversationMemory
from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)

# Lazy-load embedding model (80MB, CPU-friendly)
_embedding_model = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
            logger.info("Embedding model loaded: paraphrase-multilingual-MiniLM-L12-v2")
        except ImportError:
            logger.warning("sentence-transformers not installed. Falling back to keyword search.")
            _embedding_model = False
        except Exception as e:
            logger.warning(f"Embedding model load failed: {e}")
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
    return float(np.dot(a, b))

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
        expert_id: str | None = None,
        agent_id: str | None = None,
        db: AsyncSession | None = None,
    ) -> ConversationMemory | None:
        """Save a conversation message to memory with auto-extracted key facts."""
        mem = ConversationMemory(
            user_id=user_id,
            expert_id=expert_id,
            agent_id=agent_id,
            session_id=session_id,
            role=role,
            content=content[:2000],
        )
        # Auto-extract key facts and importance via LLM
        try:
            result = await llm_service.extract_json(
                prompt=MEMORY_SYSTEM_PROMPT,
                text=f"Role: {role}\nContent: {content[:500]}",
                schema_hint="key_facts array and importance score"
            )
            if isinstance(result, dict):
                facts_list = result.get("key_facts", [])
                mem.importance = float(result.get("importance", 0.5))
                mem.summary = result.get("summary", "")[:200]
            else:
                facts_list = []
        except Exception as e:
            logger.warning(f"Memory fact extraction failed: {e}")
            facts_list = []

        # Store embedding alongside key facts in a standardized format
        emb = _embed(content[:500])
        mem.key_facts = json.dumps({
            "facts": facts_list,
            "_embedding": emb if emb is not None else [],
        }, ensure_ascii=False)

        if db:
            db.add(mem)
            await db.commit()
        return mem

    async def recall(
        self,
        user_id: str,
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

        # Get recent high-importance memories (optionally scoped by expert/agent)
        conditions = [
            ConversationMemory.user_id == user_id,
            ConversationMemory.created_at >= datetime.now(UTC) - timedelta(days=30),
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
            score = 0
            # Semantic similarity (embedding stored in key_facts._embedding)
            if query_emb is not None and m.key_facts:
                try:
                    kf = json.loads(m.key_facts)
                    mem_emb = kf.get("_embedding") if isinstance(kf, dict) else None
                    if isinstance(mem_emb, list) and len(mem_emb) > 10:
                        score = _cosine_similarity(query_emb, mem_emb)
                except (json.JSONDecodeError, ValueError):
                    pass

            # Keyword fallback
            if score < 0.3:
                query_lower = query.lower()
                if any(term in m.content.lower() for term in query_lower.split()):
                    score += 0.5
                if m.key_facts:
                    try:
                        kf = json.loads(m.key_facts)
                        # Standardized format: {"facts": [...], "_embedding": [...]}
                        facts_list = kf.get("facts", []) if isinstance(kf, dict) else kf
                        if any(term in str(f).lower() for f in facts_list for term in query_lower.split()):
                            score += 0.5
                    except json.JSONDecodeError:
                        pass

            if score > 0:
                relevant.append({
                    "id": m.id,
                    "role": m.role,
                    "content": m.content[:300],
                    "summary": m.summary,
                    "key_facts": json.loads(m.key_facts) if m.key_facts else [],
                    "importance": m.importance,
                    "relevance_score": score,
                    "created_at": m.created_at.isoformat(),
                })

        # Sort by combined relevance + importance
        relevant.sort(key=lambda x: x["relevance_score"] + x["importance"], reverse=True)
        return relevant[:limit]

    async def get_session_context(
        self,
        user_id: str,
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
                ConversationMemory.user_id == user_id,
                ConversationMemory.session_id == session_id,
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
            lines.append(f"[{prefix}]: {m.content[:200]}")

        return "\n".join(lines)

    async def ingest_context_messages(
        self,
        context_id: str,
        user_id: str,
        db: AsyncSession,
        agent_id: str | None = None,
    ) -> int:
        """Bridge real Context messages into long-term ConversationMemory rows.

        Called by A1B-AE-R.4.b — wires the persistent memory store to the
        A2A Context. Reads every ContextMessageRow for the given context,
        extracts plain-text content from parts_json, and saves one
        ConversationMemory row per message (de-duplicated by session_id
        = context_id + message_id).

        Returns the number of memories saved. Skips messages already
        ingested (idempotent per session_id+content hash).
        """
        from app.icoder.agent_runtime.context.db_models import ContextMessageRow

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
            session_key = f"{context_id}:{m.message_id}"
            try:
                parts = json.loads(m.parts_json) if m.parts_json else []
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
                text_parts.append(str(m.parts_json))

            content = " ".join(text_parts).strip()
            if not content:
                continue

            existing = await db.execute(
                select(ConversationMemory)
                .where(
                    ConversationMemory.user_id == user_id,
                    ConversationMemory.session_id == session_key,
                )
                .limit(1)
            )
            if existing.scalars().first() is not None:
                continue

            mem = ConversationMemory(
                user_id=user_id,
                agent_id=agent_id,
                session_id=session_key,
                role=(m.role or "user").lower(),
                content=content[:2000],
            )
            emb = _embed(content[:500])
            mem.key_facts = json.dumps(
                {
                    "facts": [],
                    "_embedding": emb if emb is not None else [],
                    "source": "context",
                    "context_id": context_id,
                    "message_id": m.message_id,
                    "redacted": m.redacted,
                },
                ensure_ascii=False,
            )
            mem.importance = 0.4
            db.add(mem)
            saved += 1

        if saved > 0:
            await db.commit()
        return saved

    async def get_user_profile(self, user_id: str, db: AsyncSession | None = None) -> dict:
        """Build a user profile from accumulated memories."""
        if not db:
            return {}

        result = await db.execute(
            select(func.count(ConversationMemory.id))
            .where(ConversationMemory.user_id == user_id)
        )
        total = result.scalar() or 0

        result = await db.execute(
            select(ConversationMemory)
            .where(ConversationMemory.user_id == user_id, ConversationMemory.importance >= 0.7)
            .order_by(desc(ConversationMemory.created_at))
            .limit(20)
        )
        high_importance = result.scalars().all()

        all_facts = []
        for m in high_importance:
            if m.key_facts:
                try:
                    kf = json.loads(m.key_facts)
                    # Standardized format: {"facts": [...], "_embedding": [...]}
                    facts_list = kf.get("facts", []) if isinstance(kf, dict) else kf
                    all_facts.extend(facts_list)
                except json.JSONDecodeError:
                    pass

        return {
            "total_memories": total,
            "high_value_memories": len(high_importance),
            "top_facts": list(set(all_facts))[:10],
            "last_active": high_importance[0].created_at.isoformat() if high_importance else None,
        }


memory_expert = MemoryExpert()
