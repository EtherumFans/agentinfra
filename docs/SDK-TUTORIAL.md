# iCoDer SDK 场景化教程

三篇代码跟写教程，从零构建合规 Agent。

## 前提

后端已启动（`uvicorn app.main:app --port 8000`），已执行 `python -m app.seed`。

---

## 教程一：构建编码审核 Agent

### 1. 登录获取 Token

```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

### 2. 从模板克隆 Agent

```bash
curl -X POST http://localhost:8000/api/agents/medical-coding/clone \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"骨科编码审核","description":"骨科专科编码审核 Agent"}'
```

响应中拿到 `id`，后续步骤使用。

### 3. 自定义 System Prompt

```bash
curl -X PUT http://localhost:8000/api/agents/{agent_id} \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"system_prompt": "<role>\n你是骨科专科编码审核专家。重点关注：骨质疏松性骨折编码(M80)、关节置换编码、脊柱手术编码。\n</role>\n\n<output_format>\n1. 主诊断编码 + ICD-10-CN 编码 + 证据\n2. 次要诊断 + 编码\n3. 手术编码 + ICD-9-CM-3 编码\n4. 编码依据不足的项（标记为需人工复核）\n</output_format>"}'
```

### 4. 运行 Agent

```bash
curl -X POST http://localhost:8000/api/agents/{agent_id}/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input":"患者女性，72岁。摔倒后右髋疼痛2小时。X线示右股骨颈骨折。既往骨质疏松病史5年。行右人工全髋关节置换术。"}'
```

### 5. 用 Python SDK 做同样的事

```python
from icoder_sdk import iCoDerClient, iCoDerConfig

config = iCoDerConfig(
    base_url="http://localhost:8000",
    access_token="<token>",
)
client = iCoDerClient(config)

# Clone template
agent = client.post("/api/agents/medical-coding/clone",
    json={"name": "骨科编码审核"}).json()
agent_id = agent["id"]

# Customize
client.put(f"/api/agents/{agent_id}", json={
    "system_prompt": "你是骨科专科编码审核专家...",
})

# Run
result = client.post(f"/api/agents/{agent_id}/run", json={
    "input": "患者女性，72岁。摔倒后右髋疼痛2小时..."
}).json()

print(f"主诊断: {result.get('primary_diagnosis', {}).get('code')}")
print(f"置信度: {result.get('primary_diagnosis', {}).get('confidence')}")
```

---

## 教程二：添加自定义合规 Tool

### 1. 了解 Tool 结构

每个 Tool 包含：
- `name`：工具名称
- `description`：给 LLM 的描述
- `requires`：前置条件（调用前必须满足）
- `guarantees`：后置条件（调用后必须满足）
- `params`：参数 schema

### 2. 定义"骨科内置物检查"Tool

```python
# custom_tool.py
"""
骨科内置物合规检查 Tool —— 检查手术编码是否对应了正确的内置物。
"""

TOOL_SPEC = {
    "name": "check_ortho_implant",
    "description": "检查骨科手术编码与内置物的一致性。例如：全髋置换(81.51)必须对应髋臼杯+股骨柄。",
    "category": "合规",
    "tier": "tier1",          # 确定性检查，不依赖 LLM
    "requires": "procedure_code must be a valid ICD-9-CM-3 code",
    "guarantees": "returns implant_match: true/false and missing_implants list",
    "params": {
        "procedure_code": {"type": "string", "required": True},
        "procedure_name": {"type": "string", "required": False},
    },
}


def execute(params: dict) -> dict:
    """Execute the implant check."""
    code = params["procedure_code"]
    name = params.get("procedure_name", "")

    # Orthopedic implant mapping
    IMPLANT_MAP = {
        "81.51": ["髋臼杯", "股骨柄"],
        "81.54": ["膝关节假体"],
        "81.52": ["股骨头假体"],
        "81.01": ["椎弓根螺钉", "连接棒"],
    }

    required = IMPLANT_MAP.get(code, [])
    if not required:
        return {
            "implant_match": None,
            "message": f"编码 {code} 不在内置物检查范围内",
        }

    return {
        "implant_match": True,
        "required_implants": required,
        "check": f"手术 {name or code} 需匹配内置物: {', '.join(required)}",
        "action": f"请确认病历中是否记录了以上内置物的使用",
    }


# 测试
if __name__ == "__main__":
    result = execute({"procedure_code": "81.51", "procedure_name": "全髋关节置换"})
    print(result)
    # {'implant_match': True, 'required_implants': ['髋臼杯', '股骨柄'], ...}
```

### 3. 将 Tool 注册到平台（Phase 2 待实现）

```bash
curl -X POST http://localhost:8000/api/tools \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "check_ortho_implant",
    "description": "骨科内置物合规检查",
    "category": "合规",
    "tier": "tier1",
    "requires": "procedure_code must be valid",
    "guarantees": "returns implant match status",
    "params": {"procedure_code": {"type": "string", "required": true}}
  }'
```

---

## 教程三：导出证据包

### 1. 先跑一次编码审核

```bash
REVIEW_ID=$(curl -s -X POST http://localhost:8000/api/reviews \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"encounter_id":"DEMO-001"}' \
  | python -c "import sys,json; print(json.load(sys.stdin).get('review_id',''))")
echo "Review: $REVIEW_ID"
```

### 2. 导出证据包

```bash
curl http://localhost:8000/api/reviews/$REVIEW_ID/evidence-pack \
  -H "Authorization: Bearer $TOKEN" \
  -o evidence-pack.json
```

### 3. 查看证据包结构

```bash
python -c "
import json
with open('evidence-pack.json') as f:
    pack = json.load(f)

print('=== 证据包概览 ===')
print(f'Review: {pack[\"metadata\"][\"review_id\"]}')
print(f'Agent: {pack[\"metadata\"][\"agent_version\"]}')
print(f'Model: {pack[\"metadata\"][\"model_used\"]}')
print()

print('编码决策:')
for cd in pack['code_decisions']:
    print(f'  {cd[\"type\"]}: {cd[\"code\"]} {cd[\"name\"]} (置信度: {cd[\"confidence\"]})')

print()
print(f'证据项: {len(pack[\"evidence_items\"])} 条')
print(f'Pipeline: {pack[\"pipeline_health\"][\"status\"]}')
print(f'人审状态: {pack[\"human_review\"][\"status\"]}')
print()
print(f'完整性校验: {pack[\"integrity\"][\"content_hash\"]}')
"
```

### 4. 用 Python SDK 导出

```python
resp = client.get(f"/api/reviews/{review_id}/evidence-pack")
pack = resp.json()

# 验证完整性
import hashlib, json
expected_hash = pack["integrity"]["unsigned_hash"]
# 未来对接 CA 签名后，此处验证数字签名

print(f"Evidence pack exported. Hash: {expected_hash[:20]}...")

# 保存到文件
with open(f"evidence-pack-{review_id}.json", "w") as f:
    json.dump(pack, f, ensure_ascii=False, indent=2, default=str)
```

---

## 下一步

- [Quickstart](./QUICKSTART.md) — 5 分钟快速入门
- [API 文档](http://localhost:8000/docs) — 完整 Swagger UI
- [产品架构](./ARCHITECTURE.md) — Runtime 设计原理
