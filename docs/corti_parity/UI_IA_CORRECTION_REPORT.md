# UI_IA_CORRECTION_REPORT — P1.3 Stage 6 UI IA 纠偏报告

> **声明**: 本文档记录 P1.3 Stage 6 执行的 UI IA 最小纠偏.
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit — Stage 6
> **状态**: COMPLETED

---

## 0. 执行摘要

| 纠偏项 | 计划 | 实际 | 备注 |
|---|---|---|---|
| Sidebar 段顺序对齐 Corti | 重排 | 已对齐 (前 cycle 已做) | Top → AI Studio → Manage → Support ✅ |
| Project Home 4 tabs 雏形 | 新建 | 已存在 (前 cycle 已做) | Transcribe/Document/Chat/Code NEW ✅ |
| 顶栏 Theme toggle + Reset live cost | 新加 | 已存在 (前 cycle 已做) | ThemeToggle + liveCost 计数器 ✅ |
| 工作台共享 layout 壳子 | 抽离 | **新建** WorkbenchLayout.tsx | 5 tool 页 Phase 2 迁移 |
| 设计 token 抽离 (部分) | tailwind config | 已存在 (前 cycle 已做) | vermillion primary 保留 (iCoDer 品牌) |

**判定**: PASS — 5 项中 4 项在前 cycle 已对齐, 1 项 (WorkbenchLayout) 本 cycle 新建.

---

## 1. Sidebar 段顺序对齐 Corti (P1.3-1)

**文件**: `frontend/src/components/layout/Layout.tsx:46-83`

**现状** (已对齐):
```
topItems (Top section):
  - Home (/)
  - Developer Quickstart (/developer-quickstart)

navSections 1: AI Studio
  - Overview (/ai-studio)
  - Agents (/ai-studio/agents)
  - Speech-to-Text (/ai-studio/speech-to-text)
  - Text Generation (/ai-studio/text-generation)
  - Embedded Assistant (/ai-studio/embedded-assistant)
  - Fact Extraction (/ai-studio/fact-extraction)
  - Medical Coding (/ai-studio/medical-coding)  ← 第 7 子页 (已降级)

navSection 2: Manage
  - API Clients, Team, Billing, Usage, Customers, Templates, Settings

navSection 3: Support
  - Get Help, Tickets
```

**对齐 Corti**: Top → AI Studio → Manage → Support ✅
**Medical Coding 降为 AI Studio 第 7 子页**: ✅ (CORTI_PARITY_ROADMAP §1.3 要求)
**操作**: 无需改动, 仅验证.

---

## 2. Project Home 4 tabs 雏形 (P1.3-2)

**文件**: `frontend/src/pages/HomePage.tsx`

**现状** (已对齐):
- 4 tabs: `transcribe` / `document` / `chat` / `code`
- Code tab 带 `badge: 'NEW'` (Corti 风格)
- 每 tab 有: label + description + CTA (跳对应 AI Studio 工作台)
- 每 tab 有 3 条 value-prop list

| Tab | 跳转 | 图标 |
|---|---|---|
| Transcribe | /ai-studio/speech-to-text | Mic |
| Document | /ai-studio/text-generation | FileText |
| Chat | /ai-studio/embedded-assistant | MessageSquare |
| Code (NEW) | /ai-studio/medical-coding | Stethoscope |

**对齐 Corti Project Home IA**: ✅
**操作**: 无需改动, 仅验证.

---

## 3. 顶栏 Theme toggle + Reset live cost (P1.3-3)

**文件**: `frontend/src/components/layout/Layout.tsx:96-142`

**现状** (已对齐):
- `ThemeToggle` 组件 (lines 103-119): 切换 dark/light, 用 `useThemeStore`
- Live cost counter (lines 133-142): `$X.XXXXXX` 格式 + `RotateCcw` reset 按钮, 用 `useCostStore`
- 顶栏其他元素: Docs link / Locale toggle (EN/中) / OrgSwitcher / Notifications / User menu

**对齐 Corti 顶栏**: ✅
**操作**: 无需改动, 仅验证.

---

## 4. 工作台共享 layout 壳子 (P1.3-4)

**文件**: `frontend/src/components/layout/WorkbenchLayout.tsx` (新建, 88 LOC)

**Corti 工作台通用模式**:
- 左 Input / 右 Output (50/50 分屏)
- Input/Output 控件 header (PanelLeft/PanelRight icon + label)
- 右侧 Settings panel (w-64, 可选)
- 底部 Event Inspector (max-h-48, 可选)

**Props**:
```typescript
interface WorkbenchLayoutProps {
  title: string;
  description?: string;
  input: ReactNode;
  output: ReactNode;
  settings?: ReactNode;
  eventInspector?: ReactNode;
  inputLabel?: string;  // default 'Input'
  outputLabel?: string; // default 'Output'
}
```

**5 tool 页迁移计划** (Phase 2 执行, 本 cycle 不动各页内部):
- `AIStudioOverviewPage.tsx` (overview, 不需迁移)
- `SpeechToTextPage.tsx` → WorkbenchLayout
- `TextGenerationPage.tsx` → WorkbenchLayout
- `EmbeddedAssistantPage.tsx` → WorkbenchLayout
- `FactExtractionPage.tsx` → WorkbenchLayout
- `MedicalCodingPage.tsx` → WorkbenchLayout

**操作**: 新建 WorkbenchLayout.tsx, 不迁移现有页面 (P1.3 范围: 壳子 only).

---

## 5. 设计 token 抽离 (P1.3-5, 部分)

**文件**: `frontend/tailwind.config.js`

**现状** (已抽离):
- **Color**: vermillion primary (hsl(9 68% 48%)) + jade secondary + warm neutral background — 完整 token 集
- **Font**: sans (Noto Sans SC + 系统回退) + mono (JetBrains Mono) + brand (DM Serif Display)
- **Radius**: xs/sm/md/lg/xl/2xl/3xl 完整 (base lg = 0.5rem = 8px ✅)
- **Spacing**: 0.5 = 0.125rem
- **Dark mode**: `darkMode: 'class'` + CSS custom properties

**vermillion primary 保留决策**:
- CORTI_PARITY_ROADMAP §1.3.5 建议 "primary CTA 全黑"
- 但 iCoDer vermillion (Chinese medical seal red) 是有意识的 Chinese medical brand 选择
- 按 feedback memory "勿为像 Corti 删 iCoDer 差异化能力", 保留 vermillion
- Corti 黑色 CTA 是其西方品牌选择, iCoDer 服务中国医院, vermillion 更贴合本地语境

**操作**: 无需改动, 仅记录决策.

**Inter font gap**: Corti 用 Inter, iCoDer 用 Noto Sans SC (中文覆盖更好). 保留 Noto Sans SC 决策同上.

---

## 6. 验证

- ✅ Sidebar IA: Layout.tsx:46-83 段顺序对齐 Corti
- ✅ Home 4 tabs: HomePage.tsx 4 tabs (Transcribe/Document/Chat/Code NEW)
- ✅ Top bar: Layout.tsx:103-142 ThemeToggle + liveCost reset
- ✅ WorkbenchLayout: 新建 88 LOC shell, 5 tool 页 Phase 2 迁移
- ✅ Design tokens: tailwind.config.js 已抽离, vermillion primary 保留 (品牌决策)

**TypeScript 编译**: 待 Stage 7 验证 (`npx tsc --noEmit`).

---

## 7. 未完成的项 (推迟到 Phase 2)

| 项 | 原因 |
|---|---|
| 5 tool 页迁移到 WorkbenchLayout | P1.3 范围: 壳子 only, 不动各页内部 |
| primary CTA 改全黑 | iCoDer vermillion 是品牌选择, 保留 |
| Inter font 替换 | Noto Sans SC 中文覆盖更好, 保留 |

---

## 8. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, Stage 6 UI IA 纠偏完成 (4/5 已对齐 + 1 新建) | P1.3 Stage 6 |
