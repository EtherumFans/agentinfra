# 隔离 MedCodER Worker HTTP 接线阶段总结（2026-08-22）

本阶段关闭了“Worker 资源和客户端代码存在，但 Compose 不会把 Backend 接到 Worker、且 Backend MCP 仍可能读取本地索引降级状态”的开发环境缺口。结果是可重复的隔离检索服务合同候选，不是 Linux 原生 BGE/FAISS 质量或医院临床效果证明。

## 发现并修复的问题

- 基础 `docker-compose.local-dev.yml` 的 `medcoder-retriever` 虽可由 `ml` profile 启动，但 Backend 的 `MEDCODER_RETRIEVER_URL` 默认为空；旧文档命令因此只启动服务，不形成 API→Worker 链路。
- Backend 启动时先写入本地原生索引健康报告，再探测远端 Worker；远端探测成功只更新布尔 ready/version，没有替换 MCP `search_icd` 使用的 `app.state.medcoder_index_health`。结果是 Worker 已健康时 MCP 仍可能失败关闭或走 Windows lexical fallback，而不执行远端语义检索。
- 既有 Worker 测试使用进程内 `TestClient`，远端客户端测试使用 `MockTransport`，不能证明真实端口、Bearer header、JSON 契约、Backend lifespan 和 MCP dispatch 能跨进程协作。

## 完成内容

- 远端 Worker 配置存在时，其 readiness 成为 Backend 的权威 MedCodER 健康报告；ready/degraded、worker/index version 和远端检查进入结构化状态，异常配置继续失败关闭。
- 新增 `docker-compose.medcoder.yml` 显式 overlay：
  - Backend 固定连接 Compose 内网 `http://medcoder-retriever:8100`；
  - 只为该内网链路开启 HTTP，API 进程原生 MedCodER 强制禁用；
  - Backend 等待 Worker `/readyz` 健康；
  - Worker 与 Backend 使用同一独立服务 token；未设置 32–512 字符 token 时 Compose 配置阶段失败；
  - 选择 overlay 即显式启用 Worker，不再依赖容易漏接线的单独 profile 命令。
- 部署静态验证器新增 overlay 接线检查；发布候选 CI 增加真实 TCP 远端 Worker E2E。
- README、Cloud 部署说明和 Windows 原生安全文档更新为 overlay 命令，并明确区分合同 E2E 与真实原生质量。

## 真实 TCP 跨进程 E2E

测试在两个独立 Uvicorn 子进程上运行：

1. 启动无 Torch/FAISS/SentenceTransformers/PyArrow 的固定检索 Worker fixture；
2. 通过真实 loopback TCP 验证 `/readyz`、ICD-10-CN、ICD-9-CM-3-CN 和错误 token 401；
3. 使用隔离 SQLite、mock LLM、禁用原生 MedCodER 启动真实 Backend；
4. `/api/health` 必须报告 `remote`、ready、Worker `1.0.0` 和固定 index version；
5. 通过 Backend 的 MCP `search_icd` 调用 Worker，必须得到远端候选 `I50.900`，且不得出现 `lexical_catalog_fallback`；
6. 最终精确终止两个子进程，并确认没有残留 Uvicorn/fixture 进程。

该 E2E 使用注入的确定性检索器，验证的是进程、网络、认证、版本、编码系统、健康门与 MCP 接线。它故意不在已知不安全的 Windows Codex 宿主上导入原生 ML，因此不证明 BGE 模型加载、FAISS 召回质量、容器镜像或 Linux 性能。

## 验证结果

| 范围 | 结果 |
|---|---:|
| Worker/远端客户端/选择/配置/安全/MCP/真实 HTTP 扩大回归 | 93/93 |
| 首轮 Worker/远端/部署/TCP E2E | 24/24 |
| 静态部署候选检查 | 52/52 |
| Compose/CI YAML | 解析通过 |
| 四个索引/元数据资产 manifest 大小与 SHA-256 | 通过 |
| Agent Hub 运行矩阵 | 26/26 用户可见 Agent launch-candidate-ready |
| 隐藏 Pack 复核 | 6 个隐藏；5 个 metadata-only/stub，1 个 internal engine，均非用户入口 |
| E2E 残留进程 | 0 |
| Docker 镜像/原生 Linux Worker | 本机无 Docker，未执行 |

全部回归显式清空 `ICODER_CREDENTIAL_LLM`，设置 `LLM_PROVIDER=mock`、`ICODER_ALLOW_EXTERNAL_LLM=false`、`ICODER_DISABLE_NATIVE_MEDCODER=true`。没有调用真实 LLM，没有加载 Windows 原生 ML，也没有访问 Corti。

机器证据：[`phase_evidence.json`](../../reports/agent_hub/medcoder_remote_http_phase_20260822/phase_evidence.json)、[`deployment_preflight.json`](../../reports/agent_hub/medcoder_remote_http_phase_20260822/deployment-preflight/deployment_preflight.json)、[`agent_hub_runtime_matrix.json`](../../reports/agent_hub/medcoder_remote_http_phase_20260822/runtime-matrix/agent_hub_runtime_matrix.json)。

## 剩余门禁

- 必须在具备 Docker 的 Linux CI/开发机实际构建 API/ML 镜像，启动真实 BGE-M3 与四个索引资产，验证完整预热、双编码检索、资源上限、重启、故障注入和镜像 SBOM/漏洞。
- 需要用有标注、合法授权的中国编码数据评估真实检索 Recall@K、重复性、延迟、漂移和临床错误；固定 fixture 不能替代质量评测。
- 云/医院部署仍需要内部 TLS/mTLS 或 service mesh、KMS/Secret Manager、token 轮换、网络策略、容量、告警、SLA 和安全审计。
- 用户可见 26 Agent 的工程入口均为 launch candidate；隐藏的三个 expert-stub 不属于 Agent Hub 用户入口。若未来要公开，必须先完成真实 Provider/工具实现、合同和质量门禁，不能仅切换 `hidden_from_hub`。

下一开发优先级转为仍缺真实 adapter 的 DrugBank/POSOS/Web Search 与 semantic Memory 设计审计；Linux 原生 Worker、医院数据和质量门禁保留为外部执行项。
