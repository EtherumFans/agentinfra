# Corti Medical Coding — Verified ICD-10 Variants (Console)

> Source: `https://console.corti.app/project/4c4193c7-.../ai-studio/medical-coding` → Coding systems dropdown (open)
> Access date: 2026-07-16. Evidence: `07_medical_coding_variants.png`.

## Authoritative count: **9 ICD-10 variants** (not 5 as docs claimed)

The Corti docs page `experts/overview` lists "5 ICD-10 variants" (CM, WHO, PCS, UK, General). The Console dropdown shows 9 because each variant splits by **setting** (Inpatient vs Outpatient), and there is an additional German Modification (ICD-10-GM) not mentioned in the docs.

### Verified dropdown options

| # | Corti Variant Name | Standard | Setting | Region |
|---|--------------------|----------|---------|--------|
| 1 | ICD-10-CM Outpatient | ICD-10-CM (Clinical Modification) | Outpatient | US |
| 2 | ICD-10-CM Inpatient | ICD-10-CM | Inpatient | US |
| 3 | ICD-10-PCS | ICD-10-PCS (Procedure Coding System) | Procedure | US |
| 4 | ICD-10 Intl. Inpatient | ICD-10-WHO (International) | Inpatient | Global |
| 5 | ICD-10 Intl. Outpatient | ICD-10-WHO | Outpatient | Global |
| 6 | ICD-10-UK Inpatient | ICD-10-UK (NHS adaptation) | Inpatient | UK |
| 7 | ICD-10-UK Outpatient | ICD-10-UK | Outpatient | UK |
| 8 | ICD-10-GM Inpatient | ICD-10-GM (German Modification) | Inpatient | DE / EU |
| 9 | ICD-10-GM Outpatient | ICD-10-GM | Outpatient | DE / EU |

### What's NOT in the list

- ❌ **ICD-10-CN (Chinese National Clinical Modification)** — confirmed absent
- ❌ ICD-10-CM (no plain "General" variant in dropdown — docs mention "General" but Console has setting-specific variants instead)
- ❌ ICD-11 (WHO next-gen) — not yet exposed
- ❌ CPT / HCPCS codes — not in this surface (may be in a different tool)

## Implications for iCoDer parity

This is a **two-sided finding**:

### Corti advantage (9 vs 1)
- Corti covers US (CM+PCS), UK, WHO Intl, and German variants — 4 regulatory regions × inpatient/outpatient split
- iCoDer's MedCodER only handles ICD-10-CN (Chinese Clinical Modification)
- For a EU/US partner, Corti has 9× the geographic coverage

### iCoDer advantage (1 vs 0)
- Corti has **no ICD-10-CN support** at all
- iCoDer has 37,897 ICD-10-CN codes + 75,968 synonyms + 2,090 differentiation pairs + 972 evidence anchors (per CLAUDE.md §MedCodER)
- For any Chinese hospital pilot, Corti cannot serve the use case at all — iCoDer is the **only option**

### Parity classification (per spec §13.2)

- ICD-10-CM/PCS/UK/WHO/GM (8 variants) → `DIFFERENT_BY_DESIGN` (iCoDer targets CN market only; out-of-current-scope for hospital pilot product)
- ICD-10-CN → `ICODER_ADVANTAGE` (Corti has zero coverage here; iCoDer has the entire CN standard)
- The docs page "5 variants" understates reality → fix the parity matrix V2 to use the Console-verified **9 variants** count

## Console medical coding page layout

- Top: API Client selector + $0.000000 live cost
- Coding system dropdown (described above)
- Left pane: Input + Samples (3 templates: Hospital medical record, GP transcript, Orthopedic referral letter; plus Guided demo)
- Right pane: Output + Event Inspector + Credits consumed
- Action button: "Predict codes" + "Config" (settings)

## Config / Settings

The "Config" button was not exercised in this audit (would modify the user's working config). Per Corti docs, the medical coding config includes:
- Coding system variant (dropdown above)
- Include rationale (boolean)
- Max candidates per code (int)
- Confidence threshold (float)

## iCoDer-side mirror

iCoDer's MedicalCodingPage (`frontend/src/pages/MedicalCodingPage.tsx`) has:
- 1 coding system (ICD-10-CN only)
- MedCodER 5-stage pipeline toggle
- Diagnosis cards with TopK chips
- Same input → predict → output → trace IA

Missing vs Corti Console:
- ❌ No coding-system variant dropdown (only CN)
- ❌ No 3-template sample picker (iCoDer has its own demo cases)
- ❌ No "Guided demo" interactive walkthrough
- ✅ Has Event Inspector equivalent (Gate 9 SSE + Run Trace page)
- ✅ Has Credits consumed indicator (Phase 4-G TopBar)

## Pre-A0 Gate 7 (Parity Matrix V2) update

The V1 parity matrix scored "Medical Coding" as `PARITY` based on "both have medical coding". V2 must split this dimension:

- **ICD-10-CN coverage**: iCoDer ✅ / Corti ❌ → ICODER_ADVANTAGE
- **ICD-10-CM/PCS coverage**: iCoDer ❌ / Corti ✅ → CORTI_ADVANTAGE
- **ICD-10-WHO/UK/GM coverage**: iCoDer ❌ / Corti ✅ → CORTI_ADVANTAGE (but DIFFERENT_BY_DESIGN for CN-only product)
- **Inpatient/Outpatient split**: iCoDer implicit (CN doesn't split the same way) / Corti ✅ → DIFFERENT_BY_DESIGN

Net: For Chinese hospital pilot scope, iCoDer's ICD-10-CN coverage is the relevant dimension, and it remains ICODER_ADVANTAGE. The other 8 variants are out-of-current-scope per CLAUDE.md §产品定位.
