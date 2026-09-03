# Corti Usage + Billing — Verified Commercial Surface (Console)

> Source: `https://console.corti.app/project/4c4193c7-.../usage` + `/billing`
> Access date: 2026-07-16. Evidence: `09_usage.png` + `10_billing.png`.

## Usage page — verified

### Layout
- Header: "Usage — View credit consumption over time for your project, break down by API client and compare with previous periods"
- Compare period checkbox + Last 30 days selector + All API clients filter
- Available credits: **$37.52** with "Add credits" CTA
- Total credits consumed: **$6.84**
- Daily bar chart (16-Jun → 16-Jul, 30 days)
- Y-axis $0-$4

### Verified dimensions

- Time window: Last 7 / 30 days etc (selector present)
- Group by: API client (default = All)
- Metric: Credits consumed (USD)
- Compare period: toggle on/off (overlay previous period)

This matches iCoDer Phase 5 A2 / Phase 7 Gate 8 dimensions. iCoDer has additional dimensions (agent_id, runtime_mode, by-agent breakdown) that Corti's Usage page does NOT surface in this layout.

## Billing page — verified

### 3 tabs: Plan | Billing History | Business info

### Plan tab — "Pay-as-you-go"

```
Pay-as-you-go plan
Consume credits from a pre-paid balance

Credits
  Balance            $37.52
  Add credits        [button]
  Last updated       16-Jul-2026, 11:06:06

Alerts and auto-top-up
  Enable low balance alerts
    Receive email notifications when your balance is low
    Send alert when balance falls below [ $10 ]  [Update]
  Enable auto top-up
    Automatically add credits when your balance gets low

Payment methods
  No payment methods yet
  [Add a payment method]
```

## Critical parity finding

**Corti has REAL billing infrastructure. iCoDer has billing theater.**

| Capability | Corti (verified) | iCoDer (per Gate 13) |
|------------|------------------|----------------------|
| Plan model | Pay-as-you-go (named plan) | None — "click button → +¥50 free credits" |
| Pre-paid balance | ✅ Real, $37.52 with timestamp | ❌ Fake ¥50.00, no transaction ever recorded |
| Low balance alerts | ✅ Email notifications + threshold | ❌ None |
| Auto top-up | ✅ Toggle + amount config | ❌ None |
| Payment methods | ✅ "Add a payment method" UI | ❌ None — no Stripe / Alipay / WeChat Pay |
| Billing history | ✅ Dedicated tab | ❌ Transaction table exists but 0 rows |
| Business info | ✅ Dedicated tab (tax ID, billing address) | ❌ None |
| Currency | USD ($37.52) | CNY (¥50.00 fake) |

This **directly confirms Gate 13 G13-001 finding** that iCoDer's billing is theater. Corti's commercial surface is real and production-grade.

## Implications for Pre-A0

- Corti-side evidence now CONFIRMED for billing parity comparison (previously was inferred from docs only).
- iCoDer's gap is real and verified. No change to Gate 13 P0 severity.
- For Pre-A0 Gate 7 (Parity Matrix V2): Corti's commercial dimension = `CORTI_ADVANTAGE` (unchanged from V1, now with Console-grade evidence).
- For Pre-A0 Gate 9 (canonical architecture): Corti's commercial model = `pay-as-you-go + pre-paid + auto-topup + payment-processor`. iCoDer's roadmap must include payment processor integration (Stripe for EU/US, Alipay/WeChat Pay for CN) to close this gap.

## "Add credits" path not exercised

The "Add credits" button was clicked but the resulting modal/flow was not captured in this audit (would require real payment method). Verified evidence:
- Button is present and enabled
- Below it: "Payment methods — Add a payment method" (separate flow)
- "Auto top-up" toggle exists (not yet enabled for this user)

If a later session captures the Add Credits modal (likely Stripe Elements or similar), update this evidence file with the payment processor identity.

## Currency observation

Corti Console shows USD ($) throughout. This contrasts with iCoDer's CNY (¥) standard per CLAUDE.md §货币约定. For multi-region Corti, this likely varies by Environment (eu/us/cn); only EU region is verified here and it shows USD (not EUR). Possible explanations:
- Corti's EU region still charges in USD (developer-friendly for ISVs)
- User's account is configured for USD billing
- EU/UK customers get EUR/GBP billing in their respective scopes

iCoDer's CNY-only model is correct for the CN market but lacks the multi-currency flexibility Corti may have. Not a parity blocker (DIFFERENT_BY_DESIGN for CN-focused product).
