"""Build a governed multi-case calibration plan for the two model Agents.

This module performs no network or model calls.  It inventories the only
current fixtures that may be used in a controlled external-provider
development run and keeps the CCL-derived records out of that egress scope
until provenance, licence, and de-identification approval are recorded.

The resulting artifact is a *plan*, not clinical-quality evidence.  In
particular, neither a valid plan nor a passing synthetic replay proves Corti
parity, production readiness, or hospital acceptance.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _load_legacy_verifier():
    """Load the root-level verifier without colliding with backend/scripts."""

    module_path = REPO_ROOT / "scripts" / "corti_parity" / "verify_benchmark_candidate.py"
    spec = importlib.util.spec_from_file_location(
        "_icoder_legacy_benchmark_verifier", module_path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load legacy benchmark verifier: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.verify_candidate


verify_candidate = _load_legacy_verifier()


SCHEMA_VERSION = "icoder.agent-hub-clinical-calibration-plan/v1"
QUALITY_SCOPE = "synthetic_development_calibration_not_independent_clinical_gold"
DEFAULT_OUT_DIR = (
    REPO_ROOT / "reports" / "agent_hub" / "clinical_calibration_plan_20260825_v1"
)

CDI_FIXTURE = BACKEND_ROOT / "tests" / "fixtures" / "cdi_gate8_40cases.json"
BILINGUAL_FIXTURE = (
    BACKEND_ROOT / "tests" / "fixtures" / "held_out_bilingual_v1.json"
)
CCL_FIXTURES = (
    ("ccl2026_train_1800", BACKEND_ROOT / "tests" / "fixtures" / "ccl2026_train_gold.json"),
    ("ccl2026_validation_100", BACKEND_ROOT / "tests" / "fixtures" / "ccl2026_val_100.json"),
    ("icoder_201_subset", BACKEND_ROOT / "tests" / "fixtures" / "icoder_201.json"),
)
LEGACY_CANDIDATE = REPO_ROOT / "reports" / "track_h" / "h4_benchmark_candidate_rc5"
LEGACY_RUNNER = BACKEND_ROOT / "scripts" / "phase5_d_p05_gate8_icoder_40case_run.py"
GOLD_REVIEW_TOOL = (
    BACKEND_ROOT
    / "scripts"
    / "corti_parity"
    / "bilingual_coding_gold_review.py"
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load {path}: {exc}") from exc


def _coding_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("gold_cases", "cases"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def _asset(path: Path, *, case_count: int) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "relative_path": path.resolve().relative_to(REPO_ROOT.resolve()).as_posix(),
        "sha256": _sha256(path),
        "size_bytes": path.stat().st_size,
        "case_count": case_count,
    }


def _validate_cdi_fixture(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    cases = payload.get("cases") if isinstance(payload, dict) else None
    cases = cases if isinstance(cases, list) else []
    meta = payload.get("_meta") if isinstance(payload, dict) else {}
    meta = meta if isinstance(meta, dict) else {}
    if len(cases) != 40:
        errors.append(f"CDI fixture must contain 40 cases, found {len(cases)}")
    ids = [str(case.get("case_id") or "") for case in cases if isinstance(case, dict)]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        errors.append("CDI case IDs must be non-empty and unique")
    expected_categories = {
        "clear_gap": 10,
        "complete_chart": 10,
        "insufficient_evidence": 5,
        "negation_history": 5,
        "document_conflict": 5,
        "lab_positive_uncertain": 5,
    }
    actual_categories = Counter(
        str(case.get("category") or "") for case in cases if isinstance(case, dict)
    )
    if dict(actual_categories) != expected_categories:
        errors.append("CDI category distribution does not match the governed 40-case suite")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"CDI case[{index}] is not an object")
            continue
        expected = case.get("expected")
        expected = expected if isinstance(expected, dict) else {}
        if not str(case.get("chart_zh") or "").strip():
            errors.append(f"CDI case[{index}] has no chart_zh")
        if not isinstance(expected.get("query_count_min"), int):
            errors.append(f"CDI case[{index}] has no integer query_count_min")
        if not isinstance(expected.get("query_count_max"), int):
            errors.append(f"CDI case[{index}] has no integer query_count_max")
    deidentification = str(meta.get("deidentification") or "")
    if "no names" not in deidentification or "IDs" not in deidentification:
        errors.append("CDI fixture does not carry its expected de-identification declaration")
    return cases, errors


def _validate_bilingual_fixture(
    payload: Any,
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    cases = payload.get("cases") if isinstance(payload, dict) else None
    cases = cases if isinstance(cases, list) else []
    meta = payload.get("_meta") if isinstance(payload, dict) else {}
    meta = meta if isinstance(meta, dict) else {}
    declared_count = meta.get("current_case_count")
    if declared_count != len(cases) or len(cases) != 5:
        errors.append(
            "bilingual fixture must contain its declared five-case seed"
        )
    if str(meta.get("phi_status") or "").casefold().find("phi-free") < 0:
        errors.append("bilingual fixture is not explicitly declared PHI-free")
    if "synthetic" not in str(meta.get("construction_method") or "").casefold():
        errors.append("bilingual fixture is not explicitly declared synthetic")
    ids = [str(case.get("case_id") or "") for case in cases if isinstance(case, dict)]
    if len(ids) != len(set(ids)) or any(not value for value in ids):
        errors.append("bilingual case IDs must be non-empty and unique")
    try:
        from data.code_dicts.icd_data import ICD10_CN_CODES, ICD9_CM3_CODES

        diagnosis_catalog = {str(item[0]).upper() for item in ICD10_CN_CODES}
        procedure_catalog = {str(item[0]).upper() for item in ICD9_CM3_CODES}
    except Exception:
        diagnosis_catalog = set()
        procedure_catalog = set()
        errors.append("governed coding catalogs could not be loaded")
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"bilingual case[{index}] is not an object")
            continue
        if not str(case.get("chart_zh") or "").strip() or not str(
            case.get("chart_en") or ""
        ).strip():
            errors.append(f"bilingual case[{index}] must contain zh and en charts")
        principal = case.get("expected_principal_diagnosis")
        if not isinstance(principal, dict) or not str(principal.get("code") or ""):
            errors.append(f"bilingual case[{index}] has no principal diagnosis code")
        expected_diagnoses = [principal, *(case.get("expected_secondary_diagnoses") or [])]
        for diagnosis in expected_diagnoses:
            code = str(diagnosis.get("code") or "") if isinstance(diagnosis, dict) else ""
            if code and code.upper() not in diagnosis_catalog:
                errors.append(
                    f"bilingual case[{index}] diagnosis code is absent from governed catalog: {code}"
                )
        procedure = case.get("expected_primary_procedure")
        procedure_code = (
            str(procedure.get("code") or "")
            if isinstance(procedure, dict) else ""
        )
        if procedure_code and procedure_code.upper() not in procedure_catalog:
            errors.append(
                f"bilingual case[{index}] procedure code is absent from governed catalog: {procedure_code}"
            )
    return cases, errors


def _legacy_runner_findings(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    findings: list[dict[str, str]] = []
    checks = (
        (
            "hard_coded_multi_dimension_result",
            "multi_dim_slipped = 0" in text,
            "The legacy runner hard-codes slipped multi-dimension queries to zero instead of re-evaluating final queries.",
        ),
        (
            "hard_coded_login_credentials",
            '"password": "Gate7!2026"' in text or '"password": "admin"' in text,
            "The legacy runner contains fixed development login credentials.",
        ),
        (
            "legacy_non_agent_hub_endpoint",
            "/api/v1/cdi/runs" in text,
            "The legacy runner bypasses the unified Agent Hub run endpoint.",
        ),
        (
            "missing_live_model_attestation_gate",
            "model_call_observed" not in text,
            "The legacy runner does not require signed RunTrace evidence of a real provider/model call.",
        ),
    )
    for finding_id, present, detail in checks:
        if present:
            findings.append({"id": finding_id, "detail": detail})
    return findings


def _gold_review_workflow_is_ready(path: Path) -> bool:
    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return False
    required_markers = {
        "icoder.bilingual-coding-blind-review-packet/v1",
        "icoder.bilingual-coding-independent-review/v1",
        "icoder.bilingual-coding-gold-adjudication/v1",
        "def validate_blind_packet(",
        "def validate_completed_review(",
        "def compare_completed_reviews(",
        "def validate_completed_adjudication(",
        "engineering_expected_codes_removed",
        "external_identity_and_qualification_verification_required",
        "independent reviews must use distinct reviewer IDs",
        "adjudication_and_external_identity_verification_required",
    }
    return all(marker in source for marker in required_markers)


def build_plan(*, generated_at: datetime | None = None) -> dict[str, Any]:
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors: list[str] = []

    try:
        cdi_payload = _load_json(CDI_FIXTURE)
        cdi_cases, cdi_errors = _validate_cdi_fixture(cdi_payload)
        errors.extend(cdi_errors)
    except ValueError as exc:
        cdi_payload, cdi_cases = {}, []
        errors.append(str(exc))

    try:
        bilingual_payload = _load_json(BILINGUAL_FIXTURE)
        bilingual_cases, bilingual_errors = _validate_bilingual_fixture(
            bilingual_payload
        )
        errors.extend(bilingual_errors)
    except ValueError as exc:
        bilingual_payload, bilingual_cases = {}, []
        errors.append(str(exc))

    ccl_assets: list[dict[str, Any]] = []
    for asset_id, path in CCL_FIXTURES:
        try:
            payload = _load_json(path)
            rows = _coding_rows(payload)
            item = _asset(path, case_count=len(rows))
        except ValueError as exc:
            errors.append(str(exc))
            item = {
                "path": str(path.resolve()),
                "relative_path": path.resolve().relative_to(REPO_ROOT.resolve()).as_posix(),
                "sha256": "",
                "size_bytes": 0,
                "case_count": 0,
            }
        item.update(
            {
                "asset_id": asset_id,
                "role": "local_inventory_only",
                "external_provider_egress_allowed": False,
                "independent_clinical_gold": False,
                "blockers": [
                    "commercial-use and external-processing licence not documented",
                    "source provenance not independently verified",
                    "de-identification certificate not present",
                    "derived/subsampled from the same CCL 2026 training monoculture",
                ],
            }
        )
        ccl_assets.append(item)

    legacy_verification = verify_candidate(LEGACY_CANDIDATE)
    if legacy_verification.get("integrity") != "passed":
        errors.append("legacy CDI benchmark candidate integrity failed")
    legacy_findings = _legacy_runner_findings(LEGACY_RUNNER)
    if len(legacy_findings) != 4:
        errors.append("legacy runner audit did not detect all four known evidence flaws")
    gold_review_workflow_ready = _gold_review_workflow_is_ready(GOLD_REVIEW_TOOL)
    if not gold_review_workflow_ready:
        errors.append("independent bilingual coding gold review workflow is incomplete")

    cdi_asset = (
        _asset(CDI_FIXTURE, case_count=len(cdi_cases))
        if CDI_FIXTURE.is_file()
        else {}
    )
    cdi_asset.update(
        {
            "asset_id": "cdi_corti_teacher_calibration_40",
            "role": "controlled_external_model_calibration",
            "external_provider_egress_allowed": True,
            "egress_basis": "fixture declaration: no names, IDs, phones, or addresses",
            "independent_clinical_gold": False,
            "corti_teacher_calibration": True,
        }
    )
    bilingual_asset = (
        _asset(BILINGUAL_FIXTURE, case_count=len(bilingual_cases))
        if BILINGUAL_FIXTURE.is_file()
        else {}
    )
    bilingual_asset.update(
        {
            "asset_id": "medical_coding_held_out_bilingual_seed_5",
            "role": "controlled_external_model_calibration",
            "external_provider_egress_allowed": True,
            "egress_basis": "fixture declaration: synthetic and PHI-free",
            "independent_clinical_gold": False,
            "engineering_team_authored": True,
            "target_case_count": 100,
        }
    )

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "quality_scope": QUALITY_SCOPE,
        "valid": not errors,
        "errors": sorted(set(errors)),
        "controlled_external_model_run": {
            "ready": not errors,
            "serial_only": True,
            "loopback_application_transport_only": True,
            "native_medcoder_disabled": True,
            "local_stt_disabled": True,
            "temporary_database_required": True,
            "process_scoped_credential_required": True,
            "total_agent_invocations": len(cdi_cases) + (2 * len(bilingual_cases)),
            "suites": [
                {
                    "suite_id": "cdi_zh_40",
                    "agent_id": "clinical-documentation-improvement-agent",
                    "case_count": len(cdi_cases),
                    "languages": ["zh-CN"],
                    "metrics": [
                        "fresh_real_model_trace_attestation_rate",
                        "query_count_expected_range_rate",
                        "complete_chart_over_query_rate",
                        "clear_gap_under_query_rate",
                        "final_query_single_dimension_rate_recomputed",
                        "evidence_exact_anchor_rate",
                        "response_options_four_plus_rate",
                        "escape_hatch_rate",
                        "non_leading_gate_pass_rate",
                    ],
                },
                {
                    "suite_id": "medical_coding_bilingual_seed_5x2",
                    "agent_id": "medical-coding-agent",
                    "case_count": 2 * len(bilingual_cases),
                    "languages": ["zh-CN", "en-US"],
                    "metrics": [
                        "fresh_real_model_trace_attestation_rate",
                        "principal_diagnosis_exact_match_rate",
                        "secondary_diagnosis_set_f1",
                        "primary_procedure_exact_match_rate",
                        "assigned_code_evidence_exact_anchor_rate",
                        "cross_language_code_set_consistency_rate",
                        "human_review_enforcement_rate",
                    ],
                },
            ],
        },
        "assets": {
            "external_calibration_allowed": [cdi_asset, bilingual_asset],
            "external_calibration_blocked": ccl_assets,
        },
        "legacy_cdi_candidate": {
            "status": "historical_calibration_only_not_current_release_evidence",
            "candidate_version": legacy_verification.get("candidate_version"),
            "integrity": legacy_verification.get("integrity"),
            "parity_status": legacy_verification.get("parity_status"),
            "metric_gaps": legacy_verification.get("gaps", []),
            "runner_findings": legacy_findings,
            "fresh_model_run": False,
            "current_agent_pack_bound": False,
        },
        "independent_bilingual_coding_gold_review": {
            "protocol_version": "icoder.bilingual-coding-gold-review/2026-08-27",
            "tool_relative_path": GOLD_REVIEW_TOOL.resolve()
            .relative_to(REPO_ROOT.resolve())
            .as_posix(),
            "ready_for_blinded_external_review": gold_review_workflow_ready,
            "source_case_count": len(bilingual_cases),
            "minimum_independent_reviewers": 2,
            "engineering_gold_removed_from_review_packet": True,
            "model_outputs_removed_from_review_packet": True,
            "catalog_and_bilingual_evidence_validation": True,
            "disagreement_adjudication_required": True,
            "external_identity_verification_required": True,
            "completed_independent_reviews": 0,
            "external_identity_verification_completed": False,
            "independent_gold_ready": False,
        },
        "claim_boundaries": {
            "clinical_accuracy_proven": False,
            "independent_gold_used": False,
            "corti_parity_proven": False,
            "hospital_acceptance_proven": False,
            "production_ready_proven": False,
            "allowed_claim": (
                "Synthetic multi-case development calibration is prepared; "
                "results require a fresh, attested real-model run."
            ),
        },
        "external_release_gates": [
            "expand bilingual coding suite from 5 to at least 100 cases",
            "independent bilingual clinical coder adjudication",
            "held-out hospital-distribution validation under approved DPA",
            "data provenance, licence, and de-identification sign-off",
            "controlled Corti head-to-head on identical authorized inputs",
            "at least one design-partner hospital acceptance review",
        ],
        "network_used": False,
        "models_loaded": False,
        "real_model_executed": False,
    }
    digest_payload = copy.deepcopy(plan)
    plan["plan_sha256"] = _canonical_sha256(digest_payload)
    return plan


def validate_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if plan.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported schema_version")
    if plan.get("quality_scope") != QUALITY_SCOPE:
        errors.append("quality_scope is missing or overstated")
    supplied_digest = str(plan.get("plan_sha256") or "")
    digest_payload = copy.deepcopy(plan)
    digest_payload.pop("plan_sha256", None)
    if supplied_digest != _canonical_sha256(digest_payload):
        errors.append("canonical plan digest mismatch")
    if plan.get("valid") is not True:
        errors.append("plan source validation did not pass")
    claims = plan.get("claim_boundaries")
    claims = claims if isinstance(claims, dict) else {}
    for field in (
        "clinical_accuracy_proven",
        "independent_gold_used",
        "corti_parity_proven",
        "hospital_acceptance_proven",
        "production_ready_proven",
    ):
        if claims.get(field) is not False:
            errors.append(f"claim boundary must remain false: {field}")
    blocked = ((plan.get("assets") or {}).get("external_calibration_blocked") or [])
    if len(blocked) != 3 or any(
        item.get("external_provider_egress_allowed") is not False
        for item in blocked
        if isinstance(item, dict)
    ):
        errors.append("all three CCL-derived assets must remain external-egress blocked")
    run = plan.get("controlled_external_model_run")
    run = run if isinstance(run, dict) else {}
    if run.get("total_agent_invocations") != 50:
        errors.append("controlled calibration must contain exactly 50 serial invocations")
    review = plan.get("independent_bilingual_coding_gold_review")
    review = review if isinstance(review, dict) else {}
    if (
        review.get("ready_for_blinded_external_review") is not True
        or review.get("minimum_independent_reviewers") != 2
        or review.get("engineering_gold_removed_from_review_packet") is not True
        or review.get("model_outputs_removed_from_review_packet") is not True
        or review.get("catalog_and_bilingual_evidence_validation") is not True
        or review.get("disagreement_adjudication_required") is not True
        or review.get("external_identity_verification_required") is not True
        or review.get("completed_independent_reviews") != 0
        or review.get("external_identity_verification_completed") is not False
        or review.get("independent_gold_ready") is not False
    ):
        errors.append("independent bilingual coding gold review boundary is invalid")
    return sorted(set(errors))


def write_plan(out_dir: Path, plan: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "agent_hub_clinical_calibration_plan.json"
    md_path = out_dir / "agent_hub_clinical_calibration_plan.md"
    json_path.write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    run = plan["controlled_external_model_run"]
    lines = [
        "# Agent Hub clinical calibration plan",
        "",
        f"Generated: `{plan['generated_at']}`",
        "",
        f"Validation: **{'PASS' if plan['valid'] else 'FAIL'}**",
        "",
        f"Controlled serial invocations prepared: **{run['total_agent_invocations']}**",
        "",
        "This is a synthetic development calibration plan, not independent clinical gold or production approval.",
        "",
        "## External gates",
        "",
    ]
    lines.extend(f"- {item}" for item in plan["external_release_gates"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    plan = build_plan()
    validation_errors = validate_plan(plan)
    if validation_errors:
        plan["valid"] = False
        plan["errors"] = sorted(set(plan.get("errors", []) + validation_errors))
    json_path, md_path = write_plan(args.out_dir.resolve(), plan)
    print(json.dumps({
        "valid": plan["valid"],
        "errors": plan["errors"],
        "json": str(json_path),
        "markdown": str(md_path),
        "plan_sha256": plan["plan_sha256"],
    }, ensure_ascii=False, indent=2))
    return 0 if plan["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
