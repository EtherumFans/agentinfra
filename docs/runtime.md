> **DEPRECATED (Phase 2-F / 2026-07-02 — TD-103)**: 本文档为旧版 Runtime 部署指南, 已被新版替代.
> 当前主线参考: [docs/cloud/CLOUD_DEPLOYMENT.md](cloud/CLOUD_DEPLOYMENT.md) + [CLAUDE.md](../CLAUDE.md) §部署模型
> Runtime 不再是独立 pip 包; Runtime = iCoDer Server 内核. 部署模型 = 托管云 SaaS (Env EU/US/CN → Tenant → API Client).
> 保留仅作历史参考 — 勿据此文档做部署决策.

# Runtime 部署指南 (DEPRECATED)

## 本地开发部署

```bash
pip install icoder-runtime
export ICODER_EXECUTION_MODE=platform_runtime
icoder init
```

## 医院本地生产部署

### 环境要求
- Python 3.10+
- 8GB+ RAM
- SQLite (默认) 或 PostgreSQL
- (可选) GPU 用于本地推理加速

### 数据策略配置

```bash
# 医院内部模式 (最严格)
export ICODER_ALLOW_EXTERNAL_LLM=false       # 禁止外部 LLM API
export ICODER_PII_REDACTION_REQUIRED=true    # 强制 PII 脱敏
export ICODER_PERSIST_FULL_INPUT=false       # 不保存完整病历
export ICODER_AUDIT_LOG_LOCAL_ONLY=true      # 审计日志仅本地
export ICODER_MARKETPLACE_SYNC_MODE=offline  # 离线市场
```

### 安全策略

- PreExecutionGuard: 输入格式 + 权限策略 + 数据策略三重校验
- PostExecutionGuard: 输出安全扫描 + 规则引擎自动触发
- SafetySpiralDetector: 连续 3+ 次失败自动熔断
- CircuitBreaker: LLM 不可用时快速失败

### 启动

```bash
cd /opt/icoder
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```
