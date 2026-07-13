"""Analyze H1.2 minimal-pair + H1.3 expert-routing results.

For H1.2 (minimal-pair), pair A/B per group and compare Corti's emitted query
count + topics. Goal: characterize Corti's timeline reconstruction (ENC-003)
behavior — does Corti distinguish minimal pairs the way the iCoDer
eligibility/CEA gates do?

For H1.3 (expert-routing), enumerate which Experts Corti invoked per case.
Goal: characterize EXP-002 (AMBOSS-style expert) + EXP-005 (rejection behavior).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


PER_CASE = Path("reports/track_h/h1x_probes_per_case")
FIXTURE = Path("tests/fixtures/track_h_mechanism_probes.json")
OUT = Path("reports/track_h/h1x_analysis.json")


def _classify_expert_event(ev: dict) -> str:
    """Classify a Corti expert event by its shape."""
    if ev.get("code_system"):
        return "coding-expert"
    if "sections" in ev and any("icd-10" in str(s).lower() for s in ev.get("sections", [])):
        return "coding-expert"  # guidelines tool
    resp = ev.get("response", "") or ""
    if "web_result" in resp or "tavily" in resp:
        return "web-search-expert"
    if "pubmed" in resp.lower() or "abstract" in ev:
        return "pubmed-expert"
    if "calculator" in str(ev).lower() or "score" in ev:
        return "medical-calculator-expert"
    return "unknown"


def _parse_final_response(record: dict) -> dict:
    """Pull Corti's structured response from per-case JSON."""
    text = record.get("text", "") or ""
    parsed = record.get("parsed", {}) or {}
    expert_events = record.get("expert_events", []) or []

    gaps = parsed.get("gaps", []) or []
    q_section = ""
    m = re.search(r"Proposed Provider Queries:\s*(.*?)(?:\n\n[A-Z][a-z]+:|\Z)", text, re.DOTALL)
    if m:
        q_section = m.group(1)
    query_count = len(re.findall(r"^\s*\d+\.\s+Topic:", q_section, re.MULTILINE))
    if query_count == 0:
        query_count = len(re.findall(r"^\s*\d+\.\s", q_section, re.MULTILINE))

    # Classify each expert event
    classified = [_classify_expert_event(e) for e in expert_events]
    from collections import Counter
    expert_counts = dict(Counter(classified))

    return {
        "chart_complete": len(gaps) == 0 and query_count == 0,
        "gap_count": len(gaps),
        "query_count": query_count,
        "queries_preview": [q.strip()[:200] for q in re.findall(r"\d+\.\s+Topic:[^\n]+", q_section)][:3],
        "experts_invoked": sorted(set(classified)),
        "expert_event_count": len(expert_events),
        "expert_counts": expert_counts,
        "final_text_len": len(text),
    }


def analyze_h12_minimal_pair() -> dict:
    """For each group with A/B variants, compare Corti outputs."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    groups: dict[str, list] = defaultdict(list)
    for c in fixture["cases"]:
        if c.get("variant") in ("A", "B"):
            groups[c["group"]].append(c)

    out: dict[str, dict] = {}
    for group, cases in sorted(groups.items()):
        if len(cases) < 2:
            continue
        a, b = cases[0], cases[1]
        rec_a = json.loads((PER_CASE / f"{a['case_id']}.json").read_text(encoding="utf-8"))
        rec_b = json.loads((PER_CASE / f"{b['case_id']}.json").read_text(encoding="utf-8"))
        pa = _parse_final_response(rec_a)
        pb = _parse_final_response(rec_b)

        out[group] = {
            "variable_under_test": a.get("variable_under_test", ""),
            "case_a": {
                "id": a["case_id"],
                "expected": a.get("expected", {}),
                "actual": pa,
            },
            "case_b": {
                "id": b["case_id"],
                "expected": b.get("expected", {}),
                "actual": pb,
            },
            "delta": {
                "query_count": pa["query_count"] - pb["query_count"],
                "gap_count": pa["gap_count"] - pb["gap_count"],
                "chart_complete_flip": (
                    "Y" if pa["chart_complete"] != pb["chart_complete"] else "N"
                ),
                "experts_a": pa["experts_invoked"],
                "experts_b": pb["experts_invoked"],
            },
        }
    return out


def analyze_h13_expert_routing() -> dict:
    """For each EXPERT_ROUTING case, list the experts Corti invoked."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out: dict[str, dict] = {}
    for c in fixture["cases"]:
        if c.get("group") != "EXPERT_ROUTING":
            continue
        cid = c["case_id"]
        p = PER_CASE / f"{cid}.json"
        if not p.exists():
            out[cid] = {"error": "missing per-case file"}
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        parsed = _parse_final_response(rec)

        # Also peek at raw events for tool-call signals
        raw_events = rec.get("raw_first_events", []) or rec.get("raw_events", [])
        tool_signals: list[str] = []
        for ev in raw_events:
            ev_str = str(ev)
            if "tool" in ev_str.lower() or "expert" in ev_str.lower() or "invoke" in ev_str.lower():
                tool_signals.append(ev_str[:200])

        out[cid] = {
            "notes": c.get("notes", ""),
            "expected_expert": c.get("variable_under_test", ""),
            "actual_specialists": parsed["experts_invoked"],
            "expert_counts": parsed["expert_counts"],
            "expert_event_count": parsed["expert_event_count"],
            "query_count": parsed["query_count"],
            "gap_count": parsed["gap_count"],
            "chart_complete": parsed["chart_complete"],
            "tool_signals_count": len(tool_signals),
            "tool_signals_preview": tool_signals[:3],
        }
    return out


def main() -> int:
    h12 = analyze_h12_minimal_pair()
    h13 = analyze_h13_expert_routing()
    summary = {
        "h12_minimal_pair": h12,
        "h13_expert_routing": h13,
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")

    print("\n=== H1.2 minimal-pair summary ===")
    print(f"  {'group':22s} {'variable_under_test':30s} {'Ag':>3s} {'Bg':>3s} {'Aq':>3s} {'Bq':>3s} {'Δq':>3s} {'flip':>5s}")
    for group, d in h12.items():
        ga = d["case_a"]["actual"]["gap_count"]
        gb = d["case_b"]["actual"]["gap_count"]
        qa = d["case_a"]["actual"]["query_count"]
        qb = d["case_b"]["actual"]["query_count"]
        print(f"  {group:22s} {d['variable_under_test']:30s} {ga:>3d} {gb:>3d} {qa:>3d} {qb:>3d} {d['delta']['query_count']:+3d} {d['delta']['chart_complete_flip']:>5s}")

    print("\n=== H1.3 expert-routing summary ===")
    for cid, d in h13.items():
        if "error" in d:
            print(f"  {cid}: ERROR {d['error']}")
            continue
        print(f"  {cid:20s} expected={d['expected_expert']:25s} invoked={d['actual_specialists']} counts={d['expert_counts']} q={d['query_count']} gaps={d['gap_count']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
