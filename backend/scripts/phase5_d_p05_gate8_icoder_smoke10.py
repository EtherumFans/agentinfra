"""Phase 5 Track D P0.5 Gate 8 — iCoDer 10-case real-LLM smoke.

Reduced sample (vs 40-case full batch) to avoid circuit-breaker storms under
rate-limit pressure. Picks 1-2 cases per §9.4 category to get category-stratified
real-LLM metrics without triggering the LLM circuit breaker.

Uses 15s inter-case pacing to keep DeepSeek rate-limit well below 60 RPM.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

BACKEND = os.environ.get("ICODER_BACKEND", "http://127.0.0.1:8000")
FIXTURE = Path("tests/fixtures/cdi_gap8_smoke10.json")
FIXTURE.parent.mkdir(parents=True, exist_ok=True)

# Pick: GAP-001, GAP-005, COMPLETE-011, COMPLETE-013, INSUF-021, NEG-026, NEG-030, CONFLICT-031, CONFLICT-033, LAB-036
SMOKE_IDS = [
    "G8-CDI-GAP-001", "G8-CDI-GAP-005",
    "G8-CDI-COMPLETE-011", "G8-CDI-COMPLETE-013",
    "G8-CDI-INSUF-021",
    "G8-CDI-NEG-026", "G8-CDI-NEG-030",
    "G8-CDI-CONFLICT-031", "G8-CDI-CONFLICT-033",
    "G8-CDI-LAB-036",
]


def write_smoke_fixture() -> None:
    """Pull the 10 selected cases from the full 40-case fixture."""
    full = json.loads(Path("tests/fixtures/cdi_gate8_40cases.json").read_text(encoding="utf-8"))
    smoke_cases = [c for c in full["cases"] if c["case_id"] in SMOKE_IDS]
    assert len(smoke_cases) == 10, f"expected 10, got {len(smoke_cases)}"
    out = {"_meta": {"source": "cdi_gate8_40cases.json", "subset": "smoke10"}, "cases": smoke_cases}
    FIXTURE.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote smoke fixture: {FIXTURE} ({len(smoke_cases)} cases)")


def login() -> str:
    r = requests.post(f"{BACKEND}/api/auth/login", json={"username": "g7admin", "password": "Gate7!2026"}, timeout=10)
    if r.status_code != 200:
        r = requests.post(f"{BACKEND}/api/auth/login", json={"username": "admin", "password": "admin"}, timeout=10)
        if r.status_code != 200:
            raise SystemExit(f"login failed: {r.status_code} {r.text[:200]}")
    return r.json()["access_token"]


def parse_summary(stage_run_ids: dict[str, str], stage: str) -> dict[str, int]:
    raw = stage_run_ids.get(stage, "")
    out: dict[str, int] = {}
    for part in raw.split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            try:
                out[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return out


def run_one(token: str, case: dict[str, Any]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    chart = case["chart_zh"]
    t0 = time.time()
    r = requests.post(
        f"{BACKEND}/api/v1/cdi/runs",
        headers=headers,
        json={"chart_excerpt": chart},
        timeout=180,
    )
    elapsed = round(time.time() - t0, 1)
    if r.status_code != 200:
        return {"case_id": case["case_id"], "category": case["category"], "status": r.status_code, "error": r.text[:300], "elapsed_s": elapsed}

    data = r.json()
    queries = data.get("proposed_provider_queries", []) or data.get("proposed_provider_query", []) or []
    stage_run_ids = data.get("stage_run_ids", {}) or {}
    stage_traces = data.get("stage_traces", []) or []
    specialist_trace = data.get("specialist_trace", []) or []

    cb_open = any("circuit breaker is OPEN" in (t.get("error_reason") or "") for t in stage_traces)

    necessity = parse_summary(stage_run_ids, "query_necessity_gate")
    cea = parse_summary(stage_run_ids, "claim_evidence_alignment_gate")
    sem = parse_summary(stage_run_ids, "semantic_necessity_gate")

    expert_modes = [e.get("execution_mode", "") for e in specialist_trace]
    expert_invoked = sum(1 for m in expert_modes if m in ("REAL_TOOL", "LLM_KNOWLEDGE_ONLY"))

    # Save per-case trace for debugging
    per_case_dir = Path("reports/phase5_d_p05/gate8_icoder_smoke10_per_case")
    per_case_dir.mkdir(parents=True, exist_ok=True)
    case_idx = case["case_id"].split("-")[-1]
    per_case_file = per_case_dir / f"{case_idx}_{case['case_id']}.json"
    per_case_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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
        "stage_drops": {
            "necessity_dropped": necessity.get("unnecessary", 0),
            "necessity_final": necessity.get("final_count", 0),
            "claim_evidence_blocked": cea.get("blocked", 0),
            "claim_evidence_claims": cea.get("claims_extracted", 0),
            "semantic_blocked": sem.get("blocked", 0),
            "semantic_final": sem.get("final_count", 0),
        },
        "expert_invoked": expert_invoked,
        "query_topics": [q.get("topic", "") for q in queries],
        "total_tokens": sum(int(t.get("total_tokens", 0) or 0) for t in stage_traces),
        "case_run_id": data.get("case_id"),
    }


def main() -> None:
    write_smoke_fixture()
    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
    print(f"Loaded {len(cases)} smoke cases")

    token = login()
    print(f"Logged in. Backend={BACKEND}")

    results: list[dict[str, Any]] = []
    for i, case in enumerate(cases, 1):
        print(f"[{i:02d}/{len(cases)}] {case['case_id']} ({case['category']}) ...", end=" ", flush=True)
        r = run_one(token, case)
        if r.get("status") == 200:
            cb = "CB_OPEN" if r.get("circuit_breaker_open") else "OK"
            print(f"{cb} q={r['final_queries']} gaps={r['gap_count']} t={r['elapsed_s']}s experts={r['expert_invoked']}")
        else:
            print(f"FAIL status={r.get('status')}")
        results.append(r)
        if i < len(cases):
            time.sleep(15)  # aggressive pacing to avoid breaker storms

    out = Path("reports/phase5_d_p05/gate8_icoder_smoke10_results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "backend": BACKEND,
        "total_cases": len(results),
        "succeeded": sum(1 for r in results if r.get("status") == 200),
        "results": results,
        "aggregate": {
            "avg_queries_per_case": round(sum(r.get("final_queries", 0) for r in results) / max(1, len(results)), 2),
            "total_gaps": sum(r.get("gap_count", 0) for r in results),
            "total_tokens": sum(r.get("total_tokens", 0) for r in results),
            "circuit_breaker_open_count": sum(1 for r in results if r.get("circuit_breaker_open")),
            "degraded_count": sum(1 for r in results if r.get("degraded")),
        },
    }
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"Wrote: {out}")
    print(f"  avg queries/case: {summary['aggregate']['avg_queries_per_case']}")
    print(f"  total gaps: {summary['aggregate']['total_gaps']}")
    print(f"  CB-open count: {summary['aggregate']['circuit_breaker_open_count']}/{len(results)}")


if __name__ == "__main__":
    main()
