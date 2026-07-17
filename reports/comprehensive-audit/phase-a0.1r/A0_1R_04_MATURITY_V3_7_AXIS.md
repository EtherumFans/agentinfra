# Phase A0.1R Gate 4 — Product Maturity V3 (7-axis)

> Adds the `security` and `delivery` axes required by Phase A0.1R
> charter §3.Gate4. Phase A0.1 v2's 5-axis model could not express
> security-gapped production blockers (A0-P0-016/017/020) or
> deployment-gapped scenarios (A0-P0-003) — a scenario could pass
> maturity despite shipping no production artifact. V3 closes that.
>
> Verdict: `PHASE_A0_1_R_GATE_4_MATURITY_V3_7_AXIS_POPULATED`

Source: `reports/comprehensive-audit/phase-a0.1/product_maturity_v2.json`
Target: `reports/comprehensive-audit/phase-a0.1r/product_maturity_v3.json`
Builder: `scripts/audit/build_maturity_v3.py`

---

## §1. Axis schema

V2 (5 axes):

```
code_maturity, quality_evidence, partner_validation,
regulatory, workflow_closure
```

V3 (7 axes):

```
code_maturity, quality_evidence, partner_validation,
regulatory, workflow_closure,
security,         ← NEW
delivery          ← NEW
```

## §2. New scales

### §2.1 security_scale_v3

| Grade | Meaning |
|---|---|
| L0_NOT_PRESENT | No security-relevant code or artifact |
| L1_ASSET_PRESENT | Code exists but no security testing or audit |
| L2_CONTRACT_PRESENT | Schema/API contract present and shipped; not yet production-security-audited |
| L3_CODE_PRESENT | Security design implemented and exercised in tests; no production audit |
| L4_RUNTIME_REACHABLE | Security exercised against real attack fixtures (negative verification) |
| L5_BROWSER_VERIFIED | Browser-verified security (CSP enforced, HMAC tokens tested in browser) |
| L6_NEGATIVE_AUDITED | Independent negative audit (penetration test report on file) |
| L7_CERTIFIED | External certification (等保2.0 三级, ISO 27001) |

### §2.2 delivery_scale_v3

| Grade | Meaning |
|---|---|
| L0_NOT_PRESENT | No deployment artifact |
| L1_ASSET_PRESENT | Code exists; no deployment mechanism |
| L2_CONTRACT_PRESENT | Deployment contract defined (Dockerfile, compose) but not exercised in real env |
| L3_CODE_PRESENT | Deployment exercised in local dev only |
| L4_RUNTIME_REACHABLE | Deployment exercised in a non-local pre-prod environment |
| L5_BROWSER_VERIFIED | Deployment live and reachable from a real browser session in a non-local env |
| L6_SIGNED_DISTRIBUTABLE | Deployment artifact is signed + reproducibly buildable + has SBOM |
| L7_PRODUCTION_DEPLOYED | Deployment live in a real region with real tenant traffic |

## §3. Per-scenario grades

| ID | Scenario | code | quality | partner | reg | workflow | **security** | **delivery** |
|---|---|---|---|---|---|---|---|---|
| CN-01 | Medical Coding | L4 | SMOKE_ONLY | SYNTHETIC_E2E | NONE | OPEN_LOOP | **L1** | **L1** |
| CN-02 | CDI | L4 | SMOKE_ONLY | NONE | NONE | OPEN_LOOP | **L1** | **L1** |
| CN-03 | DRG/DIP | L3 | NONE | NONE | NONE | N/A | **L1** | **L1** |
| CN-04 | Insurance Audit | L1 | NONE | NONE | NONE | N/A | **L0** | **L0** |
| CN-05 | Charge Compliance | L1 | NONE | NONE | NONE | N/A | **L0** | **L0** |
| CN-06 | Document Evidence | L1 | NONE | NONE | NONE | N/A | **L0** | **L0** |
| CN-07 | ICD-9-CM-3 | L4 | SMOKE_ONLY | NONE | NONE | OPEN_LOOP | **L1** | **L1** |
| CN-08 | AuditLog/RunHistory | L3 | NONE | NONE | NONE | N/A | **L2** | **L2** |
| CN-09 | Billing/Usage | L2 | NONE | NONE | NONE | N/A | **L1** | **L1** |
| CN-10 | 等保2.0 三级 | L1 | NONE | NONE | NONE | N/A | **L1** | **L0** |
| CN-11 | Embedded SDK | L6 | NONE | SYNTHETIC_E2E | NONE | OPEN_LOOP | **L3** | **L3** |
| CN-12 | Multi-tenant isolation | L3 | NONE | NONE | NONE | N/A | **L2** | **L1** |
| CN-13 | Partner Reference App | L6 | NONE | SYNTHETIC_E2E | NONE | OPEN_LOOP | **L3** | **L3** |
| CN-14 | Corti-style Agent Hub | L6 | NONE | NONE | NONE | OPEN_LOOP | **L2** | **L3** |
| CN-15 | A2A v0.3 Protocol | L4 | NONE | NONE | NONE | N/A | **L2** | **L3** |
| CN-16 | PHI redaction | L3 | NONE | NONE | NONE | N/A | **L2** | **L1** |

## §4. Headline numbers

```
scenarios at code L7+                  : 0  (unchanged from v2)
scenarios with formal benchmark        : 0  (unchanged)
scenarios with real partner            : 0  (unchanged)
scenarios at security L7+              : 0  (NEW axis)
scenarios at security L6+              : 0  (NEW axis)
scenarios at delivery L7+              : 0  (NEW axis)
scenarios at delivery L6+              : 0  (NEW axis)
scenarios with formal security audit   : 0  (NEW)
scenarios with signed distributable    : 0  (NEW)
scenarios with production deployment   : 0  (NEW)
```

**Product Truth unchanged**: 0/16 scenarios are production-ready.
The new axes make the gap explicit per scenario rather than
implicitly bundling it into "workflow_closure" or omitting it.

## §5. Notable grade assignments

### §5.1 CN-01 Medical Coding — security=L1, delivery=L1

Despite `code=L4_RUNTIME_REACHABLE` (the agent path runs end-to-end
on real DeepSeek), the security axis is L1 because the underlying
platform has 6 open P0-S findings (A0-P0-010/011/012/016/017/020).
A code-maturity L4 scenario with security L1 cannot be deployed.
Same logic for delivery: no shippable deployment path (A0-P0-003).

This is exactly the gap the v2 model could not express.

### §5.2 CN-11 Embedded SDK — security=L3

Above L1 because Phase 7 Gate 13A hardened the widget: HMAC
bootstrap ticket, partner CORS, CSP nonce, sandbox, no-store,
no-referrer. Below L4 because no negative verification (e.g.,
penetration test) exists.

### §5.3 CN-10 等保2.0 三级 — security=L1, delivery=L0

Security L1 because certifications are not obtained (A0-P0-001).
Delivery L0 because compliance certification is a legal artifact,
not a deployment artifact — there is nothing to ship until the
certs are issued.

### §5.4 CN-04/05/06 Insurance Audit / Charge Compliance / Document Evidence — security=L0, delivery=L0

All three are reserved-for-future scenarios with code skeleton
only (rule structures in `compliance_services/`). No live path,
no security surface, no deployment artifact. L0/L0.

## §6. Validator V3 hooks

Gate 7 will enforce:

1. Every scenario has all 7 axis keys.
2. Each axis value is in the corresponding scale.
3. `summary.v3_axis_addition.scenarios_at_security_L7_plus`
   matches array count.
4. Negative fixture `nf05_missing_security_axis.json` (a scenario
   with `security` removed) fails.

## §7. Findings raised in Gate 4

| ID | Severity | Title |
|----|----------|-------|
| **A0.1R-G4-001** (closed) | P1 | security + delivery axes added to all 16 scenarios. |
| **A0.1R-G4-002** (closed) | P1 | Published security_scale_v3 and delivery_scale_v3 (L0-L7). |
| **A0.1R-G4-003** | P2 | CN-01 Medical Coding security=L1 + delivery=L1 makes explicit that code-L4 alone is not production-ready. Phase A1A workplan must reflect this. |
| **A0.1R-G4-004** | P2 | CN-09 Billing security=L1 + delivery=L1 makes explicit that A0-P0-004a (Product Truth) + A0-P0-004b (Commercial Capability) both block this scenario. |
| **A0.1R-G4-005** | P2 | CN-10 等保2.0 三级 delivery=L0 — no deployment artifact is possible until the cert is issued. Phase A1A-legal-compliance workplan owns this. |

---

## §8. Gate 4 verdict

```
PHASE_A0_1_R_GATE_4_MATURITY_V3_7_AXIS_POPULATED

product_maturity_v3.json:
  schema_version: 3.0
  supersedes: reports/comprehensive-audit/phase-a0.1/product_maturity_v2.json
  axes_per_scenario: 7 (was 5)
  security_scale_v3: published (L0-L7)
  delivery_scale_v3: published (L0-L7)
  scenarios_at_security_L7+: 0
  scenarios_at_delivery_L7+: 0
  product_truth_unchanged: 0/16 production-ready

NEXT_GATE: GATE_5_MANIFEST_V2_2
NEXT_ALLOWED_VERDICT:
  PHASE_A0_1_R_GATE_5_MANIFEST_V2_2_CORRECTED
```

End of Gate 4.
