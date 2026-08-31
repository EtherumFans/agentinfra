from __future__ import annotations

import pytest

from app.services.result_attestation import (
    ResultAttestationExpired,
    ResultAttestationMismatch,
    issue_result_attestation,
    verify_result_attestation,
    verify_upstream_result_attestations,
)


def _issue(result=None, *, ttl_seconds=60):
    payload = result or {"diagnoses": [{"icd10_cn_code": "I21.0"}]}
    return issue_result_attestation(
        run_id="run-upstream",
        agent_id="diagnosis-extractor",
        schema_ref="icoder/DiagnosisExtractionOutput/v6",
        organization_id="org-cn-1",
        result=payload,
        ttl_seconds=ttl_seconds,
    )


def test_result_attestation_binds_exact_result_and_identity():
    result = {"diagnoses": [{"icd10_cn_code": "I21.0"}]}
    token = _issue(result)
    claims = verify_result_attestation(
        token,
        expected_run_id="run-upstream",
        expected_agent_id="diagnosis-extractor",
        expected_schema_ref="icoder/DiagnosisExtractionOutput/v6",
        expected_organization_id="org-cn-1",
        result=result,
    )
    assert claims.result_sha256
    assert claims.organization_id == "org-cn-1"


@pytest.mark.parametrize("changed", [
    {"diagnoses": [{"icd10_cn_code": "I21.9"}]},
    {"diagnoses": []},
])
def test_result_attestation_rejects_tampered_result(changed):
    token = _issue()
    with pytest.raises(ResultAttestationMismatch):
        verify_result_attestation(
            token,
            expected_run_id="run-upstream",
            expected_agent_id="diagnosis-extractor",
            expected_schema_ref="icoder/DiagnosisExtractionOutput/v6",
            expected_organization_id="org-cn-1",
            result=changed,
        )


def test_result_attestation_rejects_cross_tenant_reuse():
    token = _issue()
    with pytest.raises(ResultAttestationMismatch):
        verify_result_attestation(
            token,
            expected_run_id="run-upstream",
            expected_agent_id="diagnosis-extractor",
            expected_schema_ref="icoder/DiagnosisExtractionOutput/v6",
            expected_organization_id="org-cn-2",
            result={"diagnoses": [{"icd10_cn_code": "I21.0"}]},
        )


def test_result_attestation_rejects_expired_proof():
    token = _issue(ttl_seconds=1)
    payload_b64, signature = token.split(".", 1)
    # Issue with a positive TTL, then patch the module clock at verification.
    from app.services import result_attestation as module
    original = module.time.time
    module.time.time = lambda: original() + 2
    try:
        with pytest.raises(ResultAttestationExpired):
            verify_result_attestation(
                f"{payload_b64}.{signature}",
                expected_run_id="run-upstream",
                expected_agent_id="diagnosis-extractor",
                expected_schema_ref="icoder/DiagnosisExtractionOutput/v6",
                expected_organization_id="org-cn-1",
                result={"diagnoses": [{"icd10_cn_code": "I21.0"}]},
            )
    finally:
        module.time.time = original


def test_upstream_collection_requires_proof_for_every_item():
    result = {"diagnoses": [{"icd10_cn_code": "I21.0"}]}
    verify_upstream_result_attestations([{
        "agent_id": "diagnosis-extractor",
        "run_id": "run-upstream",
        "schema_ref": "icoder/DiagnosisExtractionOutput/v6",
        "result": result,
        "attestation": _issue(result),
    }], organization_id="org-cn-1")

