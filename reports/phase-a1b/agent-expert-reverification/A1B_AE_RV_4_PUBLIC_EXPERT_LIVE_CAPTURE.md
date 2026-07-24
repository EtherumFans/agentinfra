# A1B-AE-RV.4 — Public Expert Live Capture (PubMed + ClinicalTrials)

**Sub-gate**: RV.4
**Date**: 2026-07-24
**Predecessor**: RV.3 `4b2fc8a`
**Worktree**: `E:/Corti4C-agent-expert-reverification`
**Branch**: `phase-a1b/agent-expert-terminal-reverification` (local-only)

## Purpose

RV.0 charter §九 / §10 require that PubMed and ClinicalTrials Experts each complete **at least one real synthetic live query** (no VCR replay). This sub-gate produces that evidence and confirms the VCR replay shape matches the live shape.

## Pre-flight environment check

```
curl -sI https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi → 200 in 1.96s
curl -sI https://clinicaltrials.gov/api/v2/studies              → 200 in 1.32s
```

Both endpoints reachable from this host. No hard blocker triggered.

## Live capture summary

| Expert | Query | Status | Returned | Body SHA-256 (canonical JSON) | VCR fixture seeded |
|--------|-------|--------|----------|-------------------------------|---------------------|
| pubmed | `RV4MARKER diabetes type 2 cohort synthetic` | OK | 5 articles | (per-envelope, see evidence file) | ✅ `pubmed_86317b41896bead5.json` |
| clinical-trials | `hypertension` | OK | 5 trials (total=19773) | (per-envelope, see evidence file) | ✅ `clinical_trials_97cf39b495a535aa.json` |

Both captures flowed through the canonical expert API:

```python
await search_async(
    query,
    max_results=5,
    egress_enabled=True,
    region="EU",
    allow_live_capture=True,  # ← the ONLY place this flag is set in audit
)
```

The expert's gate check (`external_expert_gate.evaluate`) permitted both calls (pubmed/clinical-trials require only `egress_enabled=True` + region ∈ {CN, EU, US}; no licence token needed). The SSRF guard (`assert_url_safe`) passed on every URL.

## VCR replay vs live shape

Replay (without `allow_live_capture`, no network) was verified to return the fixture:

| Expert | Live article/trial keys | Replay article/trial keys | Shape match |
|--------|-------------------------|---------------------------|-------------|
| pubmed | `{pmid, title, journal, year, authors}` | `{pmid, title, journal, year, authors}` | ✅ exact |
| clinical-trials | `{nct_id, title, status, phase}` | `{nct_id, title, status, phase}` | ✅ exact |

Replay notes string includes the literal `"VCR fixture replay"` marker — UI surfaces can show RECORDED_FIXTURE vs LIVE_CAPTURE based on that string. Live capture notes string includes `"live capture (fixture saved)"`.

## Marker isolation

The PubMed query contains the synthetic marker `RV4MARKER` (so post-capture scans can find the synthetic row). The fixture must NOT echo the marker into any article title / journal / author. `test_rv4_marker_does_not_leak_into_fixture` asserts:

```
assert "RV4MARKER" not in pm_blob.replace(pm["query"], "")
```

PubMed returned real medical articles (diabetes cohort studies from 2026); none of the article fields contain the marker. The CT query is marker-free.

## Changes applied

### New artifacts

| Path | Purpose |
|------|---------|
| `scripts/rv4_live_capture.py` | Live capture runner. Performs DNS+TLS pre-flight, real EUtils + CT.gov v2 calls, saves request/response/timing/SHA-256 to evidence dir. |
| `reports/phase-a1b/agent-expert-reverification/evidence/public-expert-live/PUBMED_LIVE_CAPTURE.json` | PubMed live envelope (query, URLs, status codes, latency, body SHA-256, articles, fixture comparison). |
| `reports/phase-a1b/agent-expert-reverification/evidence/public-expert-live/CLINICAL_TRIALS_LIVE_CAPTURE.json` | ClinicalTrials live envelope (same shape). |
| `reports/phase-a1b/agent-expert-reverification/evidence/public-expert-live/MANIFEST.json` | Combined manifest (host, Python version, capture timestamps, both captures' status + counts). |
| `reports/phase-a1b-runtime/evidence/api_captures/pubmed_86317b41896bead5.json` | VCR fixture seeded by `search_async(allow_live_capture=True)`. |
| `reports/phase-a1b-runtime/evidence/api_captures/clinical_trials_97cf39b495a535aa.json` | VCR fixture seeded. |

### New tests (16 total)

`backend/tests/test_api/test_a1b_ae_rv_4_public_expert_live_capture.py`:

| § | Test | Closes |
|---|------|--------|
| 1 | `test_rv4_1_pubmed_live_envelope_present` | Live evidence file exists |
| 2 | `test_rv4_2_clinical_trials_live_envelope_present` | Live evidence file exists |
| 3 | `test_rv4_3_pubmed_envelope_tagged_live_capture` | LIVE_CAPTURE marker |
| 3b | `test_rv4_3b_clinical_trials_envelope_tagged_live_capture` | LIVE_CAPTURE marker |
| 4 | `test_rv4_4_pubmed_live_status_ok` | No BLOCKED_BY_* |
| 4b | `test_rv4_4b_clinical_trials_live_status_ok` | No BLOCKED_BY_* |
| 5 | `test_rv4_5_pubmed_live_returned_articles` | Real articles |
| 5b | `test_rv4_5b_clinical_trials_live_returned_trials` | Real trials |
| 6 | `test_rv4_6_pubmed_vcr_fixture_seeded` | VCR fixture written |
| 6b | `test_rv4_6b_clinical_trials_vcr_fixture_seeded` | VCR fixture written |
| 7 | `test_rv4_7_pubmed_replay_returns_fixture_without_network` | Replay path works |
| 7b | `test_rv4_7b_clinical_trials_replay_returns_fixture_without_network` | Replay path works |
| 8 | `test_rv4_8_replay_shape_matches_live_shape_pubmed` | No shape drift |
| 8b | `test_rv4_8b_replay_shape_matches_live_shape_clinical_trials` | No shape drift |
| 10 | `test_rv4_10_manifest_present` | Combined manifest exists |
| — | `test_rv4_marker_does_not_leak_into_fixture` | Synthetic marker isolation |

All 16 tests pass in 3.45s. The existing `test_a1b_ae_6_external_experts.py` suite (17 tests) still passes (no regression — fixture seeding is additive).

## Acceptance conditions satisfied

- ✅ PubMed live capture completed (real EUtils call, real PMIDs returned)
- ✅ ClinicalTrials live capture completed (real CT.gov v2 call, real NCT IDs returned)
- ✅ Live capture tagged `LIVE_CAPTURE` (not `RECORDED_FIXTURE`)
- ✅ VCR replay tagged `RECORDED_FIXTURE` (not `LIVE_CAPTURE`)
- ✅ Shape match (live vs replay drift = 0 fields)
- ✅ Synthetic marker isolated to query envelope; no bleed into fixture payload
- ✅ SSRF guard exercised on every live URL
- ✅ External-expert Gate exercised (permitted pubmed + clinical-trials with egress_enabled + region)
- ✅ DNS + TLS pre-flight probe recorded (distinguishes BLOCKED_BY_NETWORK from API errors)
- ✅ No regression in `test_a1b_ae_6_external_experts.py`

## Acceptance conditions NOT satisfied at RV.4

- ⏳ True headed-browser Journey 3 verifies PubMed + ClinicalTrials citations in the UI — deferred to RV.5
- ⏳ Full BACKEND_ALL_TESTS regression — deferred to RV.6

## Forbidden ops check

- ✅ No push, no PR, no deploy
- ✅ No amend of `8546184` or ancestors
- ✅ No real patient data (queries are synthetic medical terms + marker)
- ✅ No weakening of JWT, tenant, encryption, redaction, or egress
- ✅ `allow_live_capture=True` only set in (a) the live-capture script, (b) the inline live seed used for fixture creation. Production runtime paths unchanged.

## R-CLAIM resolution

| R-CLAIM | Status after RV.4 |
|---------|-------------------|
| R-CLAIM-07 (PubMed / ClinicalTrials live capture NOT proven → proven) | **CORRECTED → NOW TRUE** — Both experts performed real live EUtils + CT.gov v2 calls; VCR fixtures seeded with the response; replay path verified to return fixtures. |
| R-CLAIM-03 (Public Expert live integration verified) | **STILL TRUE** — Re-verified at the live-capture layer. |

## Verdict

```
PASS_A1B_AE_RV_4_PUBLIC_EXPERT_LIVE_CAPTURE_AND_VCR_REPLAY_PARITY_FILED
```

Next: RV.5 — True headed-browser Playwright E2E (10 journeys × 3 runs).
