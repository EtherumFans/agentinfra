from __future__ import annotations

import base64
import hashlib
import json

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services.clinical_model_infrastructure import (
    ClinicalModelInfrastructureError,
    ExternalBundleScanner,
    GovernedDeploymentController,
    KmsEnvelopeEncryptor,
    S3ImmutableModelStore,
    stage_clinical_model_bundle,
)


class _Scanner:
    def __init__(self, events: list[str], *, status: str = "passed") -> None:
        self.events = events
        self.status = status

    def scan_bundle(self, *, content: bytes, content_sha256: str):
        self.events.append("scan")
        return {
            "engine": "hospital-av-dlp-v2",
            "status": self.status,
            "malware_status": "clean",
            "dlp_status": "clear",
            "content_sha256": content_sha256,
            "report_sha256": "b" * 64,
        }


class _Kms:
    plaintext_key = bytes(range(32))

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.request = None

    def generate_data_key(self, **kwargs):
        self.events.append("kms")
        self.request = kwargs
        return {"Plaintext": self.plaintext_key, "CiphertextBlob": b"wrapped-key"}


class _Store:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.request = None

    def put_object(self, **kwargs):
        self.events.append("store")
        self.request = kwargs
        return {"VersionId": "version-1"}


class _Controller:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.request = None

    def create_deployment(self, **kwargs):
        self.events.append("deploy")
        self.request = kwargs
        return {"deployment_id": "clinical-cn-a", "status": "staged"}


def _adapters(status: str = "passed"):
    events: list[str] = []
    scanner_client = _Scanner(events, status=status)
    kms_client = _Kms(events)
    store_client = _Store(events)
    controller_client = _Controller(events)
    return (
        events,
        ExternalBundleScanner(scanner_client, engine="hospital-av-dlp-v2"),
        KmsEnvelopeEncryptor(
            kms_client,
            key_id="arn:aws:kms:cn-north-1:123456789012:key/key-id",
        ),
        S3ImmutableModelStore(
            store_client, bucket="icoder-models-cn",
            server_side_kms_key_id="alias/icoder-model-storage",
        ),
        GovernedDeploymentController(controller_client, name="hospital-k8s-v1"),
        kms_client,
        store_client,
        controller_client,
    )


def test_staging_orders_scan_kms_immutable_store_and_controller() -> None:
    content = b"signed-clinical-model-bundle-without-patient-data"
    digest = hashlib.sha256(content).hexdigest()
    (
        events, scanner, encryptor, store, controller,
        kms_client, store_client, controller_client,
    ) = _adapters()
    receipt = stage_clinical_model_bundle(
        content, expected_sha256=digest, organization_id="org-cn-001",
        package_id="package-001", attestation_id="attestation-001",
        scanner=scanner, encryptor=encryptor, object_store=store,
        deployment_controller=controller,
    )

    assert events == ["scan", "kms", "store", "deploy"]
    assert receipt.deployment_id == "clinical-cn-a"
    assert receipt.patient_data_used is False
    assert receipt.credentials_exposed is False
    assert receipt.storage_object_key.endswith(f"/{digest}.cme")
    assert store_client.request["IfNoneMatch"] == "*"
    assert store_client.request["ServerSideEncryption"] == "aws:kms"
    assert content not in store_client.request["Body"]
    assert "credential" not in json.dumps(
        controller_client.request, sort_keys=True,
    ).lower()
    assert controller_client.request["request"]["production_traffic_enabled"] is False
    assert kms_client.request["EncryptionContext"]["icoder:sha256"] == digest

    envelope = store_client.request["Body"]
    assert envelope.startswith(b"ICODER-CME1\n")
    offset = len(b"ICODER-CME1\n")
    metadata_size = int.from_bytes(envelope[offset:offset + 4], "big")
    metadata = json.loads(envelope[offset + 4:offset + 4 + metadata_size])
    ciphertext = envelope[offset + 4 + metadata_size:]
    nonce = base64.b64decode(metadata["nonce_b64"])
    aad = json.dumps(
        kms_client.request["EncryptionContext"], sort_keys=True,
        separators=(",", ":"), ensure_ascii=True,
    ).encode()
    assert AESGCM(_Kms.plaintext_key).decrypt(nonce, ciphertext, aad) == content


def test_staging_rejects_failed_external_scan_before_kms_or_storage() -> None:
    content = b"bundle"
    digest = hashlib.sha256(content).hexdigest()
    events, scanner, encryptor, store, controller, *_ = _adapters(status="failed")
    with pytest.raises(ClinicalModelInfrastructureError, match="MODEL_SCAN_REJECTED"):
        stage_clinical_model_bundle(
            content, expected_sha256=digest, organization_id="org-cn-001",
            package_id="package-001", attestation_id="attestation-001",
            scanner=scanner, encryptor=encryptor, object_store=store,
            deployment_controller=controller,
        )
    assert events == ["scan"]


def test_staging_rejects_digest_mismatch_without_external_calls() -> None:
    events, scanner, encryptor, store, controller, *_ = _adapters()
    with pytest.raises(
        ClinicalModelInfrastructureError, match="MODEL_BUNDLE_DIGEST_MISMATCH"
    ):
        stage_clinical_model_bundle(
            b"bundle", expected_sha256="0" * 64,
            organization_id="org-cn-001", package_id="package-001",
            attestation_id="attestation-001", scanner=scanner,
            encryptor=encryptor, object_store=store,
            deployment_controller=controller,
        )
    assert events == []
