# iCoDer v1 Agent Card Spec

**作者**: iCoDer 架构组
**日期**: 2026-06-20
**状态**: Draft (待审, Phase 1 spec 之五)
**范围**: iCoDer v1 Agent Card 后端 — AgentCard/AgentDefinition/ExpertCard 数据结构、Registry 架构、Agent 注册/注销、Agent Card 动态生成、4 个 Discovery 端点、第三方 ISV 注册 stub、Agent Card 缓存
**前置**:
- `ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20, Q7 决策)
- `ICODER_V1_A2A_SPEC.md` (Draft 2026-06-20, §7.4 Discovery 端点 + §8 Agent Card schema 协议格式定义; 本 spec 是其后端落地)
- `ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft, §5.3 M2aRecorder 集成)
- `ICODER_V1_CONTEXT_SPEC.md` (Draft, RBAC 引用)
- `ICODER_V1_MCP_SPEC.md` (Draft, Expert 工具声明引用)
**后续**: `ICODER_V1_TASK_SPEC.md` (Phase 1 收尾)

---

## 0. 文档目的

把 RFC 第 3.2.9 节"Expert Registry"+ 第 3.2.10 节"Agent Card" + Q7 决策（Expert 独立 + 可共享）展开成**可实现的详细 spec**: 与 A2A spec §8 的分工（**A2A spec 定义协议格式, 本 spec 定义后端**）、AgentCard/AgentDefinition/ExpertCard 三层数据结构、Registry 架构（内存 → DB 演进路径）、Agent 注册/注销流程、Agent Card 从 AgentDefinition 动态生成、4 个 Discovery 端点（与 A2A spec §7.4 对齐）、第三方 ISV 注册 stub、Agent Card 缓存策略、测试矩阵。

本 spec 是 Q7 决策的落地核心文档, 也是 Phase 4 第三方 ISV 贡献 Expert 的前置。

---

## 1. 背景与决定

### 1.1 上游决定 (从 RFC 来)

| 决策 | 拍板 | 对本 spec 的影响 |
|------|------|------------------|
| **Q7** Expert 独立 + 可共享 | RFC 第 9 节 | ExpertCard 必含 system_prompt / tools / model / non_goals / output_contract 5 个独立配置字段 |
| **Q5** 旧 AgentRunner 不保留, clean replace | RFC 第 9 节 | 旧 `a2a_protocol.py` 的 `register_all_experts()` 30 预置 Expert **完全重做**, 改为从 AgentDefinition 动态加载 |
| **Q4** Context 隔离对齐 Corti | RFC 第 9 节 | Agent 注册/查询的 RBAC 按 contextId 隔离 (Phase 4) |

### 1.2 与 A2A spec §8 的明确分工

| 维度 | A2A spec | 本 spec (Agent Card) |
|------|----------|----------------------|
| **范围** | A2A 协议层 | 后端实现层 |
| **AgentCard schema** | 定义 JSON 结构 / 字段 (协议) | 实现数据类 (Pydantic) / 校验 |
| **Discovery 端点 URL/方法** | 定义 URL + HTTP 方法 | 实现 FastAPI 路由 + Handler |
| **Metadata 字段** | 定义 metadata 命名空间 (协议) | 实现 iCoDer metadata 字段 (production_writeback_blocked / phi_redacted / rule_sets) |
| **Card 生成** | (不涉及) | 从 AgentDefinition 动态生成 + 缓存 |
| **Registry 存储** | (不涉及) | 内存 dict (Phase 1) → SQLite (Phase 4) |
| **第三方 ISV 注册** | (不涉及) | Registry 注册 API + 校验 (Phase 4 stub) |

**核心原则**: A2A spec 写"协议长什么样", 本 spec 写"后端怎么实现"。

### 1.3 Corti Agent Card 行为参考

来源: `E:\Corti4C\Corti\llms-full.txt` (corti.ai docs 完整抓取, 2026-06-20)

| 行为 | Corti 做法 | iCoDer 对齐 |
|------|-----------|-------------|
| Discovery 端点 | `GET /.well-known/agent.json` | **同** (A2A spec §7.4.1) |
| 单 Agent Card | `GET /agents/{id}/card` | **同** (A2A spec §7.4.2) |
| Agent 列表 | (类似) `GET /agents/list-registry-experts` | **改**: `GET /api/icoder/agents` (iCoDer URL 风格) |
| 第三方注册 | (类似) MCP server 注册 Expert | **同** (Phase 4) |
| Card 缓存 | (类似) 静态 + 动态生成 | **同** (本 spec §7.3) |

### 1.4 关键边界 (从 RFC 1.3 + 4.4 来)

- `production_writeback_blocked = true` 恒定 (Agent Card metadata 必带, 不允许 false)
- Agent 不暴露任何"可写"动作 (Card.skills 全部 read-only)
- 第三方 ISV 注册的 Expert 必须通过 iCoDer 安全审查 (Phase 4 留)

---

## 2. 目标 / 非目标

### 2.1 Goals (本 spec 必须达成)

1. **G1**: AgentCard / AgentDefinition / ExpertCard 三层数据结构清晰, Q7 落地
2. **G2**: Registry 内存实现 (Phase 1), 演进到 DB (Phase 4) 路径明确
3. **G3**: Agent 注册/注销 API 完整 (内置 Agent 自动注册 + 第三方 ISV stub)
4. **G4**: Agent Card 从 AgentDefinition 动态生成 + 缓存
5. **G5**: 4 个 Discovery 端点实现 (与 A2A spec §7.4 对齐)
6. **G6**: iCoDer 特有 metadata 字段 (production_writeback_blocked / rule_sets / non_goals) 正确暴露
7. **G7**: RBAC (Phase 1: 全角色可查; Phase 4: 按角色限制)
8. **G8**: Agent Card 版本管理 (semver)
9. **G9**: 测试矩阵明确 (单元/集成/e2e)
10. **G10**: 第三方 ISV 注册 API 留 stub (Phase 4 完整实现)

### 2.2 Non-Goals (本 spec 明确不做)

1. **N1**: 不实现 Registry DB 持久化 (Phase 4 留, Phase 1 内存 dict)
2. **N2**: 不实现第三方 ISV 完整注册 (Phase 4, Phase 1 stub)
3. **N3**: 不实现 Agent 热更新 (Phase 4, Phase 1 重启生效)
4. **N4**: 不实现 Agent Card 编辑 API (只读, 改 AgentDefinition 走单独流程)
5. **N5**: 不实现 8 原子 Agent 全部注册 (Phase 3 留, Phase 1 只 homepage-coding-review)
6. **N6**: 不实现 RBAC 角色权限细粒度控制 (Phase 4)
7. **N7**: 不实现 Agent 评分 / 推荐 (Phase 6)
8. **N8**: 不实现跨实例 Registry 同步 (Phase 6 多实例)

---

## 3. 三层数据结构

### 3.1 关系图

```
AgentCard (公开协议格式, A2A spec §8)
    ↑ 从 AgentDefinition 动态生成
    │
AgentDefinition (内部, 包含 Experts + Tools)
    │
    ├─ system_prompt
    ├─ rule_sets[]
    ├─ non_goals[]
    ├─ output_contract
    └─ experts[] ────▶ ExpertCard (Q7 独立 metadata)
                          │
                          ├─ id (e.g., "coding-expert")
                          ├─ system_prompt (Expert 自己的)
                          ├─ tools[] (MCP tools 列表)
                          ├─ model (Expert 自己的 LLM model)
                          ├─ non_goals (Expert 自己的非目标)
                          └─ output_contract (Expert 自己的输出契约)
```

### 3.2 AgentDefinition (内部, 非公开)

```python
class AgentDefinition(BaseModel):
    """iCoDer 内部 Agent 定义 — Registry 存储的源头. (非公开协议格式)"""
    
    # 必填
    id: str                              # Agent ID (e.g., "homepage-coding-review")
    name: str                            # Agent 显示名
    description: str                     # Agent 功能描述
    version: str = "1.0.0"               # Agent 版本 (semver)
    
    # Orchestrator 必填
    system_prompt: str                   # Orchestrator 给 Planner 用的 system_prompt (含 PHI/production_writeback_blocked 提示)
    
    # 业务字段
    rule_sets: list[str] = []            # 启用的 RuleSet (medical_coding / drg_dip / insurance_audit / charge_compliance / document_evidence / audit)
    non_goals: list[str] = []            # Agent 不做什么 (e.g., "不直接做最终诊断决策")
    output_contract: dict = {}           # Agent 输出的 JSON schema (e.g., MedicalCodingOutputSchema)
    
    # Expert 列表
    experts: list[ExpertCard]            # Agent 包含的 Experts (Q7: 各自独立 metadata)
    
    # 元数据
    tags: list[str] = []                 # 标签 (e.g., ["coding", "drg", "audit"])
    capabilities: list[str] = []         # 能力 (e.g., ["icd_coding", "drg_grouping"])
    
    # 内部
    source: str = "builtin"              # builtin / isv / custom
    author: str = "iCoDer"               # 作者
    created_at: datetime
    updated_at: datetime
```

### 3.3 ExpertCard (Q7 决策落地, 内部)

```python
class ExpertCard(BaseModel):
    """Expert 元数据 — Q7 决策: 独立 + 可共享.
    
    "独立" = 每个 Expert 拥有自己的 system_prompt / tools / model / non_goals / output_contract
    "可共享" = 多个 Agent 可共用同一 Expert, 多个 Expert 可共用同一 LLM Gateway
    """
    
    # 必填
    id: str                              # Expert ID (e.g., "coding-expert", "drg-expert")
    name: str                            # Expert 显示名
    description: str                     # Expert 功能描述
    
    # Q7 独立配置 5 件套 (必填)
    system_prompt: str                   # Expert 自己的 system_prompt (Orchestrator 不覆盖, A2A spec §7.3)
    tools: list[str] = []                # Expert 可调的 MCP tools (e.g., ["search_icd", "verify_code"])
    model: str = "deepseek-v4-flash"     # Expert 自己的 LLM model (env 可配)
    non_goals: list[str] = []            # Expert 明确不做什么
    output_contract: dict = {}           # Expert 输出的 JSON schema
    
    # 可选
    capabilities: list[str] = []         # 能力声明 (e.g., ["icd_coding"])
    version: str = "1.0.0"
    
    # 内部
    mcp_server: str | None = None        # Expert 自己的 MCP server (Phase 1: stdio / Phase 4: HTTP)
    timeout_ms: int = 30000              # Expert 委托超时
    retry_policy: dict = {}              # 重试策略 (默认: 2 次指数退避)
```

### 3.4 AgentCard (公开协议格式, A2A spec §8 已定义)

按 A2A spec §8.1 完整定义, 本 spec 负责**从 AgentDefinition 动态生成** AgentCard:

```python
def generate_agent_card(agent_def: AgentDefinition) -> AgentCard:
    """从 AgentDefinition 动态生成 AgentCard (A2A v0.3 协议格式)."""
    return AgentCard(
        name=agent_def.name,
        description=agent_def.description,
        url=f"/api/icoder/agents/{agent_def.id}/v1/message:send",
        version=agent_def.version,
        provider="iCoDer",
        documentation_url=f"/docs/agents/{agent_def.id}",
        capabilities=AgentCapabilities(
            streaming=False,  # Phase 1 不实现
            pushNotifications=False,  # Phase 6
            stateTransitionHistory=True,  # iCoDer 必为 true (审计)
            extensions=[]
        ),
        skills=_generate_skills(agent_def),  # 从 output_contract 推导
        defaultInputModes=["text"],
        defaultOutputModes=["application/json"],
        securitySchemes={"bearer": {"type": "apiKey", "description": "Phase 4 才校验"}},
        metadata={
            "icoder": {
                "rule_sets": agent_def.rule_sets,
                "non_goals": agent_def.non_goals,
                "experts": [e.id for e in agent_def.experts],
                "tags": agent_def.tags,
                "capabilities": agent_def.capabilities,
                "production_writeback_blocked": True,  # 恒 true
                "phi_redaction": "required"
            }
        }
    )


def _generate_skills(agent_def: AgentDefinition) -> list[AgentSkill]:
    """从 AgentDefinition.output_contract 推导 Skills."""
    # ... (从 output_contract 抽取 skill 列表)
```

**关键 (Q7 落地)**:
- AgentCard 不直接暴露 ExpertCard (避免 N5 过度暴露)
- AgentCard.metadata.icoder.experts 只列 Expert ID 列表, 详细 metadata 在单独端点查询 (Phase 4 留 `GET /experts/{id}`)

---

## 4. Registry 架构

### 4.1 Phase 1: 内存 Registry

```python
class AgentRegistry:
    """Phase 1 内存 Registry — 进程启动时加载, 进程结束丢失."""
    
    def __init__(self):
        self._agents: dict[str, AgentDefinition] = {}  # agent_id → AgentDefinition
        self._by_capability: dict[str, set[str]] = {}  # capability → set of agent_ids
    
    def register(self, agent_def: AgentDefinition) -> None:
        """注册一个 Agent (启动时 + 热注册都用此)."""
        if agent_def.id in self._agents:
            raise AgentAlreadyRegisteredError(...)
        self._agents[agent_def.id] = agent_def
        for cap in agent_def.capabilities:
            self._by_capability.setdefault(cap, set()).add(agent_def.id)
        # M2aRecorder: stage("agent_registered", {agent_id, source, version})
    
    def unregister(self, agent_id: str) -> None:
        ...
    
    def get(self, agent_id: str) -> AgentDefinition | None:
        ...
    
    def list_all(self) -> list[AgentDefinition]:
        ...
    
    def find_by_capability(self, capability: str) -> list[AgentDefinition]:
        ...
    
    def count(self) -> int:
        return len(self._agents)
```

### 4.2 Phase 4: DB-backed Registry

```sql
CREATE TABLE agent_definitions (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL,
    version TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    rule_sets_json TEXT NOT NULL DEFAULT '[]',
    non_goals_json TEXT NOT NULL DEFAULT '[]',
    output_contract_json TEXT NOT NULL DEFAULT '{}',
    experts_json TEXT NOT NULL,           -- list[ExpertCard] JSON
    tags_json TEXT NOT NULL DEFAULT '[]',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL,                  -- builtin / isv / custom
    author TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',  -- active / deprecated / disabled
    
    INDEX idx_agent_defs_status (status),
    INDEX idx_agent_defs_source (source)
);
```

**Phase 1 → Phase 4 演进**:
- Phase 1: 内存 dict, 启动时从 `agent_definitions/*.json` 加载
- Phase 4: 启动时从 SQLite 加载, 运行时热注册
- 接口不变 (`register` / `unregister` / `get` / `list_all` / `find_by_capability`)

### 4.3 Registry 初始化

**Phase 1 启动流程**:
```
1. 启动时, 扫描 backend/official_agents/ 目录
2. 加载每个 Agent 的 .icoder-agent 包 (既有 AgentPackageV1)
3. 解析为 AgentDefinition
4. registry.register(agent_def)
5. Phase 1 默认注册 1 个 Agent: homepage-coding-review
```

**Phase 4 启动流程**:
```
1. 启动时, 读 SQLite agent_definitions 表
2. 加载 status='active' 的所有 Agent
3. registry.register(...) 同 Phase 1
4. 第三方 ISV 通过 Registry.register API 热注册
```

### 4.4 内置 Agent 列表 (Phase 1)

| Agent ID | Name | Experts | source |
|----------|------|---------|--------|
| `homepage-coding-review` | Homepage Coding Review Agent | coding-expert, drg-expert, compliance-expert (Phase 2-3) | builtin |

**Phase 3 完成后** (8 原子 Agent): 见 RFC §6 Phase 3 表

---

## 5. Agent 注册 / 注销

### 5.1 内置 Agent 自动注册

**位置**: `backend/app/icoder/agent_runtime/agent_card/builtin_loader.py`

**流程**:
```
1. 启动时, builtin_loader 扫描 backend/official_agents/*/
2. 加载每个 agent 的 agent_pack.json (既有 AgentPackageV1 格式)
3. 解析为 AgentDefinition
4. registry.register(agent_def)
5. M2aRecorder: stage("agent_registered_builtin", {agent_id, version, experts_count})
```

**Phase 1 内置 Agent 文件位置**:
```
backend/official_agents/
├── homepage-coding-review/
│   ├── agent_pack.json          # AgentPackageV1
│   ├── __init__.py
│   └── experts/
│       ├── coding_expert.py     # ExpertCard 解析源
│       └── drg_expert.py
```

### 5.2 第三方 ISV 注册 (Phase 4 stub)

**Phase 1 端点暴露但 stub**:

```python
# Phase 1: 端点暴露, 返回 501 UNSUPPORTED_OPERATION
@router.post("/api/icoder/registry/agents")
async def register_isv_agent(agent_def: AgentDefinition, request: Request):
    raise HTTPException(
        status_code=501,
        detail={
            "a2a_error_code": "UNSUPPORTED_OPERATION",
            "details": "Third-party ISV registration is Phase 4 (留待 Phase 4 实现). Phase 1 only supports builtin agents.",
            "phase": "phase_4_留"
        }
    )
```

**Phase 4 完整实现**:
- ISV 提供 `agent_pack.json` (AgentPackageV1 格式)
- ISV 提供 MCP server URL (HTTP transport, MCP spec §7.2)
- iCoDer 接收 AgentDefinition
- 校验: 必填字段 + production_writeback_blocked=true + rule_sets 合法 + tools 在 iCoDer 工具白名单内
- 注册到 Registry (DB-backed)
- 记录 M2aRecorder stage

### 5.3 Agent 注销

**Phase 1**: 不暴露 API, 启动时 + 配置文件控制
**Phase 4**: 暴露 `DELETE /api/icoder/registry/agents/{id}` API

### 5.4 Agent 更新

**Phase 1**: 重启生效 (改 agent_pack.json)
**Phase 4**: `PUT /api/icoder/registry/agents/{id}` 热更新 + version 递增

---

## 6. Agent Card 动态生成 + 缓存

### 6.1 动态生成

每次 `GET /api/icoder/agents/{id}/card` 调用:
1. 从 Registry 拿 AgentDefinition
2. 调用 `generate_agent_card(agent_def)` 生成 AgentCard
3. 返回 JSON

**为什么动态生成**:
- AgentDefinition 可能更新 (新版本, 新 Expert)
- iCoDer metadata 字段可能变 (e.g., 加新 compliance 字段)
- A2A spec 可能演进 (Phase 4+ 新字段)

### 6.2 缓存策略

**Phase 1 简化**:
- 不缓存 (每次实时生成)
- AgentDefinition 1 个 + 动态生成 < 1ms
- 缓存反而引入 stale 风险

**Phase 5 优化**:
- Agent Card 缓存 (per agent_id + version)
- 缓存 key: `(agent_id, version)`
- 缓存值: AgentCard JSON
- 失效: AgentDefinition 更新时主动失效

### 6.3 缓存安全

- 缓存必含 agent_id, 跨 agent_id 不命中
- 缓存必含 version, 老 version 仍可查 (审计需要)
- 缓存必带 `generated_at` 时间戳, 客户端可看 card 多老

---

## 7. Discovery 端点 (4 个, 与 A2A spec §7.4 对齐)

### 7.1 `GET /.well-known/agent.json` (A2A v0.3 标准)

**A2A spec §7.4.1 已定义**, 本 spec 负责实现:

```python
@router.get("/.well-known/agent.json")
async def well_known_agents():
    """A2A v0.3 标准 Discovery 端点."""
    agents = registry.list_all()
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "url": f"/api/icoder/agents/{a.id}/v1/message:send",
                "version": a.version
            }
            for a in agents
        ]
    }
```

**Phase 1 默认**: 1 个 Agent (homepage-coding-review)

### 7.2 `GET /api/icoder/agents/{agent_id}/card`

**A2A spec §7.4.2 已定义**, 本 spec 负责实现:

```python
@router.get("/api/icoder/agents/{agent_id}/card")
async def get_agent_card(agent_id: str):
    agent_def = registry.get(agent_id)
    if not agent_def:
        raise HTTPException(status_code=404, detail={"a2a_error_code": "AGENT_NOT_FOUND"})
    return generate_agent_card(agent_def)
```

**响应**: 完整 A2A v0.3 AgentCard (A2A spec §8.3 样板)

### 7.3 `GET /api/icoder/agents`

**A2A spec §7.4.3 已定义**, 本 spec 负责实现:

```python
@router.get("/api/icoder/agents")
async def list_agents(capability: str | None = None):
    if capability:
        agents = registry.find_by_capability(capability)
    else:
        agents = registry.list_all()
    return {
        "agents": [
            {
                "id": a.id,
                "name": a.name,
                "version": a.version,
                "capabilities": a.capabilities,
                "tags": a.tags
            }
            for a in agents
        ],
        "total": len(agents)
    }
```

**Query**: `?capability=icd_coding` 按能力过滤

### 7.4 `GET /llms.txt` (LLM 友好)

**A2A spec §7.4.4 已定义**, 本 spec 负责实现:

```python
@router.get("/llms.txt")
async def llms_txt():
    agents = registry.list_all()
    md = "# iCoDer v1 Agent Runtime\n\n"
    md += "iCoDer 是面向中国医院场景的医疗收入合规 AI 平台。\n\n"
    md += "## Available Agents\n\n"
    for a in agents:
        md += f"### {a.name} (v{a.version})\n"
        md += f"- ID: `{a.id}`\n"
        md += f"- 描述: {a.description}\n"
        md += f"- 端点: POST /api/icoder/agents/{a.id}/v1/message:send\n"
        md += f"- 输入: text\n"
        md += f"- 输出: application/json\n"
        md += f"- Experts: {[e.id for e in a.experts]}\n"
        md += f"- 能力: {a.capabilities}\n\n"
    return PlainTextResponse(md, media_type="text/markdown")
```

**LLM 阅读用**: Claude / GPT 读这个文件可了解 iCoDer Agent 生态

### 7.5 端点实现路由表

| 端点 | 文件:函数 | 引用 A2A spec |
|------|----------|---------------|
| `/.well-known/agent.json` | `routes_discovery.py:well_known_agents` | A2A spec §7.4.1 |
| `/api/icoder/agents/{id}/card` | `routes_discovery.py:get_agent_card` | A2A spec §7.4.2 |
| `/api/icoder/agents` | `routes_discovery.py:list_agents` | A2A spec §7.4.3 |
| `/llms.txt` | `routes_discovery.py:llms_txt` | A2A spec §7.4.4 |

**关键**: 本 spec 只实现 handler, 路由挂载 + URL 路径与 A2A spec 完全一致 (避免 spec 间不一致)

---

## 8. RBAC (Phase 1 简化)

### 8.1 Phase 1 RBAC 行为

| 角色 | 可查 | 可注册/注销 |
|------|------|-------------|
| admin | ✅ 全部 | ✅ (Phase 4) |
| coder | ✅ 全部 | ❌ |
| medical_insurance_reviewer | ✅ 全部 | ❌ |
| it_operator | ✅ 全部 | ❌ |
| auditor | ✅ 全部 | ❌ |

**Phase 1 默认**: 5 角色都可查所有 Agent; 不可注册/注销 (Phase 4)

### 8.2 Phase 4 RBAC 行为

- 角色 + Agent 级别细粒度权限 (e.g., auditor 只可查 compliance 标签的 Agent)
- ISV 注册必 admin 角色
- Agent Card 字段按角色脱敏 (e.g., auditor 看不到 internal metadata)

---

## 9. 测试要求

### 9.1 单元测试 (≥30 cases)

**文件**: `backend/tests/unit/icoder/agent_card/test_registry.py` + `test_generator.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **AgentDefinition** | 必填字段 / 默认值 / 解析 AgentPackageV1 | 4 |
| **ExpertCard (Q7 落地)** | 5 件套配置 (system_prompt/tools/model/non_goals/output_contract) 各 1 test | 5 |
| **Registry 内存实现** | register / unregister / get / list / find_by_capability | 8 |
| **Registry 错误路径** | 重复注册 / 不存在 / 类型错 | 3 |
| **generate_agent_card** | 必填字段 / metadata.icoder.* 正确 | 4 |
| **Skills 生成** | 从 output_contract 推导 skills[] | 3 |
| **iCoDer metadata** | production_writeback_blocked=true 强制 + rule_sets + non_goals 正确 | 3 |

**总计**: 30 单元测试

### 9.2 集成测试 (≥12 cases)

**文件**: `backend/tests/integration/icoder/agent_card/test_discovery_endpoints.py`

| 测试组 | 覆盖 | 数量 |
|--------|------|------|
| **`/.well-known/agent.json`** | 返回 Agent 列表, Phase 1 含 1 个 | 1 |
| **`/api/icoder/agents/{id}/card`** | 单 Agent 完整 Card, metadata.icoder 正确 | 1 |
| **`/api/icoder/agents`** | 全列表 / capability 过滤 | 2 |
| **`/llms.txt`** | Markdown 格式, LLM 可读 | 1 |
| **404 路径** | agent_id 不存在 = 404 | 1 |
| **缓存** | (Phase 1 不实现, Phase 5 留) | 0 |
| **Registry 启动加载** | 启动时扫描 + 加载 1 个 builtin Agent | 1 |
| **ISV 注册 stub** | POST /registry/agents = 501 UNSUPPORTED_OPERATION | 1 |
| **RBAC** | 5 角色都可查 (Phase 1 简化) | 1 |
| **Agent Card 跨 A2A spec 兼容** | AgentCard 格式与 A2A spec §8 完全一致 | 1 |
| **iCoDer metadata 完整** | 必含 production_writeback_blocked + rule_sets + non_goals | 1 |
| **端点 URL 路径一致** | 4 个端点 URL 与 A2A spec §7.4 一致 | 1 |

**总计**: 12 集成测试

### 9.3 e2e 测试 (与 Discovery 端点 e2e 合并)

**文件**: `backend/tests/e2e/icoder/test_agent_card_e2e.py` (与 Orchestrator/A2A/Context/MCP e2e 共享)

| 测试 | 覆盖 |
|------|------|
| **curl 查 /.well-known/agent.json → POST /v1/message:send** | 验证: discovery → 1 Agent → 真实 DeepSeek 端到端跑通 |

**总计**: 1 e2e (与前面 4 spec 共享)

### 9.4 测试矩阵汇总

| 层级 | 数量 | Phase 1 必需 |
|------|------|--------------|
| 单元 | 30 | ✅ |
| 集成 | 12 | ✅ |
| e2e | 1 (共享) | ✅ |
| **小计** | **43** | |

加上 Orchestrator 44 + A2A 53 + Context 46 + MCP 66 + 1227 baseline = **1479+**。

---

## 10. 与 RFC 映射 (验收对齐)

| RFC 章节 | 本 spec 章节 | 验证方式 |
|----------|--------------|----------|
| 3.2.9 Expert Registry 目标形态 | §4 | 单元测试 30 + 集成测试 12 |
| 3.2.10 Agent Card 目标形态 | §3.4 / §6 / §7 | 集成测试: 4 个 Discovery 端点 |
| 5 节映射表 Registry / Agent Card 行 | 全部 | 全覆盖 |
| 6 Phase 4 第三方 ISV Expert 注册 | §5.2 (stub) | 集成测试: 501 UNSUPPORTED_OPERATION |
| 9.2 W5 (Expert metadata 公开) | §3.3 (Q7 5 件套) | 单元测试: ExpertCard 字段完整 |
| 10.1 Phase 1 成功标准 | §9.4 | 1479+ tests 全绿 |
| 10.2 v1 完成时 | (Phase 4 才完整) | ISV 注册 + RBAC + 缓存 |

---

## 11. 实现路径 (Phase 1 落地)

### 11.1 文件结构 (新增)

```
backend/app/icoder/agent_runtime/agent_card/
├── __init__.py
├── agent_definition.py         # AgentDefinition 数据类
├── expert_card.py              # ExpertCard 数据类 (Q7 5 件套)
├── agent_card.py               # AgentCard (复用 A2A spec §8 数据类)
├── registry.py                 # AgentRegistry 内存实现
├── builtin_loader.py           # 启动时扫描 + 加载 builtin Agent
├── generator.py                # generate_agent_card() 从 AgentDefinition 生成
├── icoder_metadata.py          # iCoDer metadata 字段 (rule_sets / non_goals / experts / production_writeback_blocked)
├── routes_discovery.py         # 4 个 Discovery 端点 (与 A2A spec §7.4 对齐)
├── routes_registry.py          # 注册/注销 API (Phase 1 ISV stub)
├── rbac.py                     # RBAC 简化版 (5 角色可查)
└── migrations/                 # Phase 4 DB 迁移留 (Phase 1 不实现)

backend/app/icoder/agent_runtime/
├── __init__.py
├── agent_card_routes.py        # 路由总挂载
└── (其他 5 spec 实现: orchestrator/ a2a/ context/ mcp/ tasks/)

backend/official_agents/
├── homepage-coding-review/     # Phase 1 内置 1 个
│   ├── agent_pack.json         # AgentPackageV1 格式
│   ├── __init__.py
│   └── experts/
│       ├── coding_expert.py
│       ├── drg_expert.py
│       └── compliance_expert.py (Phase 2-3)
└── (Phase 3: 8 原子 Agent)

backend/tests/unit/icoder/agent_card/
├── test_registry.py            # 11 cases
├── test_generator.py           # 7 cases
├── test_expert_card.py         # 5 cases (Q7 5 件套)
├── test_builtin_loader.py      # 3 cases
└── test_agent_definition.py    # 4 cases
# 30 unit tests total

backend/tests/integration/icoder/agent_card/
└── test_discovery_endpoints.py  # 12 cases

backend/tests/e2e/icoder/
└── test_agent_card_e2e.py      # 1 e2e (与 Orchestrator/A2A/Context/MCP 共享)
```

### 11.2 依赖

| 依赖 | 已有? | 用途 |
|------|-------|------|
| `pydantic v2` | ✅ | 数据类 |
| `fastapi` | ✅ | Discovery 路由 |
| `AgentPackageV1` (既有) | ✅ | builtin_loader 解析 |
| M2aRecorder | ✅ | 注册/注销 stage |
| Context (Context spec) | ✅ | RBAC 按 contextId (Phase 4) |

### 11.3 实施顺序 (Phase 1 内部)

1. **AC1**: agent_definition.py + expert_card.py (数据类, Q7 5 件套, 单元测试)
2. **AC2**: agent_card.py (复用 A2A spec §8, 单元测试)
3. **AC3**: registry.py (内存实现, 单元测试 8)
4. **AC4**: icoder_metadata.py (iCoDer metadata 字段, 单元测试)
5. **AC5**: generator.py (generate_agent_card, 单元测试 7)
6. **AC6**: builtin_loader.py (启动扫描 + 加载, 单元测试 3)
7. **AC7**: routes_discovery.py (4 个 Discovery 端点, 集成测试)
8. **AC8**: routes_registry.py (ISV 注册 stub, 集成测试)
9. **AC9**: rbac.py (5 角色 RBAC, 集成测试)
10. **AC10**: 端点 URL 路径一致性验证 (集成测试)
11. **AC11**: e2e test (与 Orchestrator/A2A/Context/MCP 共享)

每个 AC = 1 个 PR, AC1-AC11 全过才进 Phase 2。

### 11.4 与既有模块的衔接 (Q5)

| 既有 | 新 |
|------|---|
| `backend/icoder_runtime/agents/registry.py` (旧 Registry) | **重做** 为新 `agent_card/registry.py`, 内部 dict → AgentDefinition, 接口兼容 |
| `backend/official_agents/*/agent_pack.json` | 沿用, builtin_loader 解析为 AgentDefinition |
| `AgentPackageV1` 校验 | 沿用, builtin_loader 复用 |
| `app.services.a2a_protocol.register_all_experts()` (旧 30 预置) | **完全删除** (Q5 决策), 改 builtin_loader 动态加载 |

---

## 12. 开放问题 (本 spec 级别)

| # | 问题 | 选项 | 倾向 |
|---|------|------|------|
| Q-AC1 | Registry 内存 vs DB 启动加载? | 倾向: Phase 1 内存 + 启动时从 `agent_pack.json` 加载; Phase 4 DB-backed | |
| Q-AC2 | Agent Card 是否缓存? | 倾向: Phase 1 不缓存 (简单), Phase 5 加 (per agent_id + version) | |
| Q-AC3 | 第三方 ISV 注册 API 端点路径? | 倾向: `POST /api/icoder/registry/agents` (RESTful) | |
| Q-AC4 | Agent Card 版本管理: semver 必填? | 倾向: 必填 semver, 不允许缺省 | |
| Q-AC5 | ExpertCard.model 默认值? | 倾向: `deepseek-v4-flash` (既有, Q9 决策) | |
| Q-AC6 | 第三方 ISV 工具白名单 (Phase 4)? | 倾向: 必在 iCoDer 工具白名单内, 不允许自造 tool | |
| Q-AC7 | RBAC 角色细粒度 (Phase 4)? | 倾向: 角色 + Agent 标签双维度 (e.g., auditor + compliance tag) | |
| Q-AC8 | Agent 热更新 (Phase 4)? | 倾向: 支持热更新 + version 递增 + 老 version 保留 (审计) | |
| Q-AC9 | Agent Card 字段按角色脱敏 (Phase 4)? | 倾向: auditor 看不到 internal metadata, 只看公开字段 | |
| Q-AC10 | e2e test 是否强制依赖 DeepSeek? | 倾向: 是 (与 Orchestrator/A2A/Context/MCP 共享 e2e) | |

---

## 13. 参考

### 13.1 战略 RFC 与上游 spec

- `E:\Corti4C\docs\ICODER_V1_AGENT_RUNTIME_ARCHITECTURE_RFC.md` (Decided 2026-06-20)
  - 第 3.2.9 节: Expert Registry
  - 第 3.2.10 节: Agent Card
  - 第 9 节: Q7 决策
- `E:\Corti4C\docs\ICODER_V1_A2A_SPEC.md` (Draft 2026-06-20)
  - 第 7.4 节: Discovery 端点 (本 spec 实现)
  - 第 8 节: Agent Card schema 协议格式 (本 spec 生成)
- `E:\Corti4C\docs\ICODER_V1_ORCHESTRATOR_SPEC.md` (Draft 2026-06-20)
  - 第 5.3 节: M2aRecorder 集成
- `E:\Corti4C\docs\ICODER_V1_CONTEXT_SPEC.md` (Draft 2026-06-20)
  - 第 6 节: 三层隔离 (RBAC 引用)
- `E:\Corti4C\docs\ICODER_V1_MCP_SPEC.md` (Draft 2026-06-20)
  - 第 8 节: 8 工具 (ExpertCard.tools 引用)

### 13.2 Corti 官方文档

- `E:\Corti4C\Corti\llms-full.txt`
  - `/agentic/architecture` - Agent 架构
  - `/agentic/experts` - Expert 抽象
  - `/agentic/faq` - Registry 行为

### 13.3 iCoDer 既有代码

- `backend/icoder_runtime/agents/registry.py` - 旧 Registry (重做)
- `backend/icoder_runtime/agents/agent_package.py` - AgentPackageV1 格式 (复用)
- `backend/app/services/a2a_protocol.py` - 旧 30 预置 Expert (Q5 完全删除)
- `backend/official_agents/*/` - builtin Agent 位置 (沿用)

### 13.4 iCoDer 战略线索

- 2026-06-20: 100% Corti 复刻 + 10 决策 (Q7: Expert 独立可共享)
- 2026-06-17: 战略转向
- 2026-06-14: 原子能力架构
- 2026-06-13: icoder-next 切片开工

---

## 14. 签字 (待审)

| 角色 | 签字 | 日期 |
|------|------|------|
| 架构组 | ___ | ___ |
| 工程 owner | ___ | ___ |
| 产品 | ___ | ___ |
| 安全/合规 | ___ | ___ |

---

**本 spec 拍板后**:
1. 起 `ICODER_V1_TASK_SPEC.md` (Phase 1 收尾, 偏小, Phase 5 完整)
2. 6 spec 全部拍板 → Phase 1 实施 (AC1-AC11, 加上 Orchestrator T1-T10 + A2A A1-A10 + Context C1-C11 + MCP M1-M15)
