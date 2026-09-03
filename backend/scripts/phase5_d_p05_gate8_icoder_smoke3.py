"""Phase 5 Track D P0.5 Gate 8 — rerun 3 CB-failed smoke cases."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import requests

BACKEND = "http://127.0.0.1:8000"
FIXTURE = Path("tests/fixtures/cdi_gap8_smoke10.json")

RERUN_IDS = ["G8-CDI-CONFLICT-031", "G8-CDI-CONFLICT-033", "G8-CDI-LAB-036"]


def login() -> str:
    r = requests.post(f"{BACKEND}/api/auth/login", json={"username": "g7admin", "password": "Gate7!2026"}, timeout=10)
    if r.status_code != 200:
        r = requests.post(f"{BACKEND}/api/auth/login", json={"username": "admin", "password": "admin"}, timeout=10)
        if r.status_code != 200:
            raise SystemExit(f"login failed: {r.status_code}")
    return r.json()["access_token"]


def run_one(token: str, case: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    t0 = time.time()
    r = requests.post(f"{BACKEND}/api/v1/cdi/runs", headers=headers, json={"chart_excerpt": case["chart_zh"]}, timeout=180)
    elapsed = round(time.time() - t0, 1)
    if r.status_code != 200:
        return {"case_id": case["case_id"], "status": r.status_code, "error": r.text[:300], "elapsed_s": elapsed}
    data = r.json()
    queries = data.get("proposed_provider_queries", []) or data.get("proposed_provider_query", []) or []
    stage_traces = data.get("stage_traces", []) or []
    cb_open = any("circuit breaker is OPEN" in (t.get("error_reason") or "") for t in stage_traces)
    per_case_dir = Path("reports/phase5_d_p05/gate8_icoder_smoke10_per_case")
    per_case_dir.mkdir(parents=True, exist_ok=True)
    case_idx = case["case_id"].split("-")[-1]
    (per_case_dir / f"{case_idx}_{case['case_id']}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "case_id": case["case_id"],
        "category": case["category"],
        "expected": case["expected"],
        "status": 200,
        "elapsed_s": elapsed,
        "completion_state": data.get("completion_state"),
        "degraded": data.get("degraded", False),
        "circuit_breaker_open": cb_open,
        "final_queries": len(queries),
        "gap_count": len(data.get("documentation_gaps", []) or []),
        "query_topics": [q.get("topic", "") for q in queries],
        "case_run_id": data.get("case_id"),
    }


def main() -> None:
    cases = [c for c in json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"] if c["case_id"] in RERUN_IDS]
    cases.sort(key=lambda c: c["case_id"])
    print(f"Loaded {len(cases)} cases for rerun")
    token = login()
    print(f"Logged in. Backend={BACKEND}")
    time.sleep(20)
    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['case_id']} ({case['category']}) ...", end=" ", flush=True)
        r = run_one(token, case)
        if r.get("status") == 200:
            cb = "CB_OPEN" if r.get("circuit_breaker_open") else "OK"
            print(f"{cb} q={r['final_queries']} gaps={r['gap_count']} t={r['elapsed_s']}s")
        else:
            print(f"FAIL status={r.get('status')}")
        results.append(r)
        if i < len(cases):
            time.sleep(20)
    out = Path("reports/phase5_d_p05/gate8_icoder_smoke3_rerun_results.json")
    out.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
