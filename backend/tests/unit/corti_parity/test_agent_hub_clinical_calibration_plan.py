from __future__ import annotations

import copy
from datetime import datetime, timezone

from scripts.corti_parity.build_agent_hub_clinical_calibration_plan import (
    build_plan,
    validate_plan,
)


def test_current_clinical_calibration_assets_are_truthfully_scoped() -> None:
    plan = build_plan(generated_at=datetime(2026, 8, 25, tzinfo=timezone.utc))

    assert plan["valid"] is True
    assert validate_plan(plan) == []
    run = plan["controlled_external_model_run"]
    assert run["total_agent_invocations"] == 50
    assert [suite["case_count"] for suite in run["suites"]] == [40, 10]
    assert plan["legacy_cdi_candidate"]["status"] == (
        "historical_calibration_only_not_current_release_evidence"
    )
    assert len(plan["legacy_cdi_candidate"]["runner_findings"]) == 4
    assert all(
        item["external_provider_egress_allowed"] is False
        for item in plan["assets"]["external_calibration_blocked"]
    )
    review = plan["independent_bilingual_coding_gold_review"]
    assert review["ready_for_blinded_external_review"] is True
    assert review["minimum_independent_reviewers"] == 2
    assert review["engineering_gold_removed_from_review_packet"] is True
    assert review["model_outputs_removed_from_review_packet"] is True
    assert review["completed_independent_reviews"] == 0
    assert review["external_identity_verification_completed"] is False
    assert review["independent_gold_ready"] is False
    assert all(value is False for key, value in plan["claim_boundaries"].items() if key.endswith("_proven"))


def test_plan_rejects_overstated_clinical_claim() -> None:
    plan = build_plan(generated_at=datetime(2026, 8, 25, tzinfo=timezone.utc))
    tampered = copy.deepcopy(plan)
    tampered["claim_boundaries"]["clinical_accuracy_proven"] = True

    errors = validate_plan(tampered)

    assert "claim boundary must remain false: clinical_accuracy_proven" in errors
    assert "canonical plan digest mismatch" in errors


def test_plan_rejects_ccl_external_egress() -> None:
    plan = build_plan(generated_at=datetime(2026, 8, 25, tzinfo=timezone.utc))
    tampered = copy.deepcopy(plan)
    tampered["assets"]["external_calibration_blocked"][0][
        "external_provider_egress_allowed"
    ] = True

    errors = validate_plan(tampered)

    assert "all three CCL-derived assets must remain external-egress blocked" in errors


def test_plan_rejects_false_independent_gold_completion_claim() -> None:
    plan = build_plan(generated_at=datetime(2026, 8, 25, tzinfo=timezone.utc))
    tampered = copy.deepcopy(plan)
    tampered["independent_bilingual_coding_gold_review"][
        "independent_gold_ready"
    ] = True

    errors = validate_plan(tampered)

    assert "independent bilingual coding gold review boundary is invalid" in errors
    assert "canonical plan digest mismatch" in errors
