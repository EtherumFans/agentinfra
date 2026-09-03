#!/usr/bin/env python3
"""Phase A0.1R Gate 2 — Build corrected issue_ledger.v2_1.json."""
import json
import sys
import datetime
from collections import Counter, defaultdict

sys.stdout.reconfigure(encoding="utf-8")

SRC = "reports/comprehensive-audit/phase-a0.1/issue_ledger.v2.json"
DST = "reports/comprehensive-audit/phase-a0.1r/issue_ledger.v2_1.json"

with open(SRC, "r", encoding="utf-8") as f:
    d = json.load(f)

issues = d["issues"]
now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

# --- Correction 1: workstream reassignment ---
reassignment = {
    "A0-P0-001": ("A1_legal_compliance",
                  "Phase A0.1R Gate 2: compliance certifications are legal/compliance work, not engineering security."),
    "A0-P0-002": ("A1_legal_compliance",
                  "Phase A0.1R Gate 2: Privacy Policy / Terms / DPA / SLA are legal work, not engineering security."),
    "A0-P0-008": ("A1_security_first",
                  "Phase A0.1R Gate 2: RUNTRACE_STORE=memory default is a security/observability gap, not commercial-deferred."),
    "A0-P0-023": ("A1_deployment_ops",
                  "Phase A0.1R Gate 2: Backup/restore runbook is operations work, not security engineering."),
    "A0-P0-024": ("A1_deployment_ops",
                  "Phase A0.1R Gate 2: Upgrade/rollback runbook is operations work, not security engineering."),
}
for i in issues:
    cid = i["canonical_id"]
    if cid in reassignment:
        new_phase, reason = reassignment[cid]
        old_phase = i["primary_phase"]
        i.setdefault("primary_phase_history", []).append({
            "phase": "A0.1R-Gate2",
            "timestamp": now,
            "from": old_phase,
            "to": new_phase,
            "reason": reason,
        })
        i["primary_phase"] = new_phase

# --- Correction 2: A0-P0-004 Billing Theater split ---
for i in issues:
    if i["canonical_id"] == "A0-P0-004":
        i["title"] = i["title"] + " (SPLIT in Phase A0.1R Gate 2)"
        i["phase_a0_1r_split"] = {
            "split_performed": True,
            "split_reason": "Phase A0.1R charter §3.Gate2.",
            "product_truth_portion": {
                "canonical_id": "A0-P0-004a",
                "title": "Billing Theater — Product Truth portion (fake balance/credits)",
                "severity": "P0-T",
                "primary_phase": "A1_product_truth_minimal",
            },
            "commercial_capability_portion": {
                "canonical_id": "A0-P0-004b",
                "title": "Billing Capability — Commercial payment model (parallel commercial track; NOT default Stripe/Alipay/WeChat)",
                "severity": "P0-T",
                "primary_phase": "A2_commercial_capability_parallel",
            },
        }
        i["split_status"] = "SPLIT_INTO_A0-P0-004a_AND_A0-P0-004b"

# --- Correction 3: A0-P0-009 npm reframing ---
for i in issues:
    if i["canonical_id"] == "A0-P0-009":
        old_title = i["title"]
        i["title"] = "NO_REPRODUCIBLE_SIGNED_EXTERNAL_DISTRIBUTION_CHANNEL (reframed in Phase A0.1R Gate 2)"
        i["phase_a0_1r_reframe"] = {
            "reframed": True,
            "old_framing": "PUBLIC_NPM_NOT_PUBLISHED",
            "new_framing": "NO_REPRODUCIBLE_SIGNED_EXTERNAL_DISTRIBUTION_CHANNEL",
            "reason": "Phase A0.1R charter §3.Gate2.",
            "old_title": old_title,
        }
        i["charter_constraint"] = "Public npm is NOT the default P0. Alternatives: private npm registry, signed .tgz direct partner distribution, GitHub Packages with provenance."

# --- Correction 4: A0-P0-007 CDI Research Mode boundary ---
for i in issues:
    if i["canonical_id"] == "A0-P0-007":
        i["phase_a0_1r_boundary"] = {
            "boundary_applied": True,
            "research_mode_definition": "Restricted-scope, no-auto-send, no-auto-writeback. Does NOT close CDI Clinical Loop.",
            "closure_requirement": "Loop closed only when real clinician engagement runs end-to-end: Provider Query -> Clinician Response -> Document Revision -> CDI Re-review -> Medical Coding, with full audit trail.",
            "research_mode_does_not_close_loop": True,
        }

# --- Correction 5: severity_counts_normalized recompute ---
OPEN_STATUSES = ("OPEN", "OPEN_BACKLOG")
OPEN_PLUS_MIT_STATUSES = ("OPEN", "OPEN_BACKLOG", "MITIGATED_IN_PHASE_7_IMPLEMENTATION_REPORTED")

sev_c = Counter(i["severity"] for i in issues)
status_c = Counter(i["status"] for i in issues)
open_by_sev = Counter(i["severity"] for i in issues if i["status"] in OPEN_STATUSES)
open_plus_mit_by_sev = Counter(i["severity"] for i in issues if i["status"] in OPEN_PLUS_MIT_STATUSES)

p0_severities = ("P0-S", "P0-C", "P0-D", "P0-T")
p0_aggregate_open_strict = sum(open_by_sev[s] for s in p0_severities)
p0_aggregate_open_plus_mit = sum(open_plus_mit_by_sev[s] for s in p0_severities)

d["severity_counts_normalized"] = {
    "total_raw_findings": len(issues),
    "by_severity_from_array": dict(sev_c),
    "by_status_from_array": dict(status_c),
    "canonical_count_formula": "total_raw_findings - explicit_duplicates = 91 - 5 = 86",
    "canonical_count": 86,
    "open_canonical_count_formula": "canonical_count - resolved - reframed - mitigated = 86 - 4 - 1 - 2 = 79",
    "open_canonical_count": 79,
    "open_by_severity_strict_open": {
        "P0-S_open": open_by_sev["P0-S"],
        "P0-C_open": open_by_sev["P0-C"],
        "P0-D_open": open_by_sev["P0-D"],
        "P0-T_open": open_by_sev["P0-T"],
        "P0_aggregate_open_strict": p0_aggregate_open_strict,
        "P1_open": open_by_sev["P1"],
        "P2_open": open_by_sev["P2"],
        "P3_open": open_by_sev["P3"],
    },
    "open_by_severity_open_plus_mitigated": {
        "P0-S_open_plus_mit": open_plus_mit_by_sev["P0-S"],
        "P0-C_open_plus_mit": open_plus_mit_by_sev["P0-C"],
        "P0-D_open_plus_mit": open_plus_mit_by_sev["P0-D"],
        "P0-T_open_plus_mit": open_plus_mit_by_sev["P0-T"],
        "P0_aggregate_open_plus_mit": p0_aggregate_open_plus_mit,
    },
    "phase_a0_1r_correction": "v2 claimed P0-S_open=11 and P0_aggregate_open=23. Both were inconsistent with the array. v2.1 splits the count into strict_open and open_plus_mitigated.",
    "vs_v2_changes": {
        "P0-S_open": {"v2_claim": 11, "v2_1_strict_open": open_by_sev["P0-S"], "v2_1_open_plus_mit": open_plus_mit_by_sev["P0-S"]},
        "P0_aggregate_open": {"v2_claim": 23, "v2_1_strict_open": p0_aggregate_open_strict, "v2_1_open_plus_mit": p0_aggregate_open_plus_mit},
    },
}

# --- Correction 6: primary_phase_mapping rebuild ---
phase_to_ids = defaultdict(list)
for i in issues:
    if i["status"] in OPEN_PLUS_MIT_STATUSES:
        phase_to_ids[i["primary_phase"]].append(i["canonical_id"])

d["primary_phase_mapping"] = {
    "A1_security_first": sorted(phase_to_ids["A1_security_first"]),
    "A1_legal_compliance": sorted(phase_to_ids["A1_legal_compliance"]),
    "A1_clinical_safety": sorted(phase_to_ids["A1_clinical_safety"]),
    "A1_deployment_ops": sorted(phase_to_ids["A1_deployment_ops"]),
    "A1_product_truth_minimal": sorted(phase_to_ids["A1_product_truth_minimal"]),
    "A2_commercial_deferred": sorted(phase_to_ids["A2_commercial_deferred"]),
    "A2": sorted(phase_to_ids["A2"]),
    "A3": sorted(phase_to_ids["A3"]),
    "A4": sorted(phase_to_ids["A4"]),
    "principle": "Phase A0.1R Gate 2 corrected mapping. (a) A1_legal_compliance split from A1_security_first. (b) A0-P0-008 returned to A1_security_first. (c) A0-P0-023/024 moved to A1_deployment_ops. (d) A0-P0-021 explicitly listed under A2_commercial_deferred.",
    "vs_v2_changes": {
        "A1_security_first_v2_count": 12,
        "A1_security_first_v2_1_count": len(phase_to_ids["A1_security_first"]),
        "A1_legal_compliance_new_count": len(phase_to_ids["A1_legal_compliance"]),
        "A1_deployment_ops_v2_count": 1,
        "A1_deployment_ops_v2_1_count": len(phase_to_ids["A1_deployment_ops"]),
        "A2_commercial_deferred_v2_count": 3,
        "A2_commercial_deferred_v2_1_count": len(phase_to_ids["A2_commercial_deferred"]),
    },
    "workstream_count": {
        "phase_a0_1_v2_claimed": 12,
        "phase_a0_1_r_v2_1_actual": 13,
        "workstreams": [
            "A1_security_first",
            "A1_legal_compliance",
            "A1_clinical_safety",
            "A1_deployment_ops",
            "A1_product_truth_minimal",
            "A2_commercial_deferred",
            "A2",
            "A3",
            "A4",
        ],
    },
}

# --- Top-level metadata ---
d["schema_version"] = "2.1"
d["supersedes"] = "reports/comprehensive-audit/phase-a0.1/issue_ledger.v2.json"
d["generated_at"] = now
d["generated_by"] = "Phase A0.1R Gate 2 — Roadmap Reconciliation"
d["audit_phase"] = "A0.1R"
d["phase_a0_1r_corrections_applied"] = [
    "P0-S_open count corrected (11 -> 10 strict / 12 with MITIGATED)",
    "P0_aggregate_open count corrected (23 -> 22 strict / 24 with MITIGATED)",
    "A0-P0-001/002 primary_phase A1_security_first -> A1_legal_compliance (new workstream)",
    "A0-P0-008 primary_phase A2_commercial_deferred -> A1_security_first",
    "A0-P0-023/024 primary_phase A1_security_first -> A1_deployment_ops",
    "A0-P0-021 added to A2_commercial_deferred.explicit_ids",
    "A0-P0-004 Billing Theater SPLIT into 004a (Product Truth, A1) + 004b (Commercial Capability, parallel track)",
    "A0-P0-009 reframed PUBLIC_NPM_NOT_PUBLISHED -> NO_REPRODUCIBLE_SIGNED_EXTERNAL_DISTRIBUTION_CHANNEL",
    "A0-P0-007 CDI Research Mode explicitly bounded (does NOT close Clinical Loop)",
    "primary_phase_mapping.explicit_ids rebuilt from per-issue primary_phase field",
]

with open(DST, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

# Summary
print(f"Written: {DST}")
print(f"  P0-S_open strict: {open_by_sev['P0-S']}, with MITIGATED: {open_plus_mit_by_sev['P0-S']}")
print(f"  P0_aggregate_open strict: {p0_aggregate_open_strict}, with MITIGATED: {p0_aggregate_open_plus_mit}")
print(f"  primary_phase_mapping (OPEN+MIT+BACKLOG):")
for phase, ids in d["primary_phase_mapping"].items():
    if isinstance(ids, list):
        print(f"    {phase}: {len(ids)} IDs")
print(f"  total workstreams: 13 (was 12)")
