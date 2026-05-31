# Changelog

## [1.0.0] - 2026-05-31

### 首次生产发布

**核心平台：**
- Agent Runtime：合同强制、Deny-First 安全模型、Runtime 持久化
- 多租户组织架构 + 角色权限（Admin / Coder / DeptHead / Insurance / QC / Clinician）
- OAuth 2.0 认证：access/refresh token、组织切换
- Marketplace：Agent 注册、发现、安装
- Web Components：可嵌入的智能体组件
- Admin API：租户管理、用量追踪

**账号安全（本迭代）：**
- 密码重置流程（忘记/重置/修改）
- 登录限流（5次/5分钟/IP）
- Token 吊销（登出所有设备）
- LLM Circuit Breaker（快速失败保护）
- 生产环境默认配置 + 动态 SECRET_KEY

**Pipeline 可观测性：**
- 错误严重性分级（critical/warning）
- Pipeline 健康状态横幅（healthy/degraded/failed）
- Evidence Ranking 面板（强证据/弱证据/冲突）
- Confidence Calibration 路由分级（auto/review/escalate）
- 主要诊断推理展示

**前端体验：**
- 全局 Toast 通知系统
- 登录页三合一（登录/注册/忘记密码）
- Settings 密码修改
- 注册/忘记密码页面

**测试：**
- 后端：579 passed, 10 skipped
- E2E：21 页烟雾测试 + 认证门控
- Playwright project 模式（setup → e2e 依赖链）

**CI/CD：**
- E2E 自动触发（push/PR main/master）
- CI 忽略 integration 测试
