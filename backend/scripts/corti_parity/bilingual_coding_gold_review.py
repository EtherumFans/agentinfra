"""Build and validate the independent review workflow for bilingual coding gold.

The generated review packet deliberately excludes engineering-authored expected
codes, notes, and evidence spans.  This module can prove that review artifacts
are complete, catalog-bound, evidence-anchored, mutually independent by
declared reviewer identity, and deterministically bound to the blinded packet.
It cannot verify a person's real-world identity or qualification; that remains
an external clinical-governance gate and is represented explicitly.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from data.code_dicts.icd_data import (  # noqa: E402
    CATALOG_MANIFEST_PATH,
    CODE_CATALOG_STATUS,
    ICD10_CN_CODES,
    ICD9_CM3_CODES,
)
from scripts.corti_parity.build_agent_hub_clinical_calibration_plan import (  # noqa: E402
    BILINGUAL_FIXTURE,
    _validate_bilingual_fixture,
)


PACKET_SCHEMA = "icoder.bilingual-coding-blind-review-packet/v1"
REVIEW_SCHEMA = "icoder.bilingual-coding-independent-review/v1"
ADJUDICATION_SCHEMA = "icoder.bilingual-coding-gold-adjudication/v1"
READINESS_SCHEMA = "icoder.bilingual-coding-review-readiness/v1"
PROTOCOL_VERSION = "icoder.bilingual-coding-gold-review/2026-08-27"
DEFAULT_OUT_DIR = (
    REPO_ROOT / "reports" / "agent_hub" / "bilingual_coding_review_readiness_20260827_v1"
)
ALLOWED_QUALIFICATION_ROLES = {
    "certified_clinical_coder",
    "licensed_physician_clinical_coder",
}


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load JSON artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def _without_digest(value: dict[str, Any], field: str) -> dict[str, Any]:
    payload = copy.deepcopy(value)
    payload.pop(field, None)
    return payload


def _iso_timestamp_is_valid(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _catalog_snapshot() -> dict[str, Any]:
    manifest = _read_object(CATALOG_MANIFEST_PATH)
    return {
        "schema_version": CODE_CATALOG_STATUS["schema_version"],
        "catalog_release": CODE_CATALOG_STATUS["catalog_release"],
        "manifest_sha256": sha256_file(CATALOG_MANIFEST_PATH),
        "diagnosis_count": CODE_CATALOG_STATUS["diagnosis_count"],
        "procedure_count": CODE_CATALOG_STATUS["procedure_count"],
        "file_sha256": {
            name: metadata["sha256"]
            for name, metadata in sorted((manifest.get("files") or {}).items())
            if isinstance(metadata, dict)
        },
    }


def _blinded_case(case: dict[str, Any]) -> dict[str, Any]:
    blinded = {
        "case_id": str(case.get("case_id") or ""),
        "department": str(case.get("department") or ""),
        "chart_zh": str(case.get("chart_zh") or ""),
        "chart_en": str(case.get("chart_en") or ""),
        "requested_coding_tasks": [
            "principal_diagnosis_icd10_cn",
            "secondary_diagnoses_icd10_cn",
            "primary_procedure_icd9_cm_3_or_null",
        ],
    }
    blinded["case_sha256"] = canonical_sha256(blinded)
    return blinded


def build_blind_packet(
    *, generated_at: datetime | None = None, fixture_path: Path = BILINGUAL_FIXTURE
) -> dict[str, Any]:
    fixture = _read_object(fixture_path)
    cases, fixture_errors = _validate_bilingual_fixture(fixture)
    if fixture_errors:
        raise ValueError("fixture governance failed: " + "; ".join(fixture_errors))
    now = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    packet: dict[str, Any] = {
        "schema_version": PACKET_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "generated_at": now.isoformat(),
        "source_fixture": {
            "relative_path": fixture_path.resolve()
            .relative_to(REPO_ROOT.resolve())
            .as_posix(),
            "sha256": sha256_file(fixture_path),
            "case_count": len(cases),
        },
        "catalog_snapshot": _catalog_snapshot(),
        "blinding": {
            "engineering_expected_codes_removed": True,
            "engineering_notes_removed": True,
            "engineering_evidence_spans_removed": True,
            "model_outputs_included": False,
        },
        "review_policy": {
            "minimum_independent_reviewers": 2,
            "distinct_reviewer_ids_required": True,
            "reviewers_must_not_view_model_outputs": True,
            "reviewers_must_not_view_engineering_gold": True,
            "exact_bilingual_evidence_anchor_required_per_code": True,
            "catalog_membership_required": True,
            "adjudicator_required_for_any_disagreement": True,
            "external_identity_and_qualification_verification_required": True,
        },
        "cases": [_blinded_case(case) for case in cases],
        "claim_boundaries": {
            "independent_gold_ready": False,
            "clinical_accuracy_proven": False,
            "corti_parity_proven": False,
            "production_ready_proven": False,
        },
    }
    packet["packet_sha256"] = canonical_sha256(packet)
    return packet


def validate_blind_packet(packet: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if packet.get("schema_version") != PACKET_SCHEMA:
        errors.append("unsupported blind review packet schema")
    if packet.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("unsupported blind review protocol")
    supplied_digest = str(packet.get("packet_sha256") or "")
    if supplied_digest != canonical_sha256(_without_digest(packet, "packet_sha256")):
        errors.append("blind review packet digest mismatch")
    source = packet.get("source_fixture")
    source = source if isinstance(source, dict) else {}
    if (
        source.get("sha256") != sha256_file(BILINGUAL_FIXTURE)
        or source.get("case_count") != 5
    ):
        errors.append("blind review packet is not bound to the governed five-case fixture")
    catalog = packet.get("catalog_snapshot")
    if catalog != _catalog_snapshot():
        errors.append("blind review packet catalog snapshot mismatch")
    blinding = packet.get("blinding")
    blinding = blinding if isinstance(blinding, dict) else {}
    if not all(
        blinding.get(field) is expected
        for field, expected in {
            "engineering_expected_codes_removed": True,
            "engineering_notes_removed": True,
            "engineering_evidence_spans_removed": True,
            "model_outputs_included": False,
        }.items()
    ):
        errors.append("blind review packet blinding declaration is invalid")
    cases = packet.get("cases")
    cases = cases if isinstance(cases, list) else []
    if len(cases) != 5:
        errors.append("blind review packet must contain five cases")
    ids: list[str] = []
    forbidden = {
        "expected_principal_diagnosis",
        "expected_secondary_diagnoses",
        "expected_primary_procedure",
        "evidence_spans",
        "notes",
    }
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"blind case[{index}] is not an object")
            continue
        case_id = str(case.get("case_id") or "")
        ids.append(case_id)
        if forbidden & set(case):
            errors.append(f"blind case[{index}] contains engineering gold fields")
        if not str(case.get("chart_zh") or "") or not str(case.get("chart_en") or ""):
            errors.append(f"blind case[{index}] lacks parallel charts")
        supplied_case_digest = str(case.get("case_sha256") or "")
        if supplied_case_digest != canonical_sha256(
            _without_digest(case, "case_sha256")
        ):
            errors.append(f"blind case[{index}] digest mismatch")
    if any(not case_id for case_id in ids) or len(ids) != len(set(ids)):
        errors.append("blind review case IDs must be non-empty and unique")
    claims = packet.get("claim_boundaries")
    claims = claims if isinstance(claims, dict) else {}
    if any(value is not False for value in claims.values()):
        errors.append("blind review packet cannot make completed quality claims")
    return sorted(set(errors))


def _blank_decision(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "principal_diagnosis": {
            "code": "",
            "evidence_zh": "",
            "evidence_en": "",
        },
        "secondary_diagnoses": [],
        "primary_procedure": None,
        "coding_notes": "",
    }


def build_review_template(packet: dict[str, Any], *, reviewer_slot: str) -> dict[str, Any]:
    packet_errors = validate_blind_packet(packet)
    if packet_errors:
        raise ValueError("invalid blind packet: " + "; ".join(packet_errors))
    return {
        "schema_version": REVIEW_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "packet_sha256": packet["packet_sha256"],
        "response_status": "pending_external_review",
        "reviewer": {
            "reviewer_slot": reviewer_slot,
            "reviewer_id": "",
            "qualification_role": "",
            "qualification_reference": "",
            "organization": "",
            "independent_of_icoder_engineering_attested": None,
            "blinded_to_engineering_gold_attested": None,
            "model_output_not_viewed_attested": None,
            "conflict_of_interest_absent_attested": None,
            "signed_at": "",
            "signature_reference": "",
            "external_identity_verification_status": "pending_external_verification",
        },
        "decisions": [
            _blank_decision(str(case.get("case_id") or ""))
            for case in packet["cases"]
            if isinstance(case, dict)
        ],
        "response_sha256": "recompute-after-completion",
    }


def _code(value: Any) -> str:
    return "".join(str(value or "").upper().split())


def _validate_code_item(
    *,
    value: Any,
    allowed_codes: set[str],
    chart_zh: str,
    chart_en: str,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{label} is not an object")
        return
    code = _code(value.get("code"))
    evidence_zh = str(value.get("evidence_zh") or "")
    evidence_en = str(value.get("evidence_en") or "")
    if not code or code not in allowed_codes:
        errors.append(f"{label} code is absent from the governed catalog")
    if not evidence_zh or evidence_zh not in chart_zh:
        errors.append(f"{label} Chinese evidence is not an exact chart span")
    if not evidence_en or evidence_en not in chart_en:
        errors.append(f"{label} English evidence is not an exact chart span")


def validate_completed_review(
    packet: dict[str, Any], review: dict[str, Any]
) -> list[str]:
    errors = validate_blind_packet(packet)
    if review.get("schema_version") != REVIEW_SCHEMA:
        errors.append("unsupported independent review schema")
    if review.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("independent review protocol mismatch")
    if review.get("packet_sha256") != packet.get("packet_sha256"):
        errors.append("independent review is bound to a different packet")
    if review.get("response_status") != "completed":
        errors.append("independent review is not completed")
    supplied_digest = str(review.get("response_sha256") or "")
    if supplied_digest != canonical_sha256(_without_digest(review, "response_sha256")):
        errors.append("independent review digest mismatch")

    reviewer = review.get("reviewer")
    reviewer = reviewer if isinstance(reviewer, dict) else {}
    if not str(reviewer.get("reviewer_id") or "").strip():
        errors.append("reviewer_id is required")
    if reviewer.get("qualification_role") not in ALLOWED_QUALIFICATION_ROLES:
        errors.append("reviewer qualification role is not allowed")
    for field in ("qualification_reference", "organization", "signature_reference"):
        if not str(reviewer.get(field) or "").strip():
            errors.append(f"reviewer {field} is required")
    for field in (
        "independent_of_icoder_engineering_attested",
        "blinded_to_engineering_gold_attested",
        "model_output_not_viewed_attested",
        "conflict_of_interest_absent_attested",
    ):
        if reviewer.get(field) is not True:
            errors.append(f"reviewer attestation must be true: {field}")
    if not _iso_timestamp_is_valid(reviewer.get("signed_at")):
        errors.append("reviewer signed_at must be timezone-aware ISO-8601")
    if reviewer.get("external_identity_verification_status") not in {
        "pending_external_verification",
        "verified",
    }:
        errors.append("reviewer external identity verification status is invalid")

    packet_cases = {
        str(case.get("case_id") or ""): case
        for case in packet.get("cases") or []
        if isinstance(case, dict)
    }
    decisions = review.get("decisions")
    decisions = decisions if isinstance(decisions, list) else []
    decision_ids = [
        str(item.get("case_id") or "") for item in decisions if isinstance(item, dict)
    ]
    if set(decision_ids) != set(packet_cases) or len(decision_ids) != len(packet_cases):
        errors.append("review decisions must cover every packet case exactly once")
    diagnosis_codes = {_code(item[0]) for item in ICD10_CN_CODES}
    procedure_codes = {_code(item[0]) for item in ICD9_CM3_CODES}
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict):
            errors.append(f"review decision[{index}] is not an object")
            continue
        case_id = str(decision.get("case_id") or "")
        case = packet_cases.get(case_id)
        if case is None:
            continue
        chart_zh = str(case.get("chart_zh") or "")
        chart_en = str(case.get("chart_en") or "")
        _validate_code_item(
            value=decision.get("principal_diagnosis"),
            allowed_codes=diagnosis_codes,
            chart_zh=chart_zh,
            chart_en=chart_en,
            label=f"decision[{case_id}].principal_diagnosis",
            errors=errors,
        )
        secondary = decision.get("secondary_diagnoses")
        if not isinstance(secondary, list):
            errors.append(f"decision[{case_id}].secondary_diagnoses is not a list")
        else:
            seen: set[str] = set()
            for secondary_index, item in enumerate(secondary):
                _validate_code_item(
                    value=item,
                    allowed_codes=diagnosis_codes,
                    chart_zh=chart_zh,
                    chart_en=chart_en,
                    label=f"decision[{case_id}].secondary[{secondary_index}]",
                    errors=errors,
                )
                code = _code(item.get("code")) if isinstance(item, dict) else ""
                if code in seen:
                    errors.append(f"decision[{case_id}] has duplicate secondary code")
                seen.add(code)
        procedure = decision.get("primary_procedure")
        if procedure is not None:
            _validate_code_item(
                value=procedure,
                allowed_codes=procedure_codes,
                chart_zh=chart_zh,
                chart_en=chart_en,
                label=f"decision[{case_id}].primary_procedure",
                errors=errors,
            )
    return sorted(set(errors))


def _decision_signature(decision: dict[str, Any]) -> dict[str, Any]:
    principal = decision.get("principal_diagnosis")
    principal = principal if isinstance(principal, dict) else {}
    secondary = decision.get("secondary_diagnoses")
    secondary = secondary if isinstance(secondary, list) else []
    procedure = decision.get("primary_procedure")
    procedure = procedure if isinstance(procedure, dict) else {}
    return {
        "principal": _code(principal.get("code")),
        "secondary": sorted(
            _code(item.get("code"))
            for item in secondary
            if isinstance(item, dict) and _code(item.get("code"))
        ),
        "procedure": _code(procedure.get("code")),
    }


def compare_completed_reviews(
    packet: dict[str, Any], review_a: dict[str, Any], review_b: dict[str, Any]
) -> dict[str, Any]:
    errors = [
        *validate_completed_review(packet, review_a),
        *validate_completed_review(packet, review_b),
    ]
    reviewer_a = review_a.get("reviewer") or {}
    reviewer_b = review_b.get("reviewer") or {}
    if str(reviewer_a.get("reviewer_id") or "") == str(
        reviewer_b.get("reviewer_id") or ""
    ):
        errors.append("independent reviews must use distinct reviewer IDs")
    decisions_a = {
        str(item.get("case_id") or ""): item
        for item in review_a.get("decisions") or []
        if isinstance(item, dict)
    }
    decisions_b = {
        str(item.get("case_id") or ""): item
        for item in review_b.get("decisions") or []
        if isinstance(item, dict)
    }
    case_results: list[dict[str, Any]] = []
    for case in packet.get("cases") or []:
        case_id = str(case.get("case_id") or "") if isinstance(case, dict) else ""
        signature_a = _decision_signature(decisions_a.get(case_id, {}))
        signature_b = _decision_signature(decisions_b.get(case_id, {}))
        case_results.append(
            {
                "case_id": case_id,
                "reviewer_a_codes": signature_a,
                "reviewer_b_codes": signature_b,
                "agreement": signature_a == signature_b,
            }
        )
    disagreement_ids = [
        item["case_id"] for item in case_results if item["agreement"] is not True
    ]
    comparison: dict[str, Any] = {
        "schema_version": "icoder.bilingual-coding-review-comparison/v1",
        "protocol_version": PROTOCOL_VERSION,
        "packet_sha256": packet.get("packet_sha256"),
        "review_response_sha256": [
            review_a.get("response_sha256"),
            review_b.get("response_sha256"),
        ],
        "valid": not errors,
        "errors": sorted(set(errors)),
        "case_results": case_results,
        "agreement_case_count": sum(item["agreement"] is True for item in case_results),
        "disagreement_case_ids": disagreement_ids,
        "requires_adjudication": bool(disagreement_ids),
        "independent_gold_ready": False,
        "external_gate": (
            "adjudication_and_external_identity_verification_required"
            if disagreement_ids
            else "external_identity_verification_required"
        ),
    }
    comparison["comparison_sha256"] = canonical_sha256(comparison)
    return comparison


def build_adjudication_template(packet: dict[str, Any]) -> dict[str, Any]:
    packet_errors = validate_blind_packet(packet)
    if packet_errors:
        raise ValueError("invalid blind packet: " + "; ".join(packet_errors))
    return {
        "schema_version": ADJUDICATION_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "packet_sha256": packet["packet_sha256"],
        "review_response_sha256": [],
        "adjudication_status": "pending_external_reviews",
        "adjudicator": {
            "adjudicator_id": "",
            "qualification_role": "",
            "qualification_reference": "",
            "organization": "",
            "independent_of_reviewers_attested": None,
            "conflict_of_interest_absent_attested": None,
            "signed_at": "",
            "signature_reference": "",
        },
        "external_identity_verification": {
            "status": "pending",
            "verified_by": "",
            "verified_at": "",
            "evidence_reference": "",
        },
        "final_decisions": [
            _blank_decision(str(case.get("case_id") or ""))
            for case in packet["cases"]
            if isinstance(case, dict)
        ],
        "claim_boundaries": {
            "independent_gold_ready": False,
            "clinical_accuracy_proven": False,
            "corti_parity_proven": False,
            "production_ready_proven": False,
        },
        "adjudication_sha256": "recompute-after-completion",
    }


def validate_completed_adjudication(
    packet: dict[str, Any],
    review_a: dict[str, Any],
    review_b: dict[str, Any],
    adjudication: dict[str, Any],
) -> list[str]:
    comparison = compare_completed_reviews(packet, review_a, review_b)
    errors = list(comparison["errors"])
    if adjudication.get("schema_version") != ADJUDICATION_SCHEMA:
        errors.append("unsupported gold adjudication schema")
    if adjudication.get("protocol_version") != PROTOCOL_VERSION:
        errors.append("gold adjudication protocol mismatch")
    if adjudication.get("packet_sha256") != packet.get("packet_sha256"):
        errors.append("gold adjudication is bound to a different packet")
    expected_review_hashes = {
        str(review_a.get("response_sha256") or ""),
        str(review_b.get("response_sha256") or ""),
    }
    supplied_review_hashes = {
        str(value or "") for value in adjudication.get("review_response_sha256") or []
    }
    if supplied_review_hashes != expected_review_hashes or "" in supplied_review_hashes:
        errors.append("gold adjudication review digests do not match")
    if adjudication.get("adjudication_status") != "completed":
        errors.append("gold adjudication is not completed")
    supplied_digest = str(adjudication.get("adjudication_sha256") or "")
    if supplied_digest != canonical_sha256(
        _without_digest(adjudication, "adjudication_sha256")
    ):
        errors.append("gold adjudication digest mismatch")

    reviewer_ids = {
        str((review_a.get("reviewer") or {}).get("reviewer_id") or ""),
        str((review_b.get("reviewer") or {}).get("reviewer_id") or ""),
    }
    adjudicator = adjudication.get("adjudicator")
    adjudicator = adjudicator if isinstance(adjudicator, dict) else {}
    adjudicator_id = str(adjudicator.get("adjudicator_id") or "")
    if not adjudicator_id or adjudicator_id in reviewer_ids:
        errors.append("adjudicator must be distinct from both reviewers")
    if adjudicator.get("qualification_role") not in ALLOWED_QUALIFICATION_ROLES:
        errors.append("adjudicator qualification role is not allowed")
    for field in (
        "qualification_reference",
        "organization",
        "signature_reference",
    ):
        if not str(adjudicator.get(field) or "").strip():
            errors.append(f"adjudicator {field} is required")
    for field in (
        "independent_of_reviewers_attested",
        "conflict_of_interest_absent_attested",
    ):
        if adjudicator.get(field) is not True:
            errors.append(f"adjudicator attestation must be true: {field}")
    if not _iso_timestamp_is_valid(adjudicator.get("signed_at")):
        errors.append("adjudicator signed_at must be timezone-aware ISO-8601")

    verification = adjudication.get("external_identity_verification")
    verification = verification if isinstance(verification, dict) else {}
    if verification.get("status") != "verified":
        errors.append("external identity verification is not completed")
    if set(verification.get("reviewer_ids_verified") or []) != reviewer_ids:
        errors.append("external identity verification does not cover both reviewers")
    if verification.get("adjudicator_id_verified") != adjudicator_id:
        errors.append("external identity verification does not cover the adjudicator")
    for field in ("verified_by", "evidence_reference"):
        if not str(verification.get(field) or "").strip():
            errors.append(f"external identity verification {field} is required")
    if not _iso_timestamp_is_valid(verification.get("verified_at")):
        errors.append("external identity verified_at must be timezone-aware ISO-8601")

    final_decisions = adjudication.get("final_decisions")
    final_decisions = final_decisions if isinstance(final_decisions, list) else []
    decision_check = {
        "schema_version": REVIEW_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "packet_sha256": packet.get("packet_sha256"),
        "response_status": "completed",
        "reviewer": {
            "reviewer_id": adjudicator_id,
            "qualification_role": adjudicator.get("qualification_role"),
            "qualification_reference": adjudicator.get("qualification_reference"),
            "organization": adjudicator.get("organization"),
            "independent_of_icoder_engineering_attested": True,
            "blinded_to_engineering_gold_attested": True,
            "model_output_not_viewed_attested": True,
            "conflict_of_interest_absent_attested": adjudicator.get(
                "conflict_of_interest_absent_attested"
            ),
            "signed_at": adjudicator.get("signed_at"),
            "signature_reference": adjudicator.get("signature_reference"),
            "external_identity_verification_status": "verified",
        },
        "decisions": final_decisions,
    }
    decision_check["response_sha256"] = canonical_sha256(decision_check)
    errors.extend(validate_completed_review(packet, decision_check))

    claims = adjudication.get("claim_boundaries")
    claims = claims if isinstance(claims, dict) else {}
    if claims.get("independent_gold_ready") is not True:
        errors.append("completed adjudication must explicitly mark independent gold ready")
    for field in (
        "clinical_accuracy_proven",
        "corti_parity_proven",
        "production_ready_proven",
    ):
        if claims.get(field) is not False:
            errors.append(f"completed adjudication cannot prove {field}")
    return sorted(set(errors))


def write_readiness_bundle(out_dir: Path) -> dict[str, Any]:
    packet = build_blind_packet()
    packet_errors = validate_blind_packet(packet)
    review_a = build_review_template(packet, reviewer_slot="reviewer_a")
    review_b = build_review_template(packet, reviewer_slot="reviewer_b")
    adjudication = build_adjudication_template(packet)
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "blind_review_packet.json": packet,
        "reviewer_a_response_template.json": review_a,
        "reviewer_b_response_template.json": review_b,
        "adjudication_template.json": adjudication,
    }
    for filename, payload in artifacts.items():
        (out_dir / filename).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    report: dict[str, Any] = {
        "schema_version": READINESS_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ready_for_external_review": not packet_errors,
        "independent_gold_ready": False,
        "packet_validation_errors": packet_errors,
        "case_count": len(packet["cases"]),
        "packet_sha256": packet["packet_sha256"],
        "artifacts": {
            filename: {
                "sha256": sha256_file(out_dir / filename),
                "size_bytes": (out_dir / filename).stat().st_size,
            }
            for filename in artifacts
        },
        "external_gates": [
            "two qualified independent reviewers must complete the blinded templates",
            "reviewer identities, qualifications, signatures, and conflicts must be externally verified",
            "all code disagreements require a distinct qualified adjudicator",
            "a clinical governance owner must approve the final adjudication artifact",
        ],
        "claim_boundaries": {
            "clinical_accuracy_proven": False,
            "corti_parity_proven": False,
            "production_ready_proven": False,
        },
    }
    report["report_sha256"] = canonical_sha256(report)
    report_path = out_dir / "review_readiness_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    validate_parser = subparsers.add_parser("validate-review")
    validate_parser.add_argument("--packet", type=Path, required=True)
    validate_parser.add_argument("--review", type=Path, required=True)
    compare_parser = subparsers.add_parser("compare")
    compare_parser.add_argument("--packet", type=Path, required=True)
    compare_parser.add_argument("--review-a", type=Path, required=True)
    compare_parser.add_argument("--review-b", type=Path, required=True)
    compare_parser.add_argument("--output", type=Path, required=True)
    adjudication_parser = subparsers.add_parser("validate-adjudication")
    adjudication_parser.add_argument("--packet", type=Path, required=True)
    adjudication_parser.add_argument("--review-a", type=Path, required=True)
    adjudication_parser.add_argument("--review-b", type=Path, required=True)
    adjudication_parser.add_argument("--adjudication", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "build":
        report = write_readiness_bundle(args.out_dir.resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ready_for_external_review"] else 2
    packet = _read_object(args.packet.resolve())
    if args.command == "validate-review":
        errors = validate_completed_review(packet, _read_object(args.review.resolve()))
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
        return 0 if not errors else 2
    if args.command == "validate-adjudication":
        errors = validate_completed_adjudication(
            packet,
            _read_object(args.review_a.resolve()),
            _read_object(args.review_b.resolve()),
            _read_object(args.adjudication.resolve()),
        )
        print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
        return 0 if not errors else 2
    comparison = compare_completed_reviews(
        packet,
        _read_object(args.review_a.resolve()),
        _read_object(args.review_b.resolve()),
    )
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"valid": comparison["valid"], "output": str(output)}))
    return 0 if comparison["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
