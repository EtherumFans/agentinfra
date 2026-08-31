#!/usr/bin/env python3
"""Validate SDK version coherence and build release evidence without publishing."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_SCHEMA = "icoder/release-candidate-manifest/v1"
SEMVER_BETA = re.compile(r"^(\d+)\.(\d+)\.(\d+)-beta\.(\d+)$")
PEP440_BETA = re.compile(r"^(\d+)\.(\d+)\.(\d+)b(\d+)$")


class ReleaseCandidateError(ValueError):
    """A safe, actionable release-candidate validation failure."""


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise ReleaseCandidateError(f"{path}: expected a JSON object")
    return value


def _normalize_beta(version: str, *, source: str) -> str:
    semver = SEMVER_BETA.fullmatch(version)
    if semver:
        return f"{semver.group(1)}.{semver.group(2)}.{semver.group(3)}-beta.{semver.group(4)}"
    pep440 = PEP440_BETA.fullmatch(version)
    if pep440:
        return f"{pep440.group(1)}.{pep440.group(2)}.{pep440.group(3)}-beta.{pep440.group(4)}"
    raise ReleaseCandidateError(
        f"{source}: {version!r} is not an explicit numbered beta version"
    )


def read_sdk_versions(root: Path = REPOSITORY_ROOT) -> dict[str, dict[str, str]]:
    js_path = root / "packages" / "icoder-sdk" / "package.json"
    python_project_path = root / "packages" / "icoder-python" / "pyproject.toml"
    python_init_path = root / "packages" / "icoder-python" / "icoder_sdk" / "__init__.py"
    dotnet_path = root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk" / "Icoder.Sdk.csproj"

    js_version = str(_load_json(js_path).get("version", "")).strip()
    with python_project_path.open("rb") as stream:
        python_version = str(tomllib.load(stream).get("project", {}).get("version", "")).strip()
    python_init = python_init_path.read_text(encoding="utf-8")
    python_init_match = re.search(r'^__version__\s*=\s*"([^"]+)"\s*$', python_init, re.MULTILINE)
    if python_init_match is None:
        raise ReleaseCandidateError(f"{python_init_path}: __version__ is missing")
    python_runtime_version = python_init_match.group(1)

    dotnet_root = ET.parse(dotnet_path).getroot()
    dotnet_version_node = dotnet_root.find(".//Version")
    dotnet_version = (
        dotnet_version_node.text.strip()
        if dotnet_version_node is not None and dotnet_version_node.text
        else ""
    )

    raw = {
        "javascript": {"version": js_version, "path": js_path.relative_to(root).as_posix()},
        "python": {
            "version": python_version,
            "runtime_version": python_runtime_version,
            "path": python_project_path.relative_to(root).as_posix(),
        },
        "dotnet": {"version": dotnet_version, "path": dotnet_path.relative_to(root).as_posix()},
    }
    if python_version != python_runtime_version:
        raise ReleaseCandidateError(
            "Python package metadata and icoder_sdk.__version__ diverge: "
            f"{python_version!r} != {python_runtime_version!r}"
        )

    normalized = {
        name: _normalize_beta(details["version"], source=name)
        for name, details in raw.items()
    }
    canonical = normalized["javascript"]
    if any(value != canonical for value in normalized.values()):
        rendered = ", ".join(f"{name}={value}" for name, value in normalized.items())
        raise ReleaseCandidateError(f"Public SDK versions diverge: {rendered}")

    for name, details in raw.items():
        details["normalized_version"] = normalized[name]
    return raw


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def collect_artifacts(
    artifact_dir: Path,
    *,
    output_path: Path,
    required_patterns: list[str],
) -> list[dict[str, Any]]:
    if not artifact_dir.is_dir():
        raise ReleaseCandidateError(f"Artifact directory does not exist: {artifact_dir}")
    for pattern in required_patterns:
        if not any(path.is_file() for path in artifact_dir.rglob(pattern)):
            raise ReleaseCandidateError(f"Required release artifact is missing: {pattern}")

    output_resolved = output_path.resolve()
    files = sorted(
        path
        for path in artifact_dir.rglob("*")
        if path.is_file() and path.resolve() != output_resolved
    )
    if not files:
        raise ReleaseCandidateError(f"No release artifacts found in {artifact_dir}")
    return [
        {
            "path": path.relative_to(artifact_dir).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in files
    ]


def _source_revision(root: Path) -> str:
    from_environment = os.environ.get("GITHUB_SHA", "").strip()
    if from_environment:
        return from_environment
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _source_tree_state(root: Path) -> str:
    """Report whether the manifest input tree differs from its Git HEAD.

    Release artifacts built from a dirty tree must not look reproducible from
    ``source_revision`` alone. This is evidence only: CI policy may still
    choose when to reject dirty build outputs.
    """
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return "dirty" if status.strip() else "clean"


def build_manifest(
    *,
    root: Path,
    artifact_dir: Path | None,
    output_path: Path,
    required_patterns: list[str],
    expected_version: str | None = None,
) -> dict[str, Any]:
    packages = read_sdk_versions(root)
    release_version = packages["javascript"]["normalized_version"]
    if expected_version is not None:
        normalized_expected = _normalize_beta(expected_version, source="expected release")
        if normalized_expected != release_version:
            raise ReleaseCandidateError(
                "Release tag/version does not match SDK metadata: "
                f"{normalized_expected} != {release_version}"
            )
    artifacts = (
        collect_artifacts(
            artifact_dir,
            output_path=output_path,
            required_patterns=required_patterns,
        )
        if artifact_dir is not None
        else []
    )
    return {
        "schema_version": MANIFEST_SCHEMA,
        "release_version": release_version,
        "source_revision": _source_revision(root),
        "source_tree_state": _source_tree_state(root),
        "packages": packages,
        "artifacts": artifacts,
        "publication": {
            "performed": False,
            "registries": [],
            "reason": "Release-candidate validation never publishes external packages.",
        },
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPOSITORY_ROOT)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--expected-version",
        help="Expected normalized beta version, normally derived from an rc-v* tag.",
    )
    parser.add_argument(
        "--require",
        action="append",
        default=[],
        help="Glob that must match below --artifact-dir; repeat for each expected artifact.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.require and args.artifact_dir is None:
            raise ReleaseCandidateError("--require needs --artifact-dir")
        manifest = build_manifest(
            root=args.root.resolve(),
            artifact_dir=args.artifact_dir.resolve() if args.artifact_dir else None,
            output_path=args.output.resolve(),
            required_patterns=args.require,
            expected_version=args.expected_version,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except ReleaseCandidateError as exc:
        print(f"RELEASE_CANDIDATE_INVALID: {exc}", file=sys.stderr)
        return 1
    print(
        "RELEASE_CANDIDATE_VALID: "
        f"version={manifest['release_version']} artifacts={len(manifest['artifacts'])} "
        f"manifest={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
