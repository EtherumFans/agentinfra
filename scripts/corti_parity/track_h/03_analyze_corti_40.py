"""Track H3.2 — Aggregate Corti 40-case results into analysis metrics.

Reads per-case JSONs from reports/track_h/corti_per_case/ and produces:
- reports/track_h/corti_40_aggregate.json  — per-case + per-group metrics
- prints summary table to stdout

Metrics per case:
- outcome (SUCCESS / FINAL_SYNTHESIS_MISSING / etc.)
- text_length, event_count, first_token_at_s, last_token_at_s
- gap_count, query_count (parsed)
- specialists_contacted (list)
- response_shape: "standard" | "input_required" | "refusal" | "empty" | "other"
- finish_state (from message-metadata: completed / input-required / etc.)
- credits_used
"""
from __future__ import annotations

import json
import re
from pathlib import Path


CASE_DIR = Path("reports/track_h/corti_per_case")
OUT = Path("reports/track_h/corti_40_aggregate.json")
FIXTURE = Path("backend/tests/fixtures/cdi_gate8_40cases.json")


def classify_shape(text: str, finish_meta: dict) -> str:
    state = (finish_meta or {}).get("state", "")
    if state == "input-required":
        return "input_required"
    if not text:
        return "empty"
    # Standard CDI output has these section headers
    if "Documentation Gaps:" in text and ("Proposed Provider Quer" in text or "Specialist Trace:" in text):
        return "standard"
    # Refusal patterns
    refusal_patterns = [
        r"can'?t safely recommend",
        r"not able to provide personalized",
        r"please provide the relevant chart",
        r"insufficient (clinical )?information",
        r"need more (clinical )?information",
    ]
    for p in refusal_patterns:
        if re.search(p, text, re.IGNORECASE):
            return "refusal"
    return "other"


def main() -> None:
    cases_fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected_by_id = {c["case_id"]: c for c in cases_fixture["cases"]}

    per_case = []
    for f in sorted(CASE_DIR.glob("*.json")):
        case_id = f.stem
        d = json.loads(f.read_text(encoding="utf-8"))
        text = d.get("text", "") or ""
        parsed = d.get("parsed", {}) or {}
        finish_meta = d.get("finish_metadata", {}) or {}
        expected = expected_by_id.get(case_id, {})

        per_case.append({
            "case_id": case_id,
            "group": d.get("group") or expected.get("group", ""),
            "outcome": d.get("outcome", ""),
            "text_length": d.get("text_length", len(text)),
            "event_count": d.get("event_count", 0),
            "first_token_at_s": d.get("first_token_at_s"),
            "stream_duration_s": d.get("elapsed_s") or d.get("stream_duration_s"),
            "gap_count": parsed.get("gap_count", 0),
            "query_count": parsed.get("query_count", 0),
            "specialists_contacted": parsed.get("specialists_contacted", []),
            "response_shape": classify_shape(text, finish_meta),
            "finish_state": finish_meta.get("state", ""),
            "credits_used": finish_meta.get("credits"),
            "expected_query_count_min": expected.get("expected", {}).get("query_count_min"),
            "expected_query_count_max": expected.get("expected", {}).get("query_count_max"),
            "expected_no_query": expected.get("expected", {}).get("no_query_expected"),
            "text_preview": text[:300] + ("..." if len(text) > 300 else ""),
        })

    # Aggregate by group
    by_group: dict[str, dict] = {}
    for c in per_case:
        g = c["group"]
        if g not in by_group:
            by_group[g] = {
                "case_count": 0,
                "success_count": 0,
                "gap_count_sum": 0,
                "query_count_sum": 0,
                "input_required_count": 0,
                "refusal_count": 0,
                "standard_count": 0,
                "empty_count": 0,
                "other_count": 0,
                "avg_text_length": 0,
                "avg_first_token_s": 0,
                "avg_duration_s": 0,
                "specialist_usage": {},
            }
        bg = by_group[g]
        bg["case_count"] += 1
        if c["outcome"] == "SUCCESS":
            bg["success_count"] += 1
        bg["gap_count_sum"] += c["gap_count"]
        bg["query_count_sum"] += c["query_count"]
        bg[f"{c['response_shape']}_count"] += 1
        bg["avg_text_length"] += c["text_length"]
        bg["avg_first_token_s"] += c["first_token_at_s"] or 0
        bg["avg_duration_s"] += c["stream_duration_s"] or 0
        for s in c["specialists_contacted"]:
            bg["specialist_usage"][s] = bg["specialist_usage"].get(s, 0) + 1

    for g, bg in by_group.items():
        n = bg["case_count"]
        if n:
            bg["avg_text_length"] = round(bg["avg_text_length"] / n, 1)
            bg["avg_first_token_s"] = round(bg["avg_first_token_s"] / n, 2)
            bg["avg_duration_s"] = round(bg["avg_duration_s"] / n, 2)
            bg["avg_gap_count"] = round(bg["gap_count_sum"] / n, 2)
            bg["avg_query_count"] = round(bg["query_count_sum"] / n, 2)

    # Totals
    totals = {
        "case_count": len(per_case),
        "success_count": sum(1 for c in per_case if c["outcome"] == "SUCCESS"),
        "input_required_count": sum(1 for c in per_case if c["response_shape"] == "input_required"),
        "refusal_count": sum(1 for c in per_case if c["response_shape"] == "refusal"),
        "standard_count": sum(1 for c in per_case if c["response_shape"] == "standard"),
        "empty_count": sum(1 for c in per_case if c["response_shape"] == "empty"),
        "other_count": sum(1 for c in per_case if c["response_shape"] == "other"),
        "total_credits_used": round(sum(c["credits_used"] or 0 for c in per_case), 4),
    }

    # Range conformance: how many cases fell within expected query_count_min/max?
    range_conformant = 0
    range_violations = []
    for c in per_case:
        e_min = c.get("expected_query_count_min")
        e_max = c.get("expected_query_count_max")
        q = c["query_count"]
        if e_min is None or e_max is None:
            continue
        if e_min <= q <= e_max:
            range_conformant += 1
        else:
            range_violations.append({
                "case_id": c["case_id"],
                "group": c["group"],
                "query_count": q,
                "expected_min": e_min,
                "expected_max": e_max,
                "delta": q - e_max if q > e_max else q - e_min,
            })

    # Negation safety: cases where expected_no_query=True
    neg_safety_total = 0
    neg_safety_violations = []
    for c in per_case:
        if c.get("expected_no_query"):
            neg_safety_total += 1
            if c["query_count"] > 0:
                neg_safety_violations.append({
                    "case_id": c["case_id"],
                    "group": c["group"],
                    "query_count": c["query_count"],
                })

    output = {
        "_meta": {
            "source": "Track H3.2 — Corti 40-case aggregate analysis",
            "generated_at": cases_fixture.get("_meta", {}).get("generated_at", ""),
            "case_count": len(per_case),
        },
        "totals": totals,
        "range_conformance": {
            "total_checkable": sum(1 for c in per_case if c.get("expected_query_count_min") is not None),
            "conformant": range_conformant,
            "violations": range_violations,
        },
        "negation_safety": {
            "total_no_query_expected": neg_safety_total,
            "violations": neg_safety_violations,
        },
        "by_group": by_group,
        "per_case": per_case,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {OUT}")
    print()
    print(f"=== Totals (n={totals['case_count']}) ===")
    print(f"  SUCCESS (stream completed): {totals['success_count']}")
    print(f"  Response shape:")
    print(f"    standard:        {totals['standard_count']}")
    print(f"    input_required:  {totals['input_required_count']}")
    print(f"    refusal:         {totals['refusal_count']}")
    print(f"    empty:           {totals['empty_count']}")
    print(f"    other:           {totals['other_count']}")
    print(f"  Total credits: {totals['total_credits_used']}")
    print()
    print(f"=== Range Conformance ===")
    rc = output["range_conformance"]
    print(f"  {rc['conformant']}/{rc['total_checkable']} cases within expected query_count range")
    if rc["violations"]:
        print("  Violations:")
        for v in rc["violations"][:10]:
            print(f"    {v['case_id']} ({v['group']}): q={v['query_count']}, expected [{v['expected_min']}, {v['expected_max']}], delta={v['delta']}")
    print()
    print(f"=== Negation Safety (expected no query) ===")
    ns = output["negation_safety"]
    print(f"  {ns['total_no_query_expected'] - len(ns['violations'])}/{ns['total_no_query_expected']} cases correctly emitted 0 queries")
    if ns["violations"]:
        print("  Violations:")
        for v in ns["violations"]:
            print(f"    {v['case_id']} ({v['group']}): emitted {v['query_count']} queries (expected 0)")
    print()
    print(f"=== Per-group ===")
    for g, bg in by_group.items():
        print(f"  {g} (n={bg['case_count']}):")
        print(f"    avg gap_count={bg.get('avg_gap_count')}, avg query_count={bg.get('avg_query_count')}")
        print(f"    avg text_length={bg['avg_text_length']}, avg duration={bg['avg_duration_s']}s")
        print(f"    shapes: standard={bg['standard_count']}, input_required={bg['input_required_count']}, refusal={bg['refusal_count']}, other={bg['other_count']}")


if __name__ == "__main__":
    main()
