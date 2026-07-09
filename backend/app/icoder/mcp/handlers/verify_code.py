"""``verify_code`` MCP handler — catalog membership + assignability + hierarchy.

Phase 4-C: extended to mirror Corti Code Validation's ``verify`` tool.
Verifies whether a code is in the icd10cn_code_catalog (37,897 codes),
returns the chapter + category hierarchy, and lists more specific
subdivisions when the code itself is non-assignable (a category, not
a leaf code).

Input shape (validated upstream by Pydantic):
  - ``code`` (str, required, e.g. "I50.900" or "I25")

Output:
  - ``code`` — the input code (echoed back)
  - ``in_catalog`` — bool, true iff the code is a known code OR category prefix
  - ``assignable`` — bool, true iff ``code`` is a leaf code (not a category).
    A category code (e.g. "I25") is in the catalog but not assignable —
    the LLM must pick a more specific subdivision.
  - ``name`` — canonical Chinese name (empty if unknown)
  - ``chapter`` — ICD-10 chapter label like "第9章 循环系统疾病"
  - ``parent_hierarchy`` — [chapter_no, category_code, code]
  - ``aliases`` — top 10 Chinese synonyms
  - ``excludes1`` / ``excludes2`` — list of code refs (Phase 4-C: empty,
    no Excludes KB yet — forward-compat slot)
  - ``code_first_notes`` / ``use_additional_code_notes`` — list of notes
    (Phase 4-C: empty, no notes KB yet — forward-compat slot)
  - ``children_if_non_assignable`` — list of ``{code, name}`` dicts for
    subdivisions of this code when ``assignable=False`` (top 20 by code)

Behavior:
  - Delegates to ``app.services.icd10cn_loader.get_loader()``.
  - When ``code`` is not in catalog but is a prefix (e.g. "I25" with
    children "I25.0", "I25.1", ...), returns ``in_catalog=True``,
    ``assignable=False`` and lists children.
  - When ``code`` is not in catalog AND has no children, returns
    ``in_catalog=False`` with everything empty.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    code: str = (arguments.get("code") or "").strip()

    out: dict[str, Any] = {
        "code": code,
        "in_catalog": False,
        "assignable": False,
        "chapter": "",
        "name": "",
        "aliases": [],
        "parent_hierarchy": [],
        "excludes1": [],
        "excludes2": [],
        "code_first_notes": [],
        "use_additional_code_notes": [],
        "children_if_non_assignable": [],
    }

    try:
        from app.services.icd10cn_loader import get_loader
        loader = get_loader()
    except Exception:
        return out

    # Direct catalog hit → assignable leaf code.
    if loader.has(code):
        out["in_catalog"] = True
        out["assignable"] = True
        entry = loader.get(code)
        if entry is not None:
            out["name"] = str(entry.name_cn or "")
            out["chapter"] = str(loader.chapter_for(code) or "")
            syns = list(entry.synonyms_cn or ())
            out["aliases"] = [str(s) for s in syns[:10] if s]
            out["parent_hierarchy"] = _build_hierarchy(entry, code)
        return out

    # Not a direct hit — check if it's a category prefix with children.
    children = _find_children(loader, code)
    if children:
        out["in_catalog"] = True
        out["assignable"] = False
        out["children_if_non_assignable"] = children[:20]
        # Try to get chapter + name from the first child.
        first_child_code = children[0].get("code", "") if children else ""
        if first_child_code:
            entry = loader.get(first_child_code)
            if entry is not None:
                out["name"] = f"(category) {entry.chapter_name or ''}".strip()
                out["chapter"] = str(loader.chapter_for(first_child_code) or "")
                out["parent_hierarchy"] = [
                    entry.chapter_no or "",
                    code,
                    code,
                ]
        return out

    # Unknown code, no children → leave in_catalog=False.
    return out


def _build_hierarchy(entry: Any, code: str) -> list[str]:
    """Build the parent hierarchy: [chapter_no, category_code, code]."""
    chapter_no = getattr(entry, "chapter_no", "") or ""
    category_code = getattr(entry, "category_code", "") or ""
    return [str(chapter_no), str(category_code), str(code)]


def _find_children(loader: Any, prefix: str) -> list[dict[str, str]]:
    """Find more specific subdivisions of ``prefix``.

    A code like "I25" is a category — its children are "I25.0", "I25.1",
    etc. A code like "I25.1" has children "I25.10", "I25.11", etc.
    """
    if not prefix:
        return []
    # Match codes that start with ``prefix + "."`` or ``prefix + digit``.
    # The catalog uses dot-separated subdivisions (I25.10), so the
    # simplest check is "starts with prefix + '.'".
    child_prefix = prefix.rstrip(".") + "."
    out: list[dict[str, str]] = []
    try:
        all_codes = loader.all_codes()
    except Exception:
        return []
    for entry in all_codes:
        ec = getattr(entry, "code", "") or ""
        if ec.startswith(child_prefix):
            out.append({
                "code": ec,
                "name": str(getattr(entry, "name_cn", "") or ""),
            })
    # Sort by code for deterministic output.
    out.sort(key=lambda x: x["code"])
    return out


__all__ = ["handle"]
