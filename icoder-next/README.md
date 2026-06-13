# iCoDer-next

医疗收入合规 AI Runtime 的端到端薄竖切（vertical slice）。

把 **Corti 的开发者范式**（薄 Agent × Experts + 可嵌入 Web Component + Agent Card）
**反转**为私有化部署、并**下沉**到中国编码体系：ICD-10-CN / ICD-9-CM-3 + DRG/DIP +
医保合规 + 字符级证据回链 —— 这是 Corti 公有云策略在结构上难以触及的缺口。

本切片实现一条完整链路，且**零外部依赖**（无需 DeepSeek key、无需 BGE-M3 模型、无需 iCoDerA 资产）：

```
<icoder-embedded> 组件  →  FastAPI API  →  Runtime(薄 Agent × coding-expert 4 工具)  →  证据回链报告
```

## 它做什么

「病案首页编码审核 Agent」(`icoder/homepage-coding-review-agent@1.0.0`) 对一段病历文本运行
7 阶段管线，产出带证据、带合规门禁、带 DRG 路由的编码建议：

1. ingest — PHI 脱敏（报告只渲染去标识化文本）
2. extract — LLMGateway provider（默认确定性本地抽取；DeepSeek 为生产 seam）
3. retrieve — coding-expert.search 得候选码 + 字符级证据偏移
4. verify — verify / guidelines / alternatives
5. sequence — 拆分 codes vs candidates，选主诊断，按临床顺序排列（不重排）
6. compliance — MedicalCodingRuleSet 门禁（severity + 是否需人工复核）
7. drg — 由主诊断派生 ADRG/DRG 路由

**关键不变量**：codes（确信·可计费）与 candidates（需复核）不合并、codes 不重排；
高风险/易错码（I66.901 / J98.414 / M80.900 / 45.1600x001 / Z51.102）强制门禁 + 人工复核；
`production_writeback_blocked` 恒为 true。

## 目录

```
icoder-next/
├── backend/
│   ├── icoder/
│   │   ├── runtime/      types · gateway(LLM) · registry · runner(7 阶段)
│   │   ├── experts/      coding_expert(4 工具) · catalog(ICD-10-CN 样本) · compliance(门禁)
│   │   ├── agents/       homepage_coding_review(薄 Agent: systemPrompt + experts)
│   │   ├── report/       render(PHI-safe 证据回链 HTML)
│   │   └── api/          app · auth · routes_coding_review · routes_agentic
│   └── tests/            26 tests (expert/runtime/compliance/api)
├── frontend/
│   ├── icoder-embedded.js   无依赖 Web Component
│   ├── index.html           宿主 demo（角色切换 / 事件控制台 / 复制代码）
│   ├── llms.txt
│   └── .well-known/agent-skills/icoder-coding-review/SKILL.md
└── docs/EMBED_CONTRACT.md
```

## 运行

```bash
cd backend
python -m pytest -q                       # 26 tests, 全绿
python -m uvicorn icoder.api.app:app --port 8000
```

同一个进程同时提供 API 与可嵌入前端（院内「一台服务器」部署故事）：

- 嵌入 demo：  http://localhost:8000/
- 健康检查：  http://localhost:8000/healthz
- Agent Card：http://localhost:8000/agents/icoder/homepage-coding-review-agent/card

```bash
# 运行一次审核（demo 令牌；生产由宿主签发）
curl -s -X POST http://localhost:8000/api/coding-review/run \
  -H "Authorization: Bearer demo:coder" -H "Content-Type: application/json" \
  -d '{"text":"主要诊断：慢性心力衰竭。手术操作：胃镜检查及活检。"}'
```

## 与生产的衔接（seams）

- **抽取**：`LLMGateway.from_env` 在设置 `ICODER_CREDENTIAL_LLM` 时切到 DeepSeek provider（抽取 parse 留作生产 seam）。
- **目录**：当前为 ~15 码样本；生产绑定 37,897 码 `icd10cn_code_catalog.json`（E:\iCoDerA，只读）。
- **检索**：确定性词典扫描可替换为 BGE-M3 + FAISS（MedCodER 管线）。
