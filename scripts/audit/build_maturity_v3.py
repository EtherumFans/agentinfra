#!/usr/bin/env python3
"""Phase A0.1R Gate 4 - Build corrected product_maturity_v3.json (7-axis)."""
import json
import sys
import datetime

sys.stdout.reconfigure(encoding="utf-8")

SRC = "reports/comprehensive-audit/phase-a0.1/product_maturity_v2.json"
DST = "reports/comprehensive-audit/phase-a0.1r/product_maturity_v3.json"

with open(SRC, "r", encoding="utf-8") as f:
    d = json.load(f)

now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

# Per-scenario security + delivery grades
# Derived from canonical issue ledger (which issues block each scenario)
SECURITY_DELIVERY = {
    "CN-01": {
        "security": ("L1_ASSET_PRESENT",
                     "Medical Coding runs on the unified agent_run path which inherits all security gaps: no encryption at rest (A0-P0-016), PHI redactor export-only (A0-P0-017), 235/240 NULL org_id (A0-P0-012), audit_logs thin (A0-P0-011). Production-blocked until A1_security_first + A1_legal_compliance close."),
        "delivery": ("L1_ASSET_PRESENT",
                     "No shippable deployment path (A0-P0-003 docs-only). Docker compose local-dev is explicitly forbidden for hospital production. Cloud SaaS path requires ICODER_DEPLOYMENT_MODE=cloud + cloud-only env vars not yet exercised."),
    },
    "CN-02": {
        "security": ("L1_ASSET_PRESENT",
                     "CDI shares the Medical Coding security surface. Research Mode boundary applied in A0.1R Gate 2 (no auto-send, no auto-writeback). A0-P0-007 still open."),
        "delivery": ("L1_ASSET_PRESENT",
                     "Same as CN-01: no shippable deployment path."),
    },
    "CN-03": {
        "security": ("L1_ASSET_PRESENT",
                     "DRG/DIP rule structures reserved; no live PHI flow yet, but any future wiring inherits platform security gaps."),
        "delivery": ("L1_ASSET_PRESENT",
                     "Reserved-for-future, no deployment artifact."),
    },
    "CN-04": {
        "security": ("L0_NOT_PRESENT",
                     "Insurance Audit rule structures not implemented; no security exposure yet because no live path."),
        "delivery": ("L0_NOT_PRESENT",
                     "No artifact to ship."),
    },
    "CN-05": {
        "security": ("L0_NOT_PRESENT", "Same as CN-04."),
        "delivery": ("L0_NOT_PRESENT", "Same as CN-04."),
    },
    "CN-06": {
        "security": ("L0_NOT_PRESENT", "Same as CN-04."),
        "delivery": ("L0_NOT_PRESENT", "Same as CN-04."),
    },
    "CN-07": {
        "security": ("L1_ASSET_PRESENT",
                     "ICD-9-CM-3 procedure coding shares the Medical Coding agent_run path; same security gap profile as CN-01."),
        "delivery": ("L1_ASSET_PRESENT", "Same as CN-01."),
    },
    "CN-08": {
        "security": ("L2_CONTRACT_PRESENT",
                     "AuditLog + RunHistory models exist; A0-P0-011 (only 5 actions audited) and A0-P0-008 (RUNTRACE_STORE=memory default) are direct security gaps for this scenario. Above L1 because there is a real schema and endpoints."),
        "delivery": ("L2_CONTRACT_PRESENT",
                     "Trace evidence is queryable via /api/v1/runs/{id}/trace and /events SSE endpoints (Phase 7 Gate 7+9). Above L1 because the API is shipped, but no deployment artifacts."),
    },
    "CN-09": {
        "security": ("L1_ASSET_PRESENT",
                     "Billing/Usage endpoints exist; A0-P0-004a (Billing Theater Product Truth) directly impacts this scenario. No payment model means no real monetary attack surface, but fake-balance UX is a product-truth issue."),
        "delivery": ("L1_ASSET_PRESENT",
                     "No commercial delivery path. A0-P0-004b (Commercial Capability) blocks. Billing endpoints exist but no ledger backend."),
    },
    "CN-10": {
        "security": ("L1_ASSET_PRESENT",
                     "等保2.0 三级 compliance certifications not obtained (A0-P0-001). Legal docs absent (A0-P0-002). All A1_legal_compliance work blocks this scenario."),
        "delivery": ("L0_NOT_PRESENT",
                     "Compliance certification is a legal/operational artifact, not a deployment artifact. Until certs are obtained, delivery is L0."),
    },
    "CN-11": {
        "security": ("L3_CODE_PRESENT",
                     "Embedded SDK Web Component shipped with partner CORS, CSP, HMAC bootstrap ticket (Phase 7 Gate 13A). Above L1 because Gate 13A's hardening is real and exercised. Still below L4 because production secrets management not yet operational."),
        "delivery": ("L3_CODE_PRESENT",
                     "Web Component is shipped as a real artifact (npm tarball icoder-embedded-2.0.0.tgz) but no signed external distribution channel (A0-P0-009 reframed in A0.1R Gate 2)."),
    },
    "CN-12": {
        "security": ("L2_CONTRACT_PRESENT",
                     "Multi-tenant isolation: schema has organization_id on most tables; alembic migrations 013-015 added run_history.status + preview_sessions. A0-P0-012 (NULL org_id on 235/240 historical rows) and A0-P0-022 (Trace+Usage+Context isolation design-only) directly impact. Above L1 because schema is real."),
        "delivery": ("L1_ASSET_PRESENT",
                     "Multi-tenant SaaS deployment not exercised in any real region. Cloud SaaS path is docs-only."),
    },
    "CN-13": {
        "security": ("L3_CODE_PRESENT",
                     "Partner Reference App shipped with server-side secret exchange (Phase 7 Gate 12). Compromised credential contained in A0.1R Gate 1. Above L1 because the security architecture is real and exercised."),
        "delivery": ("L3_CODE_PRESENT",
                     "examples/partner-reference-app/ ships as a real Node.js Express server. Above L1. Below L4 because no production deployment path."),
    },
    "CN-14": {
        "security": ("L2_CONTRACT_PRESENT",
                     "Agent Hub is a UI feature; security surface is shared with the underlying platform (auth + multi-tenant). No specific Agent Hub security gap above the platform baseline."),
        "delivery": ("L3_CODE_PRESENT",
                     "/ai-studio/agents Console page is browser-verified (Phase 4 walkthrough). Shipped as part of the frontend SPA."),
    },
    "CN-15": {
        "security": ("L2_CONTRACT_PRESENT",
                     "A2A v0.3 wrapper exposed at /a2a; shares platform auth. No protocol-level security gap beyond platform baseline."),
        "delivery": ("L3_CODE_PRESENT",
                     "A2A endpoint shipped and exercised in Phase 5 Track C. Above L1."),
    },
    "CN-16": {
        "security": ("L2_CONTRACT_PRESENT",
                     "PHI redactor (pii_redaction.py) is EXPORT-PATH ONLY per Gate 9 K3.2. A0-P0-017 is the direct finding. Above L1 because the code exists and is exercised on export paths."),
        "delivery": ("L1_ASSET_PRESENT",
                     "PHI redactor ships as part of backend; no separate deployment artifact."),
    },
}

for s in d["china_scenarios"]:
    sid = s["id"]
    if sid in SECURITY_DELIVERY:
        sec_grade, sec_rationale = SECURITY_DELIVERY[sid]
        del_grade, del_rationale = SECURITY_DELIVERY[sid]
        s["security"] = sec_grade
        s["security_rationale"] = sec_rationale
        s["delivery"] = del_grade
        s["delivery_rationale"] = del_rationale
        s["phase_a0_1r_axis_addition"] = {
            "gate": "A0.1R-Gate4",
            "timestamp": now,
            "axes_added": ["security", "delivery"],
            "reason": "Phase A0.1R charter §3.Gate4 mandates 7-axis maturity (code, quality, partner, regulatory, workflow_closure, security, delivery).",
        }

# Update multi_axis_definition
d["multi_axis_definition"]["axes_v3"] = [
    {"key": "code_maturity", "kind": "graded", "scale_ref": "maturity_scale_v1"},
    {"key": "quality_evidence", "kind": "graded", "scale_ref": "quality_scale_v1"},
    {"key": "partner_validation", "kind": "graded", "scale_ref": "partner_scale_v1"},
    {"key": "regulatory", "kind": "graded", "scale_ref": "regulatory_scale_v1"},
    {"key": "workflow_closure", "kind": "graded", "scale_ref": "workflow_scale_v1"},
    {"key": "security", "kind": "graded", "scale_ref": "security_scale_v3", "added_in": "v3"},
    {"key": "delivery", "kind": "graded", "scale_ref": "delivery_scale_v3", "added_in": "v3"},
]

d["multi_axis_definition"]["security_scale_v3"] = {
    "L0_NOT_PRESENT": "No security-relevant code or artifact.",
    "L1_ASSET_PRESENT": "Code exists but no security testing or audit.",
    "L2_CONTRACT_PRESENT": "Schema/API contract present and shipped; not yet production-security-audited.",
    "L3_CODE_PRESENT": "Security design implemented and exercised in tests; no production audit.",
    "L4_RUNTIME_REACHABLE": "Security exercised against real attack fixtures (e.g., negative verification).",
    "L5_BROWSER_VERIFIED": "Browser-verified security (e.g., CSP enforced, HMAC tokens tested in browser).",
    "L6_NEGATIVE_AUDITED": "Independent negative audit (penetration test report on file).",
    "L7_CERTIFIED": "External certification (等保2.0 三级, ISO 27001, etc.).",
}

d["multi_axis_definition"]["delivery_scale_v3"] = {
    "L0_NOT_PRESENT": "No deployment artifact.",
    "L1_ASSET_PRESENT": "Code exists; no deployment mechanism.",
    "L2_CONTRACT_PRESENT": "Deployment contract defined (Dockerfile, compose) but not exercised in any real env.",
    "L3_CODE_PRESENT": "Deployment exercised in local dev only.",
    "L4_RUNTIME_REACHABLE": "Deployment exercised in a non-local pre-prod environment.",
    "L5_BROWSER_VERIFIED": "Deployment live and reachable from a real browser session in a non-local env.",
    "L6_SIGNED_DISTRIBUTABLE": "Deployment artifact is signed + reproducibly buildable + has SBOM.",
    "L7_PRODUCTION_DEPLOYED": "Deployment live in a real region with real tenant traffic.",
}

# Top-level metadata
d["schema_version"] = "3.0"
d["supersedes"] = "reports/comprehensive-audit/phase-a0.1/product_maturity_v2.json"
d["generated_at"] = now
d["generated_by"] = "Phase A0.1R Gate 4 — Maturity V3 (7-axis)"
d["audit_phase"] = "A0.1R"
d["phase_a0_1r_corrections_applied"] = [
    "Added security axis to all 16 scenarios (16/16 previously missing)",
    "Added delivery axis to all 16 scenarios (16/16 previously missing)",
    "Published security_scale_v3 (L0-L7) and delivery_scale_v3 (L0-L7)",
    "Per-scenario rationales cross-reference canonical issue ledger (A0-P0-* IDs)",
]

# Recompute summary
scenarios_at_l7_plus_security = sum(1 for s in d["china_scenarios"] if s.get("security", "").startswith("L7"))
scenarios_at_l7_plus_delivery = sum(1 for s in d["china_scenarios"] if s.get("delivery", "").startswith("L7"))
scenarios_at_l6_plus_security = sum(1 for s in d["china_scenarios"] if s.get("security", "").startswith(("L6", "L7")))
scenarios_at_l6_plus_delivery = sum(1 for s in d["china_scenarios"] if s.get("delivery", "").startswith(("L6", "L7")))

d["summary"]["v3_axis_addition"] = {
    "axes_in_v2": 5,
    "axes_in_v3": 7,
    "axes_added": ["security", "delivery"],
    "scenarios_at_security_L7_plus": scenarios_at_l7_plus_security,
    "scenarios_at_security_L6_plus": scenarios_at_l6_plus_security,
    "scenarios_at_delivery_L7_plus": scenarios_at_l7_plus_delivery,
    "scenarios_at_delivery_L6_plus": scenarios_at_l6_plus_delivery,
    "scenarios_with_formal_security_audit": 0,
    "scenarios_with_signed_distributable": 0,
    "scenarios_with_production_deployment": 0,
    "phase_a0_1r_summary_note": "Adding security+delivery axes does not promote any scenario above L4 on the new axes. The Product Truth remains: 0 scenarios at code-maturity L7+, 0 with formal benchmark, 0 with real partner. The new axes make the security/delivery gaps explicit per scenario.",
}

with open(DST, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

print(f"Written: {DST}")
print(f"  total scenarios: {len(d['china_scenarios'])}")
print(f"  axes per scenario: 7 (was 5)")
print(f"  security scale: v3 (L0-L7)")
print(f"  delivery scale: v3 (L0-L7)")
print(f"  scenarios at security L7+: {scenarios_at_l7_plus_security}")
print(f"  scenarios at delivery L7+: {scenarios_at_l7_plus_delivery}")
