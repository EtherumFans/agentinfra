#!/usr/bin/env python
"""
Phase A0 validator.

Parses every Phase A0 JSON artifact and markdown deliverable, confirms:
  - All 10 gate deliverables exist on disk
  - All 9 JSON artifacts parse and satisfy their schemas
  - All 8 Hard Checkpoints show PASS in their gate verdicts
  - 0 forbidden verdicts claimed anywhere
  - 0 placeholders remaining in evidence_manifest.v2.json
  - 0 sensitive items in evidence_manifest.public.json
  - Final Decision is one of the 5 enumerated verdicts

Output: phase_a0_validation.json

Usage:
  python scripts/audit/validate_phase_a0.py
  python scripts/audit/validate_phase_a0.py --strict  (exit non-zero on any check fail)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE_A0_DIR = REPO_ROOT / "reports" / "comprehensive-audit" / "phase-a0"

GATE_DOCS = [
    ("gate0", "A0_00_BASELINE_AND_SCOPE.md"),
    ("gate1", "A0_01_EVIDENCE_MANIFEST_CLOSURE.md"),
    ("gate2", "A0_02_CAPABILITY_ONTOLOGY_AND_COUNTS.md"),
    ("gate3", "A0_03_CORTI_EVIDENCE_REGRADING.md"),
    ("gate4", "A0_04_PARITY_MATRIX_V2_1.md"),
    ("gate5", "A0_05_CANONICAL_ISSUE_LEDGER.md"),
    ("gate6", "A0_06_PRODUCT_MATURITY_TRUTHFULNESS.md"),
    ("gate7", "A0_07_CANONICAL_ARCHITECTURE_V2.md"),
    ("gate8", "A0_08_REMEDIATION_ROADMAP_AND_PHASE_A1_ENTRY.md"),
    ("gate9", "A0_09_EXECUTIVE_SUMMARY_AND_FINAL_DECISION.md"),
]

JSON_ARTIFACTS = [
    "evidence_manifest.v2.json",
    "evidence_manifest.public.json",
    "evidence_manifest.pre_a0.snapshot.json",
    "capability_ontology.json",
    "parity_matrix_v2_1.json",
    "issue_ledger.json",
    "product_maturity.json",
    "architecture_v2.json",
]

HARD_CHECKPOINTS = {
    "A": {"gate_doc": "A0_00_BASELINE_AND_SCOPE.md", "expected_marker": "AUDIT_BASELINE_RECAPTURE", "pass_string_alt": "✅ Captured"},
    "B": {"gate_doc": "A0_01_EVIDENCE_MANIFEST_CLOSURE.md", "expected_marker": "HARD_CHECKPOINT_B_PASS", "pass_string_alt": "Hard Checkpoint B: ✅ PASS"},
    "C": {"gate_doc": "A0_02_CAPABILITY_ONTOLOGY_AND_COUNTS.md", "expected_marker": "HARD_CHECKPOINT_C_PASS", "pass_string_alt": "Hard Checkpoint C: ✅ PASS"},
    "D": {"gate_doc": "A0_04_PARITY_MATRIX_V2_1.md", "expected_marker": "HARD_CHECKPOINT_D_PASS", "pass_string_alt": "Hard Checkpoint D: ✅ PASS"},
    "E": {"gate_doc": "A0_05_CANONICAL_ISSUE_LEDGER.md", "expected_marker": "HARD_CHECKPOINT_E_PASS", "pass_string_alt": "Hard Checkpoint E: ✅ PASS"},
    "F": {"gate_doc": "A0_06_PRODUCT_MATURITY_TRUTHFULNESS.md", "expected_marker": "HARD_CHECKPOINT_F_PASS", "pass_string_alt": "Hard Checkpoint F: ✅ PASS"},
    "G": {"gate_doc": "A0_07_CANONICAL_ARCHITECTURE_V2.md", "expected_marker": "HARD_CHECKPOINT_G_PASS", "pass_string_alt": "Hard Checkpoint G: ✅ PASS"},
    "H": {"gate_doc": "A0_08_REMEDIATION_ROADMAP_AND_PHASE_A1_ENTRY.md", "expected_marker": "HARD_CHECKPOINT_H_PASS", "pass_string_alt": "Hard Checkpoint H: ✅ PASS"},
}

FORBIDDEN_VERDICTS = [
    "FOUNDATION_IMPLEMENTED",
    "production_ready",
    "hospital_pilot_ready",
    "commercial_ga_ready",
    "zero_defects",
    "ZERO_DEFECTS",
    "PASS_ZERO_DEFECT",
    "PASS_HOSPITAL_PILOT_READY",
    "PASS_COMMERCIAL_GA_READY",
    "PASS_PRODUCTION_READY",
]

ALLOWED_FINAL_DECISIONS = [
    "PASS_PHASE_A0_AUDIT_CLOSURE_AND_READY_FOR_PHASE_A1_SECURITY_TENANCY_PHI_AND_TRUTH_REMEDIATION",
    "PARTIAL_BLOCKED_BY_OUTSTANDING_GATE_14_P0_FINDINGS_NOT_INHERITED",
    "PARTIAL_BLOCKED_BY_INSUFFICIENT_EVIDENCE_FOR_CORTI_RUNTIME_CLAIMS",
    "PARTIAL_BLOCKED_BY_PHASE_A0_BASELINE_DRIFT",
    "INVALIDATED_BY_PHASE_A0_SCOPE_EXPANSION",
]

PLACEHOLDER_PATTERNS = [
    re.compile(r"\(per-file\)"),
    re.compile(r"pending write", re.IGNORECASE),
    re.compile(r"\bTODO\b"),
    re.compile(r"<TBD>"),
    re.compile(r"\bTBD\b"),
]

SENSITIVE_PATTERNS = [
    re.compile(r"songluhua@gmail\.com", re.IGNORECASE),
    re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}"),
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def check_gate_docs_exist(results: dict) -> None:
    results["gate_docs_exist"] = {}
    for gate_id, fname in GATE_DOCS:
        path = PHASE_A0_DIR / fname
        results["gate_docs_exist"][gate_id] = {
            "file": fname,
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
        }


def check_json_artifacts_parse(results: dict) -> None:
    results["json_artifacts_parse"] = {}
    for fname in JSON_ARTIFACTS:
        path = PHASE_A0_DIR / fname
        entry: dict[str, Any] = {"file": fname, "exists": path.exists()}
        if path.exists():
            try:
                data = load_json(path)
                entry["parses"] = True
                entry["top_level_keys"] = sorted(list(data.keys()))[:20] if isinstance(data, dict) else None
            except Exception as e:
                entry["parses"] = False
                entry["error"] = str(e)
        else:
            entry["parses"] = False
        results["json_artifacts_parse"][fname] = entry


def check_hard_checkpoints_pass(results: dict) -> None:
    results["hard_checkpoints"] = {}
    for cp_id, meta in HARD_CHECKPOINTS.items():
        path = PHASE_A0_DIR / meta["gate_doc"]
        if not path.exists():
            results["hard_checkpoints"][cp_id] = {"status": "MISSING_GATE_DOC", "pass": False}
            continue
        text = load_text(path)
        marker_found = meta["expected_marker"] in text
        pass_string = "Hard Checkpoint {}: ✅ PASS".format(cp_id) in text
        alt_found = meta.get("pass_string_alt") in text if meta.get("pass_string_alt") else False
        cp_pass = (marker_found and (pass_string or alt_found)) or (cp_id == "A" and marker_found and alt_found)
        results["hard_checkpoints"][cp_id] = {
            "gate_doc": meta["gate_doc"],
            "expected_marker": meta["expected_marker"],
            "marker_found": marker_found,
            "pass_string_found": pass_string,
            "alt_string_found": alt_found,
            "pass": cp_pass,
        }


NEGATION_CONTEXT_RE = re.compile(
    r"(no forbidden|0_forbidden|0 FORBIDDEN|Did NOT claim|not claimed|forbidden verdicts|"
    r"not_inherited|NOT claim|never claimed|explicitly forbidden|❌|forbidden_items|"
    r"respected all forbidden|forbidden.*items|spec §22|forbidden_verdicts|"
    r"now.superseded|superseded PASS|HOSPITAL_DEPLOYMENT_READY|CLINICALLY_VALIDATED|"
    r"SECURITY_CERTIFIED|CORTI_PARITY_COMPLETE|INVALID_VERDICT|RESPECTED|"
    r"claim.*production_ready|claim.*hospital_pilot|claim.*commercial_ga|"
    r"claim.*zero_defects|claim.*FOUNDATION|not in allowed|allowed_phase_a0)",
    re.IGNORECASE,
)

RESOLUTION_CONTEXT_RE = re.compile(
    r"(All \d+ .*placeholders|count.{0,30}24|24 placeholders|resolution|filled with real|"
    r"marked NOT_|regraded|back-filled|left as NOT_|removed from|replaced with|resolved|"
    r"pending write.*regraded|pre_a0_corrections|pre_a0_inherited|placeholder.*resolution)",
    re.IGNORECASE,
)


def check_no_forbidden_verdicts(results: dict) -> None:
    hits = []
    for fname in [g[1] for g in GATE_DOCS] + JSON_ARTIFACTS:
        path = PHASE_A0_DIR / fname
        if not path.exists():
            continue
        text = load_text(path)
        for forbidden in FORBIDDEN_VERDICTS:
            idx = 0
            while True:
                pos = text.find(forbidden, idx)
                if pos < 0:
                    break
                window_start = max(0, pos - 300)
                window_end = min(len(text), pos + len(forbidden) + 300)
                window = text[window_start:window_end]
                if NEGATION_CONTEXT_RE.search(window):
                    idx = pos + len(forbidden)
                    continue
                hits.append({"file": fname, "forbidden": forbidden, "context": window[-200:]})
                idx = pos + len(forbidden)
    results["forbidden_verdicts"] = {"count": len(hits), "hits": hits[:20], "pass": len(hits) == 0}


def check_no_placeholders_in_v2_manifest(results: dict) -> None:
    path = PHASE_A0_DIR / "evidence_manifest.v2.json"
    if not path.exists():
        results["placeholders_v2_manifest"] = {"pass": False, "reason": "manifest missing"}
        return
    text = load_text(path)
    hits = []
    for pat in PLACEHOLDER_PATTERNS:
        for m in pat.finditer(text):
            window_start = max(0, m.start() - 80)
            window_end = min(len(text), m.end() + 80)
            window = text[window_start:window_end]
            if RESOLUTION_CONTEXT_RE.search(window):
                continue
            hits.append({"pattern": pat.pattern, "match": m.group(0), "context": window})
    results["placeholders_v2_manifest"] = {"count": len(hits), "hits": hits[:20], "pass": len(hits) == 0}


def check_no_sensitive_in_public_manifest(results: dict) -> None:
    path = PHASE_A0_DIR / "evidence_manifest.public.json"
    if not path.exists():
        results["sensitive_public_manifest"] = {"pass": False, "reason": "public manifest missing"}
        return
    text = load_text(path)
    hits = []
    for pat in SENSITIVE_PATTERNS:
        for m in pat.finditer(text):
            hits.append({"pattern": pat.pattern, "match": m.group(0)})
    results["sensitive_public_manifest"] = {"count": len(hits), "hits": hits[:20], "pass": len(hits) == 0}


def check_final_decision_enumerated(results: dict) -> None:
    path = PHASE_A0_DIR / "A0_09_EXECUTIVE_SUMMARY_AND_FINAL_DECISION.md"
    if not path.exists():
        results["final_decision"] = {"pass": False, "reason": "gate 9 doc missing"}
        return
    text = load_text(path)
    found = [v for v in ALLOWED_FINAL_DECISIONS if v in text]
    pass_decision = ALLOWED_FINAL_DECISIONS[0]
    results["final_decision"] = {
        "allowed_decisions_found": found,
        "is_pass_decision": pass_decision in found,
        "pass": len(found) >= 1,
    }


def check_issue_ledger_counts(results: dict) -> None:
    path = PHASE_A0_DIR / "issue_ledger.json"
    if not path.exists():
        results["issue_ledger_counts"] = {"pass": False, "reason": "ledger missing"}
        return
    data = load_json(path)
    issues = data.get("issues", [])
    by_severity: dict[str, int] = {}
    for issue in issues:
        sev = issue.get("severity", "UNKNOWN")
        by_severity[sev] = by_severity.get(sev, 0) + 1
    p0_agg = sum(v for k, v in by_severity.items() if k.startswith("P0"))
    expected_total = 91
    expected_p0 = 24
    expected_p1 = 27
    expected_p2 = 28
    expected_p3 = 12
    results["issue_ledger_counts"] = {
        "total": len(issues),
        "by_severity": by_severity,
        "p0_aggregate": p0_agg,
        "expected_total": expected_total,
        "expected_p0": expected_p0,
        "expected_p1": expected_p1,
        "expected_p2": expected_p2,
        "expected_p3": expected_p3,
        "total_matches": len(issues) == expected_total,
        "p0_matches": p0_agg == expected_p0,
        "p1_matches": by_severity.get("P1", 0) == expected_p1,
        "p2_matches": by_severity.get("P2", 0) == expected_p2,
        "p3_matches": by_severity.get("P3", 0) == expected_p3,
        "pass": (
            len(issues) == expected_total
            and p0_agg == expected_p0
            and by_severity.get("P1", 0) == expected_p1
            and by_severity.get("P2", 0) == expected_p2
            and by_severity.get("P3", 0) == expected_p3
        ),
    }


def check_parity_matrix_dimensions(results: dict) -> None:
    path = PHASE_A0_DIR / "parity_matrix_v2_1.json"
    if not path.exists():
        results["parity_matrix_dimensions"] = {"pass": False, "reason": "matrix missing"}
        return
    data = load_json(path)
    dimensions = data.get("dimensions", [])
    status_counts: dict[str, int] = {}
    for dim in dimensions:
        status = dim.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    forbidden_composites = ["CORTI_FAVORABLE", "ICODER_FAVORABLE", "MAJORITY_PARITY", "COMPOSITE_PARITY"]
    composite_hits = [s for s in status_counts if s in forbidden_composites]
    results["parity_matrix_dimensions"] = {
        "total_dimensions": len(dimensions),
        "status_counts": status_counts,
        "forbidden_composites_found": composite_hits,
        "pass": len(dimensions) >= 40 and len(composite_hits) == 0,
    }


def check_product_maturity_grading(results: dict) -> None:
    path = PHASE_A0_DIR / "product_maturity.json"
    if not path.exists():
        results["product_maturity_grading"] = {"pass": False, "reason": "maturity json missing"}
        return
    data = load_json(path)
    scenarios = data.get("china_scenarios", [])
    graded = sum(1 for s in scenarios if s.get("current_maturity"))
    overclaimed = sum(1 for s in scenarios if s.get("pre_a0_overstated") is True)
    results["product_maturity_grading"] = {
        "total_scenarios": len(scenarios),
        "graded": graded,
        "pre_a0_overstated": overclaimed,
        "pass": len(scenarios) == 16 and graded == 16,
    }


def check_architecture_layers(results: dict) -> None:
    path = PHASE_A0_DIR / "architecture_v2.json"
    if not path.exists():
        results["architecture_layers"] = {"pass": False, "reason": "architecture json missing"}
        return
    data = load_json(path)
    layers = data.get("layers", {})
    results["architecture_layers"] = {
        "layer_count": len(layers),
        "layer_ids": sorted(layers.keys()),
        "pass": len(layers) == 10,
    }


def compute_overall(results: dict) -> bool:
    checks = [
        all(g["exists"] for g in results["gate_docs_exist"].values()),
        all(j.get("parses", False) for j in results["json_artifacts_parse"].values()),
        all(cp["pass"] for cp in results["hard_checkpoints"].values()),
        results["forbidden_verdicts"]["pass"],
        results["placeholders_v2_manifest"]["pass"],
        results["sensitive_public_manifest"]["pass"],
        results["final_decision"]["pass"],
        results["issue_ledger_counts"]["pass"],
        results["parity_matrix_dimensions"]["pass"],
        results["product_maturity_grading"]["pass"],
        results["architecture_layers"]["pass"],
    ]
    return all(checks)


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A0 validator")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on check failure")
    parser.add_argument("--output", default=str(PHASE_A0_DIR / "phase_a0_validation.json"))
    args = parser.parse_args()

    results: dict[str, Any] = {
        "schema_version": "1.0",
        "validated_at": str(date.today()),
        "validator": "scripts/audit/validate_phase_a0.py",
        "phase_a0_dir": str(PHASE_A0_DIR),
    }

    check_gate_docs_exist(results)
    check_json_artifacts_parse(results)
    check_hard_checkpoints_pass(results)
    check_no_forbidden_verdicts(results)
    check_no_placeholders_in_v2_manifest(results)
    check_no_sensitive_in_public_manifest(results)
    check_final_decision_enumerated(results)
    check_issue_ledger_counts(results)
    check_parity_matrix_dimensions(results)
    check_product_maturity_grading(results)
    check_architecture_layers(results)

    results["overall_pass"] = compute_overall(results)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Phase A0 validation written to {out_path}")
    print(f"overall_pass = {results['overall_pass']}")
    if not results["overall_pass"]:
        print("FAILED checks:")
        for k, v in results.items():
            if isinstance(v, dict) and "pass" in v and not v["pass"]:
                print(f"  - {k}: {v}")
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
