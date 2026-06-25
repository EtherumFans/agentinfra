"""analyze_retrieval.py — Compute retrieval-layer metrics from the FAISS index.

M2.5 governance: measures how well Stage 2 (BGE-M3 + FAISS) actually
recalls gold ICD codes for the 20-case icoder_201 fixture.

Metrics:
  - Retrieval Hit Rate (% cases where Stage 2 returns ≥ 1 candidate)
  - Top-k Coverage (mean |retrieved_top_k| across all disease mentions)
  - Recall@k (fraction of gold codes that appear in retrieved top-k)
  - Per-case breakdown + aggregate

This is a **retrieval-only** analyzer — it does NOT touch the LLM
prompt, calibration, or rerank stages. It's a separate script so
the main e2e_medcoder_validation.py stays untouched.

Usage:
    python scripts/analyze_retrieval.py \\
        --cases tests/fixtures/icoder_201.json \\
        --index-dir data/medcoder \\
        --top-k 20 \\
        --out reports/retrieval_analysis.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

# Make backend root importable
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("analyze_retrieval")


def _norm_code(code: str) -> str:
    """Subdivision-tolerant ICD-10 normalization."""
    if not code:
        return ""
    c = code.strip().upper()
    # Normalize trailing zeros after dot (I50.900 == I50.9)
    if "." in c:
        prefix, suffix = c.split(".", 1)
        suffix = suffix.rstrip("0").rstrip(".")
        c = f"{prefix}.{suffix}" if suffix else prefix
    return c


def _extract_gold_codes(case: dict) -> list[str]:
    """Pull gold ICD codes from a fixture case.

    The icoder_201.json fixture has each case with one or more diagnoses
    in a structure like:
        {"encounter_id": "...", "diagnoses": [{"code": "I50.900", ...}, ...]}
    or
        {"encounter_id": "...", "primary_diagnosis": "I50.900", "secondary_diagnoses": [...]}
    """
    codes: list[str] = []
    for d in case.get("diagnoses", []) or []:
        if isinstance(d, dict) and d.get("code"):
            codes.append(d["code"])
        elif isinstance(d, str):
            codes.append(d)
    if case.get("primary_diagnosis"):
        if isinstance(case["primary_diagnosis"], dict):
            if case["primary_diagnosis"].get("code"):
                codes.append(case["primary_diagnosis"]["code"])
        elif isinstance(case["primary_diagnosis"], str):
            codes.append(case["primary_diagnosis"])
    for sd in case.get("secondary_diagnoses", []) or []:
        if isinstance(sd, dict) and sd.get("code"):
            codes.append(sd["code"])
        elif isinstance(sd, str):
            codes.append(sd)
    return list(dict.fromkeys(codes))  # dedup preserving order


def _extract_query_text(case: dict) -> str:
    """Pull the natural-language disease mentions for retrieval.

    The fixture typically carries ``chief_complaint`` / ``present_illness``
    / ``discharge_diagnosis_text`` / ``primary_diagnosis_text`` etc. We
    concatenate whatever is available.
    """
    parts: list[str] = []
    for key in (
        "chief_complaint", "present_illness", "discharge_diagnosis_text",
        "primary_diagnosis_text", "admission_diagnosis", "diagnosis_text",
    ):
        v = case.get(key)
        if isinstance(v, str) and v.strip():
            parts.append(v.strip())
    for d in case.get("diagnoses", []) or []:
        if isinstance(d, dict):
            for k in ("name_cn", "name_en", "text"):
                v = d.get(k)
                if isinstance(v, str) and v.strip():
                    parts.append(v.strip())
                    break
    if not parts:
        # Fall back to concatenating every string field
        for k, v in case.items():
            if isinstance(v, str) and len(v) < 200 and v.strip():
                parts.append(v.strip())
    # Split into sentence-like chunks for per-disease retrieval
    blob = " ".join(parts)
    sentences = re.split(r"[。；;!?！？\n]+", blob)
    return [s.strip() for s in sentences if s.strip()]


async def _load_retriever(index_dir: str | Path):
    """Load the live MedCodER retriever (BGE-M3 + FAISS)."""
    from icoder_runtime.providers.medical_coding.medcoder_retriever import (
        MedCodERRetriever,
    )
    r = MedCodERRetriever(index_dir=Path(index_dir))
    # Trigger lazy load
    if hasattr(r, "_ensure_loaded"):
        r._ensure_loaded()
    return r


async def _analyze_one_case(
    case: dict, retriever, top_k: int,
) -> dict:
    """Run Stage 2 on each disease mention in a case; compute recall/hit."""
    case_id = case.get("encounter_id", case.get("id", "case"))
    gold = _extract_gold_codes(case)
    gold_norm = {_norm_code(g) for g in gold if g}

    queries = _extract_query_text(case) or [""]
    per_query: list[dict] = []
    all_retrieved_codes: set[str] = set()
    n_retrieved_total = 0

    for q in queries:
        try:
            candidates = await retriever.retrieve_async(q, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            logger.warning("retrieve failed for %r: %s", q[:30], e)
            candidates = []
        n_retrieved_total += len(candidates)
        for c in candidates:
            all_retrieved_codes.add(_norm_code(c.code))
        per_query.append({
            "query": q[:60],
            "n_retrieved": len(candidates),
            "top_3": [c.code for c in candidates[:3]],
        })

    retrieved_norm = all_retrieved_codes - {""}
    gold_recalled = gold_norm & retrieved_norm
    recall_at_k = (
        len(gold_recalled) / len(gold_norm) if gold_norm else None
    )
    return {
        "case_id": case_id,
        "gold": gold,
        "n_gold": len(gold_norm),
        "n_queries": len(queries),
        "n_retrieved_total": n_retrieved_total,
        "n_unique_retrieved": len(retrieved_norm),
        "gold_in_top_k": sorted(gold_recalled),
        "recall_at_k": round(recall_at_k, 4) if recall_at_k is not None else None,
        "hit": n_retrieved_total > 0,
        "per_query": per_query,
    }


async def main_async(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="tests/fixtures/icoder_201.json")
    parser.add_argument("--index-dir", default="data/medcoder")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", default="reports/retrieval_analysis.json")
    args = parser.parse_args(argv)

    with open(args.cases, "r", encoding="utf-8") as f:
        cases = json.load(f)
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]
    logger.info("Loaded %d cases from %s", len(cases), args.cases)

    # 1. Health gate
    from app.services.medcoder_index_health import index_health_check
    health = index_health_check(args.index_dir)
    if health["status"] != "ok":
        logger.error(
            "FAISS index DEGRADED — %s. Run build_medcoder_index.py first.",
            health["reason"],
        )
        return 1
    logger.info(
        "FAISS index OK (ntotal=%d, dim=%d)", health["ntotal"], health["dim"]
    )

    # 2. Load retriever
    retriever = await _load_retriever(args.index_dir)
    logger.info("Retriever loaded (BGE-M3 + FAISS)")

    # 3. Per-case analysis
    t0 = time.time()
    per_case: list[dict] = []
    for i, case in enumerate(cases, 1):
        result = await _analyze_one_case(case, retriever, args.top_k)
        per_case.append(result)
        if i % 5 == 0 or i == len(cases):
            r_so_far = [r for r in per_case if r["recall_at_k"] is not None]
            avg_recall = (
                sum(r["recall_at_k"] for r in r_so_far) / len(r_so_far)
                if r_so_far else 0.0
            )
            hit_rate = sum(1 for r in per_case if r["hit"]) / len(per_case)
            print(
                f"  [{i:3d}/{len(cases)}] "
                f"Recall@{args.top_k}={avg_recall:.3f}, "
                f"Hit Rate={hit_rate:.1%}"
            )

    # 4. Aggregate
    n = len(per_case)
    cases_with_gold = [r for r in per_case if r["n_gold"] > 0]
    recall_values = [r["recall_at_k"] for r in cases_with_gold if r["recall_at_k"] is not None]
    summary = {
        "n_cases": n,
        "n_cases_with_gold": len(cases_with_gold),
        "top_k": args.top_k,
        "retrieval_hit_rate": round(
            sum(1 for r in per_case if r["hit"]) / max(n, 1), 4
        ),
        "recall_at_k_mean": round(
            sum(recall_values) / max(len(recall_values), 1), 4
        ),
        "recall_at_k_perfect": round(
            sum(1 for r in recall_values if r >= 1.0) / max(len(recall_values), 1), 4
        ),
        "top_k_coverage_mean": round(
            sum(r["n_retrieved_total"] for r in per_case) / max(n, 1), 2
        ),
        "n_unique_codes_retrieved_mean": round(
            sum(r["n_unique_retrieved"] for r in per_case) / max(n, 1), 2
        ),
        "elapsed_s": round(time.time() - t0, 1),
    }
    out = {"summary": summary, "per_case": per_case}

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    logger.info("Wrote %s", out_path)
    print()
    print("=== Retrieval summary ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(main_async(argv))


if __name__ == "__main__":
    raise SystemExit(main())
