"""Metadata-only clinical model package registry and activation controls."""

from __future__ import annotations

import asyncio
import base64
import binascii
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.middleware.audit import log_action
from app.middleware.auth import (
    get_current_organization,
    get_current_user,
    require_org_membership,
    require_org_role,
)
from app.models.clinical_model_package import (
    ClinicalModelActivation,
    ClinicalModelArtifactAttestation,
    ClinicalModelPackage,
    ClinicalModelShadowBinding,
    ClinicalModelShadowAlertState,
    ClinicalModelShadowDeadLetter,
    ClinicalModelShadowEvaluation,
    ClinicalModelShadowEvaluationJob,
)
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.services.clinical_model_package_governance import activation_blockers
from app.services.clinical_model_bundle import (
    ClinicalModelBundleError,
    validate_verification_report,
    verify_bundle_zip_bytes,
)
from app.services.clinical_model_shadow_probe import (
    ClinicalModelShadowProbeError,
    probe_verified_synthetic_bundle,
)
from app.services.clinical_model_shadow_observation import (
    ClinicalModelShadowObservationError,
    build_fault_observation,
    run_verified_shadow_suite,
)
from app.services.clinical_model_shadow_job import (
    cancel_shadow_job,
    claim_shadow_job,
    execute_claimed_repository_shadow_job,
    finalize_exhausted_shadow_jobs,
    replay_shadow_dead_letter,
    summarize_shadow_job_health,
)
from app.services.clinical_model_shadow_observability import get_clinical_shadow_metrics
from app.services.clinical_model_shadow_queue import build_shadow_queue_adapter
from app.services.clinical_model_shadow_scheduler import evaluate_persistent_shadow_alerts


router = APIRouter(
    prefix="/api/v1/clinical-model-packages",
    tags=["clinical-model-packages"],
)

Sha256 = str
UseCase = Literal[
    "clinical_coding_decision_support",
    "clinical_documentation_improvement",
]
DeploymentMode = Literal["development", "hospital_private", "cloud"]
LicenseStatus = Literal[
    "unknown", "external_review_required", "verified", "restricted"
]
PackageStatus = Literal[
    "draft", "submitted", "approved", "active", "retired", "rejected"
]


class ClinicalModelPackageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    package_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    package_version: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._+-]+$")
    package_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    use_case: UseCase
    model_kind: str = Field(min_length=3, max_length=64, pattern=r"^[a-z0-9][a-z0-9._-]+$")
    runtime_contract: str = Field(min_length=3, max_length=96, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/+:-]+$")
    jurisdiction: Literal["CN"] = "CN"
    training_data_scope: Literal["aggregate_manifest_only"] = "aggregate_manifest_only"
    training_dataset_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    training_case_count: int = Field(ge=1, le=100_000_000)
    evaluation_evidence_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    license_status: LicenseStatus = "external_review_required"
    redistribution_authorized: bool = False
    cloud_use_authorized: bool = False
    hospital_use_authorized: bool = False
    independent_gold_validated: bool = False
    independent_reviewer_approved: bool = False


class ClinicalModelPackageTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)


class ClinicalModelPackageDecision(ClinicalModelPackageTransition):
    decision: Literal["approve", "reject"]
    review_reference_sha256: Sha256 = Field(pattern=r"^[0-9a-f]{64}$")
    reason_code: Literal[
        "evidence_verified",
        "evidence_incomplete",
        "license_unverified",
        "clinical_validation_failed",
        "security_review_failed",
    ]


class ClinicalModelActivationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package_id: str = Field(min_length=36, max_length=36)
    deployment_mode: DeploymentMode
    expected_version: int = Field(ge=0)
    acknowledge_clinical_governance: Literal[True]


class ClinicalModelSyntheticArtifactProbeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bundle_base64: str = Field(min_length=4, max_length=11_200_000)
    expected_package_record_version: int = Field(ge=1)


class ClinicalModelShadowBindingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    attestation_id: str = Field(min_length=36, max_length=36)
    expected_version: int = Field(ge=0)
    acknowledge_shadow_only: Literal[True]


class ClinicalModelShadowEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_binding_version: int = Field(ge=1)
    bundle_base64: str | None = Field(default=None, max_length=11_200_000)
    fault_mode: Literal[
        "none", "worker_timeout", "malformed_response", "model_hash_mismatch"
    ] = "none"
    acknowledge_synthetic_only: Literal[True]
    acknowledge_fault_injection: bool = False


class ClinicalModelShadowJobCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_binding_version: int = Field(ge=1)
    fault_mode: Literal[
        "none", "worker_timeout", "malformed_response", "model_hash_mismatch"
    ] = "none"
    acknowledge_synthetic_only: Literal[True]
    acknowledge_fault_injection: bool = False


class ClinicalModelShadowJobCancelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: Literal["operator_request", "maintenance", "safety_stop"]


class ClinicalModelPackageResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    package_key: str
    package_version: str
    package_sha256: str
    use_case: UseCase
    model_kind: str
    runtime_contract: str
    jurisdiction: Literal["CN"]
    training_data_scope: Literal["aggregate_manifest_only"]
    training_dataset_sha256: str
    training_case_count: int
    evaluation_evidence_sha256: str
    license_status: LicenseStatus
    redistribution_authorized: bool
    cloud_use_authorized: bool
    hospital_use_authorized: bool
    independent_gold_validated: bool
    independent_reviewer_approved: bool
    status: PackageStatus
    record_version: int
    created_by_user_id: str
    submitted_by_user_id: str | None
    reviewed_by_user_id: str | None
    review_reference_sha256: str | None
    decision_reason_code: str | None
    created_at: datetime
    updated_at: datetime
    submitted_at: datetime | None
    reviewed_at: datetime | None
    binary_stored: Literal[False] = False
    patient_data_stored: Literal[False] = False


class ClinicalModelPackageListResponse(BaseModel):
    items: list[ClinicalModelPackageResponse]
    count: int
    governance_scope: Literal["metadata_and_evidence_digests_only"] = (
        "metadata_and_evidence_digests_only"
    )
    runtime_loading_enabled: Literal[False] = False


class ClinicalModelActivationResponse(BaseModel):
    id: str
    use_case: UseCase
    package_id: str
    previous_package_id: str | None
    deployment_mode: DeploymentMode
    record_version: int
    activated_by_user_id: str
    created_at: datetime
    updated_at: datetime
    activation_blockers: list[str] = Field(default_factory=list)
    runtime_loading_enabled: Literal[False] = False


class ClinicalModelArtifactAttestationResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    package_id: str
    bundle_content_sha256: str
    manifest_sha256: str
    verification_report_sha256: str
    trust_key_id: str
    trust_store_sha256: str
    sbom_sha256: str
    model_sha256: str
    artifact_class: Literal["development_synthetic"]
    model_format: Literal["icoder.synthetic-json/v1"]
    runtime_contract: str
    verifier_version: str
    content_scan_status: Literal["clean_development_scanner"]
    probe_status: Literal["passed"]
    test_vector_count: int
    verified_by_user_id: str
    created_at: datetime
    bundle_stored: Literal[False] = False
    patient_data_stored: Literal[False] = False
    production_inference_enabled: Literal[False] = False


class ClinicalModelArtifactAttestationListResponse(BaseModel):
    items: list[ClinicalModelArtifactAttestationResponse]
    count: int
    metadata_only: Literal[True] = True


class ClinicalModelShadowBindingResponse(BaseModel):
    id: str
    use_case: UseCase
    package_id: str
    attestation_id: str
    previous_package_id: str | None
    previous_attestation_id: str | None
    mode: Literal["shadow_only"]
    record_version: int
    bound_by_user_id: str
    created_at: datetime
    updated_at: datetime
    evaluation_gate_status: Literal["not_evaluated", "passed", "stopped"]
    last_evaluation_id: str | None
    last_evaluated_at: datetime | None
    patient_data_allowed: Literal[False] = False
    runtime_inference_enabled: Literal[False] = False
    predictions_emitted: Literal[False] = False


class ClinicalModelShadowEvaluationResponse(BaseModel):
    id: str
    binding_id: str
    use_case: UseCase
    package_id: str
    attestation_id: str
    source: Literal["repository_synthetic", "synthetic_fault_injection"]
    suite_id: str
    suite_sha256: str
    artifact_sha256: str
    observation_report_sha256: str
    result: Literal["passed", "stopped"]
    reason_code: str
    fault_mode: Literal[
        "none", "worker_timeout", "malformed_response", "model_hash_mismatch"
    ]
    run_count: int
    vector_observation_count: int
    success_count: int
    mismatch_count: int
    error_count: int
    latency_p50_ms: int
    latency_p95_ms: int
    artifact_reverified: bool
    rollback_performed: bool
    binding_version_before: int
    binding_version_after: int
    evaluated_by_user_id: str
    created_at: datetime
    aggregate_only: Literal[True] = True
    patient_data_used: Literal[False] = False
    raw_input_stored: Literal[False] = False
    predictions_emitted: Literal[False] = False
    network_used: Literal[False] = False
    production_inference_enabled: Literal[False] = False


class ClinicalModelShadowEvaluationListResponse(BaseModel):
    items: list[ClinicalModelShadowEvaluationResponse]
    count: int
    aggregate_only: Literal[True] = True


class ClinicalModelShadowJobResponse(BaseModel):
    id: str
    binding_id: str
    use_case: UseCase
    package_id: str
    attestation_id: str
    binding_record_version: int
    request_sha256: str
    fault_mode: Literal[
        "none", "worker_timeout", "malformed_response", "model_hash_mismatch"
    ]
    status: Literal["queued", "running", "passed", "stopped", "failed", "cancelled"]
    attempt_count: int
    max_attempts: int
    evaluation_id: str | None
    error_code: str | None
    rollback_performed: bool
    created_by_user_id: str
    started_at: datetime | None
    completed_at: datetime | None
    cancellation_reason: Literal[
        "operator_request", "maintenance", "safety_stop"
    ] | None
    cancelled_at: datetime | None
    cancelled_by_user_id: str | None
    created_at: datetime
    updated_at: datetime
    lease_active: bool
    artifact_source: Literal["repository_synthetic_fixture"] = (
        "repository_synthetic_fixture"
    )
    aggregate_only: Literal[True] = True
    patient_data_used: Literal[False] = False
    raw_input_stored: Literal[False] = False
    predictions_emitted: Literal[False] = False
    network_used: Literal[False] = False
    production_inference_enabled: Literal[False] = False


class ClinicalModelShadowJobListResponse(BaseModel):
    items: list[ClinicalModelShadowJobResponse]
    count: int
    aggregate_only: Literal[True] = True


class ClinicalModelShadowJobHealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    status_counts: dict[str, int]
    due_queued_count: int
    active_lease_count: int
    expired_lease_count: int
    exhausted_count: int
    dead_letter_count: int
    oldest_due_age_seconds: int
    alert_codes: list[Literal[
        "queue_backlog", "queue_age_exceeded", "expired_leases", "exhausted_jobs",
        "dead_letter_backlog",
    ]]
    evaluated_at: datetime
    aggregate_only: Literal[True] = True
    patient_data_used: Literal[False] = False
    identifiers_emitted: Literal[False] = False


class ClinicalModelShadowJobMaintenanceResponse(BaseModel):
    finalized_exhausted_count: int
    organizations_evaluated: int = 0
    alerts_fired: int = 0
    alerts_resolved: int = 0
    aggregate_only: Literal[True] = True
    patient_data_used: Literal[False] = False
    identifiers_emitted: Literal[False] = False


class ClinicalModelShadowDeadLetterResponse(BaseModel):
    id: str
    source_job_id: str
    binding_id: str
    use_case: UseCase
    package_id: str
    attestation_id: str
    binding_record_version: int
    error_code: str
    attempt_count: int
    max_attempts: int
    status: Literal["available", "replayed", "discarded"]
    replayed_job_id: str | None
    replayed_at: datetime | None
    replayed_by_user_id: str | None
    created_at: datetime
    updated_at: datetime
    aggregate_only: Literal[True] = True
    patient_data_used: Literal[False] = False
    raw_input_stored: Literal[False] = False


class ClinicalModelShadowDeadLetterListResponse(BaseModel):
    items: list[ClinicalModelShadowDeadLetterResponse]
    count: int
    aggregate_only: Literal[True] = True


class ClinicalModelShadowAlertStateResponse(BaseModel):
    alert_code: Literal[
        "queue_backlog", "queue_age_exceeded", "expired_leases",
        "exhausted_jobs", "dead_letter_backlog",
    ]
    state: Literal["firing", "resolved"]
    occurrence_count: int
    opened_at: datetime
    last_evaluated_at: datetime
    last_transition_at: datetime
    resolved_at: datetime | None


class ClinicalModelShadowAlertStateListResponse(BaseModel):
    items: list[ClinicalModelShadowAlertStateResponse]
    count: int
    aggregate_only: Literal[True] = True
    patient_data_used: Literal[False] = False
    identifiers_emitted: Literal[False] = False


def _package_response(row: ClinicalModelPackage) -> ClinicalModelPackageResponse:
    return ClinicalModelPackageResponse.model_validate(
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
    )


def _activation_response(row: ClinicalModelActivation) -> ClinicalModelActivationResponse:
    return ClinicalModelActivationResponse.model_validate(
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
    )


def _attestation_response(
    row: ClinicalModelArtifactAttestation,
) -> ClinicalModelArtifactAttestationResponse:
    return ClinicalModelArtifactAttestationResponse.model_validate(
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
    )


def _shadow_binding_response(
    row: ClinicalModelShadowBinding,
) -> ClinicalModelShadowBindingResponse:
    return ClinicalModelShadowBindingResponse.model_validate(
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
    )


def _shadow_evaluation_response(
    row: ClinicalModelShadowEvaluation,
) -> ClinicalModelShadowEvaluationResponse:
    return ClinicalModelShadowEvaluationResponse.model_validate(
        {column.name: getattr(row, column.name) for column in row.__table__.columns}
    )


def _shadow_job_response(
    row: ClinicalModelShadowEvaluationJob,
) -> ClinicalModelShadowJobResponse:
    values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    expires_at = row.lease_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    values["lease_active"] = (
        row.status == "running"
        and row.lease_token is not None
        and expires_at is not None
        and expires_at > datetime.now(UTC)
    )
    return ClinicalModelShadowJobResponse.model_validate(values)


def _shadow_dead_letter_response(
    row: ClinicalModelShadowDeadLetter,
) -> ClinicalModelShadowDeadLetterResponse:
    values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
    values.pop("organization_id", None)
    values.pop("replay_idempotency_key", None)
    return ClinicalModelShadowDeadLetterResponse.model_validate(values)


async def _signal_shadow_job(job_id: str) -> None:
    adapter = None
    try:
        adapter = build_shadow_queue_adapter(
            backend=settings.ICODER_CLINICAL_MODEL_SHADOW_QUEUE_BACKEND,
            redis_url=settings.ICODER_CLINICAL_MODEL_SHADOW_QUEUE_REDIS_URL,
            allow_insecure_redis=(
                settings.ICODER_CLINICAL_MODEL_SHADOW_QUEUE_ALLOW_INSECURE_REDIS
            ),
        )
        await adapter.notify(job_id)
        get_clinical_shadow_metrics().record("queue_signal_sent")
    except Exception:
        # The database is authoritative. A signal failure increases latency but
        # must not roll back or lose an already committed durable job.
        get_clinical_shadow_metrics().record("queue_signal_failed")
    finally:
        if adapter is not None:
            await adapter.close()


def _shadow_job_request_sha256(
    use_case: UseCase,
    body: ClinicalModelShadowJobCreateRequest,
) -> str:
    payload = json.dumps(
        {
            "use_case": use_case,
            "expected_binding_version": body.expected_binding_version,
            "fault_mode": body.fault_mode,
            "acknowledge_synthetic_only": body.acknowledge_synthetic_only,
            "acknowledge_fault_injection": body.acknowledge_fault_injection,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


async def _locked_package(
    db: AsyncSession,
    *,
    organization_id: str,
    package_id: str,
) -> ClinicalModelPackage:
    row = (
        await db.execute(
            select(ClinicalModelPackage)
            .where(
                ClinicalModelPackage.id == package_id,
                ClinicalModelPackage.organization_id == organization_id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_PACKAGE_NOT_FOUND"},
        )
    return row


def _check_version(actual: int, expected: int) -> None:
    if actual != expected:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_PACKAGE_VERSION_CONFLICT",
                "current_version": actual,
            },
        )


def _decode_canonical_base64(value: str) -> bytes:
    try:
        content = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "CLINICAL_MODEL_BUNDLE_BASE64_INVALID"},
        ) from exc
    if base64.b64encode(content).decode("ascii") != value:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "CLINICAL_MODEL_BUNDLE_BASE64_NOT_CANONICAL"},
        )
    return content


@router.get("", response_model=ClinicalModelPackageListResponse)
async def list_clinical_model_packages(
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelPackageListResponse:
    response.headers["Cache-Control"] = "no-store"
    rows = (
        await db.execute(
            select(ClinicalModelPackage)
            .where(ClinicalModelPackage.organization_id == current_org.id)
            .order_by(ClinicalModelPackage.created_at.desc())
        )
    ).scalars().all()
    items = [_package_response(row) for row in rows]
    return ClinicalModelPackageListResponse(items=items, count=len(items))


@router.get(
    "/{package_id}/artifact-attestations",
    response_model=ClinicalModelArtifactAttestationListResponse,
)
async def list_clinical_model_artifact_attestations(
    package_id: str,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelArtifactAttestationListResponse:
    response.headers["Cache-Control"] = "no-store"
    await _locked_package(db, organization_id=current_org.id, package_id=package_id)
    rows = (
        await db.execute(
            select(ClinicalModelArtifactAttestation)
            .where(
                ClinicalModelArtifactAttestation.organization_id == current_org.id,
                ClinicalModelArtifactAttestation.package_id == package_id,
            )
            .order_by(ClinicalModelArtifactAttestation.created_at.desc())
        )
    ).scalars().all()
    items = [_attestation_response(row) for row in rows]
    return ClinicalModelArtifactAttestationListResponse(items=items, count=len(items))


@router.post(
    "/{package_id}/synthetic-artifact-probe",
    status_code=status.HTTP_201_CREATED,
    response_model=ClinicalModelArtifactAttestationResponse,
)
async def probe_clinical_model_synthetic_artifact(
    package_id: str,
    body: ClinicalModelSyntheticArtifactProbeRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelArtifactAttestationResponse:
    response.headers["Cache-Control"] = "no-store"
    app_env = (settings.APP_ENV or "").strip().casefold()
    if (
        not settings.ICODER_CLINICAL_MODEL_SYNTHETIC_PROBE_ENABLED
        or app_env not in {"local", "development", "dev", "test"}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CLINICAL_MODEL_SYNTHETIC_PROBE_DISABLED"},
        )
    package = await _locked_package(
        db, organization_id=current_org.id, package_id=package_id,
    )
    _check_version(package.record_version, body.expected_package_record_version)
    if package.model_kind != "synthetic-shadow-fixture":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SYNTHETIC_PACKAGE_REQUIRED"},
        )
    archive = _decode_canonical_base64(body.bundle_base64)
    try:
        verified = await asyncio.to_thread(
            verify_bundle_zip_bytes,
            archive,
            environment="test" if app_env == "test" else "development",
        )
        validate_verification_report(verified.report)
        probe = await asyncio.to_thread(probe_verified_synthetic_bundle, verified)
    except (ClinicalModelBundleError, ClinicalModelShadowProbeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": str(exc) or "CLINICAL_MODEL_SYNTHETIC_PROBE_FAILED"},
        ) from exc
    report = verified.report
    expected = {
        "bundle_id": package.package_key,
        "bundle_version": package.package_version,
        "bundle_content_sha256": package.package_sha256,
        "use_case": package.use_case,
        "runtime_contract": package.runtime_contract,
        "training_dataset_sha256": package.training_dataset_sha256,
        "training_case_count": package.training_case_count,
    }
    mismatches = sorted(
        field for field, value in expected.items() if report.get(field) != value
    )
    if mismatches:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_BUNDLE_PACKAGE_MISMATCH",
                "mismatched_fields": mismatches,
            },
        )
    existing = (
        await db.execute(
            select(ClinicalModelArtifactAttestation).where(
                ClinicalModelArtifactAttestation.organization_id == current_org.id,
                ClinicalModelArtifactAttestation.package_id == package.id,
                ClinicalModelArtifactAttestation.bundle_content_sha256
                == report["bundle_content_sha256"],
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return _attestation_response(existing)
    row = ClinicalModelArtifactAttestation(
        id=str(uuid.uuid4()),
        organization_id=current_org.id,
        package_id=package.id,
        bundle_content_sha256=report["bundle_content_sha256"],
        manifest_sha256=report["manifest_sha256"],
        verification_report_sha256=report["verification_report_sha256"],
        trust_key_id=report["trust_key_id"],
        trust_store_sha256=report["trust_store_sha256"],
        sbom_sha256=report["sbom_sha256"],
        model_sha256=probe["model_sha256"],
        artifact_class=report["artifact_class"],
        model_format=report["model_format"],
        runtime_contract=report["runtime_contract"],
        verifier_version=report["verifier_version"],
        content_scan_status=report["content_scan_status"],
        probe_status="passed",
        test_vector_count=probe["test_vector_count"],
        verified_by_user_id=current_user.id,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_ARTIFACT_ATTESTATION_CONFLICT"},
        ) from exc
    await log_action(
        db, current_user.id, current_user.username,
        "clinical_model_artifact.synthetic_probe_passed",
        "clinical_model_artifact_attestation", row.id,
        details={
            "package_id": package.id,
            "bundle_content_sha256": row.bundle_content_sha256,
            "manifest_sha256": row.manifest_sha256,
            "verification_report_sha256": row.verification_report_sha256,
            "model_sha256": row.model_sha256,
            "test_vector_count": row.test_vector_count,
            "bundle_stored": False,
            "patient_data_used": False,
            "runtime_inference_enabled": False,
        },
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return _attestation_response(row)


@router.get(
    "/shadow-bindings/{use_case}",
    response_model=ClinicalModelShadowBindingResponse,
)
async def get_clinical_model_shadow_binding(
    use_case: UseCase,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowBindingResponse:
    response.headers["Cache-Control"] = "no-store"
    row = (
        await db.execute(
            select(ClinicalModelShadowBinding).where(
                ClinicalModelShadowBinding.organization_id == current_org.id,
                ClinicalModelShadowBinding.use_case == use_case,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_SHADOW_BINDING_NOT_FOUND"},
        )
    return _shadow_binding_response(row)


@router.get(
    "/shadow-bindings/{use_case}/evaluations",
    response_model=ClinicalModelShadowEvaluationListResponse,
)
async def list_clinical_model_shadow_evaluations(
    use_case: UseCase,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowEvaluationListResponse:
    response.headers["Cache-Control"] = "no-store"
    binding = (
        await db.execute(
            select(ClinicalModelShadowBinding).where(
                ClinicalModelShadowBinding.organization_id == current_org.id,
                ClinicalModelShadowBinding.use_case == use_case,
            )
        )
    ).scalar_one_or_none()
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_SHADOW_BINDING_NOT_FOUND"},
        )
    rows = (
        await db.execute(
            select(ClinicalModelShadowEvaluation)
            .where(
                ClinicalModelShadowEvaluation.organization_id == current_org.id,
                ClinicalModelShadowEvaluation.binding_id == binding.id,
            )
            .order_by(ClinicalModelShadowEvaluation.created_at.desc())
        )
    ).scalars().all()
    items = [_shadow_evaluation_response(row) for row in rows]
    return ClinicalModelShadowEvaluationListResponse(items=items, count=len(items))


@router.get("/activations/{use_case}", response_model=ClinicalModelActivationResponse)
async def get_clinical_model_activation(
    use_case: UseCase,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelActivationResponse:
    response.headers["Cache-Control"] = "no-store"
    row = (
        await db.execute(
            select(ClinicalModelActivation).where(
                ClinicalModelActivation.organization_id == current_org.id,
                ClinicalModelActivation.use_case == use_case,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_ACTIVATION_NOT_FOUND"},
        )
    return _activation_response(row)


@router.get("/{package_id}", response_model=ClinicalModelPackageResponse)
async def get_clinical_model_package(
    package_id: str,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelPackageResponse:
    response.headers["Cache-Control"] = "no-store"
    row = await _locked_package(
        db, organization_id=current_org.id, package_id=package_id,
    )
    return _package_response(row)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ClinicalModelPackageResponse)
async def create_clinical_model_package(
    body: ClinicalModelPackageCreate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelPackageResponse:
    response.headers["Cache-Control"] = "no-store"
    row = ClinicalModelPackage(
        id=str(uuid.uuid4()),
        organization_id=current_org.id,
        created_by_user_id=current_user.id,
        **body.model_dump(),
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_PACKAGE_VERSION_ALREADY_EXISTS"},
        ) from exc
    await log_action(
        db,
        current_user.id,
        current_user.username,
        "clinical_model_package.created",
        "clinical_model_package",
        row.id,
        details={
            "package_key": row.package_key,
            "package_version": row.package_version,
            "package_sha256": row.package_sha256,
            "use_case": row.use_case,
            "training_case_count": row.training_case_count,
            "metadata_only": True,
        },
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return _package_response(row)


@router.post("/{package_id}/submit", response_model=ClinicalModelPackageResponse)
async def submit_clinical_model_package(
    package_id: str,
    body: ClinicalModelPackageTransition,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelPackageResponse:
    response.headers["Cache-Control"] = "no-store"
    row = await _locked_package(db, organization_id=current_org.id, package_id=package_id)
    _check_version(row.record_version, body.expected_version)
    if row.status not in {"draft", "rejected"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_PACKAGE_NOT_SUBMITTABLE"},
        )
    now = datetime.now(UTC)
    row.status = "submitted"
    row.record_version += 1
    row.submitted_by_user_id = current_user.id
    row.submitted_at = now
    row.reviewed_by_user_id = None
    row.reviewed_at = None
    row.review_reference_sha256 = None
    row.decision_reason_code = None
    await log_action(
        db, current_user.id, current_user.username,
        "clinical_model_package.submitted", "clinical_model_package", row.id,
        details={"record_version": row.record_version, "metadata_only": True},
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return _package_response(row)


@router.post("/{package_id}/decision", response_model=ClinicalModelPackageResponse)
async def decide_clinical_model_package(
    package_id: str,
    body: ClinicalModelPackageDecision,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelPackageResponse:
    response.headers["Cache-Control"] = "no-store"
    row = await _locked_package(db, organization_id=current_org.id, package_id=package_id)
    _check_version(row.record_version, body.expected_version)
    if row.status != "submitted":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_PACKAGE_NOT_REVIEWABLE"},
        )
    if current_user.id == row.created_by_user_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_PACKAGE_FOUR_EYES_REQUIRED"},
        )
    if body.decision == "approve" and (
        body.reason_code != "evidence_verified"
        or not row.independent_reviewer_approved
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_PACKAGE_APPROVAL_EVIDENCE_INCOMPLETE"},
        )
    row.status = "approved" if body.decision == "approve" else "rejected"
    row.record_version += 1
    row.reviewed_by_user_id = current_user.id
    row.reviewed_at = datetime.now(UTC)
    row.review_reference_sha256 = body.review_reference_sha256
    row.decision_reason_code = body.reason_code
    await log_action(
        db, current_user.id, current_user.username,
        (
            "clinical_model_package.approved"
            if body.decision == "approve"
            else "clinical_model_package.rejected"
        ),
        "clinical_model_package", row.id,
        details={
            "decision": body.decision,
            "reason_code": body.reason_code,
            "review_reference_sha256": body.review_reference_sha256,
            "record_version": row.record_version,
            "four_eyes": True,
        },
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(row)
    return _package_response(row)


async def _activate(
    *,
    use_case: UseCase,
    body: ClinicalModelActivationUpdate,
    request: Request,
    current_user: User,
    current_org: Organization,
    db: AsyncSession,
    audit_action: str,
) -> ClinicalModelActivationResponse:
    # Serialize activation creation/switching at the tenant boundary.  This
    # also closes the first-write race before an activation row exists.
    await db.execute(
        select(Organization)
        .where(Organization.id == current_org.id)
        .with_for_update()
    )
    package = await _locked_package(
        db, organization_id=current_org.id, package_id=body.package_id,
    )
    if package.use_case != use_case:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_PACKAGE_USE_CASE_MISMATCH"},
        )
    blockers = activation_blockers(package, deployment_mode=body.deployment_mode)
    if blockers:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_PACKAGE_ACTIVATION_BLOCKED",
                "blocking_reasons": blockers,
            },
        )
    activation = (
        await db.execute(
            select(ClinicalModelActivation)
            .where(
                ClinicalModelActivation.organization_id == current_org.id,
                ClinicalModelActivation.use_case == use_case,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    current_version = activation.record_version if activation is not None else 0
    if current_version != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_ACTIVATION_VERSION_CONFLICT",
                "current_version": current_version,
            },
        )
    if audit_action == "clinical_model_package.rolled_back" and (
        activation is None or activation.previous_package_id != package.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_ROLLBACK_TARGET_NOT_PREVIOUS"},
        )
    previous_id = activation.package_id if activation is not None else None
    if activation is None:
        activation = ClinicalModelActivation(
            id=str(uuid.uuid4()),
            organization_id=current_org.id,
            use_case=use_case,
            package_id=package.id,
            previous_package_id=None,
            deployment_mode=body.deployment_mode,
            record_version=1,
            activated_by_user_id=current_user.id,
        )
        db.add(activation)
    else:
        if activation.package_id == package.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "CLINICAL_MODEL_PACKAGE_ALREADY_ACTIVE"},
            )
        old_package = await _locked_package(
            db, organization_id=current_org.id, package_id=activation.package_id,
        )
        if old_package.status == "active":
            old_package.status = "approved"
            old_package.record_version += 1
        activation.previous_package_id = activation.package_id
        activation.package_id = package.id
        activation.deployment_mode = body.deployment_mode
        activation.record_version += 1
        activation.activated_by_user_id = current_user.id
    package.status = "active"
    package.record_version += 1
    await log_action(
        db, current_user.id, current_user.username,
        audit_action, "clinical_model_activation", activation.id,
        details={
            "use_case": use_case,
            "package_id": package.id,
            "previous_package_id": previous_id,
            "deployment_mode": body.deployment_mode,
            "activation_version": activation.record_version,
            "runtime_loading_enabled": False,
            "governance_acknowledged": True,
        },
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(activation)
    return _activation_response(activation)


@router.put("/activations/{use_case}", response_model=ClinicalModelActivationResponse)
async def activate_clinical_model_package(
    use_case: UseCase,
    body: ClinicalModelActivationUpdate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelActivationResponse:
    response.headers["Cache-Control"] = "no-store"
    return await _activate(
        use_case=use_case, body=body, request=request, current_user=current_user,
        current_org=current_org, db=db, audit_action="clinical_model_package.activated",
    )


@router.post("/activations/{use_case}/rollback", response_model=ClinicalModelActivationResponse)
async def rollback_clinical_model_package(
    use_case: UseCase,
    body: ClinicalModelActivationUpdate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelActivationResponse:
    response.headers["Cache-Control"] = "no-store"
    return await _activate(
        use_case=use_case, body=body, request=request, current_user=current_user,
        current_org=current_org, db=db, audit_action="clinical_model_package.rolled_back",
    )


async def _bind_shadow_attestation(
    *,
    use_case: UseCase,
    body: ClinicalModelShadowBindingUpdate,
    request: Request,
    current_user: User,
    current_org: Organization,
    db: AsyncSession,
    rollback: bool,
) -> ClinicalModelShadowBindingResponse:
    await db.execute(
        select(Organization)
        .where(Organization.id == current_org.id)
        .with_for_update()
    )
    attestation = (
        await db.execute(
            select(ClinicalModelArtifactAttestation)
            .where(
                ClinicalModelArtifactAttestation.id == body.attestation_id,
                ClinicalModelArtifactAttestation.organization_id == current_org.id,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if attestation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_ARTIFACT_ATTESTATION_NOT_FOUND"},
        )
    package = await _locked_package(
        db,
        organization_id=current_org.id,
        package_id=attestation.package_id,
    )
    if package.use_case != use_case:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_PACKAGE_USE_CASE_MISMATCH"},
        )
    if (
        package.status not in {"approved", "active"}
        or package.model_kind != "synthetic-shadow-fixture"
        or attestation.runtime_contract != package.runtime_contract
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_BINDING_BLOCKED"},
        )
    binding = (
        await db.execute(
            select(ClinicalModelShadowBinding)
            .where(
                ClinicalModelShadowBinding.organization_id == current_org.id,
                ClinicalModelShadowBinding.use_case == use_case,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    current_version = binding.record_version if binding is not None else 0
    if current_version != body.expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_SHADOW_BINDING_VERSION_CONFLICT",
                "current_version": current_version,
            },
        )
    if rollback and (
        binding is None
        or binding.previous_attestation_id != attestation.id
        or binding.previous_package_id != package.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_ROLLBACK_TARGET_NOT_PREVIOUS"},
        )
    previous_package_id = binding.package_id if binding is not None else None
    previous_attestation_id = binding.attestation_id if binding is not None else None
    if binding is None:
        binding = ClinicalModelShadowBinding(
            id=str(uuid.uuid4()),
            organization_id=current_org.id,
            use_case=use_case,
            package_id=package.id,
            attestation_id=attestation.id,
            previous_package_id=None,
            previous_attestation_id=None,
            mode="shadow_only",
            record_version=1,
            bound_by_user_id=current_user.id,
            evaluation_gate_status="not_evaluated",
            last_evaluation_id=None,
            last_evaluated_at=None,
        )
        db.add(binding)
    else:
        if binding.attestation_id == attestation.id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "CLINICAL_MODEL_ATTESTATION_ALREADY_SHADOW_BOUND"},
            )
        binding.previous_package_id = binding.package_id
        binding.previous_attestation_id = binding.attestation_id
        binding.package_id = package.id
        binding.attestation_id = attestation.id
        binding.record_version += 1
        binding.bound_by_user_id = current_user.id
        binding.evaluation_gate_status = "not_evaluated"
        binding.last_evaluation_id = None
        binding.last_evaluated_at = None
    await log_action(
        db, current_user.id, current_user.username,
        (
            "clinical_model_shadow_binding.rolled_back"
            if rollback
            else "clinical_model_shadow_binding.updated"
        ),
        "clinical_model_shadow_binding", binding.id,
        details={
            "use_case": use_case,
            "package_id": package.id,
            "attestation_id": attestation.id,
            "previous_package_id": previous_package_id,
            "previous_attestation_id": previous_attestation_id,
            "binding_version": binding.record_version,
            "mode": "shadow_only",
            "patient_data_allowed": False,
            "runtime_inference_enabled": False,
            "predictions_emitted": False,
        },
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.commit()
    await db.refresh(binding)
    return _shadow_binding_response(binding)


@router.put(
    "/shadow-bindings/{use_case}",
    response_model=ClinicalModelShadowBindingResponse,
)
async def bind_clinical_model_shadow_attestation(
    use_case: UseCase,
    body: ClinicalModelShadowBindingUpdate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowBindingResponse:
    response.headers["Cache-Control"] = "no-store"
    return await _bind_shadow_attestation(
        use_case=use_case,
        body=body,
        request=request,
        current_user=current_user,
        current_org=current_org,
        db=db,
        rollback=False,
    )


@router.post(
    "/shadow-bindings/{use_case}/rollback",
    response_model=ClinicalModelShadowBindingResponse,
)
async def rollback_clinical_model_shadow_binding(
    use_case: UseCase,
    body: ClinicalModelShadowBindingUpdate,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowBindingResponse:
    response.headers["Cache-Control"] = "no-store"
    return await _bind_shadow_attestation(
        use_case=use_case,
        body=body,
        request=request,
        current_user=current_user,
        current_org=current_org,
        db=db,
        rollback=True,
    )


@router.post(
    "/shadow-bindings/{use_case}/synthetic-evaluation",
    status_code=status.HTTP_201_CREATED,
    response_model=ClinicalModelShadowEvaluationResponse,
)
async def evaluate_clinical_model_shadow_binding(
    use_case: UseCase,
    body: ClinicalModelShadowEvaluationRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowEvaluationResponse:
    response.headers["Cache-Control"] = "no-store"
    app_env = (settings.APP_ENV or "").strip().casefold()
    if (
        not settings.ICODER_CLINICAL_MODEL_SHADOW_EVALUATION_ENABLED
        or app_env not in {"local", "development", "dev", "test"}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CLINICAL_MODEL_SHADOW_EVALUATION_DISABLED"},
        )
    if body.fault_mode == "none":
        if body.bundle_base64 is None or body.acknowledge_fault_injection:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": "CLINICAL_MODEL_SHADOW_EVALUATION_REQUEST_INVALID"},
            )
    elif body.bundle_base64 is not None or not body.acknowledge_fault_injection:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "CLINICAL_MODEL_SHADOW_FAULT_ACK_REQUIRED"},
        )

    org_id = current_org.id
    user_id = current_user.id
    username = current_user.username
    binding = (
        await db.execute(
            select(ClinicalModelShadowBinding).where(
                ClinicalModelShadowBinding.organization_id == org_id,
                ClinicalModelShadowBinding.use_case == use_case,
            )
        )
    ).scalar_one_or_none()
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_SHADOW_BINDING_NOT_FOUND"},
        )
    if binding.record_version != body.expected_binding_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_SHADOW_BINDING_VERSION_CONFLICT",
                "current_version": binding.record_version,
            },
        )
    attestation = (
        await db.execute(
            select(ClinicalModelArtifactAttestation).where(
                ClinicalModelArtifactAttestation.id == binding.attestation_id,
                ClinicalModelArtifactAttestation.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    package = (
        await db.execute(
            select(ClinicalModelPackage).where(
                ClinicalModelPackage.id == binding.package_id,
                ClinicalModelPackage.organization_id == org_id,
            )
        )
    ).scalar_one_or_none()
    if (
        attestation is None
        or package is None
        or attestation.package_id != package.id
        or package.use_case != use_case
        or package.status not in {"approved", "active"}
        or package.model_kind != "synthetic-shadow-fixture"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_EVALUATION_BLOCKED"},
        )
    snapshot = {
        "binding_id": binding.id,
        "binding_version": binding.record_version,
        "package_id": package.id,
        "attestation_id": attestation.id,
        "previous_package_id": binding.previous_package_id,
        "previous_attestation_id": binding.previous_attestation_id,
        "package_key": package.package_key,
        "package_version": package.package_version,
        "package_sha256": package.package_sha256,
        "runtime_contract": package.runtime_contract,
        "training_dataset_sha256": package.training_dataset_sha256,
        "training_case_count": package.training_case_count,
        "bundle_content_sha256": attestation.bundle_content_sha256,
        "manifest_sha256": attestation.manifest_sha256,
        "verification_report_sha256": attestation.verification_report_sha256,
        "trust_key_id": attestation.trust_key_id,
        "trust_store_sha256": attestation.trust_store_sha256,
        "sbom_sha256": attestation.sbom_sha256,
        "model_sha256": attestation.model_sha256,
    }
    # Release the read transaction while the bounded subprocess suite runs.
    await db.rollback()

    if body.fault_mode == "none":
        archive = _decode_canonical_base64(body.bundle_base64 or "")
        try:
            verified = await asyncio.to_thread(
                verify_bundle_zip_bytes,
                archive,
                environment="test" if app_env == "test" else "development",
            )
            validate_verification_report(verified.report)
            observation = await asyncio.to_thread(run_verified_shadow_suite, verified)
        except (
            ClinicalModelBundleError,
            ClinicalModelShadowProbeError,
            ClinicalModelShadowObservationError,
        ) as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"code": str(exc) or "CLINICAL_MODEL_SHADOW_EVALUATION_FAILED"},
            ) from exc
        report = verified.report
        expected_report = {
            "bundle_id": snapshot["package_key"],
            "bundle_version": snapshot["package_version"],
            "bundle_content_sha256": snapshot["package_sha256"],
            "use_case": use_case,
            "runtime_contract": snapshot["runtime_contract"],
            "training_dataset_sha256": snapshot["training_dataset_sha256"],
            "training_case_count": snapshot["training_case_count"],
            "manifest_sha256": snapshot["manifest_sha256"],
            "verification_report_sha256": snapshot["verification_report_sha256"],
            "trust_key_id": snapshot["trust_key_id"],
            "trust_store_sha256": snapshot["trust_store_sha256"],
            "sbom_sha256": snapshot["sbom_sha256"],
        }
        mismatches = sorted(
            field for field, value in expected_report.items() if report.get(field) != value
        )
        if (
            mismatches
            or observation["artifact_sha256"] != snapshot["bundle_content_sha256"]
            or observation["model_sha256"] != snapshot["model_sha256"]
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "CLINICAL_MODEL_SHADOW_ATTESTATION_MISMATCH",
                    "mismatched_fields": mismatches,
                },
            )
    else:
        observation = build_fault_observation(
            body.fault_mode,
            artifact_sha256=str(snapshot["bundle_content_sha256"]),
            model_sha256=str(snapshot["model_sha256"]),
        )

    await db.execute(
        select(Organization).where(Organization.id == org_id).with_for_update()
    )
    binding = (
        await db.execute(
            select(ClinicalModelShadowBinding)
            .where(
                ClinicalModelShadowBinding.id == snapshot["binding_id"],
                ClinicalModelShadowBinding.organization_id == org_id,
                ClinicalModelShadowBinding.use_case == use_case,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if (
        binding is None
        or binding.record_version != snapshot["binding_version"]
        or binding.package_id != snapshot["package_id"]
        or binding.attestation_id != snapshot["attestation_id"]
    ):
        current_version = binding.record_version if binding is not None else None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_SHADOW_BINDING_CHANGED_DURING_EVALUATION",
                "current_version": current_version,
            },
        )

    before_version = binding.record_version
    rollback_performed = False
    if observation["result"] == "passed":
        binding.evaluation_gate_status = "passed"
    else:
        binding.evaluation_gate_status = "stopped"
        if binding.previous_package_id and binding.previous_attestation_id:
            target_attestation = (
                await db.execute(
                    select(ClinicalModelArtifactAttestation).where(
                        ClinicalModelArtifactAttestation.id
                        == binding.previous_attestation_id,
                        ClinicalModelArtifactAttestation.organization_id == org_id,
                        ClinicalModelArtifactAttestation.package_id
                        == binding.previous_package_id,
                    )
                )
            ).scalar_one_or_none()
            target_package = (
                await db.execute(
                    select(ClinicalModelPackage).where(
                        ClinicalModelPackage.id == binding.previous_package_id,
                        ClinicalModelPackage.organization_id == org_id,
                        ClinicalModelPackage.use_case == use_case,
                        ClinicalModelPackage.status.in_(["approved", "active"]),
                    )
                )
            ).scalar_one_or_none()
            if target_attestation is not None and target_package is not None:
                failed_package_id = binding.package_id
                failed_attestation_id = binding.attestation_id
                binding.package_id = target_package.id
                binding.attestation_id = target_attestation.id
                binding.previous_package_id = failed_package_id
                binding.previous_attestation_id = failed_attestation_id
                binding.evaluation_gate_status = "not_evaluated"
                rollback_performed = True
    binding.record_version += 1
    binding.bound_by_user_id = user_id
    evaluated_at = datetime.now(UTC)
    evaluation_id = str(uuid.uuid4())
    binding.last_evaluation_id = evaluation_id
    binding.last_evaluated_at = evaluated_at
    evaluation = ClinicalModelShadowEvaluation(
        id=evaluation_id,
        organization_id=org_id,
        binding_id=binding.id,
        use_case=use_case,
        package_id=str(snapshot["package_id"]),
        attestation_id=str(snapshot["attestation_id"]),
        source=observation["source"],
        suite_id=observation["suite_id"],
        suite_sha256=observation["suite_sha256"],
        artifact_sha256=observation["artifact_sha256"],
        observation_report_sha256=observation["observation_report_sha256"],
        result=observation["result"],
        reason_code=observation["reason_code"],
        fault_mode=observation["fault_mode"],
        run_count=observation["run_count"],
        vector_observation_count=observation["vector_observation_count"],
        success_count=observation["success_count"],
        mismatch_count=observation["mismatch_count"],
        error_count=observation["error_count"],
        latency_p50_ms=observation["latency_p50_ms"],
        latency_p95_ms=observation["latency_p95_ms"],
        artifact_reverified=observation["artifact_reverified"],
        rollback_performed=rollback_performed,
        binding_version_before=before_version,
        binding_version_after=binding.record_version,
        evaluated_by_user_id=user_id,
        created_at=evaluated_at,
    )
    db.add(evaluation)
    await log_action(
        db, user_id, username,
        "clinical_model_shadow_evaluation.completed",
        "clinical_model_shadow_evaluation", evaluation.id,
        details={
            "binding_id": binding.id,
            "use_case": use_case,
            "package_id": snapshot["package_id"],
            "attestation_id": snapshot["attestation_id"],
            "suite_sha256": evaluation.suite_sha256,
            "observation_report_sha256": evaluation.observation_report_sha256,
            "result": evaluation.result,
            "reason_code": evaluation.reason_code,
            "fault_mode": evaluation.fault_mode,
            "run_count": evaluation.run_count,
            "vector_observation_count": evaluation.vector_observation_count,
            "error_count": evaluation.error_count,
            "mismatch_count": evaluation.mismatch_count,
            "rollback_performed": rollback_performed,
            "binding_version_after": binding.record_version,
            "aggregate_only": True,
            "patient_data_used": False,
            "raw_input_stored": False,
            "predictions_emitted": False,
            "network_used": False,
            "production_inference_enabled": False,
        },
        organization_id=org_id,
        ip_address=request.client.host if request.client else None,
    )
    if rollback_performed:
        await log_action(
            db, user_id, username,
            "clinical_model_shadow_binding.auto_rolled_back",
            "clinical_model_shadow_binding", binding.id,
            details={
                "use_case": use_case,
                "failed_package_id": snapshot["package_id"],
                "failed_attestation_id": snapshot["attestation_id"],
                "restored_package_id": binding.package_id,
                "restored_attestation_id": binding.attestation_id,
                "evaluation_id": evaluation.id,
                "reason_code": evaluation.reason_code,
                "binding_version_after": binding.record_version,
                "aggregate_only": True,
                "patient_data_used": False,
                "predictions_emitted": False,
                "production_inference_enabled": False,
            },
            organization_id=org_id,
            ip_address=request.client.host if request.client else None,
        )
    await db.commit()
    await db.refresh(evaluation)
    return _shadow_evaluation_response(evaluation)


@router.post(
    "/shadow-bindings/{use_case}/evaluation-jobs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ClinicalModelShadowJobResponse,
)
async def create_clinical_model_shadow_job(
    use_case: UseCase,
    body: ClinicalModelShadowJobCreateRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowJobResponse:
    response.headers["Cache-Control"] = "no-store"
    app_env = (settings.APP_ENV or "").strip().casefold()
    if (
        not settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED
        or app_env not in {"local", "development", "dev", "test"}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_SIMULATION_DISABLED"},
        )
    key = idempotency_key.strip()
    if (
        len(key) < 8
        or len(key) > 128
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", key) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_IDEMPOTENCY_INVALID"},
        )
    if (
        (body.fault_mode == "none" and body.acknowledge_fault_injection)
        or (body.fault_mode != "none" and not body.acknowledge_fault_injection)
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_FAULT_ACK_INVALID"},
        )
    request_sha256 = _shadow_job_request_sha256(use_case, body)
    existing = (
        await db.execute(
            select(ClinicalModelShadowEvaluationJob).where(
                ClinicalModelShadowEvaluationJob.organization_id == current_org.id,
                ClinicalModelShadowEvaluationJob.idempotency_key == key,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.request_sha256 != request_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "CLINICAL_MODEL_SHADOW_JOB_IDEMPOTENCY_REUSED"},
            )
        return _shadow_job_response(existing)

    binding = (
        await db.execute(
            select(ClinicalModelShadowBinding).where(
                ClinicalModelShadowBinding.organization_id == current_org.id,
                ClinicalModelShadowBinding.use_case == use_case,
            )
        )
    ).scalar_one_or_none()
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_SHADOW_BINDING_NOT_FOUND"},
        )
    if binding.record_version != body.expected_binding_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_SHADOW_BINDING_VERSION_CONFLICT",
                "current_version": binding.record_version,
            },
        )
    active = (
        await db.execute(
            select(ClinicalModelShadowEvaluationJob).where(
                ClinicalModelShadowEvaluationJob.organization_id == current_org.id,
                ClinicalModelShadowEvaluationJob.active_binding_id == binding.id,
            )
        )
    ).scalar_one_or_none()
    if active is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CLINICAL_MODEL_SHADOW_JOB_ALREADY_ACTIVE",
                "active_job_id": active.id,
            },
        )
    package = await db.get(ClinicalModelPackage, binding.package_id)
    attestation = await db.get(
        ClinicalModelArtifactAttestation, binding.attestation_id,
    )
    if (
        package is None
        or attestation is None
        or package.organization_id != current_org.id
        or attestation.organization_id != current_org.id
        or attestation.package_id != package.id
        or package.use_case != use_case
        or package.status not in {"approved", "active"}
        or package.model_kind != "synthetic-shadow-fixture"
        or package.package_key != "cn.icoder.synthetic-shadow-fixture"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_ARTIFACT_BLOCKED"},
        )
    created_at = datetime.now(UTC)
    row = ClinicalModelShadowEvaluationJob(
        id=str(uuid.uuid4()),
        organization_id=current_org.id,
        binding_id=binding.id,
        active_binding_id=binding.id,
        use_case=use_case,
        package_id=package.id,
        attestation_id=attestation.id,
        binding_record_version=binding.record_version,
        idempotency_key=key,
        request_sha256=request_sha256,
        fault_mode=body.fault_mode,
        status="queued",
        attempt_count=0,
        max_attempts=3,
        next_attempt_at=created_at,
        rollback_performed=False,
        created_by_user_id=current_user.id,
        created_at=created_at,
        updated_at=created_at,
    )
    db.add(row)
    await log_action(
        db, current_user.id, current_user.username,
        "clinical_model_shadow_job.queued",
        "clinical_model_shadow_evaluation_job", row.id,
        details={
            "binding_id": binding.id,
            "use_case": use_case,
            "package_id": package.id,
            "attestation_id": attestation.id,
            "binding_record_version": binding.record_version,
            "request_sha256": request_sha256,
            "fault_mode": body.fault_mode,
            "max_attempts": 3,
            "artifact_source": "repository_synthetic_fixture",
            "aggregate_only": True,
            "patient_data_used": False,
            "raw_input_stored": False,
            "predictions_emitted": False,
            "network_used": False,
            "production_inference_enabled": False,
        },
        organization_id=current_org.id,
        ip_address=request.client.host if request.client else None,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        concurrent = (
            await db.execute(
                select(ClinicalModelShadowEvaluationJob).where(
                    ClinicalModelShadowEvaluationJob.organization_id == current_org.id,
                    ClinicalModelShadowEvaluationJob.idempotency_key == key,
                )
            )
        ).scalar_one_or_none()
        if concurrent is not None and concurrent.request_sha256 == request_sha256:
            return _shadow_job_response(concurrent)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_CONFLICT"},
        ) from exc
    await db.refresh(row)
    get_clinical_shadow_metrics().record("queued")
    await _signal_shadow_job(row.id)
    return _shadow_job_response(row)


@router.get(
    "/shadow-bindings/{use_case}/evaluation-jobs",
    response_model=ClinicalModelShadowJobListResponse,
)
async def list_clinical_model_shadow_jobs(
    use_case: UseCase,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowJobListResponse:
    response.headers["Cache-Control"] = "no-store"
    binding = (
        await db.execute(
            select(ClinicalModelShadowBinding).where(
                ClinicalModelShadowBinding.organization_id == current_org.id,
                ClinicalModelShadowBinding.use_case == use_case,
            )
        )
    ).scalar_one_or_none()
    if binding is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_SHADOW_BINDING_NOT_FOUND"},
        )
    rows = list((await db.scalars(
        select(ClinicalModelShadowEvaluationJob)
        .where(
            ClinicalModelShadowEvaluationJob.organization_id == current_org.id,
            ClinicalModelShadowEvaluationJob.binding_id == binding.id,
        )
        .order_by(ClinicalModelShadowEvaluationJob.created_at.desc())
        .limit(100)
    )).all())
    return ClinicalModelShadowJobListResponse(
        items=[_shadow_job_response(row) for row in rows],
        count=len(rows),
    )


@router.get(
    "/shadow-evaluation-jobs/{job_id}",
    response_model=ClinicalModelShadowJobResponse,
)
async def get_clinical_model_shadow_job(
    job_id: str,
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowJobResponse:
    response.headers["Cache-Control"] = "no-store"
    row = (
        await db.execute(
            select(ClinicalModelShadowEvaluationJob).where(
                ClinicalModelShadowEvaluationJob.id == job_id,
                ClinicalModelShadowEvaluationJob.organization_id == current_org.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_NOT_FOUND"},
        )
    return _shadow_job_response(row)


@router.post(
    "/shadow-evaluation-jobs/{job_id}/execute",
    response_model=ClinicalModelShadowJobResponse,
)
async def execute_clinical_model_shadow_job_simulation(
    job_id: str,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowJobResponse:
    response.headers["Cache-Control"] = "no-store"
    app_env = (settings.APP_ENV or "").strip().casefold()
    if (
        not settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED
        or app_env not in {"local", "development", "dev", "test"}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_SIMULATION_DISABLED"},
        )
    row = (
        await db.execute(
            select(ClinicalModelShadowEvaluationJob).where(
                ClinicalModelShadowEvaluationJob.id == job_id,
                ClinicalModelShadowEvaluationJob.organization_id == current_org.id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_NOT_FOUND"},
        )
    if row.status in {"passed", "stopped", "failed", "cancelled"}:
        return _shadow_job_response(row)
    current_user_id = current_user.id
    current_org_id = current_org.id
    await db.rollback()
    worker_id = f"api-{current_user_id[:24]}-{uuid.uuid4().hex[:8]}"
    claim = await claim_shadow_job(
        db, job_id, worker_id, lease_seconds=120,
    )
    if claim is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_LEASE_UNAVAILABLE"},
        )
    await execute_claimed_repository_shadow_job(claim)
    await db.rollback()
    refreshed = (
        await db.execute(
            select(ClinicalModelShadowEvaluationJob)
            .where(
                ClinicalModelShadowEvaluationJob.id == job_id,
                ClinicalModelShadowEvaluationJob.organization_id == current_org_id,
            )
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    return _shadow_job_response(refreshed)


@router.post(
    "/shadow-evaluation-jobs/{job_id}/cancel",
    response_model=ClinicalModelShadowJobResponse,
)
async def cancel_clinical_model_shadow_job(
    job_id: str,
    body: ClinicalModelShadowJobCancelRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowJobResponse:
    response.headers["Cache-Control"] = "no-store"
    outcome, row = await cancel_shadow_job(
        db,
        organization_id=current_org.id,
        job_id=job_id,
        cancelled_by_user_id=current_user.id,
        cancelled_by_username=current_user.username,
        reason=body.reason,
    )
    if outcome == "not_found":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_NOT_FOUND"},
        )
    if outcome == "terminal":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_ALREADY_TERMINAL"},
        )
    if outcome == "race_lost" or row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_CANCEL_RACE_LOST"},
        )
    return _shadow_job_response(row)


@router.get(
    "/shadow-evaluation-jobs/health/summary",
    response_model=ClinicalModelShadowJobHealthResponse,
)
async def get_clinical_model_shadow_job_health(
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowJobHealthResponse:
    response.headers["Cache-Control"] = "no-store"
    values = await summarize_shadow_job_health(
        db,
        organization_id=current_org.id,
        queue_alert_count=settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_QUEUE_ALERT_COUNT,
        max_queue_age_seconds=(
            settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_MAX_QUEUE_AGE_SECONDS
        ),
        expired_lease_alert_count=(
            settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_EXPIRED_LEASE_ALERT_COUNT
        ),
        dead_letter_alert_count=(
            settings.ICODER_CLINICAL_MODEL_SHADOW_DEAD_LETTER_ALERT_COUNT
        ),
    )
    return ClinicalModelShadowJobHealthResponse.model_validate(values)


@router.post(
    "/shadow-evaluation-jobs/maintenance/run",
    response_model=ClinicalModelShadowJobMaintenanceResponse,
)
async def maintain_clinical_model_shadow_jobs(
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowJobMaintenanceResponse:
    response.headers["Cache-Control"] = "no-store"
    app_env = (settings.APP_ENV or "").strip().casefold()
    if (
        not settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED
        or app_env not in {"local", "development", "dev", "test"}
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_MAINTENANCE_DISABLED"},
        )
    finalized = await finalize_exhausted_shadow_jobs(
        db,
        organization_id=current_org.id,
        limit=100,
    )
    transitions = await evaluate_persistent_shadow_alerts(
        db,
        queue_alert_count=settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_QUEUE_ALERT_COUNT,
        max_queue_age_seconds=(
            settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_MAX_QUEUE_AGE_SECONDS
        ),
        expired_lease_alert_count=(
            settings.ICODER_CLINICAL_MODEL_SHADOW_JOB_EXPIRED_LEASE_ALERT_COUNT
        ),
        dead_letter_alert_count=(
            settings.ICODER_CLINICAL_MODEL_SHADOW_DEAD_LETTER_ALERT_COUNT
        ),
    )
    return ClinicalModelShadowJobMaintenanceResponse(
        finalized_exhausted_count=finalized,
        organizations_evaluated=transitions["organizations_evaluated"],
        alerts_fired=transitions["alerts_fired"],
        alerts_resolved=transitions["alerts_resolved"],
    )


@router.get(
    "/shadow-evaluation-jobs/dead-letters/list",
    response_model=ClinicalModelShadowDeadLetterListResponse,
)
async def list_clinical_model_shadow_dead_letters(
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowDeadLetterListResponse:
    response.headers["Cache-Control"] = "no-store"
    rows = list((await db.scalars(
        select(ClinicalModelShadowDeadLetter)
        .where(ClinicalModelShadowDeadLetter.organization_id == current_org.id)
        .order_by(ClinicalModelShadowDeadLetter.created_at.desc())
        .limit(100)
    )).all())
    return ClinicalModelShadowDeadLetterListResponse(
        items=[_shadow_dead_letter_response(row) for row in rows],
        count=len(rows),
    )


@router.post(
    "/shadow-evaluation-jobs/dead-letters/{dead_letter_id}/replay",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ClinicalModelShadowJobResponse,
)
async def replay_clinical_model_shadow_dead_letter(
    dead_letter_id: str,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_role("owner", "admin")),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowJobResponse:
    response.headers["Cache-Control"] = "no-store"
    key = idempotency_key.strip()
    if (
        len(key) < 8
        or len(key) > 128
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", key) is None
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "CLINICAL_MODEL_SHADOW_JOB_IDEMPOTENCY_INVALID"},
        )
    outcome, row = await replay_shadow_dead_letter(
        db,
        organization_id=current_org.id,
        dead_letter_id=dead_letter_id,
        idempotency_key=key,
        replayed_by_user_id=current_user.id,
        replayed_by_username=current_user.username,
    )
    errors = {
        "not_found": (404, "CLINICAL_MODEL_SHADOW_DEAD_LETTER_NOT_FOUND"),
        "not_available": (409, "CLINICAL_MODEL_SHADOW_DEAD_LETTER_NOT_AVAILABLE"),
        "stale_snapshot": (409, "CLINICAL_MODEL_SHADOW_DEAD_LETTER_STALE_SNAPSHOT"),
        "active_conflict": (409, "CLINICAL_MODEL_SHADOW_JOB_ALREADY_ACTIVE"),
        "idempotency_conflict": (409, "CLINICAL_MODEL_SHADOW_JOB_IDEMPOTENCY_REUSED"),
        "race_lost": (409, "CLINICAL_MODEL_SHADOW_DEAD_LETTER_REPLAY_RACE_LOST"),
    }
    if outcome in errors:
        http_status, code = errors[outcome]
        raise HTTPException(status_code=http_status, detail={"code": code})
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CLINICAL_MODEL_SHADOW_DEAD_LETTER_REPLAY_RACE_LOST"},
        )
    if outcome == "replayed":
        await _signal_shadow_job(row.id)
    return _shadow_job_response(row)


@router.get(
    "/shadow-evaluation-jobs/alerts/states",
    response_model=ClinicalModelShadowAlertStateListResponse,
)
async def list_clinical_model_shadow_alert_states(
    response: Response,
    _current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(require_org_membership),
    db: AsyncSession = Depends(get_db),
) -> ClinicalModelShadowAlertStateListResponse:
    response.headers["Cache-Control"] = "no-store"
    rows = list((await db.scalars(
        select(ClinicalModelShadowAlertState)
        .where(ClinicalModelShadowAlertState.organization_id == current_org.id)
        .order_by(ClinicalModelShadowAlertState.alert_code)
    )).all())
    return ClinicalModelShadowAlertStateListResponse(
        items=[ClinicalModelShadowAlertStateResponse.model_validate({
            "alert_code": row.alert_code,
            "state": row.state,
            "occurrence_count": row.occurrence_count,
            "opened_at": row.opened_at,
            "last_evaluated_at": row.last_evaluated_at,
            "last_transition_at": row.last_transition_at,
            "resolved_at": row.resolved_at,
        }) for row in rows],
        count=len(rows),
    )


__all__ = ["router"]
