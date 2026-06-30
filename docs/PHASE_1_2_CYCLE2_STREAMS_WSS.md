# Phase 1.2 Cycle 2 — Streams WSS endpoint (Corti §13.3/§13.4)

> Date: 2026-06-30
> Roadmap: `docs/corti-reverse-engineered/SUMMARY.md §13.3 + §13.4 + §15.5`
> Capture source: `https://docs.corti.ai/api-reference/stream-asyncapi.json`
> (cached at `docs/corti-reverse-engineered/stream-asyncapi.json`)

## 1. Step 0 — Real traffic / spec capture

The ws-streams.jsonl file at `docs/corti-reverse-engineered/ws-streams.jsonl`
turned out to be Intercom chat-widget noise (`wss://nexus-websocket-a.intercom.io`),
**not** the Corti Streams WSS. We therefore went up the fallback chain:

1. **Live capture** via `curl https://docs.corti.ai/api-reference/stream-asyncapi.json`
   (HTTP 200, 17 104 bytes, 2026-06-30 23:30 UTC).
2. **Live capture** via `curl https://docs.corti.ai/stt/streams.md`
   (HTTP 200, 6 445 bytes).
3. **Cached both** at `docs/corti-reverse-engineered/stream-asyncapi.json` and
   archived in this report.

The AsyncAPI document is the authoritative wire-protocol contract for
Corti's `audio-bridge/v2/interactions/{id}/streams` endpoint.

## 2. Captured wire contract

### 2.1 Channel + handshake

```
wss://api.{eu|us|beta-eu}.corti.app/audio-bridge/v2/interactions/{id}/streams
   ?tenant-name={tenant-name}
   &token={token}
```

Path parameter ``{id}`` is the interaction session UUID; both query params
are required (no Authorization header in the WSS handshake per the spec).

### 2.2 Server → Client messages (6 types)

| ``type``              | Required fields                                                     | Optional fields                  |
|-----------------------|---------------------------------------------------------------------|----------------------------------|
| ``CONFIG_ACCEPTED``   | type                                                                | —                                |
| ``CONFIG_DENIED`` …   | type (enum), reason                                                 | —                                |
| ``transcript``        | type, data[].{id, transcript, final, speakerId, participant, time} | —                                |
| ``facts``             | type, fact[].{id, text, group, groupId, isDiscarded, source, createdAt} | updatedAt, *TzOffset fields |
| ``ENDED``             | type                                                                | —                                |
| ``usage``             | type, credits                                                       | —                                |
| ``error``             | type, error.{id, title, status, details, doc}                      | —                                |

### 2.3 Client → Server messages (3 types)

| ``type``  | Required fields                                                    |
|-----------|--------------------------------------------------------------------|
| ``config``| configuration.transcription.{primaryLanguage, participants}, configuration.mode.type |
| ``end``   | type                                                                |
| audio     | binary (``application/octet-stream``; ~64 KB / ~500 ms)            |

### 2.4 Lifecycle (per `streams.md`)

1. Create an `Interaction` → returns `webSocketUrl` + `interactionId`.
2. Open WSS; client MUST send config within **15 s**.
3. Server replies `CONFIG_ACCEPTED` or one of `CONFIG_DENIED|MISSING|…`.
4. Client streams audio chunks.
5. Server emits transcript every ~3 s, facts every ~60 s.
6. Client sends `end`; server emits `ENDED` then `usage`, then closes.

## 3. Step 1 — diff iCoDer ↔ Corti

| Concern                   | iCoDer before this cycle                                                                | Action |
|---------------------------|----------------------------------------------------------------------------------------|--------|
| `/api/v2/tools/streams`   | absent                                                                                  | **add** (this cycle) |
| `ws-streams.jsonl`        | mislabelled (Intercom noise)                                                            | leave for now — research artefact |
| legacy `/ws/agent/{id}`   | iCoDer-only chat-expert dispatcher (no Corti analog)                                    | **out of scope** (separate concept) |
| legacy `/ws/speech-to-text` | iCoDer STT dispatch (close to Corti §13.3 Transcribe; shape diverges)                | **out of scope** (Phase 1.3 = STT) |

No new feature-parity code was deleted in this cycle: `/ws/agent` and
`/ws/speech-to-text` are pre-existing M3-0 WSS surface, not "extra"
features blocking Streams. They are slated for re-shape in Phase 1.3.

## 4. Step 2 — implementation

- `backend/app/schemas/v2_tools_streams.py` — 17 Pydantic models, 1-to-1
  with the AsyncAPI ``components/schemas/*`` blocks (verbatim names,
  types, required/optional).
- `backend/app/api/v2_tools_streams.py` — WSS endpoint
  `WS /api/v2/tools/streams/{interaction_id}?token=&tenant-name=&tenant_name=`
  implementing the full lifecycle (auth → 15s config window → audio loop
  with synthetic transcript/facts cadence → end → ENDED + usage → close).
- `backend/app/main.py` — mount (L817 import + L848 include).

### 4.1 Notable deltas vs the captured spec

| Where iCoDer deviates                                       | Why                                                            |
|-------------------------------------------------------------|----------------------------------------------------------------|
| Tenant param accepts both `tenant-name` and `tenant_name`   | iCoDerexisting query-param convention is snake_case (FastAPI default); we accept both for SDK parity. |
| Auth: dev escape hatch via `ICODER_ALLOW_DEGRADED_NO_KEY=1`  | Hospital-pilot gate identical to REST v2 endpoints (Cycle 1). |
| Transcript cadence: 30-chunk in test mode, 3 s otherwise     | CI speed (the AsyncAPI says ~3 s; both modes respect that intent). |
| Close frame order: `ENDED` then `usage` then WS close       | Exact match to `streams.md`.                                   |

## 5. Step 3 — 回环一致性测试 (the hard gate)

`backend/tests/test_api/test_v2_streams_consistency.py` — 5 tests, all PASS:

| # | Test                                                | Verifies |
|---|-----------------------------------------------------|----------|
| 1 | `test_asyncapi_spec_is_real_and_cached`            | The captured AsyncAPI is the real one (title, version, channel address, 6 server messages). |
| 2 | `test_v2_streams_consistency_transcript_shape_matches_corti_spec` | iCoDer's transcript batches validate field-for-field against the AsyncAPI `StreamTranscriptMessage` schema (60 audio chunks → ≥ 2 transcripts). |
| 3 | `test_v2_streams_consistency_facts_shape_matches_corti_spec`      | iCoDer's facts batches validate against `StreamFactsMessage` (100 chunks → ≥ 1 fact). |
| 4 | `test_v2_streams_consistency_end_sequence_matches_corti_spec`     | After client `end`, server emits `ENDED` then `usage` (Corti's documented close-frame order). |
| 5 | `test_v2_streams_consistency_corti_reference_round_trip`         | A hand-built Corti-shaped reference sequence validates against its own AsyncAPI schemas (sanity check on the fixture). |

Dynamic-field skips (per policy): ``id``, ``createdAt``, ``createdAtTzOffset``,
``updatedAt``, ``updatedAtTzOffset``, ``credits``, ``time.start/end``.

## 6. Step 4 — verification

```bash
cd backend && pytest tests/test_api/test_v2_streams_consistency.py -v   # 5/5 PASS
cd backend && pytest tests/test_api/ -q                                  # 92+5 = 97 / 97 (no regression)
```

## 7. Out of scope (Phase 1.2 cycle 2)

- ❌ Re-shaping `/ws/speech-to-text` to Corti §13.3 Transcribe WSS contract (Phase 1.3).
- ❌ Re-shaping `/ws/agent/{expert_id}` (MCP/A2A replacement belongs to A2A spec).
- ❌ Real STT pipeline integration (iCoDer uses synthetic transcripts/facts for now).
- ❌ Frontend Streams page (out of scope for backend parity cycles).
- ❌ OAuth client_credentials → WSS upgrade (cycle 3 / cycle 4).

## 8. Cycle 2 risks

| Risk | Mitigation |
|------|------------|
| Synthetic transcripts/facts may not match real STT/FactsR output byte-for-byte | Wire contract validated; once real STT pipeline wires in, the discriminator + keys are already correct |
| Threaded reader may race with server emit | `time.sleep(0.3)` settle + 2 s deadline covers 64 KB/chunk × 100 chunks |
| WebSocket lifecycle differences between ASGI servers (uvicorn/hypercorn) | WSS spec uses standard `websocket.receive/send_text/send_bytes` only — should be portable |