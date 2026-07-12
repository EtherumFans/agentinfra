"""Phase 5 Track D P0.5 Gate 8 — §9.9 normalizer + §9.10 safety metrics.

Consumes:
- reports/phase5_d_p05/gate8_icoder_smoke10_final.json (10 iCoDer cases, aggregated)
- reports/phase5_d_p05/gate8_icoder_smoke10_per_case/*.json (full traces)
- reports/phase5_d_p05/gate8_corti_per_case/*.json (Corti per-case, n=1 fully captured)

Produces:
- reports/phase5_d_p05/gate8_normalizer_output.json (cross-platform comparison on shared cases)
- reports/phase5_d_p05/gate8_safety_metrics.json (§9.10 iCoDer-side safety metrics)
- prints summary table for the report
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path("reports/phase5_d_p05")
ICODER_FINAL = ROOT / "gate8_icoder_smoke10_final.json"
ICODER_PER_CASE = ROOT / "gate8_icoder_smoke10_per_case"
CORTI_PER_CASE = ROOT / "gate8_corti_per_case"
NORMALIZER_OUT = ROOT / "gate8_normalizer_output.json"
SAFETY_OUT = ROOT / "gate8_safety_metrics.json"


def load_icoder_case(case_id: str) -> dict | None:
    suffix = case_id.split("-")[-1]
    p = ICODER_PER_CASE / f"{suffix}_{case_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_corti_case(case_id: str) -> dict | None:
    suffix = case_id.split("-")[-1]
    p = CORTI_PER_CASE / f"{suffix}_{case_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def parse_corti_response(text: str) -> dict:
    """Parse Corti's free-text response into structured counts.

    Primary: use explicit numbered list markers ("1. Gap:", "2. Gap:", "1. Topic:")
    Backup: count any line that starts with a number and matches Gap/Topic keywords.
    """
    gap_markers = re.findall(r"\n\d+\.\s+Gap:", text)
    topic_markers = re.findall(r"\n\d+\.\s+Topic:", text)
    gap_count = len(gap_markers)
    query_count = len(topic_markers)
    # Sanity: if regex found nothing, fall back to looser match
    if gap_count == 0 and "Gap:" in text:
        gap_count = text.count(" Gap:") + text.count("\nGap:")
    if query_count == 0 and "Topic:" in text:
        query_count = text.count(" Topic:") + text.count("\nTopic:")
    experts_mentioned = len(re.findall(r"consulted", text, re.IGNORECASE))
    return {
        "parsed_gap_count": gap_count,
        "parsed_query_count": query_count,
        "expert_consulted_mentions": experts_mentioned,
    }


def compute_section_9_9() -> dict:
    """§9.9 — Normalizer: compare iCoDer vs Corti on shared cases."""
    icoder_final = json.loads(ICODER_FINAL.read_text(encoding="utf-8"))
    by_id = {r["case_id"]: r for r in icoder_final["results"]}

    corti_files = sorted(CORTI_PER_CASE.glob("*.json"))
    comparisons = []
    for cf in corti_files:
        case_id = cf.stem.split("_", 1)[1]
        corti_data = json.loads(cf.read_text(encoding="utf-8"))
        icoder_summary = by_id.get(case_id)
        icoder_full = load_icoder_case(case_id)
        if not icoder_summary or not icoder_full:
            continue
        corti_parsed = parse_corti_response(corti_data.get("text", ""))
        icoder_queries = icoder_full.get("proposed_provider_queries", []) or []
        icoder_gaps = icoder_full.get("documentation_gaps", []) or []
        exp = icoder_summary["expected"]
        qmin, qmax = exp["query_count_min"], exp["query_count_max"]
        icoder_in_range = qmin <= icoder_summary["final_queries"] <= qmax
        corti_in_range = qmin <= corti_parsed["parsed_query_count"] <= qmax
        comparisons.append({
            "case_id": case_id,
            "category": icoder_summary["category"],
            "expected_range": [qmin, qmax],
            "icoder": {
                "gap_count": len(icoder_gaps),
                "query_count": icoder_summary["final_queries"],
                "in_range": icoder_in_range,
                "range_status": icoder_summary["range_status"],
                "query_topics": [q.get("topic", "") for q in icoder_queries],
            },
            "corti": {
                "text_length": corti_data.get("text_length", 0),
                "credits": corti_data.get("credits", 0),
                "parsed_gap_count": corti_parsed["parsed_gap_count"],
                "parsed_query_count": corti_parsed["parsed_query_count"],
                "in_range": corti_in_range,
                "range_status": (
                    "OVER_QUERY" if corti_parsed["parsed_query_count"] > qmax
                    else "UNDER_QUERY" if corti_parsed["parsed_query_count"] < qmin
                    else "IN_RANGE"
                ),
                "experts_consulted": corti_data.get("expert_calls", []),
            },
            "agreement": {
                "query_count_delta": icoder_summary["final_queries"] - corti_parsed["parsed_query_count"],
                "both_in_range": icoder_in_range and corti_in_range,
                "both_out_of_range": (not icoder_in_range) and (not corti_in_range),
                "same_direction": (
                    icoder_summary["range_status"] == corti_parsed["parsed_query_count"] and False
                ),  # placeholder
            },
        })
    return {
        "shared_case_count": len(comparisons),
        "comparisons": comparisons,
        "aggregate": {
            "both_in_range_count": sum(1 for c in comparisons if c["agreement"]["both_in_range"]),
            "agreement_rate": (
                round(sum(1 for c in comparisons if c["agreement"]["both_in_range"]) / max(1, len(comparisons)), 3)
            ),
            "avg_abs_query_count_delta": round(
                sum(abs(c["agreement"]["query_count_delta"]) for c in comparisons) / max(1, len(comparisons)), 2
            ),
        },
    }


def compute_section_9_10() -> dict:
    """§9.10 — Safety metrics from the iCoDer smoke10 side."""
    icoder_final = json.loads(ICODER_FINAL.read_text(encoding="utf-8"))
    results = icoder_final["results"]
    n = len(results)
    total_queries = sum(r["final_queries"] for r in results)
    total_gaps = sum(r["gap_count"] for r in results)

    # Per-case full data for query-level analysis
    over_query_cases = []
    under_query_cases = []
    in_range_cases = []
    for r in results:
        full = load_icoder_case(r["case_id"]) or {}
        queries = full.get("proposed_provider_queries", []) or []
        entry = {
            "case_id": r["case_id"],
            "category": r["category"],
            "final_queries": r["final_queries"],
            "expected_range": [r["expected"]["query_count_min"], r["expected"]["query_count_max"]],
            "range_status": r["range_status"],
            "query_topics": [q.get("topic", "") for q in queries],
            "query_texts": [q.get("query_text", "")[:80] for q in queries],
        }
        if r["range_status"] == "OVER_QUERY":
            over_query_cases.append(entry)
        elif r["range_status"] == "UNDER_QUERY":
            under_query_cases.append(entry)
        else:
            in_range_cases.append(entry)

    # Multi-dimensional query rate (single-dim gate output vs final)
    single_dim_dropped_total = icoder_final["gate_drop_totals"]["single_dim_dropped"]
    necessity_dropped_total = icoder_final["gate_drop_totals"]["necessity_dropped"]
    cea_blocked_total = icoder_final["gate_drop_totals"]["cea_blocked"]
    cea_claims_total = icoder_final["gate_drop_totals"]["cea_claims_extracted"]
    semantic_blocked_total = icoder_final["gate_drop_totals"]["semantic_blocked"]

    # Expert invocation: count real (LLM_KNOWLEDGE_ONLY or REAL_TOOL) invocations across cases
    expert_invocations = 0
    expert_modes: dict[str, int] = {}
    expert_by_case: list[dict] = []
    for r in results:
        full = load_icoder_case(r["case_id"]) or {}
        traces = full.get("specialist_trace", []) or []
        case_invoked = 0
        for t in traces:
            mode = t.get("execution_mode", "")
            expert_modes[mode] = expert_modes.get(mode, 0) + 1
            if mode in ("REAL_TOOL", "LLM_KNOWLEDGE_ONLY"):
                expert_invocations += 1
                case_invoked += 1
        expert_by_case.append({"case_id": r["case_id"], "invoked": case_invoked})

    return {
        "n_cases": n,
        "total_queries_emitted": total_queries,
        "total_gaps_detected": total_gaps,
        "avg_queries_per_case": round(total_queries / n, 3),
        "avg_gaps_per_case": round(total_gaps / n, 3),
        "range_conformance": {
            "in_range": len(in_range_cases),
            "over_query": len(over_query_cases),
            "under_query": len(under_query_cases),
            "in_range_rate": round(len(in_range_cases) / n, 3),
        },
        "gate_drops": {
            "necessity_dropped": necessity_dropped_total,
            "single_dim_dropped": single_dim_dropped_total,
            "cea_blocked": cea_blocked_total,
            "cea_claims_extracted": cea_claims_total,
            "cea_block_rate": round(cea_blocked_total / max(1, cea_claims_total), 3),
            "semantic_blocked": semantic_blocked_total,
        },
        "expert_invocation": {
            "total_invocations": expert_invocations,
            "by_execution_mode": expert_modes,
            "per_case": expert_by_case,
            "avg_per_case": round(expert_invocations / n, 3),
        },
        "over_query_cases": over_query_cases,
        "under_query_cases": under_query_cases,
        "in_range_cases_summary": [
            {"case_id": c["case_id"], "category": c["category"], "final_queries": c["final_queries"]}
            for c in in_range_cases
        ],
    }


def main() -> None:
    sec_9_9 = compute_section_9_9()
    sec_9_10 = compute_section_9_10()

    NORMALIZER_OUT.write_text(json.dumps(sec_9_9, ensure_ascii=False, indent=2), encoding="utf-8")
    SAFETY_OUT.write_text(json.dumps(sec_9_10, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("§9.9 NORMALIZER (iCoDer vs Corti, shared cases)")
    print("=" * 78)
    print(f"Shared cases compared: {sec_9_9['shared_case_count']}")
    print(f"Both in range: {sec_9_9['aggregate']['both_in_range_count']}/{sec_9_9['shared_case_count']}")
    print(f"Avg |query delta|: {sec_9_9['aggregate']['avg_abs_query_count_delta']}")
    print()
    for c in sec_9_9["comparisons"]:
        print(f"  {c['case_id']} ({c['category']})")
        print(f"    expected range: {c['expected_range']}")
        print(f"    iCoDer: q={c['icoder']['query_count']} ({c['icoder']['range_status']})")
        print(f"    Corti:  q={c['corti']['parsed_query_count']} ({c['corti']['range_status']}) "
              f"credits=${c['corti']['credits']:.4f}")
        print(f"    delta: {c['agreement']['query_count_delta']:+d}")
    print()
    print("=" * 78)
    print("§9.10 SAFETY METRICS (iCoDer, n=10)")
    print("=" * 78)
    s = sec_9_10
    print(f"n_cases: {s['n_cases']}")
    print(f"total_queries_emitted: {s['total_queries_emitted']}")
    print(f"avg_queries_per_case: {s['avg_queries_per_case']}")
    print(f"range_conformance: in_range={s['range_conformance']['in_range']} "
          f"over={s['range_conformance']['over_query']} under={s['range_conformance']['under_query']}")
    print(f"  in_range_rate: {s['range_conformance']['in_range_rate']*100:.1f}%")
    print(f"gate_drops:")
    print(f"  necessity_dropped: {s['gate_drops']['necessity_dropped']}")
    print(f"  single_dim_dropped: {s['gate_drops']['single_dim_dropped']}")
    print(f"  cea_blocked: {s['gate_drops']['cea_blocked']} / {s['gate_drops']['cea_claims_extracted']} "
          f"claims ({s['gate_drops']['cea_block_rate']*100:.1f}% block rate)")
    print(f"  semantic_blocked: {s['gate_drops']['semantic_blocked']}")
    print(f"expert_invocation:")
    print(f"  total: {s['expert_invocation']['total_invocations']}")
    print(f"  by_mode: {s['expert_invocation']['by_execution_mode']}")
    print(f"  avg_per_case: {s['expert_invocation']['avg_per_case']}")
    print()
    print("OVER_QUERY cases (potential over-query risk):")
    for c in s["over_query_cases"]:
        print(f"  - {c['case_id']} ({c['category']}): q={c['final_queries']}, "
              f"expected={c['expected_range']}, topics={c['query_topics']}")
    print()
    print("UNDER_QUERY cases (CEA may be over-blocking):")
    for c in s["under_query_cases"]:
        print(f"  - {c['case_id']} ({c['category']}): q={c['final_queries']}, "
              f"expected={c['expected_range']}, gaps={c['final_queries']}/N detected")
    print()
    print(f"Wrote: {NORMALIZER_OUT}")
    print(f"Wrote: {SAFETY_OUT}")


if __name__ == "__main__":
    main()
