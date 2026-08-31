"""Signed, bounded clinical model bundle verification.

The verifier treats every bundle as hostile input.  It validates an immutable
manifest, Ed25519 signature, file inventory, CycloneDX SBOM, content scanning
and a data-only synthetic model format without importing or executing model
code.  Production model formats intentionally remain unsupported.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import math
import re
import stat
import unicodedata
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.services.artifact_object_scan import scan_deidentified_json


BUNDLE_SCHEMA = "icoder.clinical-model-bundle/v1"
SIGNATURE_SCHEMA = "icoder.clinical-model-signature/v1"
TRUST_SCHEMA = "icoder.clinical-model-trust-anchors/v1"
VERIFICATION_SCHEMA = "icoder.clinical-model-bundle-verification/v1"
VERIFIER_VERSION = "1.0.0"
SYNTHETIC_MODEL_SCHEMA = "icoder.synthetic-shadow-model/v1"
SYNTHETIC_MODEL_FORMAT = "icoder.synthetic-json/v1"
SYNTHETIC_ARTIFACT_CLASS = "development_synthetic"
MAX_BUNDLE_BYTES = 8 * 1024 * 1024
MAX_FILE_BYTES = 4 * 1024 * 1024
MAX_FILES = 64
MAX_TOTAL_UNCOMPRESSED_BYTES = 16 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100
DEFAULT_TRUST_ANCHORS = (
    Path(__file__).resolve().parents[2] / "data" / "clinical_model_trust_anchors.json"
)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,179}$")
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+:/-]{0,95}$")


class ClinicalModelBundleError(RuntimeError):
    """Stable fail-closed bundle verification failure."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class VerifiedClinicalModelBundle:
    report: dict[str, Any]
    entrypoint_bytes: bytes


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ClinicalModelBundleError("BUNDLE_JSON_DUPLICATE_KEY")
        result[key] = value
    return result


def _load_canonical_json(content: bytes, code: str) -> dict[str, Any]:
    if not content or len(content) > MAX_FILE_BYTES or b"\x00" in content:
        raise ClinicalModelBundleError(code)
    try:
        value = json.loads(
            content.decode("utf-8"), object_pairs_hook=_reject_duplicate_keys,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        if isinstance(exc, ClinicalModelBundleError):
            raise
        raise ClinicalModelBundleError(code) from exc
    if not isinstance(value, dict) or _canonical_json(value) != content:
        raise ClinicalModelBundleError(code)
    return value


def _safe_member_name(raw: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(raw or ""))
    if normalized != raw or not _SAFE_PATH.fullmatch(normalized):
        raise ClinicalModelBundleError("BUNDLE_MEMBER_PATH_INVALID")
    if "\\" in normalized or ":" in normalized:
        raise ClinicalModelBundleError("BUNDLE_MEMBER_PATH_INVALID")
    parts = PurePosixPath(normalized).parts
    if not parts or any(part in {"", ".", ".."} or part.startswith(".") for part in parts):
        raise ClinicalModelBundleError("BUNDLE_MEMBER_PATH_INVALID")
    return normalized


def _read_directory(root: Path) -> dict[str, bytes]:
    if not root.is_dir() or root.is_symlink():
        raise ClinicalModelBundleError("BUNDLE_DIRECTORY_INVALID")
    resolved_root = root.resolve()
    members: dict[str, bytes] = {}
    for candidate in root.rglob("*"):
        if candidate.is_dir():
            if candidate.is_symlink():
                raise ClinicalModelBundleError("BUNDLE_SYMLINK_FORBIDDEN")
            continue
        if candidate.is_symlink() or not candidate.is_file():
            raise ClinicalModelBundleError("BUNDLE_SYMLINK_FORBIDDEN")
        try:
            relative = candidate.resolve().relative_to(resolved_root).as_posix()
        except ValueError as exc:
            raise ClinicalModelBundleError("BUNDLE_MEMBER_PATH_INVALID") from exc
        name = _safe_member_name(relative)
        if len(members) >= MAX_FILES or candidate.stat().st_size > MAX_FILE_BYTES:
            raise ClinicalModelBundleError("BUNDLE_LIMIT_EXCEEDED")
        members[name] = candidate.read_bytes()
    return members


def _read_zip(content: bytes) -> dict[str, bytes]:
    if not content or len(content) > MAX_BUNDLE_BYTES:
        raise ClinicalModelBundleError("BUNDLE_LIMIT_EXCEEDED")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content), mode="r")
    except (zipfile.BadZipFile, OSError) as exc:
        raise ClinicalModelBundleError("BUNDLE_ARCHIVE_INVALID") from exc
    members: dict[str, bytes] = {}
    casefold_names: set[str] = set()
    total = 0
    with archive:
        infos = archive.infolist()
        if not 1 <= len(infos) <= MAX_FILES:
            raise ClinicalModelBundleError("BUNDLE_LIMIT_EXCEEDED")
        for info in infos:
            if info.is_dir():
                continue
            name = _safe_member_name(info.filename)
            folded = name.casefold()
            if name in members or folded in casefold_names:
                raise ClinicalModelBundleError("BUNDLE_MEMBER_DUPLICATE")
            casefold_names.add(folded)
            mode = info.external_attr >> 16
            if mode and stat.S_ISLNK(mode):
                raise ClinicalModelBundleError("BUNDLE_SYMLINK_FORBIDDEN")
            if info.file_size < 1 or info.file_size > MAX_FILE_BYTES:
                raise ClinicalModelBundleError("BUNDLE_LIMIT_EXCEEDED")
            total += info.file_size
            if total > MAX_TOTAL_UNCOMPRESSED_BYTES:
                raise ClinicalModelBundleError("BUNDLE_LIMIT_EXCEEDED")
            if info.compress_size == 0 or info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise ClinicalModelBundleError("BUNDLE_COMPRESSION_RATIO_EXCEEDED")
            try:
                payload = archive.read(info)
            except (RuntimeError, OSError, zipfile.BadZipFile) as exc:
                raise ClinicalModelBundleError("BUNDLE_ARCHIVE_INVALID") from exc
            if len(payload) != info.file_size:
                raise ClinicalModelBundleError("BUNDLE_ARCHIVE_INVALID")
            members[name] = payload
    return members


def _load_trust_anchors(path: Path) -> tuple[dict[str, Any], str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_UNAVAILABLE") from exc
    payload = _load_canonical_json(raw, "BUNDLE_TRUST_STORE_INVALID")
    if payload.get("schema_version") != TRUST_SCHEMA:
        raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID")
    keys = payload.get("keys")
    if not isinstance(keys, list) or not keys:
        raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID")
    seen: set[str] = set()
    for item in keys:
        if not isinstance(item, dict):
            raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID")
        key_id = str(item.get("key_id") or "")
        if key_id in seen or not _SAFE_IDENTIFIER.fullmatch(key_id):
            raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID")
        seen.add(key_id)
        if item.get("algorithm") != "Ed25519" or item.get("status") not in {"active", "revoked"}:
            raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID")
        if not isinstance(item.get("allowed_environments"), list):
            raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID")
        if not isinstance(item.get("allowed_artifact_classes"), list):
            raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID")
        try:
            public_key = base64.b64decode(str(item.get("public_key_b64") or ""), validate=True)
        except (ValueError, TypeError) as exc:
            raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID") from exc
        if len(public_key) != 32:
            raise ClinicalModelBundleError("BUNDLE_TRUST_STORE_INVALID")
    return payload, _sha256(raw)


def _exact_keys(value: dict[str, Any], expected: set[str], code: str) -> None:
    if set(value) != expected:
        raise ClinicalModelBundleError(code)


def _validate_manifest(manifest: dict[str, Any]) -> None:
    _exact_keys(
        manifest,
        {
            "artifact_class", "bundle_id", "entrypoint", "execution_policy",
            "files", "model_format", "runtime_contract", "sbom_path",
            "schema_version", "training_data", "use_case", "version",
        },
        "BUNDLE_MANIFEST_INVALID",
    )
    if manifest.get("schema_version") != BUNDLE_SCHEMA:
        raise ClinicalModelBundleError("BUNDLE_MANIFEST_INVALID")
    for field in ("bundle_id", "runtime_contract", "version"):
        if not _SAFE_IDENTIFIER.fullmatch(str(manifest.get(field) or "")):
            raise ClinicalModelBundleError("BUNDLE_MANIFEST_INVALID")
    if manifest.get("artifact_class") != SYNTHETIC_ARTIFACT_CLASS:
        raise ClinicalModelBundleError("BUNDLE_ARTIFACT_CLASS_UNSUPPORTED")
    if manifest.get("model_format") != SYNTHETIC_MODEL_FORMAT:
        raise ClinicalModelBundleError("BUNDLE_MODEL_FORMAT_UNSUPPORTED")
    if manifest.get("use_case") not in {
        "clinical_coding_decision_support",
        "clinical_documentation_improvement",
    }:
        raise ClinicalModelBundleError("BUNDLE_MANIFEST_INVALID")
    entrypoint = _safe_member_name(str(manifest.get("entrypoint") or ""))
    sbom_path = _safe_member_name(str(manifest.get("sbom_path") or ""))
    if entrypoint == sbom_path:
        raise ClinicalModelBundleError("BUNDLE_MANIFEST_INVALID")
    policy = manifest.get("execution_policy")
    if policy != {
        "code_execution_allowed": False,
        "network_allowed": False,
        "patient_data_allowed": False,
        "shadow_only": True,
    }:
        raise ClinicalModelBundleError("BUNDLE_EXECUTION_POLICY_UNSAFE")
    training = manifest.get("training_data")
    if not isinstance(training, dict):
        raise ClinicalModelBundleError("BUNDLE_TRAINING_DATA_POLICY_UNSAFE")
    _exact_keys(
        training,
        {"case_count", "classification", "dataset_sha256", "patient_data_included"},
        "BUNDLE_TRAINING_DATA_POLICY_UNSAFE",
    )
    if (
        training.get("classification") != "synthetic_only"
        or training.get("patient_data_included") is not False
        or not isinstance(training.get("case_count"), int)
        or isinstance(training.get("case_count"), bool)
        or not 1 <= training["case_count"] <= 10_000
        or not _SHA256.fullmatch(str(training.get("dataset_sha256") or ""))
    ):
        raise ClinicalModelBundleError("BUNDLE_TRAINING_DATA_POLICY_UNSAFE")
    files = manifest.get("files")
    if not isinstance(files, list) or not 2 <= len(files) <= MAX_FILES - 2:
        raise ClinicalModelBundleError("BUNDLE_FILE_INVENTORY_INVALID")
    paths: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ClinicalModelBundleError("BUNDLE_FILE_INVENTORY_INVALID")
        _exact_keys(
            item, {"media_type", "path", "sha256", "size_bytes"},
            "BUNDLE_FILE_INVENTORY_INVALID",
        )
        path = _safe_member_name(str(item.get("path") or ""))
        if path in paths:
            raise ClinicalModelBundleError("BUNDLE_FILE_INVENTORY_INVALID")
        paths.add(path)
        if item.get("media_type") not in {
            "application/json", "application/vnd.cyclonedx+json",
        }:
            raise ClinicalModelBundleError("BUNDLE_FILE_INVENTORY_INVALID")
        if not _SHA256.fullmatch(str(item.get("sha256") or "")):
            raise ClinicalModelBundleError("BUNDLE_FILE_INVENTORY_INVALID")
        size = item.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or not 1 <= size <= MAX_FILE_BYTES:
            raise ClinicalModelBundleError("BUNDLE_FILE_INVENTORY_INVALID")
    if entrypoint not in paths or sbom_path not in paths:
        raise ClinicalModelBundleError("BUNDLE_FILE_INVENTORY_INVALID")


def _validate_signature(
    signature: dict[str, Any],
    *,
    manifest_bytes: bytes,
    artifact_class: str,
    environment: str,
    trust_store: dict[str, Any],
) -> str:
    _exact_keys(
        signature,
        {"algorithm", "key_id", "manifest_sha256", "schema_version", "signature_b64"},
        "BUNDLE_SIGNATURE_INVALID",
    )
    if (
        signature.get("schema_version") != SIGNATURE_SCHEMA
        or signature.get("algorithm") != "Ed25519"
        or signature.get("manifest_sha256") != _sha256(manifest_bytes)
    ):
        raise ClinicalModelBundleError("BUNDLE_SIGNATURE_INVALID")
    key_id = str(signature.get("key_id") or "")
    key = next(
        (item for item in trust_store["keys"] if item.get("key_id") == key_id),
        None,
    )
    if key is None:
        raise ClinicalModelBundleError("BUNDLE_SIGNING_KEY_UNKNOWN")
    if key.get("status") != "active":
        raise ClinicalModelBundleError("BUNDLE_SIGNING_KEY_REVOKED")
    if environment not in key["allowed_environments"]:
        raise ClinicalModelBundleError("BUNDLE_SIGNING_KEY_SCOPE_DENIED")
    if artifact_class not in key["allowed_artifact_classes"]:
        raise ClinicalModelBundleError("BUNDLE_SIGNING_KEY_SCOPE_DENIED")
    try:
        public_key_bytes = base64.b64decode(key["public_key_b64"], validate=True)
        signature_bytes = base64.b64decode(signature["signature_b64"], validate=True)
        Ed25519PublicKey.from_public_bytes(public_key_bytes).verify(
            signature_bytes, manifest_bytes,
        )
    except (ValueError, TypeError, InvalidSignature) as exc:
        raise ClinicalModelBundleError("BUNDLE_SIGNATURE_INVALID") from exc
    return key_id


def _validate_sbom(
    sbom: dict[str, Any],
    *,
    manifest: dict[str, Any],
) -> None:
    _exact_keys(
        sbom, {"bomFormat", "components", "metadata", "specVersion", "version"},
        "BUNDLE_SBOM_INVALID",
    )
    if sbom.get("bomFormat") != "CycloneDX" or sbom.get("specVersion") != "1.5" or sbom.get("version") != 1:
        raise ClinicalModelBundleError("BUNDLE_SBOM_INVALID")
    metadata = sbom.get("metadata")
    if not isinstance(metadata, dict) or set(metadata) != {"component", "timestamp"}:
        raise ClinicalModelBundleError("BUNDLE_SBOM_INVALID")
    component = metadata.get("component")
    if component != {
        "name": manifest["bundle_id"],
        "type": "machine-learning-model",
        "version": manifest["version"],
    }:
        raise ClinicalModelBundleError("BUNDLE_SBOM_INVALID")
    inventory = {
        item["path"]: item for item in manifest["files"]
        if item["path"] != manifest["sbom_path"]
    }
    components = sbom.get("components")
    if not isinstance(components, list) or len(components) != len(inventory):
        raise ClinicalModelBundleError("BUNDLE_SBOM_INVALID")
    seen: set[str] = set()
    for item in components:
        if not isinstance(item, dict) or set(item) != {"hashes", "name", "type", "version"}:
            raise ClinicalModelBundleError("BUNDLE_SBOM_INVALID")
        name = str(item.get("name") or "")
        if name in seen or name not in inventory or item.get("type") != "file":
            raise ClinicalModelBundleError("BUNDLE_SBOM_INVALID")
        seen.add(name)
        if item.get("version") != manifest["version"]:
            raise ClinicalModelBundleError("BUNDLE_SBOM_INVALID")
        if item.get("hashes") != [{"alg": "SHA-256", "content": inventory[name]["sha256"]}]:
            raise ClinicalModelBundleError("BUNDLE_SBOM_INVALID")


def _validate_synthetic_model(model: dict[str, Any]) -> None:
    _exact_keys(
        model, {"features", "labels", "schema_version", "test_vectors"},
        "BUNDLE_SYNTHETIC_MODEL_INVALID",
    )
    if model.get("schema_version") != SYNTHETIC_MODEL_SCHEMA:
        raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
    labels = model.get("labels")
    if (
        not isinstance(labels, list) or not 2 <= len(labels) <= 64
        or len(set(labels)) != len(labels)
        or any(not isinstance(label, str) or not _SAFE_IDENTIFIER.fullmatch(label) for label in labels)
    ):
        raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
    features = model.get("features")
    if not isinstance(features, dict) or not 1 <= len(features) <= 10_000:
        raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
    for token, weights in features.items():
        if not isinstance(token, str) or not _SAFE_IDENTIFIER.fullmatch(token):
            raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
        if not isinstance(weights, dict) or not weights:
            raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
        for label, weight in weights.items():
            if label not in labels or isinstance(weight, bool) or not isinstance(weight, (int, float)):
                raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
            if not math.isfinite(float(weight)) or not -100 <= float(weight) <= 100:
                raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
    vectors = model.get("test_vectors")
    if not isinstance(vectors, list) or not 1 <= len(vectors) <= 100:
        raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
    for vector in vectors:
        if not isinstance(vector, dict) or set(vector) != {"expected", "tokens"}:
            raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
        tokens = vector.get("tokens")
        if vector.get("expected") not in labels or not isinstance(tokens, list) or not 1 <= len(tokens) <= 64:
            raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")
        if any(token not in features for token in tokens):
            raise ClinicalModelBundleError("BUNDLE_SYNTHETIC_MODEL_INVALID")


def _content_digest(members: dict[str, bytes]) -> str:
    digest = hashlib.sha256()
    for name in sorted(members):
        digest.update(name.encode("ascii"))
        digest.update(b"\0")
        digest.update(_sha256(members[name]).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _verify_members(
    members: dict[str, bytes],
    *,
    environment: str,
    trust_anchors_path: Path,
) -> VerifiedClinicalModelBundle:
    required = {"bundle.manifest.json", "bundle.signature.json"}
    if not required.issubset(members):
        raise ClinicalModelBundleError("BUNDLE_REQUIRED_FILE_MISSING")
    manifest_bytes = members["bundle.manifest.json"]
    manifest = _load_canonical_json(manifest_bytes, "BUNDLE_MANIFEST_INVALID")
    _validate_manifest(manifest)
    expected_members = required | {item["path"] for item in manifest["files"]}
    if set(members) != expected_members:
        raise ClinicalModelBundleError("BUNDLE_FILE_INVENTORY_MISMATCH")
    for item in manifest["files"]:
        content = members[item["path"]]
        if len(content) != item["size_bytes"] or _sha256(content) != item["sha256"]:
            raise ClinicalModelBundleError("BUNDLE_FILE_INTEGRITY_FAILED")
    trust_store, trust_store_sha256 = _load_trust_anchors(trust_anchors_path)
    signature = _load_canonical_json(
        members["bundle.signature.json"], "BUNDLE_SIGNATURE_INVALID",
    )
    key_id = _validate_signature(
        signature,
        manifest_bytes=manifest_bytes,
        artifact_class=manifest["artifact_class"],
        environment=environment,
        trust_store=trust_store,
    )
    for name, content in members.items():
        if name == "bundle.signature.json":
            continue
        try:
            scan_deidentified_json(content, filename=PurePosixPath(name).name)
        except Exception as exc:
            raise ClinicalModelBundleError("BUNDLE_CONTENT_SCAN_FAILED") from exc
    sbom = _load_canonical_json(
        members[manifest["sbom_path"]], "BUNDLE_SBOM_INVALID",
    )
    _validate_sbom(sbom, manifest=manifest)
    entrypoint_bytes = members[manifest["entrypoint"]]
    model = _load_canonical_json(
        entrypoint_bytes, "BUNDLE_SYNTHETIC_MODEL_INVALID",
    )
    _validate_synthetic_model(model)
    report: dict[str, Any] = {
        "schema_version": VERIFICATION_SCHEMA,
        "verifier_version": VERIFIER_VERSION,
        "bundle_id": manifest["bundle_id"],
        "bundle_version": manifest["version"],
        "bundle_content_sha256": _content_digest(members),
        "manifest_sha256": _sha256(manifest_bytes),
        "signature_verified": True,
        "trust_key_id": key_id,
        "trust_store_sha256": trust_store_sha256,
        "artifact_class": manifest["artifact_class"],
        "use_case": manifest["use_case"],
        "model_format": manifest["model_format"],
        "runtime_contract": manifest["runtime_contract"],
        "sbom_sha256": _sha256(members[manifest["sbom_path"]]),
        "sbom_verified": True,
        "files_verified": len(manifest["files"]),
        "content_scan_status": "clean_development_scanner",
        "training_data_classification": manifest["training_data"]["classification"],
        "training_dataset_sha256": manifest["training_data"]["dataset_sha256"],
        "training_case_count": manifest["training_data"]["case_count"],
        "patient_data_included": False,
        "code_execution_allowed": False,
        "network_allowed": False,
        "shadow_only": True,
        "production_inference_approved": False,
    }
    report["verification_report_sha256"] = _sha256(_canonical_json(report))
    return VerifiedClinicalModelBundle(report=report, entrypoint_bytes=entrypoint_bytes)


def verify_bundle_directory(
    root: str | Path,
    *,
    environment: str = "development",
    trust_anchors_path: str | Path = DEFAULT_TRUST_ANCHORS,
) -> VerifiedClinicalModelBundle:
    if environment not in {"development", "test", "production"}:
        raise ClinicalModelBundleError("BUNDLE_ENVIRONMENT_INVALID")
    return _verify_members(
        _read_directory(Path(root)),
        environment=environment,
        trust_anchors_path=Path(trust_anchors_path),
    )


def verify_bundle_zip_bytes(
    content: bytes,
    *,
    environment: str = "development",
    trust_anchors_path: str | Path = DEFAULT_TRUST_ANCHORS,
) -> VerifiedClinicalModelBundle:
    if environment not in {"development", "test", "production"}:
        raise ClinicalModelBundleError("BUNDLE_ENVIRONMENT_INVALID")
    return _verify_members(
        _read_zip(content),
        environment=environment,
        trust_anchors_path=Path(trust_anchors_path),
    )


def build_canonical_zip(root: str | Path) -> bytes:
    """Build a deterministic store-only archive for tests and release probes."""

    members = _read_directory(Path(root))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, members[name])
    content = output.getvalue()
    if len(content) > MAX_BUNDLE_BYTES:
        raise ClinicalModelBundleError("BUNDLE_LIMIT_EXCEEDED")
    return content


def validate_verification_report(report: dict[str, Any]) -> None:
    expected_keys = {
        "artifact_class", "bundle_content_sha256", "bundle_id", "bundle_version",
        "code_execution_allowed", "content_scan_status", "files_verified",
        "manifest_sha256", "model_format", "network_allowed",
        "patient_data_included", "production_inference_approved", "runtime_contract",
        "sbom_sha256", "sbom_verified", "schema_version", "shadow_only",
        "signature_verified", "training_data_classification", "trust_key_id",
        "training_dataset_sha256", "training_case_count", "trust_store_sha256",
        "use_case", "verification_report_sha256",
        "verifier_version",
    }
    if set(report) != expected_keys:
        raise ClinicalModelBundleError("BUNDLE_VERIFICATION_REPORT_INVALID")
    digest = str(report.get("verification_report_sha256") or "")
    unsigned = dict(report)
    unsigned.pop("verification_report_sha256", None)
    if not _SHA256.fullmatch(digest) or digest != _sha256(_canonical_json(unsigned)):
        raise ClinicalModelBundleError("BUNDLE_VERIFICATION_REPORT_INVALID")
    if (
        report.get("schema_version") != VERIFICATION_SCHEMA
        or report.get("verifier_version") != VERIFIER_VERSION
        or report.get("signature_verified") is not True
        or report.get("sbom_verified") is not True
        or report.get("content_scan_status") != "clean_development_scanner"
        or report.get("training_data_classification") != "synthetic_only"
        or not _SHA256.fullmatch(str(report.get("training_dataset_sha256") or ""))
        or not isinstance(report.get("training_case_count"), int)
        or isinstance(report.get("training_case_count"), bool)
        or not 1 <= report["training_case_count"] <= 10_000
        or report.get("patient_data_included") is not False
        or report.get("code_execution_allowed") is not False
        or report.get("network_allowed") is not False
        or report.get("shadow_only") is not True
        or report.get("production_inference_approved") is not False
    ):
        raise ClinicalModelBundleError("BUNDLE_VERIFICATION_REPORT_INVALID")


__all__ = [
    "ClinicalModelBundleError",
    "DEFAULT_TRUST_ANCHORS",
    "VerifiedClinicalModelBundle",
    "build_canonical_zip",
    "validate_verification_report",
    "verify_bundle_directory",
    "verify_bundle_zip_bytes",
]
