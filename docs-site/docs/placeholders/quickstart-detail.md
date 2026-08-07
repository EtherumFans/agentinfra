---
sidebar_position: 3
title: Quickstart 详细版 (占位)
description: 详细 Quickstart 将在 Sprint 2 拆分为 JS/Python/curl 三语言版本
---

# Quickstart 详细版 (占位)

Sprint 1 已交付 [5 分钟 Quickstart](../../quickstart.md) 单文件版本。

Sprint 2 将拆分:

- `quickstart/javascript.md` — `@icoder/sdk` + Node.js
- `quickstart/python.md` — `icoder-python` SDK (待发布)
- `quickstart/curl.md` — 纯 HTTP curl 示例

每个版本走完同一 5 步:

1. 在 iCoDer Console 注册租户 / 拿到 admin 账号
2. 创建 API Client (backend-service 推荐)
3. 安装 SDK (或直接 curl)
4. 用 `client_credentials` 换 access token
5. 调用 Medical Coding Agent run, 查看结果 + trace_url
