# Phase 1.3 Cycle 9 — Recordings (STT) LIST align Corti §13.3

## Context

Phase 1.3 cycle 8 (`d8f852f`) shipped the **first STT mutation endpoint** — `POST /api/v2/tools/interactions/{id}/transcripts/` (create-transcript). Cycle 9 closes the **first recording endpoint** — `GET /api/v2/tools/interactions/{id}/recordings/` (list-recordings).

This is the **first endpoint of the recordings family** (cycle 9 = recording #1 of 4). The STT family has 9 endpoints total: 5 transcripts + 4 recordings. Cycles 6/7/8 closed 3 transcripts (list / get / create). Cycle 9 starts the recordings family with the canonical list endpoint.

Notable spec semantics (key difference from cycle-6 transcripts list):
- **Response envelope** = `{recordings: [uuid, uuid, ...]}` (just UUID strings)
- **NOT nullable**: spec does NOT declare `recordings` as `nullable: true`. Empty list is the canonical "no recordings" signal — NOT `null`.
- **No `?full=` toggle**: recordings list is just an array of UUIDs; no metadata payload.
- **No `usageInfo`**: no credits consumption reported for listing.
- **No status field**: recordings are simple file references, no processing states.

## Spec source

`docs/corti-reverse-engineered/stt-list-recordings.md` (4,897 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/recordings/list-recordings.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_9_stt_list_recordings/corti-stt-list-recordings.md`.

## Endpoint surface

```
GET /api/v2/tools/interactions/{interaction_id}/recordings/
Authorization: Bearer <jwt or oauth>

→ 200 OK   RecordingsListResponse
             { recordings: UUID[] }    (array, NOT nullable)
→ 400, 403, 500, 504   RFC9457 ErrorResponse
→ 503            service_unavailable (hospital-pilot gate)
```

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | Added `RecordingsListResponse` |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | Added `_stub_recordings_for_interaction` + `list_v2_tools_interaction_recordings` GET endpoint (with trailing-slash dual registration) |
| `backend/tests/test_api/test_v2_stt_list_recordings_consistency.py` | NEW | 7 回环一致性测试 |
| `docs/PHASE_1_3_CYCLE9_STT_LIST_RECORDINGS.md` | NEW | this file |
| `docs/phase_cycles/cycle_9_stt_list_recordings/corti-stt-list-recordings.md` | NEW | archive |

## Stub data

Sentinel pattern reuses cycle-6's `empty-{uuid}` convention BUT for a different semantic:

- **`empty-{uuid}` → `{recordings: []}`** (empty array, NOT null)
  - Spec does NOT declare `recordings` as nullable, so this exercises the "empty list is valid" contract
  - **Different from cycle-6** which used the same sentinel to return `null`
- **default / non-sentinel** → 2 deterministic UUIDs derived from `interaction_id` prefix (path-echo pattern, mirrors cycle-6 transcripts)

## Hospital-pilot gate

Same 503 gate as cycles 1-8. No additional gating for cycle 9.

## 回环一致性测试 pattern

Reuses cycle-6/7/8 walker (with `$ref + parent-level metadata` fix) unchanged. Cycle 9 response envelope is trivial (`{recordings: [uuid]}`) so no walker changes needed.

7 tests cover:

```
test_stt_recordings_list_spec_is_real_and_cached                              PASSED
test_stt_recordings_list_response_required_field                              PASSED
test_v2_stt_recordings_list_default_shape_matches_corti_spec                  PASSED
test_v2_stt_recordings_list_empty_sentinel                                    PASSED
test_v2_stt_recordings_list_path_echoes_interaction_id                        PASSED
test_v2_stt_recordings_list_different_interactions_different_recordings       PASSED
test_v2_stt_recordings_list_reference_round_trip                              PASSED
7 passed in 1.23s
```

Full `tests/test_api` regression: **152/152 PASS** in 3:39 (was 145 pre-cycle-9, +7 for this cycle). tsc clean.

## Design decisions

1. **Reuse `empty-{uuid}` sentinel pattern with different semantic.** Cycle-6 used it for null envelope; cycle-9 uses it for empty array. Both are valid exercises of the spec.
2. **Path-echo via deterministic UUID derivation.** Stub generates recording UUIDs from `interaction_id.replace("-", "")[:8]` prefix so tests can verify path-scoping without DB.
3. **Trailing-slash dual registration.** Both `/recordings/` (matches Corti spec) and `/recordings` (REST convention) registered — consistent with cycle-6/8 LIST patterns.
4. **No new walker changes.** Trivial envelope shape (array of strings) — walker already handles `type: array, items: {$ref: UUID}`.

## Out of scope (explicit, future cycles)

- ❌ `POST /interactions/{id}/recordings/` (upload-recording) — Cycle 10
- ❌ `GET /interactions/{id}/recordings/{recordingId}` (get-recording) — Cycle 11
- ❌ `DELETE /interactions/{id}/recordings/{recordingId}` (delete-recording) — Cycle 12
- ❌ `GET /interactions/{id}/transcripts/{transcriptId}/status` — Cycle 9.1
- ❌ `DELETE /interactions/{id}/transcripts/{transcriptId}` — Cycle 9.2
- ❌ Real audio upload surface — Cycle 10 prerequisite (multipart binary)
- ❌ Frontend recording detail page — out of scope: Phase 1.3 =
  backend wire parity only

## Risk register

| Risk | Mitigation |
|---|---|
| Stub UUIDs not real (server would generate fresh UUIDs) | Documented as stub-only; path-echo makes the contract testable |
| `recordings` field empty vs null confusion | Spec explicitly non-nullable; empty-list sentinel exercises this |
| Walker doesn't validate `format: uuid` | Format strings are advisory in OpenAPI 3.0; type=string is sufficient |

## Auto-advance: Cycle 10 = upload-recording (REST POST, multipart binary)

Per the parity queue. Cycle 10 will close `POST /interactions/{id}/recordings/` — the audio upload endpoint. This is the **prerequisite for create-transcript** to be a real wire (cycle-8's stub `recordingId` references an upload). Will require:
- Multipart binary upload
- File size limits (per spec: up to 120 minutes / 150 MB total)
- Returns a recording UUID that create-transcript can reference

This will be the **first non-JSON content-type** endpoint in iCoDer's v2 surface.