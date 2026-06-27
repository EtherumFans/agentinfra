# iCoDer Cloud Tenant Intake Template (2026-06-27)

> **Status**: Phase 1 design intent. Replace 原 `HOSPITAL_DATA_REQUEST_TEMPLATE.md`
> (private-deployment intake)。本模板用于 **Tenant onboarding** 至托管云 SaaS。

## 1. Use Case

医院 / ISV 申请 iCoDer 托管云 Tenant 时,运维团队用本模板收集信息,
完成 Tenant 初始化 (Environment 分配 / database schema / LLM credential vault /
API Client 签发)。

## 2. Intake Form

### 2.1 Tenant 基本信息

| 字段 | 必填 | 说明 |
|---|---|---|
| Tenant 名 | ✅ | 医院 / ISV 法人全称 |
| Tenant slug | ✅ | 小写字母数字 + `-`, 6-32 字符;用于 subdomain (`{slug}.{region}.icoder.cloud`) |
| 联系人姓名 / 邮箱 | ✅ | Tenant admin 主联系人 |
| 联系电话 | ✅ | 仅供紧急运维联系,不进 audit log |
| 行业 | ✅ | `hospital` / `isv` / `other` |
| 部署场景 | ✅ | `hospital-internal` (院内自用) / `hospital-multi` (多院区) / `isv-resale` (转售) / `isv-integration` (HIS 集成) |
| 期望上线日期 | ✅ | YYYY-MM-DD |

### 2.2 Environment & Region 选择

| 选项 | 适用 | 备注 |
|---|---|---|
| `eu` + `eu-frankfurt` | 欧洲医院 | GDPR + EHDS |
| `us` + `us-virginia` | 美国医院 | HIPAA + HITECH |
| `cn` + `cn-hangzhou` | 中国大陆医院 | 数据安全法 + 个人信息保护法 |
| `cn` + `cn-beijing` | 中国大陆医院 (备份 region) | 同上 |

**约束**: 选定后 90 天内不可变更 (数据迁移成本);变更需走 support ticket
并经合规审批。

### 2.3 合规 & 数据驻留声明

Tenant admin 必须确认:

- [ ] 了解 iCoDer 部署于托管云,数据存储在所选 region,**原始 PHI 永远不离开
      医院 HIS/EMR**,仅脱敏样本进入云审计通道
- [ ] 同意 iCoDer 在 region 内按 audit log 留存 365 天 (可由 `AUDIT_LOG_RETENTION_DAYS`
      配置,但不得低于当地法规最低要求)
- [ ] 同意 LLM 调用路由至同 region inference endpoint,token 与推理都不出 region
- [ ] 已签订 iCoDer DPA (Data Processing Agreement) + SLA

### 2.4 API Client 签发 (默认)

| 字段 | 默认 | 备注 |
|---|---|---|
| 签发 1 个 backend-service client | ✅ | Tenant admin 持有 client_secret |
| Scopes | `codes:read` `encounters:write` `encounters:read` `reviews:read` `reviews:write` `agents:read` `agents:invoke` | 最小权限默认集 |
| ROPC embedded client (Web Component) | 按需 | 用于医院 Web 端嵌入 |

### 2.5 LLM Provider 选择

| Provider | 适用 region | 默认 |
|---|---|---|
| DeepSeek V4 (`deepseek-v4-flash`) | 全部 | ✅ |
| Anthropic Claude Sonnet | `us` / `eu` | optional |
| 自托管 vLLM (in-region) | 全部 | optional (高 cost) |

API key 由 Tenant 提供 (走云 KMS 注入,不入文件);详见 [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md)。

### 2.6 集成方式

| 方式 | 适用 | 实施工作量 |
|---|---|---|
| Web Component (`<icoder-embedded>`) | 医院 Web 端嵌入 | 1-3 天 |
| backend-service (server-to-server) | HIS / EMR 集成 | 1-2 周 |
| 双模式 | 大型医院多场景 | 2-4 周 |

## 3. Onboarding Workflow

1. **Tenant admin 提交本模板** → iCoDer 运维
2. **合规审批** (DPA / SLA / 当地法规 check) → 1-3 工作日
3. **Tenant 创建** → 自动化 provisioning script
   - database schema 创建
   - LLM credential vault entry
   - audit log partition 准备
   - 默认 backend-service client 签发
4. **Tenant admin 接收 onboarding packet**
   - 登录 Console URL: `https://{slug}.{region}.icoder.cloud`
   - 临时 admin 密码 (首次登录强制改)
   - backend-service client_secret (一次性显示)
   - API token 测试用例
5. **Smoke test** → 跑 5-case MedCodER 验证,确保 pipeline 通
6. **Go-live** → 切换至 production use

## 4. Out-of-Scope (Phase 2+)

- 跨 Environment 迁移 (Phase 2 实装)
- Active-active region (Phase 3)
- Edge node PHI redaction (separate RFC)

## 5. References

- [CLOUD_DEPLOYMENT.md](CLOUD_DEPLOYMENT.md) — 架构总览
- [API_CLIENT_MODEL.md](API_CLIENT_MODEL.md) — client 凭证与 scope
- [MULTI_REGION.md](MULTI_REGION.md) — region 与数据驻留
- 原 template: [HOSPITAL_DATA_REQUEST_TEMPLATE.md](../HOSPITAL_DATA_REQUEST_TEMPLATE.md)
  (Phase 1 删除;历史参考)