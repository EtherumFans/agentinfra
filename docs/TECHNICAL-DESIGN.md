# iCoDer Agent Runtime — 技术方案

## 一、Agent Runtime 引擎

### 1.1 合同强制工具系统

**数据结构**

```python
# backend/app/services/tool_registry.py
@dataclass
class ToolDefinition:
    id: str                          # "search_icd10_index"
    name: str                        # "ICD-10索引导航"
    description: str                 # 功能描述
    tier: ToolTier                   # DETERMINISTIC=1 | LLM_REASONING=2
    category: str                    # safety|extraction|coding|verification|analysis|report
    icon: str                        # Lucide图标名
    requires: list[str]              # 前置条件: ["state.has('diagnosis_candidates')"]
    guarantees: dict[str, str]       # 后置条件: {"output.code": "valid icd10_code"}
    executor: Callable | None        # 异步执行函数
    accuracy_tags: list[str]         # ["code_dict", "evidence_binding"]
    is_injectable: bool              # 是否可被Harness自动注入
    input_schema: dict | None        # JSON Schema参数定义
```

**合同执行流程**

```
AgentRunner._run_tool_native()
  │
  ├─ LLM决定调用 search_icd10_index({"term":"肺炎"})
  │
  ├─ Harness.pre_check()
  │   └─ contract_engine.evaluate_precondition("", state)
  │       ├─ 解析表达式: state.has('...') / and / or
  │       ├─ ✅ ALLOW → 继续
  │       └─ ❌ DENY → 反馈给LLM → LLM修正 → 重试
  │
  ├─ permissions.PermissionPolicy.check("search_icd10_index")
  │   ├─ allowed=False → DENY
  │   ├─ _invocation_count >= max_per_session → DENY
  │   └─ requires_human=True → NEEDS_HUMAN
  │
  ├─ ToolRegistry.execute("search_icd10_index", {"term":"肺炎"})
  │   └─ code_dict_service.search_icd10("肺炎")  # 确定性代码，零LLM
  │
  ├─ Harness.post_check()
  │   └─ contract_engine.validate_postcondition("output.candidates: non-empty", result)
  │       ├─ ✅ ALLOW → result写入SymbolicState
  │       └─ ❌ DENY → 拒绝写入 → 反馈LLM
  │
  └─ perm_policy.record("search_icd10_index")  # 记录调用次数
```

**符号状态引擎**

```python
# backend/app/services/contract_engine.py
class SymbolicState:
    _data: dict           # 内部状态字典
    _update_count: int    # 已验证写入计数
    _update_log: list     # Append-only写入日志

    def has(key: str) -> bool:   # 支持点号路径: "evidence.diagnosis_facts"
    def get(key: str) -> Any:    # 支持点号路径
    def merge(updates: dict, tool_id: str):  # 只允许post_check通过后调用
    def snapshot() -> dict:      # 浅拷贝
```

**Tier1自动注入算法**

```python
def _inject_tier1_tools(enabled_ids: list[str]) -> list[str]:
    tags_needed = set()
    for tid in enabled_ids:
        td = registry.get(tid)
        if td: tags_needed.update(td.accuracy_tags)

    # 注入匹配tags的injectable工具
    for tag in tags_needed:
        for injectable in registry.get_injectable_by_tag(tag):
            if injectable.id not in seen: result.append(injectable.id)

    # 始终注入安全护栏
    for safety_id in ["guard_input", "guard_output"]:
        if safety_id not in seen: result.append(safety_id)
```

### 1.2 执行模式

| 模式 | 实现文件 | 核心逻辑 |
|------|---------|---------|
| `tool_native` | agent_runner.py `_run_tool_native()` | LLM chat_with_tools → pre_check → execute → post_check → merge → 循环 |
| `llm_plan` | agent_runner.py `_run_llm_planned()` | LLM extract_json(ROUTING_PROMPT) → 按计划调用Expert |
| `fixed_order` | agent_runner.py `_run_fixed_order()` | 遍历agent.expert_ids → 串行调用 |
| `single_expert` | agent_runner.py `_run_single_expert()` | 调用默认Expert或用agent.system_prompt直接调LLM |

### 1.3 17个工具的技术实现

| 工具 | 类型 | 底层实现 |
|------|------|---------|
| guard_input | Tier1 确定性 | guardrails.validate_input() — 正则+规则引擎 |
| guard_output | Tier1 确定性 | guardrails.validate_output() — 阻断词硬编码黑名单 |
| search_icd10_index | Tier1 确定性 | code_dict_service.search_icd10() — rapidfuzz模糊匹配 |
| search_icd9_index | Tier1 确定性 | code_dict_service.search_icd9() — rapidfuzz模糊匹配 |
| rank_evidence | Tier1 确定性 | rank_all_evidence() — 文档来源评分+证据强度算法 |
| calibrate_confidence | Tier1 确定性 | calibrate_all() — 多源加权+风险分层策略 |
| analyze_disagreements | Tier1 确定性 | analyze_disagreements() — 金标准对比 |
| extract_evidence | Tier2 LLM | EvidenceExtractionExpert — LLM提取结构化JSON |
| reconstruct_timeline | Tier2 LLM | TimelineReconstructionExpert — LLM时间线构建 |
| assign_diagnosis_code | Tier2 LLM | LLM在候选集中选择编码(不能编造) |
| assign_procedure_code | Tier2 LLM | LLM在候选集中选择编码(不能编造) |
| verify_evidence | Tier2 LLM | EvidenceVerificationExpert — LLM验证 |
| analyze_drg_impact | Tier2 LLM | DRGDIPExpert — LLM分析 |
| check_documentation_gaps | Tier2 LLM | DocumentationGapExpert — LLM分析 |
| cdi_review | Tier2 LLM | CDIExpert — LLM审查 |
| format_report | Tier2 LLM | ReportExpert — LLM生成Markdown/HTML |
| generate_cdi_query | Tier2 LLM | LLM生成符合规范的CDI查询 |

---

## 二、权限系统

**文件**: `backend/app/services/permissions.py`

**核心类结构**

```python
@dataclass
class ToolPermission:
    tool_id: str
    allowed: bool = False          # 默认DENY
    max_per_session: int = 50      # 速率限制
    requires_human: bool = False   # 人机协同门
    scope: list[str] = []          # 允许访问的context key
    _invocation_count: int = 0     # 运行时追踪

    def check() -> PermissionOutcome:   # ALLOW | DENY | NEEDS_HUMAN
    def record_invocation() -> None:     # 成功调用后记录

class PermissionPolicy:
    permissions: dict[str, ToolPermission]

    def check(tool_id: str) -> PermissionOutcome:
    def record(tool_id: str) -> None:
    def to_config() -> dict:            # 序列化到Agent.config
    @classmethod from_config(dict):     # 从Agent.config反序列化

    # 预设工厂方法
    @classmethod medical_coding()    # 15工具
    @classmethod cdi_audit()        # 9工具
    @classmethod drg_analysis()     # 11工具
    @classmethod restrictive()      # 6工具
    @classmethod full_access()      # 17工具
```

**权限预设决策矩阵**

| 工具 | medical_coding | cdi_audit | drg_analysis | restrictive | full_access |
|------|:---:|:---:|:---:|:---:|:---:|
| search_icd10_index | ✅ | ❌ | ✅ | ✅ | ✅ |
| search_icd9_index | ✅ | ❌ | ✅ | ✅ | ✅ |
| rank_evidence | ✅ | ✅ | ✅ | ✅ | ✅ |
| calibrate_confidence | ✅ | ❌ | ✅ | ✅ | ✅ |
| analyze_disagreements | ✅ | ❌ | ❌ | ❌ | ✅ |
| guard_input | ✅ | ✅ | ✅ | ✅ | ✅ |
| guard_output | ✅ | ✅ | ✅ | ✅ | ✅ |
| extract_evidence | ✅ | ✅ | ✅ | ❌ | ✅ |
| assign_diagnosis_code | ✅ | ❌ | ✅ | ❌ | ✅ |
| assign_procedure_code | ✅ | ❌ | ✅ | ❌ | ✅ |
| verify_evidence | ✅ | ✅ | ❌ | ❌ | ✅ |
| analyze_drg_impact | ❌ | ❌ | ✅ | ❌ | ✅ |
| check_documentation_gaps | ❌ | ✅ | ❌ | ❌ | ✅ |
| cdi_review | ❌ | ✅ | ❌ | ❌ | ✅ |
| format_report | ✅ | ✅ | ✅ | ❌ | ✅ |
| generate_cdi_query | ❌ | ✅ | ❌ | ❌ | ✅ |
| reconstruct_timeline | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 三、安全体系

### 3.1 凭据隔离

**文件**: `backend/app/services/credential_vault.py`

```python
class CredentialVault:
    _cache: dict[str, str]        # 内存缓存

    def resolve(service: str) -> str:
        # 读取 env: ICODER_CREDENTIAL_{SERVICE_UPPER}
        # 抛 CredentialNotFound 如果未配置
        # 永不在日志中输出实际值

    def resolve_optional(service: str) -> str | None:
    def inject_headers(service: str, headers: dict) -> dict:
        # 注入 Authorization: Bearer <credential>
        # 调用者永不见凭据值

    def health_check() -> dict:
        # {"required": {"llm": "configured"}, "optional": {..}}

credential_vault = CredentialVault()  # 全局单例
```

**LLM API Key 解析流程**: `llm_service._resolve_api_key()` → `ICODER_CREDENTIAL_LLM` → `DEEPSEEK_API_KEY` → `settings.LLM_API_KEY`

### 3.2 审计链

**文件**: `backend/app/services/runtime.py`

```python
class AuditEvent:
    event_id: str          # 12位随机hex
    timestamp: str         # ISO 8601 UTC
    case_id: str           # 关联的pipeline/agent运行ID
    event_type: str        # "tool_executed" | "contract_denied" | "permission_denied"
    actor: str             # "agent_runner" | "orchestrator"
    payload: dict          # 事件数据
    payload_hash: str      # SHA-256截断16位

class AuditChain:
    _events: list[AuditEvent]   # Append-only

    def record(event_type, actor, payload) -> AuditEvent:
    def verify_integrity() -> bool:   # 重放验证所有payload_hash
    def replay(from_idx=0) -> list:   # 完整决策链重放
    def get_recent(n=10) -> list:
```

### 3.3 安全护栏

**文件**: `backend/app/services/guardrails.py`

```python
class SafetyGuardrails:
    async def validate_input(text: str) -> dict:
        # 1. 最小长度检查 (>=10 chars, 警告)
        # 2. 最大长度检查 (<=50000 chars)
        # 3. PHI检测: 身份证(18位数字+X)、手机号(1[3-9]\d{9})、邮箱、信用卡
        # 4. 屏蔽词: inject, bypass, exploit, override, jailbreak
        # 5. 返回: {"valid": bool, "violations": [...]}

    async def validate_output(text: str) -> dict:
        # 1. 处方检测: 剂量+药品名模式
        # 2. 急诊检测: 立即就医/急诊/抢救
        # 3. 诊断断言检测: 确诊/明确为(需加免责声明)
        # 4. 可疑编码检测: 过于精确的编码(可能是幻觉)
        # 5. 返回: {"valid": bool, "requires_disclaimer": bool, "violations": [...]}
```

### 3.4 登录安全

**文件**: `backend/app/api/auth.py`

```python
class LoginRateLimiter:
    _attempts: dict[str, list[float]]   # key → 时间戳列表
    max_attempts: int = 5
    window_seconds: int = 300

    def check(key: str) -> bool:        # 清理过期+检查剩余次数
    def record(key: str) -> None:       # 记录尝试
    def remaining(key: str) -> int:     # 剩余可用次数

login_limiter = LoginRateLimiter(5, 300)  # 全局单例
```

**Token模型**: `TokenBlacklist` (SHA-256哈希存储，关联user_id+过期时间) | `PasswordResetToken` (1小时有效期+is_used标记)

---

## 四、账号体系

### 4.1 认证流程

```
注册:
  POST /api/auth/register {username, password, email, full_name}
    → User创建 (SHA-256+salt哈希密码)
    → Organization自动创建
    → OrganizationMember创建 (Owner)
    → JWT access+refresh token返回

登录:
  POST /api/auth/login {username, password}
    → User查询
    → verify_password(plain, hashed)   # SHA-256+salt 或 bcrypt
    → LoginRateLimiter检查+记录
    → 获取用户组织列表
    → JWT access+refresh token返回

Token刷新:
  POST /api/auth/refresh {refresh_token}
    → decode_token验证
    → 检查token_type=="refresh"
    → 生成新access+refresh token
```

### 4.2 JWT Token结构

```json
// Access Token (8小时)
{
  "sub": "user_id",
  "username": "admin",
  "role": "admin",
  "org_id": "current_org_id",
  "exp": 1780050000,
  "iat": 1780020000,
  "type": "access"
}

// Refresh Token (7天)
{
  "sub": "user_id",
  "org_id": "current_org_id",
  "exp": 1780600000,
  "type": "refresh"
}
```

### 4.3 多租户数据模型

```sql
users (id, username, email, hashed_password, full_name, role, department, is_active)
organizations (id, name, slug, plan, is_active)
organization_members (organization_id, user_id, role, is_default)
team_members (organization_id, user_id, email, name, role, status)
```

**隔离策略**: 每个API请求通过JWT中的`org_id`确定当前组织，所有查询添加`organization_id`过滤。

### 4.4 OAuth 2.0 M2M

```python
# backend/app/models/oauth.py
class OAuthClient:
    client_id: str           # "icoder-{token_hex(12)}"
    client_secret_hash: str  # SHA-256
    scopes: str              # "api:read api:write"
    token_expires_seconds: int  # 3600

class OAuthToken:
    token_hash: str          # SHA-256
    expires_at: datetime
    is_revoked: bool

# 认证流程:
# POST /api/oauth/token {client_id, client_secret, grant_type:"client_credentials"}
#   → OAuthClient.verify_secret(plaintext, secret_hash)
#   → 生成JWT (type:"client_credentials")
#   → OAuthToken记录创建
```

---

## 五、编码审核管道

### 5.1 管道架构

**文件**: `backend/app/agents/orchestrator.py`

```python
class AgentOrchestrator:
    def __init__(self):
        # 13个Expert单例
        self.evidence_expert       # EvidenceExtractionExpert
        self.timeline_expert       # TimelineReconstructionExpert
        self.diagnosis_expert      # ICDDiagnosisExpert
        self.procedure_expert       # ProcedureCodingExpert
        self.homepage_expert       # MedicalRecordHomepageExpert
        self.drg_expert            # DRGDIPExpert
        self.doc_gap_expert        # DocumentationGapExpert
        self.evidence_verify_expert # EvidenceVerificationExpert
        self.report_expert         # ReportExpert
        self.cdi_expert            # CDIExpert
        self.denial_expert         # DenialManagementExpert
        self.audit_expert          # AuditTrailExpert
        self.hcc_expert            # HCCRiskAdjustmentExpert

    async def run_pipeline(encounter_data, progress_callback=None) -> dict:
        # 初始化DeterministicRuntime
        # 9步串行执行，每步try/except+fallback
        # guardrails输入验证
        # 5次状态转换: INGESTED→CONTEXT_READY→FACTS_EXTRACTED→
        #              CANDIDATES_READY→RULES_VALIDATED→...
        #              RISK_IDENTIFIED→REVIEW_REQUIRED→
        #              DECISION_CONFIRMED→ARCHIVED
```

### 5.2 Context流转

```python
context = {
    "pipeline_id": str,           # 12位hex
    "encounter_id": str,          # ENC-XXXX
    "documents": list[dict],      # 病历文档
    "admission_reason": str,
    "existing_diagnosis_codes": list,
    "existing_procedure_codes": list,

    # 步骤1输出
    "evidence": {"diagnosis_facts": [...], "procedure_facts": [...], "chief_complaint": "..."},

    # 步骤2输出
    "timeline": {"events": [...], "event_count": N},

    # 步骤1b输出
    "clinical_triage": {"codable_diagnosis_facts": [...], "codable_procedure_facts": [...]},

    # 步骤3a输出
    "diagnosis_candidates": [{"code": "M80.900", "name": "...", "score": 0.85}],

    # 步骤3b输出
    "procedure_candidates": [...],

    # 步骤4-6输出
    "primary_diagnosis": {"code": "...", "confidence": 0.95},
    "main_procedure": {...},

    # 步骤7输出
    "verification": {"verifications": [...], "summary": {...}},
    "evidence_ranking": {"ranked_candidates": [...], "unsupported_codes": [...], "conflicts": [...]},

    # 步骤7c-7d输出
    "disagreement_analysis": {...},
    "routing_decisions": [{"code": "...", "tier": "auto|review|escalate", "confidence": 0.X}],

    # 步骤8a-8b输出
    "drg_impact": {"expected_drg": "RU14", ...},
    "documentation_gaps": [...],

    # 步骤9输出
    "report_markdown": str,
    "report_html": str,
    "human_checklist": [...],
    "uncodable_items": [...],
}
```

### 5.3 关键服务

| 服务 | 文件 | 算法 |
|------|------|------|
| code_dict_service | code_dictionary.py | rapidfuzz.fuzz.partial_ratio 模糊匹配 |
| rank_all_evidence | evidence_ranker.py | 文档来源权威度评分 + 证据文本关键词匹配度 |
| calibrate_all | confidence_calibrator.py | 输入加权(raw_score×0.35 + evidence×0.25 + rules×0.15 - penalty×0.25) × 风险分层策略表 |
| analyze_disagreements | disagreement_analyzer.py | AI编码 vs 金标准编码逐项比对 |
| clinical_triage_service | clinical_triage.py | 规则引擎：事实→可编码/病史/已排除/偶发性 |

### 5.4 编码字典

- ICD-10-CN: 33,304条编码，含章节+类目+亚目
- ICD-9-CM-3: 23,165条手术编码
- 数据源: `backend/data/code_dicts/icd_data.py`
- 搜索算法: rapidfuzz模糊匹配 (partial_ratio)，top_k=10

---

## 六、前端架构

### 6.1 技术栈

```
React 18 + TypeScript + Vite 5
Tailwind CSS + Lucide React Icons
Zustand (全局状态) + React Router v6
i18n (中/英双语)
```

### 6.2 组件树

```
App
├── LoginPage            # 登录/注册/忘记密码
├── Layout
│   ├── Sidebar          # 15项导航
│   └── Content
│       ├── HomePage                 # 仪表板
│       ├── AgentsPage              # Agent列表
│       ├── AgentDetailPage         # Agent详情（聊天+设置+工具+代码）
│       │   ├── ToolSelector        # 工具选择器 ★新增
│       │   ├── SettingsCodeTab     # 设置/代码/工具三tab
│       │   ├── A2ACollaboration    # A2A Agent协作
│       │   └── CodeSnippet         # SDK代码生成
│       ├── NewAgentPage            # 新建Agent（模板选择）
│       ├── SpeechToTextPage        # 语音转录
│       ├── TextGenerationPage      # 文书生成
│       ├── FactExtractionPage      # 事实提取
│       ├── MedicalCodingPage       # 医学编码
│       ├── EmbeddedAssistantPage   # 嵌入助手
│       ├── OrchestrationPage       # 编码审核（已从菜单移除，API保留）
│       ├── SettingsPage            # 系统设置 ★新增密码修改
│       ├── APIClientsPage          # API客户端管理
│       ├── TeamPage                # 团队管理
│       ├── BillingPage             # 计费
│       ├── UsagePage               # 用量监控
│       ├── GoldCasesPage           # 金标准病例
│       ├── EvaluationPage          # 评估
│       └── ExpertLibraryPage       # 专家库
```

### 6.3 状态管理

```typescript
// frontend/src/store/index.ts
interface AuthState {
    user: User | null
    token: string
    refreshToken: string
    organizations: OrgInfo[]
    currentOrgId: string
    login(user, token, refreshToken, orgs, orgId)
    logout()
    setCurrentOrg(orgId)
}
```

### 6.4 API层

```typescript
// frontend/src/services/api.ts
const api = axios.create({
    baseURL: '/api',
    headers: { 'Content-Type': 'application/json' }
})
// 自动注入 JWT token
api.interceptors.request.use(config => {
    const token = useAuthStore.getState().token
    if (token) config.headers.Authorization = `Bearer ${token}`
    return config
})

export const authApi    = { login, register, forgotPassword, changePassword, ... }
export const agentsApi  = { list, get, create, update, delete, messageSend, ... }
export const expertsApi = { list, run, ... }
export const toolsApi   = { list, categories, permissionPresets }  // ★新增
export const reviewsApi = { create, list, get, ... }
```

---

## 七、LLM集成

### 7.1 LLM服务层

**文件**: `backend/app/services/llm_service.py`

```python
class LLMService:
    client: AsyncOpenAI      # api.deepseek.com/v1
    model: str = "deepseek-chat"
    max_tokens: int = 4096
    temperature: float = 0.1
    max_retries: int = 3

    async def chat(messages, temperature, max_tokens, response_format) -> dict:
        # 标准chat completion + 指数退避重试(1s,2s) + token追踪

    async def chat_stream(messages, temperature) -> AsyncGenerator:
        # OpenAI stream=True → 逐token yield

    async def chat_with_tools(messages, tools, temperature) -> dict:
        # 支持function calling → 返回tool_calls列表

    async def extract_json(prompt, text, schema_hint) -> dict:
        # temperature=0.05 + response_format="json" + markdown代码块回退提取
```

### 7.2 Expert执行层

**文件**: `backend/app/services/expert_runner.py`

```python
class ExpertRunner:
    async def run(expert, user_input, history, mcp_servers) -> str:
        # 组合: expert.system_prompt + history + user_input
        # 可选: MCP工具定义 → chat_with_tools
        # 工具调用: _handle_tool_calls → _real_mcp_call → LLM第二轮

    async def stream_run(expert, user_input, history) -> AsyncGenerator:
        # chat_stream逐token输出
```

---

## 八、数据库设计

### 8.1 核心表

```sql
-- 用户与认证
users (id, username, email, hashed_password, full_name, role, department, is_active, is_verified, created_at, updated_at)
api_keys (id, organization_id, owner_id, name, key_prefix, key_hash, is_active, last_used_at, created_at, updated_at)
oauth_clients (id, organization_id, name, client_id, client_secret_hash, description, scopes, is_active, owner_id, last_used_at, token_expires_seconds, created_at, updated_at)
oauth_tokens (id, organization_id, client_id, token_hash, scopes, expires_at, is_revoked, created_at, updated_at)
token_blacklist (id, token_hash, user_id, expires_at, revoked_reason, created_at, updated_at)                  -- ★新增
password_reset_tokens (id, user_id, token_hash, expires_at, is_used, created_at, updated_at)                   -- ★新增

-- 多租户
organizations (id, name, slug, plan, settings, is_active, created_at, updated_at)
organization_members (id, organization_id, user_id, role, is_default, created_at, updated_at)
organization_invites (id, organization_id, email, role, token, expires_at, accepted, created_at, updated_at)

-- 业务
encounters (id, organization_id, encounter_id, patient_id, department, admission_time, discharge_time, admission_reason, existing_diagnosis_codes, existing_procedure_codes, submitted_by, created_at, updated_at)
documents (id, organization_id, encounter_id, doc_type, title, content, doc_order, created_at, updated_at)
code_candidates (id, organization_id, review_id, finding, code_system, code, name, score, chapter, evidence_ids, status, rule_checks, created_at, updated_at)
coding_reviews (id, organization_id, encounter_id, status, human_review_status, documentation_gaps, uncodable_items, drg_impact, human_checklist, validation_summary, report_markdown, report_html, created_at, updated_at)

-- Agent
agents (id, organization_id, name, description, system_prompt, icon, category, expert_ids, default_expert_id, a2a_enabled, config, version, status, is_prebuilt, usage_count, created_by, created_at, updated_at)
experts (id, organization_id, name, description, system_prompt, capabilities, input_schema, output_schema, tags, icon, category, version, is_prebuilt, created_at, updated_at)

-- Runtime
runtime_sessions (id, organization_id, runtime_id, pipeline_id, review_id, agent_id, current_state, previous_state, state_entered_at, timeout_at, escalated, failed, archived, execution_path, total_processing_ms, error_count, content_hash, created_at, updated_at)
runtime_transitions (id, organization_id, runtime_id, from_state, to_state, actor, reason, created_at)
runtime_audit_records (id, organization_id, runtime_id, event_type, actor, payload, payload_hash, created_at)
runtime_duc_decisions (id, organization_id, runtime_id, action, reviewer_id, decision, rationale, created_at)
```

### 8.2 索引策略

- users: idx(username), idx(email)
- agents: idx(organization_id), idx(category), idx(status)
- encounters: idx(organization_id), idx(encounter_id)
- coding_reviews: idx(organization_id), idx(encounter_id)
- runtime_sessions: idx(runtime_id), idx(organization_id)
- token_blacklist: idx(token_hash), idx(user_id)

---

## 九、测试策略

### 9.1 测试分层

```
tests/
├── test_services/         # 577个服务层单元测试
│   ├── test_permissions.py          # 19 tests — Deny-First权限
│   ├── test_tool_contract.py        # 41 tests — 合同引擎+注册表
│   ├── test_agent_runner_tool_native.py  # 7 tests — Tool-Native执行
│   ├── test_credential_vault.py    # 12 tests — 凭据隔离
│   ├── test_guardrails.py          # 10 tests — 安全护栏
│   ├── test_runtime_discipline.py  # 状态机+审计链
│   ├── test_code_dictionary.py     # ICD编码字典
│   ├── test_evidence_ranker.py     # 证据排名
│   ├── test_confidence_calibrator.py  # 置信度校准
│   └── ...
├── test_api/             # API层测试
│   ├── test_auth.py
│   └── test_oauth.py
├── test_services/regression/  # 回归测试
└── integration/          # E2E集成测试
    └── test_e2e_coding_pipeline.py  # 4 tests — 完整业务流程
```

### 9.2 测试覆盖

| 类别 | 数量 | 说明 |
|------|------|------|
| 合同引擎 | 41 | ToolRegistry + SymbolicState + pre/post条件 |
| 权限系统 | 19 | ToolPermission + PermissionPolicy + 5预设 |
| 执行引擎 | 7 | Tool-Native + Tier1注入 + OpenAI工具构建 |
| 凭据隔离 | 12 | CredentialVault + AuditChain |
| 安全护栏 | 10 | 6条规则 + 输入/输出验证 |
| 编码字典 | 8 | ICD-10/ICD-9搜索 |
| 证据/校准 | 20+ | 证据排名+置信度校准+分歧分析 |
| 管道 | 40+ | Orchestrator各步骤 |
| API | 20+ | Auth/OAuth/Encounters/Reviews |
| E2E | 4 | 完整业务流程 |

---

## 十、部署架构

### 10.1 开发环境

```bash
# 后端
export ICODER_CREDENTIAL_LLM="sk-xxx"
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 前端
export VITE_API_TARGET="http://localhost:8000"
cd frontend && npx vite --port 3000

# 种子数据
python -c "from app.seed import seed; import asyncio; asyncio.run(seed())"
```

### 10.2 生产环境

```bash
export ICODER_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export ICODER_CREDENTIAL_LLM="<production-key>"
export APP_ENV=production
export DEBUG=false
export DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/icoder"

# 数据库迁移
alembic upgrade head

# 后端 (gunicorn + uvicorn workers)
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000

# 前端 (静态构建)
cd frontend && npx vite build
# 产物部署到 nginx/cdn
```

### 10.3 前端nginx配置

```nginx
server {
    listen 80;
    server_name icoder.example.com;

    # 前端静态文件
    root /var/www/icoder/dist;
    index index.html;

    # SPA路由
    location / {
        try_files $uri $uri/ /index.html;
    }

    # API代理
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```
