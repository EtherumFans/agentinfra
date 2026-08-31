"""Production adapter boundary for staging governed clinical model bundles.

The adapter deliberately accepts injected cloud clients.  Credentials remain
in the cloud SDK credential chain and never enter a request, database row,
audit event, or returned receipt.  The staging order is fail-closed:

external scan -> KMS envelope encryption -> immutable object write ->
deployment-controller registration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,95}$")
_KMS_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,2047}$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_MAGIC = b"ICODER-CME1\n"
_MAX_BUNDLE_BYTES = 64 * 1024 * 1024


class ClinicalModelInfrastructureError(RuntimeError):
    """Stable fail-closed error without provider response content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class SecurityScannerClient(Protocol):
    def scan_bundle(self, *, content: bytes, content_sha256: str) -> dict[str, Any]: ...


class KmsClient(Protocol):
    def generate_data_key(self, **kwargs: Any) -> dict[str, Any]: ...


class ObjectStoreClient(Protocol):
    def put_object(self, **kwargs: Any) -> dict[str, Any]: ...


class DeploymentControllerClient(Protocol):
    def create_deployment(self, **kwargs: Any) -> dict[str, Any]: ...


@dataclass(frozen=True, slots=True)
class ScanAttestation:
    engine: str
    report_sha256: str
    content_sha256: str


@dataclass(frozen=True, slots=True)
class EncryptedEnvelope:
    content: bytes
    content_sha256: str
    plaintext_sha256: str
    kms_key_id: str


@dataclass(frozen=True, slots=True)
class StoredModelObject:
    backend: str
    bucket: str
    object_key: str
    version_id: str | None
    content_sha256: str


@dataclass(frozen=True, slots=True)
class DeploymentReceipt:
    deployment_id: str
    status: str
    controller: str


@dataclass(frozen=True, slots=True)
class StagedClinicalModel:
    organization_id: str
    package_id: str
    attestation_id: str
    plaintext_sha256: str
    scan_engine: str
    scan_report_sha256: str
    kms_key_id: str
    storage_backend: str
    storage_bucket: str
    storage_object_key: str
    storage_version_id: str | None
    deployment_id: str
    deployment_status: str
    patient_data_used: bool = False
    credentials_exposed: bool = False


def _identifier(value: str, *, code: str) -> str:
    normalized = str(value or "").strip()
    if _IDENTIFIER.fullmatch(normalized) is None:
        raise ClinicalModelInfrastructureError(code)
    return normalized


def _digest(value: str, *, code: str) -> str:
    normalized = str(value or "").strip().lower()
    if _SHA256.fullmatch(normalized) is None:
        raise ClinicalModelInfrastructureError(code)
    return normalized


def _kms_identifier(value: str, *, code: str) -> str:
    normalized = str(value or "").strip()
    if _KMS_IDENTIFIER.fullmatch(normalized) is None:
        raise ClinicalModelInfrastructureError(code)
    return normalized


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


class ExternalBundleScanner:
    """Validate a minimal, digest-bound response from an operated AV/DLP scanner."""

    def __init__(self, client: SecurityScannerClient, *, engine: str) -> None:
        self._client = client
        self._engine = _identifier(engine, code="MODEL_SCAN_ENGINE_INVALID")

    def scan(self, content: bytes, *, expected_sha256: str) -> ScanAttestation:
        expected = _digest(expected_sha256, code="MODEL_BUNDLE_DIGEST_INVALID")
        if not content or len(content) > _MAX_BUNDLE_BYTES:
            raise ClinicalModelInfrastructureError("MODEL_BUNDLE_SIZE_INVALID")
        if hashlib.sha256(content).hexdigest() != expected:
            raise ClinicalModelInfrastructureError("MODEL_BUNDLE_DIGEST_MISMATCH")
        try:
            raw = self._client.scan_bundle(
                content=content, content_sha256=expected,
            )
        except Exception as exc:
            raise ClinicalModelInfrastructureError("MODEL_SCAN_UNAVAILABLE") from exc
        if not isinstance(raw, dict) or set(raw) != {
            "engine", "status", "malware_status", "dlp_status",
            "content_sha256", "report_sha256",
        }:
            raise ClinicalModelInfrastructureError("MODEL_SCAN_RESPONSE_INVALID")
        if (
            raw.get("engine") != self._engine
            or raw.get("status") != "passed"
            or raw.get("malware_status") != "clean"
            or raw.get("dlp_status") != "clear"
            or raw.get("content_sha256") != expected
        ):
            raise ClinicalModelInfrastructureError("MODEL_SCAN_REJECTED")
        return ScanAttestation(
            engine=self._engine,
            report_sha256=_digest(
                str(raw.get("report_sha256") or ""),
                code="MODEL_SCAN_RESPONSE_INVALID",
            ),
            content_sha256=expected,
        )


class KmsEnvelopeEncryptor:
    """Encrypt model bytes with a one-time AES-256 key wrapped by cloud KMS."""

    def __init__(self, client: KmsClient, *, key_id: str) -> None:
        self._client = client
        self._key_id = _kms_identifier(key_id, code="MODEL_KMS_KEY_ID_INVALID")

    def encrypt(
        self, content: bytes, *, plaintext_sha256: str,
        organization_id: str, package_id: str, attestation_id: str,
    ) -> EncryptedEnvelope:
        digest = _digest(plaintext_sha256, code="MODEL_BUNDLE_DIGEST_INVALID")
        context = {
            "icoder:purpose": "clinical-model-staging",
            "icoder:organization": _identifier(
                organization_id, code="MODEL_ORGANIZATION_ID_INVALID"
            ),
            "icoder:package": _identifier(package_id, code="MODEL_PACKAGE_ID_INVALID"),
            "icoder:attestation": _identifier(
                attestation_id, code="MODEL_ATTESTATION_ID_INVALID"
            ),
            "icoder:sha256": digest,
        }
        try:
            response = self._client.generate_data_key(
                KeyId=self._key_id, KeySpec="AES_256", EncryptionContext=context,
            )
            plaintext_key = bytes(response["Plaintext"])
            wrapped_key = bytes(response["CiphertextBlob"])
        except Exception as exc:
            raise ClinicalModelInfrastructureError("MODEL_KMS_UNAVAILABLE") from exc
        if len(plaintext_key) != 32 or not wrapped_key:
            raise ClinicalModelInfrastructureError("MODEL_KMS_RESPONSE_INVALID")
        # AES-GCM uses a fresh 96-bit nonce for every one-time data key.
        import os

        nonce = os.urandom(12)
        aad = _canonical(context)
        ciphertext = AESGCM(plaintext_key).encrypt(nonce, content, aad)
        metadata = _canonical({
            "schema_version": "icoder.clinical-model-envelope/v1",
            "kms_key_id": self._key_id,
            "encrypted_data_key_b64": base64.b64encode(wrapped_key).decode("ascii"),
            "nonce_b64": base64.b64encode(nonce).decode("ascii"),
            "aad_sha256": hashlib.sha256(aad).hexdigest(),
            "plaintext_sha256": digest,
        })
        if len(metadata) > 65535:
            raise ClinicalModelInfrastructureError("MODEL_ENVELOPE_METADATA_INVALID")
        envelope = _MAGIC + len(metadata).to_bytes(4, "big") + metadata + ciphertext
        return EncryptedEnvelope(
            content=envelope,
            content_sha256=hashlib.sha256(envelope).hexdigest(),
            plaintext_sha256=digest,
            kms_key_id=self._key_id,
        )


class S3ImmutableModelStore:
    """Write one content-addressed, KMS-protected object without overwriting."""

    def __init__(
        self, client: ObjectStoreClient, *, bucket: str,
        server_side_kms_key_id: str, prefix: str = "clinical-models/v1",
    ) -> None:
        if _BUCKET.fullmatch(str(bucket or "")) is None:
            raise ClinicalModelInfrastructureError("MODEL_STORAGE_BUCKET_INVALID")
        self._client = client
        self._bucket = bucket
        self._sse_key_id = _kms_identifier(
            server_side_kms_key_id, code="MODEL_STORAGE_KMS_KEY_ID_INVALID"
        )
        self._prefix = "/".join(
            _identifier(part, code="MODEL_STORAGE_PREFIX_INVALID")
            for part in str(prefix).strip("/").split("/")
        )

    def put(
        self, envelope: EncryptedEnvelope, *, organization_id: str,
        package_id: str,
    ) -> StoredModelObject:
        organization = _identifier(
            organization_id, code="MODEL_ORGANIZATION_ID_INVALID"
        )
        package = _identifier(package_id, code="MODEL_PACKAGE_ID_INVALID")
        object_key = (
            f"{self._prefix}/{organization}/{package}/"
            f"{envelope.plaintext_sha256}.cme"
        )
        checksum = base64.b64encode(
            bytes.fromhex(envelope.content_sha256)
        ).decode("ascii")
        try:
            result = self._client.put_object(
                Bucket=self._bucket,
                Key=object_key,
                Body=envelope.content,
                ContentType="application/vnd.icoder.clinical-model-envelope",
                ChecksumSHA256=checksum,
                ServerSideEncryption="aws:kms",
                SSEKMSKeyId=self._sse_key_id,
                IfNoneMatch="*",
                Metadata={
                    "schema": "icoder-clinical-model-envelope-v1",
                    "plaintext-sha256": envelope.plaintext_sha256,
                    "envelope-sha256": envelope.content_sha256,
                },
            )
        except Exception as exc:
            raise ClinicalModelInfrastructureError("MODEL_STORAGE_WRITE_FAILED") from exc
        version_id = result.get("VersionId") if isinstance(result, dict) else None
        return StoredModelObject(
            backend="s3-compatible", bucket=self._bucket, object_key=object_key,
            version_id=str(version_id) if version_id else None,
            content_sha256=envelope.content_sha256,
        )


class GovernedDeploymentController:
    """Register only digest-bound object metadata with an external controller."""

    def __init__(self, client: DeploymentControllerClient, *, name: str) -> None:
        self._client = client
        self._name = _identifier(name, code="MODEL_DEPLOYMENT_CONTROLLER_INVALID")

    def create(
        self, *, organization_id: str, package_id: str, attestation_id: str,
        stored: StoredModelObject, scan: ScanAttestation, kms_key_id: str,
    ) -> DeploymentReceipt:
        request = {
            "schema_version": "icoder.clinical-model-deployment-request/v1",
            "organization_id": organization_id,
            "package_id": package_id,
            "attestation_id": attestation_id,
            "object": {
                "backend": stored.backend, "bucket": stored.bucket,
                "key": stored.object_key, "version_id": stored.version_id,
                "content_sha256": stored.content_sha256,
            },
            "security": {
                "scan_engine": scan.engine,
                "scan_report_sha256": scan.report_sha256,
                "kms_key_id": kms_key_id,
            },
            "patient_data_included": False,
            "production_traffic_enabled": False,
        }
        try:
            raw = self._client.create_deployment(request=request)
        except Exception as exc:
            raise ClinicalModelInfrastructureError(
                "MODEL_DEPLOYMENT_CONTROLLER_UNAVAILABLE"
            ) from exc
        if not isinstance(raw, dict) or set(raw) != {"deployment_id", "status"}:
            raise ClinicalModelInfrastructureError("MODEL_DEPLOYMENT_RESPONSE_INVALID")
        deployment_id = _identifier(
            str(raw.get("deployment_id") or ""),
            code="MODEL_DEPLOYMENT_RESPONSE_INVALID",
        )
        status = str(raw.get("status") or "")
        if status not in {"staged", "validating", "ready"}:
            raise ClinicalModelInfrastructureError("MODEL_DEPLOYMENT_RESPONSE_INVALID")
        return DeploymentReceipt(deployment_id, status, self._name)


def stage_clinical_model_bundle(
    content: bytes,
    *,
    expected_sha256: str,
    organization_id: str,
    package_id: str,
    attestation_id: str,
    scanner: ExternalBundleScanner,
    encryptor: KmsEnvelopeEncryptor,
    object_store: S3ImmutableModelStore,
    deployment_controller: GovernedDeploymentController,
) -> StagedClinicalModel:
    """Compose all production boundaries and return metadata only."""

    scan = scanner.scan(content, expected_sha256=expected_sha256)
    envelope = encryptor.encrypt(
        content, plaintext_sha256=scan.content_sha256,
        organization_id=organization_id, package_id=package_id,
        attestation_id=attestation_id,
    )
    stored = object_store.put(
        envelope, organization_id=organization_id, package_id=package_id,
    )
    deployment = deployment_controller.create(
        organization_id=organization_id, package_id=package_id,
        attestation_id=attestation_id, stored=stored, scan=scan,
        kms_key_id=envelope.kms_key_id,
    )
    return StagedClinicalModel(
        organization_id=organization_id, package_id=package_id,
        attestation_id=attestation_id, plaintext_sha256=scan.content_sha256,
        scan_engine=scan.engine, scan_report_sha256=scan.report_sha256,
        kms_key_id=envelope.kms_key_id, storage_backend=stored.backend,
        storage_bucket=stored.bucket, storage_object_key=stored.object_key,
        storage_version_id=stored.version_id,
        deployment_id=deployment.deployment_id,
        deployment_status=deployment.status,
    )


__all__ = [
    "ClinicalModelInfrastructureError", "DeploymentReceipt",
    "EncryptedEnvelope", "ExternalBundleScanner",
    "GovernedDeploymentController", "KmsEnvelopeEncryptor",
    "S3ImmutableModelStore", "ScanAttestation", "StagedClinicalModel",
    "StoredModelObject", "stage_clinical_model_bundle",
]
