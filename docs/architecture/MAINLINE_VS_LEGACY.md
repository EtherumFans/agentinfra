# MAINLINE_VS_LEGACY — 主线 vs 实验性 vs Legacy 三层分类清单

> **声明**: 本文档是 iCoDer 所有资产的**三层分类清单** (主线 / 实验性 / Legacy), 取代 Stage 1 inventory 的标签. 任何新代码/文档应明确归属三层之一.
> **日期**: 2026-07-02
> **阶段**: P1.3 Corti Parity Direction Audit 后的分类梳理 + Phase 2-A 主线确认
> **状态**: MAINLINE

> **Phase 2-A 更新 (2026-07-02)**: 唯一 Agent Runtime 主路径已确认 = `app/icoder/agent_runtime/`. `main.py` lifespan 用新 wiring (`build_expert_invoker_for_medcoder` + `build_llm_call_from_gateway`), `HybridCodingAdapter(mode="medcoder")` 用新 wiring 构造, `mount_a2a` + `mount_mcp` 已挂载, `/.well-known/agent.json` 返 200. Legacy orchestrator/AgentRunner 已 DEPRECATED 标记, Phase 2-B 断引用, 2-C 物理删.

---

## 0. 三层定义

| 层 | 定义 | 文档态度 | 代码态度 |
|---|---|---|---|
| **Mainline (主线)** | Corti-style Agent Runtime 平台的当前主线, 上线, 文档主描述 | CLAUDE.md / PRODUCT_DIRECTION 主描述 | keep_mainline, 不动 |
| **Experimental (实验性)** | 离线评估 / 研究 / 中国特定实验, 不上线但保留 | 文档明确标 "experimental, 非主线" | keep_experimental, 不在主线文档 |
| **Legacy (Deprecated)** | 被 Mainline 取代或 P1.2/P1.3 已删概念的残留, 待删 | 文档明确标 "deprecated, 待删" | deprecated, Stage 5 标记, Phase 2 删 |

---

## 1. Mainline 主线资产

### 1.1 Backend API (38 模块, 主线 22 个)

**Corti-aligned v2 tools (8 个, keep_mainline)**:
- `v2_tools_coding.py` (559) — Phase 1.1
- `v2_tools_facts.py` (619) — Phase 1.2/1.3
- `v2_tools_stt.py` (866) — Phase 1.3
- `v2_tools_streams.py` (382) — Phase 1.2 cycle 2
- `v2_tools_guided_document.py` (277) — Phase 1.2 cycle 3
- `v2_tools_sections_templates.py` (262) — Phase 1.2 cycle 4
- `v2_tools_documents_classic.py` (196) — Phase 1.2 cycle 5
- `oauth.py` (449) — Phase 1.0

**Corti-aligned business APIs (9 个, keep_mainline)**:
- `customers.py` (217) — Loop 1
- `templates.py` (195) — Loop 2
- `tickets.py` (216) — Loop 9
- `billing.py` (80) — Loop 4
- `platform_api_clients.py` (102)
- `platform_environments.py` (68)
- `platform_tenants.py` (74)
- `auth.py` (435)
- `team.py` (141)
- `organizations.py` (363) — rename candidate (organization → project, 高代价可放缓)
- `keys.py` (98)

**Runtime 主线 (1 个, keep_mainline)**:
- `runtime_platform.py` (673) — Cycle 25 加固

**其他主线 (4 个)**:
- `compliance.py` (74)
- `admin.py` (232)
- `usage.py` (97)
- `websocket.py` (521)
- `embedded.py` (95)

### 1.2 Backend Services (50+, 主线 30+ 个)

**Agentic Framework 服务 (keep_mainline, 22 个)**:
- `expert_registry.py` (173)
- `expert_runner.py` (142)
- `mcp_client.py` (176)
- `mcp_wrapper.py` (169)
- `memory_expert.py` (271)
- `phi_redactor.py` (72)
- `sse_manager.py` (105)
- `task_manager.py` (156)
- `tool_registry.py` (147)
- `agent_registry_sync_service.py` (279) — Cycle 25 加固
- `schema_drift_service.py` (239) — Cycle 25 加
- `runtime_state_sync.py` (201)
- `permissions.py` (244)
- `guardrails.py` (149)
- `contract_engine.py` (241)
- `evidence_pack.py` (221)
- `context_scoper.py` (138)
- `tenant_scoper.py` (56)
- `thread_state.py` (128)
- `token_tracker.py` (49)
- `credential_vault.py` (124)
- `circuit_breaker.py` (80)

**MedCodER / 中国编码主线 (keep_mainline, 8 个)**:
- `icd10cn_loader.py` (290)
- `icd9cm3_loader.py` (233)
- `medcoder_index_health.py` (260)
- `code_dictionary.py` (472)
- `rule_engine.py` (246)
- `llm_service.py` (265)
- `llm_adapter.py` (209)
- `llm_planner.py` (209)

**其他主线 (3 个)**:
- `punctuation_service.py` (154)
- `agent_analytics.py` (92)
- `stt_service.py` (415) — Corti STT 对齐部分

### 1.3 Backend Agent Architecture (新 Agentic Framework, keep_mainline)

- `app/icoder/agent_runtime/a2a/` (13 文件) — A2A 协议
- `app/icoder/agent_runtime/context/` (11 文件) — Context/Memory
- `app/icoder/agent_runtime/experts/` (5 文件) — 5 atomic experts
- `app/icoder/agent_runtime/orchestrator/` (13 文件) — Orchestrator
- `app/icoder/mcp/` (7 文件) — MCP server + 5 handlers

### 1.4 Backend icoder_runtime (keep_mainline 主线部分)

- `icoder_runtime/core/` (15 文件) — Pack loader + Registry + LLMGateway + DataPolicy + evidence_parser
- `icoder_runtime/constants/`
- `icoder_runtime/observability/`
- `icoder_runtime/providers/`
- `icoder_runtime/embedded/`
- `icoder_runtime/agent_pack.py` + `agent_pack_v1.py`
- `icoder_runtime/contract_engine.py` + `guardrails.py` + `permissions.py` + `tool_registry.py` (与 app/services 重复, 需 Phase 2 合并)
- `icoder_runtime/serve.py` + `cli.py` + `types.py`
- `icoder_runtime/ISV-GUIDE.md` + `pyproject.toml`
- `icoder_runtime/tests/`
- `icoder_runtime/reports/`

### 1.5 Backend compliance_services (keep_mainline + experimental)

- `rule_engine.py` — keep_mainline
- `medical_coding_rules.py` — keep_mainline
- `medcoder_retrieval_rules.py` — keep_mainline
- `drg_dip_rules.py` — keep_experimental
- `insurance_rules.py` — keep_experimental

### 1.6 Backend official_agents (16 packs)

- `medical_coding/` (5 文件) — keep_mainline
- `medcoder-coding-review/` (1 文件) — keep_mainline
- `evidence_extractor/` + `index_navigator/` + `code_reconciler/` + `tabular_validator/` (4 atomic) — keep_mainline
- 10 metadata-only packs — keep_mainline (待 Phase 3 实装)

### 1.7 Backend Models (22, 全部 keep_mainline)

- 22 models in `app/models/` — 全部 keep_mainline (organization/agent 命名 Phase 3 可改)

### 1.8 Backend Alembic (8 migrations, 全部 keep_mainline)

- `001_initial_all_tables.py` (afeb04d02665)
- `002_agent_versioning.py`
- `003_multi_tenant.py`
- `004_coding_review_run.py`
- `005_context_tables.py`
- `006_p1_2_corti_parity_and_drop_context.py`
- `007_add_missing_orm_columns.py`
- `008_coding_review_runs_not_null.py` (Cycle 25)

### 1.9 Frontend Pages (30, 主线 24 个)

**Corti-aligned 主线 (24 个, keep_mainline)**:
- `HomePage.tsx` (181) — 待 Stage 6 改 4 tabs
- `AIStudioOverviewPage.tsx` (76)
- `AgentsPage.tsx` (686)
- `AgentDetailPage.tsx` (1286)
- `NewAgentPage.tsx` (337)
- `MedicalCodingPage.tsx` (760)
- `FactExtractionPage.tsx` (468)
- `TextGenerationPage.tsx` (570)
- `SpeechToTextPage.tsx` (557)
- `EmbeddedAssistantPage.tsx` (714)
- `APIClientsPage.tsx` (205)
- `TeamPage.tsx` (211)
- `BillingPage.tsx` (383)
- `UsagePage.tsx` (244)
- `CustomersPage.tsx` (422)
- `TemplatesPage.tsx` (420)
- `SettingsPage.tsx` (513)
- `TicketsPage.tsx` (416)
- `DeveloperQuickstartPage.tsx` (331)
- `DocsPage.tsx` (153)
- `ReleaseNotesPage.tsx` (97)
- `LoginPage.tsx` (168)
- `ResetPasswordPage.tsx` (73)
- `SupportPage.tsx` (59)

### 1.10 Frontend Components (主线)

- `components/layout/Layout.tsx` + `OrgSwitcher.tsx`
- `components/common/CodeSnippet.tsx` + `ErrorBoundary.tsx` + `EventInspector.tsx` + `SettingsCodeTab.tsx` + `Toast.tsx`
- `components/medical-coding/DiagnosisCard.tsx` + `EvidenceHighlighter.tsx` + `HighlightedTextarea.tsx` + `TopKChips.tsx`
- `components/agents/ToolSelector.tsx`
- `components/A2ACollaboration.tsx` + `AddExpertModal.tsx` + `EditSystemPromptModal.tsx`
- `components/embed/IcoderEvidenceViewer.tsx` + `IcoderReviewPanel.tsx`

### 1.11 Frontend Services / Hooks / Store / Utils (主线)

- `services/api.ts` (runtimeStatusApi)
- `services/runtimeApi.ts` (runtimeAgentApi)
- `services/agentHubApi.ts` (migrate candidate Phase 2)
- `services/__tests__/apiContract.test.ts`
- `store/index.ts`
- `utils/errors.ts` (需清理 MARKETPLACE_ERROR)
- `utils/stt-punctuation.ts`
- `config.ts` + `i18n/` + `types/`

### 1.12 Documentation (主线)

- `docs/corti_parity/` (Stage 0-8 输出)
- `docs/corti-reverse-engineered/` (49 截图 + 15 feature summary + api-contracts-v2.json + docs-site)
- `docs/corti-feature-inventory.md`
- `docs/cloud/` (4 文件)
- `docs/openapi/` (openapi.json + path_whitelist + reasons)
- `docs/dev/BACKEND_RECOVERY.md`
- `docs/specs/AGENT_PACK_SPEC_V1_2.md`
- `docs/phase_cycles/` (cycle_2 → cycle_24)
- `docs/sdk/` (js.md + python.md)
- `docs/CLAUDE.md` (项目根, 待 Stage 4 后更新)
- `docs/product/PRODUCT_DIRECTION.md` (Stage 4)
- `docs/architecture/CURRENT_ARCHITECTURE.md` (Stage 4)
- `docs/architecture/MAINLINE_VS_LEGACY.md` (本文档)
- `docs/product/CORTI_PARITY_ROADMAP.md` (Stage 4)
- `docs/backlog/PRODUCT_BACKLOG.md` (Stage 4)
- `docs/backlog/TECH_DEBT_BACKLOG.md` (Stage 4)
- `docs/README_INDEX.md` (Stage 4)
- `docs/ICODER_V1_*_SPEC.md` (7 份 A2A/AGENT_CARD/AGENT_RUNTIME_ARCHITECTURE_RFC/CONTEXT/MCP/ORCHESTRATOR/TASK)
- `docs/CORTI_STYLE_*.md` (3 份 GAP_ANALYSIS/PRODUCT_MODEL/REMEDIATION_ROADMAP)
- `docs/PHASE_1_*.md` (Phase 1.0-1.3 cycle 报告, 18 份)
- `docs/PHASE_2_CYCLE*.md` (6 份)
- `docs/PRODUCT-MODULES.md` + `PRODUCT-ROADMAP.md`
- `docs/ARCHITECTURE.md` + `TECHNICAL-DESIGN.md` + `DESIGN.md`
- `docs/runtime.md` + `agent-pack.md` + `SDK-TUTORIAL.md` + `QUICKSTART.md` + `SOLUTION-SCENARIOS.md`
- `docs/operation-manual/` (22 文件)

### 1.13 Scripts (主线)

- `scripts/corti_deep_crawler.py` + `corti_docs_crawler.py` + `corti_reverse_engineer.py` + `corti_reverse_engineer_interact.py` + `corti_deep_scan.py`
- `scripts/icoder_compare.py` + `icoder_ui_diff.py`
- `scripts/chrome-connect.skill.md` + `connect-cdp.py` + `launch-chrome-debug.ps1` + `generate-certs.sh`
- `backend/scripts/health_check.py` + `check_schema_drift.py` + `export_openapi.py`
- `backend/scripts/build_medcoder_index.py`

### 1.14 Packages & SDKs (主线, 5 个)

- `packages/icoder-sdk/` (TypeScript)
- `packages/icoder-python/` (Python)
- `packages/icoder-embedded/` (Embedded assistant)
- `packages/icoder-web/` (Web components)
- `packages/web-components/`
- `packages/examples/`

### 1.15 Tests (主线)

- `tests/unit/`
- `tests/test_api/`
- `tests/test_services/`
- `tests/test_models/`
- `tests/test_compliance/`
- `tests/integration/`
- `tests/e2e/`
- `tests/e2e_product/`
- `tests/conftest.py`

### 1.16 Data (主线)

- `backend/data/icoder.db`
- `backend/data/medcoder/` (BGE-M3 + FAISS index)
- `backend/data/code_dicts/`
- `backend/data/medical_hotwords.txt`
- `backend/data/versions.json`

### 1.17 Repo-level (主线)

- `backend/` + `frontend/` + `docs/` + `scripts/` + `packages/` + `public/` + `deploy/cloud/`
- `docker-compose.local-dev.yml`
- `CLAUDE.md` (项目根, 待 Stage 4 后更新)
- `README.md` + `VERSION` + `CHANGELOG.md`
- `.env.cloud.example` (assumed)

---

## 2. Experimental 实验性资产 (不上线, 保留)

### 2.1 MedCodER 评估资产

- `backend/app/services/gold_case_importer.py` (324) + `gold_case_template.py` (231)
- `backend/app/services/inter_rater.py` (193)
- `backend/app/services/pilot_report_builder.py` (176)
- `backend/app/services/ccl2026_importer.py` (221)
- `backend/app/services/stt_finetune.py` (323)
- `backend/app/services/disagreement_analyzer.py` (319) — MedCodER Stage 4
- `backend/app/services/reasoning_report_builder.py` (302) — MedCodER CoT
- `backend/app/services/confidence_calibrator.py` (360) — MedCodER Stage 5
- `backend/app/services/evidence_ranker.py` (562) — MedCodER Stage 4 rerank
- `backend/app/services/speaker_diarizer.py` (363) — Corti Streams 也用, 部分主线

### 2.2 DRG/DIP 系列 (中国医院需要, 实验性)

- `backend/app/services/drg_kb.py` (727)
- `backend/app/services/drg_analyzer_service.py` (430)
- `backend/app/services/drg_grouper.py` (381)
- `backend/app/services/clinical_triage.py` (195) — 对应 Corti Pre-built #9
- `backend/compliance_services/drg_dip_rules.py`
- `backend/compliance_services/insurance_rules.py`
- `backend/official_agents/drg-analyzer/` (3 文件)

### 2.3 评估脚本 + fixtures

- `backend/scripts/e2e_runtime_validation.py` — F1 baseline
- `backend/scripts/e2e_medcoder_validation.py` — 4 ablation variant
- `backend/scripts/build_icoder_201_fixture.py`
- `backend/tests/regression/` (8 文件: F1/confidence/disagreement/evidence/reasoning/fallback/runtime_recovery)
- `backend/tests/fixtures/` (ccl2026_val_100 + icoder_201 + ccl2026_train_gold)
- `backend/tests/review/`

### 2.4 实验性文档

- `docs/experiments/E2_0_NEGATIVE_SIGNAL_ARCHIVE.md`
- `docs/backlog/CODING_QUALITY_BACKLOG.md`
- `docs/document-aggregation-agent-design.md`
- `docs/knowledge-base-product-design.md`
- `docs/icoder-signit-integration-blueprint.md`
- `golden_captures/`
- `reports/`
- `postman/`

---

## 3. Legacy Deprecated 资产 (待删)

### 3.1 Legacy 单体 Agent

- `app/agents/orchestrator.py` — 引用 homepage_expert, 非 A2A
- `app/agents/base.py`
- `app/agents/experts/homepage_expert.py` (664) — P1.2 应删但残留
- `app/agents/experts/diagnosis_expert.py` (267)
- `app/agents/experts/procedure_expert.py` (229)
- `app/agents/experts/timeline_expert.py` (228)
- `app/agents/experts/drg_expert.py` (205)
- `app/agents/experts/evidence_expert.py` (126)
- `app/agents/experts/audit_expert.py` (110)
- `app/agents/experts/hcc_expert.py` (85)
- `app/agents/experts/cdi_expert.py` (84)
- `app/agents/experts/denial_expert.py` (83)
- `app/agents/experts/report_expert.py` (342)

### 3.2 Legacy AgentRunner

- `app/services/agent_runner.py` (1047)
- `icoder_runtime/agent_runner.py` (重复, 1047)
- `app/services/runtime.py` (702) — 部分被 runtime_platform.py 取代, migrate

### 3.3 Legacy API 路径

- `app/api/icoder_coding_review.py` (1283) — Corti 用 /v2/tools/coding/
- `app/api/icoder_agents_hub.py` (1029) — migrate Phase 2
- `app/api/icoder_agents_compat.py` (123)
- `app/api/icoder_registry_compat.py` (106)
- `app/api/evaluation.py` (104) + `agent_evaluation.py` (152)
- `app/api/gold_cases.py` (144)
- `app/api/code_tables.py` (169)
- `app/api/m2a.py` (277)
- `app/api/reviews.py` (921) — 人工审核, Corti 用 Pre-built Agent
- `app/api/experts.py` (551) — Corti 用 Pre-built Agents + MCP
- `app/api/encounters.py` (200) — unclear, Corti 用 interaction
- `app/api/medical_docs.py` (192) — unclear
- `app/api/codes.py` (67) — unclear
- `app/api/drg.py` (148) — keep_experimental
- `app/api/fhir.py` (429) — keep_experimental
- `app/api/tools.py` (278) — unclear
- `app/api/runtime.py` (386) — migrate 合并 runtime_platform
- `app/api/text_gen.py` (131) — migrate 合并 v2_tools_guided_document
- `app/api/facts.py` (204) — migrate 合并 v2_tools_facts
- `app/api/agents.py` (736) — migrate

### 3.4 Legacy Services

- `app/services/review_coding_service.py` (326)
- `app/services/llm_planner.py` (209) — 部分主线
- `app/services/llm_adapter.py` (209) — 部分主线

### 3.5 Legacy icoder_runtime

- `icoder_runtime/dashboard.html` — delete_candidate (无 Corti 等价)
- `icoder_runtime/sandbox.py` — deprecated
- `icoder_runtime/symbolic_state.py` — deprecated
- `icoder_runtime/methods/` (空) — delete_candidate
- `icoder_runtime/m2a/` (空) — delete_candidate

### 3.6 Legacy Frontend Pages (5 个)

- `pages/EvaluationPage.tsx` (265)
- `pages/GoldCasesPage.tsx` (272)
- `pages/ExpertLibraryPage.tsx` (604)
- `pages/OrchestrationPage.tsx` (266)
- `pages/EmbedDemoCodingReviewPage.tsx` (225) + `.bak` — delete_candidate

### 3.7 Legacy Frontend Components

- `components/orchestration/AgentTraceViewer.tsx`
- `components/orchestration/AuditTrailViewer.tsx`
- `components/orchestration/EncounterSelector.tsx`
- `components/orchestration/HumanReviewGate.tsx`
- `components/orchestration/PipelineProgress.tsx`
- `components/orchestration/ReviewResults.tsx`
- `components/orchestration/RuntimeMonitor.tsx`
- `components/icoder/RunTraceTimeline.tsx` — delete_candidate
- `components/icoder/EvidenceViewer.tsx` — unclear
- `components/icoder/HighRiskCodingPointPanel.tsx` — unclear
- `components/medical-coding/MethodTraceViewer.tsx` — delete_candidate
- `components/ExpertLibraryModal.tsx`
- `components/embed/IcoderTraceViewer.tsx` — wraps RunTraceTimeline, 同命运

### 3.8 Legacy Frontend Services/Hooks

- `services/icoderCodingReviewApi.ts`
- `hooks/useReviewPipeline.ts`

### 3.9 Legacy Repo-root Extras

- `Corti/` (PDF + llms-full.txt) — archive_docs
- `corti-crawl/` — archive_docs
- `corti_contracts/` — archive_docs
- `corti_ui_contracts/` — archive_docs
- `icoder-next/` (整个子项目) — archive_docs
- `iCoDer_Medical_Coding_Agent_PRD_V1.0.md` — archive_docs
- `icoder-mockup-variant-A.html` — archive_docs
- `train(2).xlsx` — archive_docs
- `screenshots/` (早期) — archive_docs
- `docs/corti-screens/` — archive_docs

### 3.10 Legacy Historical Docs (90+ 文件)

详见 Stage 1 inventory §8.2-8.3, 全部 archive_docs 到 `docs/archive/`.

### 3.11 Legacy DB backups + 临时文件 (delete_candidate)

- `.corti-user-data/` (Chrome profile)
- `backend/data/icoder.db.bak2`
- `backend/data/icoder.db.bak20260701`
- `backend/data/icoder.db.broken-20260702`
- `backend/data/test.db`
- `.tmp_run.json` / `.tmp_agent_run.json` / `backend/.tmp_run.json`
- `frontend/src/pages/EmbedDemoCodingReviewPage.tsx.bak`

---

## 4. 三层统计

| 层 | Backend 文件 | Frontend 文件 | Docs 文件 | 总状态 |
|---|---|---|---|---|
| Mainline | ~80 | ~30 | ~70 | keep, 主线 |
| Experimental | ~15 | 0 | ~5 | keep, 不上线 |
| Legacy | ~50 | ~15 | ~90+ | deprecated / archive / delete |

---

## 5. 处理优先级

| 优先级 | 操作 | 对象 | Stage |
|---|---|---|---|
| P0 | delete_candidate | 10 项 (无引用 / 备份 / 误入仓库) | Stage 5 |
| P1 | archive_docs | 90+ 历史文档 + repo-root extras | Stage 5 |
| P2 | deprecated 标记 | Legacy 代码 + 前端 + 服务 (代码不动, 加注释 + 文档标记) | Stage 5 |
| P3 | migrate | 7 项 (legacy API 合并到 v2_tools, agent_runner → 新 orchestrator) | Phase 2 |
| P4 | keep_mainline | 全部主线 | 不动 |

---

## 6. 新代码归属规则

任何新代码 / 文档必须明确归属三层之一:
- **Mainline** — Corti-style Agent Runtime 平台主线, 直接对齐 Corti baseline
- **Experimental** — 离线评估 / 研究 / 中国特定实验, 文件头加 `# EXPERIMENTAL — 非主线, 不上线` 注释
- **Legacy** — 不允许新建 Legacy, Legacy 只能减不能增

---

## 7. 变更日志

| 日期 | 变更 | 触发 |
|---|---|---|
| 2026-07-02 | 初始版本, 三层分类清单 | P1.3 Stage 3 方向纠偏 |
