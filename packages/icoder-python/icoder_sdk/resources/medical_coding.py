"""Typed Medical Coding prediction and pre-run pricing helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from ..client import iCoDerClient
from ..request_options import RequestOptions


CodingMode = Literal["corti_like_fast", "medcoder_deep"]
ChinaCodingSystem = Literal["icd10cn", "icd9cm3"]


class MedicalCodingResource:
    def __init__(self, client: iCoDerClient):
        self._client = client

    def predict(
        self,
        text: str,
        *,
        mode: CodingMode = "corti_like_fast",
        coding_system: ChinaCodingSystem | None = None,
        coding_systems: Sequence[ChinaCodingSystem] | None = None,
        include_evidence: bool = True,
        include_trace: bool = True,
        include_codes: Sequence[str] | None = None,
        exclude_codes: Sequence[str] | None = None,
        expand_categories: bool = True,
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        if not isinstance(text, str) or not text.strip() or len(text) > 16000:
            raise ValueError("text must contain between 1 and 16000 characters")
        if mode not in ("corti_like_fast", "medcoder_deep"):
            raise ValueError("mode must be corti_like_fast or medcoder_deep")
        normalized_systems = _normalize_systems(coding_system, coding_systems)
        code_filter = _normalize_filter(
            include_codes or (),
            exclude_codes or (),
            expand_categories,
        )
        response = self._client.post(
            "/api/v1/coding/predict",
            json={
                "text": text,
                "mode": mode,
                "coding_systems": normalized_systems,
                "include_evidence": include_evidence,
                "include_trace": include_trace,
                "filter": code_filter,
            },
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()

    def estimate_cost(
        self,
        input_chars: int,
        *,
        mode: CodingMode = "corti_like_fast",
        request_options: RequestOptions | None = None,
    ) -> dict[str, Any]:
        if not isinstance(input_chars, int) or isinstance(input_chars, bool):
            raise TypeError("input_chars must be an integer")
        if input_chars < 0 or input_chars > 16000:
            raise ValueError("input_chars must be between 0 and 16000")
        response = self._client.get(
            "/api/v1/coding/pricing",
            params={"input_chars": input_chars, "mode": mode},
            request_options=request_options,
        )
        response.raise_for_status()
        return response.json()


def _normalize_filter(
    include: Sequence[str],
    exclude: Sequence[str],
    expand: bool,
) -> dict[str, Any]:
    normalized_include = _normalize_terms(include)
    normalized_exclude = _normalize_terms(exclude)
    if len(normalized_include) + len(normalized_exclude) > 100:
        raise ValueError(
            "filter include and exclude may contain at most 100 entries combined"
        )
    return {
        "include": normalized_include,
        "exclude": normalized_exclude,
        "expand": bool(expand),
    }


def _normalize_systems(
    coding_system: ChinaCodingSystem | None,
    coding_systems: Sequence[ChinaCodingSystem] | None,
) -> list[ChinaCodingSystem]:
    if coding_system is not None and coding_systems is not None:
        raise ValueError("use coding_system or coding_systems, not both")
    systems = list(coding_systems) if coding_systems is not None else [
        coding_system or "icd10cn"
    ]
    if len(systems) < 1 or len(systems) > 2:
        raise ValueError("coding_systems must contain one or two systems")
    if any(system not in ("icd10cn", "icd9cm3") for system in systems):
        raise ValueError("coding_systems entries must be icd10cn or icd9cm3")
    if len(set(systems)) != len(systems):
        raise ValueError("coding_systems must not contain duplicates")
    return systems


def _normalize_terms(values: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if not isinstance(raw, str):
            raise TypeError("code filter entries must be strings")
        value = raw.strip()
        if (
            not value
            or len(value) > 64
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
        ):
            raise ValueError(
                "code filter entries must contain between 1 and 64 printable characters"
            )
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            normalized.append(value)
    return normalized
