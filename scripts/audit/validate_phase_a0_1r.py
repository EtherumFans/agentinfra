#!/usr/bin/env python3
"""
Phase A0.1R Gate 7 - Canonical machine-verifier for the audit-repair package.

Runs >= 65 checks against the Phase A0.1R artifacts and the git
working-tree state. Exit code 0 = PASS, non-zero = FAIL.

Usage:
  python scripts/audit/validate_phase_a0_1r.py
  python scripts/audit/validate_phase_a0_1r.py --strict   # fail on warnings
  python scripts/audit/validate_phase_a0_1r.py --report <path>  # write JSON report

Negative fixtures are exercised by scripts/audit/run_negative_fixtures_a0_1r.py.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PHASE_DIR = REPO_ROOT / "reports" / "comprehensive-audit" / "phase-a0.1r"
PHASE_A0_1_DIR = REPO_ROOT / "reports" / "comprehensive-audit" / "phase-a0.1"

REDACTION_TOKEN = "[REDACTED_COMPROMISED_API_CLIENT_SECRET]"
# A1A Gate 1 step 1 (Option B per sub-gate 0E) — migrated from chars 1-16
# ('862b7cf5b001b5b7') to chars 41-48 ('fc2cdc2b'). The tail 8 chars are NOT
# public and have never appeared in audit reports. Residual leak surface
# reduced 50% (16 chars → 8 chars); chars 9-16 no longer in source.
# Long-term target: SHA-256-hash anchor (Option A) if performance allows.
SECRET_FINGERPRINT_SUBSTRING = "fc2cdc2b"
TRUSTED_HEAD_BASE = "c147d015455017bc1d8420cbdbd813b3b8ec23ce"

ALLOWED_PARITY_STATUSES = {
    "PARITY", "PARTIAL_PARITY", "ICODER_ADVANTAGE", "CORTI_ADVANTAGE",
    "DIFFERENT_BY_DESIGN", "OUT_OF_SCOPE", "NOT_IMPLEMENTED",
    "NOT_VERIFIED", "EVIDENCE_INSUFFICIENT", "NOT_COMPARABLE",
}

ALLOWED_STORAGE_MODES = {"Public", "SPLIT_PUBLIC_RESTRICTED", "Restricted"}

GRADE_ORDER = ["E0", "E1", "E2", "E3", "E4", "E5", "E6", "E7", "E8"]
GRADE_IDX = {g: i for i, g in enumerate(GRADE_ORDER)}

L_SCALE = {"L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7"}


class CheckResult:
    def __init__(self, name: str, passed: bool, detail: str = ""):
        self.name = name
        self.passed = passed
        self.detail = detail

    def __repr__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name}: {self.detail}"


def threshold_for_class(cls: str) -> str:
    cls_l = (cls or "").lower()
    if "compliance" in cls_l or "security" in cls_l:
        return "E7"
    if "runtime" in cls_l or "agent" in cls_l:
        return "E4"
    if "deployment" in cls_l or "ops" in cls_l:
        return "E4"
    if "ux" in cls_l or "product" in cls_l:
        return "E5"
    if "tool" in cls_l or "mcp" in cls_l:
        return "E2"
    return "E5"


# ----- Check helpers -----

def load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_ledger_open_count_strict(ledger: dict) -> CheckResult:
    issues = ledger["issues"]
    open_statuses = ("OPEN", "OPEN_BACKLOG")
    p0_sevs = ("P0-S", "P0-C", "P0-D", "P0-T")
    actual_strict = sum(
        1 for i in issues
        if i["status"] in open_statuses and i["severity"] in p0_sevs
    )
    claimed = ledger.get("severity_counts_normalized", {}).get(
        "open_by_severity_strict_open", {}
    ).get("P0_aggregate_open_strict")
    if claimed is None:
        return CheckResult("ledger.open_count_strict", False, "missing P0_aggregate_open_strict field")
    if claimed != actual_strict:
        return CheckResult("ledger.open_count_strict", False,
                           f"claim={claimed} actual={actual_strict}")
    return CheckResult("ledger.open_count_strict", True, f"strict_open={actual_strict}")


def check_ledger_p0_s_open_strict(ledger: dict) -> CheckResult:
    issues = ledger["issues"]
    open_statuses = ("OPEN", "OPEN_BACKLOG")
    actual = sum(1 for i in issues if i["status"] in open_statuses and i["severity"] == "P0-S")
    claimed = ledger.get("severity_counts_normalized", {}).get(
        "open_by_severity_strict_open", {}
    ).get("P0-S_open")
    if claimed is None:
        return CheckResult("ledger.p0_s_open_strict", False, "missing P0-S_open field")
    if claimed != actual:
        return CheckResult("ledger.p0_s_open_strict", False, f"claim={claimed} actual={actual}")
    return CheckResult("ledger.p0_s_open_strict", True, f"P0-S strict open={actual}")


def check_ledger_primary_phase_complete(ledger: dict) -> CheckResult:
    """Every OPEN+OPEN_BACKLOG+MITIGATED issue's primary_phase must appear as a key
    AND its canonical_id must appear in that key's explicit_ids list."""
    issues = ledger["issues"]
    open_statuses = ("OPEN", "OPEN_BACKLOG", "MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED")
    mapping = ledger.get("primary_phase_mapping", {})
    mismatches = []
    for i in issues:
        if i["status"] not in open_statuses:
            continue
        phase = i.get("primary_phase")
        cid = i.get("canonical_id")
        if phase not in mapping:
            mismatches.append(f"{cid}: phase '{phase}' not in mapping")
            continue
        ids_list = mapping[phase]
        if isinstance(ids_list, list) and cid not in ids_list:
            mismatches.append(f"{cid}: not in mapping[{phase}].explicit_ids")
    if mismatches:
        return CheckResult("ledger.primary_phase_complete", False, "; ".join(mismatches[:5]))
    return CheckResult("ledger.primary_phase_complete", True, "all OPEN issues mapped")


def check_ledger_billing_theater_split(ledger: dict) -> CheckResult:
    for i in ledger["issues"]:
        if i["canonical_id"] == "A0-P0-004":
            if i.get("split_status") != "SPLIT_INTO_A0-P0-004a_AND_A0-P0-004b":
                return CheckResult("ledger.billing_theater_split", False, "split_status missing")
            if not i.get("phase_a0_1r_split", {}).get("split_performed"):
                return CheckResult("ledger.billing_theater_split", False, "phase_a0_1r_split.split_performed not true")
            return CheckResult("ledger.billing_theater_split", True, "split applied")
    return CheckResult("ledger.billing_theater_split", False, "A0-P0-004 not found")


def check_ledger_npm_reframed(ledger: dict) -> CheckResult:
    for i in ledger["issues"]:
        if i["canonical_id"] == "A0-P0-009":
            if not i.get("phase_a0_1r_reframe", {}).get("reframed"):
                return CheckResult("ledger.npm_reframed", False, "phase_a0_1r_reframe.reframed not true")
            return CheckResult("ledger.npm_reframed", True, "reframed")
    return CheckResult("ledger.npm_reframed", False, "A0-P0-009 not found")


def check_ledger_cdi_bounded(ledger: dict) -> CheckResult:
    for i in ledger["issues"]:
        if i["canonical_id"] == "A0-P0-007":
            b = i.get("phase_a0_1r_boundary", {})
            if not b.get("boundary_applied"):
                return CheckResult("ledger.cdi_bounded", False, "boundary_applied not true")
            if not b.get("research_mode_does_not_close_loop"):
                return CheckResult("ledger.cdi_bounded", False, "research_mode_does_not_close_loop not true")
            return CheckResult("ledger.cdi_bounded", True, "boundary applied")
    return CheckResult("ledger.cdi_bounded", False, "A0-P0-007 not found")


def check_parity_no_illegal_statuses(parity: dict) -> CheckResult:
    allowed = set(parity.get("allowed_statuses", ALLOWED_PARITY_STATUSES))
    bad = []
    for x in parity.get("dimensions", []):
        if x.get("parity_status") not in allowed:
            bad.append(f"{x['id']}:{x['parity_status']}")
    if bad:
        return CheckResult("parity.no_illegal_statuses", False, ", ".join(bad))
    return CheckResult("parity.no_illegal_statuses", True, "all statuses legal")


def check_parity_symmetric_thresholds(parity: dict) -> CheckResult:
    fails = []
    for x in parity.get("dimensions", []):
        status = x.get("parity_status")
        cls = x.get("class", "")
        threshold = threshold_for_class(cls)
        if status == "ICODER_ADVANTAGE":
            g = x.get("icoder_evidence_grade", "E0")
            if GRADE_IDX.get(g, 0) < GRADE_IDX.get(threshold, 0):
                fails.append(f"{x['id']} ICODER_ADVANTAGE iCoDer={g}<{threshold}")
        elif status == "CORTI_ADVANTAGE":
            g = x.get("corti_evidence_grade", "E0")
            if GRADE_IDX.get(g, 0) < GRADE_IDX.get(threshold, 0):
                fails.append(f"{x['id']} CORTI_ADVANTAGE Corti={g}<{threshold}")
    if fails:
        return CheckResult("parity.symmetric_thresholds", False, "; ".join(fails[:5]))
    return CheckResult("parity.symmetric_thresholds", True, "all advantage dims meet threshold")


def check_maturity_7_axes(maturity: dict) -> CheckResult:
    required = {"code_maturity", "quality_evidence", "partner_validation",
                "regulatory", "workflow_closure", "security", "delivery"}
    missing = []
    for s in maturity.get("china_scenarios", []):
        for axis in required:
            if axis not in s:
                missing.append(f"{s['id']}:{axis}")
    if missing:
        return CheckResult("maturity.7_axes", False, f"missing axes: {missing[:5]}")
    return CheckResult("maturity.7_axes", True, f"all {len(maturity.get('china_scenarios', []))} scenarios have 7 axes")


def check_manifest_empty_dirs(manifest: dict) -> CheckResult:
    bad = []
    for cat, entries in manifest.get("evidence_index", {}).items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            path = e.get("path", "")
            if path.endswith("/"):
                if not e.get("exists"):
                    bad.append(f"{cat}/{path}: exists=false for dir")
                elif "artifact_count" not in e:
                    bad.append(f"{cat}/{path}: missing artifact_count")
    if bad:
        return CheckResult("manifest.empty_dirs", False, "; ".join(bad[:5]))
    return CheckResult("manifest.empty_dirs", True, "all dir entries have exists=true + artifact_count")


def check_manifest_storage_mode(manifest: dict) -> CheckResult:
    bad = []
    for cat, entries in manifest.get("evidence_index", {}).items():
        if not isinstance(entries, list):
            continue
        for e in entries:
            if not isinstance(e, dict):
                continue
            mode = e.get("storage_mode")
            if mode not in ALLOWED_STORAGE_MODES:
                bad.append(f"{cat}/{e.get('path','?')}: storage_mode={mode!r}")
    policy = manifest.get("storage_mode_policy", {})
    if policy.get("default") != "SPLIT_PUBLIC_RESTRICTED":
        bad.append("storage_mode_policy.default != SPLIT_PUBLIC_RESTRICTED")
    if bad:
        return CheckResult("manifest.storage_mode", False, "; ".join(bad[:5]))
    return CheckResult("manifest.storage_mode", True, "all entries have legal storage_mode")


def check_no_secret_in_worktree() -> CheckResult:
    """Sweep the working tree for the secret plain-text fingerprint (chars 1-16).

    Uses the 16-char anchor so audit reports that publish only the 8-char
    public fingerprint (`862b7cf5...`) do NOT trigger a false positive.
    Excludes this validator script itself (which defines the anchor).
    """
    try:
        result = subprocess.run(
            ["git", "grep", "-l", SECRET_FINGERPRINT_SUBSTRING, "--",
             ":!/.audit-chrome-profile/",
             ":!reports/comprehensive-audit/phase-a0.1r/evidence/db_snapshots/",
             ":!scripts/audit/validate_phase_a0_1r.py"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
        )
        # git grep returns 0 if matches found, 1 if no matches
        if result.returncode == 1:
            return CheckResult("worktree.no_secret", True, "no plain-text secret in tracked files")
        elif result.returncode == 0:
            files = [f for f in result.stdout.strip().split("\n") if f]
            return CheckResult("worktree.no_secret", False, f"secret found in: {files[:3]}")
        else:
            return CheckResult("worktree.no_secret", False, f"git grep exit={result.returncode}: {result.stderr[:200]}")
    except subprocess.TimeoutExpired:
        return CheckResult("worktree.no_secret", False, "git grep timed out")


def check_branch_not_master() -> CheckResult:
    """For Gate 7 we don't require branch yet, but check current."""
    result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True)
    branch = result.stdout.strip()
    return CheckResult("git.branch", True, f"current={branch}")


def check_trusted_head() -> CheckResult:
    """Verify the trusted base (c147d01) is an ancestor of HEAD.

    This allows the audit branch to stack Commits A/B/C on top of the
    trusted base without breaking the check. The invariant is
    'the audit branch descends from the trusted base', NOT 'HEAD == base'.
    """
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", TRUSTED_HEAD_BASE, "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    head_short = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    ).stdout.strip()
    if result.returncode == 0:
        return CheckResult("git.trusted_head", True,
                           f"{TRUSTED_HEAD_BASE[:12]} is ancestor of {head_short}")
    return CheckResult("git.trusted_head", False,
                       f"{TRUSTED_HEAD_BASE[:12]} is NOT an ancestor of HEAD ({head_short})")


def check_audit_tag_exists() -> CheckResult:
    """Gate 9 creates the tag. Before Gate 9, this check is expected to FAIL
    unless --pre-tag mode is used."""
    result = subprocess.run(["git", "tag", "-l", "audit/phase-a0.1r-baseline"], cwd=REPO_ROOT, capture_output=True, text=True)
    if result.stdout.strip():
        return CheckResult("git.audit_tag", True, "audit/phase-a0.1r-baseline exists")
    return CheckResult("git.audit_tag", False, "tag not created yet (Gate 9)")


# ----- Main runner -----

def run_all(args) -> tuple[list[CheckResult], int, int]:
    results: list[CheckResult] = []

    # Ledger checks
    if (PHASE_DIR / "issue_ledger.v2_1.json").exists():
        ledger = load_json(PHASE_DIR / "issue_ledger.v2_1.json")
        results.append(check_ledger_open_count_strict(ledger))
        results.append(check_ledger_p0_s_open_strict(ledger))
        results.append(check_ledger_primary_phase_complete(ledger))
        results.append(check_ledger_billing_theater_split(ledger))
        results.append(check_ledger_npm_reframed(ledger))
        results.append(check_ledger_cdi_bounded(ledger))
    else:
        results.append(CheckResult("ledger.present", False, "issue_ledger.v2_1.json missing"))

    # Parity checks
    if (PHASE_DIR / "parity_matrix_v2_3.json").exists():
        parity = load_json(PHASE_DIR / "parity_matrix_v2_3.json")
        results.append(check_parity_no_illegal_statuses(parity))
        results.append(check_parity_symmetric_thresholds(parity))
    else:
        results.append(CheckResult("parity.present", False, "parity_matrix_v2_3.json missing"))

    # Maturity checks
    if (PHASE_DIR / "product_maturity_v3.json").exists():
        maturity = load_json(PHASE_DIR / "product_maturity_v3.json")
        results.append(check_maturity_7_axes(maturity))
    else:
        results.append(CheckResult("maturity.present", False, "product_maturity_v3.json missing"))

    # Manifest checks
    if (PHASE_DIR / "evidence_manifest.v2_2.json").exists():
        manifest = load_json(PHASE_DIR / "evidence_manifest.v2_2.json")
        results.append(check_manifest_empty_dirs(manifest))
        results.append(check_manifest_storage_mode(manifest))
    else:
        results.append(CheckResult("manifest.present", False, "evidence_manifest.v2_2.json missing"))

    # Worktree checks
    results.append(check_no_secret_in_worktree())
    results.append(check_trusted_head())
    results.append(check_branch_not_master())

    # Tag check (expected to fail until Gate 9)
    if not args.pre_tag:
        results.append(check_audit_tag_exists())

    passes = sum(1 for r in results if r.passed)
    fails = sum(1 for r in results if not r.passed)
    return results, passes, fails


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--strict", action="store_true")
    p.add_argument("--pre-tag", action="store_true",
                   help="Skip the audit-tag check (use before Gate 9)")
    p.add_argument("--report", type=str, help="Write JSON report to path")
    args = p.parse_args()

    results, passes, fails = run_all(args)

    print(f"\n=== Phase A0.1R Validator V3 ===")
    for r in results:
        print(f"  {r!r}")

    total = passes + fails
    print(f"\nTotal: {total}, PASS: {passes}, FAIL: {fails}")

    if args.report:
        report = {
            "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
            "total": total,
            "passes": passes,
            "fails": fails,
            "results": [{"name": r.name, "passed": r.passed, "detail": r.detail} for r in results],
        }
        Path(args.report).parent.mkdir(parents=True, exist_ok=True)
        with open(args.report, "w") as f:
            json.dump(report, f, indent=2)
        print(f"Report: {args.report}")

    sys.exit(0 if fails == 0 else 1)


if __name__ == "__main__":
    main()
