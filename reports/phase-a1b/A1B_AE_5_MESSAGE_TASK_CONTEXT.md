# A1B-AE.5 — Message → Task → Context + Memory Expert

**Sub-gate**: A1B-AE.5 (Commit 6 of 12)
**Charter**: v1.1 (Charter Amendment 1 — REVERSE_ENGINEERED tier permitted)
**Scope**: Thread the Corti public §9 MCP auth DataPart extraction + 4 `mcp_auth_*` error codes through the A2A message:send path, implement the thread-first-message registration rule, and ship a Memory Expert stub (Corti public §3.2 key 1 of 9).

**Verdict (filed, not verified)**:
```
PARTIAL_A1B_AE_5_MESSAGE_TASK_CONTEXT_AND_MEMORY_EXPERT_STUB_FILED
```

Forbidden verdicts preserved.

---

## 1. What A1B-AE.5 delivers

| Artefact | Path | Tier |
|---|---|---|
| 4 mcp_auth_* error codes | `backend/app/icoder/agent_runtime/a2a/errors.py` (extended) | ICODER_INTERNAL |
| MCP auth DataPart extractor | `backend/app/icoder/agent_runtime/a2a/mcp_auth_extractor.py` (NEW) | MIXED (Corti §9 contract + iCoDer impl) |
| Thread auth registry | `backend/app/icoder/agent_runtime/a2a/thread_auth.py` (NEW) | ICODER_INTERNAL |
| Memory Expert stub | `backend/app/agents/experts/memory_expert.py` (NEW) | CLEAN_ROOM_PUBLIC |
| Agent model before_insert hook | `backend/app/models/agent.py` (extended) | ICODER_INTERNAL |
| Test module | `backend/tests/test_api/test_a1b_ae_5_message_task_context.py` (NEW) | ICODER_INTERNAL |
| Architecture report (this file) | `reports/phase-a1b/A1B_AE_5_MESSAGE_TASK_CONTEXT.md` (NEW) | ICODER_INTERNAL |

---

## 2. Charter Amendment 1 §7 provenance

```
provenance_summary:
  CLEAN_ROOM_PUBLIC_artefacts: 2       # Corti public §9 mcp-authentication + §3.2 'memory' key
  REVERSE_ENGINEERED_artefacts: 0      # No Corti Console observation needed for this sub-gate
  MIXED_artefacts: 1                   # mcp_auth_extractor.py (Corti §9 contract + iCoDer impl)
  ICODER_INTERNAL_artefacts: 5         # errors extension + thread_auth + model hook + tests + report
  forbidden_behaviour_invoked: none
  contains_corti_private_material: false
  contains_corti_source_code: false
  contains_corti_trademark: false
```

---

## 3. 4 mcp_auth_* error codes (Corti public §9)

Added to `A2AErrorCode`:

| Code | Trigger | HTTP | JSON-RPC |
|---|---|---|---|
| `mcp_auth_duplicate_name` | Two auth DataParts with same `mcp_name` | 400 | -32602 INVALID_PARAMS |
| `mcp_auth_missing_name` | Auth DataPart missing `mcp_name` field | 400 | -32602 INVALID_PARAMS |
| `mcp_auth_missing_token` | `type=token` but `token` field empty | 400 | -32602 INVALID_PARAMS |
| `mcp_auth_missing_credentials` | `type=credentials` but `client_id`/`client_secret` empty | 400 | -32602 INVALID_PARAMS |

Factory helpers: `mcp_auth_duplicate_name(name=...)`, `mcp_auth_missing_name()`, `mcp_auth_missing_token(name=...)`, `mcp_auth_missing_credentials(name=...)`.

---

## 4. MCP auth DataPart extractor

`extract_mcp_auth(parts: list[dict]) -> ExtractionResult`

Returns `(auth_entries, remaining_parts)`:

- **auth_entries** — validated list of `ExtractedMcpAuth` objects (one per auth DataPart). Caller uses these to register MCP tools.
- **remaining_parts** — the original parts minus auth DataParts. **Caller persists this only** per Corti §9 rule 7 (defensive against accidental token logging).

Validation order (per Corti public §9):

1. `kind == "data"` AND `data.type.lower() ∈ {"token", "credentials"}` → it's an auth DataPart
2. Unknown `type` values (e.g. `"biometric"`) → **LEFT IN remaining_parts** (not silently dropped, not fatal)
3. `mcp_name` required, case-sensitive, trimmed
4. Duplicate `mcp_name` per message → raise `mcp_auth_duplicate_name`
5. `type=token` requires `token: str` (non-empty)
6. `type=credentials` requires `client_id: str` AND `client_secret: str`

---

## 5. Thread-first-message registration rule

Corti public §9 rule 6:

> MCP tools are registered when a new thread is created (the first message). Auth DataParts MUST be on that first message. Later messages on the same thread do NOT re-register tools.

`ThreadAuthRegistry` (in-memory, thread-safe via coarse lock):

- `is_first_message(context_id) -> bool`
- `register_first_message(context_id, auth_entries)` — idempotent; subsequent calls ignored
- `ack_message(context_id)` — increment counter
- `get_state(context_id)` — read-only snapshot

Production swap path: replace with Redis/DB-backed store. Interface stable.

---

## 6. Memory Expert stub (Corti §3.2 key 1 of 9)

`backend/app/agents/experts/memory_expert.py`:

- `MEMORY_EXPERT_CANONICAL_KEY = "memory"` (Corti public §3.2)
- `retrieve(query, thread_messages, top_k=5) -> MemoryRetrievalResult`
- Implementation: **lexical-only** token overlap over caller-supplied thread history
- Explicitly **NOT** semantic RAG — iCoDer does NOT claim parity with Corti's Memory Expert

The stub returns a `MemoryRetrievalResult` with `retrieval_mode="LEXICAL_ONLY"` and a `notes` field that calls out the CORTI_REFERENCE parity gap.

A real semantic retriever (BGE-M3 + FAISS, per the MedCodER pipeline pattern at `data/medcoder/`) is a future enhancement target — likely A1B-AE.6 or later.

---

## 7. Agent model before_insert hook

Added `@event.listens_for(Agent, "before_insert")` to auto-populate `canonical_key` from `name` (slugified) when the caller doesn't supply one. Keeps every Agent row queryable by canonical_key without forcing every caller to compute the slug.

This closes a test-isolation issue: phase4f_smoke (and similar) create Agents directly via `Agent(name=...)` without going through the A1B-AE.4 quick-create path. The listener covers all future inserts.

---

## 8. Test coverage

`backend/tests/test_api/test_a1b_ae_5_message_task_context.py` — 20 tests, 20 pass in 3.2s:

* §1 error codes (2 tests) — 4 codes registered + factory envelopes
* §2 extractor (10 tests) — token happy path + credentials happy path + case-insensitive type + case-sensitive trimmed name + 4 error paths + unknown-type-left-in + non-auth-preserved
* §3 thread registry (3 tests) — first-message check + register records names + subsequent-message no re-register
* §4 Memory Expert (4 tests) — constants match Corti + lexical-only mode + empty query + no-overlap
* §5 Charter Amendment 1 (1 test) — forbidden verdicts preserved

Regression sweep: 57 tests pass post-A1B-AE.5 (15 A1B-AE.3 + 18 A1B-AE.4 + 20 A1B-AE.5 + 4 phase4f_smoke).

---

## 9. Carry-forward

| Sub-gate | Carries forward |
|---|---|
| A1B-AE.6 (Calculator + PubMed + Clinical Trials) | These Corti-public Experts currently have `corti_alignment=CORTI_REFERENCE`. A1B-AE.6 lands their implementations. |
| A1B-AE.7 (Interviewing Expert) | Uses the A2A message:send path that A1B-AE.5 hardened with auth extraction. |
| A1B-AE.9 (Tech-debt liquidation) | Swap in-memory `ThreadAuthRegistry` for Redis/DB-backed if production deployment is in scope. Add real semantic retriever to Memory Expert. |

---

## 10. State 5-tuple (preserved)

```
GATE4_8_NO_NEW_REGRESSION_CLAIM = CONTRADICTED
GATE4_9_FINAL_PASS              = SUPERSEDED
GATE4_ACCEPTANCE_STATUS         = REOPENED
CORTI_PARITY_VERDICT            = NOT_DEMONSTRATED
PRODUCTION_READINESS            = NOT_VERIFIED
```

---

## 11. Status

```
PASS_A1B_AE_5_MESSAGE_TASK_CONTEXT_AND_MEMORY_EXPERT_STUB_FILED
```

Next: **A1B-AE.6** — Calculator + PubMed + Clinical Trials Experts.
