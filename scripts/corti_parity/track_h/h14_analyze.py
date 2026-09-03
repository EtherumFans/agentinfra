"""Analyze H1.4 repeatability: per-base-case variance across 3 runs.

Resolves OPS-005 (token variance) + OPS-007 (failure handling consistency).
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from pathlib import Path


PER_CASE = Path("reports/track_h/h1x_repeatability_per_case")
FIXTURE = Path("tests/fixtures/track_h_repeatability.json")
OUT = Path("reports/track_h/h14_repeatability_analysis.json")


def _parse(record: dict) -> dict:
    text = record.get("text", "") or ""
    parsed = record.get("parsed", {}) or {}
    gaps = parsed.get("gaps", []) or []
    import re
    q_section = ""
    m = re.search(r"Proposed Provider Queries:\s*(.*?)(?:\n\n[A-Z][a-z]+:|\Z)", text, re.DOTALL)
    if m:
        q_section = m.group(1)
    q_count = len(re.findall(r"^\s*\d+\.\s+Topic:", q_section, re.MULTILINE))
    if q_count == 0:
        q_count = len(re.findall(r"^\s*\d+\.\s", q_section, re.MULTILINE))
    return {
        "query_count": q_count,
        "gap_count": len(gaps),
        "text_len": len(text),
        "outcome": record.get("outcome"),
        "elapsed_s": record.get("elapsed_s"),
        "event_count": record.get("event_count"),
        "credits": (record.get("finish_metadata") or {}).get("credits"),
    }


def main() -> int:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    base_ids = fixture["_meta"]["base_case_ids"]

    grouped: dict[str, list[dict]] = defaultdict(list)
    for base in base_ids:
        for r in (1, 2, 3):
            p = PER_CASE / f"{base}_R{r}.json"
            if not p.exists():
                continue
            rec = json.loads(p.read_text(encoding="utf-8"))
            parsed = _parse(rec)
            parsed["run_idx"] = r
            grouped[base].append(parsed)

    out: dict[str, dict] = {}
    for base, runs in grouped.items():
        if len(runs) < 2:
            continue
        q_counts = [r["query_count"] for r in runs]
        g_counts = [r["gap_count"] for r in runs]
        text_lens = [r["text_len"] for r in runs]
        credits = [r["credits"] for r in runs if r["credits"] is not None]
        elapsed = [r["elapsed_s"] for r in runs if r["elapsed_s"]]

        out[base] = {
            "runs": runs,
            "query_count_per_run": q_counts,
            "query_count_variance": statistics.pvariance(q_counts) if len(q_counts) > 1 else 0,
            "query_count_stddev": statistics.pstdev(q_counts) if len(q_counts) > 1 else 0,
            "query_count_agreement": len(set(q_counts)) == 1,
            "gap_count_per_run": g_counts,
            "gap_count_agreement": len(set(g_counts)) == 1,
            "text_len_per_run": text_lens,
            "credits_per_run": credits,
            "credits_stddev": statistics.pstdev(credits) if len(credits) > 1 else 0,
            "elapsed_per_run": elapsed,
            "outcome_per_run": [r["outcome"] for r in runs],
            "outcome_agreement": len(set(r["outcome"] for r in runs)) == 1,
        }

    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}\n")

    print(f"{'base_case':22s} {'q_per_run':18s} {'q_agree':>8s} {'g_agree':>8s} {'o_agree':>8s} {'credits_std':>12s} {'avg_elapsed':>12s}")
    for base, d in out.items():
        q_str = str(d["query_count_per_run"])
        q_agree = "Y" if d["query_count_agreement"] else "N"
        g_agree = "Y" if d["gap_count_agreement"] else "N"
        o_agree = "Y" if d["outcome_agreement"] else "N"
        cs = f"{d['credits_stddev']:.4f}" if d["credits_stddev"] is not None else "n/a"
        ae = f"{statistics.mean(d['elapsed_per_run']):.1f}s" if d["elapsed_per_run"] else "n/a"
        print(f"{base:22s} {q_str:18s} {q_agree:>8s} {g_agree:>8s} {o_agree:>8s} {cs:>12s} {ae:>12s}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
