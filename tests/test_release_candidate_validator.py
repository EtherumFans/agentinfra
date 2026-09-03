from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release" / "validate_release_candidate.py"
SPEC = importlib.util.spec_from_file_location("validate_release_candidate", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def current_release_version() -> str:
    package = json.loads(
        (ROOT / "packages" / "icoder-sdk" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    return MODULE._normalize_beta(package["version"], source="javascript")


def test_repository_public_sdk_versions_are_coherent() -> None:
    versions = MODULE.read_sdk_versions(ROOT)
    expected = current_release_version()
    assert {item["normalized_version"] for item in versions.values()} == {expected}
    assert versions["javascript"]["version"] == expected


def test_artifact_manifest_hashes_files_and_excludes_its_output(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    package = artifact_dir / "icoder-sdk-1.0.0-beta.19.tgz"
    package.write_bytes(b"release-candidate")
    output = artifact_dir / "RELEASE_MANIFEST.json"
    output.write_text("stale", encoding="utf-8")

    artifacts = MODULE.collect_artifacts(
        artifact_dir,
        output_path=output,
        required_patterns=["icoder-sdk-*.tgz"],
    )
    assert artifacts == [
        {
            "path": package.name,
            "size_bytes": len(b"release-candidate"),
            "sha256": hashlib.sha256(b"release-candidate").hexdigest(),
        }
    ]


def test_required_artifact_is_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(MODULE.ReleaseCandidateError, match="Required release artifact"):
        MODULE.collect_artifacts(
            tmp_path,
            output_path=tmp_path / "manifest.json",
            required_patterns=["*.whl"],
        )


def test_cli_writes_non_publishing_manifest(tmp_path: Path) -> None:
    output = tmp_path / "version-manifest.json"
    assert MODULE.main(["--root", str(ROOT), "--output", str(output)]) == 0
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "icoder/release-candidate-manifest/v1"
    assert manifest["release_version"] == current_release_version()
    assert manifest["source_tree_state"] in {"clean", "dirty", "unknown"}
    assert manifest["publication"]["performed"] is False
    assert manifest["artifacts"] == []


def test_release_tag_must_match_package_metadata(tmp_path: Path) -> None:
    output = tmp_path / "mismatched.json"
    assert MODULE.main(
        [
            "--root",
            str(ROOT),
            "--output",
            str(output),
            "--expected-version",
            "1.0.0-beta.99",
        ]
    ) == 1
    assert not output.exists()
