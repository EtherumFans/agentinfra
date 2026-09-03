"""Organization-scoped governance records for immutable clinical model packages.

These rows deliberately contain metadata and evidence digests only.  Model
binaries, training rows, prompts, patient text and credentials must never be
stored in this control-plane table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


CLINICAL_MODEL_PACKAGE_STATUS_VALUES = (
    "draft",
    "submitted",
    "approved",
    "active",
    "retired",
    "rejected",
)
CLINICAL_MODEL_USE_CASE_VALUES = (
    "clinical_coding_decision_support",
    "clinical_documentation_improvement",
)
CLINICAL_MODEL_DEPLOYMENT_MODE_VALUES = (
    "development",
    "hospital_private",
    "cloud",
)
CLINICAL_MODEL_SHADOW_GATE_STATUS_VALUES = (
    "not_evaluated",
    "passed",
    "stopped",
)
CLINICAL_MODEL_SHADOW_FAULT_MODE_VALUES = (
    "none",
    "worker_timeout",
    "malformed_response",
    "model_hash_mismatch",
)
CLINICAL_MODEL_SHADOW_JOB_STATUS_VALUES = (
    "queued",
    "running",
    "passed",
    "stopped",
    "failed",
    "cancelled",
)
CLINICAL_MODEL_SHADOW_JOB_CANCELLATION_REASON_VALUES = (
    "operator_request",
    "maintenance",
    "safety_stop",
)
CLINICAL_MODEL_SHADOW_DEAD_LETTER_STATUS_VALUES = (
    "available",
    "replayed",
    "discarded",
)
CLINICAL_MODEL_SHADOW_ALERT_STATE_VALUES = (
    "firing",
    "resolved",
)


class ClinicalModelPackage(Base):
    __tablename__ = "clinical_model_packages"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "package_key",
            "package_version",
            name="uq_clinical_model_package_org_key_version",
        ),
        CheckConstraint(
            "status IN ('draft','submitted','approved','active','retired','rejected')",
            name="ck_clinical_model_package_status",
        ),
        CheckConstraint(
            "use_case IN ('clinical_coding_decision_support','clinical_documentation_improvement')",
            name="ck_clinical_model_package_use_case",
        ),
        CheckConstraint(
            "jurisdiction = 'CN'",
            name="ck_clinical_model_package_jurisdiction",
        ),
        CheckConstraint(
            "training_data_scope = 'aggregate_manifest_only'",
            name="ck_clinical_model_training_scope",
        ),
        CheckConstraint(
            "license_status IN ('unknown','external_review_required','verified','restricted')",
            name="ck_clinical_model_license_status",
        ),
        Index(
            "ix_clinical_model_packages_org_use_status",
            "organization_id",
            "use_case",
            "status",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    package_key: Mapped[str] = mapped_column(String(64), nullable=False)
    package_version: Mapped[str] = mapped_column(String(64), nullable=False)
    package_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    use_case: Mapped[str] = mapped_column(String(64), nullable=False)
    model_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_contract: Mapped[str] = mapped_column(String(96), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(
        String(8), nullable=False, default="CN", server_default="CN",
    )
    training_data_scope: Mapped[str] = mapped_column(
        String(32), nullable=False, default="aggregate_manifest_only",
        server_default="aggregate_manifest_only",
    )
    training_dataset_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    training_case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluation_evidence_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    license_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="external_review_required",
        server_default="external_review_required",
    )
    redistribution_authorized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    cloud_use_authorized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    hospital_use_authorized: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    independent_gold_validated: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    independent_reviewer_approved: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="draft", server_default="draft",
    )
    record_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    submitted_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    reviewed_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    review_reference_sha256: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    decision_reason_code: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class ClinicalModelActivation(Base):
    __tablename__ = "clinical_model_activations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "use_case",
            name="uq_clinical_model_activation_org_use_case",
        ),
        CheckConstraint(
            "use_case IN ('clinical_coding_decision_support','clinical_documentation_improvement')",
            name="ck_clinical_model_activation_use_case",
        ),
        CheckConstraint(
            "deployment_mode IN ('development','hospital_private','cloud')",
            name="ck_clinical_model_activation_deployment_mode",
        ),
        Index(
            "ix_clinical_model_activations_org_package",
            "organization_id",
            "package_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    use_case: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_packages.id"), nullable=False,
    )
    previous_package_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("clinical_model_packages.id"), nullable=True,
    )
    deployment_mode: Mapped[str] = mapped_column(String(24), nullable=False)
    record_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
    )
    activated_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class ClinicalModelArtifactAttestation(Base):
    """Aggregate result of one transient, server-side synthetic bundle probe."""

    __tablename__ = "clinical_model_artifact_attestations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "package_id", "bundle_content_sha256",
            name="uq_clinical_model_artifact_attestation_digest",
        ),
        CheckConstraint(
            "artifact_class = 'development_synthetic'",
            name="ck_clinical_model_artifact_class",
        ),
        CheckConstraint(
            "model_format = 'icoder.synthetic-json/v1'",
            name="ck_clinical_model_artifact_format",
        ),
        CheckConstraint(
            "content_scan_status = 'clean_development_scanner'",
            name="ck_clinical_model_artifact_scan_status",
        ),
        CheckConstraint(
            "probe_status = 'passed'",
            name="ck_clinical_model_artifact_probe_status",
        ),
        Index(
            "ix_clinical_model_artifact_attestations_org_package",
            "organization_id", "package_id", "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_packages.id"), nullable=False,
    )
    bundle_content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    verification_report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    trust_key_id: Mapped[str] = mapped_column(String(96), nullable=False)
    trust_store_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    sbom_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_class: Mapped[str] = mapped_column(String(32), nullable=False)
    model_format: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_contract: Mapped[str] = mapped_column(String(96), nullable=False)
    verifier_version: Mapped[str] = mapped_column(String(24), nullable=False)
    content_scan_status: Mapped[str] = mapped_column(String(40), nullable=False)
    probe_status: Mapped[str] = mapped_column(String(16), nullable=False)
    test_vector_count: Mapped[int] = mapped_column(Integer, nullable=False)
    verified_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class ClinicalModelShadowBinding(Base):
    """Tenant selection that is structurally unable to serve inference."""

    __tablename__ = "clinical_model_shadow_bindings"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "use_case",
            name="uq_clinical_model_shadow_binding_org_use_case",
        ),
        CheckConstraint(
            "use_case IN ('clinical_coding_decision_support','clinical_documentation_improvement')",
            name="ck_clinical_model_shadow_binding_use_case",
        ),
        CheckConstraint(
            "mode = 'shadow_only'",
            name="ck_clinical_model_shadow_binding_mode",
        ),
        CheckConstraint(
            "evaluation_gate_status IN ('not_evaluated','passed','stopped')",
            name="ck_clinical_model_shadow_binding_evaluation_gate",
        ),
        Index(
            "ix_clinical_model_shadow_bindings_org_package",
            "organization_id", "package_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    use_case: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_packages.id"), nullable=False,
    )
    attestation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_artifact_attestations.id"), nullable=False,
    )
    previous_package_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("clinical_model_packages.id"), nullable=True,
    )
    previous_attestation_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("clinical_model_artifact_attestations.id"), nullable=True,
    )
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="shadow_only", server_default="shadow_only",
    )
    record_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
    )
    bound_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    evaluation_gate_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_evaluated",
        server_default="not_evaluated",
    )
    last_evaluation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class ClinicalModelShadowEvaluation(Base):
    """Aggregate-only observation of a repository synthetic shadow suite."""

    __tablename__ = "clinical_model_shadow_evaluations"
    __table_args__ = (
        CheckConstraint(
            "source IN ('repository_synthetic','synthetic_fault_injection')",
            name="ck_clinical_model_shadow_evaluation_source",
        ),
        CheckConstraint(
            "result IN ('passed','stopped')",
            name="ck_clinical_model_shadow_evaluation_result",
        ),
        CheckConstraint(
            "fault_mode IN ('none','worker_timeout','malformed_response','model_hash_mismatch')",
            name="ck_clinical_model_shadow_evaluation_fault_mode",
        ),
        Index(
            "ix_clinical_model_shadow_evaluations_org_binding",
            "organization_id", "binding_id", "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    binding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_shadow_bindings.id"), nullable=False,
    )
    use_case: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_packages.id"), nullable=False,
    )
    attestation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_artifact_attestations.id"), nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    suite_id: Mapped[str] = mapped_column(String(96), nullable=False)
    suite_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    observation_report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(48), nullable=False)
    fault_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False)
    vector_observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False)
    mismatch_count: Mapped[int] = mapped_column(Integer, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_p50_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    latency_p95_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    artifact_reverified: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rollback_performed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    binding_version_before: Mapped[int] = mapped_column(Integer, nullable=False)
    binding_version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    evaluated_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class ClinicalModelShadowEvaluationJob(Base):
    """Aggregate-only asynchronous shadow work with a fenced lease."""

    __tablename__ = "clinical_model_shadow_evaluation_jobs"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "idempotency_key",
            name="uq_clinical_model_shadow_job_org_idempotency",
        ),
        UniqueConstraint(
            "active_binding_id",
            name="uq_clinical_model_shadow_job_active_binding",
        ),
        CheckConstraint(
            "status IN ('queued','running','passed','stopped','failed','cancelled')",
            name="ck_clinical_model_shadow_job_status",
        ),
        CheckConstraint(
            "fault_mode IN ('none','worker_timeout','malformed_response','model_hash_mismatch')",
            name="ck_clinical_model_shadow_job_fault_mode",
        ),
        CheckConstraint(
            "attempt_count >= 0 AND max_attempts >= 1 AND attempt_count <= max_attempts",
            name="ck_clinical_model_shadow_job_attempts",
        ),
        CheckConstraint(
            "((status IN ('queued','running') AND active_binding_id = binding_id) OR "
            "(status IN ('passed','stopped','failed','cancelled') AND active_binding_id IS NULL))",
            name="ck_clinical_model_shadow_job_active_slot",
        ),
        CheckConstraint(
            "((status = 'running' AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_expires_at IS NOT NULL) OR "
            "(status <> 'running' AND lease_owner IS NULL AND lease_token IS NULL "
            "AND lease_expires_at IS NULL))",
            name="ck_clinical_model_shadow_job_lease_shape",
        ),
        CheckConstraint(
            "((status = 'cancelled' AND cancellation_reason IS NOT NULL "
            "AND cancelled_at IS NOT NULL AND cancelled_by_user_id IS NOT NULL) OR "
            "(status <> 'cancelled' AND cancellation_reason IS NULL "
            "AND cancelled_at IS NULL AND cancelled_by_user_id IS NULL))",
            name="ck_clinical_model_shadow_job_cancellation_shape",
        ),
        CheckConstraint(
            "cancellation_reason IS NULL OR cancellation_reason IN "
            "('operator_request','maintenance','safety_stop')",
            name="ck_clinical_model_shadow_job_cancellation_reason",
        ),
        Index(
            "ix_clinical_model_shadow_jobs_dispatch",
            "status", "next_attempt_at", "lease_expires_at", "created_at",
        ),
        Index(
            "ix_clinical_model_shadow_jobs_org_binding",
            "organization_id", "binding_id", "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    binding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_shadow_bindings.id"), nullable=False,
    )
    active_binding_id: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True,
    )
    use_case: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_packages.id"), nullable=False,
    )
    attestation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_artifact_attestations.id"), nullable=False,
    )
    binding_record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fault_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="none", server_default="none",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="queued", server_default="queued",
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3, server_default="3",
    )
    lease_owner: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lease_token: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    evaluation_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("clinical_model_shadow_evaluations.id"), nullable=True,
    )
    error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    rollback_performed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0",
    )
    created_by_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False,
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    cancellation_reason: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True,
    )
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    cancelled_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class ClinicalModelShadowDeadLetter(Base):
    """Metadata-only terminal failure record eligible for governed replay."""

    __tablename__ = "clinical_model_shadow_dead_letters"
    __table_args__ = (
        UniqueConstraint(
            "source_job_id", name="uq_clinical_model_shadow_dead_letter_source",
        ),
        UniqueConstraint(
            "organization_id", "replay_idempotency_key",
            name="uq_clinical_model_shadow_dead_letter_replay_key",
        ),
        CheckConstraint(
            "status IN ('available','replayed','discarded')",
            name="ck_clinical_model_shadow_dead_letter_status",
        ),
        CheckConstraint(
            "((status = 'replayed' AND replayed_job_id IS NOT NULL "
            "AND replay_idempotency_key IS NOT NULL AND replayed_at IS NOT NULL "
            "AND replayed_by_user_id IS NOT NULL) OR "
            "(status <> 'replayed' AND replayed_job_id IS NULL "
            "AND replay_idempotency_key IS NULL AND replayed_at IS NULL "
            "AND replayed_by_user_id IS NULL))",
            name="ck_clinical_model_shadow_dead_letter_replay_shape",
        ),
        Index(
            "ix_clinical_model_shadow_dead_letters_org_status_created",
            "organization_id", "status", "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    source_job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_shadow_evaluation_jobs.id"),
        nullable=False,
    )
    binding_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_shadow_bindings.id"), nullable=False,
    )
    use_case: Mapped[str] = mapped_column(String(64), nullable=False)
    package_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_packages.id"), nullable=False,
    )
    attestation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("clinical_model_artifact_attestations.id"),
        nullable=False,
    )
    binding_record_version: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="available", server_default="available",
    )
    replayed_job_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("clinical_model_shadow_evaluation_jobs.id"),
        nullable=True,
    )
    replay_idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True,
    )
    replayed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    replayed_by_user_id: Mapped[Optional[str]] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class ClinicalModelShadowAlertState(Base):
    """Tenant aggregate alert episode without job or patient identifiers."""

    __tablename__ = "clinical_model_shadow_alert_states"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "alert_code",
            name="uq_clinical_model_shadow_alert_org_code",
        ),
        CheckConstraint(
            "alert_code IN ('queue_backlog','queue_age_exceeded',"
            "'expired_leases','exhausted_jobs','dead_letter_backlog')",
            name="ck_clinical_model_shadow_alert_code",
        ),
        CheckConstraint(
            "state IN ('firing','resolved')",
            name="ck_clinical_model_shadow_alert_state",
        ),
        CheckConstraint(
            "occurrence_count >= 1",
            name="ck_clinical_model_shadow_alert_occurrences",
        ),
        Index(
            "ix_clinical_model_shadow_alert_states_state",
            "state", "last_evaluated_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(12), ForeignKey("organizations.id"), nullable=False,
    )
    alert_code: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1",
    )
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    last_evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    last_transition_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


class ClinicalModelShadowSchedulerLease(Base):
    """Database-fenced leadership lease for one shadow maintenance role."""

    __tablename__ = "clinical_model_shadow_scheduler_leases"
    __table_args__ = (
        CheckConstraint(
            "generation >= 1",
            name="ck_clinical_model_shadow_scheduler_generation",
        ),
        CheckConstraint(
            "last_cycle_status IS NULL OR last_cycle_status IN "
            "('succeeded','failed')",
            name="ck_clinical_model_shadow_scheduler_cycle_status",
        ),
    )

    scheduler_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    lease_owner: Mapped[str] = mapped_column(String(64), nullable=False)
    lease_token: Mapped[str] = mapped_column(String(36), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    generation: Mapped[int] = mapped_column(Integer, nullable=False)
    last_cycle_started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_cycle_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    last_cycle_status: Mapped[Optional[str]] = mapped_column(
        String(16), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )


__all__ = [
    "CLINICAL_MODEL_DEPLOYMENT_MODE_VALUES",
    "CLINICAL_MODEL_PACKAGE_STATUS_VALUES",
    "CLINICAL_MODEL_SHADOW_FAULT_MODE_VALUES",
    "CLINICAL_MODEL_SHADOW_GATE_STATUS_VALUES",
    "CLINICAL_MODEL_SHADOW_JOB_STATUS_VALUES",
    "CLINICAL_MODEL_SHADOW_JOB_CANCELLATION_REASON_VALUES",
    "CLINICAL_MODEL_SHADOW_DEAD_LETTER_STATUS_VALUES",
    "CLINICAL_MODEL_SHADOW_ALERT_STATE_VALUES",
    "CLINICAL_MODEL_USE_CASE_VALUES",
    "ClinicalModelActivation",
    "ClinicalModelArtifactAttestation",
    "ClinicalModelPackage",
    "ClinicalModelShadowBinding",
    "ClinicalModelShadowEvaluation",
    "ClinicalModelShadowEvaluationJob",
    "ClinicalModelShadowDeadLetter",
    "ClinicalModelShadowAlertState",
    "ClinicalModelShadowSchedulerLease",
]
