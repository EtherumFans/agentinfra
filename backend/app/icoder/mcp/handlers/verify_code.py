"""``verify_code`` MCP handler — catalog membership check via icd10cn_loader.

Input shape (validated upstream by Pydantic):
  - ``code`` (str, required, e.g. "I50.900")

Output:
  - ``in_catalog`` — bool, true iff code is in icd10cn_code_catalog
  - ``chapter`` — ICD-10 chapter heading (empty if unknown)
  - ``name`` — canonical Chinese name (empty if unknown)
  - ``aliases`` — top 10 Chinese synonyms (empty if unknown)

Behavior:
  - Delegates to ``app.services.icd10cn_loader.get_loader()`` for catalog
    membership + chapter / name / synonyms lookup. This is the canonical
    loader used everywhere else in the codebase (retriever, FAISS index
    builder, code review report, etc.).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    code: str = (arguments.get("code") or "").strip()

    out: dict[str, Any] = {
        "code": code,
        "in_catalog": False,
        "chapter": "",
        "name": "",
        "aliases": [],
    }

    try:
        from app.services.icd10cn_loader import get_loader
        loader = get_loader()
    except Exception:
        # Catalog unavailable (e.g., asset dir not mounted) — return
        # "unknown" rather than raising; the client can decide what to do.
        return out

    out["in_catalog"] = bool(loader.has(code))
    if not out["in_catalog"]:
        return out

    entry = loader.get(code)
    if entry is None:
        return out

    out["name"] = str(entry.name_cn or "")
    out["chapter"] = str(loader.chapter_for(code) or "")
    # Synonyms: top 10 Chinese (the most informative for Chinese EMRs).
    syns = list(entry.synonyms_cn or ())
    out["aliases"] = [str(s) for s in syns[:10] if s]
    return out


__all__ = ["handle"]