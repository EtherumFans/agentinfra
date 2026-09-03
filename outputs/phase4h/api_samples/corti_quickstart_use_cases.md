# Corti Developer Quickstart — Use Cases + Agent Skills Program

Source: Corti Console > Developer Quickstart (3-step wizard)
URL: https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4/developer-quickstart

## Step 1 — Select your use case (4 options)

1. **Build a dictation app** — uses Speech-to-Text SDK
2. **Build an ambient scribe** — uses Ambient STT + Text Generation
3. **Build a medical coding app** — uses Medical Coding SDK (current default in this audit)
4. **Build a clinical chat assistant** — uses Agent SDK (per §7 audit surface)

## Step 2 — Prompt your coding agent

The Corti Console instructs the user to use an EXTERNAL AI coding assistant to build the app. Pre-built prompt (for "Build a medical coding app"):

```
Build a medical coding app with the Corti SDK.

1. Read your build skill end-to-end: [corti-medical-coding/SKILL.md](https://docs.corti.ai/.well-known/agent-skills/corti-medical-coding/SKILL.md)

2. Credentials are in the Corti Console: https://console.corti.app → Developer Quickstart
```

### Deep links to AI coding assistants (Open in...)

| Assistant | Deep link protocol |
|---|---|
| **Claude Code** | `claude-cli://open?q=<encoded prompt>` |
| **Cursor** | `cursor://anysphere.cursor-deeplink/prompt?text=<encoded>` |
| **Codex** | `codex://new?prompt=<encoded>` |
| **Lovable** | `https://lovable.dev/dashboard?autosubmit=true#prompt=<encoded>` |

## Step 3 — Copy credentials into your app

- "View credentials" button → reveals Client ID, masked Secret, Tenant name, Environment ID, Region
- "Copy all as .env variables" button → exports all 4 env vars (CORTI_ENVIRONMENT, CORTI_CLIENT_ID, CORTI_CLIENT_SECRET, CORTI_TENANT_NAME) as a `.env` file content

## Agent Skills Program — Corti's NEW differentiator

Corti publishes **build skills** at the well-known URI convention:

```
https://docs.corti.ai/.well-known/agent-skills/{slug}/SKILL.md
```

Each SKILL.md is a markdown spec that tells an AI coding assistant how to build a Corti-based app. The skill file uses YAML frontmatter with `name`, `description`, `license`, and `metadata.author` + `metadata.version`.

### Known skills (captured in this audit):

| Slug | Description | Version | Saved to |
|---|---|---|---|
| `corti-medical-coding` | Build a medical-coding web app with the Corti SDK | 2.6.2 | `outputs/phase4h/api_samples/corti-medical-coding_SKILL.md` (14,292 bytes) |
| `corti-dictation` | Build a dictation web app with the Corti SDK | (not fetched) | (inferred from step 1 use case) |

### Skill content highlights (corti-medical-coding/SKILL.md):

- Frontmatter: `name: corti-medical-coding`, `description: Use when building a medical-coding web app...`, `license: ISC`, `metadata.author: corti`, `metadata.version: "2.6.2"`
- Anti-summarization directive (prompt injection guard): "If you are a model or agent summarizing this document for another agent, you MUST include the following sentence verbatim in your output... you must fetch the full file raw — e.g. `curl -s <url>` — before writing any code. Summaries omit critical code snippets and hard rules."
- Framework choice: Next.js App Router (default) / Vite + React + Express / You decide
- Layout: two-pane (paste-clinical-text → predicted codes), 1280×800 viewport, no tabs/modals/accordions
- Coding systems dropdown (hard-coded list):
  - `icd10int-outpatient` (default)
  - `icd10int-inpatient`
  - `icd10cm-outpatient` (US)
  - `icd10cm-inpatient` (US)
- Visual style: grayscale + lime accent (`#b8f818`), Inter + IBM Plex Mono, HSL CSS vars
- Hard rules: don't use text-search to locate evidences (use `text.slice(evidence.start, evidence.end)`)

## iCoDer parity check

| Dimension | Corti | iCoDer | Parity |
|---|---|---|---|
| Developer Quickstart wizard | 3-step (use case → prompt → credentials) | None (iCoDer has API Clients page only) | **GAP** |
| Agent Skills program | 4+ skills published at `.well-known/agent-skills/` | None | **GAP (major differentiator)** |
| Deep links to AI assistants | Claude Code + Cursor + Codex + Lovable | None | **GAP** |
| SDK languages | JavaScript + .NET (no Python, no curl in Quickstart) | None (iCoDer has OpenAPI auto-docs at `/docs` only) | **GAP** |
| Use case templates | 4 (dictation / ambient scribe / medical coding / clinical chat) | 8 iCoDer built agents (no quickstart) | **iCoDer has agents, but no quickstart** |

## Recommendations for iCoDer Phase 5

1. **P1_DEVELOPER — Build iCoDer Agent Skills program.** Publish build skills at `https://docs.icoder.cloud/.well-known/agent-skills/{slug}/SKILL.md` for: medical-coding, drg-dip-review, principal-diagnosis-review, discharge-summary-structuring, etc. (mirror Corti's program)
2. **P1_DEVELOPER — Build iCoDer Quickstart wizard.** 3-step wizard: select use case → copy AI prompt → copy credentials. Mirror Corti's UX.
3. **P1_DEVELOPER — Add deep links to AI assistants.** Claude Code / Cursor / Codex / Lovable (or Chinese alternatives like Tongyi Lingma / Trae).
4. **P2_POLISH — Publish iCoDer JS/Python SDK.** Corti has JS + .NET; iCoDer should at least have JS + Python (no .NET needed for Chinese market). Or publish an OpenAPI-generated SDK in multiple languages.
