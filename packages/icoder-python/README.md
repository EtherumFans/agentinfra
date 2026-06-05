# iCoDer Python SDK

面向中国医院场景的 iCoDer AI Runtime Python SDK。支持 Facts 提取、Agent 运行、Review 管理、Marketplace 浏览。

## 安装

```bash
pip install icoder-sdk
```

## 快速开始

```python
from icoder_sdk import iCoDerClient, iCoDerConfig

config = iCoDerConfig(
    base_url="http://localhost:8000",
    client_id="your-client-id",
    client_secret="your-client-secret",
)
client = iCoDerClient(config)

# 提取临床事实
result = client.facts.extract("患者腰痛4个月，MRI提示腰椎压缩骨折")
print(result.facts)

# 运行医学编码 Agent
result = client.runtime.run_agent("icoder/medical-coding-agent@1.0.0", "病历文本...")
print(result.primary_diagnosis)

# 浏览 Marketplace
packages = client.marketplace.list(category="编码")
for pkg in packages:
    print(f"{pkg.name} v{pkg.version}")
```

## 资源模块

| 模块 | 说明 |
|------|------|
| `client.facts` | 临床事实提取 |
| `client.agents` | Agent CRUD |
| `client.experts` | Expert 管理 |
| `client.reviews` | 编码审核 |
| `client.runtime` | Runtime Agent 执行、生命周期 |
| `client.marketplace` | Agent 市场浏览、安装 |
| `client.compliance` | 合规规则引擎 |
| `client.billing` | 账单与用量 |
| `client.oauth` | OAuth 客户端管理 |

## 要求

- Python >= 3.9
- httpx >= 0.27
- pydantic >= 2.0
