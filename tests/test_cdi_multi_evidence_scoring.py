"""Contract tests for future CDI benchmark multi-evidence scoring."""

from __future__ import annotations

import importlib.util
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "corti_parity"
    / "track_h"
    / "05_h4_quality_safety_expert_scoring.py"
)
SPEC = importlib.util.spec_from_file_location("h4_scoring", MODULE_PATH)
assert SPEC and SPEC.loader
SCORING = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCORING)


def _query(*quotes: str) -> dict:
    return {
        "query_id": "q1",
        "query_text": "Please clarify the documented diagnosis for this stay.",
        "response_options": ["A", "B", "C", "Unable to determine"],
        "evidence_spans": [{"quote": quote} for quote in quotes],
    }


def test_all_independent_spans_must_be_supported() -> None:
    chart = "Admission: biliary pancreatitis. Later: idiopathic pancreatitis."

    supported = SCORING._score_query(
        _query("Admission: biliary pancreatitis.", "idiopathic pancreatitis."),
        chart,
    )
    unsupported = SCORING._score_query(
        _query("Admission: biliary pancreatitis.", "pathology confirmed cancer"),
        chart,
    )

    assert supported["evidence_quote_verbatim"] is True
    assert supported["evidence_span_count"] == 2
    assert unsupported["evidence_quote_verbatim"] is False


def test_legacy_primary_span_remains_supported() -> None:
    scored = SCORING._score_query(
        {
            "query_id": "legacy",
            "query_text": "Please clarify this documented diagnosis.",
            "response_options": [],
            "evidence_span": {"quote": "documented fact"},
        },
        "The chart contains a documented fact in this sentence.",
    )

    assert scored["evidence_quote_verbatim"] is True
    assert scored["evidence_span_count"] == 1
