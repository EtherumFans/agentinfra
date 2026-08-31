from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.corti_parity.bilingual_coding_gold_review import (
    BILINGUAL_FIXTURE,
    build_adjudication_template,
    build_blind_packet,
    build_review_template,
    canonical_sha256,
    compare_completed_reviews,
    validate_blind_packet,
    validate_completed_review,
    validate_completed_adjudication,
    write_readiness_bundle,
)


EVIDENCE_TERMS = {
    "S22.000": ("T12 椎体压缩性骨折", "T12 vertebral compression fracture"),
    "M81.900": ("骨质疏松", "osteoporosis"),
    "I10.x09": ("原发性高血压", "essential hypertension"),
    "E11.900": ("2 型糖尿病", "type 2 diabetes"),
    "K35.800x001": ("急性单纯性阑尾炎", "acute simple appendicitis"),
    "J18.900": ("社区获得性肺炎", "community-acquired pneumonia"),
    "E11.100": ("2 型糖尿病性酮症酸中毒", "type 2 diabetic ketoacidosis"),
    "I21.100": (
        "急性下壁 ST 段抬高型心肌梗死",
        "acute inferior ST-elevation myocardial infarction",
    ),
    "E78.500": ("高脂血症", "hyperlipidemia"),
}
PROCEDURE_EVIDENCE_TERMS = {
    "03.5301": (
        "T12 椎体切开复位内固定术",
        "T12 open reduction and internal fixation",
    ),
    "47.0100": ("腹腔镜阑尾切除术", "laparoscopic appendectomy"),
    "36.0601": ("药物涂层支架植入", "drug-eluting stent implantation"),
}


def _exact_chart_span(chart: str, candidate: str) -> str:
    start = chart.casefold().find(candidate.casefold())
    assert start >= 0, (candidate, chart)
    return chart[start : start + len(candidate)]


def _completed_review(
    packet: dict[str, Any], *, reviewer_id: str
) -> dict[str, Any]:
    fixture = json.loads(BILINGUAL_FIXTURE.read_text(encoding="utf-8"))
    source_cases = {
        str(case["case_id"]): case for case in fixture["cases"]
    }
    review = build_review_template(packet, reviewer_slot=reviewer_id)
    review["response_status"] = "completed"
    review["reviewer"] = {
        "reviewer_slot": reviewer_id,
        "reviewer_id": reviewer_id,
        "qualification_role": "certified_clinical_coder",
        "qualification_reference": f"test-qualification-{reviewer_id}",
        "organization": f"test-organization-{reviewer_id}",
        "independent_of_icoder_engineering_attested": True,
        "blinded_to_engineering_gold_attested": True,
        "model_output_not_viewed_attested": True,
        "conflict_of_interest_absent_attested": True,
        "signed_at": "2026-08-27T12:00:00+00:00",
        "signature_reference": f"test-signature-{reviewer_id}",
        "external_identity_verification_status": "pending_external_verification",
    }
    decisions: list[dict[str, Any]] = []
    for case_id, source in source_cases.items():
        chart_zh = source["chart_zh"]
        chart_en = source["chart_en"]

        def diagnosis_item(item: dict[str, Any]) -> dict[str, str]:
            evidence_zh, evidence_en = EVIDENCE_TERMS[item["code"]]
            return {
                "code": item["code"],
                "evidence_zh": _exact_chart_span(chart_zh, evidence_zh),
                "evidence_en": _exact_chart_span(chart_en, evidence_en),
            }

        principal = diagnosis_item(source["expected_principal_diagnosis"])
        secondary = [
            diagnosis_item(item)
            for item in source["expected_secondary_diagnoses"]
        ]
        procedure = source["expected_primary_procedure"]
        procedure_decision = None
        if procedure:
            evidence_zh, evidence_en = PROCEDURE_EVIDENCE_TERMS[procedure["code"]]
            procedure_decision = {
                "code": procedure["code"],
                "evidence_zh": _exact_chart_span(chart_zh, evidence_zh),
                "evidence_en": _exact_chart_span(chart_en, evidence_en),
            }
        decisions.append(
            {
                "case_id": case_id,
                "principal_diagnosis": principal,
                "secondary_diagnoses": secondary,
                "primary_procedure": procedure_decision,
                "coding_notes": "test-only fixture projection",
            }
        )
    review["decisions"] = decisions
    review["response_sha256"] = canonical_sha256(
        {key: value for key, value in review.items() if key != "response_sha256"}
    )
    return review


def _completed_adjudication(
    packet: dict[str, Any],
    review_a: dict[str, Any],
    review_b: dict[str, Any],
) -> dict[str, Any]:
    adjudication = build_adjudication_template(packet)
    adjudication["review_response_sha256"] = [
        review_a["response_sha256"],
        review_b["response_sha256"],
    ]
    adjudication["adjudication_status"] = "completed"
    adjudication["adjudicator"] = {
        "adjudicator_id": "adjudicator-c",
        "qualification_role": "certified_clinical_coder",
        "qualification_reference": "test-adjudicator-qualification",
        "organization": "test-governance-organization",
        "independent_of_reviewers_attested": True,
        "conflict_of_interest_absent_attested": True,
        "signed_at": "2026-08-27T13:00:00+00:00",
        "signature_reference": "test-adjudicator-signature",
    }
    adjudication["external_identity_verification"] = {
        "status": "verified",
        "reviewer_ids_verified": ["reviewer-a", "reviewer-b"],
        "adjudicator_id_verified": "adjudicator-c",
        "verified_by": "test-clinical-governance-owner",
        "verified_at": "2026-08-27T14:00:00+00:00",
        "evidence_reference": "test-only-identity-evidence",
    }
    adjudication["final_decisions"] = copy.deepcopy(review_a["decisions"])
    adjudication["claim_boundaries"]["independent_gold_ready"] = True
    adjudication["adjudication_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in adjudication.items()
            if key != "adjudication_sha256"
        }
    )
    return adjudication


def test_blind_packet_excludes_engineering_gold_and_is_digest_bound() -> None:
    packet = build_blind_packet(
        generated_at=datetime(2026, 8, 27, tzinfo=timezone.utc)
    )

    assert validate_blind_packet(packet) == []
    assert len(packet["cases"]) == 5
    serialized_cases = json.dumps(packet["cases"], ensure_ascii=False)
    assert "expected_principal_diagnosis" not in serialized_cases
    assert "expected_secondary_diagnoses" not in serialized_cases
    assert "expected_primary_procedure" not in serialized_cases
    assert "evidence_spans" not in serialized_cases
    assert '"notes"' not in serialized_cases
    assert packet["claim_boundaries"]["independent_gold_ready"] is False


def test_blind_packet_rejects_content_tampering() -> None:
    packet = build_blind_packet()
    packet["cases"][0]["chart_zh"] += "篡改"

    errors = validate_blind_packet(packet)

    assert "blind review packet digest mismatch" in errors
    assert "blind case[0] digest mismatch" in errors


def test_pending_template_cannot_be_counted_as_completed_review() -> None:
    packet = build_blind_packet()
    template = build_review_template(packet, reviewer_slot="reviewer_a")

    errors = validate_completed_review(packet, template)

    assert "independent review is not completed" in errors
    assert "reviewer_id is required" in errors
    assert any("code is absent from the governed catalog" in item for item in errors)


def test_completed_review_requires_catalog_codes_and_exact_bilingual_evidence() -> None:
    packet = build_blind_packet()
    review = _completed_review(packet, reviewer_id="reviewer-a")
    assert validate_completed_review(packet, review) == []

    tampered = copy.deepcopy(review)
    tampered["decisions"][0]["principal_diagnosis"]["code"] = "S22.GHOST"
    tampered["decisions"][0]["principal_diagnosis"]["evidence_en"] = (
        "not in the chart"
    )
    tampered["response_sha256"] = canonical_sha256(
        {key: value for key, value in tampered.items() if key != "response_sha256"}
    )

    errors = validate_completed_review(packet, tampered)

    assert any("code is absent from the governed catalog" in item for item in errors)
    assert any("English evidence is not an exact chart span" in item for item in errors)


def test_two_matching_reviews_still_require_external_identity_verification() -> None:
    packet = build_blind_packet()
    review_a = _completed_review(packet, reviewer_id="reviewer-a")
    review_b = _completed_review(packet, reviewer_id="reviewer-b")

    comparison = compare_completed_reviews(packet, review_a, review_b)

    assert comparison["valid"] is True
    assert comparison["agreement_case_count"] == 5
    assert comparison["requires_adjudication"] is False
    assert comparison["independent_gold_ready"] is False
    assert comparison["external_gate"] == "external_identity_verification_required"


def test_disagreement_is_routed_to_adjudication() -> None:
    packet = build_blind_packet()
    review_a = _completed_review(packet, reviewer_id="reviewer-a")
    review_b = _completed_review(packet, reviewer_id="reviewer-b")
    review_b["decisions"][0]["principal_diagnosis"]["code"] = "S22.000x003"
    review_b["response_sha256"] = canonical_sha256(
        {key: value for key, value in review_b.items() if key != "response_sha256"}
    )

    comparison = compare_completed_reviews(packet, review_a, review_b)

    assert comparison["valid"] is True
    assert comparison["agreement_case_count"] == 4
    assert comparison["disagreement_case_ids"] == ["HOBV1-001"]
    assert comparison["requires_adjudication"] is True
    assert comparison["external_gate"] == (
        "adjudication_and_external_identity_verification_required"
    )


def test_same_reviewer_cannot_satisfy_independence() -> None:
    packet = build_blind_packet()
    review_a = _completed_review(packet, reviewer_id="same-reviewer")
    review_b = copy.deepcopy(review_a)

    comparison = compare_completed_reviews(packet, review_a, review_b)

    assert comparison["valid"] is False
    assert "independent reviews must use distinct reviewer IDs" in comparison["errors"]


def test_pending_adjudication_cannot_mark_independent_gold_ready() -> None:
    packet = build_blind_packet()
    review_a = _completed_review(packet, reviewer_id="reviewer-a")
    review_b = _completed_review(packet, reviewer_id="reviewer-b")
    pending = build_adjudication_template(packet)

    errors = validate_completed_adjudication(packet, review_a, review_b, pending)

    assert "gold adjudication is not completed" in errors
    assert "external identity verification is not completed" in errors
    assert "completed adjudication must explicitly mark independent gold ready" in errors


def test_completed_adjudication_is_bound_to_reviews_identity_and_final_codes() -> None:
    packet = build_blind_packet()
    review_a = _completed_review(packet, reviewer_id="reviewer-a")
    review_b = _completed_review(packet, reviewer_id="reviewer-b")
    review_b["decisions"][0]["principal_diagnosis"]["code"] = "S22.000x003"
    review_b["response_sha256"] = canonical_sha256(
        {key: value for key, value in review_b.items() if key != "response_sha256"}
    )
    adjudication = _completed_adjudication(packet, review_a, review_b)

    assert (
        validate_completed_adjudication(packet, review_a, review_b, adjudication)
        == []
    )

    tampered = copy.deepcopy(adjudication)
    tampered["external_identity_verification"]["reviewer_ids_verified"] = [
        "reviewer-a"
    ]
    tampered["final_decisions"][0]["principal_diagnosis"]["code"] = "S22.GHOST"
    tampered["adjudication_sha256"] = canonical_sha256(
        {
            key: value
            for key, value in tampered.items()
            if key != "adjudication_sha256"
        }
    )

    errors = validate_completed_adjudication(packet, review_a, review_b, tampered)

    assert "external identity verification does not cover both reviewers" in errors
    assert any("code is absent from the governed catalog" in item for item in errors)


def test_readiness_bundle_is_explicitly_not_independent_gold(tmp_path: Path) -> None:
    report = write_readiness_bundle(tmp_path)

    assert report["ready_for_external_review"] is True
    assert report["independent_gold_ready"] is False
    assert report["case_count"] == 5
    assert set(report["artifacts"]) == {
        "blind_review_packet.json",
        "reviewer_a_response_template.json",
        "reviewer_b_response_template.json",
        "adjudication_template.json",
    }
    assert all((tmp_path / name).is_file() for name in report["artifacts"])
