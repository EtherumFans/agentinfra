#!/usr/bin/env python3
"""
Phase A0.1R Gate 7 - Negative fixtures.

For each defect class, mutate the corrected artifact in memory,
run the relevant validator check, and verify the check FAILS.
A passing negative fixture = validator catches the injected defect.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts" / "audit"))

from validate_phase_a0_1r import (
    check_ledger_open_count_strict,
    check_ledger_p0_s_open_strict,
    check_ledger_primary_phase_complete,
    check_ledger_billing_theater_split,
    check_ledger_npm_reframed,
    check_ledger_cdi_bounded,
    check_parity_no_illegal_statuses,
    check_parity_symmetric_thresholds,
    check_maturity_7_axes,
    check_manifest_empty_dirs,
    check_manifest_storage_mode,
)

sys.stdout.reconfigure(encoding="utf-8")


def load(path: str):
    with open(REPO_ROOT / path, "r", encoding="utf-8") as f:
        return json.load(f)


def expect_fail(name: str, result, expected_substring: str = ""):
    if result.passed:
        print(f"  [FAIL] {name}: validator PASSED on mutated input (defect not caught)")
        return False
    if expected_substring and expected_substring not in result.detail:
        print(f"  [FAIL] {name}: validator failed but detail doesn't mention '{expected_substring}'. Got: {result.detail}")
        return False
    print(f"  [PASS] {name}: validator caught defect ({result.detail[:80]})")
    return True


def main():
    all_pass = True

    # --- NF01: ledger.open_count_strict drift ---
    print("\n[NF01] ledger.open_count_strict — inject P0_aggregate_open_strict=99")
    ledger = load("reports/comprehensive-audit/phase-a0.1r/issue_ledger.v2_1.json")
    ledger["severity_counts_normalized"]["open_by_severity_strict_open"]["P0_aggregate_open_strict"] = 99
    all_pass &= expect_fail("NF01", check_ledger_open_count_strict(ledger), "claim=99")

    # --- NF02: ledger.p0_s_open_strict drift ---
    print("\n[NF02] ledger.p0_s_open_strict — inject P0-S_open=99")
    ledger = load("reports/comprehensive-audit/phase-a0.1r/issue_ledger.v2_1.json")
    ledger["severity_counts_normalized"]["open_by_severity_strict_open"]["P0-S_open"] = 99
    all_pass &= expect_fail("NF02", check_ledger_p0_s_open_strict(ledger), "claim=99")

    # --- NF03: ledger.primary_phase_complete - missing ID in mapping ---
    print("\n[NF03] ledger.primary_phase_complete — remove A0-P0-021 from A2_commercial_deferred")
    ledger = load("reports/comprehensive-audit/phase-a0.1r/issue_ledger.v2_1.json")
    if "A0-P0-021" in ledger["primary_phase_mapping"]["A2_commercial_deferred"]:
        ledger["primary_phase_mapping"]["A2_commercial_deferred"].remove("A0-P0-021")
    all_pass &= expect_fail("NF03", check_ledger_primary_phase_complete(ledger), "A0-P0-021")

    # --- NF04: ledger.billing_theater_split missing ---
    print("\n[NF04] ledger.billing_theater_split — remove split_status")
    ledger = load("reports/comprehensive-audit/phase-a0.1r/issue_ledger.v2_1.json")
    for i in ledger["issues"]:
        if i["canonical_id"] == "A0-P0-004":
            i.pop("split_status", None)
    all_pass &= expect_fail("NF04", check_ledger_billing_theater_split(ledger))

    # --- NF05: ledger.npm_reframed missing ---
    print("\n[NF05] ledger.npm_reframed — remove phase_a0_1r_reframe")
    ledger = load("reports/comprehensive-audit/phase-a0.1r/issue_ledger.v2_1.json")
    for i in ledger["issues"]:
        if i["canonical_id"] == "A0-P0-009":
            i.pop("phase_a0_1r_reframe", None)
    all_pass &= expect_fail("NF05", check_ledger_npm_reframed(ledger))

    # --- NF06: ledger.cdi_bounded missing ---
    print("\n[NF06] ledger.cdi_bounded — remove phase_a0_1r_boundary")
    ledger = load("reports/comprehensive-audit/phase-a0.1r/issue_ledger.v2_1.json")
    for i in ledger["issues"]:
        if i["canonical_id"] == "A0-P0-007":
            i.pop("phase_a0_1r_boundary", None)
    all_pass &= expect_fail("NF06", check_ledger_cdi_bounded(ledger))

    # --- NF07: parity.no_illegal_statuses — restore ICODER_TECH_DEBT on D-05 ---
    print("\n[NF07] parity.no_illegal_statuses — D-05 ICODER_TECH_DEBT restored")
    parity = load("reports/comprehensive-audit/phase-a0.1r/parity_matrix_v2_3.json")
    for x in parity["dimensions"]:
        if x["id"] == "D-05":
            x["parity_status"] = "ICODER_TECH_DEBT"
    all_pass &= expect_fail("NF07", check_parity_no_illegal_statuses(parity), "D-05")

    # --- NF08: parity.symmetric_thresholds — F-03 restored to CORTI_ADVANTAGE at E1 ---
    print("\n[NF08] parity.symmetric_thresholds — F-03 CORTI_ADVANTAGE at E1")
    parity = load("reports/comprehensive-audit/phase-a0.1r/parity_matrix_v2_3.json")
    for x in parity["dimensions"]:
        if x["id"] == "F-03":
            x["parity_status"] = "CORTI_ADVANTAGE"
            x["corti_evidence_grade"] = "E1"
    all_pass &= expect_fail("NF08", check_parity_symmetric_thresholds(parity), "F-03")

    # --- NF09: maturity.7_axes — remove security axis from a scenario ---
    print("\n[NF09] maturity.7_axes — CN-01 missing security axis")
    maturity = load("reports/comprehensive-audit/phase-a0.1r/product_maturity_v3.json")
    for s in maturity["china_scenarios"]:
        if s["id"] == "CN-01":
            s.pop("security", None)
    all_pass &= expect_fail("NF09", check_maturity_7_axes(maturity), "CN-01:security")

    # --- NF10: manifest.empty_dirs — restore exists=false on a dir ---
    print("\n[NF10] manifest.empty_dirs — set exists=false on a dir entry")
    manifest = load("reports/comprehensive-audit/phase-a0.1r/evidence_manifest.v2_2.json")
    for e in manifest["evidence_index"]["browser"]:
        if e.get("path") == "phase7/gate13a/screenshots/":
            e["exists"] = False
    all_pass &= expect_fail("NF10", check_manifest_empty_dirs(manifest), "screenshots")

    # --- NF11: manifest.storage_mode — set illegal mode ---
    print("\n[NF11] manifest.storage_mode — set storage_mode='SECRET_LEAKED'")
    manifest = load("reports/comprehensive-audit/phase-a0.1r/evidence_manifest.v2_2.json")
    manifest["evidence_index"]["git"][0]["storage_mode"] = "SECRET_LEAKED"
    all_pass &= expect_fail("NF11", check_manifest_storage_mode(manifest), "SECRET_LEAKED")

    print(f"\n=== Negative fixture summary ===")
    print(f"  All fixtures passed: {all_pass}")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
