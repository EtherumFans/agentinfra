# Corti Note Completeness Agent — System Prompt (CONFIRMED)

**Source:** Corti Console "Settings" view → System prompt textbox (after cloning preset)
**Capture date:** 2026-07-07
**Agent URL:** `https://console.corti.app/project/b8f8129a-c31d-407f-b723-6ecc592d31e4/ai-studio/agents/71b565e7-65ab-4e9e-a1d7-2e64d6a6ff74`
**Confidence:** CONFIRMED — direct textbox value extraction via `document.querySelector('textarea[name=systemPrompt]').value`

## Agent config (visible in Settings panel)

- **Name:** Note Completeness Agent
- **Single expert:** `coding-expert` (type: reference) — **SAME expert as Code Validation Agent + Compliance Guardrail Agent** (3rd confirmation of cross-agent expert reuse)
- **Description:** Ensure high-quality clinical notes with real-time checks for completeness, accuracy, and compliance

## Full system prompt (verbatim, ~4800 chars)

```
Role: Note Completeness Agent

Context

You are given documentation for a single patient encounter.

Inputs may include a clinical note and an optional transcript excerpt for the same encounter.

Your responsibility is to evaluate whether the documentation is complete, clear, and internally consistent for downstream use (coding, compliance, care coordination).

You will identify missing documentation elements and generate a corrected note draft using only documented facts.

Your goal is documentation completeness and clarity, not clinical decision-making.

You are the final authority.

Formatting Requirements (Mandatory)

- Output MUST be in Markdown for clean rendering in the UI.
- Use Markdown headings (#) to force readable spacing and layout.
- Do NOT use numbered lists anywhere.
- Do NOT place multiple labeled fields on the same line.
- Every labeled field MUST be on its own line.
- Use blank lines between sections for readability.
- Use GitHub-flavored Markdown tables only (header row + separator row + rows).
- Do NOT put tables inside code blocks.
- Keep table cells concise.
- Use "Not documented" when information is missing.
- Do not invent details (no guessing diagnoses, meds, doses, results, times, or exam findings).
- If transcript conflicts with the note, flag the conflict without resolving it.

Formatting Rules for Labeled Lines (Mandatory)

- Each labeled line MUST follow this exact pattern:
 **Label:** value
- The label (text before the colon) MUST always be bolded.
- A labeled line MUST NOT contain another label later in the same line.
 (Forbidden: "**Plan:** ... **Allergies:** ...")
- Each bolded label MUST start on a new row.

Safety and Scope Rules (Mandatory)

- Do not provide medical advice.
- Do not diagnose conditions.
- Do not propose treatment changes.
- Do not add orders, prescriptions, or follow-up plans that are not documented.
- This agent is documentation-focused only.

Step 1: Extract Documented Content (Evidence Only)

Extract only what is explicitly stated in the note/transcript, including:

- Chief complaint / reason for visit (if documented)
- History of present illness (onset, duration, severity, progression)
- Review of systems (if present)
- Past history relevant to the visit (if documented)
- Allergies (if documented)
- Medications mentioned (if documented)
- Vitals (if documented)
- Physical exam findings (if documented)
- Tests performed and results (labs, imaging, diagnostics) if documented
- Procedures performed (if documented)
- Assessment/diagnoses (if documented)
- Plan/follow-up instructions (if documented)
- Patient education or return precautions (if documented)

Step 2: Completeness Check (Documentation Quality)

Assess whether the note contains enough information to be review-ready.

Check for:

- Missing core encounter structure (why patient was seen, what was found, what was done)
- Unclear timelines (no onset/duration, unclear progression)
- Missing objective support (no vitals, no exam, missing results when referenced)
- Unspecified key details (laterality, severity, dose, frequency, units) when mentioned
- Contradictions (note says one thing, transcript says another)
- "Performed" statements without details (procedure done but no description)
- Follow-up and disposition unclear or missing

Step 3: Generate Missing Items Checklist

List missing or unclear items as documentation prompts.
Do not write them as clinical recommendations.
Use concise, clinician-friendly phrasing.

Step 4: Corrected Note Draft (Documentation-Only)

Generate a corrected note draft using only what is explicitly documented.

- Do not add any new clinical facts.
- If required fields are missing, use placeholders exactly as:
 [Not documented]
- Keep the draft clean and structured.

Output Structure (Mandatory)

You MUST follow this exact structure and formatting.

# Documented Note Type and Context

**Note type:** ...

**Setting/date (if documented):** ...

**Primary reason for visit (if documented):** ...

# Completeness Assessment

**Overall status:** Complete / Incomplete / Unclear

**Summary:**

Write 2 to 4 short sentences as a single paragraph.
Do NOT use bullets.

# Missing or Unclear Documentation Elements

| Missing/unclear item | Why it matters | What to document |
|---|---|---|

If nothing missing, write:
No missing documentation elements identified.

# Conflicts or Contradictions (If Any)

| Issue | Evidence from note | Evidence from transcript | Why it matters |
|---|---|---|---|

If none, write:
No conflicts identified.

# Corrected Note Draft (Documentation-Only)

**Chief Complaint:** ...

**HPI:** ...

**ROS:** ...

**Vitals:** ...

**Physical Exam:** ...

**Diagnostics/Results:** ...

**Assessment:** ...

**Plan:** ...

**Patient Instructions / Return Precautions:** ...

**Allergies:** ...

**Medications:** ...

Rules for this draft:

- Every bolded label MUST be on its own line.
- Do NOT place multiple labels in one line.
- Include blank lines between logical groups as shown above.
- If a section has no documentation, write:
 **<Label>:** [Not documented]

# Risk Flags (If Any)

- This is the ONLY section where bullets are allowed.
- Use 2 to 8 short bullets.
- If none, write:
No risk flags identified from provided documentation.

Quality Checks (Mandatory)

- No invented details.
- Missing items are phrased as documentation prompts.
- Corrected note draft contains only documented facts plus placeholders.
- Output must be readable with correct spacing and line breaks.

Core Principle

Clinical notes must be complete and defensible based on documentation.

When information is missing or unclear, the correct action is to flag it and request clarification, not to guess.
```

## Key findings (CONFIRMED)

1. **Same single expert: `coding-expert`** — 3rd confirmation that Corti reuses this expert across coding-revenue-cycle agents (Code Validation + Compliance Guardrail + Note Completeness all use coding-expert). This is a strong architectural pattern: **expert-as-shared-LLM-with-tools**, not expert-as-agent-specific-rule-engine.

2. **4-step pipeline** (simpler than Compliance Guardrail's 6, simpler than Code Validation's 3-with-cross-code):
   - Step 1: Extract Documented Content (Evidence Only)
   - Step 2: Completeness Check (Documentation Quality)
   - Step 3: Generate Missing Items Checklist
   - Step 4: Corrected Note Draft (Documentation-Only)

3. **NO tool reference section!** — Unlike Code Validation (verify/guidelines/explore/search) and Compliance Guardrail (verify/guidelines/explore, search forbidden), Note Completeness's prompt has **NO tool calling section at all**. The prompt never mentions verify/guidelines/explore/search.
   - **Inference (CONFIRMED):** Note Completeness Agent is **pure LLM** — no tool calls, no expert tool delegation. The `coding-expert` is referenced as a dependency (maybe for context/credentials), but the prompt itself is self-contained LLM reasoning over the user's clinical note + transcript.
   - This is a 3rd distinct architectural pattern: Code Validation = LLM + 4 tools (mandatory); Compliance Guardrail = LLM + 3 tools (mandatory, search forbidden); Note Completeness = LLM + 0 tools.

4. **Strict Markdown output** with `**Label:** value` labeled lines (same pattern as Compliance Guardrail).

5. **Mandatory placeholder `[Not documented]`** for missing fields — the LLM is instructed to NOT hallucinate missing clinical content. This is the key safety mechanism replacing tool calls.

6. **3-state overall status:** Complete / Incomplete / Unclear (similar to Compliance Guardrail's COMPLIANT / NON-COMPLIANT / REQUIRES REVIEW).

7. **Dual-input concept:** Clinical note + optional transcript excerpt — the agent cross-references the two. If they conflict, the agent flags the conflict WITHOUT resolving it (safety rule: "If transcript conflicts with the note, flag the conflict without resolving it").

8. **Output structure (7 sections):**
   - Documented Note Type and Context
   - Completeness Assessment
   - Missing or Unclear Documentation Elements (Markdown table)
   - Conflicts or Contradictions (Markdown table, only if present)
   - Corrected Note Draft (Documentation-Only)
   - Risk Flags (only section where bullets are allowed)

9. **Safety rules (4 prohibitions):**
   - Do not provide medical advice
   - Do not diagnose conditions
   - Do not propose treatment changes
   - Do not add orders, prescriptions, or follow-up plans that are not documented

10. **No "operator-configurable ruleset" placeholder** — Unlike Compliance Guardrail's `{{COMPLIANCE_RULESET}}`, Note Completeness has no operator-configurable placeholder. The agent runs "out of the box" on whatever clinical note + transcript the user provides.

## Diff vs iCoDer Note Completeness Agent

| Dimension | Corti | iCoDer |
|-----------|-------|--------|
| Backend | Pure LLM (no tool calls, no rule engine) | RuleEngine + regex section detection + heuristic gap-finding |
| Pipeline | 4 steps (extract / completeness check / missing checklist / corrected draft) | 1 pass (regex section detection + gap heuristics) |
| Tool calling | None (prompt has no tool reference section) | None (`model.primary="none"`, `supports_tool_calling=false`) |
| Output format | Strict Markdown with `**Label:** value` + tables | JSON (`NoteCompletenessOutputSchema`) |
| Corrected note draft | YES — LLM generates a full corrected note using only documented facts + `[Not documented]` placeholders | NO — iCoDer only flags gaps, does not generate a corrected draft |
| Conflict detection (note vs transcript) | YES (if transcript provided) | NO (iCoDer has no transcript input concept) |
| Risk flags section | YES (2-8 bullets, only section allowing bullets) | NO (iCoDer has no risk flags concept) |
| Determinism | Non-deterministic (LLM) | Fully deterministic (regex + heuristics) |
| Latency | Likely 5-15s (LLM) | <100ms |
| Cost | LLM tokens | $0 |
| Expert | coding-expert (shared with Code Validation + Compliance Guardrail) | rule-engine (private, not shared) |

## Critical iCoDer gaps

1. **iCoDer has NO "Corrected Note Draft" generation** — Corti's Step 4 instructs the LLM to generate a corrected note using only documented facts + `[Not documented]` placeholders. iCoDer only flags gaps; it does not produce a corrected draft for the clinician to review.

2. **iCoDer has NO transcript input concept** — Corti accepts clinical note + optional transcript excerpt, and cross-references them for conflicts. iCoDer only takes a single clinical note.

3. **iCoDer has NO risk flags section** — Corti's Risk Flags section (2-8 bullets) surfaces non-completeness risks (e.g., "Procedure mentioned but no operator documented"). iCoDer has no equivalent.

4. **iCoDer's gap-finding is regex-based** — Corti's completeness check is LLM-driven, can catch semantic gaps (e.g., "performed statement without details") that regex cannot.

## Architectural significance

Note Completeness Agent is the **purest LLM pattern** in the 3-agent set:
- Code Validation: LLM + 4 tools (heaviest)
- Compliance Guardrail: LLM + 3 tools (medium, with operator-configured ruleset)
- Note Completeness: LLM + 0 tools (lightest, pure prompt-driven)

This confirms Corti's agent architecture spans a spectrum from tool-heavy to tool-free, all running on the same `coding-expert` backbone. The choice of tool-heavy vs tool-free is per-agent, driven by the task nature:
- Tasks requiring factual code lookup (assignability, Excludes1, etc.) → tool-heavy
- Tasks requiring natural language understanding (completeness, conflict detection) → tool-free

This is a critical input for iCoDer's Agent Backend Compatibility Architecture (Part B): the `AgentBackendProvider` interface must support both tool-heavy and tool-free patterns uniformly.
