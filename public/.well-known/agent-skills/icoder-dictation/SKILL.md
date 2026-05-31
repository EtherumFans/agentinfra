---
name: icoder-dictation
description: 使用 iCoDer SDK 构建医疗语音听写 Web 应用。提供基于 @icoder/stt-web 组件的 SOAP 分节编辑器构建指南——语音指令、浏览器作用域令牌、Apple 极简风格设计令牌。
license: ISC
metadata:
  author: icoder
  version: "1.0.0"
---
# 医疗语音听写 Web 应用
使用 iCoDer SDK 和 `@icoder/stt-web` Web Component 构建可运行的医疗语音听写应用。
目标用户：刚注册 iCoDer 控制台的开发者，需在 5 分钟内搭建本地 Demo。

## 第 1 步 — 确认构建方案
使用 `AskUserQuestion`（如果可用）；否则在编写任何代码前直接询问用户。
将以下全部问题合并为单次询问呈现。若用户选择"你决定" / 跳过 / 回车，使用 **默认值**。

1. **框架**（默认：Vite + React）
   - Vite + React
   - Next.js (App Router)
   - 纯 HTML + Express
   - 你决定

2. **使用场景**（默认：SOAP 分节文书）
   - SOAP 分节医疗文书（4 节 + 语音导航切换）
   - 自由编辑（单 textarea，自由听写）
   - 患者接诊表单（离散字段：主诉、生命体征、用药——语音指令跳转字段）
   - 你决定

3. **语言/区域**（默认：简体中文，中国）
   - 简体中文，中国
   - 英文，美国
   - 其他 — 输入 BCP-47 代码（如 `en-GB`、`ja`）
   - 你决定

## 应用功能要求
- SOAP 风格文书编辑器：四个标签分区（**主观资料 S**、**客观资料 O**、**评估 A**、**计划 P**），同时可见。
- `<icoder-stt>` 元素，内建麦克风按钮。最终转录文本追加到活跃分区；暂态文本以灰色显示在其下方。
- 语音指令：
  - `"切换到{分区名}"` / `"跳转到{分区名}"`（`主观` | `客观` | `评估` | `计划` | `下一个` | `上一个`）
  - `"删除最后一句"` / `"删除上一条"`
  - `"清空分区"`
- **每条短语必须包含明确动作动词。** 不要添加裸名词模式（如仅 `"{分区名}"`）——这会误吞正常听写内容。
- 麦克风旁提供语音指令提示面板（popover 或 `<details>`），列出全部指令及示例。
- `<icoder-stt>` 配置设置：
  - `automaticPunctuation: true`、`spokenPunctuation: false`
  - `numbers: "numerals_above_nine"`、`measurements: "abbreviated"`（医疗格式）

## 设计风格 — Apple 极简
- 扁平表面，灰阶 + 朱红强调色（`#D4442A`），仅通过排版和空间传达意义。
- 正文字体：**Noto Sans SC**（UI 文本、标签、标题）；代码字体：**JetBrains Mono**（数字、编码、等宽输入）。
- 品牌字体：**DM Serif Display**（Logo 和 h1 标题）。
- 禁止除朱红强调色外的任何硬编码 hex 值——全文使用 HSL CSS 变量。

### CSS 变量
```css
:root {
  --background: 40 14% 98%;
  --foreground: 40 6% 9%;
  --card: 0 0% 100%;
  --card-foreground: 40 6% 9%;
  --primary: 9 68% 48%;
  --primary-foreground: 0 0% 100%;
  --secondary: 155 33% 38%;
  --secondary-foreground: 0 0% 100%;
  --muted: 40 10% 95%;
  --muted-foreground: 40 4% 43%;
  --border: 40 10% 89%;
  --ring: 9 68% 48%;
  --radius: 0.5rem;
}
```

### Logo
- SVG: `/logo.svg`
- 放置在页面标题左侧，约 24-32px 高度

## 硬性规则
1. **凭据保存在 `.env`，绝不出现在代码中。** 生成 `.env.example`（可提交）和 `.env`（gitignored）：
```env
ICODER_CLIENT_ID=your_client_id_here
ICODER_CLIENT_SECRET=your_client_secret_here
```
2. **浏览器仅获取作用域令牌。** `POST /api/token` 调用 iCoDer OAuth 获取 scoped token，返回 `{ accessToken, expiresIn }`。
3. **`<icoder-stt>` 仅在客户端使用。** 标记宿主组件为 `"use client"`，顶层静态导入 `@icoder/stt-web`。
4. **以真实来源为准。** 每个 URL、类型名、函数签名必须来自可读取的源。
5. **显示 SDK 错误。** 传播错误消息到 UI，不吞入空白面板。
6. **显示消耗积分。** 流式 SDK 发送 `usage` 和 `delta-usage` 事件——监听两者，最新值胜出。会话活跃但尚无积分时显示 `pending…`，有值时使用 `toFixed(4)` 格式。

## 必读文档
- `{origin}/docs/speech-to-text`
- `{origin}/developer-quickstart`

## 交付
构建、lint、类型检查必须通过。
**首先询问凭据。** Demo 已完全搭建但 `.env` 仍为占位符。
**你有 iCoDer API 凭据吗？**
- **有 — 我粘贴进去**（默认）
- **没有 — 我需要注册**（约 2 分钟在 iCoDer 控制台完成）
- **跳过 — 稍后配置**

然后展示交付摘要并让用户选择后续操作。
