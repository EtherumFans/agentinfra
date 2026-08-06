# iCoDer — Clinical AI Platform

面向中国医院场景的医疗合规 AI 平台。Agent Runtime + 编码审核 + 语音转录 + 文书生成 + 事实提取 + 嵌入助手，即开即用。SDK/API/Web Components 供 HIS 厂商和第三方深度集成。

**每条决策链可审计、可溯源、可重放**。

## Overview

iCoDer is a production-grade medical compliance AI platform for Chinese hospital scenarios. Core capabilities:

- **Clinical Documentation Improvement (CDI)**: Core entry agent #1 — identifies clinical documentation gaps, generates non-leading Provider Queries, drives clinician response → documentation revision → re-coding loop. NOT the same as note-completeness or discharge structuring.
- **Medical Coding**: Core entry agent #2 — evidence-based ICD-10-CN / ICD-9-CM-3 coding with full audit trail (Phase 5 Track C: 7-stage mainline complete).
- **Agent Runtime**: Multi-tenant, contract-enforced tool system, Deny-First security, Marketplace
- **Speech-to-Text**: Real-time clinical dictation with speaker diarization
- **Text Generation**: Template-driven clinical document generation
- **Fact Extraction**: Structured clinical entity extraction from unstructured text
- **Embedded Assistant**: Web Component for EHR/EMR integration
- **SDK/API**: Python & JavaScript SDKs for HIS vendor integration
- **Auditable**: Every code traces to source evidence, every decision chain is SHA-256 verifiable

## Two Core Entry Agents (Phase 5 Track D)

```
Clinical Documentation Improvement (CDI)
  让临床事实被写清楚
       ↓
Medical Coding
  将已经写清楚的事实准确编码
```

CDI and Medical Coding are the two `CORE_ENTRY_AGENT`s. All other agents (note-completeness, discharge-summary-structuring, evidence-extractor, principal-diagnosis-review, code-validation, compliance-guardrail, drg-analyzer, procedure-extractor) are `SPECIALIZED_AGENT` or `ORCHESTRATED_CAPABILITY` supporting the two entries.

## Architecture

```
iCoDer/
├── backend/          # FastAPI Python backend
│   ├── app/
│   │   ├── agents/   # AI expert agents (Evidence, Diagnosis, Procedure, DRG, etc.)
│   │   ├── api/      # REST API routes
│   │   ├── models/   # SQLAlchemy database models
│   │   ├── services/ # Business logic (LLM, Code Dict, Rule Engine)
│   │   ├── tools/    # Agent tools (search_codes, explore_code, etc.)
│   │   └── schemas/  # Pydantic validation schemas
│   └── tests/        # Unit and integration tests
├── frontend/         # React TypeScript frontend
│   └── src/
│       ├── pages/    # Page components (Home, Workbench, Review, etc.)
│       ├── components/ # Reusable UI components
│       ├── services/ # API client
│       ├── store/    # Zustand state management
│       └── types/    # TypeScript type definitions
└── docker-compose.local-dev.yml   # 仅本地开发;生产走托管云
```

## Quick Start

> 5 分钟快速入门：[QUICKSTART.md](./docs/QUICKSTART.md)
> 云端部署：[docs/cloud/CLOUD_DEPLOYMENT.md](./docs/cloud/CLOUD_DEPLOYMENT.md)

### Prerequisites

- Python 3.11+
- Node.js 20+
- npm 9+

### Local Backend Setup

```bash
cd backend
pip install -r requirements.txt
cp ../.env.cloud.example ../.env.cloud  # ICODER_DEPLOYMENT_MODE=local 默认所有 vars optional
uvicorn app.main:app --reload
```

### Local Frontend Setup

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

### Local Docker Stack (本地开发全栈)

```bash
docker compose -f docker-compose.local-dev.yml up --build
# 仅本地开发;绝不允许用于生产或医院部署
```

### Cloud SaaS Deployment (生产)

iCoDer v1 以**托管云 SaaS** 形式交付 (Environment EU/US/CN → Tenant → API Client)。
医院 / ISV 通过 onboarding intake 获取 Tenant 后,从 `https://{tenant_slug}.{region}.icoder.cloud` 接入。
**不再**支持医院内网 Docker 部署。详见 [docs/cloud/CLOUD_DEPLOYMENT.md](./docs/cloud/CLOUD_DEPLOYMENT.md)。

Access the app at `http://localhost:80` (local dev) and the API docs at `http://localhost:8000/docs`.

## Default Credentials

| Username | Password | Role |
|---|---|---|
| admin | admin123 | System Admin |
| coder01 | coder123 | Coder |
| depthead01 | head123 | Department Head |
| insurance01 | ins123 | Insurance |
| qc01 | qc123 | Quality Control |
| doctor01 | doc123 | Clinician |

## Features (V1.0)

### Core Capabilities
- **Agent Runtime**: Multi-tenant, contract-enforced tool system (Hoare-style pre/post conditions), Deny-First security model, runtime persistence
- **Medical Coding**: Evidence-based ICD-10-CN / ICD-9-CM-3 coding, 9-step pipeline, evidence ranking, confidence calibration, disagreement analysis
- **Speech-to-Text**: Real-time clinical dictation, speaker diarization, Medvoice/Web engines
- **Text Generation**: Template-driven clinical document generation
- **Fact Extraction**: Structured clinical entity extraction from unstructured text
- **Embedded Assistant**: Web Component for EHR/EMR integration, Context tag system
- **Marketplace**: Agent registration, discovery, installation
- **SDK/API**: Python & JavaScript SDKs, REST API, OAuth 2.0, API client management

### Platform Pages (21 pages)
AI Studio (Overview, Agents, Speech-to-Text, Text Generation, Fact Extraction, Medical Coding, Embedded Assistant), API Clients, Team, Billing, Usage, Settings, Gold Cases, Evaluation, Expert Library, Developer Quickstart, Docs, Release Notes, Tickets, Support

### Security
- OAuth 2.0 (access/refresh tokens, org switching, token revocation)
- Password reset flow (forgot/reset/change) + login rate limiting
- Circuit Breaker for LLM provider failover
- JWT authentication with 6 roles (Admin, Coder, DeptHead, Insurance, QC, Clinician)
- Complete audit logging, input validation, bcrypt password hashing

### Testing
- Backend: 579 tests passed, 10 skipped
- Frontend: 21-page smoke test, auth gate tests, Playwright project mode

## API Endpoints

| Prefix | Description |
|---|---|
| `/api/auth` | Authentication (login, register, forgot/reset/change password, revoke tokens) |
| `/api/organizations` | Multi-tenant org management |
| `/api/encounters` | Case management |
| `/api/reviews` | Coding review lifecycle |
| `/api/agents` | Agent CRUD & Marketplace |
| `/api/experts` | Expert library |
| `/api/codes` | Code dictionary search (33K ICD-10-CN + 23K ICD-9-CM-3) |
| `/api/gold-cases` | Gold standard case management |
| `/api/evaluation` | Agent evaluation metrics |
| `/api/billing` | Usage billing |
| `/api/usage` | Usage analytics |
| `/api/team` | Team management |
| `/api/admin` | Admin API (tenant management) |
| `/api/keys` | API key management |
| `/api/runtime` | Runtime session monitoring |
| `/api/health` | Health check |

Full API documentation available at `/docs` (Swagger UI).

## Testing

```bash
# Backend tests
cd backend
pytest --cov=app --cov-report=html

# Frontend tests
cd frontend
npm test
```

## Security

- OAuth 2.0 with role-based access control (6 roles)
- Password reset/change flow + login rate limiting
- LLM Circuit Breaker for provider failover
- Token revocation (logout all devices)
- Contract-enforced Agent Runtime (Hoare-style pre/post conditions)
- Complete audit logging for all operations
- Patient ID anonymization
- Built-in data subject to PHI redaction-at-edge contract — original PHI stays in hospital HIS/EMR; only redacted samples enter cloud audit channel (see [docs/cloud/CLOUD_DEPLOYMENT.md §4](./docs/cloud/CLOUD_DEPLOYMENT.md))
- Input validation on all endpoints
- Password hashing with bcrypt

## Compliance

Platform supports:
- 住院病案首页数据填写质量规范
- 医疗保障基金结算清单填写规范
- ICD-10-CN / ICD-9-CM-3 coding standards
- DRG/DIP payment reform requirements
- 《数据安全法》— 可审计决策链满足合规举证

## License

Proprietary. All rights reserved.
