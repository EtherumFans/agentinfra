# Phase 1.3 Cycle 8 — Transcripts (STT) Create — align Corti §13.3

## Context

Phase 1.3 cycle 7 (`e594dee`) shipped `GET /api/v2/tools/interactions/{id}/transcripts/{transcriptId}` (single-transcript retrieval). Cycle 8 closes the **first STT mutation endpoint** — `POST /api/v2/tools/interactions/{id}/transcripts/` (create-transcript).

This is the **first write path** in the §13.3 STT family. Up to cycle 7, the STT surface was read-only (list + get). Cycle 8 introduces the JSON request body contract required to submit an audio-recording → transcript job.

Notable spec semantics:
- **Status code 201** (not 200) — Corti-style resource creation.
- **Required body fields**: `recordingId` (UUID of an existing recording uploaded via `/recordings` endpoint, NOT in this cycle), `primaryLanguage` (e.g. `"en"`).
- **Optional knobs (9)**: `spokenPunctuation`, `automaticPunctuation`, `isDictation` (deprecated), `isMultichannel`, `diarize`, `participants[]`, `async`, `replacements[]`, `keyterms.terms[]`.
- **Response body** = same `TranscriptsResponse` envelope from cycle 7 (re-used verbatim — no new response schema needed).
- **Async dispatch**: when `async: true`, server should return 202 + `Location` header immediately and process in background. **Cycle 8 stub does NOT yet implement async dispatch** — the synchronous stub returns 201 in both cases. Async is a separate Phase 1.3 task.

## Spec source

`docs/corti-reverse-engineered/stt-create-transcript.md` (14,078 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/transcripts/create-transcript.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_8_stt_create_transcript/corti-stt-create-transcript.md`.

## Endpoint surface

```
POST /api/v2/tools/interactions/{interaction_id}/transcripts/
Authorization: Bearer <jwt or oauth>
Content-Type: application/json

Request body (TranscriptsCreateRequest):
{
  recordingId:          UUID         (required, source recording)
  primaryLanguage:      string       (required, e.g. "en" or "zh-CN")
  spokenPunctuation:    bool?        (overrides automaticPunctuation)
  automaticPunctuation: bool?        (default true)
  isDictation:          bool?        (deprecated — ignored when new fields provided)
  isMultichannel:       bool?        (per-channel transcription)
  diarize:              bool?        (separate speakers within channel)
  participants:         Participant[]?
                              [{channel: int, role: "doctor|patient|multiple"}]
  async:                bool?        (return 202 + Location, process in bg)
  replacements:         {find, replace}[]?
  keyterms:             {terms: [{term: string}]}?
}

→ 201 Created  TranscriptsResponse   (same envelope as cycle-7 GET)
                   {
                     id, metadata, transcripts (nullable),
                     usageInfo {creditsConsumed}, recordingId,
                     status: "completed" | "processing" | "failed"
                   }
→ 400, 401, 403, 500, 504   RFC9457 ErrorResponse
→ 503            service_unavailable (hospital-pilot gate)
```

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | Added `TranscriptsCreateReplacement` + `TranscriptsCreateKeyterm` + `TranscriptsCreateKeyterms` + `TranscriptsCreateRequest` |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | Added `_stub_create_transcript` + `create_v2_tools_interaction_transcript` POST endpoint (with trailing-slash dual registration) |
| `backend/tests/test_api/test_v2_stt_create_transcript_consistency.py` | NEW | 11 回环一致性测试 |
| `docs/PHASE_1_3_CYCLE8_STT_CREATE_TRANSCRIPT.md` | NEW | this file |
| `docs/phase_cycles/cycle_8_stt_create_transcript/corti-stt-create-transcript.md` | NEW | archive |

## Stub data

Stub mimics the **synchronous** path (no async dispatch yet):

- **id** = `{interaction_id}-tr-{last 12 chars of recordingId}` (deterministic, testable)
- **recordingId** = echoed from request body
- **status** = always `"completed"` (sync mimic)
- **transcripts[]** = 1 placeholder utterance
- **creditsConsumed** = 0.024 (placeholder; spec requires presence but not specific value)
- **participantsRoles** = request body's `participants` if provided, else default 2-channel mapping

## Hospital-pilot gate

Same 503 gate as cycles 1-7. No additional gating for cycle 8.

## 回环一致性测试 pattern

Reuses cycle-6/7 walker (with `$ref + parent-level metadata` fix) unchanged. Cycle 8 exercises:
- Spec sanity (right paths/schemas captured)
- Required-field contract (missing `recordingId` or `primaryLanguage` → 4xx via Pydantic validation)
- Minimal-body shape match (canonical happy path)
- Optional fields all accepted (full-body variant)
- Body-echo invariants (`recordingId` from request → response)
- Path-echo invariants (`interaction_id` prefix in response `id`)
- Async flag accepted (current stub still sync)
- Reference round-trips (both request + response)

11 tests cover:

```
test_stt_create_spec_is_real_and_cached                       PASSED
test_stt_create_required_fields_match_spec                    PASSED
test_v2_stt_create_minimal_shape_matches_corti_spec           PASSED
test_v2_stt_create_missing_recording_id_rejected              PASSED
test_v2_stt_create_missing_primary_language_rejected          PASSED
test_v2_stt_create_body_echoes_recording_id                   PASSED
test_v2_stt_create_path_echoes_interaction_id                 PASSED
test_v2_stt_create_optional_fields_accepted                   PASSED
test_v2_stt_create_async_flag_accepted                        PASSED
test_v2_stt_create_reference_round_trip                       PASSED
test_v2_stt_create_request_reference_round_trip               PASSED
11 passed in 1.17s
```

Full `tests/test_api` regression: **145/145 PASS** in 3:40 (was 134 pre-cycle-8, +11 for this cycle). tsc clean.

## Design decisions

1. **Async dispatch not yet implemented.** Per spec, `async: true` should return 202 + Location. Cycle 8 stub always returns 201 synchronously regardless of `async` value. Real async dispatch requires background task machinery — separate Phase 1.3 task.
2. **Reuse cycle-7 response envelope.** `TranscriptsResponse` already defined in cycle 7. No new response schema needed for cycle 8.
3. **Trailing-slash dual registration.** Both `/transcripts/` (with slash, matches Corti spec) and `/transcripts` (without, REST convention) registered — consistent with cycle-6 LIST pattern.
4. **`async` Pydantic alias.** Python keyword `async` requires alias `async_` in field name; aliased as `"async"` in JSON serialization.
5. **No new error codes.** Cycle 8 reuses the same `ErrorResponse` shape as cycles 3-7 (400/401/403/500/504). No new validation rules beyond Pydantic's built-in required-field checks.
6. **Cycle 6/7 walker fix carries forward.** The walker already handles `nullable: true` on `$ref` parents, so cycle 8's response (same shape as cycle 7) passed without additional walker changes.

## Out of scope (explicit, future cycles)

- ❌ Real STT processing (background task machinery) — separate Phase 1.3 task
- ❌ `async: true` → 202 + Location header — separate Phase 1.3 task (cycle 8 stub always 201)
- ❌ `GET /interactions/{id}/transcripts/{transcriptId}/status` — Cycle 8.1
- ❌ `DELETE /interactions/{id}/transcripts/{transcriptId}` — Cycle 8.2
- ❌ All 4 recording endpoints (delete-recording, get-recording,
  list-recordings, upload-recording) — Cycle 9+
- ❌ Real audio upload surface (`/recordings`) — Cycle 9+ prerequisite
- ❌ Frontend transcript detail page — out of scope: Phase 1.3 =
  backend wire parity only

## Risk register

| Risk | Mitigation |
|---|---|
| Stub always 201 (ignores `async` flag) | Documented as out-of-scope; real async is a separate Phase 1.3 task |
| `recordingId` not validated as UUID | Pydantic accepts any string; real implementation should validate UUID format |
| `primaryLanguage` not validated against language registry | Pydantic accepts any string; real implementation should validate against `/languages` endpoint list |
| `isDictation` is deprecated but Pydantic still accepts it | Marked Optional, description carries the deprecation notice; backward-compatible |

## Auto-advance: Cycle 9 = recordings family

Per the parity queue. The STT family has 5 transcript + 4 recording = 9 endpoints. Cycles 6/7/8 closed 3 transcripts (list / get / create). Remaining: 2 transcripts (get-status, delete) + 4 recordings (delete-recording, get-recording, list-recordings, upload-recording).

Cycle 9 will likely be **`GET /interactions/{id}/recordings/`** (list-recordings) — the canonical first recording endpoint, mirroring cycle-6 transcripts LIST pattern.