"""Combine prompt and retrieve eval reports into prompt+retrieve variant.

Reads two JSON reports produced by e2e_medcoder_validation.py, unions their
per-case predicted top-5 lists, and recomputes F1@K on the union. This
sidesteps the Windows OpenMP segfault that occurs when httpx (LLM) and
BGE-M3 (retriever) are loaded in the same process.
"""
import argparse
import json
from collections import OrderedDict
from pathlib import Path

from e2e_medcoder_validation import f1_at_k, extract_gold_codes, _norm_code


def load_report(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_predictions(prompt_pred: list[str], retrieve_pred: list[str]) -> list[str]:
    """Union of two ordered lists, preserving order, deduped (normalized)."""
    seen: set[str] = set()
    out: list[str] = []
    for c in (prompt_pred or []) + (retrieve_pred or []):
        if not c:
            continue
        n = _norm_code(c)
        if n in seen:
            continue
        seen.add(n)
        out.append(c)
    return out


def merge_reports(prompt_report: dict, retrieve_report: dict, k_values=(1, 2, 5)) -> dict:
    """Build a synthetic prompt+retrieve report from two single-variant reports."""
    by_id_p = {c["case_id"]: c for c in prompt_report["per_case"]}
    by_id_r = {c["case_id"]: c for c in retrieve_report["per_case"]}
    common = sorted(set(by_id_p) & set(by_id_r))
    per_case = []
    for cid in common:
        p_top = by_id_p[cid].get("predicted_top_5", [])
        r_top = by_id_r[cid].get("predicted_top_5", [])
        gold = set(by_id_p[cid].get("gold", [])) | set(by_id_r[cid].get("gold", []))
        top_k = merge_predictions(p_top, r_top)
        per_k = {k: f1_at_k(gold, top_k, k) for k in k_values}
        per_case.append({
            "case_id": cid,
            "gold": sorted(gold),
            "predicted_top_5": top_k[:5],
            "f1_at_1": per_k.get(1, 0.0),
            "f1_at_2": per_k.get(2, 0.0),
            "f1_at_5": per_k.get(5, 0.0),
            "latency_s": (by_id_p[cid].get("latency_s", 0) + by_id_r[cid].get("latency_s", 0)),
        })

    n = max(len(per_case), 1)
    summary = {
        "variant": "prompt+retrieve",
        "n_cases": len(per_case),
        "f1_at_1": round(sum(c["f1_at_1"] for c in per_case) / n, 4),
        "f1_at_2": round(sum(c["f1_at_2"] for c in per_case) / n, 4),
        "f1_at_5": round(sum(c["f1_at_5"] for c in per_case) / n, 4),
        "avg_latency_s": round(sum(c["latency_s"] for c in per_case) / n, 3),
        "source": {
            "prompt_report": args.prompt_report,
            "retrieve_report": args.retrieve_report,
        },
    }
    return {"summary": summary, "per_case": per_case}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-report", required=True)
    parser.add_argument("--retrieve-report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    pr = load_report(args.prompt_report)
    rr = load_report(args.retrieve_report)
    merged = merge_reports(pr, rr)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print("=== prompt+retrieve (merged) ===")
    for k, v in merged["summary"].items():
        if k != "source":
            print(f"  {k}: {v}")
    print(f"  report: {args.out}")
