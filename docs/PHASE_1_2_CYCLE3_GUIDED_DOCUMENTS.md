# Phase 1.2 Cycle 3 — Guided Documents (REST Beta) — templateRef + ephemeral path

## Context

Phase 1.2 cycle 1 (`b7bf0aa`) shipped FactsR™ (stateless REST extraction).
Phase 1.2 cycle 2 (`e398c31`) shipped Streams WSS.
Cycle 3 closes **the simplest path of §13.4 Guided Documents** so iCoDer
can offer a Corti-SDK-compatible structured-document generator without
taking on the full CRUD surface (Sections, Templates, Documents Classic)
in one go.

Corti §13.4 declares `POST /documents/` with three template-supply paths
(`templateRef`, `assemblyTemplate`, `dynamicTemplate`) and two retention
modes (`X-Corti-Retention-Policy: none` → 200 ephemeral, omitted → 201
saved auto-generated template aggregate, persisted 30d).

**Cycle 3 scope (intentionally narrow):**

| In scope | Out of scope (explicit, future cycle) |
|---|---|
| `templateRef` (no overrides) supply path | `assemblyTemplate` and `dynamicTemplate` (422'd) |
| `X-Corti-Retention-Policy: none` → 200 ephemeral | Omitted header → 201 saved (422'd) |
| `context[].type == "text"` flattening | transcript / facts context variants |
| `interactionId`-less path | interaction-aware context (422'd) |
| Single-shot REST POST | WSS / streaming variant |

Everything else (Sections / Templates / Documents Classic CRUD) belongs
to Cycles 4 and 5 per the parity queue.

## Spec source

`docs/corti-reverse-engineered/guided-documents-generate.md` (35,728 bytes,
fetched 2026-06-30 from
`https://docs.corti.ai/api-reference/guided-documents/generate-a-structured-document.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_3_guided_doc/corti-guided-generate.md`.

## Endpoint surface

```
POST /api/v2/tools/guided-documents/      (and /guided-documents trailing-slash-less alias)
Authorization: Bearer <jwt or oauth>      (Phase 1.0 capability scope path)
X-Corti-Retention-Policy: none            (Cycle 3 only accepted value)
Content-Type: application/json

{
  "outputLanguage": "en-US",
  "templateRef": { "templateId": "...uuid...", "templateVersionId": "...uuid..." | null },
  "context": [ { "type": "text", "text": "..." } ],       // at least one of context / interactionId
  "interactionId": null,
  "labels": [ { "key": "...", "value": "..." } ]
}

→ 200 OK   { document: {name,templateId,templateVersionId,language,interactionId?,
                         stringDocument,structuredDocument?,labels[]},
             usageInfo: {creditsConsumed} }

→ 422  ErrorResponse with Corti `requestid/status/type/detail[/validationErrors]`
       types: unsupported_retention_policy | missing_context | empty_context |
              interaction_unsupported
→ 503  ErrorResponse type=service_unavailable   (hospital-pilot gate)
→ 500  ErrorResponse type=internal_error         (LLM failure)
```

## Files

| Path | Lines | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_guided_document.py` | ~165 | Pydantic models for the minimal path |
| `backend/app/api/v2_tools_guided_document.py` | ~225 | REST router + LLM projection |
| `backend/tests/test_api/test_v2_guided_document_consistency.py` | ~310 | 6 回环一致性测试 |
| `backend/app/main.py` | +2 lines | import + include router |
| `docs/corti-reverse-engineered/guided-documents-generate.md` | 35,728B | captured spec |
| `docs/PHASE_1_2_CYCLE3_GUIDED_DOCUMENTS.md` | this file | spec doc |
| `docs/phase_cycles/cycle_3_guided_doc/` | REPORT.md + spec archive | per-cycle archive |

## Field projection (iCoDer Runtime → Corti envelope)

| Corti field | Source (iCoDer) |
|---|---|
| `document.name` | `f"guided-{templateId}-{uuid4().hex[:8]}"` (deterministic per request) |
| `document.templateId` | echo `body.templateRef.templateId` |
| `document.templateVersionId` | echo caller value, else `00000000-...` (sentinel = "published") |
| `document.language` | echo `body.outputLanguage` |
| `document.interactionId` | echo `body.interactionId` (null when caller omitted; spec marks `nullable: true`) |
| `document.stringDocument` | parsed LLM JSON: every key whose value is a string |
| `document.structuredDocument` | parsed LLM JSON: non-string values; null if all-string |
| `document.labels` | echo `body.labels` (default `[]`) |
| `usageInfo.creditsConsumed` | `(prompt+completion tokens) / 1000 * 0.011`, rounded 6dp, ≥ 0 |

## Hospital-pilot gate

Pre-flight before any LLM call:

1. `ICODER_CREDENTIAL_LLM` empty + `ICODER_ALLOW_DEGRADED_NO_KEY != "1"`
   → **503 service_unavailable** (consistent with all Phase 1.1/1.2 endpoints).

This matches the existing dev escape hatch (`ICODER_ALLOW_DEGRADED_NO_KEY=1`
is set in `tests/test_api/test_v2_guided_document_consistency.py`).

## PII redaction

Reuses the best-effort `app.state.data_policy.pii_redaction_required`
switch from cycle 1 (no cycle-specific change). Always non-fatal — if
redaction is requested but the redactor raises, we log + continue.

## 回环一致性测试 pattern (matches cycles 1+2)

1. Load the captured OpenAPI YAML from
   `docs/corti-reverse-engineered/guided-documents-generate.md` (regex
   extracts the `````yaml…`````` block).
2. Drive iCoDer's `POST /api/v2/tools/guided-documents/` with a realistic
   clinical request (stubbed LLM).
3. Recursive `_check_shape(value, schema, spec, path)`:
   - walks `$ref` resolvable inside `components/schemas/*`
   - **skips dynamic leaves**: `requestid`, `creditsConsumed`
   - honors `nullable: true` (Corti spec marks `interactionId`,
     `structuredDocument` nullable — Walker must NOT flag `None` as an
     error in that case)
   - asserts type equality (number accepts integer)
   - required-field presence
   - enum / const membership
4. Six tests cover: spec sanity, ephemeral shape parity, error envelope
   parity, empty-context 422, no-credential 503, hand-built reference
   round-trip.

## Test matrix (6 tests, all green)

```
tests/test_api/test_v2_guided_document_consistency.py::test_openapi_spec_is_real_and_cached            PASSED
tests/test_api/test_v2_guided_document_consistency.py::test_v2_guided_document_ephemeral_shape_matches_corti_spec PASSED
tests/test_api/test_v2_guided_document_consistency.py::test_v2_guided_document_error_envelope_matches_corti_spec PASSED
tests/test_api/test_v2_guided_document_consistency.py::test_v2_guided_document_empty_context_rejected  PASSED
tests/test_api/test_v2_guided_document_consistency.py::test_v2_guided_document_no_llm_credential_returns_503 PASSED
tests/test_api/test_v2_guided_document_consistency.py::test_v2_guided_document_reference_round_trip    PASSED
6 passed in 1.57s
```

Full `tests/test_api` regression: **103/103 PASS** in 5:22 (no collateral
damage to Phase 1.0 / 1.1 / Phase 1.2 cycles 1-2 / M3-0 surfaces).

Frontend `tsc --noEmit`: exit 0, no errors.

## Design decisions

1. **Single-path scope (templateRef + ephemeral only).** Two supply paths
   and one retention mode are explicitly 422'd with future-cycle hints.
   This keeps one-cycle closure tractable and leaves clear seams for the
   follow-on cycles (4 = Sections & Templates; 5 = Documents Classic).
2. **`validationErrors` omitted entirely** (not serialized as `null`)
   when there are no per-field validation errors. Per the spec,
   `validationErrors` is `type: array` with **no `nullable: true`** —
   serializing it as `null` would violate the contract.
3. **`structuredDocument` may be absent** when LLM output is all-string
   (e.g. legacy SOAP-style headings). Spec marks it `nullable: true`.
4. **Credits estimation is deterministic** for test reproducibility —
   `tokens / 1000 * 0.011`, same as the §13.3 Streams rate.
5. **Markdown-fence stripping** in LLM output (`\`\`\`json…\`\`\``) so
   models that emit fenced JSON parse cleanly.
6. **Trailing-slash dual registration** (`/guided-documents/` + `/guided-documents`)
   for SDK parity (some Corti SDK clients omit the slash).

## Out of scope (explicit)

- ❌ `assemblyTemplate` / `dynamicTemplate` (422 with future-cycle hint)
- ❌ Saved-retention 201 response + auto-generated aggregate template
- ❌ Sections CRUD / Templates CRUD / Documents Classic CRUD
  (Cycles 4 and 5)
- ❌ Frontend `GuidedDocumentsPage` (out of scope: Phase 1.2 = backend
  wire parity only; frontend pages land in Phase 1.5+ per existing
  parity queue)
- ❌ `transcript` / `facts` context variants (only `text` is flattened)
- ❌ Live interaction-aware context resolution
  (would need `MedCodERICD9CM3Retriever`-style fact store; Cycle 3 is
  a stateless single-shot call)

## Risk register

| Risk | Mitigation |
|---|---|
| Hospital-pilot gate gives a 503 instead of useful errors | Only fires when credential missing AND dev opt-in off; tests set `ICODER_ALLOW_DEGRADED_NO_KEY=1` to bypass |
| LLM returns non-JSON content | Markdown-fence strip; raw content kept under `stringDocument.body` so no data loss |
| Cycle 3 caller passes `interactionId` without context | Explicit 422 `interaction_unsupported` (Cycle 3 cannot resolve) |
| Caller supplies unknown retention | 422 `unsupported_retention_policy` with explicit future-cycle hint |
| Credits estimator drifts from real billing | Documented as deterministic placeholder; final billing settles in Cycle 4 (Sections & Templates likely introduces real billing pipeline) |

## Auto-advance: Cycle 4 = Sections & Templates REST (Beta)

Per the Phase 1.2 cycle queue and the parity policy, the next cycle
addresses the **CRUD for Guided Document Sections & Templates** so
iCoDer can host its own templates that the cycle-3 endpoint will
reference. Likely next actions:

- Reverse-engineer
  `https://docs.corti.ai/api-reference/guided-documents/{sections,templates,…}.md`
- Plan whether to share schemas with cycle 3 (`GuidedTemplateRef`,
  `GuidedLabel`) or split per-resource.
- Hospital-pilot gate still applies; ephemeral vs saved retention
  semantics get re-evaluated for CRUD (likely all saved).