# iCoDer Medical Coding Agent V1.0

面向中国医院病案首页与医保结算清单场景的编码审核智能体。

## Overview

iCoDer is a production-grade AI-powered medical coding audit platform designed for Chinese hospital scenarios. It supports:

- **Evidence-based coding**: Every recommended code traces back to medical record evidence
- **Rule-validated**: All code judgments pass through ICD-10/ICD-9-CM-3 code tables and coding rules
- **Auditable**: Complete audit trail from input → evidence → candidates → rules → report → human review
- **Reviewable**: Coders can confirm, reject, or modify AI-suggested codes with documented reasons
- **Iterable**: Human review results feed back into gold cases and evaluation

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
└── docker-compose.yml
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 20+
- npm 9+

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Edit with your LLM API key
python -m app.seed     # Seed demo data
uvicorn app.main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install --legacy-peer-deps
npm run dev
```

### Docker Deployment

```bash
docker-compose up --build
```

Access the app at `http://localhost:80` and the API docs at `http://localhost:8000/docs`.

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

### Core Workflow
1. Medical record text input (paste or sample case)
2. Clinical evidence extraction (diagnosis, procedures, anatomy, etiology, negation)
3. ICD-10/ICD-9-CM-3 code candidate generation
4. Code dictionary validation and rule checking
5. DRG/DIP risk analysis
6. Documentation gap identification
7. Structured Coding Review Report generation (Markdown/HTML)
8. Human review workflow (confirm/reject/modify)
9. Evidence Pack export

### Pages
- **Home / Agent Studio**: Input area with settings panel and expert configuration
- **Coding Workbench**: 4-panel layout (record, evidence, candidates, report)
- **Case Review**: Human review interface for confirming/rejecting codes
- **Gold Cases**: Benchmark case management for evaluation
- **Evaluation**: Agent performance metrics dashboard
- **Code Dictionaries**: ICD-10, ICD-9-CM-3, insurance code search
- **Rule Libraries**: Coding rule retrieval and application

### Agent Pipeline (9-step fixed orchestration)
1. Evidence Extraction Expert
2. ICD Diagnosis Expert + Procedure Coding Expert
3. Medical Record Homepage Expert
4. Code Dictionary Tool
5. Coding Rule Tool
6. Evidence Verification Expert
7. DRG/DIP Expert + Documentation Gap Expert
8. Report Expert
9. Human Review

## API Endpoints

| Prefix | Description |
|---|---|
| `/api/auth` | Authentication (register, login, refresh) |
| `/api/encounters` | Case management |
| `/api/reviews` | Coding review lifecycle |
| `/api/codes` | Code dictionary search & explore |
| `/api/rules` | Rule library retrieval |
| `/api/gold-cases` | Gold standard case management |
| `/api/evaluation` | Agent evaluation |
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

- JWT authentication with role-based access control (6 roles)
- Complete audit logging for all operations
- Patient ID anonymization
- Built-in data never leaves the server
- Production deployments support private deployment behind hospital firewall
- Input validation on all endpoints
- Password hashing with bcrypt

## Compliance

Aligned with:
- 住院病案首页数据填写质量规范
- 医疗保障基金结算清单填写规范
- ICD-10 / ICD-9-CM-3 coding standards
- DRG/DIP payment reform requirements

## License

Proprietary. All rights reserved.
