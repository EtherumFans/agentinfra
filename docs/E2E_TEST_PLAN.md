# E2E Test Plan — iCoDer Medical Coding Agent

> 测试策略、环境搭建、数据准备、执行方案。
> 基于 E2E_TEST_DISCOVERY.md 的侦察结果制定。

---

## 1. 测试目标

验证 iCoDer 的 17 条核心业务流程在端到端层面正确运行：

1. 核心业务对象列表加载
2. 核心业务对象过滤/搜索
3. 核心业务对象分页
4. 新建核心业务对象
5. 新建表单校验
6. 核心业务对象删除
7. 核心业务对象详情查看
8. 核心业务对象编辑
9. 核心业务对象提交
10. 核心业务状态变更
11. 权限不足时按钮不可见
12. 直接访问无权限 URL 被拒绝
13. API 返回失败时页面提示
14. 表单校验
15. 导出或下载
16. 页面刷新后数据保持
17. 退出登录

**核心业务对象**: Encounter (就诊病历) → Review (编码审核) → GoldCase (金标准病例)

---

## 2. 测试策略

### 2.1 分层策略

```
  Layer 1: 真实后端 E2E (主要)
  │  后端: uvicorn on :8001, SQLite test DB
  │  前端: Vite dev server on :3000
  │  浏览器: Playwright Chromium headless
  │  └─> 覆盖: 测试 1-10, 14-17
  │
  Layer 2: 网络 Mock E2E (辅助)
  │  拦截特定 API 返回错误/边界值
  │  └─> 覆盖: 测试 13 (API 失败)
  │
  Layer 3: 无后端 E2E (权限)
  │  清空 localStorage，验证重定向
  │  └─> 覆盖: 测试 11-12 (权限门控)
```

### 2.2 测试框架

| 组件 | 选型 | 说明 |
|------|------|------|
| 测试运行器 | Playwright Test | 内置断言、fixtures、并行、trace |
| 浏览器 | Chromium | headless，CI 兼容 |
| 报告 | Playwright HTML Reporter | 含截图、trace、视频 |
| 环境管理 | playwright.config.ts webServer | 自动启动/复用 backend + frontend |
| 认证 | 手动登录 (每个 test 调用 login helper) | 避免 shared auth state 污染 |

### 2.3 不覆盖的范围

- **视觉回归测试** — 不在此阶段
- **性能测试** — LLM 调用时间不可预测
- **WebSocket 测试** — 需要独立方案
- **OAuth 客户端凭证流** — 独立安全测试
- **多角色权限矩阵** — 前端未实现角色级 UI 门控

---

## 3. 测试环境

### 3.1 启动命令

```bash
# Backend (test DB)
cd backend
SET DATABASE_URL=sqlite+aiosqlite:///./data/test.db
python -m uvicorn app.main:app --port 8001

# Frontend
cd frontend
npm run dev     # Vite on :3000, proxy /api → :8001

# Run tests
cd frontend
npx playwright test
```

### 3.2 环境变量

| 变量 | 值 | 说明 |
|------|-----|------|
| DATABASE_URL | sqlite+aiosqlite:///./data/test.db | 测试独立数据库 |
| DEBUG | false | 测试时不输出 verbose SQL |
| SECRET_KEY | (使用 .env 默认值) | JWT 签名密钥 |
| LLM_PROVIDER / LLM_MODEL | deepseek / deepseek-chat | 需要真实 API key |

### 3.3 测试数据

| 数据 | 来源 | 说明 |
|------|------|------|
| 测试用户 | seed.py → admin / admin123 | 预置管理员账号 |
| Encounter | 通过 API 创建 (POST /api/encounters/text) | 测试前创建 |
| GoldCase | 通过 API 创建 (POST /api/gold-cases) | 测试前创建 |
| ICD codes | iCoDerA knowledge base (33K+ entries) | 启动时自动加载 |
| LLM responses | DeepSeek API | 真实调用 (非 mock) |

### 3.4 Playwright 配置要点

```typescript
// playwright.config.ts
{
  testDir: './tests/e2e',
  fullyParallel: false,     // 1 worker — 避免 auth state 竞争
  timeout: 30000,           // 单个测试超时
  expect: { timeout: 10000 },
  webServer: [
    { command: 'python -m uvicorn app.main:app --port 8001', port: 8001, reuseExistingServer: true },
    { command: 'npm run dev', port: 3000, reuseExistingServer: true },
  ],
}
```

### 3.5 已知环境限制

| 限制 | 影响 | 缓解 |
|------|------|------|
| LLM 调用费用 | 测试 09 (提交审核) 消耗 token | 仅在必要时运行；可 skip |
| SQLite 并发 | 多 worker 写冲突 | 使用 1 worker |
| `/api-clients` proxy 冲突 | 测试 12 URL 导航失效 | 使用其他路由 (`/team`, `/billing`) |
| DeepSeek API 限速 | 管线超时 | 120s axios timeout |

---

## 4. 测试执行方案

### 4.1 执行顺序

测试按依赖关系排序：

```
Phase 1: Auth & Navigation (测试 11, 12, 14, 16, 17)
  └─> 不依赖后端数据

Phase 2: CRUD Operations (测试 1, 2, 3, 4, 5, 6, 7, 8)
  └─> 依赖后端 API + seed data

Phase 3: Business Flow (测试 9, 10)
  └─> 依赖 LLM (耗时/费用高)

Phase 4: Error Handling (测试 13, 15)
  └─> 依赖网络拦截
```

### 4.2 运行命令

```bash
# 全部测试
npx playwright test

# 按 tag 运行
npx playwright test --grep "Auth|Navigation"
npx playwright test --grep "CRUD"
npx playwright test --grep "Business Flow"

# 带 UI 模式 (调试)
npx playwright test --ui

# 生成报告
npx playwright show-report
```

### 4.3 CI 集成 (待实现)

```yaml
# .github/workflows/e2e.yml (推荐)
name: E2E Tests
on: [push, pull_request]
jobs:
  e2e:
    runs-on: ubuntu-latest
    services:
      backend:
        image: python:3.12
        env: { DATABASE_URL: "sqlite+aiosqlite:///./data/test.db" }
    steps:
      - uses: actions/checkout@v4
      - run: cd frontend && npx playwright test
      - uses: actions/upload-artifact@v4
        if: failure()
        with: { name: playwright-report, path: frontend/playwright-report }
```

---

## 5. 测试设计模式

### 5.1 Login Helper

```typescript
async function login(page: Page) {
  await page.goto('/login');
  await page.fill('input[placeholder="用户名"]', 'admin');
  await page.fill('input[placeholder="密码"]', 'admin123');
  await Promise.all([
    page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 }),
    page.click('button:has-text("登录")'),
  ]);
  await expect(page.locator('h2, h1, .text-2xl').first()).toBeVisible({ timeout: 5000 });
}
```

### 5.2 i18n-Aware Selectors

所有页面文本通过 `useT()` i18n hook 获取。Playwright 定位器必须使用实际的**中文文本**：

| i18n Key | 中文文本 |
|----------|---------|
| t.department | 科室 |
| t.diagnosisGroup | 诊断分组 |
| t.code | 编码 |
| t.name | 名称 |
| t.save | 保存 |
| t.cancel | 取消 |
| t.addGoldCase | 添加金标准病例 |
| t.newGoldCase | 新建金标准病例 |
| t.goldCasesTitle | 金标准病例 |
| t.difficulty | 难度 |

### 5.3 稳定性策略

1. **避免 `page.waitForTimeout(n)`** — 使用 `waitForSelector` / `waitForResponse` / `waitForURL`
2. **使用 `data-testid`** (长期方案) — 当前代码库无 testid，推荐逐步添加
3. **表单填充前先 `clear()` + `fill()`** — 避免追加而非替换
4. **对话框处理** — `page.once('dialog', ...)` 在触发动作前注册
5. **重试** — `retries: 2` in CI

---

## 6. 风险与缓解

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| LLM API 不可用 | 中 | 测试 09 阻塞 | Skip 或 mock agent_runner |
| 测试 DB 数据污染 | 低 | 测试不稳定 | 每次测试前清理 (conftest.py 已处理) |
| i18n 文本变化 | 中 | 定位器失效 | 建立 i18n key → selector 映射表 |
| React 渲染竞态 | 中 | 元素未就绪 | 合理使用 waitFor + timeout |
| Vite HMR 干扰 | 低 | 页面重载 | CI 中使用 preview (非 dev) |

---

## 7. 测试数据准备脚本

```bash
# 创建测试 Encounter (通过 API)
curl -X POST http://localhost:8001/api/encounters/text \
  -H "Authorization: Bearer $(curl -s -X POST http://localhost:8001/api/auth/login \
    -H 'Content-Type: application/json' \
    -d '{"username":"admin","password":"admin123"}' | jq -r .access_token)" \
  -H 'Content-Type: application/json' \
  -d '{"text":"患者因胸闷3天入院。心电图示ST段改变。诊断为冠心病。","department":"心内科"}'

# 创建测试 GoldCase
curl -X POST http://localhost:8001/api/gold-cases \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "department":"心内科",
    "diagnosis_group":"冠心病",
    "original_primary_diagnosis":"I25.101",
    "original_primary_diag_name":"冠状动脉粥样硬化性心脏病",
    "gold_primary_diagnosis":"I25.101",
    "gold_primary_diag_name":"动脉硬化性心脏病",
    "difficulty":"medium"
  }'
```
