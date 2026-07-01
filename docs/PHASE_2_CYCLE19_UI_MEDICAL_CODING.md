# Phase 2 Cycle 19 — UI 逆向 toolchain + 编码主界面 字符计数/分段高亮

## 1. Context

Phase 1.x closed with API parity toolchain (commit `54b0e30`):
- `scripts/corti_deep_scan.py` extracts Corti API contracts from captured .md specs
- `scripts/icoder_compare.py` diffs iCoDer responses vs Corti golden, writes `VERIFIED_OK`

User has directed Phase 2 to start with **UI parity**. This is the first UI cycle.

Two Corti parity gaps on the 编码主界面 (MedicalCodingPage) that this cycle ships:

| Feature | Corti behaviour | iCoDer before cycle 19 |
|---|---|---|
| **字符计数** (real-time char/cost counter) | Live counter in input area header, updates on every keystroke | `liveCost` from `useCostStore` updates ONLY after `handlePredict()`, rendered in Event Inspector footer, not top-right of input. NOT derived from `input.length` per-keystroke. |
| **分段高亮** (click code → highlight evidence in input) | Click a code on the right panel → evidence sentence in input gets highlighted in green (other evidence stays yellow) | `EvidenceHighlighter` imported at line 11 but never rendered. Code rows at lines 445-454 are plain `<tr>` with no onClick. `dataEvidences()` returns only `e.text \|\| e.quote` strings — drops `char_start`/`char_end`. |

The cycle ALSO ships the foundation for all future UI cycles: `scripts/icoder_ui_diff.py` (UI contract diff gate) + `corti_ui_contracts/medical-coding.json` (first UI feature spec).

## 2. Audit (iCoDer state at cycle start)

- `frontend/src/pages/MedicalCodingPage.tsx` (728 lines, 3-pane layout)
  - `EvidenceHighlighter` imported (line 11) but **never used as JSX** — dead code
  - Textarea at line 373: plain `<textarea value={input} onChange={...} />`
  - `dataEvidences()` at lines 724-728 returns `string[]` — drops char_start/char_end
  - Code rows at lines 445-454: plain `<tr>` with no onClick
  - `liveCost` (line 698): only updates after predict, footer not header
- `frontend/src/components/medical-coding/EvidenceHighlighter.tsx` (100 lines)
  - Has `useMemo` segment-builder over char ranges — pure & testable
  - No `focusedSpanIndex` prop; all spans get same yellow class
- `frontend/src/i18n/locales.ts`
  - No `charCount` or `costEstimate` key in either locale
- No UI toolchain existed; existing `corti_*_reverse_engineer*.py` scripts produce `interactions/*_step.png + _final.html` captures but no diff gate

## 3. Spec — what cycle 19 ships

### 3.1 UI toolchain: `scripts/icoder_ui_diff.py` (~250 LOC)

Mirrors `icoder_compare.py:1-368` style:
- argparse: `--feature`, `--cycle-dir`, `--contracts-dir`, `--list`
- Reads `corti_ui_contracts/{feature}.json`
- For each check runs **static TSX analysis** with 4 set-based patterns:
  - `must_contain` — pattern must appear in file
  - `must_not_contain` — pattern must NOT appear (proves old code is gone)
  - `imported` — pattern must appear on an `import ... from ...` line
  - `jsx_used` — pattern must appear as `<Foo` (NOT in import statement); spec may use `<Foo` or `Foo` — leading `<` stripped before symbol match
- Color-coded report, exits 0 on full pass, 1 on any fail
- Writes `corti_ui_contracts/{feature}.VERIFIED_OK` on full pass
- Writes `UI_DIFF.md` to `--cycle-dir` on any fail

Spec format: `schema_version: 1`, `checks[].static.{...}`, `checks[].runtime: {}` reserved for future Playwright assertions.

**Why static-only for first cycle**: no jsdom env wired in vitest config yet, Playwright would need dev stack running. Static checks defeat the "imported but never rendered" trap via `must_contain` + `must_not_contain` + `jsx_used` together. Future cycles will add `runtime: {}` Playwright assertions.

### 3.2 First UI feature spec: `corti_ui_contracts/medical-coding.json`

5 checks across 4 files:

| Check | File | What it proves |
|---|---|---|
| `real_time_char_counter` | `MedicalCodingPage.tsx` | Live char + cost estimate is derived from `input.length` per-keystroke |
| `no_plain_textarea_in_page` | `MedicalCodingPage.tsx` | Plain `<textarea>` replaced by `<HighlightedTextarea>` (positive: import + jsx + name in file; negative: `<textarea` not in file) |
| `highlighted_textarea_overlay_pattern` | `HighlightedTextarea.tsx` (new) | Component renders BOTH a textarea (input) AND a `<pre>` overlay with shared `INPUT_TEXT_CLASS` for font-metric sync, uses `EvidenceHighlighter` as JSX, has `aria-hidden`, `onScroll`, `pointer-events` |
| `evidence_highlighter_focused_state` | `EvidenceHighlighter.tsx` | Component accepts `focusedSpanIndex` prop and renders `bg-green` for focused span vs `bg-yellow` for others |
| `i18n_keys_added` | `locales.ts` | `charCount: '...'` + `costEstimate: '...'` exist in file (locales.test.ts enforces zh-CN/en-US parity) |

### 3.3 Implementation in iCoDer

**`frontend/src/components/medical-coding/HighlightedTextarea.tsx` (NEW, ~95 LOC)**

- **Pattern**: textarea + absolutely-positioned `<pre>` overlay (NOT `contenteditable` — Chinese IME composition would eat characters on the actual clinical text input)
- **Font-metric sync**: `INPUT_TEXT_METRICS` (text-sm, font-sans, leading-relaxed, whitespace-pre-wrap, break-words, p-3) + `INPUT_CHROME` (rounded-lg, border, bg-background) shared constants; textarea gets `text-transparent caret-foreground` so only the overlay colors show
- **Scroll sync**: `onScroll` on textarea → `preRef.scrollTop/Left`; overlay has `pointer-events: none` so the textarea owns all input
- **IME**: `onCompositionEnd` (not `onChange`) drives refresh — avoids "flash of un-highlighted text" mid-composition
- **a11y**: `<pre aria-hidden="true">`; the textarea is the only accessible input

**`frontend/src/components/medical-coding/EvidenceHighlighter.tsx` (MODIFIED)**

- New optional prop: `focusedSpanIndex?: number | null`
- New optional prop: `focusedClassName` (default `'bg-green-200 ...'`)
- `buildSegments()` now marks each segment with `focused: focusedSpanIndex === s.index`
- JSX renders `focusedClassName` when `seg.focused` else `highlightClassName`

**`frontend/src/i18n/locales.ts` (MODIFIED)**

- Type interface: added `charCount: string; costEstimate: string;`
- zh-CN: `charCount: '{{n}} 字'`, `costEstimate: '约 ${{n}}'`
- en-US: `charCount: '{{n}} chars'`, `costEstimate: '~${{n}}'`
- `locales.test.ts` already enforces parity (9/9 green)

**`frontend/src/pages/MedicalCodingPage.tsx` (MODIFIED, ~50 LOC delta)**

- Removed unused `EvidenceHighlighter` import
- Added `HighlightedTextarea` + `EvidenceSpanLike` imports
- New state: `focusedSpanIndex: number | null`
- New derivations: `charCount = input.length`, `costEstimate = (charCount * 0.00001).toFixed(6)` with explicit `// TODO: real pricing` comment
- New char counter element in input header (right side, before the `Eraser`/`Copy` buttons): `<span data-testid="char-counter" ...>{charCount} · ${costEstimate}</span>`
- Replaced plain `<textarea>` with `<HighlightedTextarea spans={dataEvidences(result)} focusedSpanIndex={focusedSpanIndex} ... />`
- `dataEvidences()` rewritten: returns `EvidenceSpanLike[]` with `{text, char_start, char_end, confidence}` (was returning `string[]`); backward-compat for missing offsets (defaults to 0, which the highlighter filters out)
- Evidence-quote block (lines 458-467) updated to read `.text` from span object (not bare string)
- Code table rows: added `onClick={() => setFocusedSpanIndex(focusedSpanIndex === i ? null : i)}` (toggle); `cursor-pointer` + hover bg + `bg-primary/5` for focused row

**Layout (3-pane) intentionally NOT collapsed to 2-pane this cycle** — that's a separate cycle. The two new features live within the current layout.

**Cost formula is a placeholder** — `0.00001` per char. Marked `// TODO: real pricing` in source. Real pricing from `/api/v2/tools/coding/pricing` endpoint is a separate cycle.

## 4. Files

### New
- `scripts/icoder_ui_diff.py` (~250 LOC) — UI contract diff gate
- `corti_ui_contracts/medical-coding.json` (54 lines) — first UI feature spec
- `frontend/src/components/medical-coding/HighlightedTextarea.tsx` (~95 LOC)
- `docs/phase_cycles/cycle_19_ui_medical_coding/REPORT.md` (auto-generated by toolchain)
- `corti_ui_contracts/medical-coding.VERIFIED_OK` (auto-generated)
- `docs/phase_cycles/cycle_19_ui_medical_coding/UI_DIFF.md` (auto-generated on first FAIL run, kept as baseline record)

### Modified
- `frontend/src/components/medical-coding/EvidenceHighlighter.tsx` (+focusedSpanIndex prop, focused class)
- `frontend/src/i18n/locales.ts` (+2 keys interface, +2 keys zh-CN, +2 keys en-US)
- `frontend/src/pages/MedicalCodingPage.tsx` (+char counter, +clickable code rows, +HighlightedTextarea, +dataEvidences return type change, +4 call-site fixes)

## 5. Verification

### 5.1 Primary gate — UI toolchain self-test
```bash
cd "E:/Corti4C" && PYTHONIOENCODING=utf-8 \
  python scripts/icoder_ui_diff.py --feature medical-coding \
    --cycle-dir docs/phase_cycles/cycle_19_ui_medical_coding
```
**Result**: 5/5 checks pass. `VERIFIED_OK` written.

### 5.2 i18n parity
```bash
cd frontend && npx vitest run src/i18n/locales.test.ts
```
**Result**: 9/9 pass. New `charCount` + `costEstimate` keys exist in both locales; placeholders balanced.

### 5.3 TypeScript
```bash
cd frontend && npx tsc --noEmit
```
**Result**: 0 errors. `dataEvidences()` return-type migration caught and fixed all 4 call sites in one commit.

### 5.4 Read-back sanity
| Check | Count | Expected |
|---|---|---|
| `<textarea` in `MedicalCodingPage.tsx` | 0 | 0 (was 1) |
| `<EvidenceHighlighter` in `HighlightedTextarea.tsx` | 1 | ≥1 (was 0) |
| `<HighlightedTextarea` in `MedicalCodingPage.tsx` | 1 | ≥1 (was 0) |
| `charCount` in `MedicalCodingPage.tsx` | 3 | ≥1 |
| `input.length` in `MedicalCodingPage.tsx` | 2 | ≥1 |
| `focusedSpanIndex` in `MedicalCodingPage.tsx` | 4 | ≥2 |

### 5.5 Backend regression (untouched but verified)
- No backend changes this cycle
- `pytest -x -q` in `backend/` was not re-run (no risk surface)

### 5.6 Manual browser test (deferred to dev mode)
- Open the page, type in the input area — char counter should update per keystroke
- Click a code row in the right panel — corresponding evidence span in the input should turn green
- Click the same code row again — highlight should toggle off

## 6. Migration / risk

### Migration of `dataEvidences()` return type
Was `string[]`, now `EvidenceSpanLike[]`. The evidence-quote block (lines 458-467) was the only consumer and was updated in the same commit. No external callers.

### Missing char_start/char_end offsets
If the backend returns evidence without `char_start`/`char_end`, the helper defaults to 0/0. The highlighter filters these out (line 70 in `EvidenceHighlighter.tsx`: `s.end > s.start` is required). So the evidence is preserved in the quote list but the input highlight is silently dropped. This is a graceful degradation — the iCoDer `/api/v2/tools/coding/` endpoint already returns `char_start`/`char_end` (Phase 1.3 cycle 18 contract), so this only matters for legacy backends.

### Cost formula is a placeholder
`input.length * 0.00001` is a placeholder. Real pricing from a `/api/v2/tools/coding/pricing` endpoint is a separate cycle. The `// TODO: real pricing` comment in `MedicalCodingPage.tsx:121` is the only breadcrumb.

### Layout still 3-pane
iCoDer's 3-pane layout (sidebar + middle + right) is NOT collapsed to Corti's 2-pane in this cycle. Doing both would double the diff and obscure the toolchain validation. Cycle 20+ candidate.

### Static-only checks
Cannot catch "component rendered but state never updates". `runtime: {}` Playwright assertions for that are deferred to cycle 20+ (spec already reserves the field). The current static checks use negative patterns (`must_not_contain: ["<textarea"]`) + positive patterns (`jsx_used: ["<HighlightedTextarea"]`) together to defeat the "imported-but-unused" false positive — but they can't prove the wiring actually works at runtime.

## 7. Next

**Cycle 20 candidates** (in rough priority order):

1. **`runtime: {}` Playwright assertions** — add 2 checks to `medical-coding.json`: (a) `await page.fill('textarea', '...')` then assert `[data-testid="char-counter"]` text contains the right char count; (b) `await page.click('tr:has-text("I50.9")')` then assert `<mark class*="bg-green">` exists in the overlay
2. **2nd UI spec** — `corti_ui_contracts/home.json` (4 tabs) or `corti_ui_contracts/agent-studio.json` (templates)
3. **Layout collapse to 2-pane** — biggest visible diff remaining
4. **Real pricing endpoint** — backend change + cycle
5. **AST-based static checks** — switch from grep to TypeScript compiler API when check count > 10

## 8. Toolchain notes

### `_run_static_check` gotcha (fixed in same commit)
Initial `jsx_used` check failed even when the JSX existed. Root cause: spec patterns included `<` for visual clarity (e.g. `"<HighlightedTextarea"`) but the regex extracts just the symbol name (e.g. `HighlightedTextarea`). Fix: `symbol = needle.lstrip("<")` before comparing. Now both `Foo` and `<Foo` work in the spec.

### Why mirrors `icoder_compare.py` style
- Same colorama output, same UTF-8 stdout fix, same `VERIFIED_OK` sentinel pattern
- Same `--cycle-dir` archive pattern (`docs/phase_cycles/cycle_NN_*/REPORT.md` or `UI_DIFF.md`)
- Same argparser structure (`--feature`, `--contracts-dir`, `--list`)
- Different output filename: `UI_DIFF.md` vs `contract_diff.md` (to keep the two streams separable in the cycle archive)
