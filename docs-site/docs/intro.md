---
sidebar_position: 1
title: 欢迎来到 iCoDer 开发者文档
description: iCoDer 是面向中国医院场景的医疗 AI 智能体平台。本文档面向在 iCoDer 上开发、集成或部署 Agent 的开发者。
---

# 欢迎来到 iCoDer 开发者文档

iCoDer 是**面向中国医院场景的医疗收入合规 AI 平台**, 以托管云 SaaS 形式交付。
本文档面向**在 iCoDer 上开发、集成或部署 Agent 的开发者**。

## 当前阶段

本文档站为 **Sprint 1 脚手架** —— Docusaurus 站点结构与导航已就位, 详细内容迁移
将在 Sprint 2 完成 (详见 `docs/governance/RELEASE_ROADMAP.md`)。

- ✅ 站点 scaffold + 主题 + i18n 配置 (zh-CN)
- ⏳ SDK 完整文档 (迁移自 `docs/sdk/`)
- ⏳ Quickstart 详细版 (见 `docs-site/docs/quickstart.md`)
- ⏳ Console API Clients 操作指南
- ⏳ Agent Pack 格式规范
- ⏳ Compliance & 审计接口文档

## iCoDer 是什么?

iCoDer 提供:

1. **Agent Runtime** — A2A v0.3 + MCP 协议, Python FastAPI 后端
2. **多租户 SaaS** — 环境 (EU/US/CN) → Tenant (医院) → API Client (HIS/EMR)
3. **官方 Agent 库** — Medical Coding / CDI / DRG-DIP / Denial Appeals 等
4. **合规服务** — PHI 脱敏 + 编码规则集 + 审计日志

详见 [CLAUDE.md](https://github.com/icoder-cloud/icoder/blob/main/CLAUDE.md) 产品定位章节。

## 5 分钟 Hello World

参见 [Quickstart](../quickstart.md)。

## 部署形态

iCoDer 是**云托管 SaaS**, 部署决策记录在
[Deployment Path ADR](https://github.com/icoder-cloud/icoder/blob/main/docs/governance/DEPLOYMENT_PATH_ADR.md)。
**不再**支持医院内网 Docker 部署。
