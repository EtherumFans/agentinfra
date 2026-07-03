# Corti Embedded Assistant vs iCoDer 逆向分析与差距报告

> 生成日期：2026-05-11
> 基于：Corti Console 认证页面 HTML、screenshots、gap-analysis 文档、Corti.ai 核心竞争力调研报告

---

## 1. Corti Embedded Assistant 架构推断

### 1.1 定位

Corti 的 Embedded Assistant 不是 iCoDer 这样的"配置+预览"页面。它是一个**完整的可嵌入 Web Component 产品**，具备三个层次：

```
Layer 1: Console 配置页
  └─ 可视化配置器（模式/语言/功能/外观）
  └─ 桌面+移动端实时预览
  └─ 代码生成器（HTML/React/JS SDK）
  └─ 事件检查器（WebSocket/STT/API 调试）

Layer 2: Web Component（icoder-assistant / corti-assistant）
  └─ 零代码嵌入（一行 HTML）
  └─ 认证（access_token 模式）
  └─ 会话管理（configureSession）
  └─ 事件系统（embedded-event → 父页面通信）

Layer 3: Runtime（运行时能力）
  └─ 实时语音转写（流式）
  └─ 实时事实提取（LLM）
  └─ 实时编码建议
  └─ 说话人分离
  └─ 音频质量检测
```

### 1.2 Corti 的实现方式（基于 Console 代码 + 调研报告推断）

| 组件 | 技术选型 | 证据 |
|------|---------|------|
| 前端框架 | React + React Router v7 | HTML 源码 `reactRouterContext.streamController` |
| UI 框架 | shadcn/ui + Radix UI | `radix-:r0:` data attributes, `bg-primary` classes |
| Toast | Sonner | `data-sonner-toaster` CSS variables |
| 分析 | PostHog + GTM + Cookiebot + Intercom | 多个 tracking script |
| Web Component | Lit Element (Standard Custom Element) | iCoDer 实现为 `icoder-assistant` |
| 实时通信 | WebSocket (流式 STT) | 代码中的 `ws://` URL |
| STT 引擎 | Corti 自研 ASR + Whisper Large | 调研报告 |
| 事实提取 | Corti 专有 LLM 管线 | 调研报告 "LLM实时" |
| 说话人分离 | Corti 自研 diarization | 调研报告 |
| 认证 | OAuth 2.0 + access_token | HTML 中 `auth({access_token, refresh_token, token_type, mode})` |

### 1.3 Corti Console 核心 UI 布局

```
┌─────────────────────────────────────────────────────────────────┐
│ Header: [Corti Console]        [¥实时费用] [$余额] [文档] [LS]  │
├──────────┬──────────────────────────────────┬───────────────────┤
│          │  预览  [桌面|手机] [刷新]         │                   │
│ 引导     │  ┌───────────────────────────┐  │  ← 设置面板        │
│ 面板    │  │ [预览会话] [上下文]         │  │    界面语言         │
│ (拖拽)  │  │                            │  │    听写语言         │
│          │  │          🎤                │  │    识别引擎         │
│          │  │        写入内容             │  │    麦克风           │
│          │  │     开始录音以开始          │  │    主色             │
│          │  │                            │  │    ·········       │
│          │  │    [服务端 | 浏览器]       │  │                     │
│          │  └───────────────────────────┘  │  ← 代码面板         │
│          │                                   │    HTML/React/JSON │
│          │  事件检查器 (可展开)             │    [复制代码]       │
│          │  ┌───────────────────────────┐  │                     │
│          │  │ 事件时间线                  │  │                     │
│          │  └───────────────────────────┘  │                     │
├──────────┴──────────────────────────────────┴───────────────────┤
│ Footer: 系统状态 · 三级等保合规                                    │
└─────────────────────────────────────────────────────────────────┘
```

### 1.4 关键功能拆解

#### A. 双模式（诊室内 + 远程）

Corti 的远程模式不只是 `getDisplayMedia`——它有 ZOOM/Teams/腾讯会议的原生 SDK 集成。iCoDer 仅实现了通用的 `getDisplayMedia` 系统音频捕获。

#### B. 实时事实提取（LLM）

Corti 在转录进行中实时运行 LLM 提取临床事实。iCoDer 转录完成后才调用 `factsApi.extract()`，且客户端还有一个 regex fallback（非 LLM）。

#### C. 实时编码建议

Corti 边听边输出 ICD-10 编码候选（类似 CodingWorkbenchPage 的实时模式，但嵌入在 Assistant 中）。iCoDer 完全没有这个功能。

#### D. 说话人分离（Speaker Diarization）

后端 `stt_service.py` 已有 diarization 代码但未暴露到前端。Corti 在前端显示「医生：... / 患者：...」标注。

#### E. 音频质量检测

Corti 实时显示音量指示器、噪声水平、信号质量。iCoDer 没有。

#### F. 事件检查器

Corti 的事件检查器是开发者调试工具，实时显示 WebSocket 消息、STT 事件、API 调用时间线、Token 消耗。iCoDer 已实现基础版。

#### G. 引导式新手体验（Tour）

Corti 有可拖拽的引导面板，带分步教程。iCoDer 已实现 5 步引导。

---

## 2. iCoDer vs Corti 逐项对比

### 2.1 架构层

| 维度 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| Web Component | ✅ `<corti-assistant>` | ✅ `<icoder-assistant>` | 🟢 持平 |
| 嵌入方式 | 一行 HTML `<script>` | 一行 HTML `<script>` | 🟢 持平 |
| 认证 | OAuth access_token | OAuth access_token | 🟢 持平 |
| 事件通信 | `embedded-event` CustomEvent | `embedded-event` CustomEvent | 🟢 持平 |
| **平台 SDK 集成** | ZOOM/Teams/腾讯会议 | 仅通用 getDisplayMedia | 🔴 |
| **分析/监控** | PostHog + Intercom | 无 | 🔴 |
| **错误追踪** | Sentry/Datadog (推断) | 无 | 🔴 |

### 2.2 语音转写

| 维度 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| 浏览器 STT | ✅ Web Speech API | ✅ Web Speech API | 🟢 持平 |
| 服务端 ASR | 自研 ASR + Whisper Large | FunASR Paraformer | 🟡 |
| **流式返回** | 逐词流式 | 4秒轮询 interim | 🔴 |
| **说话人分离** | ✅ 医生/患者 | ❌ (后端有代码但未接线) | 🔴 |
| **实时音量** | ✅ | ❌ | 🔴 |
| **噪声检测** | ✅ | ❌ | 🔴 |
| **术语增强** | ✅ 医学术语词典 | ✅ 后端有 fuzzy matching | 🟢 |
| **标点恢复** | Corti 自研 punc 模型 | CT-Transformer + LLM (刚实现) | 🟡 |
| **标点恢复** | Corti 自研 punc 模型 | CT-Transformer + LLM (刚实现) | 🟡 |

### 2.3 临床智能

| 维度 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| **实时事实提取** | ✅ LLM 实时 | ⚠️ 转录完成后再调 LLM | 🔴 |
| **实时编码建议** | ✅ 边听边出编码 | ❌ 完全缺失 | 🔴 |
| 转录后事实提取 | ✅ | ✅ factsApi.extract() | 🟢 |
| **代码建议** | ✅ 自动搜索 ICD 编码 | ⚠️ 仅诊断事实有代码搜索 | 🟡 |
| **证据溯源** | ✅ 代码→原文关联 | ❌ | 🔴 |
| **AI 对话** | ✅ 对转录内容提问 | ✅ 基础实现 | 🟡 |

### 2.4 配置与定制

| 维度 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| 模式切换 (诊室/远程) | ✅ | ✅ | 🟢 |
| 语言选择 | ✅ 30+ | ✅ 中/英 (2) | 🟡 |
| 界面语言 | ✅ | ✅ | 🟢 |
| 主色定制 | ✅ | ✅ 8 色预设 | 🟢 |
| 功能开关 | ✅ | ✅ 6 个 toggle | 🟢 |
| **代码生成** | HTML/React/SDK | HTML/React/JSON | 🟢 持平 |
| **桌面/移动端预览** | ✅ | ✅ | 🟢 持平 |
| **模板编辑器** | ✅ 可编辑转录文本 | ✅ | 🟢 |

### 2.5 UI/UX

| 维度 | Corti | iCoDer | 差距 |
|------|-------|--------|------|
| 加载状态 | ✅ Skeleton/Spinner | ✅ Spinner | 🟢 |
| Toast 通知 | ✅ Sonner | ❌ (alert 代替) | 🟡 |
| 引导体验 | ✅ 分步 Tour | ✅ 5 步 Tour | 🟢 接近 |
| 错误处理 | ✅ Toast + Inspector | ⚠️ alert + console.error | 🟡 |
| 可访问性 | ✅ aria-labels | ⚠️ 部分 | 🟡 |
| 移动端响应 | ✅ 375px 手机模拟 | ✅ 375px 预览 | 🟢 |

---

## 3. 核心差距排序（按影响）

| # | 差距 | 严重度 | 工作量 | 价值 |
|---|------|--------|--------|------|
| 1 | **实时编码建议** — 边听边出编码 | 🔴 P0 | 大 (新管线) | 核心差异 |
| 2 | **流式 STT** — 逐词返回代替 4s 轮询 | 🔴 P0 | 中 (后端改动) | 体验质变 |
| 3 | **实时事实提取** — LLM 实时代替转录后 | 🔴 P0 | 中 (管线改动) | 核心差异 |
| 4 | **说话人分离** — 医生/患者标注 | 🔴 P0 | 小 (前端接线) | 中国场景关键 |
| 5 | **腾讯会议 SDK** — 中国市场 Windows 生态 | 🔴 P1 | 大 (SDK 集成) | 中国市场核心 |
| 6 | **音频质量检测** — 音量/噪声指示 | 🟡 P1 | 小 (前端) | 用户信任 |
| 7 | **证据溯源** — 代码→原文点击跳转 | 🟡 P1 | 中 (前端+后端) | 审核必需 |
| 8 | **Toast 通知** — 替代 alert() | 🟡 P2 | 小 (引入 Sonner) | 体验 |

---

## 4. 下一步计划

### Phase 1: 实时管线 (P0)
1. 说话人分离前端展示（后端已有 diarization，接线到前端即可）
2. 流式 STT 逐词返回（当前是 4s 轮询 interim，改为 WebSocket 实时推送每个识别结果）
3. 实时事实提取（转录进行中，每收到一句完整的话就异步调用 LLM 提取事实）

### Phase 2: 编码闭环 (P0)
4. 实时编码建议（事实提取后立即搜索 ICD 编码，边听边出编码候选）
5. 证据溯源（编码→原文荧光高亮）

### Phase 3: 体验增强 (P1-P2)
6. 音频质量指示器
7. Sonner toast 替代 alert
8. 腾讯会议 SDK 集成方案调研
