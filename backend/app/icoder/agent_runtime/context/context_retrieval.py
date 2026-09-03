"""Bounded, deterministic retrieval over redacted Context messages.

This is the safe Windows fallback while local sentence-transformers are
disabled. It supports unsegmented Chinese using CJK bigrams, preserves final
chronological order, and applies a hard character budget before context enters
the orchestrator prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from .context import ContextMessage


@dataclass(frozen=True)
class ContextMemorySelection:
    messages: list[ContextMessage]
    retrieval_mode: str
    candidate_count: int
    selected_count: int
    selected_characters: int


def _units(text: str) -> set[str]:
    normalized = " ".join((text or "").lower().split())
    words = set(re.findall(r"[a-z0-9]+", normalized))
    cjk_units: set[str] = set()
    for run in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+", normalized):
        if len(run) == 1:
            cjk_units.add(run)
        else:
            cjk_units.update(run[index:index + 2] for index in range(len(run) - 1))
    return words | cjk_units


def lexical_similarity(query: str, candidate: str) -> float:
    query_normalized = " ".join((query or "").lower().split())
    candidate_normalized = " ".join((candidate or "").lower().split())
    if not query_normalized or not candidate_normalized:
        return 0.0
    if query_normalized in candidate_normalized:
        return 1.0
    query_units = _units(query_normalized)
    if not query_units:
        return 0.0
    return len(query_units & _units(candidate_normalized)) / len(query_units)


def message_text(message: ContextMessage) -> str:
    chunks: list[str] = []
    for part in message.parts:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str):
            chunks.append(part["text"])
        elif part.get("kind") == "data" and part.get("data") is not None:
            import json

            chunks.append(json.dumps(part["data"], ensure_ascii=False))
    return "\n".join(chunks).strip()


def select_context_memory(
    query: str,
    messages: Iterable[ContextMessage],
    *,
    limit: int = 8,
    character_budget: int = 6000,
    recent_fallback: int = 4,
) -> ContextMemorySelection:
    """Select relevant prior messages without loading native model code."""
    candidates = list(messages)
    scored = [
        (lexical_similarity(query, message_text(message)), index, message)
        for index, message in enumerate(candidates)
    ]
    selected = [item for item in scored if item[0] > 0]
    if selected:
        selected.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = selected[:max(1, limit)]
    else:
        selected = scored[-max(0, min(recent_fallback, limit)):]

    budgeted: list[tuple[int, ContextMessage]] = []
    consumed = 0
    for _score, index, message in selected:
        text_length = len(message_text(message))
        if text_length == 0:
            continue
        if budgeted and consumed + text_length > character_budget:
            continue
        if not budgeted and text_length > character_budget:
            truncated = message.model_copy(
                update={"parts": [{"kind": "text", "text": message_text(message)[:character_budget]}]}
            )
            budgeted.append((index, truncated))
            consumed = character_budget
            break
        budgeted.append((index, message))
        consumed += text_length

    budgeted.sort(key=lambda item: item[0])
    chosen = [message for _, message in budgeted]
    return ContextMemorySelection(
        messages=chosen,
        retrieval_mode="LEXICAL_CJK_BIGRAM",
        candidate_count=len(candidates),
        selected_count=len(chosen),
        selected_characters=consumed,
    )


__all__ = [
    "ContextMemorySelection",
    "lexical_similarity",
    "message_text",
    "select_context_memory",
]
