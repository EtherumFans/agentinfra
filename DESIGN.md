# Design System — iCoDer

## Product Context
- **What this is:** AI-powered medical coding audit console for Chinese hospitals. Coders, department heads, and insurance reviewers use it to audit ICD-10-CN diagnoses and ICD-9-CM-3 procedures.
- **Who it's for:** Medical coders (病案科), department heads, insurance reviewers (医保办), QC staff (质控科)
- **Space/industry:** Healthcare IT / medical coding / Chinese hospital information systems
- **Project type:** Web app (React SPA dashboard/console)
- **Reference:** Corti Console (console.corti.app)

## Aesthetic Direction
- **Direction:** Industrial/Utilitarian with Chinese editorial warmth
- **Decoration level:** Minimal — typography does the work
- **Mood:** A precision medical instrument built by a design-forward Chinese studio. Authoritative but warm. Functional clarity first, brand personality through restrained Chinese medical visual cues.

## Typography

| Role | Font | Rationale |
|------|------|-----------|
| Display / Brand | **DM Serif Display** | Scholarly, authoritative. Evokes medical textbooks. Only for logo and h1 headings. |
| Body / UI | **Noto Sans SC** (400/500/600/700) | Best CJK sans-serif. Excellent Chinese text readability. |
| Data / Code | **JetBrains Mono** (400/500) | Clear distinction between I/l/1 and O/0. Critical for ICD codes like I25.101. |
| Fallback | Noto Serif SC (brand), IBM Plex Mono (code), system-ui (body) | |

**Loading:** Google Fonts with `preconnect` + `display=swap`

**Scale:** 12/14/16/20/24/32/40px (xs/sm/base/lg/xl/2xl/3xl/4xl)

## Color

**Approach:** Balanced — vermillion accent (sparingly), jade secondary (confirmation/accuracy), warm neutrals throughout.

| Token | HSL | Hex | Usage |
|-------|-----|-----|-------|
| Background | 40 14% 98% | `#FAFAF8` | Page background |
| Surface | 0 0% 100% | `#FFFFFF` | Cards, panels |
| Primary text | 40 6% 9% | `#1A1A18` | Body text |
| Muted text | 40 4% 43% | `#706F6A` | Secondary text |
| **Vermillion (accent)** | 9 68% 48% | `#D4442A` | Active nav, primary CTA, logo mark |
| **Jade (secondary)** | 155 33% 38% | `#3D7A5C` | Confirmed codes, accuracy, success |
| Border | 40 10% 89% | `#E8E6E1` | Card borders, dividers |
| Warm hover | 40 12% 94% | `#F0EDE8` | Hover states |
| Warm muted | 40 10% 95% | `#F5F3EF` | Muted backgrounds |

**Semantic colors:**
- Success: Jade 155 33% 38%
- Error: Red 0 72% 48%
- Warning: Amber 40 45% 40%
- Info: Blue 200 50% 35%

**Design rationale:** Vermillion (朱红) is the color of Chinese medical seals — it encodes "authority" and "verification" without words. Jade (玉色) is the color of healing and precision in Chinese tradition. Together they signal "trusted audit" and "accurate coding."

## Spacing
- **Base unit:** 4px
- **Density:** Comfortable — Chinese characters need more breathing room than Latin
- **Scale:** 2xs(2) xs(4) sm(8) md(16) lg(24) xl(32) 2xl(48) 3xl(64)

## Layout
- **Approach:** Grid-disciplined (workbench) + hybrid (console/dashboard)
- **Max content width:** 1280px for reading, full-width for workbenches
- **Border radius:** Hierarchical — sm(4px) md(6px) lg(8px) xl(12px) 2xl(16px) 3xl(24px)
- **Sidebar:** 48px collapsed / 256px expanded

## Motion
- **Approach:** Minimal-functional — only transitions that aid comprehension
- **Easing:** ease-out (enter), ease-in (exit), ease-in-out (move)
- **Duration:** 150ms (standard), never >700ms
- **No scroll animations, no decorative motion**

## Component Patterns
- **Cards:** Only when card IS the interaction. No decorative card grids.
- **Buttons:** Vermillion for primary CTA. Ghost for secondary. 44px minimum touch target.
- **Inputs:** Clean borders, warm white bg, 44px minimum height.
- **Status:** Jade (confirmed/supported), amber (needs review), red (error/unsupported).

## Product Positioning

**iCoDer is a medical AI agent development platform for Chinese hospitals.**

- **Target users:** Developers building healthcare AI applications, ISVs integrating AI into HIS/EMR systems.
- **Not a coding workbench:** The Console is a developer reference implementation, not a coder's daily tool.
- **Platform-first:** SDK/API/Skills as primary surface. Console as onboarding and management tool.

### Platform Capabilities

| Capability | Status | Description |
|-----------|--------|-------------|
| Speech To Text | ✅ | Real-time medical dictation, voice commands, dual-engine (FunASR/Web) |
| Fact Extraction | ✅ | Clinical text → structured facts (diagnosis/procedure/negated/timing) |
| Text Generation | ✅ | 13 medical templates, LLM document generation |
| Medical Coding | ✅ | ICD-10-CN diagnosis + ICD-9-CM-3 procedure coding with evidence |
| Embedded Assistant | ✅ | Web Component for 3rd-party HIS/EMR integration |
| Agentic Framework | ✅ | 39 prebuilt experts, agent creation with AI-generated prompts, SSE streaming |
| Agent Skills | ✅ | 4 `.well-known/agent-skills/` SKILL.md files for AI coding agent discoverability |
| OAuth 2.0 + PKCE | ✅ | Client credentials, authorization code, token management |
| SDK Code Generation | ✅ | JavaScript, Python, C#/.NET, JSON Config auto-filled from UI config |
| API Playground | ✅ | Interactive API testing in Developer Quickstart |
| API Documentation | ✅ | FastAPI auto-generated Swagger (OpenAPI 3.0) |
| Usage Monitoring | ✅ | Real-time credit tracking, usage history with charts |
| Usage Alerts | ✅ | Low balance alerts, auto top-up with localStorage persistence |

### Product Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-05-06 | Initial design system | Vermillion+jade palette. DM Serif Display, Noto Sans SC, JetBrains Mono. |
| 2026-05-20 | Remove coding workbench pages | Align with developer platform positioning. Audit cockpit belongs in end-user tools, not the platform Console. |
| 2026-05-20 | Unify all pages to Apple minimalist design | 27 pages using semantic tokens (bg-muted/20, rounded-xl shadow-sm ring-1 ring-border/20). Zero hardcoded hex colors, zero text-gray-*, zero bg-foreground. |
| 2026-05-20 | Replace all alert()/confirm() with modal dialogs | UX polish. Inline error banners + confirmation modals throughout. |
| 2026-05-20 | Complete i18n coverage | 463 keys across zh-CN + en-US. All UI text in Chinese with English fallback. |
| 2026-05-21 | Remove Code Dictionaries & Rule Libraries from Console | These are backend data services exposed via API, not Console pages. SDK users call them programmatically. |
| 2026-05-21 | Add API Playground to Developer Quickstart | Interactive API testing reduces time-to-first-call for new developers. |
| 2026-05-21 | Connect API docs to Swagger | FastAPI auto-generates OpenAPI spec. Console sidebar links point to live Swagger UI. |

## Design System

### Component Patterns
- **Cards:** `bg-background rounded-xl shadow-sm ring-1 ring-border/20`
- **Section headers:** `w-1 h-4 rounded-full bg-primary/40` accent bar + uppercase tracking-wider label
- **Buttons:** `bg-primary text-primary-foreground rounded-lg` for primary. Ghost for secondary.
- **Layout:** 75/25 split with `bg-border/40` separator. Left content `bg-muted/20`, right panel `bg-muted/10`.
- **Error states:** `bg-destructive/10 border border-destructive/20 text-destructive` dismissible banner.
- **Modals:** `fixed inset-0 z-50 bg-black/40` overlay + `bg-card rounded-xl border border-border shadow-xl` card.
- **Empty states:** Icon + centered text, muted colors.

### Quality Standards
- Zero `alert()` / `confirm()` — all modal or inline
- Zero hardcoded hex colors — all semantic tokens
- Zero `text-gray-*` / `bg-foreground` — all `text-muted-foreground` / `bg-primary`
- 463 i18n keys, zh-CN + en-US in sync
- All pages Apple minimalist: Noto Sans SC body, JetBrains Mono code, vermillion accent
