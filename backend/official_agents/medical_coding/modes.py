"""MedicalCodingOutputSchema.mode — StrEnum + coercion helpers.

Per ``MEDCODER_CAPABILITY_AUDIT.md`` Part 7.4 (M2), the
``MedicalCodingOutputSchema.mode`` field is upgraded from a free-form
``str`` to a :class:`Mode` ``str`` ``Enum`` so:

  - the set of valid mode strings is enforced at type-check time
  - the M1 mode vocabulary (``medcoder`` / ``medcoder_full`` /
    ``medcoder_prompt`` / ``medcoder_retrieve`` /
    ``medcoder_prompt+retrieve``) is centralized in one SSOT
  - legacy modes (``deepseek`` / ``prompt_llm`` / ``hybrid`` /
    ``no_repair``) keep working unchanged

String-compat guarantees:

  - ``Mode`` extends ``(str, Enum)`` so every member IS its own string
    value (``Mode.MEDCODER == "medcoder"`` is True).
  - ``to_dict`` / JSON serialization is unchanged — enum members print
    as their string value.
  - ``from_dict`` uses :func:`coerce` which accepts both ``str`` and
    ``Mode``, returning :attr:`Mode.UNSET` for unknown values rather
    than raising (defensive against persisted JSON from older versions).
"""

from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    """Valid ``MedicalCodingOutputSchema.mode`` values.

    The canonical values are the 5 MedCodER modes (per M1). The 4 legacy
    values are retained for backward compat with persisted JSON and the
    existing evaluation harness. :attr:`UNSET` is the default for fresh
    schemas (e.g. ``mock_result()``).

    Why a ``str`` Enum (not plain Enum):
      - ``Mode.MEDCODER == "medcoder"`` must remain True so old code
        that compares ``schema.mode == "medcoder"`` keeps working.
      - ``json.dumps(Mode.MEDCODER) == '"medcoder"'`` (no extra
        serialization layer needed).
    """

    UNSET = ""
    DEEPSEEK = "deepseek"            # legacy
    PROMPT_LLM = "prompt_llm"        # legacy
    HYBRID = "hybrid"                # legacy
    NO_REPAIR = "no_repair"          # legacy
    MEDCODER = "medcoder"            # canonical alias for MEDCODER_FULL
    MEDCODER_FULL = "medcoder_full"
    MEDCODER_PROMPT = "medcoder_prompt"
    MEDCODER_RETRIEVE = "medcoder_retrieve"
    MEDCODER_PROMPT_RETRIEVE = "medcoder_prompt+retrieve"
    # Phase C: Code Like Humans 4-step pipeline.
    # Lives in the MedCodER family because it's a structured-pipeline
    # variant (vs. the single-shot legacy modes), but it does NOT use
    # FAISS — it relies on local code_dict_service + LLM, so it works
    # in environments where BGE-M3+FAISS is not built.
    MEDCODER_CODE_LIKE_HUMANS = "code_like_humans"


# ── Vocabulary groupings ──


MEDCODER_MODES: tuple[Mode, ...] = (
    Mode.MEDCODER,
    Mode.MEDCODER_FULL,
    Mode.MEDCODER_PROMPT,
    Mode.MEDCODER_RETRIEVE,
    Mode.MEDCODER_PROMPT_RETRIEVE,
    Mode.MEDCODER_CODE_LIKE_HUMANS,
)


LEGACY_MODES: tuple[Mode, ...] = (
    Mode.DEEPSEEK,
    Mode.PROMPT_LLM,
    Mode.HYBRID,
    Mode.NO_REPAIR,
)


# ── Coercion helper ──


def coerce(value) -> Mode:
    """Robustly coerce ``value`` to a :class:`Mode`.

    Accepts:
      - A :class:`Mode` instance → returned unchanged.
      - A ``str`` → looked up; falls back to :attr:`Mode.UNSET` on unknown.
      - Anything else (None, int, list, ...) → :attr:`Mode.UNSET`.

    The fallback to ``UNSET`` is intentional — persisted JSON from older
    versions may contain ``mode=""`` (M0 ``mock_result``) or
    unknown values. Raising ``ValueError`` there would break deserialization
    on startup.
    """
    if isinstance(value, Mode):
        return value
    if isinstance(value, str):
        try:
            return Mode(value)
        except ValueError:
            return Mode.UNSET
    return Mode.UNSET


__all__ = ["Mode", "MEDCODER_MODES", "LEGACY_MODES", "coerce"]