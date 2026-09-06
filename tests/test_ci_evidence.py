from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / "ci" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SUMMARY = load_script("summarize_integration_evidence")
GATE = load_script("verify_release_ci_evidence")
SHA = "a" * 40
REPO = "example/product"


def needs(live="success", enabled="true"):
    result = {name: {"result": "success"} for name in SUMMARY.OFFLINE_JOBS}
    result["agent-hub-offline"]["outputs"] = {"live_enabled": enabled}
    result["agent-hub-live-e2e"] = {"result": live}
    return result


@pytest.mark.parametrize("result,enabled,expected", [
    ("success", "true", "passed"), ("skipped", "false", "not_executed"),
    ("failure", "true", "failed"), ("cancelled", "true", "failed"),
    ("skipped", "true", "failed"), ("missing", "false", "failed"),
    ("success", "false", "failed"),
])
def test_execution_status_never_promotes_skips(result, enabled, expected):
    report = SUMMARY.summarize(needs(result, enabled), revision=SHA, run_id="1", attempt="2")
    assert report["live_status"] == expected
    assert report["release_eligible"] is (expected == "passed")
    assert report["clinical_quality_proven"] is False


def test_missing_or_failed_offline_job_blocks_evidence():
    for value in ("failure", "cancelled", "skipped", "missing"):
        data = needs("skipped", "false")
        data["integration"]["result"] = value
        report = SUMMARY.summarize(data, revision=SHA, run_id="1", attempt="1")
        assert report["live_status"] == "failed"
        assert not report["release_eligible"]


def test_summary_cli_writes_machine_and_human_evidence(tmp_path, monkeypatch):
    for key, value in {"CI_NEEDS_JSON": json.dumps(needs("skipped", "false")),
                       "GITHUB_SHA": SHA, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "2",
                       "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md")}.items():
        monkeypatch.setenv(key, value)
    output = tmp_path / "result.json"
    assert SUMMARY.main(["--output", str(output)]) == 0
    report = json.loads(output.read_text())
    assert report["source_revision"] == SHA and report["run_attempt"] == "2"
    assert report["live_status"] == "not_executed"
    assert "not_executed" in (tmp_path / "summary.md").read_text()
    monkeypatch.setenv("CI_NEEDS_JSON", json.dumps(needs("failure", "true")))
    assert SUMMARY.main(["--output", str(output)]) == 1


def run(workflow="ci-pr.yml", **overrides):
    return {"id": 10, "head_sha": SHA, "path": f".github/workflows/{workflow}",
            "head_repository": {"full_name": REPO}, "event": "push", "run_attempt": 1,
            "status": "completed", "conclusion": "success", "html_url": "https://github.com/run/10",
            **overrides}


def jobs(workflow, run_id=10):
    return [{"name": name, "id": index + 100, "run_id": run_id, "head_sha": SHA,
             "status": "completed", "conclusion": "success", "html_url": "https://github.com/job/100",
             "steps": [{"name": step, "status": "completed", "conclusion": "success"} for step in steps]}
            for index, (name, steps) in enumerate(GATE.REQUIRED_JOBS[workflow].items())]


@pytest.mark.parametrize("override", [
    {"head_sha": "b" * 40}, {"event": "pull_request"}, {"event": "pull_request_target"},
    {"head_repository": {"full_name": "fork/product"}}, {"path": ".github/workflows/other.yml"},
])
def test_untrusted_or_other_commit_runs_are_rejected(override):
    with pytest.raises(GATE.EvidenceError, match="no trusted run"):
        GATE.select_run([run(**override)], repository=REPO, revision=SHA, workflow="ci-pr.yml")


@pytest.mark.parametrize("state", ["failure", "cancelled", "skipped", "timed_out", None])
def test_latest_failure_cannot_fall_back_to_old_green(state):
    with pytest.raises(GATE.EvidenceError, match="newest run"):
        GATE.select_run([run(), run(id=11, conclusion=state)], repository=REPO, revision=SHA, workflow="ci-pr.yml")


@pytest.mark.parametrize("state", ["skipped", "failure", "cancelled", None])
def test_live_job_must_really_have_succeeded(state):
    data = jobs("ci-integration.yml")
    next(job for job in data if job["name"] == "Agent Hub 26-Agent live E2E")["conclusion"] = state
    with pytest.raises(GATE.EvidenceError, match="not executed successfully"):
        GATE.validate_jobs(data, run=run("ci-integration.yml"), workflow="ci-integration.yml", revision=SHA)


def test_required_frontend_test_step_cannot_be_missing_or_skipped():
    for conclusion in ("missing", "skipped", "failure"):
        data = jobs("ci-pr.yml")
        frontend = next(job for job in data if job["name"] == "Frontend (TS + Build)")
        if conclusion == "missing":
            frontend["steps"] = []
        else:
            frontend["steps"][0]["conclusion"] = conclusion
        with pytest.raises(GATE.EvidenceError, match="required step"):
            GATE.validate_jobs(data, run=run(), workflow="ci-pr.yml", revision=SHA)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "wrong_sha", "wrong_run"])
def test_incomplete_or_mismatched_jobs_are_rejected(mutation):
    data = jobs("ci-pr.yml")
    if mutation == "missing":
        data.pop()
    elif mutation == "duplicate":
        data.append(deepcopy(data[0]))
    elif mutation == "wrong_sha":
        data[0]["head_sha"] = "b" * 40
    else:
        data[0]["run_id"] = 99
    with pytest.raises(GATE.EvidenceError):
        GATE.validate_jobs(data, run=run(), workflow="ci-pr.yml", revision=SHA)


class FakeGitHub:
    def pages(self, path, key):
        if key == "workflow_runs":
            workflow = path.split("/workflows/")[1].split("/")[0]
            self.workflow = workflow
            return [run(workflow)]
        assert "filter=latest" in path
        return jobs(self.workflow)

    def get(self, path):
        return run(self.workflow)


def test_complete_same_commit_evidence_passes_without_network():
    report = GATE.collect(FakeGitHub(), repository=REPO, revision=SHA)
    assert report["status"] == report["live_e2e_status"] == "passed"
    assert report["source_revision"] == SHA
    assert len(report["workflows"]) == 3
    assert report["clinical_quality_proven"] is False
    GATE.validate_record(report, repository=REPO, revision=SHA)


@pytest.mark.parametrize("field,value", [("source_revision", "b" * 40), ("status", "blocked"),
    ("repository", "fork/product"), ("live_e2e_status", "not_executed"),
    ("workflows", []), ("clinical_quality_proven", True)])
def test_downloaded_evidence_cannot_be_stale_or_incomplete(field, value):
    report = GATE.collect(FakeGitHub(), repository=REPO, revision=SHA)
    report[field] = value
    with pytest.raises(GATE.EvidenceError):
        GATE.validate_record(report, repository=REPO, revision=SHA)


def test_downloaded_evidence_requires_frontend_steps():
    report = GATE.collect(FakeGitHub(), repository=REPO, revision=SHA)
    job = next(row for row in report["workflows"][0]["jobs"] if row["name"] == "Frontend (TS + Build)")
    job["required_steps"] = []
    with pytest.raises(GATE.EvidenceError):
        GATE.validate_record(report, repository=REPO, revision=SHA)


@pytest.mark.parametrize("field", ["run_id", "run_attempt"])
def test_downloaded_evidence_requires_run_provenance(field):
    report = GATE.collect(FakeGitHub(), repository=REPO, revision=SHA)
    del report["workflows"][0][field]
    with pytest.raises(GATE.EvidenceError, match="provenance"):
        GATE.validate_record(report, repository=REPO, revision=SHA)


def test_artifact_revalidation_cli_needs_no_token(tmp_path, monkeypatch):
    report = GATE.collect(FakeGitHub(), repository=REPO, revision=SHA)
    source, output = tmp_path / "input.json", tmp_path / "output.json"
    source.write_text(json.dumps(report))
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert GATE.main(["--input", str(source), "--output", str(output)]) == 0
    assert json.loads(output.read_text())["status"] == "passed"


def test_rerun_during_snapshot_is_rejected():
    class RacingGitHub(FakeGitHub):
        def get(self, path):
            return run(self.workflow, run_attempt=2)
    with pytest.raises(GATE.EvidenceError, match="changed"):
        GATE.collect(RacingGitHub(), repository=REPO, revision=SHA)


def test_api_pagination_is_not_silently_truncated():
    client = GATE.GitHub(REPO, "test-token-not-saved")
    calls = []
    def get(path):
        calls.append(path)
        return {"jobs": [{"id": 1}] * (100 if len(calls) == 1 else 1)}
    client.get = get
    assert len(client.pages("/jobs?filter=latest", "jobs")) == 101
    assert calls[-1].endswith("&per_page=100&page=2")


@pytest.mark.parametrize("error,count", [(HTTPError("https://api.github.com", 503, "busy", {}, None), 3),
    (HTTPError("https://api.github.com", 401, "unauthorized", {}, None), 1),
    (URLError("offline"), 3)])
def test_api_retry_is_bounded_and_auth_errors_do_not_retry(monkeypatch, error, count):
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise error
    monkeypatch.setattr(GATE, "urlopen", fail)
    monkeypatch.setattr(GATE.time, "sleep", lambda seconds: None)
    with pytest.raises(GATE.EvidenceError, match="evidence unavailable") as caught:
        GATE.GitHub(REPO, "private-test-token").get("/actions/runs")
    assert "private-test-token" not in str(caught.value)
    assert len(calls) == count


def test_gate_cli_blocks_missing_configuration_without_secret_leak(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("GITHUB_SHA", SHA)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    output = tmp_path / "gate.json"
    assert GATE.main(["--output", str(output)]) == 1
    assert json.loads(output.read_text())["status"] == "blocked"


def workflow(name):
    return yaml.safe_load((ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8"))


def test_workflows_match_required_jobs_and_steps():
    for name, required in GATE.REQUIRED_JOBS.items():
        actual = {job["name"]: job for job in workflow(name)["jobs"].values()}
        for job_name, step_names in required.items():
            assert job_name in actual
            steps = actual[job_name]["steps"]
            for step_name in step_names:
                selected = next(step for step in steps if step.get("name") == step_name)
                assert "continue-on-error" not in selected
            assert "continue-on-error" not in actual[job_name]


def test_frontend_unit_evidence_is_always_retained_and_tests_are_blocking():
    for name in ("ci-pr.yml", "release-candidate.yml"):
        steps = workflow(name)["jobs"]["frontend"]["steps"]
        unit = next(step for step in steps if step.get("name") == "Frontend unit tests")
        assert "npm test -- --run" in unit["run"] and "--reporter=junit" in unit["run"]
        assert "continue-on-error" not in unit and "if" not in unit
        upload = next(step for step in steps if step.get("name") == "Upload frontend unit evidence")
        assert upload["if"] == "always()"
        assert upload["with"]["if-no-files-found"] == "error"


def test_live_is_a_real_skipped_job_and_release_cannot_bypass_gate():
    integration = workflow("ci-integration.yml")["jobs"]
    assert integration["agent-hub-live-e2e"]["if"] == "needs.agent-hub-offline.outputs.live_enabled == 'true'"
    assert integration["ci-evidence"]["if"] == "always()"
    assert "agent-hub-live-e2e" in integration["ci-evidence"]["needs"]
    release = workflow("release-candidate.yml")["jobs"]
    assert release["version-contract"]["needs"] == "ci-evidence"
    assert "ci-evidence" in release["assemble"]["needs"]
    gate = release["ci-evidence"]
    assert gate["permissions"] == {"contents": "read", "actions": "read"}
    assert "if" not in gate and "continue-on-error" not in gate
    assemble = "\n".join(step.get("run", "") for step in release["assemble"]["steps"])
    assert "--require 'release-ci-evidence.json'" in assemble
    assert "--require 'frontend-unit.xml'" in assemble
    assert "--input release-candidate/artifacts/release-ci-evidence.json" in assemble
