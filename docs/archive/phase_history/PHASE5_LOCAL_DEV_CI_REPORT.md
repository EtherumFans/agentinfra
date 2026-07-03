# Phase 5 — Local Dev & CI 基础设施报告

**日期**: 2026-05-12

---

## 1. 本地启动流程

### Docker Compose

```bash
# Clone + start
git clone <repo>
cd iCoDer

# Optional: set LLM API key
export LLM_API_KEY=sk-your-key

# Build + start (local-dev only — production 走托管云 SaaS)
docker compose -f docker-compose.local-dev.yml up -d --build

# Verify
curl http://localhost:8000/api/health
curl http://localhost/

# Stop
docker compose down
```

### 手动开发

```bash
# Terminal 1: Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm install
npm run dev

# Access
open http://localhost:3000  # Frontend (Vite dev)
open http://localhost:8000/docs  # Backend Swagger
```

## 2. CI 检查项 (`.github/workflows/ci.yml`)

| 阶段 | 检查项 | 触发 |
|------|--------|------|
| Backend | `pip install -r requirements.txt` | push/PR |
| Backend | `alembic upgrade head` + `downgrade -1` + `upgrade head` | push/PR |
| Backend | `pytest tests/ -v` (149 passed) | push/PR |
| Frontend | `npm ci` | push/PR |
| Frontend | `npx tsc --noEmit` (0 errors) | push/PR |
| Frontend | `npm run build` | push/PR |

### E2E Workflow (`.github/workflows/e2e.yml`)

| 阶段 | 说明 |
|------|------|
| 触发 | `workflow_dispatch` (手动) |
| 环境 | `docker compose -f docker-compose.local-dev.yml up -d --build` |
| 测试 | `npx playwright test` |
| 产物 | `playwright-report/` artifact, 保留 7 天 |

## 3. Docker 修复项

| 修复 | 之前 | 之后 |
|------|------|------|
| nginx WebSocket 代理 | 无 `/ws/` location | 新增 `/ws/` → backend:8000 (Upgrade + Connection headers) |
| 前端 healthcheck | `wget -qO-` (alpine 无 wget) | `curl -f` (apk add curl) |
| 后端 healthcheck | 内联 Python urllib | `curl -f http://localhost:8000/api/health` |
| 后端镜像 | `build-essential` 残留 | 移除，仅保留 `curl` |
| 前端 npm | `npm ci --legacy-peer-deps` | `npm ci` (peer deps 已修复) |
| 数据持久化 | bind mount `./data` | named volume `icoder_data` |
| 环境变量注入 | `.env` 文件挂载 | `environment:` 块 + `${VAR:-default}` 语法 |

## 4. 环境变量清单

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SECRET_KEY` | `dev-secret-change-in-production` | JWT 签名密钥 |
| `LLM_PROVIDER` | `deepseek` | LLM 提供商 |
| `LLM_MODEL` | `deepseek-chat` | 模型名称 |
| `LLM_API_KEY` | (空) | API 密钥 |
| `LLM_BASE_URL` | `https://api.deepseek.com/v1` | API 端点 |
| `APP_ENV` | `production` | 运行环境 |
| `DEBUG` | `false` | 调试模式 |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/icoder.db` | 数据库连接 |

## 5. 测试命令

```bash
# Backend
cd backend
pip install -r requirements.txt
python -m pytest tests/ -v              # Full suite (149 tests)
python -m pytest tests/ --cov=app       # With coverage
python -m alembic upgrade head          # Run migrations
python -m alembic downgrade -1          # Rollback

# Frontend
cd frontend
npm ci                                  # Install
npx tsc --noEmit                        # Type check
npx playwright test                     # E2E tests (requires running app)
npx playwright test --ui                # Debug mode
npm run build                           # Production build
```

## 6. 验收结果

| 标准 | 结果 |
|------|------|
| docker compose -f docker-compose.local-dev.yml up 可启动前后端 | ✅ 修复 nginx WS proxy + healthcheck |
| /api/health 正常 | ✅ curl -f 验证 |
| alembic upgrade head CI 通过 | ✅ CI workflow 含 3 步验证 |
| backend pytest 149/149 | ✅ |
| frontend typecheck 0 error | ✅ |
| frontend build success | ✅ `npm run build` |
| CI workflow 可运行 | ✅ `.github/workflows/ci.yml` |
| E2E workflow 手动触发 | ✅ `.github/workflows/e2e.yml` |
| 不新增业务功能 | ✅ 仅基础设施 |

## 7. 剩余风险

| 风险 | 级别 | 缓解 |
|------|------|------|
| SQLite 不适合生产并发 | P1 | 迁移至 PostgreSQL + 连接池 |
| LLM_API_KEY 在 CI 为 placeholder | P2 | 配置 GitHub Secrets |
| E2E 测试需人工触发 | P2 | 可升级为定时触发 (schedule) |
| Docker image 无版本标签 | P3 | 添加 `image: icoder-backend:${VERSION}` |
| 无 staging 环境 | P2 | 后续搭建 |
