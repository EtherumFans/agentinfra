---
name: icoder-scribe
description: 使用 iCoDer SDK 构建环境临床抄录 Web 应用。提供实时转录+实时事实提取+结构化文书生成的完整构建指南。覆盖单麦克风和远程虚拟诊疗双音频流场景。
license: ISC
metadata:
  author: icoder
  version: "1.0.0"
---
# 环境临床抄录 Web 应用
使用 iCoDer SDK（`@icoder/sdk`）和 TypeScript 构建可运行的环境临床抄录应用。
目标用户：刚注册 iCoDer 控制台的开发者，需在 5 分钟内搭建本地 Demo。

## 第 1 步 — 确认构建方案
1. **模式**（默认：实时）
   - **实时现场诊疗** — 捕获麦克风，实时显示转录片段和临床事实，结束时生成结构化文书。
   - **异步文件上传** — 上传预录音频文件（MP3/WebM/WAV，≤60 分钟/150 MB），处理后获取转录+事实+文书。
   - 你决定。

2. **音频源**（仅实时模式，默认：单麦克风）
   - **单麦克风 + 自动说话人分离** — 单个采集设备，API 按语音分离说话人。
   - **虚拟诊疗** — 麦克风 + 远程音频合并为 2 通道流（通道 0=医生，通道 1=患者）。
   - 你决定。

3. **框架**（默认：Vite + React）
   - Vite + React
   - Next.js (App Router)
   - 纯 HTML + Express
   - 你决定。

## 应用功能要求
- 服务端持有 `clientId`/`clientSecret`，是唯一拥有完整 iCoDer API 访问权限的位置。
- 浏览器仅做两件事与 iCoDer 直接交互：打开流（实时模式）或显示结果（两种模式）。
  其余全部——创建交互、列出事实、生成文书、异步管线编排——通过服务端端点完成。
- 诊疗结束后（实时）或上传后（异步），使用标准模板分区键生成结构化临床文书：
  `soap-subjective`、`soap-objective`、`soap-assessment`、`soap-plan`。
- 实时模式：转录片段实时滚动显示，事实实时更新（列表或标签形式）。
  "实时活动面板"必须在诊疗过程中持续更新，而非仅结束时一次性显示。
- 异步模式：上传进度 → 处理状态 → 结果展示（转录+事实+文书）。

## 设计风格 — Apple 极简
- 扁平表面，灰阶 + 朱红强调色（`#D4442A`），仅通过排版和空间传达意义。
- 正文字体：**Noto Sans SC**；代码字体：**JetBrains Mono**（仅数字、编码、时间戳）。
- 禁止除朱红强调色外的任何硬编码 hex 值——全文使用 HSL CSS 变量。
- 页面左上角渲染 iCoDer 文字标识。

### 布局约束（硬性）
- 主控制区（开始/停止/生成文书 或 上传/处理）、实时活动面板（实时模式）或上传状态（异步），以及生成文书区域，
  必须在 1280×800 视口内无需滚动全部可见。
- **实时模式三栏水平分割：** 控制+事实左列（~20%），实时转录中列（~30%），生成文书右列（~50%）。
  文书列最小宽度 600px——医疗内容需要足够空间。
- **禁止标签页、折叠面板、模态框等隐藏任一区域的设计。** 整个流程就是 Demo。
- **停止和生成文书是独立按钮，始终同时可见。**

## 硬性规则
1. **凭据保存在 `.env`：**
```env
ICODER_CLIENT_ID=your_client_id_here
ICODER_CLIENT_SECRET=your_client_secret_here
```
2. **浏览器仅获取作用域令牌。** `POST /api/token` 调用 iCoDer OAuth，`scopes: ["transcribe", "facts", "documents"]`。
3. **所有 iCoDer 组件仅客户端使用。**
4. **以真实来源为准。** 禁止猜测对象形状、使用 `as any`、忽略类型错误。
5. **显示 SDK 错误。** 传播到 UI。
6. **显示消耗积分。** 监听 `usage` 和 `delta-usage` 事件。使用 `toFixed(4)` 格式。

## 必读文档
- `{origin}/docs/embedded-assistant`
- `{origin}/docs/fact-extraction`
- `{origin}/developer-quickstart`

## 交付
构建、lint、类型检查必须通过。
**首先询问凭据。** 然后展示交付摘要并让用户选择后续操作。
