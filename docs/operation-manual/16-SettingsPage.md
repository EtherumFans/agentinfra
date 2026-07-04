# SettingsPage

**路由**: `/settings` | **定位**: 系统设置

## 元素
| 元素 | 操作 | 预期 |
|------|------|------|
| 账户信息 | 查看 | 用户名/全名/角色/部门 |
| 国家选择 | 下拉 | localStorage 持久化 |
| 系统信息 | 查看 | 版本/LLM/环境/运行状态 |
| 安全护栏 | 开关切换 | 6 条规则：处方拦截/PHI检测/等 |
| A2A 智能体列表 | 查看+刷新 | GET /api/icoder/agents (Phase 2.1-B 起 /api/experts/a2a/agents 删除) |
| 保存设置 | 点击 | localStorage 持久化 |
