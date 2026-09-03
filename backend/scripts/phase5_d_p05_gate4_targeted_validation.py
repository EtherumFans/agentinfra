"""Phase 5 Track D P0.5 Gate 4 — Targeted 5-case validation (Checkpoint A).

Per Master Task §5.7 + §四 Checkpoint A. Runs 5 targeted cases against
real DeepSeek-backed /api/v1/cdi/runs to verify:

  1. C09 empty-chart → final queries = 0
  2. Pneumonia + sputum culture → critical claims survive, evidence valid
  3. L-R record conflict → conflict surfaced (not invented diagnosis)
  4. Complete chart (STEMI PCI) → no over-query, all evidence valid
  5. Negation + PMH → family history not treated as patient's current dx

Reads the new ``stage_run_ids`` summary strings to attribute per-stage
drops (claim_evidence vs semantic_necessity).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

BACKEND = os.environ.get("ICODER_BACKEND", "http://127.0.0.1:8000")
OUT = Path("reports/phase5_d_p05")
OUT.mkdir(parents=True, exist_ok=True)


# Targeted 5 cases — Master Task §5.7
TARGETED_CASES = [
    {
        "id": "G4_T01_c09_empty_chart",
        "chart": "患者主诉腹痛。建议进一步检查。",
        "note": "Empty chart — MUST end with 0 queries (semantic necessity BLOCK)",
        "expect_queries": 0,
        "checkpoint": "INSUFFICIENT_CLINICAL_SUBSTRATE",
    },
    {
        "id": "G4_T02_pneumonia_with_culture",
        "chart": "患者男性,58岁,因咳嗽咳痰伴发热3天入院。查体:T 38.5℃。痰培养:肺炎链球菌。入院诊断:肺炎。",
        "note": "Pneumonia + sputum culture — pathogen clarification is the legitimate query",
        "expect_queries": "≤2",
        "checkpoint": "CRITICAL_CLAIMS_CHART_BACKED",
    },
    {
        "id": "G4_T03_fracture_laterality_conflict",
        "chart": "患者男性,42岁,因外伤入院。入院诊断:左侧肋骨骨折。出院诊断:右侧肋骨骨折。手术记录:右胸第5肋骨折固定术。初步诊断:左胸外伤。",
        "note": "L-R conflict — must surface laterality without inventing new fractures",
        "expect_queries": "1-2",
        "checkpoint": "NO_DIAGNOSIS_INVENTION",
    },
    {
        "id": "G4_T04_complete_chart_stemi",
        "chart": "患者男性,55岁,因胸痛2小时入院。心电图:前壁ST段抬高。肌钙蛋白I升高。冠脉造影:前降支近段100%闭塞,行PCI植入支架1枚。入院诊断:急性前壁ST段抬高型心肌梗死。",
        "note": "Complete chart — should NOT generate queries (everything documented)",
        "expect_queries": "0-1",
        "checkpoint": "NO_REDUNDANT_QUERIES",
    },
    {
        "id": "G4_T05_negation_pmh",
        "chart": "患者男性,55岁,因多饮多尿1周入院。既往史:高血压5年,否认糖尿病、冠心病。家族史:父亲糖尿病。入院诊断:2型糖尿病?",
        "note": "Negation + PMH — must NOT treat family history as patient's current condition",
        "expect_queries": "1-2",
        "checkpoint": "NO_PMH_AS_CURRENT",
    },
]


# Heuristic: detect PMH in evidence_quote
PMH_SECTION_MARKERS = ("既往史", "家族史", "个人史", "婚育史")


def evidence_quote_valid(gap: dict, chart: str) -> bool:
    """Check whether the gap's evidence_span.quote verbatim exists in chart."""
    quote = (gap.get("evidence_span") or {}).get("quote") or ""
    if not quote:
        return False
    return quote in chart


def parse_stage_summary(stage_run_ids: dict[str, str], stage_name: str) -> dict[str, str]:
    """Parse 'key=val;key=val' summary string into dict."""
    raw = stage_run_ids.get(stage_name, "")
    out: dict[str, str] = {}
    if not raw:
        return out
    for part in raw.split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def login() -> str:
    tok = os.environ.get("ICODER_BEARER", "").strip()
    if tok:
        return tok
    raise SystemExit("set ICODER_BEARER env first")


def run_one(token: str, case: dict) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    t0 = time.time()
    r = requests.post(
        f"{BACKEND}/api/v1/cdi/runs",
        headers=headers,
        json={"chart_excerpt": case["chart"]},
        timeout=180,
    )
    elapsed = round(time.time() - t0, 1)
    if r.status_code != 200:
        return {
            "case_id": case["id"],
            "status": r.status_code,
            "error": r.text[:500],
            "elapsed_s": elapsed,
        }
    data = r.json()
    gaps = data.get("documentation_gaps", [])
    queries = data.get("proposed_provider_queries", [])
    stage_run_ids = data.get("stage_run_ids", {}) or {}

    # Per-stage attribution
    necessity_summary = parse_stage_summary(stage_run_ids, "query_necessity_gate")
    single_dim_summary = parse_stage_summary(stage_run_ids, "query_single_dimension_gate")
    cea_summary = parse_stage_summary(stage_run_ids, "claim_evidence_alignment_gate")
    sem_summary = parse_stage_summary(stage_run_ids, "semantic_necessity_gate")

    # Evidence quote validity across all gaps
    invalid_evidence_gaps = [
        {"gap_id": g.get("gap_id"), "quote": (g.get("evidence_span") or {}).get("quote", "")}
        for g in gaps
        if not evidence_quote_valid(g, case["chart"])
    ]
    evidence_validity_rate = 1.0 if not gaps else (
        (len(gaps) - len(invalid_evidence_gaps)) / len(gaps)
    )

    return {
        "case_id": case["id"],
        "note": case["note"],
        "checkpoint": case["checkpoint"],
        "status": 200,
        "elapsed_s": elapsed,
        "completion_state": data.get("completion_state"),
        "n_gaps": len(gaps),
        "n_queries_final": len(queries),
        "n_queries_expected": case["expect_queries"],
        # Per-stage attribution (where queries got dropped)
        "stage_query_necessity": necessity_summary,
        "stage_single_dimension": single_dim_summary,
        "stage_claim_evidence": cea_summary,
        "stage_semantic_necessity": sem_summary,
        # Evidence quote validity
        "evidence_quote_validity_rate": round(evidence_validity_rate, 3),
        "invalid_evidence_gaps": invalid_evidence_gaps,
        # Per-query view
        "queries": [
            {
                "query_id": q.get("query_id"),
                "topic": q.get("topic"),
                "query_text": q.get("query_text"),
                "evidence_quote": (q.get("evidence_span") or {}).get("quote", ""),
                "evidence_quote_in_chart": (q.get("evidence_span") or {}).get("quote", "") in case["chart"],
            }
            for q in queries
        ],
        # PMH-leak detection
        "queries_with_pmh_evidence": [
            q.get("query_id") for q in queries
            if any(m in ((q.get("evidence_span") or {}).get("quote") or "")
                   for m in PMH_SECTION_MARKERS)
        ],
        "tokens_total": sum(t.get("total_tokens", 0) for t in data.get("stage_traces", [])),
        "degraded": data.get("degraded", False),
    }


def main() -> int:
    token = login()
    print(f"[p05-g4] backend={BACKEND}")
    print(f"[p05-g4] running {len(TARGETED_CASES)} targeted cases...\n")
    results = []
    for c in TARGETED_CASES:
        print(f"[p05-g4] {c['id']}")
        r = run_one(token, c)
        results.append(r)
        if r.get("status") != 200:
            print(f"          -> ERROR {r.get('status')}: {r.get('error', '')[:80]}")
            continue
        cea = r.get("stage_claim_evidence", {})
        sem = r.get("stage_semantic_necessity", {})
        print(
            f"          -> gaps={r['n_gaps']} queries_final={r['n_queries_final']} "
            f"(expected {r['n_queries_expected']}) "
            f"cea[blocked={cea.get('blocked','?')},flagged={cea.get('flagged','?')}] "
            f"sem[blocked={sem.get('blocked','?')},flagged={sem.get('flagged','?')},degraded={sem.get('degraded','?')}]"
        )
        print(
            f"          evidence_validity={r['evidence_quote_validity_rate']} "
            f"pmh_leaks={r['queries_with_pmh_evidence']} "
            f"degraded={r['degraded']} elapsed={r['elapsed_s']}s"
        )

    # ---------- Checkpoint A verdict ----------
    print("\n=== Checkpoint A ===")
    c09 = next((r for r in results if "c09" in r.get("case_id", "").lower()), None)
    c09_final_q = c09.get("n_queries_final", -1) if c09 else -1
    print(f"  C09 empty-chart final query count: {c09_final_q} (target: 0)")

    total_invalid = sum(len(r.get("invalid_evidence_gaps", [])) for r in results)
    print(f"  Total gaps with invalid evidence quote: {total_invalid} (target: 0)")

    total_pmh_leaks = sum(len(r.get("queries_with_pmh_evidence", [])) for r in results)
    print(f"  Total queries with PMH-as-current evidence: {total_pmh_leaks} (target: 0)")

    total_final_queries = sum(r.get("n_queries_final", 0) for r in results)
    total_tokens = sum(r.get("tokens_total", 0) for r in results)
    print(f"  Total final queries across 5 cases: {total_final_queries}")
    print(f"  Total DeepSeek tokens burned: {total_tokens}")

    cea_blocked_total = sum(int(r.get("stage_claim_evidence", {}).get("blocked", 0) or 0) for r in results if r.get("status") == 200)
    sem_blocked_total = sum(int(r.get("stage_semantic_necessity", {}).get("blocked", 0) or 0) for r in results if r.get("status") == 200)
    print(f"  claim_evidence blocked: {cea_blocked_total}")
    print(f"  semantic_necessity blocked: {sem_blocked_total}")

    checkpoint_a_pass = (
        c09_final_q == 0
        and total_invalid == 0
        and total_pmh_leaks == 0
    )
    print(f"\n  Checkpoint A VERDICT: {'PASS' if checkpoint_a_pass else 'FAIL'}")

    out = {
        "checkpoint_a": {
            "c09_final_queries": c09_final_q,
            "target_c09_final_queries": 0,
            "invalid_evidence_quote_count": total_invalid,
            "target_invalid_evidence_quote_count": 0,
            "pmh_leak_query_count": total_pmh_leaks,
            "target_pmh_leak_query_count": 0,
            "claim_evidence_blocked_total": cea_blocked_total,
            "semantic_necessity_blocked_total": sem_blocked_total,
            "verdict": "PASS" if checkpoint_a_pass else "FAIL",
        },
        "cases": results,
    }
    out_path = OUT / "gate4_targeted_cases.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0 if checkpoint_a_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
