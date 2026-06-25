"""M2 — ``Mode`` StrEnum tests (~6 cases).

Per ``MEDCODER_CAPABILITY_AUDIT.md`` Part 7.4 (M2), ``Mode`` is the SSOT
for ``MedicalCodingOutputSchema.mode``. Asserts:

  - 10 members + ``UNSET`` = 11 total (Phase C added CLH)
  - ``MEDCODER_MODES`` = 6 (canonical alias + 4 explicit variants + CLH)
  - ``LEGACY_MODES`` = 4 (deepseek / prompt_llm / hybrid / no_repair)
  - StrEnum guarantees: ``Mode.MEDCODER == "medcoder"`` is True, and
    ``json.dumps`` produces the string value (not ``"Mode.MEDCODER"``)
  - ``coerce()`` accepts both ``Mode`` and ``str``, falling back to
    ``UNSET`` on unknown values (R1 from plan — persisted JSON compat)
"""

from __future__ import annotations

import json

from official_agents.medical_coding.modes import (
    Mode, MEDCODER_MODES, LEGACY_MODES, coerce,
)


def test_mode_has_11_members():
    """10 named modes + UNSET = 11 total (Phase C added code_like_humans)."""
    assert len(Mode) == 11


def test_medcoder_modes_has_6():
    """MEDCODER_MODES groups canonical alias + 4 NAACL variants + CLH."""
    assert len(MEDCODER_MODES) == 6
    assert set(MEDCODER_MODES) == {
        Mode.MEDCODER,
        Mode.MEDCODER_FULL,
        Mode.MEDCODER_PROMPT,
        Mode.MEDCODER_RETRIEVE,
        Mode.MEDCODER_PROMPT_RETRIEVE,
        Mode.MEDCODER_CODE_LIKE_HUMANS,
    }


def test_legacy_modes_has_4():
    """LEGACY_MODES groups the 4 pre-MedCodER modes (deepseek family)."""
    assert len(LEGACY_MODES) == 4
    assert set(LEGACY_MODES) == {
        Mode.DEEPSEEK,
        Mode.PROMPT_LLM,
        Mode.HYBRID,
        Mode.NO_REPAIR,
    }


def test_mode_is_string_enum_string_compat():
    """StrEnum guarantees — ``Mode.MEDCODER == "medcoder"`` is True.

    This is the load-bearing property that keeps the StrEnum refactor
    backward-compatible with all existing ``mode == "medcoder"`` checks
    scattered across the codebase.
    """
    assert Mode.MEDCODER == "medcoder"
    assert Mode.DEEPSEEK == "deepseek"
    assert Mode.UNSET == ""
    # ``in`` operator still works against a tuple of plain strings.
    assert Mode.MEDCODER in ("medcoder", "medcoder_full")
    assert Mode.UNSET not in ("medcoder", "deepseek")


def test_mode_json_serialization():
    """``json.dumps(Mode.X)`` returns the string value, not the member repr."""
    assert json.dumps(Mode.MEDCODER) == '"medcoder"'
    assert json.dumps(Mode.UNSET) == '""'
    assert json.dumps(Mode.MEDCODER_PROMPT_RETRIEVE) == '"medcoder_prompt+retrieve"'


def test_coerce_accepts_str_and_mode():
    """``coerce()`` accepts both ``Mode`` and ``str``, returning ``Mode``."""
    # Mode passthrough
    assert coerce(Mode.MEDCODER) is Mode.MEDCODER
    # String lookup
    assert coerce("medcoder") is Mode.MEDCODER
    assert coerce("medcoder_full") is Mode.MEDCODER_FULL
    assert coerce("") is Mode.UNSET
    # Defensive fallback (R1): unknown values → UNSET, not raise.
    # This protects deserialization of persisted JSON from older versions
    # that may carry stale or empty mode strings.
    assert coerce("nonexistent_mode") is Mode.UNSET
    assert coerce(None) is Mode.UNSET
    assert coerce(42) is Mode.UNSET
    assert coerce(["medcoder"]) is Mode.UNSET