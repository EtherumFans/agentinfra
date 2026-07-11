# iCoDer — 医疗收入合规 AI 平台 (托管云 SaaS, Corti-style)

## 产品定位

iCoDer 是面向中国医院场景的**医疗收入合规 AI 平台**,以**托管云 SaaS** 形式交付
(Environments: EU / US / CN; 医院 = Tenant; HIS/EMR = API Client)。

前端 React SPA,后端 = 多租户 FastAPI on 托管控制面。医院 HIS/EMR 通过 API Client
(`backend-service` 服务端集成 或 `ROPC embedded` Web Component 嵌入) 接入。
**不再**支持医院内网 Docker 部署。

Runtime 是 iCoDer Server 的内核执行引擎(不是独立的便携 Runtime)。

```
医疗收入合规体系
├── 编码合规 (Medical Coding)      ← 第一个官方样板 Agent, 已完成闭环
├── 分组合规 (DRG/DIP)            ← 规则结构已预留
├── 结算合规 (Insurance Audit)    ← 规则结构已预留
├── 收费合规 (Charge Compliance)  ← 规则结构已预留
├── 病历合规 (Document Evidence)  ← 规则结构已预留
└── 审计合规 (Audit)              ← AuditLog/RunHistory 已完整
```

## 架构层次

```
第四层: Business Workbenches   app/api/*         ~190 endpoints
第三层: Official Agent Packs   official_agents/   Medical Coding (icoder/medical-coding-agent@1.0.0)
第二层: Compliance Services    compliance_services/ RuleEngine + MedicalCodingRuleSet (12 rules)
第一层: Runtime Core           icoder_runtime/   AgentRunner, LLMGateway, Registry, Observability, DataPolicy
```

## Runtime Core 职责

通用 Agent 基础设施，不包含任何医学编码领域知识：
- AgentPackageV1 — .icoder-agent 包格式与校验
- RuntimeAgentRegistry — 持久化 Agent 注册表
- AgentRunner — Agent 执行引擎
- LLMGateway — LLM Provider 路由层
- DataPolicy — 边缘 PHI 脱敏 + 区域数据驻留策略 (EU/US/CN 租户路由;原始 PHI 不进入云审计通道,仅脱敏样本用于合规审计)
- RunHistory, AuditLog, FallbackTracker, ShadowDiffService — 可观测性

## Compliance Services 职责

领域独立的合规规则验证框架：
- RuleEngine — 多 rule_set 支持 (medical_coding, drg_dip, insurance_audit, charge_compliance, document_evidence)
- MedicalCodingRuleSet — ICD-10/ICD-9-CM-3 编码规则 (R001-R010 + MC-R-M80-001)
- CodingEngineAdapter — 编码推理适配器抽象

## 关键调用链

```
Agent 开发 → pack → Marketplace publish → install → PlatformRuntime → AgentRunner
  → LLMGateway → DeepSeek V4 → Compliance RuleEngine → RepairLoop → RuntimeRunResult
```

## 部署模型

| 环境 | 方式 | 说明 |
|------|------|------|
| 本地开发 | `python -m uvicorn` + `npm run dev`, 或 `docker compose -f docker-compose.local-dev.yml up` | 前后端分离 / 全栈容器。**仅供本地开发,绝不允许部署医院或生产** |
| 托管云 SaaS | `https://{tenant_slug}.{region}.icoder.cloud` | 三层架构: Environment (EU/US/CN) → Tenant (医院) → API Client (backend-service / ROPC embedded)。详见 [docs/cloud/CLOUD_DEPLOYMENT.md](docs/cloud/CLOUD_DEPLOYMENT.md) |
| ISV 开发 | CLI: `icoder pack`, `icoder test` | Agent 打包和本地测试 |

**Runtime 不再是独立的 pip 包安装到医生电脑。** Runtime 是 iCoDer Server 的内核。

## 启动命令

```bash
# 本地开发 (唯一受测开发路径;ICODER_DEPLOYMENT_MODE=local)
docker compose -f docker-compose.local-dev.yml up -d --build
# 或
cd backend && python -m uvicorn app.main:app --port 8000
cd frontend && npm run dev  # 前端单独跑

# 托管云接入 (ICODER_DEPLOYMENT_MODE=cloud,所有 ICODER_* cloud-only vars 必填)
export ICODER_DEPLOYMENT_MODE=cloud
export ICODER_HOSTED_URL=https://api.icoder.cloud
export ICODER_ENVIRONMENT=cn
export ICODER_REGION=cn-hangzhou
export ICODER_TENANT_ID=<tenant_id>
export ICODER_API_CLIENT_ID=<client_id>
export ICODER_API_CLIENT_SECRET=<client_secret>
# LLM_API_KEY 走云 KMS 注入,不进文件

# 环境变量 (兼容)
export ICODER_EXECUTION_MODE=platform_runtime
export ICODER_ALLOW_EXTERNAL_LLM=true
```

详见 [docs/cloud/CLOUD_DEPLOYMENT.md](docs/cloud/CLOUD_DEPLOYMENT.md) §6 + [.env.cloud.example](.env.cloud.example)。

## 金标准评估

```bash
python scripts/e2e_runtime_validation.py --base-url http://localhost:8000
# 201 cases, F1 = per-case micro-F1 over primary + secondary dx,
# subdivision-tolerant (I50.900 ≡ I50.9 ≡ I50.x00).
# See tests/regression/test_f1_baseline.py for the metric.
# Headline: diagnosis_code_f1 (per-case) and diagnosis_code_f1_micro_pooled
# Repair loop: HybridCodingAdapter.infer_async, not the e2e script.
```

## MedCodER 管线 (NAACL 2025 Industry Track)

> **Phase 2-F (2026-07-02 — TD-098) 更新**: MedCodER 是 Pre-built Agent #18, 非产品本体.
> 产品主线 = Corti-style 医疗 Agent Runtime 平台 (A2A + MCP + Orchestrator + Context).
> 详见 [docs/product/PRODUCT_DIRECTION.md](docs/product/PRODUCT_DIRECTION.md) + [docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md](docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md).
> 以下技术细节仍适用于 MedCodER Agent 本身, 但不代表产品主线范围.

`HybridCodingAdapter` 新增 `mode="medcoder"`，实现 5 阶段 ICD 编码管线（参考 Baksi et al., NAACL 2025, p.449-459）：

```
EMR text
  ↓
[Stage 1: Extraction] (DeepSeek chat, 1 call)
  抽取 {disease, supporting_evidence, llm_initial_code} × N
  server-side 用 rapidfuzz.partial_ratio ≥ 0.85 snap 句子到 char span
  ↓
[Stage 2: Retrieval] (BGE-M3 + FAISS, 本地, no LLM)
  synonym expansion → embed (BAAI/bge-m3, 1024-dim) → FAISS top-20
  filter 通过 icd10cn_code_catalog (37,897 码合规兜底)
  ↓
[Stage 3: Merge]
  candidate_set = (LLM codes) ∪ (Retrieved top-20) → cap 30
  注入 coding_differentiation_kb P0/P1 hints
  ↓
[Stage 4: Re-rank] (DeepSeek, RankGPT-style, 1 call)
  对每个 disease, top-5 + per-diagnosis final_confidence
  Few-shot: cot_generation_progress_v2 中 verified 案例
  ↓
[Stage 5: Compliance + Calibration]
  MedCodERRetrievalRuleSet (catalog membership + 高 similarity)
  per-diagnosis calibration (不再 flat primary)
  ↓
MedicalCodingOutputSchema (extracted_diagnoses: list[ExtractedDiagnosis])
```

**触发**: runtime endpoint 传 `?mode=medcoder` 或 `headers["X-Coding-Mode"]=medcoder`。
**前端**: MedicalCodingPage 加 toggle "MedCodER pipeline"，启用时展示 per-disease `DiagnosisCard` (evidence chips + TopKChips + override)。

**数据资产** (`E:\iCoDerA\`, 只读):
- `icd10cn_code_catalog.json` — 37,897 码 (35,468 中文同义词 + 5,560 英文)
- `icd10cn_synonym_map.json` — 75,968 同义词 + 21 类 term_index
- `evidence_anchoring_kb.json` — 972 码 × 6,490 evidence patterns
- `coding_differentiation_kb.json` — 2,090 code-pair 决策 (P0/P1/P2)
- `gold_disease_catalog.json` — 37,897 码规范化
- `cot_generation_progress_v2.json` — 175/500 rerank CoT few-shot

**本地模型 + 索引**:
- `data/medcoder/models/` — BGE-M3 (2.3GB, sentence-transformers 首次跑自动下载)
- `data/medcoder/faiss.index` + `metadata.pkl` — 一次性构建
  ```bash
  python scripts/build_medcoder_index.py --asset-dir E:/iCoDerA/DataAsset --out data/medcoder
  ```
  Build time: ~10-15min on CPU; 索引只构建一次，运行时 lazy load。

## MedCodER 评估

```bash
# 4 个 ablation variant — 对齐论文 Fig 2
python scripts/e2e_medcoder_validation.py --cases tests/fixtures/ccl2026_val_100.json --variant full
python scripts/e2e_medcoder_validation.py --cases tests/fixtures/ccl2026_val_100.json --variant prompt
python scripts/e2e_medcoder_validation.py --cases tests/fixtures/ccl2026_val_100.json --variant retrieve
python scripts/e2e_medcoder_validation.py --cases tests/fixtures/ccl2026_val_100.json --variant prompt+retrieve
# iCoDer 201 baseline
python scripts/e2e_medcoder_validation.py --cases tests/fixtures/icoder_201.json --variant full
```

**4 个 variant**:
- `prompt` — Stage 1 only (LLM 初始编码)
- `retrieve` — Stage 2 only (BGE-M3 RAG, no LLM)
- `prompt+retrieve` — Stage 1+2 合并去重 (no re-rank)
- `full` — 5 阶段完整管线 (Stage 1+2+3+4+5)

**指标**:
- `F1@1`, `F1@2`, `F1@5` — subdivision-tolerant (I50.900 ≡ I50.9)
- per-case micro-F1 (over primary + secondary dx)
- aggregate micro-pooled (整个数据集上算)

**预期** (按论文 Fig 2): `full > prompt+retrieve > prompt ≈ retrieve > baseline`。

**评测集**:
- `tests/fixtures/ccl2026_train_gold.json` — 1800 cases (CCL 2026 train.xlsx, 公开)
- `tests/fixtures/ccl2026_val_100.json` — 100 cases random sample (seed=42), CI 用
- `tests/fixtures/icoder_201.json` — 201 cases (sample of `ccl2026_train_gold.json`, seed=42, `source: icoder_201_subset`), 回归对照. Regenerate with `python scripts/build_icoder_201_fixture.py` if the CCL train file is updated.

## 技术栈

- 后端: FastAPI + SQLAlchemy (async) + SQLite
- LLM: DeepSeek V4 (deepseek-v4-flash) via LLMGateway
- Embedding: BGE-M3 (BAAI/bge-m3) 本地 sentence-transformers, 1024-dim
- 向量索引: FAISS IndexFlatIP (cosine via inner product on normalized)
- 数据: iCoDerA 资产(只读;本地开发 / CI/eval 用 `E:\iCoDerA\`;托管云 region-shared object storage,`ICODER_ASSET_BUCKET=icoder-assets-{region}`)
- 前端: React + TypeScript + Vite + Tailwind CSS
- 测试: pytest (752 tests, 80 baseline + 672 MedCodER/规则/修复)

## 货币约定 (Phase 5 A2 — 2026-07-10)

**统一使用 CNY (人民币 ¥)**,不用 USD ($). 原因:

- iCoDer 是面向中国医院场景的平台 (CLAUDE.md §产品定位).
- DeepSeek 公开定价以 RMB 计价,LLM_PRICE_INPUT_PER_1M / LLM_PRICE_OUTPUT_PER_1M 反映 RMB 价格.
- 后端 billing endpoint 已经返回 `{"currency": "CNY"}` 且交易流水用 `¥` 前缀格式化.
- 后端 agent_run endpoint 的 `cost.currency` 字段也用 `"CNY"`.
- 前端 TopBar / BillingPage / UsagePage / MedicalCodingPage / AgentChatPage / EventInspector / i18n locales 全部统一为 `¥` 前缀.

**注意:** `run_history.cost_usd` DB 列名 (alembic 010) 保留不变 — 列名是历史遗留,实际值为 CNY. 重命名 DB 列涉及迁移风险,不在 Phase 5 范围.
