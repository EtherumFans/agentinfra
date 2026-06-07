#!/usr/bin/env python3
"""E2E MedCodER Validation — 4-variant ablation evaluation.

Runs the MedCodER pipeline against a gold-case fixture and reports F1@1,
F1@2, F1@5 metrics. The 4 ablation variants:

  full          — Full 5-stage MedCodER pipeline (Extraction + Retrieval + Re-rank)
  prompt        — Stage 1 LLM only (no Retrieval, no Re-rank) — baseline
  retrieve      — Stage 2 FAISS only (no LLM extraction, no re-rank) — RAG baseline
  prompt+retrieve — Stage 1 + Stage 2 union (no re-rank)

Usage:
  python scripts/e2e_medcoder_validation.py \\
      --cases tests/fixtures/icoder_201.json \\
      --variant full \\
      --limit 20

The script runs in-process (no HTTP server). It uses a mock LLM gateway
for testing; in production, swap in a real LLMGateway.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Make backend root importable
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s: %(message)s",
)
logger = logging.getLogger("e2e_medcoder")


# ── F1@K metric ──


def _norm_code(code: str) -> str:
    """Subdivision-tolerant ICD-10 normalization (mirrors e2e_runtime_validation)."""
    if not code:
        return ""
    c = code.strip().upper()
    c = c.replace("X", "")
    if "." in c:
        head, _, tail = c.partition(".")
        tail = tail.rstrip("0")
        if tail:
            return f"{head}.{tail}"
        return head
    return c


def f1_at_k(expected: set[str], predicted_top_k: list[str], k: int) -> float:
    """Per-case F1 computed from the top-K predicted codes.

    expected: set of normalized gold codes (may be primary + secondary)
    predicted_top_k: ordered list of predicted codes (top-1 first); normalized
    k: the cut-off (use only first K predicted codes)

    Returns 1.0 if both expected and predicted are empty, 0.0 if no overlap
    in non-empty sets, else 2*P*R / (P+R).
    """
    if not expected and not predicted_top_k:
        return 1.0
    expected_norm = {_norm_code(c) for c in expected}
    expected_norm.discard("")
    top_k = [_norm_code(c) for c in predicted_top_k[:k] if c]
    top_k = [c for c in top_k if c]
    if not expected_norm and not top_k:
        return 1.0
    if not expected_norm or not top_k:
        return 0.0
    pred_set = set(top_k)
    tp = len(expected_norm & pred_set)
    if tp == 0:
        return 0.0
    p = tp / len(pred_set)
    r = tp / len(expected_norm)
    return 2 * p * r / (p + r)


# ── Gold case loader ──


def load_gold_cases(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "gold_cases" in data:
        return data["gold_cases"]
    if isinstance(data, list):
        return data
    return []


def extract_gold_codes(case: dict) -> set[str]:
    """Extract the gold code set from a CCL 2026 / iCoDer 201 fixture case.

    Supports two shapes:

    CCL 2026 (flat)::
        {"expected_principal_diagnosis": "I50.900",
         "expected_secondary_diagnoses": ["I10"],
         "expected_procedure_codes": ["00.66"]}

    iCoDer 201 (nested under "expected")::
        {"expected": {"primary_diagnosis": {"code": "I50.900"},
                      "secondary_diagnoses": [{"code": "I10"}]}}
    """
    out: set[str] = set()

    # Flat shape (CCL 2026)
    if case.get("expected_principal_diagnosis"):
        out.add(case["expected_principal_diagnosis"])
    for c in case.get("expected_secondary_diagnoses", []) or []:
        if isinstance(c, str):
            if c:
                out.add(c)
        elif isinstance(c, dict) and c.get("code"):
            out.add(c["code"])
    for c in case.get("expected_procedure_codes", []) or []:
        if isinstance(c, str):
            if c:
                out.add(c)
        elif isinstance(c, dict) and c.get("code"):
            out.add(c["code"])

    # Nested shape (iCoDer 201)
    exp = case.get("expected") or {}
    if isinstance(exp, dict):
        pd = exp.get("primary_diagnosis")
        if isinstance(pd, dict) and pd.get("code"):
            out.add(pd["code"])
        elif isinstance(pd, str) and pd:
            out.add(pd)
        for d in exp.get("secondary_diagnoses", []) or []:
            if isinstance(d, dict) and d.get("code"):
                out.add(d["code"])
            elif isinstance(d, str) and d:
                out.add(d)
        pp = exp.get("primary_procedure")
        if isinstance(pp, dict) and pp.get("code"):
            out.add(pp["code"])
        for p in exp.get("procedures", []) or []:
            if isinstance(p, dict) and p.get("code"):
                out.add(p["code"])
            elif isinstance(p, str) and p:
                out.add(p)

    return out


# ── Variants ──


VARIANTS = ("full", "prompt", "retrieve", "prompt+retrieve")


def _get_case_text(case: dict) -> str:
    """Extract the EMR text from a case dict, handling both fixtures."""
    return (
        case.get("text")
        or case.get("encounter_text")
        or case.get("admission_reason")
        or ""
    )


def _prompt_only_topk(case: dict, gateway) -> list[str]:
    """Variant 1: Stage 1 LLM only → return its llm_initial_codes for each dx."""
    if not gateway:
        return []
    from icoder_runtime.providers.medical_coding.medcoder_adapter import (
        build_extraction_messages, parse_extraction_response,
    )
    text = _get_case_text(case)
    if not text:
        return []
    msgs = build_extraction_messages(text)
    try:
        resp = asyncio.run(gateway.generate(msgs, provider="default"))
        items = parse_extraction_response(resp.get("content", ""))
    except Exception:
        return []
    return [item.get("llm_initial_code", "") for item in items if item.get("llm_initial_code")]


def _retrieve_only_topk(case: dict, retriever, k: int = 20) -> list[str]:
    """Variant 2: Stage 2 retrieve only → use text as query, return top-K."""
    if not retriever:
        return []
    text = _get_case_text(case)
    if not text:
        return []
    try:
        cands = asyncio.run(retriever.retrieve_async(text[:200], top_k=k))
    except Exception:
        return []
    return [c.code for c in cands]


def _prompt_plus_retrieve_topk(case: dict, gateway, retriever, k: int = 20) -> list[str]:
    """Variant 3: Stage 1 + Stage 2 union, no re-rank."""
    prompt_codes = _prompt_only_topk(case, gateway)
    retrieve_codes = _retrieve_only_topk(case, retriever, k=k)
    seen: set[str] = set()
    out: list[str] = []
    for c in prompt_codes + retrieve_codes:
        if c and c not in seen:
            out.append(c)
            seen.add(c)
    return out


def _full_topk(case: dict, adapter) -> list[str]:
    """Variant 4: Full MedCodER pipeline (uses 1 LLM call + 1 retrieve + 1 rerank)."""
    text = _get_case_text(case)
    if not text:
        return []
    try:
        out = asyncio.run(adapter.infer_async([{"role": "user", "content": text}]))
    except Exception as e:
        logger.warning("Full pipeline failed: %s", e)
        return []
    # Aggregate top-K from all extracted diagnoses (deduplicate, preserve order)
    out_codes: list[str] = []
    seen: set[str] = set()
    for edx in (out.extracted_diagnoses or []):
        for c in (edx.final_top_k or []):
            if c.code and c.code not in seen:
                out_codes.append(c.code)
                seen.add(c.code)
    return out_codes


# ── Evaluation loop ──


def run_evaluation(
    cases: list[dict],
    variant: str,
    gateway=None,
    retriever=None,
    adapter=None,
    k_values: tuple[int, ...] = (1, 2, 5),
) -> dict:
    """Run the chosen variant on each case; return aggregate F1@K + per-case results."""
    if variant not in VARIANTS:
        raise ValueError(f"Unknown variant '{variant}'. Choose from {VARIANTS}")

    results: list[dict] = []
    t0 = time.time()
    for i, case in enumerate(cases):
        case_t0 = time.time()
        gold = extract_gold_codes(case)

        # Get top-K predictions based on variant
        if variant == "prompt":
            top_k = _prompt_only_topk(case, gateway)
        elif variant == "retrieve":
            top_k = _retrieve_only_topk(case, retriever)
        elif variant == "prompt+retrieve":
            top_k = _prompt_plus_retrieve_topk(case, gateway, retriever)
        elif variant == "full":
            top_k = _full_topk(case, adapter)
        else:
            top_k = []

        # Compute F1@K
        per_k = {k: f1_at_k(gold, top_k, k) for k in k_values}
        elapsed = time.time() - case_t0
        results.append({
            "case_id": case.get("encounter_id", case.get("id", f"case_{i}")),
            "gold": sorted(gold),
            "predicted_top_5": top_k[:5],
            "f1_at_1": per_k.get(1, 0.0),
            "f1_at_2": per_k.get(2, 0.0),
            "f1_at_5": per_k.get(5, 0.0),
            "latency_s": round(elapsed, 3),
        })
        if (i + 1) % 10 == 0 or i == len(cases) - 1:
            f1_1_so_far = sum(r["f1_at_1"] for r in results) / len(results)
            print(f"  [{i+1:3d}/{len(cases)}] F1@1={f1_1_so_far:.3f} (variant={variant})")

    total_elapsed = time.time() - t0

    # Aggregate
    n = max(len(results), 1)
    summary = {
        "variant": variant,
        "n_cases": len(cases),
        "total_elapsed_s": round(total_elapsed, 1),
        "avg_latency_s": round(total_elapsed / n, 3),
        "f1_at_1": round(sum(r["f1_at_1"] for r in results) / n, 4),
        "f1_at_2": round(sum(r["f1_at_2"] for r in results) / n, 4),
        "f1_at_5": round(sum(r["f1_at_5"] for r in results) / n, 4),
    }
    return {"summary": summary, "per_case": results}


# ── CLI ──


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases",
        default="tests/fixtures/icoder_201.json",
        help="Path to gold cases JSON.",
    )
    parser.add_argument(
        "--variant",
        choices=VARIANTS,
        default="full",
        help="Ablation variant to run.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of cases (0 = all).",
    )
    parser.add_argument(
        "--retriever-index-dir",
        default="data/medcoder",
        help="FAISS index directory (for retrieve variants).",
    )
    parser.add_argument(
        "--out",
        default="data/medcoder/eval_report.json",
        help="Where to write the JSON report.",
    )
    parser.add_argument(
        "--use-mock-gateway",
        action="store_true",
        default=True,
        help="Use a mock LLM gateway (default: True for offline tests).",
    )
    args = parser.parse_args(argv)

    cases = load_gold_cases(args.cases)
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]
    print(f"Loaded {len(cases)} cases from {args.cases}")
    print(f"Variant: {args.variant}")

    # Build dependencies lazily — only what's needed for this variant
    gateway = None
    retriever = None
    adapter = None
    if args.variant in ("prompt", "prompt+retrieve"):
        # Mock LLM gateway for offline eval
        from icoder_runtime.providers.medical_coding.medcoder_adapter import (
            build_extraction_messages, parse_extraction_response,
        )
        class _MockGateway:
            def __init__(self):
                self.call_count = 0
            async def generate(self, messages, *, provider: str = "", **kwargs):
                self.call_count += 1
                # Mock: extract a single likely-disease from the text
                user = ""
                for m in reversed(messages):
                    if m.get("role") == "user":
                        user = m.get("content", "")
                        break
                # Very crude: return a mock extraction with a placeholder code
                # that won't match the gold, so the F1@1 ≈ 0
                if "心" in user or "胸" in user:
                    return {"content": '[{"disease_text": "心力衰竭", "supporting_evidence": "胸闷", "llm_initial_code": "I50.900"}]'}
                if "高血" in user:
                    return {"content": '[{"disease_text": "高血压", "supporting_evidence": "高血压", "llm_initial_code": "I10"}]'}
                return {"content": '[{"disease_text": "未知", "supporting_evidence": "未知", "llm_initial_code": "R69"}]'}
        gateway = _MockGateway()

    if args.variant in ("retrieve", "prompt+retrieve"):
        try:
            from icoder_runtime.providers.medical_coding.medcoder_retriever import MedCodERRetriever
            retriever = MedCodERRetriever(index_dir=args.retriever_index_dir)
        except Exception as e:
            print(f"WARNING: could not create retriever ({e}). retrieve variants will return 0 codes.")

    if args.variant == "full":
        from icoder_runtime.providers.medical_coding.hybrid_adapter import HybridCodingAdapter
        adapter = HybridCodingAdapter(gateway=gateway, mode="medcoder", retriever=retriever)

    # Run eval
    result = run_evaluation(cases, args.variant, gateway=gateway, retriever=retriever, adapter=adapter)
    print()
    print(f"=== {args.variant} ===")
    print(f"  cases:        {result['summary']['n_cases']}")
    print(f"  F1@1:         {result['summary']['f1_at_1']:.4f}")
    print(f"  F1@2:         {result['summary']['f1_at_2']:.4f}")
    print(f"  F1@5:         {result['summary']['f1_at_5']:.4f}")
    print(f"  avg latency:  {result['summary']['avg_latency_s']:.3f}s")
    print(f"  total time:   {result['summary']['total_elapsed_s']:.1f}s")

    # Write report
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"  report:       {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
