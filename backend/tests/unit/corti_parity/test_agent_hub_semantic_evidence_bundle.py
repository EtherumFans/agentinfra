from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import pytest

from scripts.corti_parity.agent_hub_live_evidence import (
    execution_provenance,
    extract_trace_evidence,
    result_attestation_evidence,
    row_execution_evidence,
    sha256_file,
)
from scripts.corti_parity.build_agent_hub_runtime_matrix import build_matrix
from scripts.corti_parity.build_agent_hub_semantic_evidence_bundle import (
    DEFAULT_REFERENCE_CASES,
    _raw_visible_packs,
    _snapshot_from_agents_dir,
    build_bundle,
    validate_bundle_file,
)
from scripts.corti_parity.build_agent_hub_local_semantic_evidence_bundle import (
    EXPECTED_LOCAL_AGENT_COUNT,
    _local_agent_ids,
    build_local_bundle,
    validate_local_bundle_file,
)
from scripts.corti_parity.build_agent_hub_external_semantic_evidence_bundle import (
    EXPECTED_EXTERNAL_AGENT_COUNT,
    _external_agent_ids,
    build_external_bundle,
    validate_external_bundle_file,
)
from scripts.corti_parity.build_agent_hub_composite_semantic_evidence_bundle import (
    build_composite_bundle,
    validate_composite_bundle_file,
)
from app.config import settings
from app.services.result_attestation import issue_result_attestation
from app.services.trace_attestation import issue_trace_attestation


BACKEND_ROOT = Path(__file__).resolve().parents[3]
AGENTS_DIR = BACKEND_ROOT / "official_agents"


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _attestation(result: dict[str, Any], *, run_id: str, agent_id: str, schema_ref: str, now: datetime) -> str:
    del now
    return issue_result_attestation(
        run_id=run_id,
        agent_id=agent_id,
        schema_ref=schema_ref,
        organization_id="org-test",
        result=result,
        ttl_seconds=2 * 60 * 60,
    )


def _make_execution_row(
    root: Path,
    *,
    label: str,
    suffix: str,
    pack: dict[str, Any],
    external: bool,
    now: datetime,
    case_kind: str | None = None,
    repetition: int | None = None,
) -> dict[str, Any]:
    agent_id = str(pack["agent_ref"]).rsplit("/", 1)[-1].split("@", 1)[0]
    schema_ref = str(pack["output_contract"]["schema_ref"])
    run_id = f"run-{label}-{agent_id}-{suffix}"
    trace_id = f"trace-{label}-{agent_id}-{suffix}"
    result: dict[str, Any] = {}
    response = {
        "agent_id": agent_id,
        "run_id": run_id,
        "trace_id": trace_id,
        "schema_ref": schema_ref,
        "result": result,
        "result_attestation": _attestation(
            result,
            run_id=run_id,
            agent_id=agent_id,
            schema_ref=schema_ref,
            now=now,
        ),
        "error": False,
        "_http_status": 200,
    }
    response_path = root / label / "responses" / f"{agent_id}-{suffix}.json"
    _write(response_path, response)
    metadata: dict[str, Any] = {
        "backend_provider": str(pack.get("backend_provider") or "dedicated.runtime"),
        "backend_type": "llm_with_tools" if external else "rule_engine",
        "finish_state": "completed",
    }
    if external:
        metadata.update({"model_provider": "deepseek", "model_name": "deepseek-chat"})
    trace = {
        "run_id": run_id,
        "events": [{"step": "provider.completed", "safe_metadata": metadata}],
        "_http_status": 200,
    }
    trace["trace_attestation"] = issue_trace_attestation(
        run_id=run_id,
        organization_id="org-test",
        events=trace["events"],
        ttl_seconds=2 * 60 * 60,
    )
    trace_path = root / label / "traces" / f"{agent_id}-{suffix}.json"
    _write(trace_path, trace)
    trace_evidence = extract_trace_evidence(trace, run_id=run_id)
    trace_evidence.update({
        "artifact_path": str(trace_path.resolve()),
        "artifact_sha256": sha256_file(trace_path),
    })
    row: dict[str, Any] = {
        "agent_id": agent_id,
        "http_status": 200,
        "elapsed_seconds": 0.1,
        "evaluation": {"passed": True},
        "response_path": str(response_path.resolve()),
        "execution_evidence": row_execution_evidence(
            action="run",
            response=response,
            response_path=response_path,
            pack=pack,
            trace_evidence=trace_evidence,
            started_at=now.isoformat(),
            completed_at=now.isoformat(),
        ),
    }
    if case_kind is not None:
        row["case_kind"] = case_kind
    if repetition is not None:
        row["repetition"] = repetition
    return row


def _fixture_reports(
    root: Path,
    now: datetime,
    *,
    selected_agent_ids: set[str] | None = None,
) -> dict[str, Path]:
    matrix = build_matrix(AGENTS_DIR)
    external = {
        str(row["agent_id"])
        for row in matrix["rows"]
        if row["hub_visible"] and row["external_llm_dependent"]
    }
    packs = _raw_visible_packs(AGENTS_DIR)
    if selected_agent_ids is not None:
        packs = [
            pack
            for pack in packs
            if str(pack["agent_ref"]).rsplit("/", 1)[-1].split("@", 1)[0]
            in selected_agent_ids
        ]
    full_snapshot = _snapshot_from_agents_dir(AGENTS_DIR)
    snapshot = {
        agent_id: full_snapshot[agent_id]
        for agent_id in sorted(
            selected_agent_ids if selected_agent_ids is not None else full_snapshot
        )
    }
    expected_count = len(snapshot)
    example_rows = [
        _make_execution_row(
            root,
            label="examples",
            suffix="happy",
            pack=pack,
            external=str(pack["agent_ref"]).rsplit("/", 1)[-1].split("@", 1)[0] in external,
            now=now,
        )
        for pack in packs
    ]
    examples = {
        "schema_version": "icoder.agent-hub-examples-e2e/v3",
        "generated_at": now.isoformat(),
        "total": expected_count,
        "passed": expected_count,
        "capability_passed": expected_count,
        "safe_fail_closed": 0,
        "safety_passed": expected_count,
        "unsafe_or_invalid": 0,
        "failed": 0,
        "execution_provenance": execution_provenance(
            example_rows, base_url="http://127.0.0.1:8000", session_started_at=now.isoformat()
        ),
        "agent_snapshot": snapshot,
        "rows": example_rows,
    }
    examples_path = root / "examples" / "agent_hub_examples_e2e.json"
    _write(examples_path, examples)

    adversarial_rows = [
        _make_execution_row(
            root,
            label="adversarial",
            suffix="adversarial",
            pack=pack,
            external=str(pack["agent_ref"]).rsplit("/", 1)[-1].split("@", 1)[0] in external,
            now=now,
        )
        for pack in packs
    ]
    adversarial = {
        "schema_version": "icoder.agent-hub-adversarial-e2e/v3",
        "generated_at": now.isoformat(),
        "expected": expected_count,
        "completed": expected_count,
        "passed": expected_count,
        "semantic_capability_passed": expected_count,
        "safe_fail_closed": 0,
        "safety_passed": expected_count,
        "unsafe_or_invalid": 0,
        "failed": 0,
        "complete": True,
        "execution_provenance": execution_provenance(
            adversarial_rows, base_url="http://127.0.0.1:8000", session_started_at=now.isoformat()
        ),
        "agent_snapshot": snapshot,
        "rows": adversarial_rows,
    }
    adversarial_path = root / "adversarial" / "agent_hub_adversarial_e2e.json"
    _write(adversarial_path, adversarial)

    repetitions = 2
    stability_rows: list[dict[str, Any]] = []
    for pack in packs:
        agent_id = str(pack["agent_ref"]).rsplit("/", 1)[-1].split("@", 1)[0]
        for case_kind in ("happy", "adversarial"):
            for repetition in range(1, repetitions + 1):
                stability_rows.append(
                    _make_execution_row(
                        root,
                        label="stability",
                        suffix=f"{case_kind}-{repetition}",
                        pack=pack,
                        external=agent_id in external,
                        now=now,
                        case_kind=case_kind,
                        repetition=repetition,
                    )
                )
    stability = {
        "schema_version": "icoder.agent-hub-stability-benchmark/v2",
        "quality_scope": "contract_safety_reliability_not_clinical_accuracy",
        "generated_at": now.isoformat(),
        "repetitions": repetitions,
        "expected": len(stability_rows),
        "completed": len(stability_rows),
        "complete": True,
        "passed": len(stability_rows),
        "failed": 0,
        "gates": {"complete": True, "pass_rate": True, "latency": True, "all_passed": True},
        "execution_provenance": execution_provenance(
            stability_rows, base_url="http://127.0.0.1:8000", session_started_at=now.isoformat()
        ),
        "agent_snapshot": snapshot,
        "per_agent": [
            {"agent_id": agent_id, "all_scenarios_repeatably_passed": True}
            for agent_id in sorted(snapshot)
        ],
        "rows": stability_rows,
    }
    stability_path = root / "stability" / "agent_hub_stability_benchmark.json"
    _write(stability_path, stability)

    response_hashes = {
        str(row["agent_id"]): str(row["execution_evidence"]["response_sha256"])
        for row in example_rows
    }
    reference_rows = [
        {
            "agent_id": agent_id,
            "base_contract_safety_passed": True,
            "reference_assertions_passed": True,
            "passed": True,
            "safe_fail_closed": False,
            "response_sha256": response_hashes[agent_id],
        }
        for agent_id in sorted(snapshot)
    ]
    reference = {
        "schema_version": "icoder.agent-hub-reference-quality-replay/v1",
        "quality_scope": "pack_owned_synthetic_reference_semantics_not_independent_clinical_gold",
        "generated_at": now.isoformat(),
        "network_used": False,
        "credential_used": False,
        "cases_sha256": sha256_file(DEFAULT_REFERENCE_CASES),
        "source_report": {"sha256": sha256_file(examples_path)},
        "expected": expected_count,
        "completed": expected_count,
        "passed": expected_count,
        "failed": 0,
        "safe_fail_closed": 0,
        "all_passed": True,
        "rows": reference_rows,
    }
    reference_path = root / "reference" / "agent_hub_reference_quality_replay.json"
    _write(reference_path, reference)
    return {
        "examples": examples_path,
        "adversarial": adversarial_path,
        "reference": reference_path,
        "stability": stability_path,
    }


@pytest.fixture()
def valid_sources(tmp_path: Path) -> tuple[dict[str, Path], datetime]:
    now = datetime.now(timezone.utc)
    return _fixture_reports(tmp_path, now), now


@pytest.fixture(autouse=True)
def fixed_result_attestation_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings,
        "SECRET_KEY",
        "semantic-evidence-pytest-only-key-20260823-not-production",
    )


def _build(paths: dict[str, Path], now: datetime) -> dict[str, Any]:
    return build_bundle(
        examples_path=paths["examples"],
        adversarial_path=paths["adversarial"],
        reference_path=paths["reference"],
        stability_path=paths["stability"],
        agents_dir=AGENTS_DIR,
        now=now,
    )


def test_valid_fresh_non_mock_bundle_is_the_only_path_to_26_live_semantic(
    valid_sources: tuple[dict[str, Path], datetime], tmp_path: Path
) -> None:
    paths, now = valid_sources
    bundle = _build(paths, now)
    assert bundle["valid"] is True
    assert bundle["errors"] == []
    assert bundle["summary"]["semantic_live_e2e_verified"] == 26

    bundle_path = tmp_path / "bundle.json"
    _write(bundle_path, bundle)
    validation = validate_bundle_file(
        bundle_path, agents_dir=AGENTS_DIR, now=now
    )
    assert validation["valid"] is True
    matrix = build_matrix(
        AGENTS_DIR,
        semantic_evidence_path=bundle_path,
        semantic_max_age_hours=24,
        semantic_now=now,
    )
    assert matrix["semantic_evidence"]["valid"] is True
    assert matrix["summary"]["visible_semantic_live_e2e_verified"] == 26
    assert matrix["summary"]["visible_semantic_live_e2e_pending"] == []
    assert matrix["summary"]["visible_local_semantic_e2e_verified"] == 23
    assert matrix["summary"]["visible_local_semantic_e2e_pending"] == [
        "code-validation-agent"
    ]
    assert matrix["local_semantic_evidence"][
        "derived_from_semantic_evidence"
    ] is True
    assert matrix["local_semantic_evidence"]["derived_scope"] == (
        "structural_local_deterministic_subset_only"
    )
    visible = {row["agent_id"]: row for row in matrix["rows"] if row["hub_visible"]}
    assert visible["claim-check"]["local_semantic_e2e_verified"] is True
    assert visible["code-validation-agent"]["local_semantic_e2e_verified"] is False
    assert visible["clinical-documentation-improvement-agent"][
        "local_semantic_e2e_verified"
    ] is False


def _mutate_resume(report: dict[str, Any]) -> None:
    report["rows"][0]["execution_evidence"]["artifact_source"] = "resume"


def _mutate_partial(report: dict[str, Any]) -> None:
    report["rows"].pop()
    report["total"] = 25
    report["passed"] = 25
    report["capability_passed"] = 25


def _mutate_pack(report: dict[str, Any]) -> None:
    agent_id = sorted(report["agent_snapshot"])[0]
    report["agent_snapshot"][agent_id]["pack_sha256"] = "0" * 64


def _mutate_safe_fail(report: dict[str, Any]) -> None:
    report["passed"] = 25
    report["capability_passed"] = 25
    report["safe_fail_closed"] = 1


@pytest.mark.parametrize(
    "mutator,expected",
    [
        (_mutate_resume, "artifact_source"),
        (_mutate_partial, "exactly once"),
        (_mutate_pack, "snapshot"),
        (_mutate_safe_fail, "safe-fail"),
    ],
)
def test_resume_partial_pack_mismatch_and_safe_fail_cannot_inflate_live_count(
    valid_sources: tuple[dict[str, Path], datetime],
    mutator: Callable[[dict[str, Any]], None],
    expected: str,
) -> None:
    paths, now = valid_sources
    report = json.loads(paths["examples"].read_text(encoding="utf-8"))
    mutator(report)
    _write(paths["examples"], report)
    bundle = _build(paths, now)
    assert bundle["valid"] is False
    assert bundle["summary"]["semantic_live_e2e_verified"] == 0
    assert expected.casefold() in " ".join(bundle["errors"]).casefold()


def test_mock_trace_telemetry_cannot_inflate_live_count(
    valid_sources: tuple[dict[str, Path], datetime]
) -> None:
    paths, now = valid_sources
    report = json.loads(paths["examples"].read_text(encoding="utf-8"))
    row = next(
        item
        for item in report["rows"]
        if item["execution_evidence"]["trace"]["model_call_observed"]
    )
    trace_path = Path(row["execution_evidence"]["trace"]["artifact_path"])
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    trace["events"][0]["safe_metadata"]["model_provider"] = "mock"
    trace["events"][0]["safe_metadata"]["model_name"] = "mock-model"
    _write(trace_path, trace)
    actual = extract_trace_evidence(trace, run_id=str(trace["run_id"]))
    actual.update({"artifact_path": str(trace_path), "artifact_sha256": sha256_file(trace_path)})
    row["execution_evidence"]["trace"] = actual
    _write(paths["examples"], report)
    bundle = _build(paths, now)
    assert bundle["valid"] is False
    assert bundle["summary"]["semantic_live_e2e_verified"] == 0
    assert any("mock/test" in error for error in bundle["errors"])


def test_forged_result_attestation_signature_cannot_inflate_live_count(
    valid_sources: tuple[dict[str, Path], datetime]
) -> None:
    paths, now = valid_sources
    examples = json.loads(paths["examples"].read_text(encoding="utf-8"))
    row = examples["rows"][0]
    response_path = Path(row["response_path"])
    response = json.loads(response_path.read_text(encoding="utf-8"))
    payload, _signature = str(response["result_attestation"]).split(".", 1)
    response["result_attestation"] = f"{payload}.forged-signature"
    _write(response_path, response)
    agent_id = str(row["agent_id"])
    schema_ref = str(row["execution_evidence"]["output_schema_ref"])
    row["execution_evidence"]["response_sha256"] = sha256_file(response_path)
    row["execution_evidence"]["result_attestation"] = result_attestation_evidence(
        response,
        agent_id=agent_id,
        output_schema_ref=schema_ref,
    )
    _write(paths["examples"], examples)
    reference = json.loads(paths["reference"].read_text(encoding="utf-8"))
    reference_row = next(item for item in reference["rows"] if item["agent_id"] == agent_id)
    reference_row["response_sha256"] = sha256_file(response_path)
    reference["source_report"]["sha256"] = sha256_file(paths["examples"])
    _write(paths["reference"], reference)
    bundle = _build(paths, now)
    assert bundle["valid"] is False
    assert bundle["summary"]["semantic_live_e2e_verified"] == 0
    assert any("invalid signature" in error for error in bundle["errors"])


def test_stability_seed_is_accepted_only_when_bound_to_fresh_source_runs(
    valid_sources: tuple[dict[str, Path], datetime]
) -> None:
    paths, now = valid_sources
    examples = json.loads(paths["examples"].read_text(encoding="utf-8"))
    adversarial = json.loads(paths["adversarial"].read_text(encoding="utf-8"))
    stability = json.loads(paths["stability"].read_text(encoding="utf-8"))
    source_rows = {
        (str(row["agent_id"]), "happy"): row for row in examples["rows"]
    }
    source_rows.update({
        (str(row["agent_id"]), "adversarial"): row
        for row in adversarial["rows"]
    })
    for row in stability["rows"]:
        if row["repetition"] != 1:
            continue
        source = source_rows[(str(row["agent_id"]), str(row["case_kind"]))]
        source_path = Path(source["response_path"])
        target_path = Path(row["response_path"])
        target_path.write_bytes(source_path.read_bytes())
        row["execution_evidence"]["artifact_source"] = "seed"
        row["execution_evidence"]["response_sha256"] = sha256_file(target_path)
        row["execution_evidence"]["result_attestation"] = copy.deepcopy(
            source["execution_evidence"]["result_attestation"]
        )
    stability["execution_provenance"] = execution_provenance(
        stability["rows"],
        base_url="http://127.0.0.1:8000",
        session_started_at=now.isoformat(),
    )
    stability["seed_sources"] = {
        "happy": {
            "report_path": str(paths["examples"].resolve()),
            "report_sha256": sha256_file(paths["examples"]),
        },
        "adversarial": {
            "report_path": str(paths["adversarial"].resolve()),
            "report_sha256": sha256_file(paths["adversarial"]),
        },
    }
    _write(paths["stability"], stability)
    bundle = _build(paths, now)
    assert bundle["valid"] is True
    assert bundle["summary"]["semantic_live_e2e_verified"] == 26

    stability["seed_sources"]["happy"]["report_sha256"] = "0" * 64
    _write(paths["stability"], stability)
    rejected = _build(paths, now)
    assert rejected["valid"] is False
    assert any("seed source report digests" in error for error in rejected["errors"])


def test_stale_reports_cannot_inflate_live_count(
    valid_sources: tuple[dict[str, Path], datetime]
) -> None:
    paths, now = valid_sources
    report = json.loads(paths["adversarial"].read_text(encoding="utf-8"))
    report["generated_at"] = (now - timedelta(hours=25)).isoformat()
    _write(paths["adversarial"], report)
    bundle = _build(paths, now)
    assert bundle["valid"] is False
    assert bundle["summary"]["semantic_live_e2e_verified"] == 0
    assert "stale" in " ".join(bundle["errors"])


def test_tampered_bundle_or_source_is_rejected_at_matrix_ingestion(
    valid_sources: tuple[dict[str, Path], datetime], tmp_path: Path
) -> None:
    paths, now = valid_sources
    bundle = _build(paths, now)
    bundle_path = tmp_path / "bundle.json"
    tampered = copy.deepcopy(bundle)
    tampered["agent_results"][0]["semantic_live_e2e_verified"] = False
    _write(bundle_path, tampered)
    invalid = validate_bundle_file(bundle_path, agents_dir=AGENTS_DIR, now=now)
    assert invalid["valid"] is False
    assert invalid["verified_agent_ids"] == []
    assert any("digest mismatch" in error for error in invalid["errors"])
    invalid_matrix = build_matrix(
        AGENTS_DIR,
        semantic_evidence_path=bundle_path,
        semantic_now=now,
    )
    assert invalid_matrix["summary"]["visible_local_semantic_e2e_verified"] == 0
    assert invalid_matrix["local_semantic_evidence"][
        "derived_from_semantic_evidence"
    ] is False

    _write(bundle_path, bundle)
    examples = json.loads(paths["examples"].read_text(encoding="utf-8"))
    examples["passed"] = 25
    _write(paths["examples"], examples)
    invalid_source = validate_bundle_file(bundle_path, agents_dir=AGENTS_DIR, now=now)
    assert invalid_source["valid"] is False
    assert invalid_source["verified_agent_ids"] == []
    assert any("source artifact digest mismatch" in error for error in invalid_source["errors"])


def test_local_semantic_bundle_is_strictly_scoped_and_cannot_inflate_full_gate(
    tmp_path: Path,
) -> None:
    now = datetime.now(timezone.utc)
    local_ids = _local_agent_ids(AGENTS_DIR)
    assert local_ids == [
        "claim-check",
        "clinical-education",
        "clinical-guidelines",
        "code-validation-agent",
        "compliance-guardrail-agent",
        "denial-appeals",
        "diagnosis-extractor",
        "discharge-edu",
        "discharge-summary-structuring",
        "drg-analyzer",
        "evidence-extractor",
        "evidence-ranker",
        "icd10-navigator",
        "icu-summary",
        "med-reconciliation",
        "note-completeness-agent",
        "nursing-handoff",
        "principal-diagnosis-review",
        "prior-auth",
        "procedure-extractor",
        "referral-gen",
        "rule-explainer",
        "surgical-registry",
        "triage",
    ]
    assert len(local_ids) == EXPECTED_LOCAL_AGENT_COUNT
    paths = _fixture_reports(
        tmp_path / "sources",
        now,
        selected_agent_ids=set(local_ids),
    )
    bundle = build_local_bundle(
        examples_path=paths["examples"],
        adversarial_path=paths["adversarial"],
        reference_path=paths["reference"],
        stability_path=paths["stability"],
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert bundle["valid"] is True
    assert bundle["errors"] == []
    assert bundle["summary"] == {
        "visible_agents": 26,
        "local_agents_expected": 24,
        "local_semantic_e2e_verified": 24,
        "external_model_agents_not_evaluated": 2,
    }
    assert any(
        limitation.startswith("2 external-model-dependent Agents")
        for limitation in bundle["limitations"]
    )

    bundle_path = tmp_path / "bundle" / "agent_hub_local_semantic_evidence_bundle.json"
    _write(bundle_path, bundle)
    validation = validate_local_bundle_file(
        bundle_path,
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert validation["valid"] is True
    assert validation["verified_agent_ids"] == local_ids

    matrix = build_matrix(
        AGENTS_DIR,
        local_semantic_evidence_path=bundle_path,
        semantic_now=now,
    )
    assert matrix["local_semantic_evidence"]["valid"] is True
    assert matrix["summary"]["visible_local_semantic_e2e_verified"] == 24
    assert matrix["summary"]["visible_local_semantic_e2e_pending"] == []
    assert matrix["summary"]["visible_semantic_live_e2e_verified"] == 0
    assert len(matrix["summary"]["visible_semantic_live_e2e_pending"]) == 26
    assert len(matrix["summary"]["visible_external_semantic_live_e2e_pending"]) == 2
    visible = [row for row in matrix["rows"] if row["hub_visible"]]
    assert {
        row["agent_id"]
        for row in visible
        if row["local_semantic_e2e_verified"]
    } == set(local_ids)
    assert all(row["semantic_live_e2e_verified"] is False for row in visible)


def test_tampered_local_bundle_cannot_verify_any_agent(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    local_ids = _local_agent_ids(AGENTS_DIR)
    paths = _fixture_reports(
        tmp_path / "sources",
        now,
        selected_agent_ids=set(local_ids),
    )
    bundle = build_local_bundle(
        examples_path=paths["examples"],
        adversarial_path=paths["adversarial"],
        reference_path=paths["reference"],
        stability_path=paths["stability"],
        agents_dir=AGENTS_DIR,
        now=now,
    )
    bundle["summary"]["local_semantic_e2e_verified"] = 26
    bundle_path = tmp_path / "bundle.json"
    _write(bundle_path, bundle)

    validation = validate_local_bundle_file(
        bundle_path,
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert validation["valid"] is False
    assert validation["verified_agent_ids"] == []
    assert any("canonical digest mismatch" in item for item in validation["errors"])


def test_external_semantic_bundle_requires_both_real_model_agents(
    tmp_path: Path,
) -> None:
    now = datetime.now(timezone.utc)
    external_ids = _external_agent_ids(AGENTS_DIR)
    assert external_ids == [
        "clinical-documentation-improvement-agent",
        "medical-coding-agent",
    ]
    assert len(external_ids) == EXPECTED_EXTERNAL_AGENT_COUNT
    paths = _fixture_reports(
        tmp_path / "sources",
        now,
        selected_agent_ids=set(external_ids),
    )
    bundle = build_external_bundle(
        examples_path=paths["examples"],
        adversarial_path=paths["adversarial"],
        reference_path=paths["reference"],
        stability_path=paths["stability"],
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert bundle["valid"] is True
    assert bundle["errors"] == []
    assert bundle["summary"] == {
        "visible_agents": 26,
        "external_agents_expected": 2,
        "external_semantic_live_e2e_verified": 2,
        "local_agents_not_evaluated": 24,
    }

    bundle_path = tmp_path / "bundle" / "agent_hub_external_semantic_evidence_bundle.json"
    _write(bundle_path, bundle)
    validation = validate_external_bundle_file(
        bundle_path,
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert validation["valid"] is True
    assert validation["verified_agent_ids"] == external_ids


def test_external_bundle_rejects_absent_model_call_telemetry(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    external_ids = _external_agent_ids(AGENTS_DIR)
    paths = _fixture_reports(
        tmp_path / "sources",
        now,
        selected_agent_ids=set(external_ids),
    )
    report = json.loads(paths["examples"].read_text(encoding="utf-8"))
    row = report["rows"][0]
    trace_path = Path(row["execution_evidence"]["trace"]["artifact_path"])
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    for event in trace["events"]:
        safe_metadata = event.get("safe_metadata") or {}
        safe_metadata.pop("model_provider", None)
        safe_metadata.pop("model_name", None)
    _write(trace_path, trace)
    actual = extract_trace_evidence(trace, run_id=str(trace["run_id"]))
    actual.update({
        "artifact_path": str(trace_path),
        "artifact_sha256": sha256_file(trace_path),
    })
    row["execution_evidence"]["trace"] = actual
    _write(paths["examples"], report)

    bundle = build_external_bundle(
        examples_path=paths["examples"],
        adversarial_path=paths["adversarial"],
        reference_path=paths["reference"],
        stability_path=paths["stability"],
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert bundle["valid"] is False
    assert bundle["summary"]["external_semantic_live_e2e_verified"] == 0
    assert any("real model provider/name telemetry is absent" in item for item in bundle["errors"])


def test_composite_bundle_is_only_valid_for_disjoint_current_24_plus_2(
    tmp_path: Path,
) -> None:
    now = datetime.now(timezone.utc)
    local_ids = _local_agent_ids(AGENTS_DIR)
    external_ids = _external_agent_ids(AGENTS_DIR)
    local_sources = _fixture_reports(
        tmp_path / "local-sources",
        now,
        selected_agent_ids=set(local_ids),
    )
    external_sources = _fixture_reports(
        tmp_path / "external-sources",
        now,
        selected_agent_ids=set(external_ids),
    )
    local_bundle = build_local_bundle(
        examples_path=local_sources["examples"],
        adversarial_path=local_sources["adversarial"],
        reference_path=local_sources["reference"],
        stability_path=local_sources["stability"],
        agents_dir=AGENTS_DIR,
        now=now,
    )
    external_bundle = build_external_bundle(
        examples_path=external_sources["examples"],
        adversarial_path=external_sources["adversarial"],
        reference_path=external_sources["reference"],
        stability_path=external_sources["stability"],
        agents_dir=AGENTS_DIR,
        now=now,
    )
    local_path = tmp_path / "local" / "agent_hub_local_semantic_evidence_bundle.json"
    external_path = tmp_path / "external" / "agent_hub_external_semantic_evidence_bundle.json"
    _write(local_path, local_bundle)
    _write(external_path, external_bundle)

    composite = build_composite_bundle(
        local_bundle_path=local_path,
        external_bundle_path=external_path,
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert composite["valid"] is True
    assert composite["summary"] == {
        "visible_agents": 26,
        "local_semantic_e2e_verified": 24,
        "external_semantic_live_e2e_verified": 2,
        "semantic_live_e2e_verified": 26,
        "semantic_live_e2e_pending": [],
    }
    composite_path = (
        tmp_path / "composite" / "agent_hub_composite_semantic_evidence_bundle.json"
    )
    _write(composite_path, composite)
    validation = validate_composite_bundle_file(
        composite_path,
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert validation["valid"] is True
    assert len(validation["verified_agent_ids"]) == 26

    matrix = build_matrix(
        AGENTS_DIR,
        semantic_evidence_path=composite_path,
        semantic_now=now,
    )
    assert matrix["semantic_evidence"]["valid"] is True
    assert matrix["summary"]["visible_semantic_live_e2e_verified"] == 26
    assert matrix["summary"]["visible_semantic_live_e2e_pending"] == []
    assert matrix["summary"]["visible_local_semantic_e2e_verified"] == 24
    assert matrix["summary"]["visible_local_semantic_e2e_pending"] == []
    assert matrix["local_semantic_evidence"][
        "derived_from_semantic_evidence"
    ] is True
    assert matrix["local_semantic_evidence"]["derived_scope"] == (
        "composite_validated_local_component"
    )

    external_bundle["summary"]["external_semantic_live_e2e_verified"] = 1
    _write(external_path, external_bundle)
    rejected = validate_composite_bundle_file(
        composite_path,
        agents_dir=AGENTS_DIR,
        now=now,
    )
    assert rejected["valid"] is False
    assert rejected["verified_agent_ids"] == []
    assert any("source bundle digest mismatch" in item for item in rejected["errors"])
