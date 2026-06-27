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
        "source": "retrieve",
        # E1.1: surface the Stage 2 degradation state to MCP consumers.
        "degraded": stage2_result.degraded,
        "error_code": stage2_result.error_code,
        "error_detail": stage2_result.error_detail,
    }


__all__ = ["handle"]