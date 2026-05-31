---
name: icoder-coding
description: 使用 iCoDer SDK 构建医学编码 Web 应用。提供临床文本→ICD-10-CN 诊断编码和 ICD-9-CM-3 手术编码的完整构建指南，含证据引用、候选编码、置信度评分。
license: ISC
metadata:
  author: icoder
  version: "1.0.0"
---
# 医学编码 Web 应用
使用 iCoDer SDK（`@icoder/sdk`）构建可运行的医学编码应用。
目标用户：刚注册 iCoDer 控制台的开发者，需在 5 分钟内搭建本地 Demo。

## 第 1 步 — 确认构建方案
1. **框架**（默认：Vite + React）
   - Vite + React
   - Next.js (App Router)
   - 纯 HTML + Express
   - 你决定。

2. **编码系统**（默认：ICD-10-CN + ICD-9-CM-3）
   - ICD-10-CN（诊断）+ ICD-9-CM-3（手术）——中国医院标准
   - ICD-10-CM + ICD-10-PCS ——美国医院标准
   - 全部可用编码系统
   - 你决定。

3. **语言**（默认：简体中文）
   - 简体中文
   - 英文
   - 你决定。

## 应用功能要求
- 输入区：支持粘贴/键入临床文本（如出院小结、病程记录、手术记录）。
- **提取事实**按钮：调用 `POST /api/facts/extract`，返回结构化临床事实（诊断事实、手术/操作事实、排除发现、主诉、时间信息）。
- 事实展示区：按类别分组（诊断、手术、排除发现、文档概览），每项显示：
  - 名称 + ICD 编码标签 + 状态徽章（已确认/待确认/已排除）
  - 证据引用文本
  - 可点击状态徽章循环切换状态
- 编码结果区：主诊断编码 + 主手术编码，含备选编码列表、证据摘要、置信度评分。
- 右侧设置面板：编码系统选择、置信度阈值、输出语言。

## 设计风格 — Apple 极简
- 扁平表面，灰阶 + 朱红强调色（`#D4442A`）+ 玉色辅助色（`#3D7A5C`，仅确认/成功状态）。
- 正文字体：**Noto Sans SC**；代码字体：**JetBrains Mono**（ICD 编码如 `I25.101`）。
- 禁止除朱红/玉色外的任何硬编码 hex 值——全文使用 HSL CSS 变量。
- 布局：左侧 75% 主内容（输入+事实+编码结果），右侧 25% 设置面板。

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
  --radius: 0.625rem;
}
```
暗色模式通过 `prefers-color-scheme` 跟随系统。

## 硬性规则
1. **凭据保存在 `.env`：**
```env
ICODER_CLIENT_ID=your_client_id_here
ICODER_CLIENT_SECRET=your_client_secret_here
```
2. 所有 iCoDer API 调用通过服务端端点代理。
3. 编码结果展示必须包含证据引用——不可凭空显示编码。
4. 以真实来源为准。禁止猜测 API 响应形状。
5. 显示 SDK 错误到 UI。
6. 显示消耗积分（`toFixed(4)` 格式）。

## 必读文档
- `{origin}/docs/fact-extraction`
- `{origin}/docs/medical-coding`
- `{origin}/developer-quickstart`

## 交付
构建、lint、类型检查必须通过。先询问凭据，然后展示摘要。
