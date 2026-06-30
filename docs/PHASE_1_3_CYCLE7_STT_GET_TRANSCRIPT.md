# Phase 1.3 Cycle 7 — Transcripts (STT) GET single — align Corti §13.3

## Context

Phase 1.3 cycle 6 (`729a2e6`) shipped `GET /api/v2/tools/interactions/{id}/transcripts/?full=bool`
(LIST with optional full payload). Cycle 7 closes the **single-transcript
GET** endpoint — `GET /api/v2/tools/interactions/{id}/transcripts/{transcriptId}`.

This is the "drill into one" companion to cycle 6's LIST. While cycle 6
returns a `transcripts[]` envelope with optional preview/full payload,
cycle 7 returns the **canonical single-transcript body** with no `?full=`
toggle (it's always full).

Notable spec semantics:
- `status` is an enum: `completed | processing | failed`
- `transcripts` field is **nullable** — null while status is `processing`
  or `failed` (transcript not yet finalized)
- `recordingId` is a UUID that links to the source recording
- `usageInfo.creditsConsumed` is included (consumption is non-zero only
  on retrieval of finalized transcripts per the spec)

## Spec source

`docs/corti-reverse-engineered/stt-get-transcript.md` (9,859 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/transcripts/get-transcript.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_7_stt_get_transcript/corti-stt-get-transcript.md`.

## Endpoint surface

```
GET /api/v2/tools/interactions/{interaction_id}/transcripts/{transcript_id}
Authorization: Bearer <jwt or oauth>

→ 200 OK   TranscriptsResponse
             {
               id:           UUID,
               metadata:     TranscriptsMetadata (participantsRoles[]),
               transcripts:  CommonTranscriptResponse[] | null   (nullable while !completed),
               usageInfo:    { creditsConsumed: number },
               recordingId:  UUID,
               status:       "completed" | "processing" | "failed"
             }
→ 503      service_unavailable (hospital-pilot gate)
```

Note: no trailing-slash alias here — Corti spec path is exactly
`/interactions/{id}/transcripts/{transcriptId}` with no trailing slash.

## Files

| Path | Status | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | MODIFIED | Added `CommonUsageInfo` + `TranscriptsResponse` |
| `backend/app/api/v2_tools_stt.py` | MODIFIED | Added `_stub_single_transcript` + `get_v2_tools_interaction_transcript` endpoint |
| `backend/tests/test_api/test_v2_stt_get_transcript_consistency.py` | NEW | 8 回环一致性测试 |
| `docs/PHASE_1_3_CYCLE7_STT_GET_TRANSCRIPT.md` | NEW | this file |
| `docs/phase_cycles/cycle_7_stt_get_transcript/corti-stt-get-transcript.md` | NEW | archive |

## Stub data

Three transcript_id sentinels exercise the full lifecycle:

- **default / non-sentinel** → status=completed, transcripts[] populated
  (3 utterances), creditsConsumed=0.018
- **`processing-{uuid}`** → status=processing, transcripts=null,
  creditsConsumed=0.0
- **`failed-{uuid}`** → status=failed, transcripts=null,
  creditsConsumed=0.0

`recordingId` echoes the interaction_id prefix so callers can verify the
path-echo contract.

## Hospital-pilot gate

Same 503 gate as cycles 1-6.

## 回环一致性测试 pattern

Reuses cycle-6 walker with the `$ref + parent-level metadata` fix.
The cycle-7 endpoint exercises the nullable contract twice (processing +
failed), validating that the walker correctly accepts `null` for
`transcripts` when the parent property declares `nullable: true`.

8 tests cover:

```
test_stt_get_spec_is_real_and_cached                                  PASSED
test_stt_get_status_enum_matches_spec                                 PASSED
test_v2_stt_get_completed_shape_matches_corti_spec                    PASSED
test_v2_stt_get_processing_shape_with_nullable_transcripts            PASSED
test_v2_stt_get_failed_shape_with_nullable_transcripts                PASSED
test_v2_stt_get_path_echoes_ids                                       PASSED
test_v2_stt_get_completed_has_populated_transcripts                   PASSED
test_v2_stt_get_reference_round_trip                                  PASSED
8 passed in <1s
```

Full `tests/test_api` regression: **134/134 PASS** in 3:37 (was 126
pre-cycle-7, +8 for this cycle). tsc clean.

## Design decisions

1. **Sentinel transcript_id for status states.** Three different
   transcript_id prefixes (`processing-`, `failed-`, anything-else)
   exercise the full enum without needing actual async processing.
   Same pattern as cycle-6's `empty-{uuid}` sentinel for nullable
   envelope.
2. **`recordingId` echoes interaction_id prefix.** Makes the path-echo
   contract testable. Real recordingId would be a fresh UUID tied to
   the actual audio file.
3. **Reuse cycle-6 schemas.** `CommonTranscriptResponse`,
   `TranscriptsMetadata`, `TranscriptsParticipant` all shared.
   Only added `CommonUsageInfo` + `TranscriptsResponse` (and the
   Literal status enum).
4. **No `?full=` toggle on cycle 7.** Cycle 6 has `?full=` for the LIST
   (preview vs full payload); cycle 7 is always full because callers
   wouldn't GET a single transcript to see just a preview.
5. **Cycle 6 walker fix carries forward.** The walker already handles
   `nullable: true` on `$ref` parents, so cycle 7's two nullable cases
   (processing + failed) passed without additional walker changes.

## Out of scope (explicit, future cycles)

- ❌ `POST /interactions/{id}/transcripts/` (create) — Cycle 8
- ❌ `GET /interactions/{id}/transcripts/{transcriptId}/status` — Cycle 8.1
- ❌ `DELETE /interactions/{id}/transcripts/{transcriptId}` — Cycle 8.2
- ❌ All 4 recording endpoints (delete-recording, get-recording,
  list-recordings, upload-recording) — Cycle 9+
- ❌ Real async transcript processing (would need background task
  machinery) — separate Phase 1.3 task
- ❌ Frontend transcript detail page — out of scope: Phase 1.3 =
  backend wire parity only

## Risk register

| Risk | Mitigation |
|---|---|
| Sentinel-based stub assumes callers don't pass real-looking IDs | Real production would have real UUIDs; stub mimics typical UUID shape |
| `recordingId` echoes interaction_id prefix | Real recordingId is server-assigned; stub is for path-echo testing only |
| `transcripts: null` while processing might confuse SDK callers | This matches Corti's spec exactly; documented in OpenAPI description field |

## Auto-advance: Cycle 8 = create-transcript (REST POST)

Per the parity queue. Cycle 8 will close
`POST /interactions/{id}/transcripts/` (create-transcript), the first
STT endpoint that mutates state. Will require accepting a multipart
audio upload or a recordingId reference per the captured spec.