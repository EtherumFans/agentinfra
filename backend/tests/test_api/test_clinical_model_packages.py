from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select


async def _register(client, label: str) -> dict:
    suffix = uuid.uuid4().hex[:8]
    response = await client.post("/api/auth/register", json={
        "username": f"{label}-{suffix}",
        "email": f"{label}-{suffix}@example.com",
        "password": "password123",
        "full_name": f"{label} Test",
        "organization_name": f"{label} Org {suffix}",
    })
    assert response.status_code == 201, response.text
    return response.json()


def _manifest(version: str, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "package_key": "cn.icoder.coding-neighbor",
        "package_version": version,
        "package_sha256": "1" * 64,
        "use_case": "clinical_coding_decision_support",
        "model_kind": "bounded-char-ngram-neighbor",
        "runtime_contract": "icoder.clinical-coding/v1",
        "jurisdiction": "CN",
        "training_data_scope": "aggregate_manifest_only",
        "training_dataset_sha256": "2" * 64,
        "training_case_count": 1800,
        "evaluation_evidence_sha256": "3" * 64,
        "license_status": "verified",
        "redistribution_authorized": True,
        "cloud_use_authorized": True,
        "hospital_use_authorized": True,
        "independent_gold_validated": True,
        "independent_reviewer_approved": True,
    }
    payload.update(overrides)
    return payload


async def _reviewer_headers(client, owner: dict) -> dict[str, str]:
    from app.database import AsyncSessionLocal
    from app.middleware.auth import create_access_token
    from app.models.organization import OrganizationMember, OrgRole
    from app.models.user import User

    reviewer = await _register(client, "clinical-model-reviewer")
    reviewer_username = reviewer["user"]["username"]
    async with AsyncSessionLocal() as db:
        user = (
            await db.execute(select(User).where(User.username == reviewer_username))
        ).scalar_one()
        db.add(OrganizationMember(
            organization_id=owner["current_org_id"],
            user_id=user.id,
            role=OrgRole.ADMIN,
            is_default=False,
        ))
        await db.commit()
        token = create_access_token(
            user.id,
            user.username,
            user.role.value,
            owner["current_org_id"],
            token_version=user.token_version,
        )
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_clinical_model_packages_require_authentication(client, needs_auth) -> None:
    response = await client.get("/api/v1/clinical-model-packages")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_clinical_model_package_is_metadata_only_tenant_scoped_and_fail_closed(
    client,
    needs_auth,
) -> None:
    owner = await _register(client, "clinical-model-owner")
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    other = await _register(client, "clinical-model-other")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    rejected_payload = _manifest("0.0.0")
    rejected_payload["artifact_path"] = "E:/iCoDerA/data/train.xlsx"
    rejected = await client.post(
        "/api/v1/clinical-model-packages",
        headers=owner_headers,
        json=rejected_payload,
    )
    assert rejected.status_code == 422

    created = await client.post(
        "/api/v1/clinical-model-packages",
        headers=owner_headers,
        json=_manifest(
            "oof-only",
            license_status="external_review_required",
            redistribution_authorized=False,
            cloud_use_authorized=False,
            hospital_use_authorized=False,
            independent_gold_validated=False,
        ),
    )
    assert created.status_code == 201, created.text
    package = created.json()
    assert package["binary_stored"] is False
    assert package["patient_data_stored"] is False
    assert package["training_data_scope"] == "aggregate_manifest_only"
    serialized = created.text.lower()
    assert "train.xlsx" not in serialized
    assert "artifact_path" not in serialized
    assert "patient_text" not in serialized

    own_list = await client.get(
        "/api/v1/clinical-model-packages", headers=owner_headers,
    )
    assert own_list.status_code == 200
    assert own_list.json()["count"] == 1
    assert own_list.json()["runtime_loading_enabled"] is False
    other_list = await client.get(
        "/api/v1/clinical-model-packages", headers=other_headers,
    )
    assert other_list.status_code == 200
    assert other_list.json()["count"] == 0
    cross_tenant = await client.get(
        f"/api/v1/clinical-model-packages/{package['id']}",
        headers=other_headers,
    )
    assert cross_tenant.status_code == 404


@pytest.mark.asyncio
async def test_four_eyes_activation_versioning_and_audited_rollback(
    client,
    needs_auth,
) -> None:
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog

    owner = await _register(client, "clinical-model-lifecycle")
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    reviewer_headers = await _reviewer_headers(client, owner)

    async def register_and_approve(version: str) -> dict:
        created = await client.post(
            "/api/v1/clinical-model-packages",
            headers=owner_headers,
            json=_manifest(version),
        )
        assert created.status_code == 201, created.text
        row = created.json()
        submitted = await client.post(
            f"/api/v1/clinical-model-packages/{row['id']}/submit",
            headers=owner_headers,
            json={"expected_version": row["record_version"]},
        )
        assert submitted.status_code == 200, submitted.text
        row = submitted.json()
        self_review = await client.post(
            f"/api/v1/clinical-model-packages/{row['id']}/decision",
            headers=owner_headers,
            json={
                "expected_version": row["record_version"],
                "decision": "approve",
                "review_reference_sha256": "4" * 64,
                "reason_code": "evidence_verified",
            },
        )
        assert self_review.status_code == 409
        assert self_review.json()["detail"]["code"] == (
            "CLINICAL_MODEL_PACKAGE_FOUR_EYES_REQUIRED"
        )
        approved = await client.post(
            f"/api/v1/clinical-model-packages/{row['id']}/decision",
            headers=reviewer_headers,
            json={
                "expected_version": row["record_version"],
                "decision": "approve",
                "review_reference_sha256": "4" * 64,
                "reason_code": "evidence_verified",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        return approved.json()

    first = await register_and_approve("1.0.0")
    activated = await client.put(
        "/api/v1/clinical-model-packages/activations/clinical_coding_decision_support",
        headers=owner_headers,
        json={
            "package_id": first["id"],
            "deployment_mode": "hospital_private",
            "expected_version": 0,
            "acknowledge_clinical_governance": True,
        },
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["record_version"] == 1
    assert activated.json()["runtime_loading_enabled"] is False

    stale = await client.put(
        "/api/v1/clinical-model-packages/activations/clinical_coding_decision_support",
        headers=owner_headers,
        json={
            "package_id": first["id"],
            "deployment_mode": "hospital_private",
            "expected_version": 0,
            "acknowledge_clinical_governance": True,
        },
    )
    assert stale.status_code == 409

    second = await register_and_approve("1.1.0")
    switched = await client.put(
        "/api/v1/clinical-model-packages/activations/clinical_coding_decision_support",
        headers=owner_headers,
        json={
            "package_id": second["id"],
            "deployment_mode": "hospital_private",
            "expected_version": 1,
            "acknowledge_clinical_governance": True,
        },
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["previous_package_id"] == first["id"]
    assert switched.json()["record_version"] == 2

    rolled_back = await client.post(
        "/api/v1/clinical-model-packages/activations/clinical_coding_decision_support/rollback",
        headers=owner_headers,
        json={
            "package_id": first["id"],
            "deployment_mode": "hospital_private",
            "expected_version": 2,
            "acknowledge_clinical_governance": True,
        },
    )
    assert rolled_back.status_code == 200, rolled_back.text
    assert rolled_back.json()["package_id"] == first["id"]
    assert rolled_back.json()["previous_package_id"] == second["id"]
    assert rolled_back.json()["record_version"] == 3

    async with AsyncSessionLocal() as db:
        audits = (
            await db.execute(
                select(AuditLog)
                .where(
                    AuditLog.organization_id == owner["current_org_id"],
                    AuditLog.action.in_([
                        "clinical_model_package.activated",
                        "clinical_model_package.rolled_back",
                    ]),
                )
                .order_by(AuditLog.created_at)
            )
        ).scalars().all()
    assert [row.action for row in audits] == [
        "clinical_model_package.activated",
        "clinical_model_package.activated",
        "clinical_model_package.rolled_back",
    ]
    audit_text = str([row.details for row in audits]).lower()
    assert "patient" not in audit_text
    assert "train.xlsx" not in audit_text
    assert "api_key" not in audit_text


@pytest.mark.asyncio
async def test_oof_only_package_cannot_be_activated(client, needs_auth) -> None:
    owner = await _register(client, "clinical-model-oof")
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    reviewer_headers = await _reviewer_headers(client, owner)
    created = await client.post(
        "/api/v1/clinical-model-packages",
        headers=owner_headers,
        json=_manifest(
            "same-workbook-oof",
            license_status="external_review_required",
            redistribution_authorized=False,
            cloud_use_authorized=False,
            hospital_use_authorized=False,
            independent_gold_validated=False,
        ),
    )
    row = created.json()
    submitted = await client.post(
        f"/api/v1/clinical-model-packages/{row['id']}/submit",
        headers=owner_headers,
        json={"expected_version": row["record_version"]},
    )
    row = submitted.json()
    approved = await client.post(
        f"/api/v1/clinical-model-packages/{row['id']}/decision",
        headers=reviewer_headers,
        json={
            "expected_version": row["record_version"],
            "decision": "approve",
            "review_reference_sha256": "5" * 64,
            "reason_code": "evidence_verified",
        },
    )
    assert approved.status_code == 200, approved.text
    blocked = await client.put(
        "/api/v1/clinical-model-packages/activations/clinical_coding_decision_support",
        headers=owner_headers,
        json={
            "package_id": row["id"],
            "deployment_mode": "cloud",
            "expected_version": 0,
            "acknowledge_clinical_governance": True,
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == {
        "code": "CLINICAL_MODEL_PACKAGE_ACTIVATION_BLOCKED",
        "blocking_reasons": [
            "license_not_verified",
            "redistribution_not_authorized",
            "independent_gold_not_validated",
            "hospital_use_not_authorized",
            "cloud_use_not_authorized",
        ],
    }


@pytest.mark.asyncio
async def test_signed_synthetic_bundle_probe_is_metadata_only_and_shadow_bound(
    client,
    needs_auth,
) -> None:
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models.audit_log import AuditLog
    from app.services.clinical_model_bundle import build_canonical_zip

    fixture = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "clinical_model_bundle_v1"
    )
    archive = build_canonical_zip(fixture)
    encoded = base64.b64encode(archive).decode("ascii")
    owner = await _register(client, "clinical-model-shadow")
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    reviewer_headers = await _reviewer_headers(client, owner)
    other = await _register(client, "clinical-model-shadow-other")
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    created = await client.post(
        "/api/v1/clinical-model-packages",
        headers=owner_headers,
        json=_manifest(
            "1.0.0",
            package_key="cn.icoder.synthetic-shadow-fixture",
            package_sha256="5d959101180a47de33df63a94bc7b065ae4da0dd01c7fc46569d9f8223378cb0",
            model_kind="synthetic-shadow-fixture",
            runtime_contract="icoder.clinical-coding-shadow/v1",
            training_dataset_sha256="0" * 64,
            training_case_count=2,
        ),
    )
    assert created.status_code == 201, created.text
    package = created.json()
    submitted = await client.post(
        f"/api/v1/clinical-model-packages/{package['id']}/submit",
        headers=owner_headers,
        json={"expected_version": package["record_version"]},
    )
    package = submitted.json()
    approved = await client.post(
        f"/api/v1/clinical-model-packages/{package['id']}/decision",
        headers=reviewer_headers,
        json={
            "expected_version": package["record_version"],
            "decision": "approve",
            "review_reference_sha256": "6" * 64,
            "reason_code": "evidence_verified",
        },
    )
    assert approved.status_code == 200, approved.text
    package = approved.json()

    original_enabled = settings.ICODER_CLINICAL_MODEL_SYNTHETIC_PROBE_ENABLED
    original_evaluation_enabled = (
        settings.ICODER_CLINICAL_MODEL_SHADOW_EVALUATION_ENABLED
    )
    original_job_enabled = (
        settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED
    )
    original_env = settings.APP_ENV
    try:
        settings.ICODER_CLINICAL_MODEL_SYNTHETIC_PROBE_ENABLED = False
        settings.ICODER_CLINICAL_MODEL_SHADOW_EVALUATION_ENABLED = False
        disabled = await client.post(
            f"/api/v1/clinical-model-packages/{package['id']}/synthetic-artifact-probe",
            headers=owner_headers,
            json={
                "bundle_base64": encoded,
                "expected_package_record_version": package["record_version"],
            },
        )
        assert disabled.status_code == 403

        settings.ICODER_CLINICAL_MODEL_SYNTHETIC_PROBE_ENABLED = True
        settings.APP_ENV = "cloud"
        cloud_denied = await client.post(
            f"/api/v1/clinical-model-packages/{package['id']}/synthetic-artifact-probe",
            headers=owner_headers,
            json={
                "bundle_base64": encoded,
                "expected_package_record_version": package["record_version"],
            },
        )
        assert cloud_denied.status_code == 403

        settings.APP_ENV = "test"
        tampered_archive = bytearray(archive)
        tampered_archive[len(tampered_archive) // 2] ^= 1
        tampered = await client.post(
            f"/api/v1/clinical-model-packages/{package['id']}/synthetic-artifact-probe",
            headers=owner_headers,
            json={
                "bundle_base64": base64.b64encode(tampered_archive).decode("ascii"),
                "expected_package_record_version": package["record_version"],
            },
        )
        assert tampered.status_code == 422

        probed = await client.post(
            f"/api/v1/clinical-model-packages/{package['id']}/synthetic-artifact-probe",
            headers=owner_headers,
            json={
                "bundle_base64": encoded,
                "expected_package_record_version": package["record_version"],
            },
        )
        assert probed.status_code == 201, probed.text
        attestation = probed.json()
        assert attestation["bundle_stored"] is False
        assert attestation["patient_data_stored"] is False
        assert attestation["production_inference_enabled"] is False
        assert attestation["probe_status"] == "passed"
        assert attestation["test_vector_count"] == 2

        idempotent = await client.post(
            f"/api/v1/clinical-model-packages/{package['id']}/synthetic-artifact-probe",
            headers=owner_headers,
            json={
                "bundle_base64": encoded,
                "expected_package_record_version": package["record_version"],
            },
        )
        assert idempotent.status_code == 201
        assert idempotent.json()["id"] == attestation["id"]

        cross_tenant = await client.get(
            f"/api/v1/clinical-model-packages/{package['id']}/artifact-attestations",
            headers=other_headers,
        )
        assert cross_tenant.status_code == 404
        own = await client.get(
            f"/api/v1/clinical-model-packages/{package['id']}/artifact-attestations",
            headers=owner_headers,
        )
        assert own.status_code == 200
        assert own.json()["count"] == 1

        bound = await client.put(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support",
            headers=owner_headers,
            json={
                "attestation_id": attestation["id"],
                "expected_version": 0,
                "acknowledge_shadow_only": True,
            },
        )
        assert bound.status_code == 200, bound.text
        binding = bound.json()
        assert binding["mode"] == "shadow_only"
        assert binding["patient_data_allowed"] is False
        assert binding["runtime_inference_enabled"] is False
        assert binding["predictions_emitted"] is False
        assert binding["record_version"] == 1
        assert binding["evaluation_gate_status"] == "not_evaluated"

        evaluation_disabled = await client.post(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support/synthetic-evaluation",
            headers=owner_headers,
            json={
                "expected_binding_version": 1,
                "bundle_base64": encoded,
                "fault_mode": "none",
                "acknowledge_synthetic_only": True,
            },
        )
        assert evaluation_disabled.status_code == 403

        settings.ICODER_CLINICAL_MODEL_SHADOW_EVALUATION_ENABLED = True
        settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED = True
        evaluated = await client.post(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support/synthetic-evaluation",
            headers=owner_headers,
            json={
                "expected_binding_version": 1,
                "bundle_base64": encoded,
                "fault_mode": "none",
                "acknowledge_synthetic_only": True,
            },
        )
        assert evaluated.status_code == 201, evaluated.text
        passed_evaluation = evaluated.json()
        assert passed_evaluation["result"] == "passed"
        assert passed_evaluation["reason_code"] == "passed"
        assert passed_evaluation["run_count"] == 3
        assert passed_evaluation["vector_observation_count"] == 6
        assert passed_evaluation["rollback_performed"] is False
        assert passed_evaluation["patient_data_used"] is False
        assert passed_evaluation["predictions_emitted"] is False
        assert passed_evaluation["binding_version_before"] == 1
        assert passed_evaluation["binding_version_after"] == 2

        evaluated_binding = await client.get(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support",
            headers=owner_headers,
        )
        assert evaluated_binding.status_code == 200
        assert evaluated_binding.json()["evaluation_gate_status"] == "passed"
        assert evaluated_binding.json()["record_version"] == 2

        stale = await client.put(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support",
            headers=owner_headers,
            json={
                "attestation_id": attestation["id"],
                "expected_version": 0,
                "acknowledge_shadow_only": True,
            },
        )
        assert stale.status_code == 409

        from app.models.clinical_model_package import ClinicalModelArtifactAttestation

        second_attestation_id = str(uuid.uuid4())
        async with AsyncSessionLocal() as db:
            db.add(ClinicalModelArtifactAttestation(
                id=second_attestation_id,
                organization_id=owner["current_org_id"],
                package_id=package["id"],
                bundle_content_sha256="7" * 64,
                manifest_sha256="8" * 64,
                verification_report_sha256="9" * 64,
                trust_key_id="icoder-dev-synthetic-2026-08",
                trust_store_sha256="a" * 64,
                sbom_sha256="b" * 64,
                model_sha256="c" * 64,
                artifact_class="development_synthetic",
                model_format="icoder.synthetic-json/v1",
                runtime_contract="icoder.clinical-coding-shadow/v1",
                verifier_version="1.0.0",
                content_scan_status="clean_development_scanner",
                probe_status="passed",
                test_vector_count=2,
                verified_by_user_id=package["created_by_user_id"],
            ))
            await db.commit()

        switched = await client.put(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support",
            headers=owner_headers,
            json={
                "attestation_id": second_attestation_id,
                "expected_version": 2,
                "acknowledge_shadow_only": True,
            },
        )
        assert switched.status_code == 200, switched.text
        assert switched.json()["record_version"] == 3
        assert switched.json()["evaluation_gate_status"] == "not_evaluated"
        assert switched.json()["previous_attestation_id"] == attestation["id"]

        rolled_back = await client.post(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support/rollback",
            headers=owner_headers,
            json={
                "attestation_id": attestation["id"],
                "expected_version": 3,
                "acknowledge_shadow_only": True,
            },
        )
        assert rolled_back.status_code == 200, rolled_back.text
        assert rolled_back.json()["record_version"] == 4
        assert rolled_back.json()["previous_attestation_id"] == second_attestation_id

        faulted = await client.post(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support/synthetic-evaluation",
            headers=owner_headers,
            json={
                "expected_binding_version": 4,
                "fault_mode": "worker_timeout",
                "acknowledge_synthetic_only": True,
                "acknowledge_fault_injection": True,
            },
        )
        assert faulted.status_code == 201, faulted.text
        stopped_evaluation = faulted.json()
        assert stopped_evaluation["result"] == "stopped"
        assert stopped_evaluation["reason_code"] == "worker_timeout"
        assert stopped_evaluation["rollback_performed"] is True
        assert stopped_evaluation["binding_version_before"] == 4
        assert stopped_evaluation["binding_version_after"] == 5

        evaluations = await client.get(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support/evaluations",
            headers=owner_headers,
        )
        assert evaluations.status_code == 200
        assert evaluations.json()["count"] == 2
        assert {item["result"] for item in evaluations.json()["items"]} == {
            "passed", "stopped",
        }
        cross_tenant_evaluations = await client.get(
            "/api/v1/clinical-model-packages/shadow-bindings/clinical_coding_decision_support/evaluations",
            headers=other_headers,
        )
        assert cross_tenant_evaluations.status_code == 404

        job_path = (
            "/api/v1/clinical-model-packages/shadow-bindings/"
            "clinical_coding_decision_support/evaluation-jobs"
        )
        fault_job_body = {
            "expected_binding_version": 5,
            "fault_mode": "model_hash_mismatch",
            "acknowledge_synthetic_only": True,
            "acknowledge_fault_injection": True,
        }
        queued = await client.post(
            job_path,
            headers={**owner_headers, "Idempotency-Key": "shadow-job-fault-001"},
            json=fault_job_body,
        )
        assert queued.status_code == 202, queued.text
        fault_job = queued.json()
        assert fault_job["status"] == "queued"
        assert fault_job["attempt_count"] == 0
        assert fault_job["lease_active"] is False
        assert fault_job["patient_data_used"] is False

        replayed = await client.post(
            job_path,
            headers={**owner_headers, "Idempotency-Key": "shadow-job-fault-001"},
            json=fault_job_body,
        )
        assert replayed.status_code == 202
        assert replayed.json()["id"] == fault_job["id"]
        reused = await client.post(
            job_path,
            headers={**owner_headers, "Idempotency-Key": "shadow-job-fault-001"},
            json={**fault_job_body, "fault_mode": "malformed_response"},
        )
        assert reused.status_code == 409
        duplicate_active = await client.post(
            job_path,
            headers={**owner_headers, "Idempotency-Key": "shadow-job-fault-002"},
            json=fault_job_body,
        )
        assert duplicate_active.status_code == 409
        cross_tenant_job = await client.get(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{fault_job['id']}",
            headers=other_headers,
        )
        assert cross_tenant_job.status_code == 404

        executed_fault = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{fault_job['id']}/execute",
            headers=owner_headers,
        )
        assert executed_fault.status_code == 200, executed_fault.text
        fault_job = executed_fault.json()
        assert fault_job["status"] == "stopped"
        assert fault_job["attempt_count"] == 1
        assert fault_job["rollback_performed"] is True
        assert fault_job["evaluation_id"]
        assert fault_job["lease_active"] is False

        crash_job_response = await client.post(
            job_path,
            headers={**owner_headers, "Idempotency-Key": "shadow-job-crash-001"},
            json={
                "expected_binding_version": 6,
                "fault_mode": "none",
                "acknowledge_synthetic_only": True,
            },
        )
        assert crash_job_response.status_code == 202, crash_job_response.text
        crash_job_id = crash_job_response.json()["id"]
        from app.models.clinical_model_package import ClinicalModelShadowEvaluationJob
        async with AsyncSessionLocal() as db:
            crash_job_row = await db.get(ClinicalModelShadowEvaluationJob, crash_job_id)
            assert crash_job_row is not None
            crash_job_row.max_attempts = 2
            await db.commit()

        from app.services.clinical_model_shadow_job import (
            claim_next_shadow_job,
            claim_shadow_job,
            finalize_exhausted_shadow_jobs,
            renew_shadow_job_lease,
            settle_claimed_shadow_job,
            summarize_shadow_job_health,
        )
        from app.services.clinical_model_shadow_observation import (
            build_fault_observation,
        )
        from app.services.clinical_model_shadow_scheduler import (
            acquire_shadow_scheduler_lease,
            complete_shadow_scheduler_cycle,
            evaluate_persistent_shadow_alerts,
        )

        lease_now = datetime.now(UTC) + timedelta(seconds=1)
        async with AsyncSessionLocal() as db:
            first_claim = await claim_next_shadow_job(
                db, "worker-a", lease_seconds=5, now=lease_now,
            )
        assert first_claim is not None
        assert first_claim.job_id == crash_job_id
        async with AsyncSessionLocal() as db:
            renewed = await renew_shadow_job_lease(
                db, first_claim, lease_seconds=5,
                now=lease_now + timedelta(seconds=1),
            )
        assert renewed is True
        async with AsyncSessionLocal() as db:
            blocked_claim = await claim_shadow_job(
                db, crash_job_id, "worker-b", lease_seconds=5,
                now=lease_now + timedelta(seconds=4),
            )
        assert blocked_claim is None
        async with AsyncSessionLocal() as db:
            recovered_claim = await claim_shadow_job(
                db, crash_job_id, "worker-b", lease_seconds=5,
                now=lease_now + timedelta(seconds=7),
            )
        assert recovered_claim is not None
        assert recovered_claim.lease_token != first_claim.lease_token
        assert recovered_claim.attempt_count == 2
        stale_observation = build_fault_observation(
            "worker_timeout",
            artifact_sha256=attestation["bundle_content_sha256"],
            model_sha256=attestation["model_sha256"],
        )
        async with AsyncSessionLocal() as db:
            stale_result = await settle_claimed_shadow_job(
                db, first_claim, stale_observation,
                now=lease_now + timedelta(seconds=8),
            )
        assert stale_result is None
        async with AsyncSessionLocal() as db:
            degraded_health = await summarize_shadow_job_health(
                db,
                organization_id=owner["current_org_id"],
                now=lease_now + timedelta(seconds=13),
                queue_alert_count=1,
                max_queue_age_seconds=1,
                expired_lease_alert_count=1,
            )
        assert degraded_health["status"] == "degraded"
        assert degraded_health["expired_lease_count"] == 1
        assert degraded_health["exhausted_count"] == 1
        assert {"expired_leases", "exhausted_jobs"} <= set(
            degraded_health["alert_codes"]
        )
        assert degraded_health["patient_data_used"] is False
        assert degraded_health["identifiers_emitted"] is False
        async with AsyncSessionLocal() as db:
            firing_transitions = await evaluate_persistent_shadow_alerts(
                db,
                now=lease_now + timedelta(seconds=13),
                queue_alert_count=1,
                max_queue_age_seconds=1,
                expired_lease_alert_count=1,
                dead_letter_alert_count=1,
            )
        assert firing_transitions["organizations_evaluated"] >= 1
        assert firing_transitions["alerts_fired"] >= 2
        async with AsyncSessionLocal() as db:
            exhausted = await finalize_exhausted_shadow_jobs(
                db, now=lease_now + timedelta(seconds=13),
            )
        assert exhausted == 1

        from app.main import app
        app.state.rate_limiter_counts.clear()
        dead_letters = await client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/list",
            headers=owner_headers,
        )
        assert dead_letters.status_code == 200, dead_letters.text
        assert dead_letters.json()["count"] == 1
        dead_letter = dead_letters.json()["items"][0]
        assert dead_letter["source_job_id"] == crash_job_id
        assert dead_letter["status"] == "available"
        assert dead_letter["error_code"] == "LEASE_EXPIRED"
        assert dead_letter["patient_data_used"] is False
        assert "replay_idempotency_key" not in dead_letter
        from app.models.clinical_model_package import ClinicalModelShadowDeadLetter
        async with AsyncSessionLocal() as db:
            dead_letter_row = await db.get(ClinicalModelShadowDeadLetter, dead_letter["id"])
            assert dead_letter_row is not None
            original_dead_letter_version = dead_letter_row.binding_record_version
            dead_letter_row.binding_record_version += 1
            await db.commit()
        stale_snapshot_replay = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/{dead_letter['id']}/replay",
            headers={**owner_headers, "Idempotency-Key": "shadow-replay-stale-001"},
        )
        assert stale_snapshot_replay.status_code == 409
        assert stale_snapshot_replay.json()["detail"]["code"] == (
            "CLINICAL_MODEL_SHADOW_DEAD_LETTER_STALE_SNAPSHOT"
        )
        async with AsyncSessionLocal() as db:
            dead_letter_row = await db.get(ClinicalModelShadowDeadLetter, dead_letter["id"])
            assert dead_letter_row is not None
            dead_letter_row.binding_record_version = original_dead_letter_version
            await db.commit()
        other_dead_letters = await client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/list",
            headers=other_headers,
        )
        assert other_dead_letters.status_code == 200
        assert other_dead_letters.json()["count"] == 0
        cross_tenant_replay = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/{dead_letter['id']}/replay",
            headers={**other_headers, "Idempotency-Key": "shadow-replay-other-001"},
        )
        assert cross_tenant_replay.status_code == 404
        replay_response = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/{dead_letter['id']}/replay",
            headers={**owner_headers, "Idempotency-Key": "shadow-replay-owner-001"},
        )
        assert replay_response.status_code == 202, replay_response.text
        replay_job = replay_response.json()
        assert replay_job["status"] == "queued"
        assert replay_job["attempt_count"] == 0
        replay_idempotent = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/{dead_letter['id']}/replay",
            headers={**owner_headers, "Idempotency-Key": "shadow-replay-owner-001"},
        )
        assert replay_idempotent.status_code == 202
        assert replay_idempotent.json()["id"] == replay_job["id"]
        replay_conflict = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/dead-letters/{dead_letter['id']}/replay",
            headers={**owner_headers, "Idempotency-Key": "shadow-replay-owner-002"},
        )
        assert replay_conflict.status_code == 409
        cancelled_dead_letter_replay = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{replay_job['id']}/cancel",
            headers=owner_headers,
            json={"reason": "maintenance"},
        )
        assert cancelled_dead_letter_replay.status_code == 200
        assert cancelled_dead_letter_replay.json()["status"] == "cancelled"

        # This end-to-end contract intentionally exercises more than the
        # default per-minute request budget in one test; reset only the
        # in-memory test limiter before the independent normal-job path.
        from app.main import app
        app.state.rate_limiter_counts.clear()
        normal_job_response = await client.post(
            job_path,
            headers={**owner_headers, "Idempotency-Key": "shadow-job-normal-001"},
            json={
                "expected_binding_version": 6,
                "fault_mode": "none",
                "acknowledge_synthetic_only": True,
            },
        )
        assert normal_job_response.status_code == 202, normal_job_response.text
        normal_job_id = normal_job_response.json()["id"]
        executed_normal = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{normal_job_id}/execute",
            headers=owner_headers,
        )
        assert executed_normal.status_code == 200, executed_normal.text
        assert executed_normal.json()["status"] == "passed"
        assert executed_normal.json()["attempt_count"] == 1
        assert executed_normal.json()["rollback_performed"] is False
        terminal_cancel = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{normal_job_id}/cancel",
            headers=owner_headers,
            json={"reason": "operator_request"},
        )
        assert terminal_cancel.status_code == 409

        running_cancel_response = await client.post(
            job_path,
            headers={**owner_headers, "Idempotency-Key": "shadow-job-cancel-001"},
            json={
                "expected_binding_version": 7,
                "fault_mode": "none",
                "acknowledge_synthetic_only": True,
            },
        )
        assert running_cancel_response.status_code == 202
        running_cancel_id = running_cancel_response.json()["id"]
        async with AsyncSessionLocal() as db:
            cancelled_claim = await claim_shadow_job(
                db,
                running_cancel_id,
                "worker-cancelled",
                lease_seconds=120,
                now=datetime.now(UTC),
            )
        assert cancelled_claim is not None
        running_before_cancel = await client.get(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{running_cancel_id}",
            headers=owner_headers,
        )
        assert running_before_cancel.status_code == 200
        assert running_before_cancel.json()["status"] == "running"
        assert running_before_cancel.json()["lease_active"] is True
        cancelled_running = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{running_cancel_id}/cancel",
            headers=owner_headers,
            json={"reason": "safety_stop"},
        )
        assert cancelled_running.status_code == 200, cancelled_running.text
        assert cancelled_running.json()["status"] == "cancelled"
        assert cancelled_running.json()["cancellation_reason"] == "safety_stop"
        assert cancelled_running.json()["cancelled_by_user_id"] == package[
            "created_by_user_id"
        ]
        assert cancelled_running.json()["cancelled_at"]
        assert cancelled_running.json()["lease_active"] is False
        async with AsyncSessionLocal() as db:
            stale_cancelled_result = await settle_claimed_shadow_job(
                db,
                cancelled_claim,
                stale_observation,
                now=datetime.now(UTC) + timedelta(seconds=1),
            )
        assert stale_cancelled_result is None
        cancelled_replay = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{running_cancel_id}/cancel",
            headers=owner_headers,
            json={"reason": "operator_request"},
        )
        assert cancelled_replay.status_code == 200
        assert cancelled_replay.json()["cancellation_reason"] == "safety_stop"
        cross_tenant_cancel = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{running_cancel_id}/cancel",
            headers=other_headers,
            json={"reason": "operator_request"},
        )
        assert cross_tenant_cancel.status_code == 404

        queued_cancel_response = await client.post(
            job_path,
            headers={**owner_headers, "Idempotency-Key": "shadow-job-cancel-002"},
            json={
                "expected_binding_version": 7,
                "fault_mode": "none",
                "acknowledge_synthetic_only": True,
            },
        )
        assert queued_cancel_response.status_code == 202
        queued_cancel_id = queued_cancel_response.json()["id"]
        cancelled_queued = await client.post(
            f"/api/v1/clinical-model-packages/shadow-evaluation-jobs/{queued_cancel_id}/cancel",
            headers=owner_headers,
            json={"reason": "maintenance"},
        )
        assert cancelled_queued.status_code == 200
        assert cancelled_queued.json()["status"] == "cancelled"
        assert cancelled_queued.json()["attempt_count"] == 0
        assert cancelled_queued.json()["cancellation_reason"] == "maintenance"

        health = await client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/health/summary",
            headers=owner_headers,
        )
        assert health.status_code == 200, health.text
        assert health.json()["status"] == "healthy"
        assert health.json()["status_counts"] == {
            "queued": 0,
            "running": 0,
            "passed": 1,
            "stopped": 1,
            "failed": 1,
            "cancelled": 3,
        }
        assert health.json()["dead_letter_count"] == 0
        assert health.json()["alert_codes"] == []
        assert health.json()["identifiers_emitted"] is False
        other_health = await client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/health/summary",
            headers=other_headers,
        )
        assert other_health.status_code == 200
        assert sum(other_health.json()["status_counts"].values()) == 0
        assert other_health.json()["identifiers_emitted"] is False
        maintenance = await client.post(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/maintenance/run",
            headers=owner_headers,
        )
        assert maintenance.status_code == 200
        assert maintenance.json()["finalized_exhausted_count"] == 0
        assert maintenance.json()["organizations_evaluated"] >= 1
        assert maintenance.json()["identifiers_emitted"] is False

        alerts = await client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/alerts/states",
            headers=owner_headers,
        )
        assert alerts.status_code == 200, alerts.text
        assert alerts.json()["count"] >= 2
        assert {item["state"] for item in alerts.json()["items"]} == {"resolved"}
        assert alerts.json()["identifiers_emitted"] is False
        other_alerts = await client.get(
            "/api/v1/clinical-model-packages/shadow-evaluation-jobs/alerts/states",
            headers=other_headers,
        )
        assert other_alerts.status_code == 200
        assert other_alerts.json()["count"] == 0

        scheduler_now = datetime.now(UTC) + timedelta(minutes=1)
        async with AsyncSessionLocal() as db:
            scheduler_a = await acquire_shadow_scheduler_lease(
                db, owner="scheduler-a", lease_seconds=5, now=scheduler_now,
            )
        assert scheduler_a is not None
        async with AsyncSessionLocal() as db:
            scheduler_blocked = await acquire_shadow_scheduler_lease(
                db,
                owner="scheduler-b",
                lease_seconds=5,
                now=scheduler_now + timedelta(seconds=1),
            )
        assert scheduler_blocked is None
        async with AsyncSessionLocal() as db:
            scheduler_b = await acquire_shadow_scheduler_lease(
                db,
                owner="scheduler-b",
                lease_seconds=5,
                now=scheduler_now + timedelta(seconds=6),
            )
        assert scheduler_b is not None
        assert scheduler_b.token != scheduler_a.token
        assert scheduler_b.generation == scheduler_a.generation + 1
        async with AsyncSessionLocal() as db:
            stale_scheduler_completion = await complete_shadow_scheduler_cycle(
                db,
                scheduler_a,
                succeeded=True,
                now=scheduler_now + timedelta(seconds=7),
            )
        assert stale_scheduler_completion is False
        async with AsyncSessionLocal() as db:
            scheduler_completed = await complete_shadow_scheduler_cycle(
                db,
                scheduler_b,
                succeeded=True,
                now=scheduler_now + timedelta(seconds=7),
            )
        assert scheduler_completed is True

        jobs = await client.get(job_path, headers=owner_headers)
        assert jobs.status_code == 200
        assert jobs.json()["count"] == 6
        assert {item["status"] for item in jobs.json()["items"]} == {
            "passed", "stopped", "failed", "cancelled",
        }
        cross_tenant_jobs = await client.get(job_path, headers=other_headers)
        assert cross_tenant_jobs.status_code == 404
    finally:
        settings.ICODER_CLINICAL_MODEL_SYNTHETIC_PROBE_ENABLED = original_enabled
        settings.ICODER_CLINICAL_MODEL_SHADOW_EVALUATION_ENABLED = (
            original_evaluation_enabled
        )
        settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED = (
            original_job_enabled
        )
        settings.APP_ENV = original_env

    async with AsyncSessionLocal() as db:
        audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.organization_id == owner["current_org_id"],
                    AuditLog.action.in_([
                        "clinical_model_artifact.synthetic_probe_passed",
                        "clinical_model_shadow_binding.updated",
                        "clinical_model_shadow_binding.rolled_back",
                    ]),
                ).order_by(AuditLog.created_at)
            )
        ).scalars().all()
    assert len(audits) == 4
    assert [row.action for row in audits] == [
        "clinical_model_artifact.synthetic_probe_passed",
        "clinical_model_shadow_binding.updated",
        "clinical_model_shadow_binding.updated",
        "clinical_model_shadow_binding.rolled_back",
    ]
    audit_text = str([row.details for row in audits]).lower()
    assert "bundle_base64" not in audit_text
    assert "synthetic-score" not in audit_text
    assert "api_key" not in audit_text

    async with AsyncSessionLocal() as db:
        evaluation_audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.organization_id == owner["current_org_id"],
                    AuditLog.action.in_([
                        "clinical_model_shadow_evaluation.completed",
                        "clinical_model_shadow_binding.auto_rolled_back",
                    ]),
                ).order_by(AuditLog.created_at)
            )
        ).scalars().all()
    assert [row.action for row in evaluation_audits] == [
        "clinical_model_shadow_evaluation.completed",
        "clinical_model_shadow_evaluation.completed",
        "clinical_model_shadow_binding.auto_rolled_back",
    ]
    evaluation_audit_text = str([row.details for row in evaluation_audits]).lower()
    assert "bundle_base64" not in evaluation_audit_text
    assert "patient" not in evaluation_audit_text.replace("patient_data_used", "")
    assert "api_key" not in evaluation_audit_text

    async with AsyncSessionLocal() as db:
        job_audits = (
            await db.execute(
                select(AuditLog).where(
                    AuditLog.organization_id == owner["current_org_id"],
                    AuditLog.action.like("clinical_model_shadow_job.%"),
                ).order_by(AuditLog.created_at)
            )
        ).scalars().all()
    assert {row.action for row in job_audits} >= {
        "clinical_model_shadow_job.queued",
        "clinical_model_shadow_job.claimed",
        "clinical_model_shadow_job.completed",
        "clinical_model_shadow_job.auto_rolled_back",
        "clinical_model_shadow_job.failed",
        "clinical_model_shadow_job.cancelled",
        "clinical_model_shadow_job.dead_lettered",
        "clinical_model_shadow_job.dead_letter_replayed",
    }
    job_audit_text = str([row.details for row in job_audits]).lower()
    assert "idempotency_key" not in job_audit_text
    assert "lease_token" not in job_audit_text
    assert "bundle_base64" not in job_audit_text
    assert "api_key" not in job_audit_text
