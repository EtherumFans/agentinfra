"""Deterministic pre-execution safety checks for A2A message payloads.

The detector intentionally recognizes only explicit attempts to override the
runtime's instruction hierarchy or disclose hidden prompts.  A lone word such
as "system", "prompt", "忽略" or "规则" is not sufficient, which keeps ordinary
Chinese clinical notes and technical metadata usable.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PI-001_INSTRUCTION_OVERRIDE_EN",
        re.compile(
            r"\b(?:ignore|disregard|override|bypass|forget)\b.{0,48}"
            r"\b(?:previous|prior|above|system|developer)\b.{0,32}"
            r"\b(?:instruction|instructions|prompt|prompts|rule|rules)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "PI-002_PROMPT_DISCLOSURE_EN",
        re.compile(
            r"\b(?:reveal|show|print|output|expose|leak)\b.{0,40}"
            r"\b(?:system|developer|hidden)\b.{0,24}"
            r"\b(?:prompt|instructions?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
    ),
    (
        "PI-003_INSTRUCTION_OVERRIDE_ZH",
        re.compile(
            r"(?:忽略|无视|绕过|覆盖|取代|忘掉).{0,32}"
            r"(?:之前|此前|以上|上述|系统|开发者).{0,20}"
            r"(?:指令|提示词|规则|要求)",
            re.DOTALL,
        ),
    ),
    (
        "PI-004_PROMPT_DISCLOSURE_ZH",
        re.compile(
            r"(?:泄露|显示|展示|输出|打印|告诉我).{0,32}"
            r"(?:系统|开发者|隐藏).{0,16}(?:提示词|指令|规则)",
            re.DOTALL,
        ),
    ),
)


def _iter_strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_strings(item)


def detect_prompt_injection(payload: Any) -> list[str]:
    """Return stable rule IDs without returning or logging matched content."""

    seen: set[str] = set()
    for raw_text in _iter_strings(payload):
        text = unicodedata.normalize("NFKC", raw_text)
        for rule_id, pattern in _PATTERNS:
            if rule_id not in seen and pattern.search(text):
                seen.add(rule_id)
    return [rule_id for rule_id, _ in _PATTERNS if rule_id in seen]


__all__ = ["detect_prompt_injection"]
