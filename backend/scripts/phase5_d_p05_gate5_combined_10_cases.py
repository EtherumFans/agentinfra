"""Phase 5 Track D P0.5 Gate 5 — Combined 10-case run (Gate 4 + Gate 5).

Per Master Task §6.6 / §10.2 — single 10-case execution covering both
Gate 4 (claim-evidence + semantic necessity) and Gate 5 (expert routing)
effects. Records per-stage drop attribution so each gate's contribution
to the final query count is visible.

Output: ``reports/phase5_d_p05/gate5_combined_10_cases.json``

Per-stage attribution sources
=============================

The orchestrator stashes summary strings in ``case.stage_run_ids``:

  query_necessity_gate         necessary=K;unnecessary=N;overquery_triggered=B;final_count=P
  query_single_dimension_gate  single_dim=K;multi_dim=N;axis_cluster_triggered=B;final_count=P
  claim_evidence_alignment_gate claims_extracted=K;blocked=N;flagged=M;final_count=P
  semantic_necessity_gate      blocked=K;flagged=M;degraded=D;final_count=P
  query_compliance_gate        (no summary string)

Final query count comes from ``proposed_provider_query`` length.

Expert routing attribution sources
==================================

``specialist_trace`` now contains one entry per Expert with
``execution_mode`` set. We tally per-case:

  expert_candidates            = 4 (always)
  expert_invoked               = count(execution_mode ∈ {REAL_TOOL, LLM_KNOWLEDGE_ONLY})
  expert_skipped_not_needed    = count(SKIPPED_NOT_NEEDED)
  expert_skipped_missing       = count(SKIPPED_MISSING_INPUTS)
  expert_tool_unavailable      = count(TOOL_UNAVAILABLE)

Checkpoint B target (Master Task §6.6)
======================================

  avg_experts_per_case   ≤ 1.5  (baseline was 4.0)
  c09_empty_experts      = 0
  avg_queries_per_case   ≤ 2.0  (Gate 3 baseline was 2.6)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

BACKEND = os.environ.get("ICODER_BACKEND", "http://127.0.0.1:8000")
OUT = Path("reports/phase5_d_p05")
OUT.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# 10-case fixture — same as baseline + Gate 4 targeted
# ---------------------------------------------------------------------------


CASES: list[dict[str, Any]] = [
    {
        "id": "C01_pneumonia_simple",
        "chart": "患者男性,58岁,因咳嗽咳痰伴发热3天入院。查体:T 38.5℃。痰培养:肺炎链球菌。入院诊断:肺炎。",
    },
    {
        "id": "C02_cholecystitis",
        "chart": "患者女性,45岁,因右上腹痛2天入院。查体:Murphy征阳性。腹部B超:胆囊壁增厚,胆囊结石。入院诊断:急性胆囊炎。",
    },
    {
        "id": "C03_hypertension_workup",
        "chart": "患者男性,60岁,因头晕乏力1月入院。查体:BP 160/95。既往史:无。辅助检查:心电图窦性心律,心脏彩超正常。入院诊断:高血压病。",
    },
    {
        "id": "C04_diabetes_negation",
        "chart": "患者男性,55岁,因多饮多尿1周入院。既往史:高血压5年,否认糖尿病、冠心病。家族史:父亲糖尿病。入院诊断:2型糖尿病?",
    },
    {
        "id": "C05_fracture_conflict",
        "chart": "患者男性,42岁,因外伤入院。入院诊断:左侧肋骨骨折。出院诊断:右侧肋骨骨折。手术记录:右胸第5肋骨折固定术。初步诊断:左胸外伤。",
    },
    {
        "id": "C06_appendicitis",
        "chart": "患者女性,28岁,因转移性右下腹痛1天入院。查体:右下腹压痛、反跳痛阳性。腹部CT:阑尾肿胀。入院诊断:急性阑尾炎。手术:腹腔镜阑尾切除术。",
    },
    {
        "id": "C07_copd_exacerbation",
        "chart": "患者男性,70岁,因咳嗽气促加重3天入院。既往史:慢性阻塞性肺疾病10年。查体:双肺哮鸣音。动脉血气:pH 7.35,PaCO2 60mmHg。入院诊断:慢性阻塺肺疾病急性加重。",
    },
    {
        "id": "C08_stemi_pci",
        "chart": "患者男性,55岁,因胸痛2小时入院。心电图:前壁ST段抬高。肌钙蛋白I升高。冠脉造影:前降支近段100%闭塞,行PCI植入支架1枚。入院诊断:急性前壁ST段抬高型心肌梗死。",
    },
    {
        "id": "C09_minimal_info",
        "chart": "患者主诉腹痛。建议进一步检查。",
    },
    {
        "id": "C10_peds_pneumonia",
        "chart": "患者5岁,因咳嗽发热2天入院。查体:双肺湿啰音。胸片:支气管肺炎。入院诊断:支气管肺炎。",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_summary(stage_run_ids: dict[str, str], stage: str) -> dict[str, int]:
    """Parse 'key=val;key=val' summary into int dict."""
    raw = stage_run_ids.get(stage, "")
    out: dict[str, int] = {}
    if not raw:
        return out
    for part in raw.split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            try:
                out[k.strip()] = int(v.strip())
            except ValueError:
                out[k.strip()] = 0
    return out


def login() -> str:
    tok = os.environ.get("ICODER_BEARER", "").strip()
    if tok:
        return tok
    raise SystemExit("set ICODER_BEARER env first")


def run_one(token: str, case: dict[str, Any]) -> dict[str, Any]:
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
    queries = data.get("proposed_provider_query", []) or data.get("proposed_provider_queries", [])
    stage_run_ids = data.get("stage_run_ids", {}) or {}
    specialist_trace = data.get("specialist_trace", []) or []
    stage_traces = data.get("stage_traces", []) or []

    necessity = _parse_summary(stage_run_ids, "query_necessity_gate")
    single_dim = _parse_summary(stage_run_ids, "query_single_dimension_gate")
    cea = _parse_summary(stage_run_ids, "claim_evidence_alignment_gate")
    sem = _parse_summary(stage_run_ids, "semantic_necessity_gate")

    # Expert routing attribution
    expert_modes = [e.get("execution_mode", "") for e in specialist_trace]
    expert_invoked = sum(1 for m in expert_modes if m in ("REAL_TOOL", "LLM_KNOWLEDGE_ONLY"))
    expert_not_needed = sum(1 for m in expert_modes if m == "SKIPPED_NOT_NEEDED")
    expert_missing = sum(1 for m in expert_modes if m == "SKIPPED_MISSING_INPUTS")
    expert_unavailable = sum(1 for m in expert_modes if m == "TOOL_UNAVAILABLE")
    expert_degraded = sum(1 for m in expert_modes if m == "DEGRADED")

    # NLQ gate drops — query_count_after_semantic - query_count_final
    final_count = len(queries)
    after_semantic = sem.get("final_count", final_count)
    nlq_blocked = max(0, after_semantic - final_count)

    # Total tokens across all stages (incl. Expert LLM calls)
    total_tokens = sum(int(t.get("total_tokens", 0) or 0) for t in stage_traces)

    return {
        "case_id": case["id"],
        "status": 200,
        "elapsed_s": elapsed,
        "completion_state": data.get("completion_state"),
        "degraded": data.get("degraded", False),
        "final_queries": final_count,
        "stage_drops": {
            "necessity_dropped": necessity.get("unnecessary", 0),
            "single_dimension_dropped": single_dim.get("multi_dim", 0),
            "claim_evidence_blocked": cea.get("blocked", 0),
            "claim_evidence_flagged": cea.get("flagged", 0),
            "semantic_necessity_blocked": sem.get("blocked", 0),
            "semantic_necessity_flagged": sem.get("flagged", 0),
            "semantic_necessity_degraded": sem.get("degraded", 0),
            "nlq_blocked": nlq_blocked,
        },
        "expert_routing": {
            "candidates": 4,
            "invoked": expert_invoked,
            "skipped_not_needed": expert_not_needed,
            "skipped_missing_inputs": expert_missing,
            "tool_unavailable": expert_unavailable,
            "degraded": expert_degraded,
            "modes": dict(zip(
                [e.get("expert_id", "") for e in specialist_trace],
                expert_modes,
            )),
        },
        "specialist_trace": specialist_trace,
        "tokens": total_tokens,
        "queries": [
            {
                "query_id": q.get("query_id"),
                "topic": q.get("topic"),
                "query_text": q.get("query_text"),
            }
            for q in queries
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    token = login()
    print(f"[p05-g5] backend={BACKEND}")
    print(f"[p05-g5] running {len(CASES)} cases (combined Gate 4 + Gate 5)...\n")

    results: list[dict[str, Any]] = []
    for c in CASES:
        print(f"[p05-g5] {c['id']}")
        r = run_one(token, c)
        results.append(r)
        if r.get("status") != 200:
            print(f"          -> ERROR {r.get('status')}: {r.get('error', '')[:80]}")
            continue

        drops = r["stage_drops"]
        experts = r["expert_routing"]
        print(
            f"          -> final_queries={r['final_queries']} "
            f"cea[blocked={drops['claim_evidence_blocked']},flagged={drops['claim_evidence_flagged']}] "
            f"sem[blocked={drops['semantic_necessity_blocked']}] "
            f"nlq[blocked={drops['nlq_blocked']}]"
        )
        print(
            f"          -> experts: invoked={experts['invoked']}/4 "
            f"not_needed={experts['skipped_not_needed']} "
            f"missing={experts['skipped_missing_inputs']} "
            f"unavailable={experts['tool_unavailable']} "
            f"tokens={r['tokens']} elapsed={r['elapsed_s']}s"
        )

    # ---------- Aggregate ----------
    print("\n=== Checkpoint B ===")
    ok_results = [r for r in results if r.get("status") == 200]
    n = max(1, len(ok_results))
    total_queries = sum(r.get("final_queries", 0) for r in ok_results)
    total_expert_invocations = sum(r["expert_routing"]["invoked"] for r in ok_results)
    c09 = next((r for r in ok_results if "C09" in r.get("case_id", "")), None)
    c09_experts = c09["expert_routing"]["invoked"] if c09 else -1

    avg_queries = total_queries / n
    avg_experts = total_expert_invocations / n
    print(f"  Avg queries / case: {avg_queries:.2f}  (target ≤ 2.0)")
    print(f"  Avg experts invoked / case: {avg_experts:.2f}  (baseline 4.0, target ≤ 1.5)")
    print(f"  C09 empty-chart experts invoked: {c09_experts}  (target: 0)")
    print(f"  Total tokens burned: {sum(r.get('tokens', 0) for r in ok_results)}")

    checkpoint_b_pass = (
        avg_queries <= 2.0
        and avg_experts <= 1.5
        and c09_experts == 0
    )
    print(f"\n  Checkpoint B VERDICT: {'PASS' if checkpoint_b_pass else 'FAIL'}")

    # ---------- Per-stage contribution ----------
    print("\n=== Per-stage drop attribution (sum across cases) ===")
    sum_drops = {
        "necessity_dropped": sum(r["stage_drops"]["necessity_dropped"] for r in ok_results),
        "single_dimension_dropped": sum(r["stage_drops"]["single_dimension_dropped"] for r in ok_results),
        "claim_evidence_blocked": sum(r["stage_drops"]["claim_evidence_blocked"] for r in ok_results),
        "semantic_necessity_blocked": sum(r["stage_drops"]["semantic_necessity_blocked"] for r in ok_results),
        "nlq_blocked": sum(r["stage_drops"]["nlq_blocked"] for r in ok_results),
    }
    for k, v in sum_drops.items():
        print(f"  {k}: {v}")

    print("\n=== Expert routing breakdown (sum across cases) ===")
    sum_experts = {
        "candidates": sum(r["expert_routing"]["candidates"] for r in ok_results),
        "invoked": total_expert_invocations,
        "skipped_not_needed": sum(r["expert_routing"]["skipped_not_needed"] for r in ok_results),
        "skipped_missing_inputs": sum(r["expert_routing"]["skipped_missing_inputs"] for r in ok_results),
        "tool_unavailable": sum(r["expert_routing"]["tool_unavailable"] for r in ok_results),
        "degraded": sum(r["expert_routing"]["degraded"] for r in ok_results),
    }
    for k, v in sum_experts.items():
        print(f"  {k}: {v}")

    # ---------- Write JSON ----------
    out = {
        "checkpoint_b": {
            "avg_queries_per_case": round(avg_queries, 2),
            "target_avg_queries_per_case_max": 2.0,
            "avg_experts_invoked_per_case": round(avg_experts, 2),
            "target_avg_experts_per_case_max": 1.5,
            "c09_empty_chart_experts_invoked": c09_experts,
            "target_c09_empty_chart_experts": 0,
            "verdict": "PASS" if checkpoint_b_pass else "FAIL",
        },
        "stage_drops_total": sum_drops,
        "expert_routing_total": sum_experts,
        "cases": results,
    }
    out_path = OUT / "gate5_combined_10_cases.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nwrote {out_path}")
    return 0 if checkpoint_b_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
