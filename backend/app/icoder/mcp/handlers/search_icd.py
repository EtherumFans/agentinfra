"""``search_icd`` MCP handler — wraps ``MedCodERStrategy.stage2_retrieve``.

Input shape (validated upstream by Pydantic):
  - ``emr_text`` (str, required, 1-20000 chars)
  - ``top_k`` (int, optional, 1-50, default 5)

Output:
  - ``candidates`` — list of dicts (each ``code/name/score/chapter/source``)
  - ``source`` — always ``"retrieve"``

Behavior:
  - Reads the per-request ``MedCodERStrategy`` from ``app.state.medcoder_strategy``
    (set by ``mount_mcp``).
  - **M2.5 governance gate**: if the FAISS index health check reported
    ``status="degraded"`` at startup, return ``-32002 Retriever
    Unavailable`` instead of silently returning ``[]``. This closes
    the silent-degradation hole that bit us on 2026-06-19 (the FAISS
    index disappeared, F1@1 dropped to 0.09, no error surfaced).
  - When health is OK but the strategy's retriever is still None
    (e.g. lazy init failed mid-request), also return ``-32002``.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    emr_text: str = arguments.get("emr_text", "").strip()
    top_k: int = int(arguments.get("top_k", 5))

    # M2.5: governance gate. Read the health report from app.state
    # (populated by app.main lifespan startup). If degraded, raise
    # -32002 so the client knows retrieval is unavailable, not "empty".
    health = getattr(request.app.state, "medcoder_index_health", None)
    if health is None or health.get("status") != "ok":
        from app.icoder.mcp.errors import MCPError, MCPErrorCode
        reason = (
            health.get("reason", "no health report")
            if isinstance(health, dict) else "no health report"
        )
        # On Windows we may deliberately disable the native Torch/FAISS
        # stack after a validated access-violation finding.  In that one
        # explicit safety state, use the read-only ICD catalog without ever
        # importing the unsafe native stack.  Other degraded states (missing
        # or corrupt index, unknown health) continue to fail closed.
        if _native_stack_safely_disabled(reason):
            candidates = _lexical_catalog_fallback(emr_text, top_k=top_k)
            if candidates:
                return {
                    "candidates": candidates,
                    "source": "lexical_catalog_fallback",
                    "degraded": False,
                    "error_code": "MEDCODER_RETRIEVE_LEXICAL_FALLBACK",
                    "error_detail": (
                        "semantic retriever safely disabled; exact catalog "
                        "term/code lookup used"
                    ),
                }
        raise MCPError(
            code=MCPErrorCode.RETRIEVER_UNAVAILABLE,
            message=(
                f"MedCodER FAISS index is degraded: {reason}. "
                "Rebuild with: python scripts/build_medcoder_index.py"
            ),
            data={"health": health} if isinstance(health, dict) else None,
        )

    strategy = request.app.state.medcoder_strategy
    if strategy is None:
        from app.icoder.mcp.errors import MCPError, MCPErrorCode
        raise MCPError(
            code=MCPErrorCode.RETRIEVER_UNAVAILABLE,
            message="MedCodERStrategy not initialized on app.state",
        )

    # Stage 2 takes a disease mention; for ``search_icd`` we treat the whole
    # ``emr_text`` as one query. The strategy's retriever handles sentence-
    # boundary splitting if needed downstream (Stage 2 with long input).
    #
    # E1.1 (2026-06-26): ``stage2_retrieve`` now returns a ``Stage2Result``
    # envelope (candidates + degraded + error_code). The MCP handler
    # surfaces ``degraded`` + ``error_code`` to the caller so the
    # consumer can route around missing retriever gracefully.
    stage2_result = await strategy.stage2_retrieve(emr_text, top_k=top_k)
    candidates = stage2_result.candidates
    source = "retrieve"
    degraded = stage2_result.degraded
    error_code = stage2_result.error_code
    error_detail = stage2_result.error_detail

    # Windows safety fallback: the semantic BGE runtime is deliberately
    # disabled when its native Torch stack is known unsafe. The verified
    # 37,897-code read-only catalog still provides exact term/code lookup
    # without importing Torch, PyArrow or FAISS. This is narrower than
    # semantic retrieval, so provenance must say lexical_fallback.
    if stage2_result.degraded and stage2_result.error_code == "MEDCODER_RETRIEVER_UNAVAILABLE":
        candidates = _lexical_catalog_fallback(emr_text, top_k=top_k)
        if candidates:
            source = "lexical_catalog_fallback"
            degraded = False
            error_code = "MEDCODER_RETRIEVE_LEXICAL_FALLBACK"
            error_detail = "semantic retriever unavailable; exact catalog term/code lookup used"

    # Convert CandidateCode dataclasses to dicts for JSON serialization.
    out: list[dict] = []
    for c in candidates or []:
        if hasattr(c, "to_dict"):
            out.append(c.to_dict())
        elif isinstance(c, dict):
            out.append(c)
        else:
            out.append({"code": str(c), "name": "", "score": 0.0,
                        "chapter": "", "source": "retrieve"})

    return {
        "candidates": out,
        "source": source,
        # E1.1: surface the Stage 2 degradation state to MCP consumers.
        "degraded": degraded,
        "error_code": error_code,
        "error_detail": error_detail,
    }


def _lexical_catalog_fallback(emr_text: str, *, top_k: int) -> list[dict[str, Any]]:
    """Exact, provenance-preserving lookup in the read-only ICD-10-CN catalog."""
    try:
        from app.services.icd10cn_loader import get_loader

        loader = get_loader()
        terms: list[str] = []
        for code in re.findall(r"\b[A-Z][0-9]{2}(?:\.[0-9A-Z]+)?\b", emr_text.upper()):
            terms.append(code)
        # Prefer longer chart phrases first, then individual tokens. Exact
        # term-index lookup rejects unrelated fuzzy matches.
        chunks = [
            chunk.strip(" ，。；：、,:;()（）\n\t")
            for chunk in re.split(r"[，。；：、,:;()（）\n\t]", emr_text)
        ]
        terms.extend(sorted((chunk for chunk in chunks if chunk), key=len, reverse=True))
        terms.extend(re.findall(r"[\u4e00-\u9fff]{2,20}", emr_text))

        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for term in terms:
            direct = loader.get(term.upper())
            codes = [direct.code] if direct is not None else loader.codes_for_term(term)
            for code in codes:
                if code in seen:
                    continue
                entry = loader.get(code)
                if entry is None:
                    continue
                seen.add(code)
                out.append({
                    "code": entry.code,
                    "name": entry.name_cn,
                    "score": 1.0,
                    "chapter": loader.chapter_for(entry.code),
                    "source": "lexical_catalog_fallback",
                    "matched_term": term,
                })
                if len(out) >= top_k:
                    return out
        return out
    except (FileNotFoundError, OSError, ValueError):
        return []


def _native_stack_safely_disabled(reason: Any) -> bool:
    normalized = str(reason or "").strip().lower()
    return (
        "known_unsafe_windows_native_stack" in normalized
        or "windows_native_stack_disabled" in normalized
    )


__all__ = ["handle"]
