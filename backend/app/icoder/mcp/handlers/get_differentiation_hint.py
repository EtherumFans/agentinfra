"""``get_differentiation_hint`` MCP handler — wrap ``medcoder_adapter.get_differentiation_hints``.

Input shape (validated upstream by Pydantic):
  - ``disease_text`` (str, required) — disease name (Chinese preferred)
  - ``code_a`` (str, optional) — first code in a comparison pair
  - ``code_b`` (str, optional) — second code in a comparison pair

Output:
  - ``hints`` — list[str] of P0/P1 differentiation hints (≤3)

Behavior:
  - Calls the existing ``medcoder_adapter.get_differentiation_hints``
    pure function, which reads ``coding_differentiation_kb.json`` from
    ``$ICODER_DATA_ASSET_DIR`` (default ``E:\\iCoDerA\\DataAsset``).
  - If both ``code_a`` and ``code_b`` are supplied, the handler filters
    the KB for entries that mention both codes (P0/P1 priority).
  - Returns ``{"hints": []}`` on KB miss or read error (never raises).
"""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import Request


_KB_PATH = os.path.join(
    os.environ.get("ICODER_DATA_ASSET_DIR", r"E:\iCoDerA\DataAsset"),
    "coding_differentiation_kb.json",
)


def _load_kb() -> list[dict] | None:
    """Best-effort load of coding_differentiation_kb.json.

    Returns ``None`` if the file is missing or malformed. Mirrors the
    fallback semantics of ``medcoder_adapter.get_differentiation_hints``.
    """
    try:
        if not os.path.isfile(_KB_PATH):
            return None
        with open(_KB_PATH, "r", encoding="utf-8", errors="replace") as f:
            kb = json.load(f)
        if isinstance(kb, dict):
            return kb.get("rules") if isinstance(kb.get("rules"), list) else None
        if isinstance(kb, list):
            return kb
        return None
    except Exception:
        return None


def _filter_hints(
    rules: list[dict],
    disease_text: str,
    code_a: str,
    code_b: str,
    max_hints: int = 3,
) -> list[str]:
    """Filter KB rules to P0/P1 entries that match the request.

    Preference order:
      1) Both ``code_a`` and ``code_b`` mentioned in the rule (P0/P1)
      2) ``disease_text`` mentioned in the rule (P0/P1)
    """
    out: list[str] = []
    for r in rules:
        if not isinstance(r, dict):
            continue
        if r.get("priority") not in ("P0", "P1"):
            continue
        text = r.get("text") or r.get("hint") or r.get("description") or ""
        text_str = str(text)[:200]
        if not text_str:
            continue
        rule_blob = json.dumps(r, ensure_ascii=False)
        if code_a and code_b and code_a in rule_blob and code_b in rule_blob:
            out.append(text_str)
        elif disease_text and disease_text in rule_blob:
            out.append(text_str)
        if len(out) >= max_hints:
            break
    return out


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    disease_text: str = (arguments.get("disease_text") or "").strip()
    code_a: str = (arguments.get("code_a") or "").strip()
    code_b: str = (arguments.get("code_b") or "").strip()

    # Fast-path: when both codes are provided, prefer the code-pair filter
    # (more precise than disease-text fuzzy match).
    rules = _load_kb()
    if rules is None:
        return {"hints": []}

    hints = _filter_hints(rules, disease_text, code_a, code_b)
    return {"hints": hints}


__all__ = ["handle"]