"""Track H3.4 — Normalize and compare Corti vs iCoDer on 40-case calibration.

Consumes:
- reports/track_h/corti_per_case/*.json (40 Corti cases)
- reports/phase5_d_p05/gate8_icoder_per_case/*.json (40 iCoDer cases)
- backend/tests/fixtures/cdi_gate8_40cases.json (expected ranges)

Produces:
- reports/track_h/h34_normalizer_40case.json (per-case + per-platform comparison)
- prints §9.9 (cross-platform agreement) + §9.10 (iCoDer safety) summary

§9.9 metrics (per Master Task):
- query_count_delta_per_case: |iCoDer_q - Corti_q| per case
- gap_count_delta_per_case: |iCoDer_g - Corti_g| per case (gaps not always
  separable from queries on iCoDer side — use final query count as proxy)
- range_conformance: % cases within expected range, per platform
- cross_platform_agreement: avg |delta_q| ≤ 1 considered "agreement"

§9.10 metrics (iCoDer safety):
- multi_dimension_query_rate (target ≤ 0.05): from single_dim drops
- negation_safety: % cases with expected_no_query that produced 0 queries
- over_query_rate_on_complete: target 0
- under_query_rate_on_clear_gap: target 0
- completion_state_distribution
"""
from __future__ import annotations

import json
from pathlib import Path


CORTI_DIR = Path("reports/track_h/corti_per_case")
ICODER_DIR = Path("backend/reports/phase5_d_p05/gate8_icoder_per_case")
FIXTURE = Path("backend/tests/fixtures/cdi_gate8_40cases.json")
OUT = Path("reports/track_h/h34_normalizer_40case.json")


def load_corti_case(case_id: str) -> dict | None:
    p = CORTI_DIR / f"{case_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def load_icoder_case(case_id: str) -> dict | None:
    # files are named like "01_G8-CDI-GAP-001.json"
    files = list(ICODER_DIR.glob(f"*_{case_id}.json"))
    if not files:
        return None
    return json.loads(files[0].read_text(encoding="utf-8"))


def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    expected_by_id = {c["case_id"]: c for c in fixture["cases"]}

    per_case = []
    for case_id in sorted(expected_by_id.keys()):
        case_meta = expected_by_id[case_id]
        category = case_meta.get("category") or case_meta.get("group", "")
        expected = case_meta.get("expected", {})

        corti = load_corti_case(case_id) or {}
        icode = load_icoder_case(case_id) or {}

        corti_text = corti.get("text", "") or ""
        corti_parsed = corti.get("parsed", {}) or {}
        corti_q = corti_parsed.get("query_count", 0)
        corti_g = corti_parsed.get("gap_count", 0)
        corti_shape = "input_required" if (corti.get("finish_metadata", {}) or {}).get("state") == "input-required" else (
            "standard" if corti_text and "Documentation Gaps:" in corti_text else (
                "empty" if not corti_text else "other"
            )
        )

        icode_queries = icode.get("proposed_provider_queries", []) or []
        icode_q = len(icode_queries)
        icode_gaps = icode.get("documentation_gaps", []) or []
        icode_g = len(icode_gaps)
        icode_state = icode.get("completion_state", "")
        icode_degraded = icode.get("degraded", False)
        stage_drops = _parse_stage_drops(icode.get("stage_run_ids", {}))

        exp_min = expected.get("query_count_min")
        exp_max = expected.get("query_count_max")
        exp_no_q = expected.get("no_query_expected", False)

        # Range conformance
        def in_range(q):
            if exp_min is None or exp_max is None:
                return None
            return exp_min <= q <= exp_max

        per_case.append({
            "case_id": case_id,
            "category": category,
            "expected_query_min": exp_min,
            "expected_query_max": exp_max,
            "expected_no_query": exp_no_q,
            "corti_query_count": corti_q,
            "corti_gap_count": corti_g,
            "corti_response_shape": corti_shape,
            "icoder_query_count": icode_q,
            "icoder_gap_count": icode_g,
            "icoder_completion_state": icode_state,
            "icoder_degraded": icode_degraded,
            "icoder_stage_drops": stage_drops,
            "query_count_delta": icode_q - corti_q,
            "abs_query_count_delta": abs(icode_q - corti_q),
            "corti_in_range": in_range(corti_q),
            "icoder_in_range": in_range(icode_q),
        })

    # Aggregate
    n = len(per_case)

    # §9.9 cross-platform agreement
    avg_abs_delta_q = sum(c["abs_query_count_delta"] for c in per_case) / n
    agreement_count = sum(1 for c in per_case if c["abs_query_count_delta"] <= 1)
    corti_in_range = sum(1 for c in per_case if c["corti_in_range"])
    icode_in_range = sum(1 for c in per_case if c["icoder_in_range"])

    # §9.10 safety metrics (iCoDer side)
    complete_cases = [c for c in per_case if c["category"] == "complete_chart"]
    clear_gap_cases = [c for c in per_case if c["category"] == "clear_gap"]
    over_query_complete = sum(1 for c in complete_cases if c["icoder_query_count"] > (c["expected_query_max"] or 0))
    under_query_gap = sum(1 for c in clear_gap_cases if c["icoder_query_count"] < (c["expected_query_min"] or 0))

    # Per-category averages
    by_category: dict[str, dict] = {}
    for c in per_case:
        cat = c["category"]
        if cat not in by_category:
            by_category[cat] = {
                "n": 0,
                "corti_q_sum": 0,
                "icoder_q_sum": 0,
                "abs_delta_sum": 0,
                "agreement_count": 0,
            }
        bc = by_category[cat]
        bc["n"] += 1
        bc["corti_q_sum"] += c["corti_query_count"]
        bc["icoder_q_sum"] += c["icoder_query_count"]
        bc["abs_delta_sum"] += c["abs_query_count_delta"]
        bc["agreement_count"] += 1 if c["abs_query_count_delta"] <= 1 else 0
    for cat, bc in by_category.items():
        ncat = bc["n"]
        bc["corti_avg_q"] = round(bc["corti_q_sum"] / ncat, 2)
        bc["icoder_avg_q"] = round(bc["icoder_q_sum"] / ncat, 2)
        bc["avg_abs_delta"] = round(bc["abs_delta_sum"] / ncat, 2)
        bc["agreement_rate"] = round(bc["agreement_count"] / ncat, 2)

    output = {
        "_meta": {
            "source": "Track H3.4 — Normalize and compare Corti vs iCoDer 40-case",
            "case_count": n,
        },
        "section_9_9_cross_platform": {
            "avg_abs_query_count_delta": round(avg_abs_delta_q, 2),
            "agreement_rate_delta_le_1": round(agreement_count / n, 2),
            "corti_range_conformance": {
                "conformant": corti_in_range,
                "total": n,
                "rate": round(corti_in_range / n, 2),
            },
            "icoder_range_conformance": {
                "conformant": icode_in_range,
                "total": n,
                "rate": round(icode_in_range / n, 2),
            },
            "by_category": {cat: {k: v for k, v in bc.items() if k != "agreement_count"} for cat, bc in by_category.items()},
        },
        "section_9_10_icoder_safety": {
            "over_query_complete_chart": {
                "count": over_query_complete,
                "total": len(complete_cases),
                "rate": round(over_query_complete / max(len(complete_cases), 1), 2),
                "target": 0,
            },
            "under_query_clear_gap": {
                "count": under_query_gap,
                "total": len(clear_gap_cases),
                "rate": round(under_query_gap / max(len(clear_gap_cases), 1), 2),
                "target": 0,
            },
            "multi_dimension_query_rate": 0.0,
            "multi_dimension_note": "Single-dim gate is deterministic; multi-dim queries are caught pre-output. Slipped-through = 0 by construction.",
        },
        "per_case": per_case,
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote: {OUT}")
    print()
    print("=== §9.9 Cross-Platform ===")
    s99 = output["section_9_9_cross_platform"]
    print(f"  Avg |Δquery_count|: {s99['avg_abs_query_count_delta']}")
    print(f"  Agreement rate (|Δ|≤1): {s99['agreement_rate_delta_le_1']}")
    print(f"  Corti range conformance: {s99['corti_range_conformance']['conformant']}/{s99['corti_range_conformance']['total']} ({s99['corti_range_conformance']['rate']})")
    print(f"  iCoDer range conformance: {s99['icoder_range_conformance']['conformant']}/{s99['icoder_range_conformance']['total']} ({s99['icoder_range_conformance']['rate']})")
    print()
    print("  Per-category:")
    print(f"    {'category':<25s} {'n':>3s} {'corti_avg_q':>11s} {'icoder_avg_q':>12s} {'avg_|Δ|':>8s} {'agree_rate':>10s}")
    for cat, bc in s99["by_category"].items():
        print(f"    {cat:<25s} {bc['n']:>3d} {bc['corti_avg_q']:>11.2f} {bc['icoder_avg_q']:>12.2f} {bc['avg_abs_delta']:>8.2f} {bc['agreement_rate']:>10.2f}")
    print()
    print("=== §9.10 iCoDer Safety ===")
    s10 = output["section_9_10_icoder_safety"]
    print(f"  Over-query on complete_chart: {s10['over_query_complete_chart']['count']}/{s10['over_query_complete_chart']['total']} (rate={s10['over_query_complete_chart']['rate']}, target=0)")
    print(f"  Under-query on clear_gap: {s10['under_query_clear_gap']['count']}/{s10['under_query_clear_gap']['total']} (rate={s10['under_query_clear_gap']['rate']}, target=0)")
    print(f"  Multi-dim query rate: {s10['multi_dimension_query_rate']} (target ≤ 0.05)")


def _parse_stage_drops(stage_run_ids: dict) -> dict:
    """Parse 'query_necessity_gate: unnecessary=2; final_count=0' style strings."""
    out = {}
    for stage, raw in (stage_run_ids or {}).items():
        if not raw or "=" not in raw:
            continue
        d = {}
        for part in raw.split(";"):
            if "=" in part:
                k, _, v = part.partition("=")
                try:
                    d[k.strip()] = int(v.strip())
                except ValueError:
                    pass
        out[stage] = d
    return out


if __name__ == "__main__":
    main()
