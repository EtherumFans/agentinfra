"""``rerank_codes`` MCP handler — wraps ``MedCodERStrategy.stage4_rerank``.

Input shape (validated upstream by Pydantic):
  - ``disease_text`` (str, required)
  - ``evidence`` (str, optional, default "")
  - ``candidates`` (list[dict], required, 1-50 entries)

Output:
  - ``ranked`` — list[dict] of top-K re-ranked codes
    (each ``code/name/confidence/rationale``)

Behavior:
  - Delegates to ``MedCodERStrategy.stage4_rerank(disease_text, evidence, candidates, hints)``.
  - M2 does NOT inject CoT few-shot (``cot_generation_progress_v2.json``);
    that's M3 per the audit (Part 7.4 last bullet). For now, the
    handler may optionally pull P0/P1 hints via the get_differentiation_hint
    logic and pass them as the ``hints`` argument to stage 4.
"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from app.icoder.mcp.handlers.get_differentiation_hint import _filter_hints, _load_kb


async def handle(arguments: dict[str, Any], request: Request) -> dict[str, Any]:
    disease_text: str = (arguments.get("disease_text") or "").strip()
    evidence: str = (arguments.get("evidence") or "").strip()
    candidates: list[dict] = arguments.get("candidates") or []

    # Best-effort hints (M2: no CoT few-shot yet; P0/P1 hints only).
    hints: list[str] = []
    try:
        rules = _load_kb()
        if rules:
            hints = _filter_hints(rules, disease_text, "", "", max_hints=3)
    except Exception:
        hints = []

    strategy = request.app.state.medcoder_strategy
    ranked = await strategy.stage4_rerank(
        disease_text=disease_text,
        evidence=evidence,
        candidates=candidates,
        hints=hints,
    )

    # Normalize: ensure each entry is a plain dict (no CandidateCode leakage).
    out: list[dict] = []
    for r in ranked or []:
        if isinstance(r, dict):
            out.append({
                "code": str(r.get("code", "")),
                "name": str(r.get("name", "")),
                "confidence": float(r.get("confidence", 0.0)),
                "rationale": str(r.get("rationale", "")),
            })

    return {"ranked": out}


__all__ = ["handle"]