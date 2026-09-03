"""Fail-closed policy helpers for clinical model package activation."""

from __future__ import annotations

from app.models.clinical_model_package import ClinicalModelPackage


def activation_blockers(
    package: ClinicalModelPackage,
    *,
    deployment_mode: str,
) -> list[str]:
    """Return stable, non-secret reason codes blocking an activation.

    Registration and workflow approval do not establish clinical safety.  A
    package becomes runtime-selectable only when every external evidence flag
    relevant to the requested deployment boundary is present.
    """

    blockers: list[str] = []
    if package.status not in {"approved", "active"}:
        blockers.append("package_not_approved")
    if package.license_status != "verified":
        blockers.append("license_not_verified")
    if not package.redistribution_authorized:
        blockers.append("redistribution_not_authorized")
    if not package.independent_gold_validated:
        blockers.append("independent_gold_not_validated")
    if not package.independent_reviewer_approved:
        blockers.append("independent_reviewer_not_approved")
    if not package.review_reference_sha256:
        blockers.append("review_evidence_missing")
    if (
        not package.reviewed_by_user_id
        or package.reviewed_by_user_id == package.created_by_user_id
    ):
        blockers.append("four_eyes_review_missing")
    if deployment_mode in {"hospital_private", "cloud"} and not package.hospital_use_authorized:
        blockers.append("hospital_use_not_authorized")
    if deployment_mode == "cloud" and not package.cloud_use_authorized:
        blockers.append("cloud_use_not_authorized")
    return blockers


__all__ = ["activation_blockers"]
