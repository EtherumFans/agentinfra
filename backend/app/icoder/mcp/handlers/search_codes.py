"""``search_codes`` MCP handler — alias for ``search_icd`` (PHI-redacted).

Phase 4-C: new tool, mirrors Corti Code Validation's ``search`` tool.
Wraps the existing ``search_icd`` handler so the LLM can request
alternative code candidates when the original assignment is wrong or
non-assignable.

Input shape:
  - ``query`` (str, required) — EMR text or disease mention
  - ``top_k`` (int, optional, 1-50, default 5)

Behavior:
  - Normalizes ``query`` → ``emr_text`` and delegates to
    ``app.icoder.mcp.handlers.search_icd.handle``.
  - All PHI redaction + scope check + governance gate logic is shared
    with ``search_icd`` (the dispatcher already enforces it).

Output: same as ``search_icd`` (``candidates`` + ``source`` + ``degraded``).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    # Normalize: accept both ``query`` (Corti-style) and ``emr_text``
    # (legacy) for backwards compatibility with callers that already
    # used the search_icd schema.
    query: str = (
        arguments.get("query")
        or arguments.get("emr_text")
        or ""
    )
    top_k: int = int(arguments.get("top_k", 5))

    # Delegate to search_icd.handle — reuse the existing handler so
    # PHI redaction, governance gate, and FAISS retrieval stay unified.
    from app.icoder.mcp.handlers.search_icd import handle as search_icd_handle
    return await search_icd_handle(
        {"emr_text": query, "top_k": top_k},
        request,
    )


__all__ = ["handle"]
