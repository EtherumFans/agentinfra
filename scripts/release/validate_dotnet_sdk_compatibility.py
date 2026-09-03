#!/usr/bin/env python3
"""Build aggregate-only evidence for the supported iCoDer .NET SDK targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SDK_ROOT = ROOT / "packages" / "icoder-dotnet"
SDK_PROJECT = SDK_ROOT / "src" / "Icoder.Sdk" / "Icoder.Sdk.csproj"
TEST_PROJECT = SDK_ROOT / "tests" / "Icoder.Sdk.Tests" / "Icoder.Sdk.Tests.csproj"
NETSTANDARD_CONSUMER = (
    SDK_ROOT
    / "tests"
    / "Icoder.Sdk.NetStandard20Consumer"
    / "Icoder.Sdk.NetStandard20Consumer.csproj"
)
NET462_CONSUMER = (
    SDK_ROOT / "tests" / "Icoder.Sdk.Net462Consumer" / "Icoder.Sdk.Net462Consumer.csproj"
)
REQUIRED_ASSETS = {
    "lib/netstandard2.0/Icoder.Sdk.dll",
    "lib/net8.0/Icoder.Sdk.dll",
    "lib/net10.0/Icoder.Sdk.dll",
}


class CompatibilityValidationError(RuntimeError):
    """A build or evidence invariant failed."""


def _run(dotnet: Path, *arguments: str) -> str:
    command = [str(dotnet), *arguments]
    result = subprocess.run(
        command,
        cwd=SDK_ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        tail = result.stdout[-4000:]
        raise CompatibilityValidationError(
            f"dotnet command failed with exit {result.returncode}: "
            f"{' '.join(arguments[:3])}\n{tail}"
        )
    return result.stdout


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _test_counters(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    counters = next(
        (node for node in root.iter() if node.tag.rsplit("}", 1)[-1] == "Counters"),
        None,
    )
    if counters is None:
        raise CompatibilityValidationError(f"TRX counters are missing: {path}")
    values = {
        name: int(counters.attrib.get(name, "0"))
        for name in ("total", "executed", "passed", "failed")
    }
    if values["total"] <= 0 or values["failed"] != 0:
        raise CompatibilityValidationError(f"test counters are not passing: {values}")
    return values


def validate(dotnet: Path, output_dir: Path) -> Path:
    if not dotnet.is_file():
        raise CompatibilityValidationError(f"dotnet executable not found: {dotnet}")
    output_dir.mkdir(parents=True, exist_ok=True)
    test_results = output_dir / "test-results"
    package_dir = output_dir / "packages"
    for path in (test_results, package_dir):
        if path.exists():
            shutil.rmtree(path)
        path.mkdir(parents=True)

    _run(dotnet, "restore", str(TEST_PROJECT), "--nologo")
    _run(dotnet, "restore", str(SDK_PROJECT), "--nologo")
    runtime_tests: dict[str, dict[str, int]] = {}
    for framework in ("net8.0", "net10.0"):
        framework_results = test_results / framework
        framework_results.mkdir()
        _run(
            dotnet,
            "test",
            str(TEST_PROJECT),
            "-c",
            "Release",
            "-f",
            framework,
            "--no-restore",
            "--nologo",
            "--logger",
            f"trx;LogFileName={framework}.trx",
            "--results-directory",
            str(framework_results),
        )
        runtime_tests[framework] = _test_counters(framework_results / f"{framework}.trx")

    _run(dotnet, "build", str(NETSTANDARD_CONSUMER), "-c", "Release", "--nologo")
    _run(dotnet, "build", str(NET462_CONSUMER), "-c", "Release", "--nologo")
    _run(
        dotnet,
        "pack",
        str(SDK_PROJECT),
        "-c",
        "Release",
        "--no-restore",
        "--nologo",
        "-o",
        str(package_dir),
    )

    primary = sorted(package_dir.glob("*.nupkg"))
    symbols = sorted(package_dir.glob("*.snupkg"))
    if len(primary) != 1 or len(symbols) != 1:
        raise CompatibilityValidationError(
            f"expected one nupkg and one snupkg, got {len(primary)} and {len(symbols)}"
        )
    with zipfile.ZipFile(primary[0]) as archive:
        names = set(archive.namelist())
        nuspec_names = [name for name in names if name.endswith(".nuspec")]
        if len(nuspec_names) != 1:
            raise CompatibilityValidationError(
                f"expected one nuspec, got {len(nuspec_names)}"
            )
        nuspec_root = ET.fromstring(archive.read(nuspec_names[0]))
    missing = sorted(REQUIRED_ASSETS - names)
    framework_assets = sorted(
        name for name in names if name.startswith("lib/") and name.endswith("/Icoder.Sdk.dll")
    )
    if missing or set(framework_assets) != REQUIRED_ASSETS:
        raise CompatibilityValidationError(
            f"NuGet framework assets diverge; missing={missing}, actual={framework_assets}"
        )
    dependency_groups: dict[str, dict[str, str]] = {}
    for group in nuspec_root.iter():
        if group.tag.rsplit("}", 1)[-1] != "group":
            continue
        target = group.attrib.get("targetFramework", "")
        dependency_groups[target] = {
            dependency.attrib.get("id", ""): dependency.attrib.get("version", "")
            for dependency in group
            if dependency.tag.rsplit("}", 1)[-1] == "dependency"
        }
    expected_netstandard_dependencies = {
        "System.Net.Http.Json": "10.0.11",
        "System.Text.Json": "10.0.11",
    }
    if dependency_groups.get(".NETStandard2.0") != expected_netstandard_dependencies:
        raise CompatibilityValidationError(
            "netstandard2.0 NuGet dependencies diverge: "
            f"{dependency_groups.get('.NETStandard2.0')}"
        )

    version = ET.parse(SDK_PROJECT).getroot().findtext(".//Version", default="").strip()
    report = {
        "schema_version": "icoder.dotnet-sdk-compatibility/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "passed",
        "sdk_version": version,
        "dotnet_sdk": _run(dotnet, "--version").strip(),
        "runtime_tests": runtime_tests,
        "compile_consumers": {
            "netstandard2.0": {"status": "passed", "runtime_executed": False},
            "net462": {
                "status": "passed",
                "runtime_executed": False,
                "reference_assemblies": "Microsoft.NETFramework.ReferenceAssemblies.net462",
            },
        },
        "nuget": {
            "framework_assets": framework_assets,
            "netstandard2.0_dependencies": expected_netstandard_dependencies,
            "package": {
                "name": primary[0].name,
                "size_bytes": primary[0].stat().st_size,
                "sha256": _sha256(primary[0]),
            },
            "symbols": {
                "name": symbols[0].name,
                "size_bytes": symbols[0].stat().st_size,
                "sha256": _sha256(symbols[0]),
            },
        },
        "claims": {
            "source_and_package_compatibility_proven": True,
            "net462_compile_compatibility_proven": True,
            "net462_runtime_integration_proven": False,
            "nuget_publication_proven": False,
            "corti_hosted_interoperability_proven": False,
            "clinical_production_readiness_proven": False,
        },
    }
    report_path = output_dir / "dotnet_sdk_compatibility.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dotnet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report_path = validate(args.dotnet.resolve(), args.output_dir.resolve())
    print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
