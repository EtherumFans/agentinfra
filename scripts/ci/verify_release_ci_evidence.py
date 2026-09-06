"""Read GitHub Actions evidence for the exact release commit; fail closed on gaps.

Only the newest same-repository, non-PR run of each workflow is eligible.
An older green run must never hide a newer failure, cancellation or pending run.
No credentials, logs, clinical payloads or external artifact contents are saved.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


SCHEMA = "icoder/release-ci-evidence/v1"
REQUIRED_JOBS = {
    "ci-pr.yml": {
        "P1 PHI / Multi-tenant Release Gate": ["Run PHI, RLS, migration, rotation and artifact gates"],
        "Frontend (TS + Build)": ["Frontend unit tests"],
        "Backend (Unit)": ["Unit tests (excludes integration / e2e / regression / e2e_product)"],
        "JS SDK": [],
        "Python SDK": [],
        ".NET SDK (netstandard2.0 + net8.0 + net10.0)": ["Test native runtime targets"],
        "OpenAPI + Deployment Preflight": ["Cross-language release version contract"],
        "Web Components": [],
    },
    "ci-integration.yml": {
        "Integration / Regression / E2E": ["Integration tests", "Regression tests", "Backend e2e tests", "e2e_product tests"],
        "MedCodER registry / index smoke (no quality claim)": [],
        "Agent Hub offline contracts (no live claim)": ["Validate all Hub-visible Packs without network access"],
        "Agent Hub 26-Agent live E2E": [
            "Verify live configuration, schema and Registry readiness",
            "Real-provider canonical A2A E2E",
            "Run 26 happy-path and 26 adversarial Agent cases",
            "Run two-round Agent stability benchmark",
            "Validate reference semantics and assemble live evidence bundle",
        ],
        "CI evidence summary (live status explicit)": ["Record execution evidence"],
    },
    "e2e.yml": {"Playwright E2E": ["Run Playwright tests"]},
}
TRUSTED_EVENTS = {"push", "schedule", "workflow_dispatch"}


class EvidenceError(ValueError):
    pass


def select_run(runs: list[dict], *, repository: str, revision: str, workflow: str) -> dict:
    candidates = [run for run in runs if (
        run.get("head_sha") == revision
        and run.get("path") == f".github/workflows/{workflow}"
        and run.get("event") in TRUSTED_EVENTS
        and (run.get("head_repository") or {}).get("full_name") == repository
    )]
    if not candidates:
        raise EvidenceError(f"{workflow}: no trusted run for the release commit")
    latest = max(candidates, key=lambda run: int(run["id"]))
    if latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise EvidenceError(f"{workflow}: newest run is not completed/success")
    return latest


def validate_jobs(jobs: list[dict], *, run: dict, workflow: str, revision: str) -> list[dict]:
    evidence = []
    for name, steps in REQUIRED_JOBS[workflow].items():
        matches = [job for job in jobs if job.get("name") == name]
        if len(matches) != 1:
            raise EvidenceError(f"{workflow}: required job missing or ambiguous: {name}")
        job = matches[0]
        if (job.get("head_sha") != revision or job.get("run_id") != run["id"]
                or job.get("status") != "completed" or job.get("conclusion") != "success"):
            raise EvidenceError(f"{workflow}: job not executed successfully for this commit: {name}")
        for step_name in steps:
            matched = [step for step in job.get("steps", []) if step.get("name") == step_name]
            if (len(matched) != 1 or matched[0].get("status") != "completed"
                    or matched[0].get("conclusion") != "success"):
                raise EvidenceError(f"{workflow}: required step missing, skipped or failed: {step_name}")
        evidence.append({
            "name": name, "job_id": job["id"], "conclusion": "success",
            "required_steps": steps, "url": job["html_url"],
        })
    return evidence


class GitHub:
    def __init__(self, repository: str, token: str):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise EvidenceError("Invalid repository identifier")
        self.base = f"https://api.github.com/repos/{repository}"
        self.token = token

    def get(self, path: str) -> dict:
        request = Request(self.base + path, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        for attempt in range(3):
            try:
                with urlopen(request, timeout=30) as response:
                    return json.load(response)
            except HTTPError as exc:
                if exc.code not in {429, 500, 502, 503, 504} or attempt == 2:
                    raise EvidenceError(f"GitHub evidence unavailable (HTTP {exc.code})") from None
            except (URLError, TimeoutError):
                if attempt == 2:
                    raise EvidenceError("GitHub evidence unavailable (network error)") from None
            time.sleep(2 ** attempt)
        raise EvidenceError("GitHub evidence unavailable")  # pragma: no cover

    def pages(self, path: str, key: str) -> list[dict]:
        rows = []
        separator = "&" if "?" in path else "?"
        for page in range(1, 11):
            payload = self.get(f"{path}{separator}per_page=100&page={page}")
            batch = payload.get(key)
            if not isinstance(batch, list):
                raise EvidenceError("Malformed GitHub evidence response")
            rows.extend(batch)
            if len(batch) < 100:
                return rows
        raise EvidenceError("GitHub evidence exceeds bounded pagination; narrow the run history")


def collect(client: GitHub, *, repository: str, revision: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise EvidenceError("A full 40-character source revision is required")
    workflows = []
    for workflow in REQUIRED_JOBS:
        runs = client.pages(
            f"/actions/workflows/{workflow}/runs?{urlencode({'head_sha': revision})}",
            "workflow_runs",
        )
        run = select_run(runs, repository=repository, revision=revision, workflow=workflow)
        # 'latest' preserves successful jobs reused by rerun-failed-jobs, while
        # selecting the latest execution of every job rather than old failures.
        jobs = client.pages(f"/actions/runs/{run['id']}/jobs?filter=latest", "jobs")
        verified = validate_jobs(jobs, run=run, workflow=workflow, revision=revision)
        # Detect a rerun started while the evidence snapshot was being read.
        fresh = client.get(f"/actions/runs/{run['id']}")
        if (fresh.get("run_attempt") != run.get("run_attempt")
                or fresh.get("status") != "completed" or fresh.get("conclusion") != "success"):
            raise EvidenceError(f"{workflow}: run changed during evidence collection")
        workflows.append({
            "workflow": workflow, "run_id": run["id"], "run_attempt": run["run_attempt"],
            "url": run["html_url"], "jobs": verified,
        })
    return {
        "schema_version": SCHEMA, "status": "passed", "repository": repository,
        "source_revision": revision, "checked_at": datetime.now(timezone.utc).isoformat(),
        "workflows": workflows, "live_e2e_status": "passed", "clinical_quality_proven": False,
    }


def validate_record(report: dict, *, repository: str, revision: str) -> None:
    """Recheck the downloaded gate artifact before RC assembly (not attestation)."""
    if (report.get("schema_version") != SCHEMA or report.get("status") != "passed"
            or report.get("repository") != repository or report.get("source_revision") != revision
            or report.get("live_e2e_status") != "passed" or report.get("clinical_quality_proven") is not False):
        raise EvidenceError("Release CI artifact is not valid passed evidence for this commit")
    workflows = report.get("workflows", [])
    if len(workflows) != len(REQUIRED_JOBS):
        raise EvidenceError("Release CI artifact has missing or duplicate workflows")
    for workflow, required in REQUIRED_JOBS.items():
        matches = [row for row in workflows if row.get("workflow") == workflow]
        if len(matches) != 1:
            raise EvidenceError("Release CI artifact has missing or duplicate workflows")
        if any(type(matches[0].get(key)) is not int or matches[0][key] <= 0
               for key in ("run_id", "run_attempt")):
            raise EvidenceError("Release CI artifact has missing run provenance")
        recorded = matches[0].get("jobs", [])
        if len(recorded) != len(required):
            raise EvidenceError("Release CI artifact has incomplete job evidence")
        for name, steps in required.items():
            found = [job for job in recorded if job.get("name") == name]
            if (len(found) != 1 or found[0].get("conclusion") != "success"
                    or found[0].get("required_steps") != steps
                    or type(found[0].get("job_id")) is not int or found[0]["job_id"] <= 0):
                raise EvidenceError("Release CI artifact has incomplete job/step evidence")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path, help="Revalidate a downloaded gate artifact without network access")
    args = parser.parse_args(argv)
    try:
        repository, revision = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
        if args.input:
            report = json.loads(args.input.read_text(encoding="utf-8"))
        else:
            report = collect(GitHub(repository, os.environ["GITHUB_TOKEN"]), repository=repository, revision=revision)
        validate_record(report, repository=repository, revision=revision)
    except (EvidenceError, KeyError, TypeError, AttributeError, OSError, json.JSONDecodeError) as exc:
        message = str(exc) if isinstance(exc, EvidenceError) else "Missing or malformed CI evidence"
        report = {"schema_version": SCHEMA, "status": "blocked", "reason": message}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    message = f"Release CI evidence: {report['status']}"
    if report["status"] != "passed":
        message += f" - {report['reason']}"
    print(message)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as stream:
            stream.write(f"## {message}\n\nNo clinical-quality or production approval is implied.\n")
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
