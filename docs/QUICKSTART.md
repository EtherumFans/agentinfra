# iCoDer Quickstart — 5 分钟构建第一个合规 Agent

以病案编码审核 Agent 为例，展示从安装到运行的全流程。

## 1. 启动后端

```bash
cd backend
pip install -r requirements.txt
cp .env.example .env          # 编辑 LLM API Key
python -m app.seed              # 初始化数据库 + 演示数据
uvicorn app.main:app --reload   # http://localhost:8000
```

验证：

```bash
curl http://localhost:8000/api/health
# {"status":"healthy","app":"iCoDer Clinical AI Platform","version":"1.0.0"}
```

## 2. 登录获取 Token

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

响应中包含 `access_token`，后续请求在 Header 中携带：
```
Authorization: Bearer <access_token>
```

## 3. 浏览 Agent 模板库

```bash
curl http://localhost:8000/api/agents/templates \
  -H "Authorization: Bearer $TOKEN"
```

20 个预置模板，覆盖 8 个类别：编码、医保、质控、文书、护理、急诊、药学、教育。

## 4. 克隆模板，创建你的第一个 Agent

```bash
curl -X POST http://localhost:8000/api/agents/medical-coding/clone \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"我的编码审核 Agent"}'
```

返回：
```json
{
  "id": "abc123...",
  "name": "我的编码审核 Agent",
  "category": "编码",
  "is_prebuilt": false,
  "status": "draft",
  "created_by": "56140ade8877"
}
```

**发生了什么**：系统从模板复制了 `system_prompt`、`expert_ids`、`icon`、`category`，创建了一个属于你的 Agent。`is_prebuilt=false` 意味着你可以自由编辑。

## 5. 运行 Agent — 文本输入模式

```bash
curl -X POST http://localhost:8000/api/agents/abc123/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":"患者男性，65岁。主诉胸痛3小时。心电图示ST段抬高。诊断为急性前壁心肌梗死。行冠状动脉支架植入术。"}'
```

Agent 自动编排多个 Expert 执行编码审核流程：

```
输入病历 → 证据提取 → ICD-10 诊断编码 → ICD-9-CM-3 手术编码
  → 规则校验 → 证据排名 → 置信度校准 → 报告生成
```

## 6. 查看编码审核结果

```bash
curl http://localhost:8000/api/reviews?page=1&page_size=1 \
  -H "Authorization: Bearer $TOKEN"
```

每条 Review 包含：
- **primary_diagnosis**：主诊断编码 + 证据 + 置信度
- **main_procedure**：主要手术编码 + 证据
- **evidence_ranking**：证据全景（强证据 / 弱证据 / 冲突）
- **pipeline_health**：healthy / degraded / failed
- **report_markdown**：完整审核报告

## 7. 查看审计证据链

```bash
curl http://localhost:8000/api/reviews/{review_id} \
  -H "Authorization: Bearer $TOKEN"
```

响应中的 `primary_diagnosis_reasoning` 字段包含：
- **why_selected**：为什么选择这个编码
- **why_not_selected**：未选编码及排除原因
- **rule_basis**：引用的编码规则
- **confidence_level**：high / medium / low

每一步决策都可追溯到病历原文证据。

---

## 使用 Python SDK

```python
from icoder_sdk import iCoDerClient, iCoDerConfig

client = iCoDerClient(iCoDerConfig(
    base_url="http://localhost:8000",
    access_token="<your-token>",
))

# 克隆模板
agent = client.post("/api/agents/medical-coding/clone",
    json={"name": "测试 Agent"}).json()

# 运行
result = client.post(f"/api/agents/{agent['id']}/run",
    json={"input": "患者女性，45岁。体检发现甲状腺结节。"}).json()
```

---

## 下一步

- [API 完整文档](http://localhost:8000/docs) — Swagger UI
- [SDK 场景教程](./SDK-TUTORIAL.md) — 构建自己的合规 Agent
- [产品架构](./ARCHITECTURE.md) — Runtime 设计原理
- [Roadmap](./PRODUCT-ROADMAP.md) — 平台演进计划
