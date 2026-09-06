"""Record offline and live CI outcomes separately; never turn a skip into a pass."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


OFFLINE_JOBS = ("integration", "medcoder-validation", "agent-hub-offline")


def summarize(needs: dict, *, revision: str, run_id: str, attempt: str) -> dict:
    offline = {name: needs.get(name, {}).get("result", "missing") for name in OFFLINE_JOBS}
    live_result = needs.get("agent-hub-live-e2e", {}).get("result", "missing")
    enabled = needs.get("agent-hub-offline", {}).get("outputs", {}).get("live_enabled")
    offline_passed = all(value == "success" for value in offline.values())
    if live_result == "success" and enabled == "true" and offline_passed:
        live = "passed"
    elif live_result == "skipped" and enabled == "false" and offline_passed:
        live = "not_executed"
    else:
        live = "failed"
    return {
        "schema_version": "icoder/integration-execution-evidence/v1",
        "source_revision": revision,
        "run_id": run_id,
        "run_attempt": attempt,
        "offline_jobs": offline,
        "offline_passed": offline_passed,
        "live_status": live,
        "live_job_result": live_result,
        "release_eligible": offline_passed and live == "passed",
        "clinical_quality_proven": False,
        "excluded_default_markers": ["heavy", "retrieval", "infra"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = summarize(
        json.loads(os.environ["CI_NEEDS_JSON"]),
        revision=os.environ["GITHUB_SHA"],
        run_id=os.environ["GITHUB_RUN_ID"],
        attempt=os.environ["GITHUB_RUN_ATTEMPT"],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    summary = (
        "## Integration execution evidence\n\n"
        f"- Commit: `{report['source_revision']}`\n"
        f"- Offline gates passed: `{report['offline_passed']}`\n"
        f"- Real Agent E2E: **{report['live_status']}**\n"
        f"- Eligible as release evidence: `{report['release_eligible']}`\n\n"
        "`not_executed` means no live credential was available; it is not a live pass.\n"
        "Default pytest excludes heavy/retrieval/infra; clinical quality is not proven.\n"
    )
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write(summary)
    print(summary)
    return 0 if report["offline_passed"] and report["live_status"] != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
