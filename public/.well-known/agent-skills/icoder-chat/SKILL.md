---
name: icoder-chat
description: 使用 iCoDer SDK 构建临床对话助手 Web 应用。提供基于 iCoDer Agentic Framework 的智能体创建、专家绑定、流式对话的完整构建指南。
license: ISC
metadata:
  author: icoder
  version: "1.0.0"
---
# 临床对话助手 Web 应用
使用 iCoDer SDK（`@icoder/sdk`）构建可运行的临床 AI 对话助手应用。
目标用户：刚注册 iCoDer 控制台的开发者，需在 5 分钟内搭建本地 Demo。

## 第 1 步 — 确认构建方案
1. **框架**（默认：Vite + React）
   - Vite + React
   - Next.js (App Router)
   - 纯 HTML + Express
   - 你决定。

2. **智能体类型**（默认：医学编码助手）
   - 医学编码助手（诊断+手术编码，证据引用）
   - 临床文书助手（SOAP/病程/出院小结生成）
   - 用药咨询助手（药物信息、相互作用、剂量）
   - 自定义——输入 System Prompt
   - 你决定。

3. **语言**（默认：简体中文）
   - 简体中文
   - 英文
   - 你决定。

## 应用功能要求
- 左侧对话面板：
  - 流式 SSE 对话（`POST /api/agents/{id}/stream`），实时显示 AI 回复。
  - 消息支持文本、JSON、文件附件（.txt/.csv/.json/.md/.xml）。
  - 快速操作按钮："你能做什么？"、"建议提示"、以及智能体特定建议。
  - 会话上下文记忆（跨对话保留关键事实）。
- 右侧设置面板（Settings/Code 双标签）：
  - Settings：智能体名称、System Prompt 编辑器（支持 XML 标签模板）、
    专家绑定（浏览/添加/删除）、模型参数配置。
  - Code：自动填充的 JavaScript/Python/C#/JSON SDK 代码片段。
- 智能体管理：
  - 我的智能体列表 + 预置智能体库（可浏览、搜索、按分类筛选）。
  - 创建智能体：克隆/模板/从零开始，含 AI 辅助 System Prompt 生成。
  - 删除确认（模态框，非 `confirm()`）。

## 设计风格 — Apple 极简
- 扁平表面，灰阶 + 朱红强调色（`#D4442A`）+ 玉色辅助色（`#3D7A5C`）。
- 正文字体：**Noto Sans SC**；代码字体：**JetBrains Mono**。
- 禁止除朱红/玉色外的任何硬编码 hex 值——全文使用 HSL CSS 变量。
- 布局：左侧 75% 对话面板，右侧 25% 设置/代码面板。

## 硬性规则
1. **凭据保存在 `.env`：**
```env
ICODER_CLIENT_ID=your_client_id_here
ICODER_CLIENT_SECRET=your_client_secret_here
```
2. SSE 流式连接正确处理 `text`、`json`、`error`、`done` 四种事件类型。
3. 所有 iCoDer API 调用通过服务端端点代理。
4. 以真实来源为准。禁止猜测 API 响应形状。
5. 显示 SDK 错误到 UI。
6. 显示消耗积分（`toFixed(4)` 格式）。

## 必读文档
- `{origin}/docs/agents`
- `{origin}/developer-quickstart`

## 交付
构建、lint、类型检查必须通过。先询问凭据，然后展示摘要。
