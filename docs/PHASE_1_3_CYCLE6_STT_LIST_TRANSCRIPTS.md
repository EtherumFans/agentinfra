# Phase 1.3 Cycle 6 — Transcripts (STT) LIST — align Corti §13.3

## Context

Phase 1.2 = 5 cycles all GREEN, wrapping up the §13.4 TextGen family.
Phase 1.3 = STT alignment (Corti §13.3). The STT family has 9 endpoints
total (5 transcripts + 4 recordings); cycle 6 closes only the LIST for
transcripts per the same "simplest path" scope discipline used in
cycles 3-5.

Corti §13.3 transcripts are scoped to a single interaction:

```
GET /interactions/{id}/transcripts/?full=true|false
```

Returns an envelope `{transcripts: TranscriptsListItem[] | null}`
where the `transcripts` field is **declared nullable** in the captured
OpenAPI spec (unusual — most envelope arrays are not nullable).

## Spec source

`docs/corti-reverse-engineered/stt-list-transcripts.md` (7,962 bytes,
fetched 2026-07-01 from
`https://docs.corti.ai/api-reference/transcripts/list-transcripts.md`).
Embedded OpenAPI 3.0.0 YAML is the **ground truth** — never inferred.

Archive: `docs/phase_cycles/cycle_6_stt_list_transcripts/corti-stt-list-transcripts.md`.

## Endpoint surface

```
GET /api/v2/tools/interactions/{interaction_id}/transcripts/      (and trailing-slash-less alias)
Authorization: Bearer <jwt or oauth>

Query params (optional):
  full    boolean   Display full transcripts in listing (default: false)

→ 200 OK   { transcripts: TranscriptsListItem[] | null }
→ 503      service_unavailable (hospital-pilot gate)
```

## Files

| Path | Lines | Purpose |
|---|---|---|
| `backend/app/schemas/v2_tools_stt.py` | 130 | Pydantic for CommonTranscriptResponse + TranscriptsMetadata + TranscriptsData + TranscriptsListItem + TranscriptsListResponse |
| `backend/app/api/v2_tools_stt.py` | 175 | LIST router with deterministic stub data + ?full support + nullable envelope support |
| `backend/tests/test_api/test_v2_stt_consistency.py` | 310 | 8 回环一致性测试 |
| `backend/app/main.py` | +2 | include + import |

## Stub data

2 transcript items per interaction, deterministic per-UUID:

- `transcriptSample` is always populated (it's required).
- `transcript` (full data with channel/participant/text/start/end rows)
  is populated only when `?full=true`; omitted otherwise.
- Sentinel interaction IDs starting with `empty-` return
  `{transcripts: null}` to exercise the spec's nullable envelope
  contract.

`TranscriptsParticipant.role` is the strict enum
`doctor | patient | multiple` (NOT iCoDer-friendly Chinese names —
Corti's enum is the wire contract).

## Hospital-pilot gate

Same 503 gate as cycles 1-5.

## 回环一致性测试 pattern

Same walker as cycles 3-5, with one **major extension**:

```python
# Walker fix: when property has both $ref AND parent-level metadata
# (type, nullable, enum), preserve parent overrides when resolving.
if "$ref" in schema:
    parent_overrides = {k: v for k, v in schema.items() if k != "$ref"}
    resolved = _resolve_ref(spec, schema["$ref"])
    schema = {**resolved, **parent_overrides}  # parent wins
```

Without this fix, the walker would treat `transcript: {$ref: ...,
nullable: true}` as if the resolved schema didn't have nullable (because
`TranscriptsData` itself doesn't declare nullable), causing false
positives for any endpoint with nullable parent properties.

**This walker fix applies retroactively to cycles 3-5** — the
nullable marker for cycle 3's `interactionId`/`structuredDocument` and
cycle 5's `transcripts` field all flow through the same code path, but
none of them had parent-level `nullable: true` on a `$ref` property
(they were resolved via the inner object's own nullable declaration).
The cycle 6 case is the first that exercises this edge.

8 tests cover:

```
test_stt_spec_is_real_and_cached                                PASSED
test_stt_envelope_field_is_nullable_in_spec                     PASSED
test_v2_stt_list_shape_matches_corti_spec                       PASSED
test_v2_stt_list_full_true_includes_transcript_data             PASSED
test_v2_stt_list_full_false_omits_transcript                    PASSED
test_v2_stt_envelope_nullable_round_trip                        PASSED
test_v2_stt_path_scoping                                        PASSED
test_v2_stt_reference_round_trip                                PASSED
8 passed in <1s
```

Full `tests/test_api` regression: **126/126 PASS** in 3:45 (was 118
pre-cycle-6, +8 for this cycle). tsc clean.

## Design decisions

1. **LIST only, not CRUD.** STT family has 9 endpoints. Closing all in
   one cycle violates the "按复杂度排序" rule. Cycles 7+ layer on
   create-transcript, get-transcript, get-transcript-status,
   delete-transcript, and the 4 recording endpoints.
2. **Stub data over real STT.** iCoDer has no real STT integration yet
   (the legacy `/ws/speech-to-text` WSS surface is unrelated).
   Stub data lets us validate the wire contract without faking
   audio processing.
3. **`TranscriptsParticipant.role` is the strict Corti enum.**
   `doctor | patient | multiple` — NOT Chinese labels. The wire
   contract is the contract; iCoDer callers are expected to translate
   at their own layer.
4. **Sentinel interaction_id for nullable envelope.** `empty-{uuid}`
   returns `{transcripts: null}` so the test suite verifies the
   nullable envelope contract end-to-end.
5. **Walker fix preserves parent-level metadata on `$ref` resolution.**
   This is a generic OpenAPI semantics fix that benefits all future
   cycles with nullable parent properties.

## Out of scope (explicit, future cycles)

- ❌ `POST /interactions/{id}/transcripts/` (create) — Cycle 7
- ❌ `GET /interactions/{id}/transcripts/{transcript_id}` (get one) — Cycle 7.1
- ❌ `GET /interactions/{id}/transcripts/{transcript_id}/status` — Cycle 7.2
- ❌ `DELETE /interactions/{id}/transcripts/{transcript_id}` — Cycle 7.3
- ❌ All 4 recording endpoints (delete-recording, get-recording,
  list-recordings, upload-recording) — Cycle 8+
- ❌ Real STT integration (audio decoding, language detection, etc.)
  — separate Phase 1.3 task
- ❌ Frontend transcript viewing page — out of scope: Phase 1.3 =
  backend wire parity only

## Risk register

| Risk | Mitigation |
|---|---|
| Nullable envelope field tested via sentinel only | Real production interactions would have non-null lists; sentinel is a contract guarantee, not a behavior assumption |
| `role` enum drift | Captured from live spec; if Corti adds new roles, walker + stub must update |
| Walker fix retroactively affects cycles 3-5 | All three cycles still pass regression; fix is strictly additive (preserves nullable marker) |

## Auto-advance: Cycle 7 = get-transcript (REST)

Per the parity queue. Cycle 7 will close the `GET
/interactions/{id}/transcripts/{transcript_id}` endpoint, which returns
a single full transcript (not the list with optional full payload).
Same stub-data approach.