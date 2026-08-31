"""Deterministic code-filter semantics shared by Coding v1 and Corti v2.

The model receives the requested filter as guidance, but the public boundary
must enforce it independently.  ``expand=True`` treats a category such as
``E11`` as a prefix and therefore admits/subtracts leaf codes such as
``E11.9``.  ``expand=False`` requires an exact code match.
"""

from __future__ import annotations

from collections.abc import Iterable


def code_allowed_by_filter(
    code: str,
    *,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
    expand: bool = True,
) -> bool:
    """Return whether *code* is admitted by a Corti-style code filter.

    Exclusions always win.  Matching is case-insensitive and ignores
    surrounding whitespace, while the returned code itself is never altered.
    """

    normalized = (code or "").strip().casefold()
    if not normalized:
        return False

    included = _normalized_terms(include)
    excluded = _normalized_terms(exclude)

    if any(_matches(normalized, term, expand=expand) for term in excluded):
        return False
    if included and not any(
        _matches(normalized, term, expand=expand) for term in included
    ):
        return False
    return True


def _normalized_terms(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        normalized
        for value in values
        if (normalized := str(value or "").strip().casefold())
    )


def _matches(code: str, term: str, *, expand: bool) -> bool:
    return code == term or (expand and code.startswith(term))

