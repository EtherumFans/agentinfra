"""Phase 5 Track D P0 Gate 6 — E2E scenario sweep via /api/v1/cdi/runs.

Runs 4 scenarios through the real DeepSeek-backed CDI orchestrator and
captures results as JSON for the Gate 6 report:

    S1: happy path (pneumonia)               — baseline
    S2: missing critical info (no diagnosis) — should still produce gaps
    S3: negation + history                    — must not invent facts
    S4: conflicting documentation             — must surface conflict

Usage:
    python scripts/phase5_d_gate6_e2e_scenarios.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests

BACKEND = os.environ.get("ICODER_BACKEND", "http://127.0.0.1:8000")
OUT = Path("reports/phase5_d_gate6_e2e")
OUT.mkdir(parents=True, exist_ok=True)


SCENARIOS = {
    "S1_happy_pneumonia": {
        "description": "Baseline — typical pneumonia admission with culture",
        "chart_excerpt": (
            "患者男性,58岁,因咳嗽咳痰伴发热3天入院。"
            "查体:T 38.5℃。痰培养:肺炎链球菌。"
            "入院诊断:肺炎。"
        ),
        "expect_gaps": ">=1",
        "expect_queries": ">=1",
    },
    "S2_missing_no_diagnosis": {
        "description": "No diagnosis stated — system should not invent one",
        "chart_excerpt": (
            "患者女性,72岁,因反复头晕乏力1周入院。"
            "查体:BP 150/95 mmHg,HR 82次/分。"
            "辅助检查:血常规正常,心电图窦性心律。"
            "建议进一步检查。"  # no diagnosis at all
        ),
        "expect_gaps": ">=1 (diagnostic specificity unknown)",
        "expect_queries": "varies",
    },
    "S3_negation_and_history": {
        "description": "Negation + historical — must NOT invent active dx",
        "chart_excerpt": (
            "患者男性,65岁,因上腹痛2天入院。"
            "既往史:高血压10年,已治愈肺结核,否认糖尿病、冠心病。"
            "家族史:父亲高血压。"
            "查体:上腹压痛阳性。"
            "初步诊断:急性胃炎;排除急性胰腺炎。"
        ),
        "expect_gaps": "must NOT claim patient has TB/diabetes/CHD",
        "expect_queries": ">=1",
    },
    "S4_conflicting_documentation": {
        "description": "Conflict between admission and discharge dx + laterality",
        "chart_excerpt": (
            "患者男性,45岁,因外伤入院。"
            "入院诊断:左侧肋骨骨折。"
            "出院诊断:右侧肋骨骨折。"
            "手术记录:右胸第5-7肋骨骨折固定术。"
            "主治医师记录:左胸外伤。"
        ),
        "expect_gaps": "must surface laterality conflict (left vs right)",
        "expect_queries": ">=1",
    },
}


def login() -> str:
    """Read token from env (preferred) or register a new user."""
    env_tok = os.environ.get("ICODER_BEARER", "").strip()
    if env_tok:
        return env_tok
    r = requests.post(
        f"{BACKEND}/api/auth/register",
        json={
            "username": f"gate6user_{int(time.time()) % 10000}",
            "email": f"gate6_{int(time.time())}@icoder.cloud",
            "password": "TestGate6!2026",
            "full_name": "Gate 6 Sweep",
        },
        timeout=10,
    )
    if r.status_code in (200, 201):
        return r.json()["access_token"]
    raise RuntimeError(f"register failed: {r.status_code} {r.text[:200]}")


def run_one(token: str, name: str, chart: str) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    t0 = time.time()
    r = requests.post(
        f"{BACKEND}/api/v1/cdi/runs",
        headers=headers,
        json={"chart_excerpt": chart},
        timeout=120,
    )
    elapsed = round(time.time() - t0, 1)
    if r.status_code != 200:
        return {
            "status": r.status_code,
            "elapsed_s": elapsed,
            "error": r.text[:500],
        }
    data = r.json()
    return {
        "status": 200,
        "elapsed_s": elapsed,
        "case_id": data.get("case_id"),
        "completion_state": data.get("completion_state"),
        "degraded": data.get("degraded"),
        "runtime_mode": data.get("runtime_mode"),
        "n_gaps": len(data.get("documentation_gaps", [])),
        "n_queries": len(data.get("proposed_provider_queries", [])),
        "gap_types": [g.get("gap_type") for g in data.get("documentation_gaps", [])],
        "gap_descriptions": [g.get("description") for g in data.get("documentation_gaps", [])],
        "query_topics": [q.get("topic") for q in data.get("proposed_provider_queries", [])],
        "query_texts": [q.get("query_text") for q in data.get("proposed_provider_queries", [])],
        "n_stage_traces": len(data.get("stage_traces", [])),
        "stage_latency": {
            t.get("stage"): t.get("latency_ms") for t in data.get("stage_traces", [])
        },
        "stage_tokens": {
            t.get("stage"): t.get("total_tokens") for t in data.get("stage_traces", [])
        },
        "total_tokens": sum(t.get("total_tokens", 0) for t in data.get("stage_traces", [])),
    }


def main() -> int:
    print(f"[gate6] backend={BACKEND}")
    token = login()
    print(f"[gate6] logged in (token len={len(token)})")
    results = {}
    for name, spec in SCENARIOS.items():
        print(f"[gate6] running {name}...")
        results[name] = {"spec": spec, "result": run_one(token, name, spec["chart_excerpt"])}
        r = results[name]["result"]
        print(
            f"          -> status={r['status']} elapsed={r.get('elapsed_s')}s "
            f"gaps={r.get('n_gaps')} queries={r.get('n_queries')} "
            f"completion={r.get('completion_state')}"
        )

    out_path = OUT / "gate6_e2e_scenarios.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[gate6] wrote {out_path}")

    # Quick assertions
    print("\n[gate6] assertions:")
    for name, payload in results.items():
        r = payload["result"]
        ok = (
            r.get("status") == 200
            and r.get("runtime_mode") == "real"
            and r.get("total_tokens", 0) > 100
        )
        print(f"  {name}: {'PASS' if ok else 'FAIL'} (tokens={r.get('total_tokens')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
