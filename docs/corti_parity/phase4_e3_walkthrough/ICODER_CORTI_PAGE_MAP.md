# iCoDer × Corti Page Map

**Date**: 2026-07-09
**Source**: Live browser walkthrough (Corti console.corti.app authorized; iCoDer localhost:3002)
**Corti project**: b8f8129a-c31d-407f-b723-6ecc592d31e4 (Songluhua)
**iCoDer tenant**: icoder-medical-coding

## Module Correspondence Table

| # | Domain | Corti Path | Corti Title | iCoDer Path | iCoDer Title | Parity |
|---|---------|-----------|-------------|-------------|--------------|--------|
| 1 | Home | `/project/{id}` | Console Home | `/` | 首页 | Partial |
| 2 | Dev quickstart | `/project/{id}/developer-quickstart` | Developer Quickstart | `/developer-quickstart` | 开发者快速入门 | Match |
| 3 | Corti Models | `/project/{id}/corti-models` | Corti Models | (none) | (none) | **Corti-only** |
| 4 | AI Studio Overview | `/project/{id}/ai-studio-overview` | AI Studio Overview | `/ai-studio` | 总览 | Match |
| 5 | Agents list | `/project/{id}/ai-studio/agents` | Agents | `/ai-studio/agents` | AI智能体 | Match |
| 6 | Agent detail | `/project/{id}/ai-studio/agents/{agent}` | Agent detail | `/ai-studio/agents/{id}` | Agent detail | Match |
| 7 | STT Dictation | `/project/{id}/ai-studio/speech-to-text/dictation` | Dictation | (none) | (none) | **Corti-only** |
| 8 | STT Ambient | `/project/{id}/ai-studio/speech-to-text/ambient` | Ambient | (none) | (none) | **Corti-only** |
| 9 | STT Pre-recorded | `/project/{id}/ai-studio/speech-to-text/pre-recorded` | Pre-recorded | (none) | (none) | **Corti-only** |
| 10 | STT (umbrella) | `/project/{id}/ai-studio/speech-to-text` | Speech to Text (umbrella) | `/ai-studio/speech-to-text` | 语音转录 | Partial |
| 11 | Text Generation | `/project/{id}/ai-studio/text-generation` | Text Generation | (none) | (none) | **Corti-only** |
| 12 | Embedded Assistant | `/project/{id}/ai-studio/embedded-assistant` | Embedded Assistant | (none) | (none) | **Corti-only** |
| 13 | Fact Extraction | `/project/{id}/ai-studio/fact-extraction` | Fact Extraction | `/ai-studio/fact-extraction` | 事实提取 | Match |
| 14 | Medical Coding | `/project/{id}/ai-studio/medical-coding` | Medical Coding | `/ai-studio/medical-coding` | 医学编码 | Match |
| 15 | API Clients | `/project/{id}/api-clients` | API Clients | `/api-clients` | API 客户端 | Match |
| 16 | Team | `/project/{id}/team` | Team | `/team` | 团队 | Match |
| 17 | Billing | `/project/{id}/billing` | Billing | `/billing` | 计费 | Match |
| 18 | Usage | `/project/{id}/usage` | Usage | `/usage` | 用量 | Match |
| 19 | Customers | `/project/{id}/customers` | Customers | `/customers` | 客户 | Match |
| 20 | Templates | `/project/{id}/templates` | Templates (Beta) | `/templates` | 模板 | Match (Corti has Beta badge) |
| 21 | Settings | `/project/{id}/settings` | Settings | `/settings` | 设置 | Match |
| 22 | Get Help | `/project/{id}` (same as Home) | Get Help | `/support` | 获取帮助 | Partial |
| 23 | Tickets Portal | `https://help.corti.app/tickets-portal` (external) | Tickets Portal | `/tickets` | 工单 | Partial (Corti=external, iCoDer=internal) |
| 24 | Docs | `https://docs.corti.ai/` (external) | Docs | `/docs` (internal route) | 文档 | Partial (Corti=external docs site, iCoDer=internal route) |

## Counts

- **Corti total nav items**: 22 (Home + 2 Dev + 7 AI Studio + 7 Manage + 2 Support + 3 STT sub-items)
- **iCoDer total nav items**: 16 (Home + 1 Dev + 5 AI Studio + 7 Manage + 2 Support)
- **Gap count**: 6 Corti-only items (Corti Models + 3 STT sub-modes + Text Generation + Embedded Assistant)

## Notes on Project Switcher

- Corti: project switcher in sidebar header (`Songluhua songluhua` dropdown with avatar) — user can switch between multiple projects per account
- iCoDer: top-right `??` button (likely a project/console switcher, naming unclear) — needs verification

## Notes on Top Bar

- Corti top breadcrumb bar: breadcrumb on left + credits link ($48.78) + theme toggle + Docs link on right
- iCoDer top header: logo + 文档 link + EN button + Test button + dark mode toggle + ?? + ?? — no live credits link in top bar (credits may be in Usage page instead)

