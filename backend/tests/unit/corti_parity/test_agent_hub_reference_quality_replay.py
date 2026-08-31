from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

from icoder_runtime.backends.contracts import AgentRunContext, BackendRequest
from icoder_runtime.backends.governed_diagnosis_extractor_provider import (
    GovernedDiagnosisExtractorProvider,
)
from icoder_runtime.backends.governed_discharge_education_provider import (
    GovernedDischargeEducationProvider,
)
from icoder_runtime.backends.governed_evidence_extractor_provider import (
    GovernedEvidenceExtractorProvider,
)
from icoder_runtime.backends.governed_icu_summary_provider import (
    GovernedIcuSummaryProvider,
)
from icoder_runtime.backends.governed_drg_dip_risk_review_provider import (
    GovernedDRGDIPRiskReviewProvider,
)
from icoder_runtime.backends.governed_medication_reconciliation_provider import (
    GovernedMedicationReconciliationProvider,
)
from icoder_runtime.backends.governed_nursing_handoff_provider import (
    GovernedNursingHandoffProvider,
)
from icoder_runtime.backends.governed_procedure_extractor_provider import (
    GovernedProcedureExtractorProvider,
)
from icoder_runtime.backends.governed_rule_explainer_provider import (
    GovernedRuleExplainerProvider,
)
from icoder_runtime.backends.governed_surgical_registry_provider import (
    GovernedSurgicalRegistryProvider,
)
from scripts.corti_parity.sync_agent_pack_example_outputs import _domain_result


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "corti_parity"
    / "run_agent_hub_reference_quality_replay.py"
)
SPEC = importlib.util.spec_from_file_location("reference_quality_replay", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _packs():
    return MODULE._visible_packs(MODULE.DEFAULT_AGENTS_DIR.resolve())


def test_reference_manifest_exactly_covers_visible_agents() -> None:
    packs = _packs()
    document, cases = MODULE.load_reference_cases(MODULE.DEFAULT_CASES, packs)

    assert document["scope"] == (
        "pack_owned_synthetic_reference_semantics_not_independent_clinical_gold"
    )
    assert len(packs) == 26
    assert len(cases) == 26
    assert set(cases) == {MODULE._agent_id(pack) for pack in packs}


def test_reference_manifest_can_be_strictly_scoped_to_selected_local_agents() -> None:
    selected = {
        "code-validation-agent",
        "compliance-guardrail-agent",
        "diagnosis-extractor",
        "discharge-edu",
        "evidence-extractor",
        "evidence-ranker",
        "icd10-navigator",
        "icu-summary",
        "med-reconciliation",
        "note-completeness-agent",
        "nursing-handoff",
        "procedure-extractor",
        "rule-explainer",
        "surgical-registry",
    }
    packs = [pack for pack in _packs() if MODULE._agent_id(pack) in selected]
    _document, cases = MODULE.load_reference_cases(
        MODULE.DEFAULT_CASES,
        packs,
        allow_case_superset=True,
    )

    assert len(packs) == 14
    assert set(cases) == selected


def test_every_pack_reference_satisfies_its_semantic_assertions() -> None:
    packs = _packs()
    _document, cases = MODULE.load_reference_cases(MODULE.DEFAULT_CASES, packs)

    failures: dict[str, list[str]] = {}
    for pack in packs:
        agent_id = MODULE._agent_id(pack)
        case = cases[agent_id]
        reference = pack["example_outputs"][case["example_index"]]
        evaluation = MODULE.evaluate_reference_output(reference, case)
        if not evaluation["assertions_passed"]:
            failures[agent_id] = [
                item["path"]
                for item in evaluation["assertions"]
                if not item["passed"]
            ]

    assert failures == {}


def test_semantic_mutation_fails_without_copying_actual_content() -> None:
    packs = {MODULE._agent_id(pack): pack for pack in _packs()}
    _document, cases = MODULE.load_reference_cases(
        MODULE.DEFAULT_CASES, list(packs.values())
    )
    reference = copy.deepcopy(packs["triage"]["example_outputs"][0])
    reference["acuity_level"] = "Ⅳ级"

    evaluation = MODULE.evaluate_reference_output(
        reference, cases["triage"]
    )

    assert evaluation["assertions_passed"] is False
    failed = [item for item in evaluation["assertions"] if not item["passed"]]
    assert any(item["path"] == "acuity_level" for item in failed)
    assert all("actual" not in item for item in evaluation["assertions"])
    assert all(
        item["actual_sha256"] is not None
        for item in evaluation["assertions"]
        if item["exists"]
    )


def test_source_report_must_be_complete_successful_and_match_visible_agents(
    tmp_path: Path,
) -> None:
    expected_agent_ids = {MODULE._agent_id(pack) for pack in _packs()}
    rows = [
        {"agent_id": agent_id, "evaluation": {"passed": True}}
        for agent_id in sorted(expected_agent_ids)
    ]
    report_path = tmp_path / "source.json"
    report_path.write_text(
        json.dumps({
            "schema_version": "icoder.agent-hub-examples-e2e/v1",
            "generated_at": "2026-08-22T00:00:00+00:00",
            "total": 26,
            "passed": 26,
            "failed": 0,
            "rows": rows,
        }),
        encoding="utf-8",
    )

    loaded = MODULE._load_source_report(
        report_path,
        expected_agent_ids=expected_agent_ids,
    )
    assert loaded is not None
    assert loaded["passed"] == 26

    failed_report = json.loads(report_path.read_text(encoding="utf-8"))
    failed_report["passed"] = 25
    failed_report["failed"] = 1
    failed_report["rows"][0]["evaluation"]["passed"] = False
    report_path.write_text(json.dumps(failed_report), encoding="utf-8")

    with pytest.raises(ValueError, match="26/26 successful"):
        MODULE._load_source_report(
            report_path,
            expected_agent_ids=expected_agent_ids,
        )


def test_source_report_accepts_a_complete_fourteen_agent_scope(tmp_path: Path) -> None:
    expected_agent_ids = {
        "code-validation-agent",
        "compliance-guardrail-agent",
        "diagnosis-extractor",
        "discharge-edu",
        "evidence-extractor",
        "evidence-ranker",
        "icd10-navigator",
        "icu-summary",
        "med-reconciliation",
        "note-completeness-agent",
        "nursing-handoff",
        "procedure-extractor",
        "rule-explainer",
        "surgical-registry",
    }
    report_path = tmp_path / "source.json"
    report_path.write_text(
        json.dumps({
            "schema_version": "icoder.agent-hub-examples-e2e/v3",
            "generated_at": "2026-08-24T00:00:00+00:00",
            "total": 14,
            "passed": 14,
            "failed": 0,
            "rows": [
                {"agent_id": agent_id, "evaluation": {"passed": True}}
                for agent_id in sorted(expected_agent_ids)
            ],
        }),
        encoding="utf-8",
    )

    loaded = MODULE._load_source_report(
        report_path,
        expected_agent_ids=expected_agent_ids,
    )
    assert loaded is not None
    assert loaded["passed"] == 14


@pytest.mark.parametrize("agent_id", ["drg-analyzer"])
def test_current_runtime_rejects_legacy_drg_response_as_current_governed_evidence(
    agent_id: str,
) -> None:
    """Re-run current normalization over the immutable 2026-08-15 response.

    This is regression evidence, not a fresh live-model claim.  The original
    response must still demonstrate the historical semantic miss.  Projection
    must not manufacture the explicit coded-case inputs, rule provenance, or
    development-only authority required by the governed contract.
    """

    packs = {MODULE._agent_id(pack): pack for pack in _packs()}
    _document, cases = MODULE.load_reference_cases(
        MODULE.DEFAULT_CASES, list(packs.values())
    )
    response_path = (
        MODULE.REPO_ROOT
        / "reports"
        / "agent_hub"
        / "examples_e2e_20260815_china_coding_chain"
        / "responses"
        / f"{agent_id}.json"
    )
    response = json.loads(response_path.read_text(encoding="utf-8"))
    historical = response.get("result") or {}

    assert MODULE.evaluate_reference_output(
        historical, cases[agent_id]
    )["assertions_passed"] is False

    current = _domain_result(response, packs[agent_id])
    assert MODULE.evaluate_reference_output(
        current, cases[agent_id]
    )["assertions_passed"] is False


@pytest.mark.asyncio
async def test_current_governed_drg_provider_closes_known_historical_real_gap() -> None:
    """The current offline provider, not legacy projection, passes the DRG case."""

    agent_id = "drg-analyzer"
    packs = {MODULE._agent_id(pack): pack for pack in _packs()}
    _document, cases = MODULE.load_reference_cases(
        MODULE.DEFAULT_CASES, list(packs.values())
    )
    pack = packs[agent_id]
    example = pack["example_inputs"][0]
    text = str(example.get("input_text") or example.get("text") or "")
    response = await GovernedDRGDIPRiskReviewProvider().invoke(
        BackendRequest(input={"text": text}),
        AgentRunContext(
            run_id="run-drg-analyzer-historical-gap-regression",
            context_id="context-drg-analyzer-historical-gap-regression",
            agent_id=agent_id,
            redacted_input=text,
            agent_pack=pack,
        ),
    )
    result = json.loads(response.markdown)

    assert response.cost_usd == 0.0
    assert response.finish_state == "completed"
    assert MODULE.evaluate_reference_output(
        result, cases[agent_id]
    )["assertions_passed"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_id", "provider"),
    [
        ("diagnosis-extractor", GovernedDiagnosisExtractorProvider()),
        ("discharge-edu", GovernedDischargeEducationProvider()),
        ("evidence-extractor", GovernedEvidenceExtractorProvider()),
        ("icu-summary", GovernedIcuSummaryProvider()),
        ("med-reconciliation", GovernedMedicationReconciliationProvider()),
        ("nursing-handoff", GovernedNursingHandoffProvider()),
        ("procedure-extractor", GovernedProcedureExtractorProvider()),
        ("rule-explainer", GovernedRuleExplainerProvider()),
        ("surgical-registry", GovernedSurgicalRegistryProvider()),
    ],
)
async def test_current_governed_local_provider_closes_known_historical_real_gap(
    agent_id: str,
    provider,
) -> None:
    """Known historical misses now pass through current offline providers."""

    packs = {MODULE._agent_id(pack): pack for pack in _packs()}
    _document, cases = MODULE.load_reference_cases(
        MODULE.DEFAULT_CASES, list(packs.values())
    )
    pack = packs[agent_id]
    example = pack["example_inputs"][0]
    text = str(example.get("input_text") or example.get("text") or "")
    response = await provider.invoke(
        BackendRequest(input={"text": text}),
        AgentRunContext(
            run_id=f"run-{agent_id}-historical-gap-regression",
            context_id=f"context-{agent_id}-historical-gap-regression",
            agent_id=agent_id,
            redacted_input=text,
            agent_pack=pack,
        ),
    )
    result = json.loads(response.markdown)

    assert response.cost_usd == 0.0
    assert response.finish_state == "completed"
    assert MODULE.evaluate_reference_output(
        result, cases[agent_id]
    )["assertions_passed"] is True
