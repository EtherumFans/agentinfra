# ICD 编码引擎接入：第一阶段开发拆解与实施

日期：2026-09-29—2026-09-30。基线：`origin/master` 的 `90d0093e`；开发分支：`codex/pluggable-coding-engines`。

本阶段交付可替换引擎的后端基础设施，继续强制人工审核。它不代表 CoderFlow 医学能力已上线，也不代表已有 E384 服务或已通过临床验收。实现代码位于本地工作区，尚未发布。

## 1. 开发拆解

| 工作项 | 实施位置 | 完成标准 | 优先级/依赖 |
|---|---|---|---|
| ICE-P1-001 通用运行契约、Capability Manifest | `backend/app/coding_runtime/base.py`、`engines.py` | 引擎以相同请求/结果协议注册；显式版本；拒绝重复注册和不支持的契约 | P0，无 |
| ICE-P1-002 租户绑定与统一分发 | `engines.py`、`dispatcher.py` | 认证组织决定绑定；版本不存在、能力不支持或调用失败均不得降级到另一引擎 | P0，001 |
| ICE-P1-003 兼容引擎封装 | `dispatcher.py:LegacyCodingEngine` | 现有 Fast/Deep 仅在选择 `icoder.legacy` 时实例化；凭据检查限定于兼容引擎 | P0，001 |
| ICE-P1-004 入口收拢 | `api/coding_predict.py`、`api/v2_tools_coding.py`、`api/agent_run.py`、`icoder/agent_runtime/a2a_facade.py`、`main.py` | Predict、Agent Run、A2A（含 Deep）、专用克隆共用分发器；v2 iCoDer 不直接创建 HybridCodingAdapter | P0，002、003 |
| ICE-P1-005 审计与安全标识 | `base.py`、上述响应投影、`official_agents/medical_coding/agent_pack.json` | 返回引擎 ID/版本、绑定修订、调用 ID；人工审核为 true；禁止生产回写 | P0，004 |
| ICE-P1-006 验收回归 | `tests/coding_runtime/test_engine_registry.py`、`tests/test_api/test_pluggable_coding_engine.py`及原有回归 | 替换成功、失败不回退、租户隔离、取消/超时、能力不匹配、身份透传 | P0，001–005 |

所有工作项的业务原因：让 Coding Agent 编排与医学决策实现解耦，换引擎时不再逐一修改业务入口。统一失败行为：不返回可供业务使用的编码，保留人工审核要求；已有业务历史结果不被本次失败覆盖。

## 2. 第一阶段接口边界

`CodingEngine.predict(CodingRequest) -> CodingResult` 是进程内兼容契约，`EngineManifest.contract_version=1.0`。它与完整需求里的 CaseSnapshot/CodingTaskSpec/CompiledCodingResult JSON Schema **不是同一个协议**，不宣称完成后者。

请求保留现有 text、coding_systems、run_id、tenant_id、user_id、include_evidence/include_trace。tenant_id 必须由身份认证组织产生。旧 mode 是运行模式兼容参数，不能决定或覆盖租户绑定的 engine_id/version。未知 mode 在分发器拒绝。

`CodingResult` 保留 codes 与 raw_schema。真实适配器接入时需同时提供现有 `MedicalCodingOutputSchema` 兼容投影（含角色、证据、审核信息），确保 Agent 的八字段契约仍能验证；不能把检索候选直接作为最终代码。新引擎无需伪造旧管线的检索/重排阶段。完整 MD/OD/MP/OP 编译协议在第二阶段引入。

新增结果元数据：

```json
{
  "engine": {
    "contract_version": "1.0",
    "engine_id": "icoder.legacy",
    "engine_version": "1.0.0",
    "binding_revision": "migration-default-v1",
    "invocation_id": "server-generated-uuid"
  },
  "manual_review_required": true,
  "production_writeback_blocked": true
}
```

Predict/v2 iCoDer 的 engine 为顶层字段；Agent Run/A2A 的引擎身份放在 `result.trace_refs.engine` / A2A 数据部分的 `trace_refs.engine`，纳入既有结果签名与审核存储。它是调用身份记录，不等同于完整可重放执行凭证。原始病例快照、模型/知识/政策全版本以及幂等结果存储尚未交付。

`GET /api/v1/coding/engine-capabilities` 返回当前认证组织的 manifest、绑定修订和强制审核/回写标识，不能查询其他租户或修改绑定。

现有 `/api/v1/coding/pricing` 只适用于兼容引擎；绑定其他引擎时返回 HTTP 409、`engine_pricing_not_available`，避免将 DeepSeek 的费用估算当作新引擎费用。

## 3. 配置和扩展

未设置 `ICODER_CODING_ENGINE_BINDINGS` 时使用明确的迁移默认值 `icoder.legacy@1.0.0`。此默认值只用于未绑定租户，绝不是运行失败后的回退策略。

部署配置示例（医院 ID 必须是真实 Organization ID）：

```json
{
  "legacy_default": false,
  "tenants": {
    "hospital-a": {
      "engine_id": "hospital.icd",
      "engine_version": "2026.1",
      "revision": "approved-release-001"
    }
  }
}
```

配置必须完整有效；未知字段、错误类型和空版本拒绝解析。生产采用 `legacy_default=false`，未绑定租户阻断。将配置作为发布制品的一部分，所有 worker 必须一致；变更与回滚通过重新部署完成。首版没有在线管理接口、数据库绑定表或热切换审批工作流。

启动时解析绑定配置，并验证所有绑定目标已注册；配置错误或版本未注册会使启动失败，不悄悄启用默认引擎。

受信任的适配器通过 Python 启动代码显式注册：

```python
from app.main import app

# 在进入 lifespan 前由受信任的应用装配代码安装 factory。
# create_hospital_engine(application) 由医院适配器实现，不来自请求或 Prompt。
app.state.coding_engine_factory = lambda application: (create_hospital_engine(application),)
```

lifespan 在 gateway 初始化后、接受请求前调用 factory，并通过 `configure_coding_engines` 注册。每次 lifespan 重建适配器；已初始化后禁止重复配置。兼容引擎仍注册但不作为错误回退目标。注册不执行任意字符串 import，也不从请求读取引擎 URL/密钥。引擎是受信任的服务端代码，本阶段没有为 Python 插件建立沙箱；第三方服务需通过后续审核的适配器接入。

外部真实 ICD 引擎所需地址、鉴权、超时预算、码表和版本须在接入下一阶段落实；不能用当前兼容引擎冒充已经接入的真实引擎。

## 4. 安全与降级

- 请求缺少租户、租户未绑定、绑定版本未注册：阻断，无推理调用。
- 不支持的 mode、码表系统或旧研究变体：阻断，不自动切换模式。
- Fast 30 秒、Deep 90 秒协作式超时：终止等待并返回 engine_timeout。调用方取消向上传播，不包装成成功；阻塞同步代码和底层外部进程仍需适配器自身提供取消机制。
- 插件异常：只返回稳定错误码，不返回异常中可能含患者信息的文本。
- 返回类型异常、非法置信值、伪造 run_id、mock/degraded 标记：阻断。
- 请求及结果在分发边界复制，避免共享缓存对象被平台修改后串用。
- 所有执行强制人工审核和禁止回写；本阶段未新增 HIS 客户端和写入动作。
- 旧 v2 的非 full 研究模式只由声明支持的兼容引擎处理；替换引擎不支持时返回明确错误。
- 通用 15 码表 Corti `/api/v2/tools/coding/` 是独立通用预测工具，此次没有将它改成 iCoDer 病案决策模块；后续业务若把它用于正式病案决策，必须接入同一审核安全边界。

## 5. 验收方式

隔离测试引擎不调用 LLM、GPU、检索或 HIS；分别替换默认引擎，验证不同入口确实调用它。原有兼容接口测试把 mock 下移到 Legacy provider 边界，经过真实注册/绑定/分发路径，而不是跳过分发器。

测试数据库使用独立 `data/test_engine_phase1.db` / `data/test_engine_http_phase1.db`，不使用产品数据库。回归范围包括原有编码运行时、Predict 过滤、v2 投影、Agent Run、A2A 当前契约及审计生命周期。最终测试结果见本次交付说明。

2026-09-30 验证结果：以下选定回归 **78 passed，1 warning**（46.46 秒）。警告为 `aiosqlite` 工作线程向已关闭测试事件循环回传结果，出现在 pricing 回归；未屏蔽该警告。尚未执行完整仓库回归、生产 PostgreSQL 集成测试或真实引擎临床验证。

```powershell
# 在 backend 目录执行；数据库必须使用独立测试文件。
$env:ICODER_DATABASE_URL='sqlite+aiosqlite:///./data/test_engine_phase1.db'
../.venv/Scripts/python.exe -m pytest tests/coding_runtime tests/test_api/test_coding_predict_filters.py tests/test_api/test_v2_tools_coding.py tests/unit/icoder/agent_runtime/test_medical_coding_a2a_current_contract.py tests/unit/icoder/agent_runtime/test_medical_coding_a2a_lifecycle.py tests/test_api/test_pluggable_coding_engine.py tests/test_api/test_medical_coding_a2a_owned_trace.py -q --tb=short --show-capture=no
```

Python AST/Agent Pack JSON 解析通过，`git diff --check` 无空白错误。测试中的认证组织前置数据已补齐，真实审计外键和结果签名流程保持启用。当前未进行提交、推送或部署。

## 6. 后续阶段与上线闸门

1. 接入真实引擎适配器与强类型 CaseSnapshot/Anchor/CodingTaskSpec 契约；码表版本、有效日期、独立政策和输出编译不可省略。
2. 增加持久化绑定审批、运行幂等、不可变结果、审核反馈和完整重放；当前进程内 invocation_id 不等于这些能力。
3. 接入 E384/医院引擎或 CoderFlow，做历史回放与 Shadow；完成动作 precision、harm rate、自动覆盖率—有害修改率评测后再批准自动接受。
4. 发布前确定 Agent Pack 的发布版本、部署配置和兼容矩阵；当前工作区的可选审计字段扩展需要随发布制品统一发布。
5. 首阶段不开放自动 HIS 回写，不开展未经授权的模型训练，不新增数据库、消息队列或拆分微服务。
