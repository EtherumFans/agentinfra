"""Phase 5 Track D P0.5 Gate 8 — merge smoke10 + smoke3 rerun into final 10-case aggregate."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

SMOKE10 = Path("reports/phase5_d_p05/gate8_icoder_smoke10_results.json")
SMOKE3 = Path("reports/phase5_d_p05/gate8_icoder_smoke3_rerun_results.json")
PER_CASE = Path("reports/phase5_d_p05/gate8_icoder_smoke10_per_case")
OUT = Path("reports/phase5_d_p05/gate8_icoder_smoke10_final.json")


def parse_summary(stage_run_ids: dict, stage: str) -> dict:
    raw = stage_run_ids.get(stage, "")
    out = {}
    if not raw:
        return out
    for part in raw.split(";"):
        if "=" in part:
            k, _, v = part.partition("=")
            try:
                out[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return out


def main() -> None:
    smoke10 = json.loads(SMOKE10.read_text(encoding="utf-8"))
    smoke3 = json.loads(SMOKE3.read_text(encoding="utf-8"))

    # Build case_id → result map, preferring the rerun (smoke3) for cases that CB'd
    by_id = {}
    for r in smoke10["results"]:
        if r.get("status") == 200 and not r.get("circuit_breaker_open"):
            by_id[r["case_id"]] = r
    for r in smoke3["results"]:
        if r.get("status") == 200 and not r.get("circuit_breaker_open"):
            by_id[r["case_id"]] = r

    # Re-load per-case traces for full stage details
    final_results = []
    for r in sorted(by_id.values(), key=lambda x: x["case_id"]):
        case_id = r["case_id"]
        # Find per-case file
        suffix = case_id.split("-")[-1]
        per_case = PER_CASE / f"{suffix}_{case_id}.json"
        stage_drops = r.get("stage_drops", {})
        if per_case.exists():
            data = json.loads(per_case.read_text(encoding="utf-8"))
            stage_run_ids = data.get("stage_run_ids") or {}
            neness = parse_summary(stage_run_ids, "query_necessity_gate")
            single = parse_summary(stage_run_ids, "query_single_dimension_gate")
            cea = parse_summary(stage_run_ids, "claim_evidence_alignment_gate")
            sem = parse_summary(stage_run_ids, "semantic_necessity_gate")
            stage_drops = {
                "necessity_dropped": neness.get("unnecessary", 0),
                "necessity_final": neness.get("final_count", 0),
                "single_dim_dropped": single.get("multi_dim", 0),
                "single_dim_final": single.get("final_count", 0),
                "cea_blocked": cea.get("blocked", 0),
                "cea_claims_extracted": cea.get("claims_extracted", 0),
                "cea_final": cea.get("final_count", 0),
                "semantic_blocked": sem.get("blocked", 0),
                "semantic_degraded": sem.get("degraded", 0),
                "semantic_final": sem.get("final_count", 0),
            }
        # Range check vs expected
        exp = r["expected"]
        qmin, qmax = exp["query_count_min"], exp["query_count_max"]
        fc = r["final_queries"]
        if fc > qmax:
            range_status = "OVER_QUERY"
        elif fc < qmin:
            range_status = "UNDER_QUERY"
        else:
            range_status = "IN_RANGE"
        final_results.append({
            "case_id": case_id,
            "category": r["category"],
            "expected": exp,
            "elapsed_s": r["elapsed_s"],
            "completion_state": r["completion_state"],
            "degraded": r["degraded"],
            "final_queries": fc,
            "gap_count": r["gap_count"],
            "stage_drops": stage_drops,
            "query_topics": r["query_topics"],
            "range_status": range_status,
        })

    # Aggregate per category
    by_cat = {}
    for r in final_results:
        by_cat.setdefault(r["category"], []).append(r)
    cat_summary = {}
    for cat, rows in by_cat.items():
        n = len(rows)
        final_qs = [r["final_queries"] for r in rows]
        cat_summary[cat] = {
            "n": n,
            "total_queries": sum(final_qs),
            "avg_queries": round(sum(final_qs) / n, 2),
            "in_range": sum(1 for r in rows if r["range_status"] == "IN_RANGE"),
            "over_query": sum(1 for r in rows if r["range_status"] == "OVER_QUERY"),
            "under_query": sum(1 for r in rows if r["range_status"] == "UNDER_QUERY"),
            "cea_blocked_total": sum(r["stage_drops"].get("cea_blocked", 0) for r in rows),
            "cea_claims_total": sum(r["stage_drops"].get("cea_claims_extracted", 0) for r in rows),
            "single_dim_dropped_total": sum(r["stage_drops"].get("single_dim_dropped", 0) for r in rows),
        }

    summary = {
        "total_cases": len(final_results),
        "total_gaps": sum(r["gap_count"] for r in final_results),
        "total_queries": sum(r["final_queries"] for r in final_results),
        "avg_queries_per_case": round(sum(r["final_queries"] for r in final_results) / max(1, len(final_results)), 3),
        "category_breakdown": cat_summary,
        "results": final_results,
        "gate_drop_totals": {
            "cea_blocked": sum(r["stage_drops"].get("cea_blocked", 0) for r in final_results),
            "cea_claims_extracted": sum(r["stage_drops"].get("cea_claims_extracted", 0) for r in final_results),
            "single_dim_dropped": sum(r["stage_drops"].get("single_dim_dropped", 0) for r in final_results),
            "necessity_dropped": sum(r["stage_drops"].get("necessity_dropped", 0) for r in final_results),
            "semantic_blocked": sum(r["stage_drops"].get("semantic_blocked", 0) for r in final_results),
        },
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {OUT}")
    print(f"  total cases: {summary['total_cases']}")
    print(f"  total gaps: {summary['total_gaps']}")
    print(f"  total queries: {summary['total_queries']}")
    print(f"  avg queries/case: {summary['avg_queries_per_case']}")
    print(f"  CEA blocked total: {summary['gate_drop_totals']['cea_blocked']}")
    print()
    print("Per-category:")
    for cat, s in cat_summary.items():
        print(f"  {cat:30s}  n={s['n']}  avg_q={s['avg_queries']:5.2f}  "
              f"in_range={s['in_range']}/{s['n']}  over={s['over_query']}  under={s['under_query']}  "
              f"cea_blocked={s['cea_blocked_total']}/{s['cea_claims_total']}")


if __name__ == "__main__":
    main()
