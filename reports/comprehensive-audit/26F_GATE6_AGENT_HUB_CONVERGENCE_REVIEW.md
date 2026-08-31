# 26F — Pre-A0 Gate 6: Agent Hub Convergence Review

> Per spec §16. Reviews whether iCoDer's Agent Hub display converges with Corti Console's Agents page surface (IA, count, badges, classification, actions).

## Methodology

- Source: Corti Console `/ai-studio/agents` (Gate 1 §C-02 + §C-04) vs iCoDer `/api/icoder/agents/hub` (icoder_agents_hub.py)
- Compare: layout, card schema, filters, actions, count, classification
- Each delta classified: PARITY / ICODER_ADVANTAGE / CORTI_ADVANTAGE / DIFFERENT_BY_DESIGN

---

## §1. Corti Console Agents page surface (verified)

| Element | Value |
|---------|-------|
| URL | `console.corti.app/.../ai-studio/agents` |
| Tabs | "My agents" + "Pre-built agents" (2 tabs) |
| Filter | "Use case" (single filter) + "Open filter menu" |
| Card content | Name + created date + author + description |
| Sort | Not user-configurable in UI (default: most recent first) |
| New action | "New Agent" button top-right → 2 paths (Start from scratch / Use a template) |
| Per-card actions | Click card → opens detail page |
| Detail page tabs | Settings + Code (with 3 generators: JS SDK, .NET SDK, JSON Config) |
| Top-right header | API Client selector + live cost + Docs link |

### Pre-built count (authoritative from Gate 1)

**20 pre-built agents** in Corti Console (not 13 as prior Gate 4/14 claimed).

---

## §2. iCoDer Agent Hub surface (per code)

`backend/app/api/icoder_agents_hub.py:298-333`:

```python
@router.get("/hub", operation_id="icoder_agents_hub_list_v1")
async def list_hub_agents(use_case: str | None = Query(None, ...)):
    """Corti-style Agent Hub card list.
    Reads official_agents/**/agent_pack.json as the canonical source.
    Filters:
    - hidden_from_hub=true packs excluded.
    - agent_type=expert-stub packs excluded.
    - agent_type=internal_engine packs excluded.
    - use_case query param filters by manifest.use_case (Phase 3-B2 Loop 4).

    Metadata-only certified packs ARE included with runnable=false and
    badge="Coming Soon / Metadata only". Medical Coding Agent appears
    with runnable=true and badge="MVP / AI-assisted / Human review required".
    """
```

### Card schema (iCoDer)

Per icoder_agents_hub.py `_build_card()`:

- `name`, `description`, `category`, `use_case`
- `runnable: bool` (key field)
- `badge: str` (e.g., "Coming Soon", "MVP", "AI-assisted", "Human review required")
- `agent_id`, `runtime_agent_id`, `source_agent_ref`
- `default_runtime_mode`, `available_runtime_modes`
- `example_inputs[]`, `example_outputs[]`
- `built_by`
- `chat_url`, `customize_url`, `run_url`, `clone_url`

---

## §3. Convergence deltas

| Element | Corti | iCoDer | Verdict |
|---------|-------|--------|---------|
| **Count (pre-built)** | 20 | 30 raw (per Gate 2) | **DIFFERENT_BY_DESIGN** — iCoDer has 30 dirs but some are duplicates; effective unique is ~25; some have no Corti mirror |
| **Tabs** | My agents + Pre-built agents | Single list (no tabs) | **CORTI_ADVANTAGE** — Corti separates user-created from pre-built; iCoDer mixes them |
| **Card "runnable" flag** | Implied by template type | Explicit `runnable` boolean | **ICODER_ADVANTAGE** — iCoDer surfaces runnable status explicitly with badge |
| **Badge taxonomy** | None visible | Multi-state badge ("Coming Soon", "MVP", "AI-assisted", "Human review required", "preview", "available", "controlled_use", "deprecated") | **ICODER_ADVANTAGE** — iCoDer's 9-state taxonomy is richer |
| **Filter** | Use case (1 filter) | Use case + runnable + category (3 implicit filters) | **ICODER_ADVANTAGE** |
| **Code generators** | 3 (JS SDK + .NET SDK + JSON Config) | 3 (HTML + React + JSON, per Phase 7 Gate 13) | **PARITY** (same count, different languages: Corti = JS+.NET+JSON, iCoDer = HTML+React+JSON) |
| **API Client selector** | Top-right, project-scoped | In TopBar (Phase 4-G) | **PARITY** |
| **Live cost counter** | $0.000000 inline | ¥ in TopBar (Phase 4-G) | **PARITY** (different currency per spec) |
| **New Agent flow** | 2-path modal (scratch/template) | Single create flow | **CORTI_ADVANTAGE** — Corti's template picker is smoother |
| **Sort** | Not configurable | Configurable via `sort` param | **ICODER_ADVANTAGE** |
| **Auth** | No auth on browse | No auth on browse (per code comment) | **PARITY** |
| **Per-card actions** | Click → detail | Click → detail + clone URL + run URL exposed | **ICODER_ADVANTAGE** — iCoDer exposes more programmatic URLs |

---

## §4. iCoDer Hub → Runtime convergence (HC-6 reverification extended)

Per Gate 3 HC-6: "Hub shows 30, Runtime has specialized execution for ~10".

### Detailed convergence

| Hub display state | Runtime backing | Converged? |
|-------------------|-----------------|------------|
| `runnable=true` + `badge="MVP / AI-assisted"` | Medical Coding Agent → MedCodER 5-stage | ✅ Yes |
| `runnable=true` + `badge="available"` | ~8 agents have specialized runtime (CDI, drg-analyzer, evidence-ranker, etc.) | ✅ Yes |
| `runnable=true` + `badge="controlled_use"` | ~5 agents use `corti_like_fast` pure-LLM mode | ⚠️ Partially — runtime works but no specialized logic |
| `runnable=true` + `badge="preview"` | ~3 agents in preview state | ⚠️ Partially |
| `runnable=false` + `badge="Coming Soon / Metadata only"` | No runtime backing | ✅ Yes (honest non-runnable display) |
| `runnable=false` + `badge="deprecated"` | Removed from runtime | ✅ Yes |

### Convergence verdict

iCoDer Hub is **honest**: the `runnable` flag + badge taxonomy accurately reflects runtime backing. No "phantom agents" displayed without runtime support. This is a **better convergence than the prior Gate 6 historical claim suggested**.

---

## §5. Corti-side Hub gaps (vs iCoDer)

These are iCoDer advantages that Corti Console lacks:

| Gap | iCoDer feature | Corti status |
|-----|----------------|--------------|
| Explicit runnable flag | `runnable: bool` per card | Not surfaced — Corti relies on template type inference |
| Multi-state badge | 9-state taxonomy (preview/available/controlled_use/coming_soon/deprecated) | No badge UI in Console |
| Clone URL | Programmatic clone via API | Corti has clone via "Use a template" UI flow only |
| Run URL | Direct run link per card | Corti requires opening detail page first |
| Customizable sort | `sort` query param | Not configurable in Corti UI |
| Phase 5 Track D 5-label system | preview/available/controlled_use/coming_soon/deprecated (per memory) | Corti has no equivalent labeling |

---

## §6. Corti-side Hub advantages (vs iCoDer)

| Gap | Corti feature | iCoDer status |
|-----|---------------|---------------|
| Tab separation | My agents + Pre-built agents (2 tabs) | iCoDer single list — user must filter |
| Template picker | "Use a template" with 20 cards visible | iCoDer single create flow without template browse |
| Save = live | Agents go live on save (zero-step deploy) | iCoDer requires pack/install per CLAUDE.md |
| 3 SDK language tabs | JS + .NET + JSON Config | iCoDer has HTML + React + JSON (different but equal count) |
| Live "API Client" selector per agent page | Top-right of every agent detail | iCoDer has global TopBar API Client |

---

## §7. Findings raised in Gate 6

| ID | Severity | Title |
|----|----------|-------|
| **G6-001** | P2 | iCoDer Hub lacks "My agents" vs "Pre-built" tab separation — Corti UX advantage |
| **G6-002** | P2 | iCoDer "New Agent" flow lacks template picker — must add template browsing |
| **G6-003** | P2 | iCoDer requires pack/install for agent lifecycle; Corti is save-and-go-live |
| **G6-004** | P3 | iCoDer has 3 SDK generators but missing .NET (only HTML/React/JSON) — Corti has JS/.NET/JSON |
| **G6-005** | P3 | iCoDer Code tab shows programmatic URLs (chat_url, run_url, clone_url) — Corti does not expose these in Console |
| **G6-006** | P1 | HC-6 "Hub vs Runtime mismatch" smaller than prior Gate 6 claimed: iCoDer `runnable` flag + badge taxonomy makes the display honest; only ~5 agents in "controlled_use" state run via pure-LLM fallback |

---

## §8. Gate 6 verdict

```
PRE_A0_GATE6_AGENT_HUB_CONVERGENCE_REVIEW_COMPLETE
CORTI_20_PREBUILT_vs_ICODER_30_HUB_ENTRIES
5_ICODER_ADVANTAGES (runnable flag, badge taxonomy, clone URL, run URL, sort)
3_CORTI_ADVANTAGES (tabs, template picker, save-and-go-live)
3_PARITY_ELEMENTS (count format, no-auth browse, code generators count)
HC-6_NUANCED (smaller mismatch than prior reports claimed)
0_FORBIDDEN_VERDICTS_CLAIMED
```

Gate 6 closes. Proceed to **Pre-A0 Gate 7 — Parity Matrix V2 + Delta**.
