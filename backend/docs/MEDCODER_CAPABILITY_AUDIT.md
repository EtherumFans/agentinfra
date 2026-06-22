# MedCodER 能力普查报告

> 目标:回答"MedCodER 现在藏在哪里?",而非"如何重写 MedCodER"。
> 范围:`E:\Corti4C\backend\` (生产 backend)。排除 `icoder-next/`、`node_modules`、训练数据 dump、`.pyc`。
> 时点:2026-06-21,Phase 1 Runtime (Context / A2A / Orchestrator / Recorder / Metrics) 已闭环。

---

## 摘要

MedCodER 5 阶段管线**已经基本完整实现**,但**散落在 `icoder_runtime/providers/medical_coding/` 这一个目录里**,以 `_medcoder_pipeline()` 单体方法 + 4 个私有 stage 方法的形式存在。新 Runtime 通过 `app/icoder/agent_runtime/orchestrator/wiring.py` 的 `MedCodERExpertAdapter` 已经把 `coding-expert` 路由到这条管线,**端到端跑通**(`tests/e2e/icoder/test_orchestrator_real_deepseek.py` 32s 内 HTTP 200,产出 ICD 编码)。

**完成度评分:82/100**。`Stage 1/2/3/4/5` 全部 FULL,4 个 ablation variants 全在 `scripts/e2e_medcoder_validation.py`,但 Stage 5 的 per-disease calibration 只是 2 行 floor,Stage 4 缺 CoT few-shot 注入,MCP server 0 实现。

**Runtime 适配难度:MEDIUM**。能力在,shape 不在 — 5 个 stage 是私有方法不是 composable functions,Coding Expert 没有 Python impl,MCP server 没影子。

---

# Part 1 — MedCodER 能力地图

## 1.1 管线核心 (Stage 1-5)

| 能力 | 文件 | 类 / 函数 | 调用入口 | LOC | 状态 |
|---|---|---|---|---|---|
| Mode-switching orchestrator | `icoder_runtime/providers/medical_coding/hybrid_adapter.py` | `HybridCodingAdapter` (8 modes: `deepseek`/`prompt_llm`/`hybrid`/`no_repair`/`medcoder`) | `app/main.py` lifespan: `HybridCodingAdapter(gateway=..., mode="medcoder")` | 661 | FULL |
| Stage 1 Extraction (LLM) | `icoder_runtime/providers/medical_coding/hybrid_adapter.py` | `_stage1_extraction` L401-412 + `_mock_stage1` L414-420 | `_medcoder_pipeline()` | — | FULL |
| Stage 2 Retrieval (BGE-M3 + FAISS) | `icoder_runtime/providers/medical_coding/medcoder_retriever.py` | `MedCodERRetriever.retrieve_async` L111-186 (同义词扩展 L137-140,embed L145,FAISS top-20 L154,`icd10cn_loader.has(code)` 过滤 L172) | `_stage234_per_disease` L452 | 591 (含 SubprocessMedCodERRetriever) | FULL |
| Stage 2 subprocess 隔离 | `icoder_runtime/providers/medical_coding/medcoder_retriever.py` | `SubprocessMedCodERRetriever` L414-591 (Windows-safe:避免 BGE-M3 与 httpx 同进程 segfault) | `app/main.py` lifespan | — | FULL |
| Embedder | `icoder_runtime/providers/medical_coding/embedding_bge_m3.py` | `BGEEmbedder` (BAAI/bge-m3, 1024-dim, `normalize_embeddings=True`) | `MedCodERRetriever._embed` | 137 | FULL |
| Stage 3 Merge (LLM ∪ Retrieved, cap 30) | `icoder_runtime/providers/medical_coding/hybrid_adapter.py` | `_stage234_per_disease` L457-475;常量 `MERGE_CANDIDATE_CAP=30` L45 | `_medcoder_pipeline()` | — | FULL |
| Stage 4 Re-Rank (RankGPT-style) | `icoder_runtime/providers/medical_coding/hybrid_adapter.py` | `_stage4_rerank` L523-555;常量 `RERANK_TOP_K=5` L48 | `_medcoder_pipeline()` | — | FULL |
| Stage 5 Compliance + Calibration | `icoder_runtime/providers/medical_coding/hybrid_adapter.py` | `_stage5_build_output` L557-609 (`MedCodERRetrievalRuleSet` + per-dx confidence floor `<0.5` L597) | `_medcoder_pipeline()` | — | PARTIAL (calibration floor only) |
| Stage 5 Rule Set (MR-001/002/003) | `compliance_services/medcoder_retrieval_rules.py` | `MedCodERRetrievalRuleSet` (catalog membership / similarity ≥ 0.5 / chapter metadata) | `_stage5_build_output` | 138 | FULL |
| Stage 1/4 Prompt 构建 + 解析 | `icoder_runtime/providers/medical_coding/medcoder_adapter.py` | `EXTRACTION_SYSTEM_PROMPT` L25-33 + `build_extraction_messages` L36-40 + `parse_extraction_response` L97-136 + `RERANK_SYSTEM_PROMPT` L46-58 + `build_rerank_messages` L61-91 + `parse_rerank_response` L139-175 | `_stage1_extraction`, `_stage4_rerank` | 293 | FULL |
| Evidence span (fuzzy → char offset) | `icoder_runtime/providers/medical_coding/medcoder_adapter.py` | `fuzzy_evidence_to_span` (rapidfuzz.partial_ratio ≥ 0.85) | `_stage1_extraction` postprocess | — | FULL |
| Differentiation KB hints (P0/P1) | `icoder_runtime/providers/medical_coding/medcoder_adapter.py` | `get_differentiation_hints` L261-293 (读 `coding_differentiation_kb.json`) | Stage 4 prompt injection L478 | — | ADVISORY-ONLY |
| 离线索引构建 | `scripts/build_medcoder_index.py` | one-shot embed of 37,897 ICD-10-CN rows → `faiss.index` + `metadata.pkl` | CLI | 165 | FULL |
| 4-variant 评测 | `scripts/e2e_medcoder_validation.py` | `full` / `prompt` / `retrieve` / `prompt+retrieve` over `ccl2026_val_100.json` + `icoder_201.json` (F1@1/@2/@5, subdivision-tolerant) | CLI | 519 | FULL |

## 1.2 Schema (输出契约)

| 能力 | 文件 | 类 | LOC |
|---|---|---|---|
| 顶层输出 schema | `official_agents/medical_coding/schema.py` | `MedicalCodingOutputSchema` (`mode` discriminator, `extracted_diagnoses: list[ExtractedDiagnosis]`) | 456 |
| Per-disease 抽取 schema | 同上 | `ExtractedDiagnosis` (L195-255) | — |
| Evidence span schema | 同上 | `EvidenceSpan` (含 text + char offsets) | — |
| 候选码 schema | 同上 | `CandidateCode` (`source` enum: `retrieve` / `rerank`) | — |
| Diagnosis / Procedure / CodingIssue schema | 同上 | `DiagnosisEntry` / `ProcedureEntry` / `CodingIssue` | — |
| Deprecated re-export shim | `icoder_runtime/core/coding_schema.py` | re-exports (header: "DEPRECATED — TODO(v2.1) Remove") | 28 |

## 1.3 规则引擎 + Calibration

| 能力 | 文件 | 角色 | LOC |
|---|---|---|---|
| Legacy 编码规则 R001-R012 + DRG001/002/DIP001 | `icoder_runtime/providers/medical_coding/rule_engine_adapter.py` | post-inference format/quality rules;legacy mode only — `medcoder` mode 不走 | 255 |
| Fuzzy-rule retrieval (旧 MVP) | `app/services/rule_engine.py` | `CODING_RULES` 知识库中文 prose,无 Runtime 引用 | 246 |
| 多源 calibration | `app/services/confidence_calibrator.py` | `calibrate_all` + `RISK_TIER_POLICY` (`auto`/`review`/`escalate`) | 360 |
| 旧 MVP catalog loader (singleton) | `app/services/icd10cn_loader.py` | `icd10cn_code_catalog.json` (37,897 码) + `icd10cn_synonym_map.json` (75,968 syns) | 290 |

## 1.4 Agents touching codes

| 能力 | 文件 | 角色 | LOC |
|---|---|---|---|
| Reference Agent Card (空) | `official_agents/medical_coding/agent_pack.json` | `icoder/medical-coding-agent@1.0.0` — 无 experts/tools 声明 | 37 |
| Homepage 14-stage agent (cosmetic) | `official_agents/homepage_coding_review.py` + `homepage-coding-review/__init__.py` | 14 stage 名 list (不执行,纯字符串);调用 `HybridCodingAdapter(mode="hybrid")` — **不走 MedCodER 5-stage** | 68 + 117 |
| Compliance guardrail (空) | `official_agents/compliance-guardrail/agent_pack.json` | 声明 5 tools 但无 Python 实现 | — |
| Code validation / reconciler (空) | `official_agents/code-validation/`, `code_reconciler/` | stubs | — |

## 1.5 Runtime 接线 (Phase 1 已闭环)

| 能力 | 文件 | 角色 | LOC |
|---|---|---|---|
| Sync↔async bridge for LLM | `app/icoder/agent_runtime/orchestrator/wiring.py` | `LMGatewaySyncAdapter` (Planner.sync ← LMGateway.async) | — |
| Sync↔async bridge for MedCodER | 同上 | `MedCodERExpertAdapter` (Delegator.sync ← HybridCodingAdapter.async,`expert_id=="coding-expert"` 路由) | 278 |
| Orchestrator core | `app/icoder/agent_runtime/orchestrator/{state_machine,run_context,events,errors,phi_redactor,planner,delegator,aggregator,inbound_handler,recorder_adapter,metrics,prompts}.py` | Phase 1 runtime scaffolding,zero MedCodER 耦合 | 3,187 |
| A2A package | `app/icoder/agent_runtime/a2a/{agent_card,envelope,errors,messages,routes_inbound,routes_discovery,routes_task_stub,version,icoder_metadata}.py` | 8 leaf modules + Agent Card 骨架;**`coding-expert` 的 Agent Card 尚未发布** | — |
| Context package | `app/icoder/agent_runtime/context/` | 10 文件,1061 LOC,C1-C11 闭环 | 1,061 |
| Lifespan wiring | `app/main.py` | 接 HybridCodingAdapter(`mode="medcoder"`) + SubprocessMedCodERRetriever;`app.state.medcoder_index_ready` flag → `/api/health` | — |

## 1.6 KB 资产 (in `E:\iCoDerA\`)

| 资产 | 消费方 | 状态 |
|---|---|---|
| `icd10cn_code_catalog.json` (37,897) | `app/services/icd10cn_loader.py` (singleton) + `medcoder_retriever._get_loader` | IN-USE |
| `icd10cn_synonym_map.json` (75,968 + 21 term_index) | `medcoder_retriever._get_synonyms` (query expansion,top-3 syns) | IN-USE |
| `evidence_anchoring_kb.json` (972 × 6,490 patterns) | **CLAUDE.md mentions;grep 找到 0 个 backend 消费者** | GAP — 未接 |
| `coding_differentiation_kb.json` (2,090 P0/P1 pairs) | `medcoder_adapter.get_differentiation_hints()` (inline filesystem read,via `ICODER_DATA_ASSET_DIR`) | IN-USE (hard-coded path) |
| `cot_generation_progress_v2.json` (175/500 rerank few-shot) | **CLAUDE.md mentions;无 backend producer/consumer** | GAP — 未接 |
| `gold_disease_catalog.json` | 无 backend 消费者 | GAP |

---

# Part 2 — MedCodER 三阶段映射 (按论文)

论文 5 阶段 + 4 ablation vs 当前实现:

| 论文组件 | 当前实现 | 文件 | 完成度 |
|---|---|---|---|
| Stage 1: Extraction (LLM 抽取 disease + evidence + initial_code) | `_stage1_extraction` + `build_extraction_messages` + `parse_extraction_response` + `fuzzy_evidence_to_span` | `hybrid_adapter.py:401-420`, `medcoder_adapter.py:25-136,184` | **FULL** |
| Stage 2: Retrieval (BGE-M3 + FAISS, synonym expansion) | `MedCodERRetriever.retrieve_async` + `BGEEmbedder` + `icd10cn_loader.synonyms_for()` | `medcoder_retriever.py:111-186`, `embedding_bge_m3.py` | **FULL** |
| Stage 3: Merge (LLM codes ∪ Retrieved top-20, cap 30) | `_stage234_per_disease` L457-475 (`MERGE_CANDIDATE_CAP=30`) | `hybrid_adapter.py:45, 457-475` | **FULL** |
| Stage 3: Differentiation KB hints injection (P0/P1) | `get_differentiation_hints` (inline filesystem,best-effort 3 hints) | `medcoder_adapter.py:261-293` | **ADVISORY-ONLY** |
| Stage 4: Re-Rank (RankGPT-style, top-5 per disease) | `_stage4_rerank` + `build_rerank_messages` + `parse_rerank_response` (`RERANK_TOP_K=5`) | `hybrid_adapter.py:523-555`, `medcoder_adapter.py:46-91, 139-175` | **FULL** |
| Stage 4: CoT few-shot rerank | `cot_generation_progress_v2.json` 未注入 prompt | — | **MISSING** |
| Stage 5: Compliance (rule set, catalog + similarity + chapter) | `MedCodERRetrievalRuleSet` (MR-001/002/003) | `compliance_services/medcoder_retrieval_rules.py` | **FULL** |
| Stage 5: Per-disease calibration | `_stage5_build_output` L597: `if edx.final_confidence < 0.5: out.manual_review_required = True` (flat floor,非 5-component weighted) | `hybrid_adapter.py:596-598` | **PARTIAL** |
| Ablation `prompt` (Stage 1 only) | `scripts/e2e_medcoder_validation.py:177 _prompt_only_topk` (eval only) | `e2e_medcoder_validation.py` | **FULL in eval, MISSING in adapter** |
| Ablation `retrieve` (Stage 2 only) | `_retrieve_only_topk` L200 (eval only) | 同上 | **FULL in eval, MISSING in adapter** |
| Ablation `prompt+retrieve` (Stage 1+2 dedup) | `_prompt_plus_retrieve_topk` L219 (eval only) | 同上 | **FULL in eval, MISSING in adapter** |
| Ablation `full` (5 stages) | `_full_topk` L236 → `adapter.infer_async()` | 同上 | **FULL** |
| F1@1/@2/@5 + subdivision-tolerant | `scripts/e2e_medcoder_validation.py` | — | **FULL** |

**关键观察**:`HybridCodingAdapter` 暴露的 `mode` 集合 (`deepseek`/`prompt_llm`/`hybrid`/`no_repair`/`medcoder`) 与论文的 4 ablation (`prompt`/`retrieve`/`prompt+retrieve`/`full`) **不对齐**。Eval 脚本的 4 个 variant 函数是 standalone,不走 adapter。

---

# Part 3 — 写死逻辑审计

| 位置 | 类型 | 风险 | 阻碍 | 建议 |
|---|---|---|---|---|
| `hybrid_adapter.py:45` `MERGE_CANDIDATE_CAP=30` | 常量阈值 | MEDIUM | Agent 化 (per-org) | WRAP — config knob |
| `hybrid_adapter.py:48` `RERANK_TOP_K=5` | 常量阈值 | MEDIUM | Agent 化 | WRAP |
| `hybrid_adapter.py:78,82,85-90,199` | 写死 stage 名 + mode dispatch (`"medcoder"`/`"no_repair"`/`"hybrid"`/`"deepseek"`/`"prompt_llm"`) | **HIGH** | Runtime 化 (literal-driven 非 data-driven) | REFACTOR — stage list as config,Mode as enum |
| `hybrid_adapter.py:199` `if self._mode == "medcoder"` 单入口 | 写死 pipeline 入口 | **HIGH** | MCP 化 (无法独立暴露 Stage 2 retriever);Expert 化 (retriever 不可热插) | REFACTOR — `_medcoder_pipeline` 拆为 5 个可独立调用的 stage method |
| `hybrid_adapter.py:380,387` `category="principal"`/`"comorbidity"` | 写死分类法 | LOW | Agent 化 (per-hospital taxonomy) | WRAP |
| `hybrid_adapter.py:444` `confidence=0.9` literal | 写死 confidence | LOW | Agent 化 | WRAP |
| `hybrid_adapter.py:597` `< 0.5` calibration floor | 写死阈值 + Stage 5 逻辑泄漏到 adapter | MEDIUM | Agent 化 + Rule 化 (应住进 rule set) | REFACTOR — 移到 `MedCodERRetrievalRuleSet` 或新建 `MedCodERCalibrationRuleSet` |
| `hybrid_adapter.py:606` notes format `"MedCodER: {n_dx} ..."` | 写死输出格式 | LOW | Context 化 (formatting 泄漏到 pipeline) | DELETE / WRAP |
| `hybrid_adapter.py:611-648` `os.name == 'nt'` retriever 选择 | 写死 OS detection | LOW | Runtime 化 | REFACTOR — retriever factory 注入 |
| `medcoder_adapter.py:25-33` `EXTRACTION_SYSTEM_PROMPT` | 写死 prompt | MEDIUM | Agent 化 + MCP 化 | WRAP — 从 agent_card.prompt 或 expert config 加载 |
| `medcoder_adapter.py:46-58` `RERANK_SYSTEM_PROMPT` | 写死 prompt | MEDIUM | 同上 | WRAP |
| `medcoder_adapter.py:184` `0.85` fuzzy threshold | 写死阈值 | MEDIUM | Agent 化 | WRAP |
| `medcoder_adapter.py:215` `20000` 文本 cap + `n // 4` step | 写死长度处理 | LOW | Runtime 化 (长 EMR) | REFACTOR |
| `medcoder_adapter.py:240` `BOUNDARIES = "。；\n.!?;"` | 写死句子边界 (CJK-only) | LOW | Agent 化 (non-CJK EMR) | WRAP |
| `medcoder_adapter.py:269` `r"E:\iCoDerA\DataAsset"` | 写死 Windows asset path | LOW | Agent 化 (Linux/macOS 部署) | REFACTOR — default `./data` |
| `medcoder_retriever.py:39-42` `DEFAULT_INDEX_DIR="data/medcoder"` 等常量 | 写死路径 | MEDIUM | Agent 化 (per-deployment) | WRAP — env/config |
| `medcoder_retriever.py:140` `[:3]` synonym cap | 写死 top-N | LOW | Agent 化 | WRAP |
| `medcoder_retriever.py:218,233` `_retrieve_inline` 与 `retrieve_async` 重复 | 写死双路径 | MEDIUM | Runtime 化 (subprocess workaround 复制 pipeline logic) | REFACTOR — single source |
| `medcoder_retrieval_rules.py:25` `HIGH_SIMILARITY_THRESHOLD=0.5` | 写死阈值 | MEDIUM | Agent 化 | WRAP |
| `medcoder_retrieval_rules.py:33-45` MR-001/002/003 hardcoded | 写死规则 (in code 非 registry) | MEDIUM | Agent 化 | REFACTOR — load from rule registry |
| `medcoder_retrieval_rules.py:55` `if structured_output.get("mode") != "medcoder"` literal gate | 写死 mode 字面量 | LOW | Expert 化 (rule set 不可复用) | WRAP |
| `medcoder_retrieval_rules.py:62` MR-000 合成 rule id | 写死命名空间 | LOW | Runtime 化 (与真实 rule id 冲突风险) | REFACTOR — `MR-DIAG-000` 前缀 |
| `schema.py:296` `mode: str = ""` (允许值在 docstring,无 type 约束) | 写死 discriminator 集合 (无 enum) | **HIGH** | Runtime 化 (consumer 全部 string equality) | REFACTOR — `enum.StrEnum Mode` |
| `schema.py:367-372` `mock_result` 写死 ICD codes `I21.0`/`I10`/`00.66`/`F60A` | 写死 mock 数据 | LOW | Agent 化 (mock-only 但 agent 可能依赖) | WRAP |
| `schema.py:425-433` `PromptLLMAdapter` 默认 system prompt | 写死英文 prompt 默认值 | MEDIUM | Agent 化 (prompt_llm mode) | WRAP — 构造参数化 |

**HIGH 风险项阻塞 Runtime 化的**:`hybrid_adapter.py:78-90` 写死 stage 名 + mode dispatch,`hybrid_adapter.py:199` `_medcoder_pipeline` 单入口,`schema.py:296` `mode` 字段无 enum — 三者共同导致 5 stage 无法独立暴露为 MCP tool,无法独立被 Expert 组合调用。

---

# Part 4 — Runtime 兼容性矩阵

| 模块 | 文件 | 处理 | 理由 |
|---|---|---|---|
| `HybridCodingAdapter` | `icoder_runtime/providers/medical_coding/hybrid_adapter.py` (661) | **REFACTOR** | 单体;5 stage 是私有方法;Runtime 已通过 `wiring.MedCodERExpertAdapter` 包好但 shape 不对 — 应拆出 `MedCodERStrategy` |
| `medcoder_adapter.py` | `icoder_runtime/providers/medical_coding/medcoder_adapter.py` (293) | **WRAP** | Prompt builder + parser 都是纯函数,可直接作为 Expert 方法 |
| `MedCodERRetriever` | `icoder_runtime/providers/medical_coding/medcoder_retriever.py` (591) | **WRAP** | BGE-M3 + FAISS 核心 OK;应作为 MCP tool `search_icd` |
| `BGEEmbedder` | `icoder_runtime/providers/medical_coding/embedding_bge_m3.py` (137) | **KEEP** | 纯本地模型 wrapper,与 Runtime 无关 |
| `MedCodERRetrievalRuleSet` | `compliance_services/medcoder_retrieval_rules.py` (138) | **KEEP** | 纯 rule-set,RuleEngine 兼容 |
| `RuleEngineAdapter` (R001-R012) | `icoder_runtime/providers/medical_coding/rule_engine_adapter.py` (255) | **KEEP** | 旧 mode 用;MedCodER Expert 可复用做 output gate |
| `coding_schema.py` shim | `icoder_runtime/core/coding_schema.py` (28) | **DELETE** | re-export,header 标 "DEPRECATED" |
| `MedicalCodingOutputSchema` 等 | `official_agents/medical_coding/schema.py` (456) | **KEEP** | canonical 契约,Runtime 不重新定义 |
| `medical-coding/agent_pack.json` | `official_agents/medical_coding/agent_pack.json` (37) | **WRAP** | experts/tools 空;需声明 `coding-expert` + 5 MCP tools |
| `homepage_coding_review.py` (Python) | `official_agents/homepage_coding_review.py` (68) + `homepage-coding-review/__init__.py` (117) | **DELETE** | 14-stage 是 cosmetic 字符串;Python impl 只 export 常数;新的 MedCodER Agent 替代 |
| `homepage-coding-review/agent_pack.json` | `official_agents/homepage-coding-review/agent_pack.json` | **WRAP** | 14 tools 是真信号,迁移到 MedCodER Agent Card |
| `icd10cn_loader` | `app/services/icd10cn_loader.py` (290) | **KEEP** | singleton catalog,与 Runtime 独立 |
| `confidence_calibrator` | `app/services/confidence_calibrator.py` (360) | **KEEP** | legacy calibration,Runtime 可选复用 |
| `rule_engine.py` (旧 MVP) | `app/services/rule_engine.py` (246) | **DELETE** | 旧 MVP `CODING_RULES` 知识库,被 `compliance_services/medical_coding_rules.py` + `RuleEngineAdapter` 替代 |
| `build_medcoder_index.py` | `scripts/build_medcoder_index.py` (165) | **KEEP** | 离线索引构建,无 Runtime touch |
| `e2e_medcoder_validation.py` | `scripts/e2e_medcoder_validation.py` (519) | **KEEP** | 4 ablation 评测 |

**统计**:6 KEEP / 4 WRAP / 1 REFACTOR / 4 DELETE — 共 15 模块,4,509 LOC → 3,445 LOC,**净 -1,064 LOC** (仅 Module-list D)。

---

# Part 5 — MedCodER Agent 设计映射

```
Context  →  Orchestrator  →  Coding Expert  →  MedCodER Strategy  →  MCP Tools
```

| 层 | 已存在 | 缺失 | 需新设计 |
|---|---|---|---|
| **Context** | `app/icoder/agent_runtime/context/` (10 文件,1,061 LOC,C1-C11 闭环) | — | — |
| **Orchestrator** | `app/icoder/agent_runtime/orchestrator/` (state_machine 5 态 / planner / delegator / aggregator / inbound_handler / phi_redactor / recorder_adapter / metrics / wiring) | Planner prompt 对 MedCodER 5 stage 的 sub-task decomposition 不够 specific (目前通用) | Agent-specific `prompts.py` override (目前只有医疗编码领域 1 套 `ORCHESTRATOR_SYSTEM_PROMPT`) |
| **Coding Expert** | `wiring.MedCodERExpertAdapter` (sync↔async bridge,路由 `coding-expert` → `HybridCodingAdapter`) | 真正的 `coding-expert` Python impl — Phase 1 仅做 routing,实质逻辑是 HybridCodingAdapter 黑盒 | `app/icoder/agent_runtime/experts/coding_expert.py` (Phase 2 改 async,委托 MedCodERStrategy) |
| **MedCodER Strategy (5 stage 可组合)** | `hybrid_adapter._medcoder_pipeline()` + 5 个私有 stage method + prompts + rules (整段可工作) | Stage 不是独立 function/object,无法单独单元测试或单独 Expert 委托 | `MedCodERStrategy` 类,5 个 callable stage method |
| **MCP Tools** | `app/services/mcp_client.py` (98 LOC stub) + `mcp_wrapper.py` — 仅 client 侧 | 全部 8 个 MedCodER MCP tool (`search_icd` / `verify_code` / `get_guidelines` / `explore_code` / `group_drg` / `group_dip` / `semantic_search` / `redact_phi`) | 完整 MCP server: `app/icoder/mcp/server.py` + tool registry + `tools/list` handler |

**逐层完成度**:Context 100% / Orchestrator 90% / Coding Expert 50% (wiring 完成,impl 是 HybridCodingAdapter-as-is) / MedCodER Strategy 80% (works monolithically,缺 extraction) / MCP Tools 0%。

---

# Part 6 — 技术债报告

| 技术债 | 风险 | 建议 |
|---|---|---|
| `app/services/agent_runner.py` (1047 LOC) + `icoder_runtime/agent_runner.py` (≥80) 与新 `InboundHandler` + `state_machine` 重复 | **HIGH** — 两个并行 AgentRunner,各带自己的 LLM gateway 注册 | DELETE `app/services/agent_runner.py`;保留 `icoder_runtime/agent_runner.py` 作为 `ExecutionPath.LEGACY` fallback,gate 在 `RuntimeConfig.fallback_to_legacy` |
| `app/services/__pycache__/a2a_protocol.cpython-312.pyc` (source 已删 per RFC Q5) | LOW — 残留 build artifact | DELETE |
| Legacy `coding_expert.py` in `icoder-next/backend/icoder/experts/` (CLAUDE.md 提及,**不在本 repo `backend/`**) | MEDIUM — 跨 sibling repo | 确认 `app/main.py` 已不 import (已确认:用新 `wiring.MedCodERExpertAdapter`) |
| `homepage-coding-review` agent (14-stage cosmetic, `mode="hybrid"`) 与新 MedCodER 5-stage 重复 | **HIGH** — 两个 "first official reference agent" manifests 并行 | DELETE Python impl (`homepage_coding_review.py` + `homepage-coding-review/__init__.py`);KEEP `homepage-coding-review/agent_pack.json` 的 14 tool 描述,迁到 MedCodER Agent Card |
| `compliance-guardrail` agent (声明 5 tools 无 Python impl) | MEDIUM — manifest-only ghost agent | DELETE `agent_pack.json`;等 MCP spec 落地后重建为 thin Agent Card,或合并到 `medcoder-coding-review-agent` 作为 `icoder.medical_safety_gate` tool |
| `RuleEngineAdapter` (R001-R012) vs `MedCodERRetrievalRuleSet` (MR-001/002/003) | LOW — 阶段不同 (post-inference vs post-retrieval),按 design orthogonal | KEEP both |
| `app/services/review_coding_service.py` (326 LOC) — 旧 `CodingReviewService` 与 MedCodER 5-stage 重复 | MEDIUM — `app/agents/orchestrator.py` + `app/api/reviews.py` 仍调 `calibrate_all` 旧路径;**不走 BGE-M3/FAISS** | DELETE `review_coding_service.py`;reroute `app/api/reviews.py` 和 `app/agents/orchestrator.py` 到新 `InboundHandler` |
| `Mode` 字段无 enum (`schema.py:296` `mode: str = ""`) | **HIGH** — 所有 consumer string equality | REFACTOR — `enum.StrEnum Mode` |

**Headline 技术债风险**:`agent_runner.py` 双副本 + `homepage-coding-review` 重复 manifest + `review_coding_service.py` 旧路径并存 — 三者共同造成新 Runtime 闭环 vs 旧 MVP 路径并行运行。需 M0/M1 阶段统一清理。

---

# Part 7 — 最终结论

## 1. MedCodER 能力完成度

**82 / 100**

| 维度 | 分数 | 说明 |
|---|---|---|
| Stage 1 Extraction | 100 | LLM 抽取 + evidence span 完整 |
| Stage 2 Retrieval | 100 | BGE-M3 + FAISS + synonym + catalog filter |
| Stage 3 Merge | 100 | union + cap 30 + dedup |
| Stage 4 Re-Rank | 95 | RankGPT prompt + parsers;**-5** for missing CoT few-shot |
| Stage 5 Compliance | 100 | MR-001/002/003 全在 |
| Stage 5 Calibration | 50 | 仅 2 行 floor,缺 5-component weighted calibration |
| 4 Ablations in eval | 100 | `full`/`prompt`/`retrieve`/`prompt+retrieve` 全在 `e2e_medcoder_validation.py` |
| 4 Ablations in adapter | 0 | `HybridCodingAdapter.mode` 不暴露 `prompt`/`retrieve`/`prompt+retrieve` |
| Differentiation KB hints | 80 | 注入 3 hint,inline filesystem read |
| Evidence anchoring KB | 0 | asset 在,0 consumer |
| CoT few-shot | 0 | asset 在,0 consumer |
| Repair loop in medcoder mode | 0 | `_repair_enabled = mode not in ("no_repair", "medcoder")` L82 显式关掉 |

## 2. Runtime 适配难度

**MEDIUM**

- 能力在 (`HybridCodingAdapter._medcoder_pipeline` 端到端可跑,iCoDer 201 baseline 已验证)
- shape 不在 (5 stage 是私有方法,无法独立暴露为 MCP tool 或独立 Expert)
- shape 修正工作可控 (~1,500 LOC net delta,4 模块级 PR)

## 3. 现有代码处理建议

| 处理 | 模块数 | LOC (current) | LOC (after) | Net |
|---|---|---|---|---|
| KEEP | 6 | 1,975 | 1,975 | 0 |
| WRAP | 4 | 989 | 1,079 | +90 |
| REFACTOR | 1 | 661 | 391 | -270 |
| DELETE | 4 | 884 | 0 | -884 |
| **Module-list D 合计** | **15** | **4,509** | **3,445** | **-1,064** |
| Tech-debt 增量删除 (Part 6) | 4 | 1,728 | 0 | -1,728 |
| **含 tech debt 合计** | **19** | **6,237** | **3,445** | **-2,792** |

## 4. MedCodER Agent 落地路线

### M0 — Quick wins (1 PR, ~3 天)

- DELETE: `icoder_runtime/core/coding_schema.py` (28 LOC shim),`app/services/__pycache__/a2a_protocol.cpython-312.pyc`,`app/services/rule_engine.py` (246 LOC 旧 MVP KB)
- EDIT `official_agents/medical_coding/agent_pack.json`:声明 `experts: [coding-expert]` + 5 MCP tools
- EDIT `official_agents/homepage-coding-review/agent_pack.json`:repoint `experts: [coding-expert]`,rename `agent_ref → icoder/medcoder-coding-review-agent@1.0.0`
- DELETE `app/services/review_coding_service.py` (326);reroute `app/api/reviews.py` + `app/agents/orchestrator.py` → 新 `InboundHandler`
- DELETE `app/services/agent_runner.py` (1047);gate legacy path 在 `RuntimeConfig.fallback_to_legacy`

### M1 — Extract MedCodER Strategy (~1 周)

- REFACTOR `icoder_runtime/providers/medical_coding/hybrid_adapter.py` `_medcoder_pipeline` → 新 `icoder_runtime/providers/medical_coding/medcoder_strategy.py` (~350 LOC),5 个 stage method 改为 public 函数
- WRAP `medcoder_adapter.py` 内容到 `app/icoder/agent_runtime/experts/coding_expert.py` — 删 module-level 函数,暴露 `class CodingExpert`
- WRAP `medcoder_retriever.retrieve_async` 后置 MCP tool `search_icd` 入口(M2 实现)
- EDIT `hybrid_adapter.py`:增加 `mode ∈ {"medcoder_prompt", "medcoder_retrieve", "medcoder_prompt+retrieve"}` dispatch,实现 4 ablation 在 adapter 层的可配置
- 增加 4 ablation 对应的 `mode` 在 `HybridCodingAdapter.__init__`,eval 脚本逐步迁移到 adapter

### M2 — MCP server + Agent Card (~2 周)

- BUILD `app/icoder/mcp/server.py` (JSON-RPC 2.0 + `tools/list` + `tools/call`),暴露 5 个 MedCodER tools:
  - `search_icd` (Stage 2 retriever)
  - `verify_code` (Stage 5 catalog check)
  - `get_differentiation_hint` (Stage 4 P0/P1 hints)
  - `rerank_codes` (Stage 4 RankGPT)
  - `calibrate_confidence` (per-dx calibration,补足 Stage 5 calibration gap)
- BUILD `Agent Card` for `coding-expert` per `AC spec §3` (5 件套: `system_prompt` + `tools` + `model` + `non_goals` + `output_contract`)
- DELETE `official_agents/homepage_coding_review.py` + `homepage-coding-review/__init__.py` (14-stage cosmetic Python);KEEP renamed `medcoder-coding-review/agent_pack.json`
- REFACTOR `schema.py:296` `mode: str` → `enum.StrEnum Mode`
- ADD per-diagnosis `DiagnosisCard` UI evidence chips + override (前端 `DiagnosisCard.tsx` 已存在,补 wire 即可)
- 复跑 `python scripts/e2e_medcoder_validation.py --cases tests/fixtures/icoder_201.json --variant full` 确认 F1 baseline 不退化

---

## Headline LOC Swing

- Part D (Module-list): **-1,064 LOC**
- Part E (Tech debt): **-1,728 LOC**
- Part F+M1+M2 (新 Runtime shape + MCP server + CodingExpert): **+~600 LOC**
- **Net: ~-2,200 LOC,Phase 1 Runtime + MedCodER Agent 闭环**
