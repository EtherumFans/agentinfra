"""Build tamper-evident development evidence for roadmap phases 3 through 5."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.offline_evaluation import validate_offline_report  # noqa: E402


SOURCES = {
    "infrastructure_adapters": ROOT / "backend/app/services/clinical_model_infrastructure.py",
    "offline_evaluator": ROOT / "backend/app/services/offline_evaluation.py",
    "offline_suite": ROOT / "backend/evaluations/agent_hub_26_v1.json",
    "memory_api": ROOT / "backend/app/api/agent_connectors.py",
    "experts_api": ROOT / "backend/app/api/experts.py",
    "stt_api": ROOT / "backend/app/api/v2_tools_stt.py",
    "javascript_agents": ROOT / "packages/icoder-sdk/src/resources/agents.ts",
    "javascript_stt": ROOT / "packages/icoder-sdk/src/resources/speech-to-text.ts",
    "python_agents": ROOT / "packages/icoder-python/icoder_sdk/resources/agents.py",
    "python_stt": ROOT / "packages/icoder-python/icoder_sdk/resources/speech_to_text.py",
    "dotnet_connectors": ROOT / "packages/icoder-dotnet/src/Icoder.Sdk/AgentConnectorsResource.cs",
    "dotnet_experts": ROOT / "packages/icoder-dotnet/src/Icoder.Sdk/ExpertsResource.cs",
    "dotnet_stt": ROOT / "packages/icoder-dotnet/src/Icoder.Sdk/SpeechToTextResource.cs",
    "experts_ui": ROOT / "frontend/src/pages/ExpertsPage.tsx",
    "stt_ui": ROOT / "frontend/src/pages/SpeechToTextPage.tsx",
    "agent_ui": ROOT / "frontend/src/pages/AgentDetailPage.tsx",
}


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _junit(path: Path) -> dict[str, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    return {
        key: sum(int(float(suite.attrib.get(key, "0"))) for suite in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase3-junit", type=Path, required=True)
    parser.add_argument("--phase4-junit", type=Path, required=True)
    parser.add_argument("--phase5-junit", type=Path, required=True)
    parser.add_argument("--offline-report", type=Path, required=True)
    parser.add_argument("--build-status", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    phase3 = _junit(args.phase3_junit.resolve())
    phase4 = _junit(args.phase4_junit.resolve())
    phase5 = _junit(args.phase5_junit.resolve())
    offline = json.loads(args.offline_report.resolve().read_text(encoding="utf-8"))
    validate_offline_report(offline)
    builds = json.loads(args.build_status.resolve().read_text(encoding="utf-8-sig"))
    required_builds = ("javascript_sdk", "python_sdk", "frontend")
    tests_clean = all(
        item["tests"] > 0 and item["failures"] == 0 and item["errors"] == 0
        for item in (phase3, phase4, phase5)
    )
    passed = bool(
        tests_clean
        and offline.get("passed") is True
        and offline.get("agent_count") == 26
        and offline.get("passed_case_count") == 26
        and all(builds.get(name) == "passed" for name in required_builds)
    )
    report: dict[str, object] = {
        "schema_version": "icoder.roadmap-phases-3-5-evidence/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "development_scope_complete": passed,
        "corti_capability_parity_proven": False,
        "production_ready": False,
        "patient_data_used": False,
        "credentials_used": False,
        "phase3_infrastructure_adapter_tests": phase3,
        "phase4_offline_platform_tests": phase4,
        "phase4_agent_count": offline["agent_count"],
        "phase4_passed_case_count": offline["passed_case_count"],
        "phase4_contract_pass_rate": offline["contract_pass_rate"],
        "clinical_accuracy_proven": offline["clinical_accuracy_proven"],
        "phase5_readiness_api_tests": phase5,
        "builds": builds,
        "dotnet_build_required_before_publish": builds.get("dotnet_sdk") != "passed",
        "external_cloud_integrations_live_verified": False,
        "external_mcp_live_verified": False,
        "stt_live_health_verified": False,
        "limitations": [
            "Cloud KMS, object storage, scanner and deployment controllers were tested through injected contracts only.",
            "The 26-Agent reference suite proves contract and evidence conformance, not independent clinical accuracy.",
            "External MCP, multilingual clinical STT and hospital-system integrations require credentialed target environments.",
            "A .NET SDK publish remains blocked until the .NET toolchain is available and its tests pass.",
        ],
        "source_sha256": {name: _sha(path) for name, path in SOURCES.items()},
    }
    report["report_sha256"] = hashlib.sha256(_canonical(report)).hexdigest()
    args.output.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.output.resolve().write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not passed:
        raise RuntimeError("ROADMAP_PHASES_3_TO_5_EVIDENCE_INVALID")
    print("Roadmap phases 3-5 development evidence validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
