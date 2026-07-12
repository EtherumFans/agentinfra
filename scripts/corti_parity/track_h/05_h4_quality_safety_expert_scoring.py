"""Track H4.1 — Quality + Safety + Expert scoring on iter 3 baseline.

Reads 40 per-case JSON files from backend/reports/phase5_d_p05/gate8_icoder_per_case/
and computes three families of metrics:

  A. Quality (per-query, then aggregated)
     - evidence_quote_present_rate
     - evidence_quote_verbatim_rate (rapidfuzz >= 0.85 fuzzy fallback)
     - response_options_4plus_rate
     - response_options_escape_hatch_rate (contains 无法确定/不确定/不详/未明确/未知)
     - non_leading_query_rate (heuristic: no 是不是/是否为/确诊 patterns; len >= 10)

  B. Safety (per-case aggregated)
     - multi_dim_query_rate (target = 0.0)
     - unsupported_query_rate (target = 0.0)
     - leading_query_rate (target = 0.0)
     - contradiction_preservation_rate (queries still emitted on contradiction risk_flag)

  C. Expert (per-Expert: coding / pubmed / web-search / medical-calculator)
     - route_needed_count, consulted_count, invoke_rate
     - avg_latency_ms_when_consulted, avg_tokens_when_consulted
     - rejection_count (route=needed but consulted=false)

Output: reports/track_h/h41_quality_safety_expert_40case.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

try:
    from rapidfuzz import fuzz
except ImportError:  # pragma: no cover
    print("ERROR: rapidfuzz not installed. pip install rapidfuzz", file=sys.stderr)
    sys.exit(2)


REPO_ROOT = Path(__file__).resolve().parents[3]
PER_CASE_DIR = REPO_ROOT / "backend" / "reports" / "phase5_d_p05" / "gate8_icoder_per_case"
FIXTURE_PATH = REPO_ROOT / "backend" / "tests" / "fixtures" / "cdi_gate8_40cases.json"
OUTPUT_JSON = REPO_ROOT / "reports" / "track_h" / "h41_quality_safety_expert_40case.json"

LEADING_QUERY_PATTERNS = [
    r"是不是",
    r"是否为",
    r"确诊",
    r"应该诊断为",
    r"实际上是",
    r"可以考虑.*吧",
]
ESCAPE_PHRASES = ["无法确定", "不确定", "不详", "未明确", "未知", "尚不明确"]


def _extract_fixture_case_id_from_filename(filename: str) -> str | None:
    """ filename pattern: NN_G8-CDI-CAT-NNN.json -> G8-CDI-CAT-NNN """
    stem = Path(filename).stem
    parts = stem.split("_", 1)
    if len(parts) == 2:
        return parts[1]
    return None


def _is_verbatim_or_fuzzy(quote: str, chart: str) -> tuple[bool, float]:
    if not quote or not chart:
        return (False, 0.0)
    if quote in chart:
        return (True, 1.0)
    score = fuzz.partial_ratio(quote, chart) / 100.0
    return (score >= 0.85, score)


def _score_query(q: dict, chart: str) -> dict:
    quote = (q.get("evidence_span") or {}).get("quote", "") or ""
    verbatim, fuzz_score = _is_verbatim_or_fuzzy(quote, chart)
    options = q.get("response_options", []) or []
    has_escape = any(any(p in opt for p in ESCAPE_PHRASES) for opt in options)
    qt = q.get("query_text", "") or ""
    leading_hits = [p for p in LEADING_QUERY_PATTERNS if re.search(p, qt)]
    non_leading = (len(leading_hits) == 0) and (len(qt) >= 10)

    return {
        "query_id": q.get("query_id"),
        "evidence_quote_present": bool(quote),
        "evidence_quote_verbatim": verbatim,
        "evidence_quote_fuzz_score": round(fuzz_score, 3),
        "response_options_count": len(options),
        "response_options_has_escape": has_escape,
        "query_text_non_leading": non_leading,
        "leading_flags": leading_hits,
        "query_text_length": len(qt),
    }


def _score_case(case_data: dict, fixture_case: dict | None) -> dict:
    chart = case_data.get("chart_excerpt_preview", "") or ""
    queries = case_data.get("proposed_provider_queries", []) or []
    scored_queries = [_score_query(q, chart) for q in queries]

    # parse multi_dim_count from query_single_dimension_gate stage_run_ids string
    sdg = case_data.get("stage_run_ids", {}).get("query_single_dimension_gate", "") or ""
    m = re.search(r"multi_dim=(\d+)", sdg)
    multi_dim_count = int(m.group(1)) if m else 0

    # parse claim_evidence_alignment_gate blocked count
    ceg = case_data.get("stage_run_ids", {}).get("claim_evidence_alignment_gate", "") or ""
    m = re.search(r"blocked=(\d+)", ceg)
    cea_blocked = int(m.group(1)) if m else 0

    # parse semantic_necessity_gate degraded count
    sng = case_data.get("stage_run_ids", {}).get("semantic_necessity_gate", "") or ""
    m = re.search(r"degraded=(\d+)", sng)
    sem_degraded = int(m.group(1)) if m else 0

    # specialists
    specialists = case_data.get("specialist_trace", []) or []
    expert_summary = {}
    for s in specialists:
        eid = s.get("expert_id")
        if not eid:
            continue
        expert_summary[eid] = {
            "route_decision": s.get("route_decision"),
            "consulted": s.get("consulted"),
            "execution_mode": s.get("execution_mode"),
            "latency_ms": s.get("latency_ms", 0) or 0,
            "tokens": s.get("tokens", 0) or 0,
        }

    # contradiction preservation
    risk_flags = case_data.get("risk_flags", []) or []
    has_contradiction = any(
        ((rf.get("category") == "contradiction") or (rf.get("type") == "contradiction"))
        for rf in risk_flags
    )
    contradiction_preserved = has_contradiction and len(queries) > 0

    # final_count after single-dim gate (gate deterministically drops multi-dim)
    m = re.search(r"final_count=(\d+)", sdg)
    sdg_final = int(m.group(1)) if m else 0
    multi_dim_leaked = max(0, len(queries) - sdg_final)  # should always be 0

    return {
        "case_id": case_data.get("case_id"),
        "fixture_case_id": (fixture_case or {}).get("case_id"),
        "category": (fixture_case or {}).get("category"),
        "chart_length": len(chart),
        "query_count": len(queries),
        "scored_queries": scored_queries,
        "multi_dim_input_count": multi_dim_count,    # gate-prefilter volume (over-query prevention workload)
        "single_dim_gate_final_count": sdg_final,
        "multi_dim_leaked_count": multi_dim_leaked,   # final queries that are multi-dim (target = 0)
        "cea_blocked": cea_blocked,
        "semantic_degraded": sem_degraded,
        "expert_summary": expert_summary,
        "has_contradiction_risk_flag": has_contradiction,
        "contradiction_preserved_query_emitted": contradiction_preserved if has_contradiction else None,
        "completion_state": case_data.get("completion_state"),
        "degraded": case_data.get("degraded"),
    }


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _aggregate(per_case_results: list[dict]) -> dict:
    total_queries = sum(c["query_count"] for c in per_case_results)
    all_scored = [q for c in per_case_results for q in c["scored_queries"]]

    quality = {
        "total_queries": total_queries,
        "evidence_quote_present_rate": round(_safe_div(
            sum(1 for q in all_scored if q["evidence_quote_present"]), total_queries), 4),
        "evidence_quote_verbatim_rate": round(_safe_div(
            sum(1 for q in all_scored if q["evidence_quote_verbatim"]), total_queries), 4),
        "avg_evidence_quote_fuzz_score": round(_safe_div(
            sum(q["evidence_quote_fuzz_score"] for q in all_scored), len(all_scored)), 4),
        "response_options_4plus_rate": round(_safe_div(
            sum(1 for q in all_scored if q["response_options_count"] >= 4), total_queries), 4),
        "response_options_escape_hatch_rate": round(_safe_div(
            sum(1 for q in all_scored if q["response_options_has_escape"]), total_queries), 4),
        "non_leading_query_rate": round(_safe_div(
            sum(1 for q in all_scored if q["query_text_non_leading"]), total_queries), 4),
        "leading_query_count": sum(1 for q in all_scored if not q["query_text_non_leading"]),
    }

    safety = {
        "multi_dim_input_per_case": round(
            sum(c["multi_dim_input_count"] for c in per_case_results) / max(len(per_case_results), 1), 4),
        "multi_dim_input_total": sum(c["multi_dim_input_count"] for c in per_case_results),
        "multi_dim_leaked_total": sum(c["multi_dim_leaked_count"] for c in per_case_results),
        "multi_dim_leaked_rate": round(_safe_div(
            sum(c["multi_dim_leaked_count"] for c in per_case_results), total_queries), 4),
        "cases_with_multi_dim_input": sum(1 for c in per_case_results if c["multi_dim_input_count"] > 0),
        "unsupported_query_rate": round(_safe_div(
            sum(1 for q in all_scored if not q["evidence_quote_verbatim"]), total_queries), 4),
        "leading_query_rate": round(_safe_div(
            sum(1 for q in all_scored if not q["query_text_non_leading"]), total_queries), 4),
        # Contradiction proxy: fixture category == document_conflict (5 cases).
        # risk_flags are empty in iter 3 baseline — H3.10 override logic exists in
        # code but is not triggered because gap_identification does not emit
        # contradiction risk_flags. Carried forward as an H3.x observation.
        "document_conflict_cases_total": sum(1 for c in per_case_results if c.get("category") == "document_conflict"),
        "document_conflict_emit_cases": sum(1 for c in per_case_results
                                            if c.get("category") == "document_conflict" and c["query_count"] > 0),
        "contradiction_risk_flag_cases": sum(1 for c in per_case_results if c["has_contradiction_risk_flag"]),
    }
    if safety["document_conflict_cases_total"] > 0:
        safety["document_conflict_emit_rate"] = round(
            safety["document_conflict_emit_cases"] / safety["document_conflict_cases_total"], 4)
    else:
        safety["document_conflict_emit_rate"] = None

    # expert breakdown
    expert_ids = set()
    for c in per_case_results:
        expert_ids.update(c["expert_summary"].keys())
    expert_breakdown = {}
    for eid in sorted(expert_ids):
        needed = [c for c in per_case_results
                  if c["expert_summary"].get(eid, {}).get("route_decision") == "needed"]
        consulted = [c for c in per_case_results
                     if c["expert_summary"].get(eid, {}).get("consulted") is True]
        latencies = [c["expert_summary"][eid]["latency_ms"] for c in consulted]
        tokens = [c["expert_summary"][eid]["tokens"] for c in consulted]
        rejections = [c for c in needed if not c["expert_summary"][eid]["consulted"]]
        expert_breakdown[eid] = {
            "route_needed_count": len(needed),
            "consulted_count": len(consulted),
            "invoke_rate": round(len(consulted) / max(len(per_case_results), 1), 4),
            "avg_latency_ms_when_consulted": round(_safe_div(sum(latencies), len(latencies)), 1),
            "avg_tokens_when_consulted": round(_safe_div(sum(tokens), len(tokens)), 1),
            "rejection_count": len(rejections),
            "rejection_rate": round(_safe_div(len(rejections), max(len(needed), 1)), 4),
        }

    return {
        "quality": quality,
        "safety": safety,
        "expert": expert_breakdown,
    }


def _by_category(per_case_results: list[dict]) -> dict:
    by_cat: dict[str, dict] = {}
    for c in per_case_results:
        cat = c.get("category") or "unknown"
        by_cat.setdefault(cat, {"cases": 0, "queries": 0,
                                "multi_dim_input": 0, "multi_dim_leaked": 0,
                                "cea_blocked": 0, "sem_degraded": 0,
                                "leading": 0, "verbatim_pass": 0,
                                "options_4plus": 0, "escape_hatch": 0,
                                "emit_cases": 0})
        b = by_cat[cat]
        b["cases"] += 1
        b["queries"] += c["query_count"]
        b["multi_dim_input"] += c["multi_dim_input_count"]
        b["multi_dim_leaked"] += c["multi_dim_leaked_count"]
        b["cea_blocked"] += c["cea_blocked"]
        b["sem_degraded"] += c["semantic_degraded"]
        if c["query_count"] > 0:
            b["emit_cases"] += 1
        for q in c["scored_queries"]:
            if not q["query_text_non_leading"]:
                b["leading"] += 1
            if q["evidence_quote_verbatim"]:
                b["verbatim_pass"] += 1
            if q["response_options_count"] >= 4:
                b["options_4plus"] += 1
            if q["response_options_has_escape"]:
                b["escape_hatch"] += 1
    return by_cat


def main() -> int:
    if not PER_CASE_DIR.exists():
        print(f"ERROR: per-case dir not found: {PER_CASE_DIR}", file=sys.stderr)
        return 2

    fixture_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    fixture_cases = fixture_data.get("cases", [])
    fixture_by_id = {c["case_id"]: c for c in fixture_cases}

    per_case_results: list[dict] = []
    files = sorted(PER_CASE_DIR.glob("*.json"))
    for f in files:
        case_data = json.loads(f.read_text(encoding="utf-8"))
        fx_case_id = _extract_fixture_case_id_from_filename(f.name)
        fx = fixture_by_id.get(fx_case_id) if fx_case_id else None
        per_case_results.append(_score_case(case_data, fx))

    summary = _aggregate(per_case_results)
    by_category = _by_category(per_case_results)

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "_meta": {
            "source": "Track H4.1 — Quality + Safety + Expert scoring on iter 3 baseline",
            "case_count": len(per_case_results),
            "candidate": "icoder-cdi-agent-v1.0.0-rc1",
            "iter": 3,
            "per_case_dir": str(PER_CASE_DIR.relative_to(REPO_ROOT)),
        },
        "summary": summary,
        "by_category": by_category,
        "per_case": per_case_results,
    }
    OUTPUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # stdout summary
    q = summary["quality"]
    s = summary["safety"]
    e = summary["expert"]
    print()
    print("=" * 64)
    print("Track H4.1 — Quality + Safety + Expert scoring (iter 3 baseline)")
    print("=" * 64)
    print(f"Cases: {len(per_case_results)} | Total final queries: {q['total_queries']}")
    print()
    print("[A] QUALITY (per-query)")
    print(f"  evidence_quote_present_rate      : {q['evidence_quote_present_rate']:.3f}")
    print(f"  evidence_quote_verbatim_rate     : {q['evidence_quote_verbatim_rate']:.3f}")
    print(f"  avg_evidence_quote_fuzz_score    : {q['avg_evidence_quote_fuzz_score']:.3f}")
    print(f"  response_options_4plus_rate      : {q['response_options_4plus_rate']:.3f}")
    print(f"  response_options_escape_hatch_rate: {q['response_options_escape_hatch_rate']:.3f}")
    print(f"  non_leading_query_rate           : {q['non_leading_query_rate']:.3f}")
    print(f"  leading_query_count              : {q['leading_query_count']}")
    print()
    print("[B] SAFETY (per-case)")
    print(f"  multi_dim_input_per_case         : {s['multi_dim_input_per_case']:.3f}   (prevention workload, lower = cleaner)")
    print(f"  multi_dim_input_total            : {s['multi_dim_input_total']}   (queries caught by single-dim gate)")
    print(f"  multi_dim_leaked_total           : {s['multi_dim_leaked_total']}   (target = 0 — gate is deterministic)")
    print(f"  multi_dim_leaked_rate            : {s['multi_dim_leaked_rate']:.3f}   (target = 0.0)")
    print(f"  cases_with_multi_dim_input       : {s['cases_with_multi_dim_input']}")
    print(f"  unsupported_query_rate           : {s['unsupported_query_rate']:.3f}   (target = 0.0)")
    print(f"  leading_query_rate               : {s['leading_query_rate']:.3f}   (target = 0.0)")
    print(f"  document_conflict_cases_total    : {s['document_conflict_cases_total']}   (fixture category=CONFLICT)")
    print(f"  document_conflict_emit_cases     : {s['document_conflict_emit_cases']}")
    print(f"  document_conflict_emit_rate      : {s['document_conflict_emit_rate']}")
    print(f"  contradiction_risk_flag_cases    : {s['contradiction_risk_flag_cases']}   (H3.10 override prerequisite; observed = 0)")
    print()
    print("[C] EXPERT (per-Expert)")
    for eid, stats in e.items():
        print(f"  {eid:<28} invoke={stats['invoke_rate']:.2%}  "
              f"consulted={stats['consulted_count']}/40  "
              f"avg_lat={stats['avg_latency_ms_when_consulted']}ms  "
              f"avg_tok={stats['avg_tokens_when_consulted']}  "
              f"rej={stats['rejection_count']}")
    print()
    print("[D] BY CATEGORY  (cases / emit_cases / queries / md_input / md_leaked / cea_blocked / leading / verbatim_pass / options_4plus / escape)")
    for cat, b in sorted(by_category.items()):
        print(f"  {cat:<26} {b['cases']:>2}case {b['emit_cases']:>2}emit {b['queries']:>2}q  "
              f"md_in={b['multi_dim_input']} md_leak={b['multi_dim_leaked']} "
              f"cea={b['cea_blocked']} lead={b['leading']} verb={b['verbatim_pass']} "
              f"4+={b['options_4plus']} esc={b['escape_hatch']}")
    print()
    print(f"Output: {OUTPUT_JSON.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
