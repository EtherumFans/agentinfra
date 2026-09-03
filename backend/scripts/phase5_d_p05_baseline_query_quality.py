"""Phase 5 Track D P0.5 Gate 0 — 10-case query quality baseline.

Runs 10 diverse smoke cases through real DeepSeek-backed /api/v1/cdi/runs
and tallies:
  - gaps/case, queries/case
  - multi-dimension queries (heuristic: query_text matches ≥2 of 这些/及/与/both)
  - over-query rate (cases where >2 queries for a single chart)
  - zero-gap-but-N-query cases (data integrity signal)
  - evidence quote population rate
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


CASES = [
    {
        "id": "C01_pneumonia_simple",
        "chart": "患者男性,58岁,因咳嗽咳痰伴发热3天入院。查体:T 38.5℃。痰培养:肺炎链球菌。入院诊断:肺炎。",
        "note": "Simple pneumonia — should not generate 4+ queries",
    },
    {
        "id": "C02_cholecystitis",
        "chart": "患者女性,45岁,因右上腹痛2天入院。查体:Murphy征阳性。腹部B超:胆囊壁增厚,胆囊结石。入院诊断:急性胆囊炎。",
        "note": "Surgical case — single dx, expect 0-1 queries",
    },
    {
        "id": "C03_hypertension_workup",
        "chart": "患者男性,60岁,因头晕乏力1月入院。查体:BP 160/95。既往史:无。辅助检查:心电图窦性心律,心脏彩超正常。入院诊断:高血压病。",
        "note": "Hypertension — should NOT query severity without end-organ evidence",
    },
    {
        "id": "C04_diabetes_negation",
        "chart": "患者男性,55岁,因多饮多尿1周入院。既往史:高血压5年,否认糖尿病、冠心病。家族史:父亲糖尿病。入院诊断:2型糖尿病?",
        "note": "Negation — must NOT claim patient has CHD",
    },
    {
        "id": "C05_fracture_conflict",
        "chart": "患者男性,42岁,因外伤入院。入院诊断:左侧肋骨骨折。出院诊断:右侧肋骨骨折。手术记录:右胸第5肋骨折固定术。初步诊断:左胸外伤。",
        "note": "Laterality conflict — must surface left vs right",
    },
    {
        "id": "C06_appendicitis",
        "chart": "患者女性,28岁,因转移性右下腹痛1天入院。查体:右下腹压痛、反跳痛阳性。腹部CT:阑尾肿胀。入院诊断:急性阑尾炎。手术:腹腔镜阑尾切除术。",
        "note": "Clean surgical case — should mostly pass",
    },
    {
        "id": "C07_copd_exacerbation",
        "chart": "患者男性,70岁,因咳嗽气促加重3天入院。既往史:慢性阻塞性肺疾病10年。查体:双肺哮鸣音。动脉血气:pH 7.35,PaCO2 60mmHg。入院诊断:慢性阻塞性肺疾病急性加重。",
        "note": "COPD with explicit historical — must not elevate",
    },
    {
        "id": "C08_stemi_pci",
        "chart": "患者男性,55岁,因胸痛2小时入院。心电图:前壁ST段抬高。肌钙蛋白I升高。冠脉造影:前降支近段100%闭塞,行PCI植入支架1枚。入院诊断:急性前壁ST段抬高型心肌梗死。",
        "note": "STEMI PCI — clean explicit dx",
    },
    {
        "id": "C09_minimal_info",
        "chart": "患者主诉腹痛。建议进一步检查。",
        "note": "Minimal info — should NOT invent diagnoses",
    },
    {
        "id": "C10_peds_pneumonia",
        "chart": "患者5岁,因咳嗽发热2天入院。查体:双肺湿啰音。胸片:支气管肺炎。入院诊断:支气管肺炎。",
        "note": "Pediatric pneumonia — should be clean",
    },
]

# Heuristic for multi-dimension queries.
MULTI_DIM_PATTERNS = [
    r"类型.{0,4}(严重|部位|解剖)",
    r"严重.{0,4}(部位|解剖|并发症)",
    r"侧.{0,4}(肺叶|部位)",
    r"急性.{0,4}病程",
    r"(及|和|与).{0,15}(及|和|与)",
    r"both\s+the\s+\w+\s+and",
]


def count_multi_dim(queries: list[dict]) -> int:
    cnt = 0
    for q in queries:
        text = (q.get("topic", "") + " " + q.get("query_text", "")).lower()
        for pat in MULTI_DIM_PATTERNS:
            if re.search(pat, text, flags=re.IGNORECASE):
                cnt += 1
                break
    return cnt


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
        timeout=120,
    )
    elapsed = round(time.time() - t0, 1)
    if r.status_code != 200:
        return {"case_id": case["id"], "status": r.status_code, "error": r.text[:300], "elapsed_s": elapsed}
    data = r.json()
    gaps = data.get("documentation_gaps", [])
    queries = data.get("proposed_provider_queries", [])
    multi_dim = count_multi_dim(queries)
    no_evidence_gaps = sum(1 for g in gaps if not (g.get("evidence_span") or {}).get("quote"))
    topics = [q.get("topic", "") for q in queries]
    return {
        "case_id": case["id"],
        "note": case["note"],
        "status": 200,
        "elapsed_s": elapsed,
        "internal_case_id": data.get("case_id"),
        "completion_state": data.get("completion_state"),
        "n_gaps": len(gaps),
        "n_queries": len(queries),
        "multi_dim_queries": multi_dim,
        "no_evidence_gaps": no_evidence_gaps,
        "topics": topics,
        "query_texts": [q.get("query_text", "") for q in queries],
        "tokens": sum(t.get("total_tokens", 0) for t in data.get("stage_traces", [])),
        "experts_invoked": [
            t.get("expert_id") for t in data.get("stage_traces", []) if t.get("expert_id")
        ],
    }


def main() -> int:
    token = login()
    print(f"[p05-g0] backend={BACKEND}")
    results = []
    for c in CASES:
        print(f"[p05-g0] running {c['id']}...")
        r = run_one(token, c)
        results.append(r)
        print(
            f"           -> status={r.get('status')} gaps={r.get('n_gaps')} "
            f"queries={r.get('n_queries')} multi_dim={r.get('multi_dim_queries')} "
            f"tokens={r.get('tokens')} elapsed={r.get('elapsed_s')}s"
        )

    # Aggregate
    total = len(results)
    n_with_queries = sum(1 for r in results if r.get("n_queries", 0) > 0)
    n_overquery = sum(1 for r in results if r.get("n_queries", 0) >= 4)
    n_zero_gap_with_q = sum(1 for r in results if r.get("n_gaps", 0) == 0 and r.get("n_queries", 0) > 0)
    n_multi_dim = sum(1 for r in results if r.get("multi_dim_queries", 0) > 0)
    total_q = sum(r.get("n_queries", 0) for r in results)
    total_g = sum(r.get("n_gaps", 0) for r in results)
    total_multi = sum(r.get("multi_dim_queries", 0) for r in results)
    summary = {
        "total_cases": total,
        "cases_with_queries": n_with_queries,
        "cases_with_overquery_ge4": n_overquery,
        "cases_zero_gap_with_queries": n_zero_gap_with_q,
        "cases_with_multi_dim_query": n_multi_dim,
        "total_gaps": total_g,
        "total_queries": total_q,
        "total_multi_dim_queries": total_multi,
        "avg_queries_per_case": round(total_q / max(1, total), 2),
        "avg_gaps_per_case": round(total_g / max(1, total), 2),
        "multi_dim_query_rate": round(total_multi / max(1, total_q), 3),
    }
    out = {"summary": summary, "cases": results}
    (OUT / "baseline_query_quality_10_cases.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("\n=== summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    print(f"\nwrote {OUT / 'baseline_query_quality_10_cases.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
