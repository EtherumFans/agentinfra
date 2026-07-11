# Corti Agent × Expert × Tool Call Graph (Track C Gate 0B)

**Captured**: 2026-07-11
**Source**: PHASE4H-AUDIT-MC (medical-coding-icd-10-cpt-agent preset) on console.corti.app
**Experiments**: A/B/C/E

---

## 1. Agent → Expert wiring (PHASE4H-AUDIT-MC)

```
medical-coding-icd-10-cpt-agent (preset)
  ├── pubmed-expert                 (type: reference, no MCP server bound)
  ├── web-search-expert             (type: reference, no MCP server bound)
  ├── medical-calculator-expert     (type: reference, no MCP server bound)
  └── coding-expert                 (type: reference, no MCP server bound)
```

All 4 experts have `type: "reference"`. Per Phase 4-H §7 audit, only 2/13 Corti Experts (posos + drugbank) have `mcpServers` bound. The other 11 experts (including these 4) are Corti-hosted reference experts.

---

## 2. Expert → Tool mapping (verified via SSE data-json payloads)

| Expert | MCP tools (inferred) | data-json payload schema |
|---|---|---|
| **coding-expert** | `search_codes(query, code_system, count)` → top-N results with `match_path` + `related_codes`<br>`verify(code, code_system)` → `assignable` + `parent` + `related_codes[]`<br>`explore(code, code_system)` → `parents[]` hierarchical<br>`guidelines(code_area)` → coding conventions (not exercised)<br>`predict(note, code_system, filters)` → assigned codes (not exercised) | `{code_system, count, next_steps[{reason, tool}], query, results[]}` for search; `{assignable, code, description, parent, related_codes[]}` for verify; `{assignable, code, description, parents[], next_steps[]}` for explore |
| **pubmed-expert** | `search(query)` → web_result[] | `{response: [{type:"web_result", url, site{name,favicon_url}, source{provider, retrieved_at}, title, snippet}]}` |
| **web-search-expert** | `search(query)` → web_result[] | same as pubmed-expert |
| **medical-calculator-expert** | (not exercised) | TBD — likely `{calculation, inputs, result, reference}` |

---

## 3. Agent → Expert dispatch (observed)

### 3.1 Experiment A (no expert)
```
PHASE4H-AUDIT-MC
  └── (no expert dispatched, LLM direct answer)
```

### 3.2 Experiment B (force coding-expert)
```
PHASE4H-AUDIT-MC
  └── coding-expert
        ├── search_codes("acute STEMI inferior wall") → I21.19, I24.89, I21.09, I21.11, I21.4
        ├── verify(I21.19) → assignable=true, parent=I21.1, related=[I21.11]
        └── explore(I21.19) → parents: I21.1 → I21 → I20-I25 → 9
```
LLM synthesis cited evidence from all 3 tool calls.

### 3.3 Experiment C (force pubmed-expert)
```
PHASE4H-AUDIT-MC
  └── pubmed-expert
        └── search("DES vs BMS elderly STEMI 2022-2025") → web_result[10 items]
              └── sample: PMID 38815671 (10-year STEMI review, Anz J Surg 2024)
```

### 3.4 Experiment E (dual expert)
```
PHASE4H-AUDIT-MC
  ├── pubmed-expert.search("CHADS-VASc elderly AF anticoagulation") → web_result[]
  └── web-search-expert.search("2024 ESC/AHA AF guidelines") → web_result[]
(LLM combined both result sets in synthesis)
```

---

## 4. Sequential vs parallel dispatch

**Sequential only**. Experiment E shows:
```
"Calling expert: pubmed-expert"
"Calling expert: web-search-expert"
[data-json combined]
```

No evidence of parallel expert execution. LLM issues function calls one at a time, waits for each result.

→ **Track C Gate 3 implication**: iCoDer's `CortiLikeOrchestrator` should support sequential dispatch only. Parallel expert dispatch is OUT of scope for Corti-parity.

---

## 5. Tool result projection (Track C Gate 1 mapping)

Corti's data-json payloads are **already structured** (not markdown). iCoDer's `StructuredOutputProjector` (planned Gate 1) should mirror these schemas for tools that exist on both sides:

| Corti tool | iCoDer equivalent | Schema match |
|---|---|---|
| coding-expert.search_codes | `verify_code` MCP tool (iCoDer) | PARTIAL — iCoDer returns verify-only, no search |
| coding-expert.verify | `verify_code` MCP tool | YES |
| coding-expert.explore | `explore_code` MCP tool | YES |
| coding-expert.guidelines | `get_guidelines` MCP tool | YES |
| coding-expert.predict | medical-coding-agent | YES (different layer) |
| pubmed-expert.search | (not in iCoDer) | NO — iCoDer Gap |
| web-search-expert.search | (not in iCoDer) | NO — iCoDer Gap |
| medical-calculator-expert.* | (not in iCoDer) | NO — iCoDer Gap |

**iCoDer Gap**: 3 Corti experts (pubmed, web-search, medical-calculator) have no iCoDer equivalent. For Corti-parity single-agent runs, iCoDer medical-coding-agent should declare these as optional experts with stub providers OR omit them entirely (China localization: PubMed/WebSearch less critical for ICD-10-CN coding).

---

## 6. Call graph visual

```
            ┌─ Agent (PHASE4H-AUDIT-MC)
            │     systemPrompt: <role>...</quality_standards>
            │     experts: [pubmed, web-search, med-calc, coding]
            │
            ▼
       ┌─ LLM (Corti-hosted, model not exposed) ─┐
       │   • reads systemPrompt + user msg        │
       │   • decides expert dispatch              │
       │   • synthesizes final answer             │
       └────┬──────────────────────────┬──────────┘
            │ (0..N times)             │
            ▼                          ▼
       "Calling expert: X"        text-delta (final answer)
            │
            ▼
       Expert X (MCP tool collection)
            │
            ▼
       data-json (tool result)
            │
            ▼
       (back to LLM for next decision)
```

---

## 7. Files

- `outputs/phase5_track_c/corti_network/corti_medical_coding_agent_sdk_code.ts` — Corti SDK code (TS)
- `outputs/phase5_track_c/corti_network/expB_coding_expert_sse_stream.txt` — Exp B raw SSE
- `screenshots/phase5_track_c/corti_orchestrator/04_user_mc_code_tab.png` — Code tab screenshot
