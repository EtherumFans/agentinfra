# Phase 4-D — taste-skill Design Audit Report

> Audit scope: iCoDer Agent pages (AgentsPage hub + AgentChatPage + AgentConfigSidebar)
> Audit tool: [taste-skill `redesign-existing-projects`](https://github.com/Leonxlnx/taste-skill) — 178-line checklist
> Audit date: 2026-07-08
> Auditor: Claude Code (taste-skill-assisted)

## 1. Tech Stack Scan

| Layer | Stack |
|-------|-------|
| Framework | React 18 + TypeScript + Vite |
| Styling | Tailwind CSS v3 (semantic HSL tokens, no `@apply` soup) |
| Icons | `lucide-react` (exclusive) |
| Fonts (loaded) | Noto Sans SC (sans) + JetBrains Mono (mono) + DM Serif Display (brand) |
| Color palette | Vermillion primary `hsl(9 68% 48%)` + Jade secondary `hsl(155 33% 38%)` + warm neutral grays |
| i18n | Custom `useT()` hook, 2 locales (zh-CN default, en-US) |

**Verdict**: Stack is solid. No framework migration needed. Audit focuses on Tailwind patterns + component composition.

## 2. Design Audit Findings (by taste-skill category)

### 2.1 Typography — 4 issues

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| T1 | **DM Serif Display loaded but never used** — declared in `tailwind.config.js:52` as `font-brand`, but no agent page uses `font-brand`. Wasted 17KB woff2 download. | `index.html:9` loads it; 0 usages in `AgentChatPage.tsx` / `AgentConfigSidebar.tsx` / `AgentsPage.tsx` | Med |
| T2 | **Chat message body has no max-width** — user/agent bubbles can stretch to 85% viewport, lines exceed 65ch readability limit. | `AgentChatPage.tsx` MessageBubble `max-w-[85%]` | Med |
| T3 | **Only 400/500/600 weights used** — no SemiBold (600) for hierarchy emphasis, no Bold (700) for agent identity. Agent name in header uses `font-semibold` (600) but is `text-sm` — lacks presence. | `AgentChatPage.tsx:181` header; `AgentConfigSidebar.tsx:82` labels | Small |
| T4 | **No tabular-nums on counters** — `28/50` char counter + `0 字符` use proportional numerals, jitter on input. | `AgentConfigSidebar.tsx:94`; `AgentChatPage.tsx` bottom bar | Small |

**Fix recommendations**:
- T1: Either use `font-brand` for the agent name in the chat header (premium editorial feel) or remove the DM Serif Display `<link>` from `index.html` to save 17KB.
- T2: Wrap message text in `max-w-[65ch]` (Corti spec — their chat bubbles cap at ~600px).
- T3: Bump agent name to `text-base font-bold` (700) for header presence; keep `text-sm font-semibold` for in-bubble names.
- T4: Add `tabular-nums` Tailwind class to all counters.

### 2.2 Color and Surfaces — 3 issues

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| C1 | **Generic `shadow-sm` + `ring-1 ring-border/20` on every card** — taste-skill calls this out verbatim: "Generic card look (border + shadow + white background). Remove the border, or use only background color, or use only spacing." | `AgentChatPage.tsx` greeting card + result card; `AgentsPage.tsx` hub cards | Med |
| C2 | **Pure-black shadows at low opacity** — Tailwind default `shadow-sm` = `0 1px 2px rgba(0,0,0,0.05)`. Shadows should carry the background hue (warm gray tint). | All `shadow-*` usages | Small |
| C3 | **Avatar backgrounds use only 2 hues** — `bg-primary/15` for user, `bg-muted` for agent. No semantic differentiation for agent subtypes (medical-coding vs compliance-guardrail). | `AgentChatPage.tsx` MessageBubble avatar | Small |

**Fix recommendations**:
- C1: Drop `ring-1 ring-border/20` from chat cards; rely on `bg-background` contrast against `bg-muted/20` page background. Keep `shadow-sm` only on hover.
- C2: Define a custom Tailwind shadow `shadow-warm` = `0 1px 3px hsl(40 30% 20% / 0.06)` matching the warm palette.
- C3: Map agent_id → avatar tint (medical-coding=vermillion, compliance=jade, code-validation=amber) for visual variety.

### 2.3 Layout — 3 issues

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| L1 | **No max-width container** — chat page + hub page stretch edge-to-edge on wide screens. On 2560px displays, content spans 2560px; lines become unreadable. | `AgentChatPage.tsx` root div; `AgentsPage.tsx` hub grid | Med |
| L2 | **Uniform `rounded-xl` (12px) on every card** — no radius tiering. Inner elements (chips, badges) also use `rounded-md` (6px), but containers and bubbles share `rounded-xl`/`rounded-lg` — flat hierarchy. | throughout | Small |
| L3 | **Symmetric padding everywhere** — `px-6 py-3`, `px-6 py-4` — taste-skill: "Top and bottom padding are always identical. Adjust optically — bottom padding often needs to be slightly larger." | breadcrumb bar, header, input bar | Small |

**Fix recommendations**:
- L1: Wrap chat + hub content in `max-w-[1440px] mx-auto` container. Corti console caps at 1440px.
- L2: Tier the radius: page containers `rounded-2xl` (16px), cards `rounded-xl` (12px), inner chips `rounded-md` (6px), badges `rounded-xs` (2px) — visual hierarchy through radius.
- L3: Use asymmetric padding `pt-3 pb-4` on header bars for optical balance.

### 2.4 Interactivity and States — 4 issues

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| I1 | **No active/pressed feedback on buttons** — taste-skill: "Add a subtle `scale(0.98)` or `translateY(1px)` on press to simulate a physical click." Zero `active:` classes in agent pages. | All buttons (Add context, Use Agent, Customize, etc.) | Med |
| I2 | **Generic `Loader2 animate-spin` spinner** — taste-skill: "Replace generic circular spinners with skeleton loaders that match the layout shape." | `AgentChatPage.tsx` loading state | Med |
| I3 | **Empty state is text-only** — "无固定消息片段" + "无专家" are plain `<p>` text. taste-skill: "Design a composed 'getting started' view." | `AgentConfigSidebar.tsx:135,168` | Small |
| I4 | **Default transition duration** — `transition-colors` uses Tailwind default 150ms. taste-skill: "Add smooth transitions (200-300ms) to all interactive elements." | throughout | Small |

**Fix recommendations**:
- I1: Add `active:scale-[0.98] transition-transform` to all primary buttons (Add context, Use Agent, Customize, Send).
- I2: Replace `Loader2` in chat loading with a 3-line skeleton bubble matching agent message shape (avatar block + 3 text lines).
- I3: Compose empty states with an icon + heading + CTA. Pinned parts empty state: pin icon + "No pinned parts" + "Pin a message part to anchor the agent's behavior" helper text.
- I4: Use `duration-200` explicitly on all `transition-colors`.

### 2.5 Content — 1 issue

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| N1 | **"(Clone)" suffix on agent name** — functional but unpolished. Corti shows the agent name cleanly; the clone status is communicated via breadcrumb. | `AgentChatPage.tsx` header + breadcrumb | Small |

**Fix recommendation**:
- N1: Drop "(Clone)" from the displayed name; surface clone status via a small "Cloned from {agent_ref}" subtitle under the breadcrumb, or omit entirely (the breadcrumb `> source: icoder/medical-coding-agent@2.0.0` already conveys this).

### 2.6 Component Patterns — 2 issues

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| P1 | **Pill-shaped badges everywhere** — `rounded-full` on red_lines chips (no_upcoding, evidence_required), `rounded-md` on maturity chips. taste-skill: "Pill-shaped 'New' and 'Beta' badges. Try square badges, flags, or plain text labels." | `AgentsPage.tsx:532-538` red_lines chips | Small |
| P2 | **Modal stubs are placeholders** — Expert Library modal + Add expert dropdown show "coming soon (Phase 5)" text. taste-skill: "Dead links. Buttons that link to `#`. Either link to real destinations or visually disable them." | `AgentConfigSidebar.tsx:234-263` | Small |

**Fix recommendations**:
- P1: Replace `rounded-full` with `rounded-xs` (2px) for red_lines chips — they read as labels, not status pills.
- P2: Disable the "Browse Expert Library" + "Add expert" buttons visually (`disabled`, `opacity-50`, `cursor-not-allowed`) and add `title="Coming in Phase 5"` tooltip instead of opening empty modals.

### 2.7 Iconography — 2 issues

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| G1 | **Lucide exclusively** — taste-skill verbatim: "Lucide or Feather icons exclusively. These are the 'default' AI icon choice. Use Phosphor, Heroicons, or a custom set for differentiation." | All agent pages | Med |
| G2 | **Cliché metaphors** — `Bot` icon for agent avatar, `Send` for submit, `AlertCircle` for errors, `CheckCircle2` for success. These are the most generic AI icon choices. | throughout | Small |

**Fix recommendations**:
- G1: Evaluate Phosphor Icons (`@phosphor-icons/react`) as a Lucide replacement — same API but more visual character. OR mix Lucide with custom SVGs for branded moments (logo, agent avatar).
- G2: For agent avatars, use a monogram (first 2 chars of agent_id, uppercase, `font-mono`) instead of `Bot` icon — Corti uses monogram avatars.

### 2.8 Code Quality — 2 issues

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| Q1 | **Arbitrary Tailwind values** — `w-[400px]`, `w-[280px]`, `max-w-[200px]`, `max-w-[85%]`. taste-skill: "Hardcoded pixel widths. Use relative units (`%`, `rem`, `em`, `max-width`) for flexible layouts." | `AgentConfigSidebar.tsx:229`; `AgentChatPage.tsx` MessageBubble | Small |
| Q2 | **Mixed semantic + non-semantic HTML** — sidebar uses `<aside>` (semantic), but message history uses `<div>` for bubbles. Could use `<article>` for each message turn. | `AgentChatPage.tsx` MessageBubble | Small |

**Fix recommendations**:
- Q1: Replace `w-[400px]` with `w-96` (24rem = 384px, close enough) or define a `w-sidebar` theme token. Replace `max-w-[85%]` with `max-w-prose` (65ch).
- Q2: Wrap each MessageBubble in `<article>` for screen reader semantics.

### 2.9 Strategic Omissions — 2 issues

| # | Issue | Where | Severity |
|---|-------|-------|----------|
| S1 | **No custom 404 page** — App.tsx redirects `*` to `/`. taste-skill: "Design a helpful, branded 'page not found' experience." | `App.tsx:134` | Small |
| S2 | **No "skip to content" link** — accessibility omission. taste-skill: "Essential for keyboard users. Add a hidden skip-link." | `Layout.tsx` | Small |

**Fix recommendations**:
- S1: Create a branded `NotFoundPage.tsx` with the iCoDer logo, a friendly message in both locales, and a CTA back to `/ai-studio/agents`.
- S2: Add `<a href="#main-content" class="sr-only focus:not-sr-only ...">Skip to content</a>` as the first child of `Layout.tsx`.

## 3. Tally

| Category | Issues | Critical | Med | Small |
|----------|--------|----------|-----|-------|
| Typography | 4 | 0 | 2 | 2 |
| Color/Surfaces | 3 | 0 | 1 | 2 |
| Layout | 3 | 0 | 1 | 2 |
| Interactivity | 4 | 0 | 2 | 2 |
| Content | 1 | 0 | 0 | 1 |
| Components | 2 | 0 | 0 | 2 |
| Iconography | 2 | 0 | 1 | 1 |
| Code Quality | 2 | 0 | 0 | 2 |
| Strategic | 2 | 0 | 0 | 2 |
| **Total** | **23** | **0** | **7** | **16** |

**Zero critical issues**. The agent pages are functional and Corti-spec-compliant. The 7 medium issues are the highest-leverage fixes.

## 4. Recommended Fix Priority (taste-skill order)

Per taste-skill "Fix Priority" §:
1. **Font swap** (T1) — use `font-brand` for agent name in chat header OR remove the unused DM Serif Display link. Biggest instant improvement, lowest risk.
2. **Color palette cleanup** (C1, C2) — drop `ring-1 ring-border/20` from cards; define `shadow-warm` token.
3. **Hover and active states** (I1) — add `active:scale-[0.98]` to all primary buttons.
4. **Layout and spacing** (L1, L2) — wrap content in `max-w-[1440px] mx-auto`; tier border-radius.
5. **Replace generic components** (I2, G2) — skeleton loader for chat loading; monogram avatar instead of `Bot` icon.
6. **Add loading/empty/error states** (I3) — compose pinned-parts empty state with icon + heading + CTA.
7. **Polish typography scale** (T2, T3, T4) — `max-w-[65ch]` on message text; `font-bold` for agent name; `tabular-nums` on counters.

## 5. Corti Parity Cross-Check

Re-walked Corti `console.corti.app/ai-studio/agents/{id}` after audit. Findings:

| Corti does | iCoDer does | Gap |
|------------|-------------|-----|
| Agent name in `font-serif` (Corti uses a serif for branding) | `font-sans font-semibold` | T1 fix closes this |
| Chat bubbles cap at ~600px width | `max-w-[85%]` (unbounded on wide viewports) | T2 fix closes this |
| Cards have no border, only background contrast | `ring-1 ring-border/20` on every card | C1 fix closes this |
| Active button press = subtle scale | No active state | I1 fix closes this |
| Loading = skeleton matching message shape | Generic `Loader2` spinner | I2 fix closes this |
| Agent avatar = monogram (2-char uppercase) | `Bot` lucide icon | G2 fix closes this |

**Conclusion**: 6 of 7 medium issues directly close Corti parity gaps. The taste-skill audit confirms the Corti replication is **functionally complete** (D-1~D-6 ✅) but **visually still 6 fixes away from premium parity**.

## 6. Next Steps (Recommended)

- **Phase 4-E1 (quick wins, ~2hr)**: T1 + T4 + I1 + I4 + C1 + L2 + P1 + N1 + P2 — all small/med fixes that don't change layout structure.
- **Phase 4-E2 (structural, ~4hr)**: L1 (max-width container) + T2 (message max-w) + I2 (skeleton loaders) + I3 (composed empty states) + G2 (monogram avatars).
- **Phase 4-E3 (differentiation, ~3hr)**: G1 (evaluate Phosphor Icons) + C3 (agent-tinted avatars) + S1 (custom 404) + S2 (skip-link).

Total: ~9 hours of polish work to take iCoDer agent pages from "Corti-functional" to "premium product quality".
