# iCoDer M3 — 安全与审计规范 (Security & Audit Spec)

**日期**: 2026-06-10
**阶段**: M3-0 (链路验证) / M3-1 (产品化闭环)
**适用**: 病案首页编码审核 Agent (Homepage Coding Review Agent) + 后续 4 个官方样板 Agent
**目标**: 在 iCoDer Runtime 上明确 5 类角色的权限边界 + 审计链完整性 + 生产写回硬性封禁。

---

## 1. 5 类角色 (硬性)

| Role | 角色 | 主责 | 默认权限 | 默认禁止 |
|------|------|------|----------|----------|
| `admin` | 系统管理员 | 平台配置 / Agent 注册 / 规则更新 | 全部查询 / 全部操作 | 无 |
| `coder` | 编码员 | 录入主/其他诊断 + 手术, 提交供审核 | 编码查询 / 规则校验 / 提交复核 | 接受 / 驳回他人编码 (无主诊断 modify 权限) |
| `medical_insurance_reviewer` | 医保审核员 | 接受 / 驳回编码 (主诊断 modify) | 全部编码查询 / 全部复核操作 / 风险路由查询 | 平台配置 / 规则更新 |
| `it_operator` | IT 运维 | 日志 / 索引 / 健康检查 | 全部只读 (query) | 任何编码操作 / 任何复核 |
| `auditor` | 审计员 | 审计日志查询 + 报告导出 | 全部审计日志 / 报告 / Run Trace 只读 | 任何编码操作 / 任何复核 / 任何配置变更 |

> M3-0 阶段, 角色通过 `reviewer_role` 字段显式传入, **未在 API 层强制 RBAC** (依赖 iCoDer's runtime auth 在更高层)。M3+ 阶段在 `/human-review` 端点引入 FastAPI Depends + JWT 解码后强制 role 校验。

---

## 2. 权限矩阵 (硬性)

| 操作 | admin | coder | med_insurance_reviewer | it_operator | auditor |
|------|:-----:|:-----:|:---------------------:|:-----------:|:-------:|
| `POST /coding-review/run` | ✓ | ✓ | ✓ | ✗ (只读) | ✗ (只读) |
| `POST /coding-review/{run_id}/human-review` | ✓ | ✓ (主诊断 modify 除外) | ✓ | ✗ | ✗ |
| `GET /coding-review/{run_id}/report` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `GET /coding-review/{run_id}` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `GET /coding-review/` (列表) | ✓ | ✓ | ✓ | ✓ | ✓ |
| `GET /m2a/runs/{run_id}` (Run Trace) | ✓ | ✓ | ✓ | ✓ | ✓ |
| **production writeback** | ✗ (硬性封禁) | ✗ | ✗ | ✗ | ✗ |
| **规则更新** (`/rule-engine/...`) | ✓ | ✗ | ✗ | ✗ | ✗ |
| **Agent 注册 / 卸载** | ✓ | ✗ | ✗ | ✗ | ✗ |
| **审计日志查询** | ✓ | ✓ (自己) | ✓ (自己) | ✓ (全部) | ✓ (全部) |

---

## 3. 审计链 (硬性)

每次 `POST /human-review` 调用必须落地以下 11 个字段到 audit log:

| 字段 | 来源 | 用途 |
|------|------|------|
| `record_id` | 后端生成 UUID | 审计记录主键 |
| `run_id` | URL 参数 | 关联 Agent run |
| `trace_id` | 来自 run | 关联 M2a Run Trace |
| `agent_ref` | 来自 run | Agent 标识 |
| `action` | request | accept / reject / modify / insufficient_evidence / escalate |
| `target_code` | request | 被操作编码 |
| `new_code` | request | modify 时的目标编码 |
| `target_role` | request | primary_disease / other_disease / primary_surgery / other_surgery |
| `reason_code` | request | R001-R010 + 自定义 |
| `reviewer` | request | 审核人 ID |
| `reviewer_role` | request | 5 类角色之一 |
| `review_note` | request | 备注 (可选) |
| `production_writeback_blocked` | 后端硬编码 `true` | 防止生产写回 |
| `recorded_at` | 后端时间戳 | ISO8601 |

**M3-0 存储**: in-memory dict (`_RUNS_STORE[run_id].human_review_records`), M3+ 替换为 PostgreSQL `coding_review_audit` 表。

---

## 4. production_writeback_blocked 硬性封禁 (M3-0)

| 字段 | 值 | 原因 |
|------|----|------|
| `production_writeback_blocked` (response) | `true` (always) | M3-0 阶段不接 EMR 生产写回 |
| `production_writeback_blocked` (audit_log_entry) | `true` (always) | 审计可追溯 |

**封禁检查点** (M3+ 实现时强制):
1. `POST /human-review` 返回值
2. 审计日志条目
3. 报告 18 节 §17 摘要
4. 前端 UI 状态条 (Workbench 底部 + Embed 组件 disclaimer)
5. Run Trace 阶段 14 (`audit_logger` 必须打 `production_writeback_blocked=true`)

---

## 5. 数据策略 (Data Policy)

iCoDer 部署在医院内网, **数据不出院**:

| 数据 | 存储 | 出院 |
|------|------|------|
| 病历原文 (encounter_text) | Runtime in-memory | ✗ |
| Agent run 结果 | in-memory → PostgreSQL | ✗ |
| 审计日志 | PostgreSQL | ✗ |
| LLM 调用的 prompt | LLM Gateway 日志 (本地) | 仅当 `ICODER_ALLOW_EXTERNAL_LLM=true` 才发到外部 LLM |
| 嵌入向量 (BGE-M3) | 本地 (data/medcoder/) | ✗ |
| FAISS 索引 | 本地 (data/medcoder/) | ✗ |

**M3-0 默认**: `ICODER_ALLOW_EXTERNAL_LLM=true` (用于接入 DeepSeek V4); 切到 `false` 时自动回退到 `MockLLMProvider`, 标记 `degraded=true, degraded_reason=no_llm_gateway_or_disallowed`。

---

## 6. 失败模式 (Failure Modes)

| 失败 | 检测 | 行为 |
|------|------|------|
| LLM Gateway 不可达 | `httpx.HTTPError` | 回退 mock, `degraded=true` |
| Circuit breaker open | `llm_circuit_breaker.is_open` | 回退 mock, `degraded_reason=circuit_open` |
| 429 / 503 (3 次重试) | DeepSeek 限流 | 回退 mock, `degraded_reason=429_503_exhausted` |
| HybridCodingAdapter 抛异常 | try/except | 整体 `status=unavailable`, `business_result_generated=false` |
| Run Trace 写入失败 | try/except | 标 warning, 不阻塞 run |
| 审计日志写入失败 | try/except | 标 warning, 不阻塞 run |
| HTML 报告生成失败 | try/except | 标 warning, JSON 报告仍可用 |
| reason_code 缺失 | 端点校验 | `accepted=false`, `validation_errors=[...]` |
| reviewer 缺失 | 端点校验 | `accepted=false`, `validation_errors=[...]` |
| 主诊断 modify 缺 new_code | 端点校验 | `accepted=false`, `validation_errors=[...]` |
| 5 重点码 reject/insufficient 缺 reason | 端点校验 | `accepted=false`, `validation_errors=[...]` |

---

## 7. 客户端注入防护 (M3-0 简化, M3+ 加强)

| 攻击面 | M3-0 防护 | M3+ 防护 |
|--------|-----------|----------|
| XSS (HTML 报告) | Jinja2 autoescape 等价 (Python str.replace + html.escape) | CSP header + Trusted Types |
| SQL Injection | 暂无 (无 DB 写入) | SQLAlchemy parameterized query |
| CSRF | 暂无 (API 鉴权靠 JWT) | SameSite=Strict cookie + CSRF token |
| 越权 (reviewer_role 伪造) | 客户端字段, M3-0 不验证 | JWT signature 验证 + role 强制 |
| 病历原文注入到 LLM prompt | prompt template 严格, 不可执行 | prompt sandboxing + 输出 schema 校验 |
| 审计日志篡改 | 暂无 | append-only DB + HMAC 签名 |

---

## 8. 审计报告导出 (M3-0)

`GET /api/icoder/coding-review/{run_id}/report?format=html|json` 输出包含:

- 18 节结构化报告
- 完整 audit_log 列表
- 完整 evidence_chain
- 完整 human_review_records
- 免责声明 (Pipeline Validation 模式)

**审计员** (`auditor` role) 可批量下载, 用于医院内部合规审计。

---

## 9. 已知安全限制 (M3-0 边界)

> **M3-0 是 pipeline validation 阶段, 不应在医院生产环境直接使用**。以下安全特性 **M3+ 阶段必须实现**:

1. RBAC 强制 (FastAPI Depends + JWT 解码)
2. 审计日志持久化 (PostgreSQL)
3. 审计日志完整性校验 (HMAC / 区块链追加)
4. 数据脱敏导出 (报告 HTML 中去除患者 PII)
5. LLM 输出 schema 严格校验 (Pydantic v2)
6. Run Trace 阶段级 tool_run_id + 完整耗时 + 错误堆栈
7. WebSocket 实时进度 (替代当前 polling)
8. 操作幂等性 (同一 record_id 多次提交不重复)
9. 速率限制 (FastAPI Depends + Redis)
10. CSP / Trusted Types / SameSite cookie
11. 病历原文加密存储 (AES-256 at rest)
12. 失败注入测试 (chaos engineering)

---

## 10. 后续 Agent 的安全约束 (M3+)

新注册的 Agent (`.icoder-agent` 包) 必须满足:

1. 显式声明 `permissions.production_allowed: false` (M3 阶段)
2. 显式声明 `permissions.tools` (工具白名单)
3. `agent_pack.json` 的 `integrity.sha256` 必须与打包时一致
4. 必须通过 `official_agent_validator` 校验才能上 marketplace
5. 上 marketplace 后, 安装时必须走 `RuntimeAgentRegistry.install_agent` 而非文件系统直拷

---

## 11. 联系与升级路径

| 问题 | 升级路径 |
|------|----------|
| 安全漏洞 (CVE) | `it_operator` → `admin` → 7 日内 fix |
| 角色权限争议 | `admin` review → `auditor` audit → 季度评审 |
| 审计日志异常 | `auditor` 标记 → `admin` 调查 |
| production_writeback 误开 | 不可能 (M3-0 硬性 true, M3+ 需 admin + 双人审批才能临时开) |

---

**附录: 审计日志 JSON Schema (M3-0 in-memory)**

```json
{
  "record_id": "uuid",
  "run_id": "uuid",
  "trace_id": "uuid",
  "agent_ref": "icoder/homepage-coding-review-agent@1.0.0",
  "action": "accept | reject | modify | insufficient_evidence | escalate",
  "target_code": "I66.901",
  "new_code": "I63.900",
  "target_role": "primary_disease",
  "reason_code": "R007",
  "review_note": "放射科会诊意见: 实为脑出血",
  "reviewer": "dr.li",
  "reviewer_role": "medical_insurance_reviewer",
  "production_writeback_blocked": true,
  "recorded_at": "2026-06-10T12:34:56.789Z",
  "validation_errors": [],
  "warnings": []
}
```
