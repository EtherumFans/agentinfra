"""``explore_code`` MCP handler — parent / siblings / children traversal.

Phase 4-C: new tool, mirrors Corti Code Validation's ``explore`` tool.
Given a code or prefix, returns:
  - ``parent`` — the parent chapter + category info
  - ``siblings`` — codes sharing the same category (top 20 by code)
  - ``children`` — more specific subdivisions (top 20 by code)

The LLM uses this when a code is non-assignable, ambiguous, or when a
more specific code might exist (Corti: "explore 在非 assignable / 组合码 /
更具体 code 场景调用").

Input shape:
  - ``code`` (str, required) — e.g. "I25.10" or "I25" or "I25.1"

Output:
  - ``code`` — the input code (echoed)
  - ``parent`` — ``{chapter, chapter_no, category_code, category_name}``
  - ``siblings`` — list of ``{code, name}`` (top 20)
  - ``children`` — list of ``{code, name}`` (top 20)
  - ``in_catalog`` — bool

PHI safety:
  - Input is a code string. Safe to log/trace.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    code: str = (arguments.get("code") or "").strip()

    out: dict[str, Any] = {
        "code": code,
        "parent": None,
        "siblings": [],
        "children": [],
        "in_catalog": False,
    }

    if not code:
        return out

    try:
        from app.services.icd10cn_loader import get_loader
        loader = get_loader()
    except Exception:
        return out

    out["in_catalog"] = bool(loader.has(code))

    # Resolve the entry (either direct hit or via first child of prefix).
    entry = loader.get(code)
    if entry is None:
        # Maybe it's a category prefix — try to find children + use first child's metadata.
        children_codes = _find_codes_with_prefix(loader, code + ".")
        if not children_codes:
            return out
        entry = loader.get(children_codes[0])
        if entry is None:
            return out
    else:
        children_codes = _find_codes_with_prefix(loader, code + ".")

    chapter_no = str(getattr(entry, "chapter_no", "") or "")
    category_code = str(getattr(entry, "category_code", "") or "")
    category_name = ""

    # Parent — the category code's chapter-level info.
    out["parent"] = {
        "chapter": str(loader.chapter_for(code) or ""),
        "chapter_no": chapter_no,
        "category_code": category_code,
        "category_name": category_name,
    }

    # Siblings — codes sharing the same category_code (excluding this code itself).
    if category_code:
        siblings: list[dict[str, str]] = []
        try:
            all_codes = loader.all_codes()
        except Exception:
            all_codes = []
        for e in all_codes:
            ec = getattr(e, "code", "") or ""
            cc = str(getattr(e, "category_code", "") or "")
            if cc == category_code and ec != code:
                siblings.append({
                    "code": ec,
                    "name": str(getattr(e, "name_cn", "") or ""),
                })
                if len(siblings) >= 20:
                    break
        siblings.sort(key=lambda x: x["code"])
        out["siblings"] = siblings

    # Children — codes that start with ``code + "."`` (more specific subdivisions).
    children: list[dict[str, str]] = []
    for child_code in children_codes:
        e = loader.get(child_code)
        if e is not None:
            children.append({
                "code": child_code,
                "name": str(getattr(e, "name_cn", "") or ""),
            })
        if len(children) >= 20:
            break
    children.sort(key=lambda x: x["code"])
    out["children"] = children

    return out


def _find_codes_with_prefix(loader: Any, prefix: str) -> list[str]:
    """Return all codes in the catalog that start with ``prefix``."""
    if not prefix:
        return []
    out: list[str] = []
    try:
        all_codes = loader.all_codes()
    except Exception:
        return []
    for entry in all_codes:
        ec = getattr(entry, "code", "") or ""
        if ec.startswith(prefix):
            out.append(ec)
    out.sort()
    return out


__all__ = ["handle"]
