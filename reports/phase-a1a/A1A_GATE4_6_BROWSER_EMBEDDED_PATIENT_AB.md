# Phase A1A Gate 4.6 — Browser + Embedded + Patient A/B Verification

**Date**: 2026-07-20
**Branch**: `phase-a1a/emergency-containment`
**Predecessor**: Gate 4.5 (`A1A_GATE4_5_PROVIDER_EGRESS_REGIONAL_RESIDENCY.md`)
**Successor**: Gate 4.7 (Retention + deletion + audit closure)

Charter §4.6: close the browser-storage PHI boundary flagged in Gate 4.0
§6 item 25. Pre-Gate-4.6 logout only cleared `access_token` and
`refresh_token`, leaving `icoder-textgen-templates` (user-saved templates
that may contain pasted PHI), `icoder-billing-*`, `icoder-settings`,
`icoder-theme`, and the zustand-persisted `icoder-auth` blob on disk.
On a shared hospital workstation a subsequent different user could inherit
the previous user's templates and UI preferences.

---

## §1. Browser storage registry

`frontend/src/store/index.ts` is now the source of truth for every
localStorage key the frontend writes. `ICODER_LOCALSTORAGE_KEYS`
enumerates the canonical 10 keys:

| # | Key | Purpose |
|---|---|---|
| 1 | `access_token` | JWT access token |
| 2 | `refresh_token` | JWT refresh token |
| 3 | `icoder-auth` | zustand `persist` blob (user, orgs, currentOrgId, tokens) |
| 4 | `icoder-textgen-templates` | user-saved Medical Coding prompt templates (may carry pasted PHI) |
| 5 | `icoder-project-name` | last-used project name |
| 6 | `icoder-billing-alerts` | low-balance alert threshold |
| 7 | `icoder-billing-autotopup` | auto-topup toggle + amount |
| 8 | `icoder-settings` | UI preferences |
| 9 | `icoder-agent-runtime-mode` | runtime mode selector |
| 10 | `icoder-theme` | light/dark theme |

`clearAllIcoderBrowserStorage()` iterates the registry and removes each
key inside a try/catch (so one missing key does not abort the wipe).
`listIcoderBrowserStorageKeys()` is the inverse: returns which keys
are currently set (used by the diagnostic UI).

---

## §2. `logout` action calls the helper

Pre-Gate-4.6 logout:

```ts
logout: () => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  set({ user: null, ... });
}
```

Gate 4.6 logout:

```ts
logout: () => {
  clearAllIcoderBrowserStorage();
  set({ user: null, ... });
}
```

The two-lines-less, two-keys-more behaviour closes the shared-workstation
inheritance gap. The `set()` call still runs after the wipe to flush
in-memory React state.

---

## §3. Patient Context Isolation — static re-confirmation

Phase 7 Gate 11 Playwright-verified the runtime behaviour of Patient
Context Isolation. Gate 4.6 does NOT re-run the browser walkthrough
because Gate 4.6's storage cleanup is orthogonal to the patient-context
events: Gate 4.6 wipes *login* storage (auth + preferences + templates)
on explicit logout; Patient Context Isolation wipes *session-scoped*
patient state on every patient switch or session end (via the
`patient.context.cleared` / `session.cleared` events emitted from
`packages/icoder-embedded/src/icoder-assistant.ts`).

Gate 4.6 re-confirms the static contract:

- `EmbeddedAssistantPage.tsx` carries the "no PHI in parent JS memory"
  comment (parent-side ticket is in-memory only, never localStorage).
- The icoder-embedded widget still emits `patient.context.cleared` and
  `session.cleared` events (Phase 6 / Phase 7 Gate 11 contract intact).

---

## §4. Demo HTML — no embedded PHI

`examples/partner-reference-app/public/index.html` is the single
shipped demo HTML. Two regex sweeps assert it does not embed PHI-shaped
literals:

- `\b\d{17}[\dXx]\b` — Chinese resident ID card (18 digits ending in
  digit or X)
- `\b1[3-9]\d{9}\b` — Chinese mobile phone (11 digits starting with 1X)

Both match → test fails → developer must replace with placeholder
(`YOUR_PATIENT_ID`, `YOUR_PATIENT_NAME`, `YOUR_ENCOUNTER_ID`).

The Medical Coding / CDI / DRG-DIP demos are Flask-served templates
populated at request time, so they cannot embed PHI in source.

---

## §5. Tests

`backend/tests/test_api/test_a1a_gate4_6_browser_storage_audit.py`
(6 tests):

| § | Test | Verifies |
|---|---|---|
| 1.1 | `test_clear_helper_is_defined_and_exported` | `store/index.ts` exports `clearAllIcoderBrowserStorage` and declares `ICODER_LOCALSTORAGE_KEYS` |
| 1.2 | `test_logout_calls_clear_helper` | The `logout` action body contains `clearAllIcoderBrowserStorage()` |
| 2.1 | `test_every_localstorage_key_is_in_registry` | Grep-walks every `localStorage.setItem('X', …)` in `frontend/src` and asserts X appears in the registry |
| 3.1 | `test_embedded_assistant_page_declares_no_phi_in_parent_memory` | `EmbeddedAssistantPage.tsx` carries the "parent JS memory only" + "localStorage" contract comment |
| 3.2 | `test_clear_patient_context_events_emitted` | The icoder-embedded widget still references `patient.context.cleared` or `session.cleared` |
| 4.1 | `test_partner_reference_app_has_no_embedded_phi` | `examples/partner-reference-app/public/index.html` has no ID-card-shaped or mobile-phone-shaped literals |

Test report: `6 passed in 1.57s`.

---

## §6. Files touched

### Code

| File | Change |
|---|---|
| `frontend/src/store/index.ts` | New `ICODER_LOCALSTORAGE_KEYS` registry (10 keys); new `clearAllIcoderBrowserStorage()` + `listIcoderBrowserStorageKeys()` exports; `logout` now calls `clearAllIcoderBrowserStorage()` instead of removing only two keys; added `icoder-theme` to registry |

### Tests

| File | Change |
|---|---|
| `backend/tests/test_api/test_a1a_gate4_6_browser_storage_audit.py` | **NEW**. 6 tests. |

### Docs

| File | Change |
|---|---|
| `reports/phase-a1a/A1A_GATE4_6_BROWSER_EMBEDDED_PATIENT_AB.md` | This closure report. |

---

## §7. Forbidden list — re-confirmation

Gate 4.6 did NOT:

- Modify any Medical Coding / CDI / DRG-DIP prompt
- Touch real patient data
- Push, PR, master commit, amend `b737eab`
- Use `git add -A`
- Issue any charter §22 forbidden verdict
- Re-run the Phase 7 Gate 11 Playwright walkthrough (the storage
  cleanup is orthogonal to the patient-context event contract)
- Introduce new localStorage keys without adding them to the registry
  (the test in §2.1 enforces this invariant going forward)

---

## §8. Provisional verdict

```
PASS_A1A_GATE4_6_BROWSER_EMBEDDED_PATIENT_AB_VERIFIED
```

T-CC-11 (browser-storage PHI retention on shared workstations) closed.
A subsequent different user on the same browser cannot inherit the
previous user's auth, templates, billing prefs, or UI prefs.

---

## §9. Next

Gate 4.7 — Retention + deletion + audit closure.
