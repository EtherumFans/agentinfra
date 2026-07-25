"""HIS/EMR Simulator runner.

Executes scenarios from scenarios.py and produces structured evidence.
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import Any, Iterator

from .scenarios import SCENARIO_REGISTRY


def _now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SimulatorRunner:
    """Runs scenarios; collects step results.

    Two modes:
      - DRY (default): no network call; just emit what would-be sent + asserted outcome
      - LIVE: HTTP POST/GET/DELETE to ICODER_PILOT_URL using urllib (no third-party dep)
    """

    def __init__(self, mode: str = "DRY", base_url: str | None = None, jwt: str | None = None):
        self.mode = mode.upper()
        self.base_url = (base_url or os.environ.get("ICODER_PILOT_URL") or "").rstrip("/")
        self.jwt = jwt or os.environ.get("ICODER_PILOT_JWT")
        self.results: list[dict[str, Any]] = []
        self.scenario_outcomes: list[dict[str, Any]] = []

    def _headers(self, step_headers: dict) -> dict:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.jwt:
            h["Authorization"] = f"Bearer {self.jwt}"
        h.update(step_headers)
        return h

    def _do_live_call(self, action: str, path: str, headers: dict, body: dict | None) -> tuple[int, dict | None, str]:
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=action, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body_text = resp.read().decode("utf-8", errors="replace")
                try:
                    return resp.status, json.loads(body_text), ""
                except json.JSONDecodeError:
                    return resp.status, None, body_text[:500]
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace") if e.fp else ""
            try:
                return e.code, json.loads(body_text), ""
            except json.JSONDecodeError:
                return e.code, None, body_text[:500]
        except (urllib.error.URLError, OSError) as e:
            return 0, None, str(e)

    def run_step(self, scenario_id: int, step: dict, captured_context: dict) -> dict:
        """Run a single step. `captured_context` lets later steps reference earlier outputs."""
        # Resolve path templating like {context_id}
        path = step["path"]
        for k, v in captured_context.items():
            path = path.replace("{" + k + "}", str(v))

        record = {
            "scenario_id": scenario_id,
            "step": step["step"],
            "action": step["action"],
            "path": path,
            "expect_status": step.get("expect_status"),
            "expect_error_code": step.get("expect_error_code"),
            "note": step.get("note", ""),
            "started_at": _now_iso(),
            "mode": self.mode,
        }

        if step["action"] == "WAIT":
            wait = step.get("wait_seconds", 0)
            if self.mode == "LIVE":
                time.sleep(min(wait, 5))  # cap live waits at 5s to keep CI tractable
            record["status_code"] = 0
            record["response_body"] = None
            record["error_text"] = f"waited {wait}s"
            record["verdict"] = "WAIT_OK"
            record["finished_at"] = _now_iso()
            return record

        if self.mode == "DRY":
            record["status_code"] = step.get("expect_status", 0)
            record["response_body"] = None
            record["error_text"] = ""
            record["verdict"] = "DRY_PASS"
        else:
            status, body, err = self._do_live_call(step["action"], path, self._headers(step.get("headers", {})), step.get("body"))
            record["status_code"] = status
            record["response_body"] = body
            record["error_text"] = err
            if step.get("expect_status") and status == step["expect_status"]:
                record["verdict"] = "PASS"
            elif step.get("expect_status"):
                record["verdict"] = f"FAIL_expected_{step['expect_status']}_got_{status}"
            else:
                record["verdict"] = f"NO_EXPECT_status_{status}"

            # capture created context_id for later steps
            if body and isinstance(body, dict):
                if "context_id" in body:
                    captured_context["context_id"] = body["context_id"]
                if "webhook_id" in body:
                    captured_context["webhook_id"] = body["webhook_id"]
                if "id" in body and step["path"].endswith("patient-context"):
                    captured_context["context_id"] = body["id"]

        record["finished_at"] = _now_iso()
        return record

    def run_scenario(self, scenario_id: int) -> dict:
        title, gen = SCENARIO_REGISTRY[scenario_id]
        captured: dict[str, Any] = {}
        steps_run = []
        for step in gen():
            r = self.run_step(scenario_id, step, captured)
            steps_run.append(r)
            self.results.append(r)

        verdicts = [s["verdict"] for s in steps_run if s["action"] != "WAIT"]
        if all(v in ("PASS", "DRY_PASS") for v in verdicts):
            scenario_verdict = "PASS"
        elif any(v.startswith("FAIL") for v in verdicts):
            scenario_verdict = "FAIL"
        else:
            scenario_verdict = "PARTIAL"

        outcome = {
            "scenario_id": scenario_id,
            "title": title,
            "verdict": scenario_verdict,
            "steps": steps_run,
        }
        self.scenario_outcomes.append(outcome)
        return outcome

    def summary(self) -> dict:
        passed = sum(1 for o in self.scenario_outcomes if o["verdict"] == "PASS")
        failed = sum(1 for o in self.scenario_outcomes if o["verdict"] == "FAIL")
        partial = sum(1 for o in self.scenario_outcomes if o["verdict"] == "PARTIAL")
        return {
            "mode": self.mode,
            "base_url": self.base_url or "(dry-run)",
            "ran_at": _now_iso(),
            "total_scenarios": len(self.scenario_outcomes),
            "pass": passed,
            "fail": failed,
            "partial": partial,
            "verdict": "HIS_EMR_SIMULATOR_VERIFIED" if passed == 16 and self.mode == "LIVE" else (
                "HIS_EMR_SIMULATOR_DRY_VERIFIED" if passed == 16 and self.mode == "DRY" else
                "HIS_EMR_SIMULATOR_PARTIAL"
            ),
            "scenario_outcomes": self.scenario_outcomes,
        }


SCENARIOS = sorted(SCENARIO_REGISTRY.keys())


def run_all_scenarios(mode: str = "DRY", base_url: str | None = None) -> dict:
    runner = SimulatorRunner(mode=mode, base_url=base_url)
    for sid in SCENARIOS:
        runner.run_scenario(sid)
    return runner.summary()


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    if not argv or "--help" in argv or "-h" in argv:
        print(__doc__)
        print("\nUsage: python -m his_emr_simulator [--scenario N | --all | --list] [--live]")
        return 0

    if "--list" in argv:
        for sid, (title, _) in sorted(SCENARIO_REGISTRY.items()):
            print(f"  {sid:2d}  {title}")
        return 0

    mode = "LIVE" if "--live" in argv else "DRY"
    base_url = os.environ.get("ICODER_PILOT_URL")

    if "--all" in argv:
        runner = SimulatorRunner(mode=mode, base_url=base_url)
        for sid in SCENARIOS:
            runner.run_scenario(sid)
        summary = runner.summary()
    else:
        try:
            idx = argv.index("--scenario")
            sid = int(argv[idx + 1])
        except (ValueError, IndexError):
            print("ERROR: must pass --scenario N or --all")
            return 2
        if sid not in SCENARIO_REGISTRY:
            print(f"ERROR: scenario {sid} not in registry (1-{len(SCENARIO_REGISTRY)})")
            return 2
        runner = SimulatorRunner(mode=mode, base_url=base_url)
        runner.run_scenario(sid)
        summary = runner.summary()

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["fail"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
