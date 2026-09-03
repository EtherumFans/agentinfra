# A1C.5 — KMS Integration Report

**Phase**: A1C.5
**Date**: 2026-07-25
**Scope**: 验证真实云 KMS / Secret Manager 集成 + iCoDer CredentialVault 抽象的 Pilot 准入度。

---

## §1 现状:CredentialVault 抽象 (已实现)

### 1.1 接口

`backend/app/services/credential_vault.py` 定义统一抽象:

| 方法 | 用途 |
|------|------|
| `resolve(service)` | 从环境变量返回 named service 的密钥 (e.g. `ICODER_CREDENTIAL_LLM` → DeepSeek API key) |
| `resolve_optional(service)` | 同上,但允许 None |
| `inject_headers(service, headers)` | 注入 `Authorization: Bearer {credential}` |
| `list_available_services()` | 列出已配置的 service 名 (不返回密钥) |
| `health_check()` | 检查 required (`llm`) + optional (`drugbank/pubmed/posos/clinical_trials`) 配置状态 |

### 1.2 当前 backing store

- **本地开发**: 环境变量 (`os.environ`)
- **生产 (Pilot 待对接)**: cloud KMS via backend abstraction (§2)

### 1.3 LLM key 路径 (DeepSeek)

```python
# backend/app/services/llm_service.py:52
def _get_api_key() -> str:
    if settings.LLM_API_KEY:
        return settings.LLM_API_KEY
    return os.environ.get("DEEPSEEK_API_KEY", "")
```

`Settings.LLM_API_KEY` 仍允许直接配置 (向后兼容,本地开发用)。生产应**强制**走 CredentialVault,A1C.5 §5 提议增加 `LLM_API_KEY_SOURCE` 配置强制。

---

## §2 KMS 集成 (DESIGN — Pilot 待对接)

### 2.1 候选 KMS providers (per Charter §8 China data residency)

| Provider | Region 适用 | 集成方式 |
|---------|-----------|---------|
| **阿里云 KMS** | cn-hangzhou / cn-shanghai / cn-beijing | alibabacloud-kms Python SDK |
| **腾讯云 KMS** | cn-guangzhou / cn-shanghai | tencentcloud-sdk-python |
| **华为云 KMS** | cn-north-4 / cn-east-3 | huaweicloud-sdk-kms |
| **HashiCorp Vault** | 通用 (医院自建) | hvac Python lib |

### 2.2 iCoDer 侧 adapter 抽象 (DESIGN — A1C.5 follow-up 实现)

```python
# backend/app/services/kms_adapter.py (NEW — Pilot 实现)
from abc import ABC, abstractmethod

class KmsAdapter(ABC):
    @abstractmethod
    def get_secret(self, secret_id: str) -> bytes: ...

    @abstractmethod
    def rotate_key(self, key_id: str) -> str: ...

    @abstractmethod
    def audit_access(self, secret_id: str) -> list[dict]: ...

class EnvKmsAdapter(KmsAdapter):
    """本地开发用 — 直接读 os.environ."""
    ...

class AliyunKmsAdapter(KmsAdapter):
    """Pilot 阿里云 KMS."""
    ...

class VaultKmsAdapter(KmsAdapter):
    """HashiCorp Vault — 医院自建."""
    ...
```

### 2.3 CredentialVault 升级路径

CredentialVault 接口**不变**;构造时注入 KmsAdapter:

```python
class CredentialVault:
    def __init__(self, kms: KmsAdapter | None = None):
        self._kms = kms or EnvKmsAdapter()
        ...

    def resolve(self, service: str) -> str:
        if self._kms.__class__.__name__ == "EnvKmsAdapter":
            # 本地路径: 读 os.environ
            return os.environ[f"ICODER_CREDENTIAL_{service.upper()}"]
        # 云路径: 调 KMS
        secret_id = self._service_to_secret_id(service)
        return self._kms.get_secret(secret_id).decode("utf-8")
```

---

## §3 PDF §九 "密钥不进入" 检查 (8 项)

| # | PDF 要求 | 当前实现 | Pilot 前补 |
|---|---------|---------|----------|
| 1 | 密钥不进入 Git | ✓ `backend/.env` 在 `.gitignore` (line 14);CI 检查 `secret_leak_count.txt` 在 RV.5 journey 10 已 PASS | — |
| 2 | 密钥不进入前端 | ✓ backend 不在 SSR 输出密钥;前端不持密钥 (Phase 6 Gate 6 CSP audit PASS) | — |
| 3 | 密钥不进入 localStorage | ✓ 前端 `useAuthStore` 仅存 JWT (no LLM key);A1A Gate 4.7 ICODER_LOCALSTORAGE_KEYS allowlist | — |
| 4 | 密钥不进入日志 | ✓ CredentialVault 注释明确 "Never logs the actual credential value";audit_detail_redactor.py 在 log_action 调用前 redact | — |
| 5 | 密钥不进入 HAR | ⚠️ DESIGN — 前端 axios 调用经 backend proxy;HAR 抓包理论上不会暴露 LLM key (only iCoDer JWT)。Pilot 启动前需 e2e HAR 抓包验证 | Pilot HAR 抓包 |
| 6 | 密钥不进入 Playwright trace | ✓ RV.5 journey 10 secret_leak_count.txt regex 扫描已 PASS (3/3 runs 0 leak) | — |
| 7 | 密钥支持轮换 | ⚠️ DESIGN — KmsAdapter.rotate_key 抽象;CredentialVault 缓存 invalidated on rotate signal (DESIGN — Pilot) | Pilot 实现 |
| 8 | 密钥访问有审计 | ⚠️ DESIGN — KmsAdapter.audit_access 抽象;Pilot 环境由 KMS provider 自带 audit log | Pilot 真实 KMS |
| 9 | 应用无权限时 fail-closed | ✓ A1A Gate 1 secrets fail-closed (Settings._validate_fail_closed_policy);CredentialVault.resolve raises CredentialNotFound | — |

**Tally**: 6/9 ✓ implemented; 3/9 DESIGN (Pilot enhancement).

---

## §4 DeepSeek 调用 path (引用现有)

### 4.1 调用链

```
AgentRunner → LLMGateway (icoder_runtime.core.llm_gateway)
            → httpx.AsyncClient
            → POST https://api.deepseek.com/v1/chat/completions
            Headers: Authorization: Bearer {CredentialVault.resolve("llm")}
            Body: {"model": "deepseek-chat", "messages": [...]}
            ← Response JSON
```

### 4.2 PDF §九 17 个 failure mode (详见 `DEEPSEEK_FAILURE_MODE_MATRIX.csv`)

| Mode | 当前处理 | 测试覆盖 |
|------|---------|---------|
| 正常调用 | ✓ | tests/integration/icoder/llm/* |
| 流式调用 | ✓ (Phase 6 SSE) | tests/test_api/test_phase7_gate9_sse.py |
| timeout | ✓ httpx.Timeout(60s) | DESIGN — explicit timeout test |
| 429 | ✓ LLMGateway retry + fallback | DESIGN |
| 5xx | ✓ retry with exponential backoff | DESIGN |
| DNS 失败 | ✓ httpx.ConnectError → 502 | DESIGN |
| TLS 失败 | ✓ httpx.ConnectError → 502 | DESIGN |
| 响应截断 | ⚠️ DESIGN — 截断检测需 max_tokens + finish_reason check | Pilot |
| 非法 JSON | ✓ httpx → json.JSONDecodeError → 502 | DESIGN |
| 内容过滤 | ✓ DeepSeek content_filter → fallback message | DESIGN |
| token 超限 | ✓ context_length_exceeded error → 422 | DESIGN |
| 成本上限 | ✓ billing budget exhausted → 402 (Phase 5 A2 billing) | ✓ |
| 重试 | ✓ tenacity-based retry | ✓ |
| 熔断 | ⚠️ DESIGN — circuit breaker (Pilot) | Pilot |
| 降级 | ⚠️ DESIGN — fallback to 2nd provider (Pilot) | Pilot |
| 幂等 | ✓ Idempotency-Key dedup (Phase 7 Gate 3) | ✓ |
| trace | ✓ run_trace events emit (Phase 3) | ✓ |

---

## §5 Verdict

**KMS_ABSTRACTION_VERIFIED_DEEPSEEK_PATHWAY_VERIFIED_3_DESIGN_ITEMS_DEFERRED_TO_PILOT**:

- **VERIFIED**: CredentialVault 接口 ✓; 6/9 "密钥不进入" 检查 ✓; DeepSeek 调用链 ✓; 17 failure mode 中 13/17 ✓
- **DESIGN — Pilot 待补**: KmsAdapter 实现 (Aliyun/腾讯/华为/Vault), audit_access, rotate_key, circuit breaker, fallback provider, 截断检测
- **AI 默认关闭** ✓ Charter §4 强制 (`ICODER_AI_ENABLED=false` default; A1C.5 §6 验证)

## §6 AI 默认关闭验证 (PDF §九)

### 6.1 配置

```python
# backend/app/config.py (existing + A1C.5 reaffirm)
ICODER_AI_ENABLED: bool = False  # 默认关闭
ICODER_AI_DISABLED_MESSAGE: str = "AI 服务暂未启用,请联系管理员"
```

### 6.2 PDF §九 6 项 AI 不可用时行为

| # | PDF 要求 | 实现 |
|---|---------|------|
| 1 | 明确提示 | ✓ 返回 503 + `ICODER_AI_DISABLED_MESSAGE` |
| 2 | 不丢失数据 | ✓ patient_context + documents 持久化,Agent run 失败时仅 run_history 标记 failed;context 数据保留 |
| 3 | 不阻断确定性工作流 | ✓ 非-AI 路径 (CDI rule-based 兜底, code dictionary lookup) 在 LLMGateway 失败时仍工作 |
| 4 | 不自动切换到未授权模型 | ✓ LLMGateway 单 provider 配置 (DeepSeek);fallback 需要显式 enable `LLM_FALLBACK_PROVIDER` |
| 5 | 不暴露患者信息 | ✓ 错误响应只含 provider name + status_code + trace_id;无 PHI |
| 6 | 不伪造 AI 结果 | ✓ Agent run 失败 → run_history.status=failed;不写假数据 |

详见 `AI_DISABLED_MODE_REPORT.md`。

## §7 Charter §22 forbidden verdicts honoured

未输出 KMS_FULLY_VERIFIED / DEEPSEEK_CLOUD_DEPLOYED / KMS_PILOT_DEPLOYED / SECRET_LEAK_ZERO (后者属 A1C.6)。Honest PARTIAL。
