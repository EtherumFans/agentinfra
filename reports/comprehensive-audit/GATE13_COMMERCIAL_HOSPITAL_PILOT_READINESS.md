# Audit Gate 13 — Commercial and Hospital Pilot Readiness (Track O)

> Per PDF §三 Track O: audits the commercial surface (billing, pricing, subscription tiers), the hospital pilot intake process, compliance certifications (等保2.0 / GB/T 35273-2020 / HIPAA), legal docs (ToS / Privacy / DPA), and partner/channel readiness. Determines whether iCoDer can sign a hospital pilot contract tomorrow.

## O1. Commercial surface — internal credits only, no real money flow

### O1.1 Billing model

`backend/app/models/billing.py`:

```python
class Transaction(Base, TimestampMixin):
    __tablename__ = "transactions"
    organization_id: Mapped[str | None]
    user_id: Mapped[str]
    type: Mapped[str]            # credit / debit
    amount: Mapped[float]
    balance_after: Mapped[float]
    description: Mapped[str]
    source: Mapped[str]          # purchase / api_usage / refund
```

One table, append-only ledger. Default starting balance: `¥50.0` (`billing.py:23`).

### O1.2 Billing endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/billing/balance` | Current credit balance |
| GET | `/api/billing/transactions` | Transaction history |
| POST | `/api/billing/credits?amount=50.0` | **Add credits (no payment)** |

The "Add credits" endpoint just creates a Transaction row with `source="purchase"` and bumps `balance_after`. **No real payment processor is wired.** No Stripe, no Alipay, no WeChat Pay. The credits are free.

### O1.3 DB reality — 0 transactions

```
transactions: 0 rows
```

Despite 240 agent runs consuming an aggregate ¥0.049392 of LLM cost (per Gate 7), **no transaction has ever been written to debit the user's balance**. The credits system is dormant.

Register as **G13-001 (P0)**: billing is theater. The "Add credits" button in the Console UI calls `POST /api/billing/credits` which adds free credits. There is no payment processor. No transaction has ever been recorded in production. The `/billing` page shows `¥50.00` balance + `¥0.00 consumed` (per Gate 3 §C1) — both numbers are fake.

### O1.4 No pricing tiers

Search across docs + code for pricing tiers, plans, paid vs free:

```
$ grep -rn "tier\|plan_id\|free.*plan\|paid.*plan\|enterprise" docs/ CLAUDE.md README.md
(empty)
```

- ❌ No tiered pricing (free / pro / enterprise)
- ❌ No subscription model
- ❌ No per-case pricing
- ❌ No per-token pass-through pricing
- ❌ No invoice generation
- ❌ No tax calculation

The entire commercial model is **"click button → +¥50 free credits"**.

## O2. Hospital pilot intake — process documented, never exercised

### O2.1 Intake template

`docs/cloud/CLOUD_INTAKE_TEMPLATE.md` is a real intake form with 6 sections:

1. Tenant basic info (name, slug, contact, industry, scenario, target date)
2. Environment & region selection (eu / us / cn × multi-region)
3. Compliance & data residency declarations (4 checkboxes)
4. API Client provisioning defaults (scopes, ROPC optional)
5. LLM provider selection (DeepSeek default, Claude optional, vLLM optional)
6. Integration mode selection (Web Component / backend-service / dual)

This is **methodologically sound** onboarding paperwork.

### O2.2 Onboarding workflow

Per template §3:

```
1. Tenant admin submits template → iCoDer ops
2. Compliance review (DPA / SLA / local regs) → 1-3 business days
3. Tenant creation → automated provisioning script
   - database schema creation
   - LLM credential vault injection
   - API Client issuance (client_id + client_secret)
4. Tenant handoff → tenant admin logs in, configures
5. Pilot kickoff → integration team supports
```

### O2.3 DB reality — 0 real tenants

Per Gate 9 §K4.3: 42 organizations, all test/audit artifacts:

```
"E2E Org e2e_*"               (auto-generated test orgs)
"Healthcheck Org *"
"Gate 6 Sweep's Organization"
"P05 Gate2 After's Organization"
"Gate 7 Walkthrough Org" (g7org)
"Gate13's Organization"
"Phase 4B Walker's Organization"
"CDI Test's Organization"
默认组织 (default)
```

**Zero real hospital tenants.** The intake template has never been submitted by a real customer.

Register as **G13-002 (P1)**: hospital pilot intake process is documented but never exercised. There is no evidence iCoDer has ever talked to a real hospital about piloting.

## O3. Compliance certifications — TARGETS only, no certifications

### O3.1 Compliance frameworks listed

`docs/cloud/CLOUD_DEPLOYMENT.md §2 Region table`:

| Environment | Compliance frameworks | Status |
|-------------|----------------------|--------|
| eu | GDPR + EHDS | TBD |
| us | HIPAA + HITECH | TBD |
| cn | 数据安全法 + 个人信息保护法 + 医疗数据规定 | TBD |

All three regions list frameworks as **TBD** (to-be-determined). No certification has been obtained.

### O3.2 China-specific compliance — what's needed vs what's present

For a Chinese hospital pilot, the typical compliance stack is:

| Certification | Required for | iCoDer status |
|---------------|--------------|---------------|
| 等保2.0 三级 (MLPS Level 3) | Public hospital systems handling PHI | ❌ Not certified; G9-005 fails encryption-at-rest; G9-006 fails password complexity |
| GB/T 35273-2020 (PII protection) | Personal information security specification | ❌ Not certified; PIIRedactor has explicit WARNING it's not compliant (G9-004) |
| 医疗器械软件 (SaMD) | If classified as medical device (clinical decision support) | ❌ Not filed with NMPA |
| 网络安全审查 | Cross-border data transfer | ❌ Not filed |
| ISO 27001 | Information security management | ❌ Not certified |
| HIPAA (for us region) | US hospital PHI | ❌ Not certified |

Register as **G13-003 (P0)**: zero compliance certifications obtained. The product cannot be sold to any Chinese public hospital without 等保2.0 三级 certification. The current implementation actively fails the technical controls (encryption at rest, audit log coverage, password complexity) that 等保 audit would check.

### O3.3 PHI redaction compliance gap

`backend/icoder_runtime/core/pii_redaction.py:1-8`:

```python
"""PII Redaction — simple rule-based redaction for hospital deployment.

WARNING: This is SIMPLE rule-based redaction, NOT production-grade medical de-identification.
It removes obvious PII patterns (names, IDs, phone numbers, addresses) but does NOT
guarantee HIPAA/GB/T 35273-2020 compliance. For production, integrate a certified
medical de-identification service.
"""
```

The code itself disclaims GB/T 35273 compliance. Per Gate 9 §K3.2, the redactor is also **export-only** — the live LLM-bound path (corti_like_fast, 35 production runs) does not redact.

## O4. Legal documents — none exist

### O4.1 Login page references

`frontend/src/pages/LoginPage.tsx:164`:

```tsx
使用前请阅读 <button onClick={() => navigate('/support')}>隐私政策</button> 和
<button onClick={() => navigate('/support')}>服务条款</button>
```

The login page links to `/support` for both Privacy Policy and Terms of Service. But `/support` (per Gate 3 + `SupportPage.tsx` source) is a generic help page with links to docs / tickets / customer service / email.

- ❌ No `/legal/privacy` page
- ❌ No `/legal/terms` page
- ❌ No `/legal/dpa` page
- ❌ No `/legal/sla` page

Register as **G13-004 (P0)**: zero legal documents exist. No Privacy Policy, no Terms of Service, no DPA, no SLA document. The login page pretends to link to them but both links redirect to the generic support page. For any hospital contract signature, these 4 documents are mandatory.

### O4.2 SLA document

`docs/cloud/CLOUD_DEPLOYMENT.md §5` lists SLA targets:

```
| Availability | 99.5% (single region) / 99.9% (active-active, future) |
| P50 latency (coding run) | ≤ 8s (BGE-M3 cached) / ≤ 60s (cold) |
| P99 latency (coding run) | ≤ 120s |
| Data durability | 99.999999% |
| RTO | ≤ 4h (single region) |
| RPO | ≤ 1h (single region) |
```

These are targets in a markdown design doc, not a signed SLA contract. No penalty clauses, no measurement methodology, no reporting cadence.

## O5. Partner channel readiness

### O5.1 Partner reference app — sole channel artifact

Per Gate 8 §J3: `examples/partner-reference-app/` is the **only** partner-facing artifact. It implements:

- Server-side OAuth client_credentials exchange
- iframe widget bootstrap
- Real DeepSeek run (Phase 7 Gate 12 verified)

### O5.2 Partner ecosystem — empty

- ❌ No partner program documentation
- ❌ No ISV onboarding process (separate from hospital intake)
- ❌ No revenue-share / referral model
- ❌ No partner-tier pricing
- ❌ No co-marketing materials
- ❌ No partner portal (beyond the Console API Clients page)

Register as **G13-005 (P1)**: partner channel is reference-app-only. No partner program, no ISV contract template, no revenue model.

### O5.3 SDK on npm — not published

Per Gate 8 §J1.3: `@icoder/sdk` and `@icoder/embedded` both return 404 from `registry.npmjs.org`. Partners cannot `npm install` them; they must either clone the monorepo or use the dist-serve widget. This blocks organic partner adoption.

## O6. Sales readiness

### O6.1 Demo capability

Per Phase 7 Gate 10: 3 demos (medical-coding / CDI / DRG-DIP) verified in Playwright MCP against real DeepSeek. Each surfaces signed trace_url. These are real, repeatable demos.

### O6.2 Pilot Runbook

Search for `Runbook` / `pilot` documents:

```
docs/archive/phase_history/PHASE11D_PILOT_EVALUATION_RUNBOOK.md
docs/archive/phase_history/PILOT_ISSUE_TEMPLATE.md
docs/archive/corti_analysis_2026_05/CORTI_STYLE_REMEDIATION_ROADMAP.md (mentions Pilot Runbook)
```

The Pilot Runbook exists but is **archived** under `docs/archive/phase_history/`. It's not on the mainline doc path. A sales team pointing a hospital CIO at the repo would not find it.

### O6.3 Pricing for sales conversations

```
Q: "How much does iCoDer cost per month?"
A: (undefined)

Q: "What's the difference between pilot and production pricing?"
A: (undefined)

Q: "Do you offer a free trial?"
A: (undefined — but free credits are infinite)

Q: "What's the enterprise contract length?"
A: (undefined)
```

Register as **G13-006 (P1)**: no commercial package. No published pricing, no tier definitions, no contract templates. A sales conversation cannot close without these.

## O7. Hospital deployment path — non-existent

### O7.1 The deployment story problem

CLAUDE.md says: "托管云 SaaS" (managed cloud SaaS). Cloud Deployment doc says: Phase 1 = docs only. Per Gate 11 §L3.3, 6 critical cloud features are unimplemented:

1. ❌ Region routing (LLM / data policy)
2. ❌ Billing (Stripe)
3. ❌ Multi-region failover
4. ❌ Edge-node PHI redaction
5. ❌ Platform API stubs (5 endpoints return 501)
6. ❌ Org-scoped team management

### O7.2 The on-premise alternative — explicitly disclaimed

CLAUDE.md:

> **不再**支持医院内网 Docker 部署。Runtime 是 iCoDer Server 的内核执行引擎(不是独立的便携 Runtime)。

So:
- Cloud SaaS: docs-only, 6 critical features unimplemented
- On-premise: explicitly disclaimed

→ **There is no shippable deployment path.** A hospital signing a contract today cannot deploy iCoDer in any form.

Register as **G13-007 (P0)**: zero shippable deployment paths. Cloud SaaS is docs-only; on-premise is explicitly disclaimed. Even if a hospital signed a pilot contract, there is no engineering plan to deliver the software to them within a defined timeframe.

## O8. Support capability

### O8.1 Support channels (from `SupportPage.tsx`)

| Channel | Status |
|---------|--------|
| Documentation (`/docs`) | ✅ Live |
| Tickets (`/tickets`) | ✅ Live (page exists) |
| Live chat | ⚠️ Routes to `/tickets` (not separate channel) |
| Email (`support@icoder.local`) | ⚠️ Fake domain (.local) |

The email link uses `support@icoder.local` — a fake domain that cannot receive mail. Register as **G13-008 (P2)**: support email is non-functional placeholder.

### O8.2 SLA-breach response

Per O4.2: SLA targets are documented but no on-call runbook (G11-005), no incident response playbook, no escalation matrix. Even if a hospital knew to file a ticket, there is no documented process for resolving it within SLA.

## O9. Competitive commercial positioning vs Corti

### O9.1 Corti's commercial surface (per public docs)

- ✅ Published pricing (Corti.ai/pricing)
- ✅ Stripe + invoice billing
- ✅ Tiered plans (Team / Enterprise)
- ✅ Signed customer contracts (European hospitals)
- ✅ Production deployment in 4+ regions
- ✅ ISO 27001 / GDPR compliance
- ✅ DPA template published
- ✅ 24/7 support SLA

### O9.2 iCoDer's commercial surface

- ❌ No pricing (free infinite credits)
- ❌ No payment processor
- ❌ No tier plans
- ❌ 0 signed customers
- ❌ No production deployment
- ❌ No compliance certifications
- ❌ No DPA, no SLA contract
- ❌ No on-call runbook

→ **iCoDer is not commercially viable in its current state.** The product is at the "free internal tool" stage, not the "sellable hospital SaaS" stage.

## O10. New findings

| ID | Severity | Domain | Title |
|----|----------|--------|-------|
| **G13-001** | P0 | billing-theater | `/api/billing/credits` endpoint adds free credits with no payment processor wired. **0 transactions ever recorded** despite 240 agent runs consuming ¥0.049 LLM cost. `/billing` page shows fake ¥50.00 balance + ¥0.00 consumed. No Stripe, no Alipay, no WeChat Pay. |
| **G13-002** | P0 | no-certifications | Zero compliance certifications obtained. 等保2.0 三级 + GB/T 35273-2020 + HIPAA + ISO 27001 all unobtained. Code actively fails technical controls (G9-005 encryption, G9-002 audit log, G9-006 password complexity). Cannot be sold to any Chinese public hospital. |
| **G13-003** | P0 | no-legal-docs | Zero legal documents. No Privacy Policy, no Terms of Service, no DPA, no SLA contract. Login page links to `/support` for both "隐私政策" and "服务条款" — both redirect to a generic help page. Mandatory for any hospital contract signature. |
| **G13-004** | P0 | no-deployment-path | Zero shippable deployment paths. Cloud SaaS is docs-only (6 critical features unimplemented per G11-001). On-premise explicitly disclaimed in CLAUDE.md. A hospital signing today cannot deploy iCoDer in any form. |
| **G13-005** | P1 | pilot-never-exercised | Intake template (`CLOUD_INTAKE_TEMPLATE.md`) is methodologically sound but has never been submitted by a real customer. 0 real hospital tenants; 42 orgs in DB all test/audit artifacts. |
| **G13-006** | P1 | no-pricing | No pricing model. No tiers, no plans, no per-case or per-token pricing, no contract templates. Sales conversations cannot close. |
| **G13-007** | P1 | no-partner-program | Partner channel is reference-app-only. No partner program, no ISV contract template, no revenue-share model, no co-marketing materials. SDK not on npm (G8-001) blocks organic adoption. |
| G13-008 | P2 | support-placeholder | Support email `support@icoder.local` is non-functional fake domain. Tickets page exists but no on-call runbook (G11-005). |
| G13-009 | P2 | pilot-runbook-archived | Pilot Runbook + Issue Template exist but archived under `docs/archive/phase_history/`. Not on the mainline doc path; sales teams will not find them. |
| G13-010 | P3 | sla-targets-only | SLA targets documented in CLOUD_DEPLOYMENT.md but no signed SLA contract, no penalty clauses, no measurement methodology, no reporting cadence. |

## O11. Track-level verdicts (interim)

| Sub-track | Verdict |
|-----------|---------|
| **O1 Commercial billing** | `THEATER_0_TRANSACTIONS_NO_PAYMENT_PROCESSOR` — Free infinite credits, no real money flow |
| **O2 Pilot intake** | `DOCUMENTED_NEVER_EXERCISED` — Sound template, 0 real submissions |
| **O3 Compliance** | `ZERO_CERTIFICATIONS_CODE_FAILS_TECHNICAL_CONTROLS` — 等保/GB-T-35273/HIPAA/ISO all unobtained |
| **O4 Legal** | `ZERO_LEGAL_DOCS_LOGIN_PRETENDS_TO_LINK` — No privacy/terms/DPA/SLA documents exist |
| **O5 Partner channel** | `REFERENCE_APP_ONLY_NO_PROGRAM` — 1 demo app, no partner program |
| **O6 Sales** | `3_DEMOS_REAL_BUT_NO_PRICING_NO_CONTRACTS` — Demos work; nothing else sales-ready |
| **O7 Deployment** | `ZERO_SHIPPABLE_PATHS` — Cloud docs-only, on-prem disclaimed |
| **O8 Support** | `TICKETS_EXIST_BUT_NO_RUNBOOK_FAKE_EMAIL` — Surface real; ops missing |

## O12. Gate 13 verdict

`NOT_COMMERCially_VIABLE_NO_CERTIFICATIONS_NO_LEGAL_DOCS_NO_DEPLOYMENT_PATH`

Specifically:

- ❌ **G13-001 P0**: billing is theater (0 transactions, no payment processor, fake ¥50 balance)
- ❌ **G13-002 P0**: zero compliance certifications; code actively fails 等保2.0 technical controls
- ❌ **G13-003 P0**: zero legal documents; login pretends to link but redirects to generic support
- ❌ **G13-004 P0**: zero shippable deployment paths (cloud docs-only, on-prem disclaimed)
- ❌ Hospital pilot intake never exercised; 0 real tenants
- ❌ No pricing model, no partner program, no SLA contract
- ⚠️ 3 demos (medical-coding / CDI / DRG-DIP) work against real DeepSeek
- ⚠️ Pilot Runbook + Issue Template exist but archived
- ⚠️ Support tickets page exists but no runbook

**Bottom line**: iCoDer is at the "internal R&D project" stage of commercial maturity, not the "hospital-pilot-ready" stage. Even if a hospital CIO wanted to sign a pilot contract tomorrow, the legal, compliance, deployment, and billing infrastructure does not exist to close the deal.

Gate 13 closes. Proceed to **Gate 14 — Issue Grading, Roadmap and Final Verdict**.
