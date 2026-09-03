from __future__ import annotations

import copy

import pytest

from app.services.offline_evaluation import (
    OfflineEvaluationError,
    _sha,
    build_reference_prediction_packet,
    evaluate_prediction_packet,
    load_offline_cases,
    validate_offline_report,
)


def _resign(packet: dict) -> dict:
    packet = copy.deepcopy(packet)
    packet.pop("packet_sha256", None)
    packet["packet_sha256"] = _sha(packet)
    return packet


def test_all_26_visible_agents_are_wired_to_one_offline_suite() -> None:
    suite, cases, dataset_sha256 = load_offline_cases()
    assert len(cases) == 26
    assert len({case.agent_id for case in cases}) == 26
    assert {case.agent_id for case in cases} == set(suite["expected_agent_ids"])
    assert len(dataset_sha256) == 64

    packet = build_reference_prediction_packet()
    report = evaluate_prediction_packet(packet)
    validate_offline_report(report)
    assert report["passed"] is True
    assert report["passed_case_count"] == 26
    assert report["exact_reference_match_count"] == 26
    assert report["case_text_emitted"] is False
    assert "input_text" not in str(report)


def test_contract_regression_is_localized_without_emitting_case_content() -> None:
    packet = build_reference_prediction_packet()
    removed = next(iter(packet["items"][0]["output"]))
    packet["items"][0]["output"].pop(removed)
    report = evaluate_prediction_packet(_resign(packet))
    assert report["passed"] is False
    assert report["passed_case_count"] == 25
    failed = [row for row in report["agents"] if not row["passed"]]
    assert len(failed) == 1
    assert failed[0]["missing_required_count"] == 1
    assert removed not in str(failed[0])


def test_tampered_prediction_packet_is_rejected() -> None:
    packet = build_reference_prediction_packet()
    packet["items"].pop()
    with pytest.raises(OfflineEvaluationError, match="OFFLINE_PACKET_INVALID"):
        evaluate_prediction_packet(packet)
