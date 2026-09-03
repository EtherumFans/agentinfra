from __future__ import annotations

import ast
import base64
import copy
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.services.clinical_model_bundle import (
    ClinicalModelBundleError,
    build_canonical_zip,
    validate_verification_report,
    verify_bundle_directory,
    verify_bundle_zip_bytes,
)
from app.services.clinical_model_shadow_probe import (
    WORKER_PATH,
    probe_verified_synthetic_bundle,
)


FIXTURE = Path(__file__).parents[3] / "fixtures" / "clinical_model_bundle_v1"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _members() -> dict[str, bytes]:
    return {
        path.relative_to(FIXTURE).as_posix(): path.read_bytes()
        for path in FIXTURE.rglob("*") if path.is_file()
    }


def _zip(members: dict[str, bytes], *, compression: int = zipfile.ZIP_STORED) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=compression) as archive:
        for name, content in members.items():
            info = zipfile.ZipInfo("placeholder")
            # Assign after construction so Windows' ZipInfo path normalization
            # cannot hide a hostile backslash member from the verifier.
            info.filename = name
            info.compress_type = compression
            archive.writestr(info, content)
    return output.getvalue()


def _resign(
    tmp_path: Path,
    members: dict[str, bytes],
    *,
    environment: str = "test",
) -> Path:
    manifest = json.loads(members["bundle.manifest.json"])
    sbom = json.loads(members["sbom.cdx.json"])
    model_hash = hashlib.sha256(members["model/model.json"]).hexdigest()
    sbom["components"][0]["hashes"] = [{"alg": "SHA-256", "content": model_hash}]
    members["sbom.cdx.json"] = _canonical(sbom)
    for item in manifest["files"]:
        content = members[item["path"]]
        item["sha256"] = hashlib.sha256(content).hexdigest()
        item["size_bytes"] = len(content)
    members["bundle.manifest.json"] = _canonical(manifest)
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )
    signature = {
        "algorithm": "Ed25519",
        "key_id": "test-ephemeral",
        "manifest_sha256": hashlib.sha256(members["bundle.manifest.json"]).hexdigest(),
        "schema_version": "icoder.clinical-model-signature/v1",
        "signature_b64": base64.b64encode(
            private_key.sign(members["bundle.manifest.json"])
        ).decode("ascii"),
    }
    members["bundle.signature.json"] = _canonical(signature)
    trust = {
        "keys": [{
            "algorithm": "Ed25519",
            "allowed_artifact_classes": ["development_synthetic"],
            "allowed_environments": [environment],
            "key_id": "test-ephemeral",
            "public_key_b64": base64.b64encode(public_key).decode("ascii"),
            "status": "active",
        }],
        "schema_version": "icoder.clinical-model-trust-anchors/v1",
    }
    path = tmp_path / "trust.json"
    path.write_bytes(_canonical(trust))
    return path


def test_signed_directory_and_canonical_zip_verify_and_probe() -> None:
    directory = verify_bundle_directory(FIXTURE, environment="test")
    archive = build_canonical_zip(FIXTURE)
    zipped = verify_bundle_zip_bytes(archive, environment="test")

    assert directory.report == zipped.report
    assert directory.report["bundle_content_sha256"] == (
        "5d959101180a47de33df63a94bc7b065ae4da0dd01c7fc46569d9f8223378cb0"
    )
    assert directory.report["signature_verified"] is True
    assert directory.report["sbom_verified"] is True
    assert directory.report["patient_data_included"] is False
    assert directory.report["production_inference_approved"] is False
    validate_verification_report(directory.report)

    probe = probe_verified_synthetic_bundle(zipped)
    assert probe == {
        "model_sha256": "facb07eb49a09dcb98048448c8a751ffda462489adc70935d55264fb6fa13612",
        "network_used": False,
        "passed": True,
        "patient_data_used": False,
        "predictions_emitted": False,
        "schema_version": "icoder.synthetic-shadow-probe/v1",
        "test_vector_count": 2,
        "test_vectors_passed": 2,
    }


def test_tampered_content_and_manifest_fail_closed() -> None:
    members = _members()
    members["model/model.json"] += b" "
    with pytest.raises(ClinicalModelBundleError, match="BUNDLE_FILE_INTEGRITY_FAILED"):
        verify_bundle_zip_bytes(_zip(members), environment="test")

    members = _members()
    manifest = bytearray(members["bundle.manifest.json"])
    manifest[-2] = ord(" ")
    members["bundle.manifest.json"] = bytes(manifest)
    with pytest.raises(ClinicalModelBundleError, match="BUNDLE_MANIFEST_INVALID"):
        verify_bundle_zip_bytes(_zip(members), environment="test")


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("../escape.json", "BUNDLE_MEMBER_PATH_INVALID"),
        ("C:/escape.json", "BUNDLE_MEMBER_PATH_INVALID"),
        # Python's zipfile exposes this member as a raw invalid path on POSIX
        # and as a normalized-but-undeclared member on Windows. Both outcomes
        # reject the archive before any content is trusted.
        ("model\\escape.json", "BUNDLE_(MEMBER_PATH_INVALID|FILE_INVENTORY_MISMATCH)"),
    ],
)
def test_archive_path_traversal_is_rejected(name: str, code: str) -> None:
    members = _members()
    members[name] = b"{}\n"
    with pytest.raises(ClinicalModelBundleError, match=code):
        verify_bundle_zip_bytes(_zip(members), environment="test")


def test_casefold_duplicate_symlink_and_compression_bomb_are_rejected() -> None:
    members = _members()
    members["MODEL/model.json"] = members["model/model.json"]
    with pytest.raises(ClinicalModelBundleError, match="BUNDLE_MEMBER_DUPLICATE"):
        verify_bundle_zip_bytes(_zip(members), environment="test")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        info = zipfile.ZipInfo("model/link.json")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "target")
    with pytest.raises(ClinicalModelBundleError, match="BUNDLE_SYMLINK_FORBIDDEN"):
        verify_bundle_zip_bytes(output.getvalue(), environment="test")

    bomb = _zip({"bomb.json": b"0" * 100_000}, compression=zipfile.ZIP_DEFLATED)
    with pytest.raises(
        ClinicalModelBundleError, match="BUNDLE_COMPRESSION_RATIO_EXCEEDED"
    ):
        verify_bundle_zip_bytes(bomb, environment="test")


def test_development_signing_key_cannot_verify_for_production() -> None:
    with pytest.raises(ClinicalModelBundleError, match="BUNDLE_SIGNING_KEY_SCOPE_DENIED"):
        verify_bundle_directory(FIXTURE, environment="production")


def test_resigned_phi_or_executable_payload_is_scanner_blocked(tmp_path: Path) -> None:
    members = _members()
    model = json.loads(members["model/model.json"])
    model["features"]["患者姓名:张三"] = {"synthetic-ok": 1.0}
    members["model/model.json"] = _canonical(model)
    trust = _resign(tmp_path, members)
    with pytest.raises(ClinicalModelBundleError, match="BUNDLE_CONTENT_SCAN_FAILED"):
        verify_bundle_zip_bytes(
            _zip(members), environment="test", trust_anchors_path=trust,
        )

    members = _members()
    members["model/model.json"] = b"MZ" + b"\x00" * 16
    trust = _resign(tmp_path, members)
    with pytest.raises(ClinicalModelBundleError, match="BUNDLE_CONTENT_SCAN_FAILED"):
        verify_bundle_zip_bytes(
            _zip(members), environment="test", trust_anchors_path=trust,
        )


def test_signed_sbom_mismatch_and_report_tamper_fail_closed(tmp_path: Path) -> None:
    members = _members()
    sbom = json.loads(members["sbom.cdx.json"])
    sbom["metadata"]["component"]["name"] = "wrong-component"
    members["sbom.cdx.json"] = _canonical(sbom)
    trust = _resign(tmp_path, members)
    # _resign only refreshes file hashes; the wrong component identity remains.
    with pytest.raises(ClinicalModelBundleError, match="BUNDLE_SBOM_INVALID"):
        verify_bundle_zip_bytes(
            _zip(members), environment="test", trust_anchors_path=trust,
        )

    verified = verify_bundle_directory(FIXTURE, environment="test")
    tampered = copy.deepcopy(verified.report)
    tampered["production_inference_approved"] = True
    with pytest.raises(
        ClinicalModelBundleError, match="BUNDLE_VERIFICATION_REPORT_INVALID"
    ):
        validate_verification_report(tampered)


def test_probe_worker_is_stdlib_only_and_has_no_network_or_process_imports() -> None:
    tree = ast.parse(WORKER_PATH.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        str(node.module or "").split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    )
    assert imports <= {"__future__", "hashlib", "json", "math", "sys", "pathlib"}
    assert imports.isdisjoint({"socket", "subprocess", "urllib", "http", "requests"})
