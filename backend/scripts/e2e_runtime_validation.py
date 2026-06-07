#!/usr/bin/env python3
"""E2E Runtime Validation — Gold case evaluation via PlatformRuntime + RuleEngine + RepairLoop.

Usage:
  python scripts/e2e_runtime_validation.py [--base-url http://localhost:8003] [--agent-ref icoder/medical-coding-agent@1.0.0]
"""

import json
import sys
import time
import hashlib
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

BASE_URL = "http://localhost:8003"
AGENT_REF = "icoder/medical-coding-agent@1.0.0"


def api(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=90) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw.strip().startswith("{") else {"raw": raw}
    except HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
        except Exception:
            err_body = {"error": str(e)}
        return e.code, err_body
    except URLError as e:
        return 0, {"error": f"Connection: {e}"}


def load_gold_cases() -> list[dict]:
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "gold_cases", "samples.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("gold_cases", [])


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _norm_code(code: str) -> str:
    """Subdivision-tolerant ICD-10 normalization.

    I50.900 → I50.9  (trailing subdivision zeros are stripped)
    I50.x00 → I50    (x placeholder stripped, all subdivision zeros stripped)
    Z45.800x012 → Z45.800012  (x placeholder stripped, digits after preserved)
    C20.x00 → C20    (x + all subdivision zeros stripped)
    Leading/trailing whitespace and case are also normalized.
    The dot separator is preserved when there's a non-empty tail.
    """
    if not code:
        return ""
    c = code.strip().upper()
    # X is a placeholder, never meaningful — strip it everywhere
    c = c.replace("X", "")
    if "." in c:
        head, _, tail = c.partition(".")
        tail = tail.rstrip("0")
        if tail:
            return f"{head}.{tail}"
        return head
    return c


def _compute_case_f1(expected_codes: set[str], predicted_codes: set[str]) -> float:
    """Per-case micro-F1 over ICD-10 diagnosis codes (subdivision-tolerant).

    Normalizes each code via _norm_code before comparison. Counts every code
    as one unit; partial credit for partial overlap.
    """
    if not expected_codes and not predicted_codes:
        return 1.0
    exp_norm = {_norm_code(c) for c in expected_codes}
    act_norm = {_norm_code(c) for c in predicted_codes}
    exp_norm.discard("")
    act_norm.discard("")
    if not exp_norm and not act_norm:
        return 1.0
    tp = len(exp_norm & act_norm)
    fp = len(act_norm - exp_norm)
    fn = len(exp_norm - act_norm)
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    if p + r < 1e-9:
        return 0.0
    return 2 * p * r / (p + r)


def classify_error(expected_code: str, actual_code: str) -> str:
    """Classify coding error type."""
    if not expected_code or not actual_code:
        return "missing_code" if expected_code and not actual_code else "extra_code"
    if expected_code == actual_code:
        return "exact_match"
    # First 3 characters determine the category
    exp_prefix = expected_code[:3] if len(expected_code) >= 3 else expected_code
    act_prefix = actual_code[:3] if len(actual_code) >= 3 else actual_code
    if exp_prefix == act_prefix:
        return "subdivision_error"  # Same category, different sub-code
    # Check if same letter category (e.g., I20 vs I21)
    if expected_code[0] == actual_code[0] and expected_code[0].isalpha():
        return "same_category_error"
    return "cross_category_error"


def run_evaluation() -> dict:
    """Run gold case evaluation through PlatformRuntime."""
    cases = load_gold_cases()
    print(f"Evaluating {len(cases)} gold cases via PlatformRuntime...")
    print(f"  Agent: {AGENT_REF}")
    print(f"  Base URL: {BASE_URL}")

    results = []
    t0 = time.time()

    for i, case in enumerate(cases):
        case_start = time.time()
        case_id = case["id"]
        encounter = case["encounter_text"]
        expected = case.get("expected", {})
        exp_dx = (expected.get("primary_diagnosis") or {}).get("code", "")
        exp_sec = [d.get("code") for d in expected.get("secondary_diagnoses", [])]
        exp_proc = [p.get("code") for p in expected.get("procedures", [])]

        # Step 1: Run agent via PlatformRuntime
        code, data = api("POST", f"/api/runtime/agents/{AGENT_REF}/run", {
            "input": encounter,
        })

        run_id = data.get("run_id", "")
        act_dx = data.get("primary_diagnosis", {}).get("code", "")
        act_sec = []
        act_proc = []
        structured = data.get("structured")
        if structured:
            for d in structured.get("secondary_diagnoses", []):
                if isinstance(d, dict):
                    act_sec.append(d.get("code", ""))
            for p in structured.get("procedures", []):
                if isinstance(p, dict):
                    act_proc.append(p.get("code", ""))

        # Step 2: RuleEngine validation
        rule_issues = []
        rule_fired = []
        manual_review = False
        if structured and run_id:
            val_code, val_data = api("POST", "/api/compliance/rule-engine/validate", {
                "rule_set": "medical_coding",
                "structured_output": structured,
                "context": {"encounter_text": encounter},
            })
            if val_code == 200:
                rule_issues = val_data.get("issues", [])
                rule_fired = val_data.get("rules_fired", [])
                manual_review = val_data.get("manual_review_required", False)

        # Step 3: RepairLoop if rule issues found
        repair_attempted = False
        repair_success = False
        repaired_output = None
        initial_hash = _hash(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str))

        # Build gold set (normalized) for honest repair_success judgment
        gold_norm = {_norm_code(exp_dx)} | {_norm_code(c) for c in exp_sec if c}
        gold_norm.discard("")

        if rule_issues and any(i.get("severity") in ("critical", "high") for i in rule_issues):
            repair_attempted = True
            issue_text = "; ".join(f"{i.get('rule_id', '?')}: {i.get('message', '')}" for i in rule_issues[:3])
            repair_prompt = (
                f"Your previous coding output had the following issues:\n{issue_text}\n\n"
                f"Original encounter: {encounter[:500]}\n\n"
                f"Please review and correct your coding output. Return ONLY valid JSON with MedicalCodingOutputSchema format. "
                f"Do NOT fabricate evidence. If you are unsure, set manual_review_required=true."
            )
            repair_code, repair_data = api("POST", f"/api/runtime/agents/{AGENT_REF}/run", {
                "input": repair_prompt,
            })
            if repair_code == 200:
                repaired_output = repair_data
                # Collect normalized codes from the repaired output
                new_codes = set()
                rdx = repair_data.get("primary_diagnosis", {}).get("code", "")
                if rdx:
                    new_codes.add(_norm_code(rdx))
                rs = repair_data.get("structured") or {}
                for d in rs.get("secondary_diagnoses", []):
                    if isinstance(d, dict) and d.get("code"):
                        new_codes.add(_norm_code(d["code"]))
                # Collect normalized codes from the original output
                old_codes = set()
                if act_dx:
                    old_codes.add(_norm_code(act_dx))
                for d in act_sec:
                    if d:
                        old_codes.add(_norm_code(d))
                # Repair succeeds only if the new code matches gold AND
                # the old code did not already match gold (otherwise it
                # was already correct; no "fix" happened).
                repair_success = bool(new_codes & gold_norm) and not (old_codes & gold_norm)
                if repair_success:
                    data = repair_data  # Use repaired output
                    act_dx = rdx
                    # Refresh act_sec from the repaired structured payload
                    act_sec = []
                    rs2 = repair_data.get("structured") or {}
                    for d in rs2.get("secondary_diagnoses", []):
                        if isinstance(d, dict) and d.get("code"):
                            act_sec.append(d["code"])

        # Error classification
        error_type = classify_error(exp_dx, act_dx)
        is_rule_sensitive = "MC-R-M80-001" in rule_fired

        elapsed = time.time() - case_start

        # Per-case diagnosis micro-F1 (primary + secondary, subdivision-tolerant)
        exp_set = {_norm_code(c) for c in [exp_dx] + exp_sec if c}
        exp_set.discard("")
        act_set = {_norm_code(c) for c in [act_dx] + act_sec if c}
        act_set.discard("")
        case_f1 = _compute_case_f1(exp_set, act_set)

        results.append({
            "case_id": case_id,
            "category": case.get("category", "unknown"),
            "expected_dx": exp_dx,
            "actual_dx": act_dx,
            "expected_secondary_dx": exp_sec,
            "actual_secondary_dx": act_sec,
            "expected_codes_norm": sorted(exp_set),
            "actual_codes_norm": sorted(act_set),
            "per_case_f1": round(case_f1, 4),
            "error_type": error_type,
            "correct": (exp_dx == act_dx),
            "run_id": run_id,
            "latency_ms": int(elapsed * 1000),
            "rule_issues_count": len(rule_issues),
            "rule_fired": rule_fired,
            "manual_review_required": manual_review,
            "rule_sensitive": is_rule_sensitive,
            "repair_attempted": repair_attempted,
            "repair_success": repair_success,
            "initial_output_hash": initial_hash if repair_attempted else "",
            "repaired_output_hash": _hash(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)) if repair_attempted else "",
        })

        status = "OK" if exp_dx == act_dx else ("REPAIR" if repair_success else "FAIL")
        tag = " [RULE]" if is_rule_sensitive else ""
        arrow = "->"
    print(f"  [{i+1:2d}/{len(cases)}] {status} {case_id}: {exp_dx} {arrow} {act_dx} ({error_type}){tag} "
              f"{'repair=' + str(repair_success) if repair_attempted else ''} "
              f"({elapsed:.1f}s)")

    total_elapsed = time.time() - t0

    # ── Compute metrics ──
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    repair_attempted_count = sum(1 for r in results if r["repair_attempted"])
    repair_success_count = sum(1 for r in results if r["repair_success"])

    # Primary diagnosis match
    primary_match_rate = correct / max(total, 1)

    # Per-case diagnosis micro-F1 (primary + secondary, subdivision-tolerant)
    # Each case contributes its per_case_f1 equally; the macro average is
    # the headline number. We also compute a micro-pooled variant for
    # reference, but the per-case number is the one that moves with recall.
    per_case_f1_values = [r["per_case_f1"] for r in results]
    diagnosis_code_f1 = sum(per_case_f1_values) / max(len(per_case_f1_values), 1)

    # Micro-pooled (for reference): pool all TP/FP/FN across cases
    micro_tp = micro_fp = micro_fn = 0
    for r in results:
        exp_set = set(r["expected_codes_norm"])
        act_set = set(r["actual_codes_norm"])
        micro_tp += len(exp_set & act_set)
        micro_fp += len(act_set - exp_set)
        micro_fn += len(exp_set - act_set)
    dx_precision = micro_tp / max(micro_tp + micro_fp, 1)
    dx_recall = micro_tp / max(micro_tp + micro_fn, 1)
    micro_pooled_f1 = 2 * dx_precision * dx_recall / max(dx_precision + dx_recall, 1e-9)

    # Error type distribution
    error_types: dict[str, int] = {}
    for r in results:
        et = r["error_type"]
        error_types[et] = error_types.get(et, 0) + 1

    # Per-category metrics
    categories: dict[str, dict] = {}
    for r in results:
        cat = r["category"]
        if cat not in categories:
            categories[cat] = {"total": 0, "correct": 0, "rule_sensitive": 0}
        categories[cat]["total"] += 1
        if r["correct"]:
            categories[cat]["correct"] += 1
        if r["rule_sensitive"]:
            categories[cat]["rule_sensitive"] += 1

    per_category = {}
    for cat, stats in sorted(categories.items()):
        per_category[cat] = {
            "total": stats["total"],
            "correct": stats["correct"],
            "match_rate": round(stats["correct"] / max(stats["total"], 1), 4),
            "rule_sensitive_count": stats["rule_sensitive"],
        }

    report = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "evaluation": {
            "total_cases": total,
            "correct": correct,
            "primary_diagnosis_match_rate": round(primary_match_rate, 4),
            "diagnosis_code_precision": round(dx_precision, 4),
            "diagnosis_code_recall": round(dx_recall, 4),
            "diagnosis_code_f1": round(diagnosis_code_f1, 4),
            "diagnosis_code_f1_micro_pooled": round(micro_pooled_f1, 4),
            "repair_attempted_count": repair_attempted_count,
            "repair_success_count": repair_success_count,
            "repair_success_rate": round(repair_success_count / max(repair_attempted_count, 1), 4),
            "rule_triggered_cases": sum(1 for r in results if r["rule_issues_count"] > 0),
            "manual_review_triggered": sum(1 for r in results if r["manual_review_required"]),
            "error_distribution": error_types,
            "per_category": per_category,
            "average_latency_ms": int(sum(r["latency_ms"] for r in results) / max(total, 1)),
            "total_elapsed_seconds": round(total_elapsed, 1),
        },
        "per_case": results,
        "config": {
            "base_url": BASE_URL,
            "agent_ref": AGENT_REF,
            "execution_path": "PlatformRuntime → AgentRunner → DeepSeekV4 → RuleEngine → RepairLoop",
            "rule_engine": "compliance_services/medical_coding_rules",
            "repair_max_attempts": 1,
        },
    }

    return report


def main():
    global BASE_URL, AGENT_REF
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--base-url" and i + 1 < len(args):
            BASE_URL = args[i + 1]; i += 2
        elif args[i] == "--agent-ref" and i + 1 < len(args):
            AGENT_REF = args[i + 1]; i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            global OUTPUT_FILE
            OUTPUT_FILE = args[i + 1]; i += 2
        else:
            i += 1

    print(f"iCoDer Medical Coding Agent — Closed-Loop Evaluation")
    print(f"  PlatformRuntime: {BASE_URL}")
    print(f"  Agent: {AGENT_REF}")
    print()

    report = run_evaluation()

    # Print summary
    ev = report["evaluation"]
    print(f"\n{'='*60}")
    print(f"Evaluation Summary")
    print(f"{'='*60}")
    print(f"  Total cases:                    {ev['total_cases']}")
    print(f"  Correct (primary dx match):     {ev['correct']}/{ev['total_cases']} ({ev['primary_diagnosis_match_rate']:.1%})")
    print(f"  Diagnosis Precision:            {ev['diagnosis_code_precision']:.4f}")
    print(f"  Diagnosis Recall:               {ev['diagnosis_code_recall']:.4f}")
    print(f"  Diagnosis F1 (per-case):        {ev['diagnosis_code_f1']:.4f}")
    print(f"  Diagnosis F1 (micro-pooled):    {ev['diagnosis_code_f1_micro_pooled']:.4f}")
    print(f"  Repair attempted:               {ev['repair_attempted_count']}")
    print(f"  Repair succeeded:               {ev['repair_success_count']}")
    print(f"  Rule triggered cases:           {ev['rule_triggered_cases']}")
    print(f"  Manual review triggered:        {ev['manual_review_triggered']}")
    print(f"  Average latency:                {ev['average_latency_ms']}ms")
    print(f"  Total time:                     {ev['total_elapsed_seconds']}s")
    print(f"\n  Error distribution:")
    for et, cnt in sorted(ev["error_distribution"].items()):
        print(f"    {et}: {cnt}")
    print(f"\n  Per category:")
    for cat, stats in ev["per_category"].items():
        print(f"    {cat}: {stats['correct']}/{stats['total']} ({stats['match_rate']:.1%}) rule_sensitive={stats['rule_sensitive_count']}")

    # Save report
    output_path = args[args.index("--output") + 1] if "--output" in args else ".gstack/evaluation_report.json"
    import os
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  Report saved: {output_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
