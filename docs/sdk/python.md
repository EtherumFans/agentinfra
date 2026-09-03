# Python SDK

```bash
pip install icoder-sdk
```

Python SDK 接受已经换取的 tenant-bound access token。client secret 只应由服务端 OAuth
交换逻辑或密钥管理系统读取，不应写入病历处理代码。

```python
import os
import uuid

from icoder_sdk import iCoDerClient, iCoDerConfig

client = iCoDerClient(iCoDerConfig(
    base_url=os.getenv('ICODER_BASE_URL', 'http://127.0.0.1:8000'),
    access_token=os.environ['ICODER_ACCESS_TOKEN'],
))

facts = client.facts.extract('去标识病历文本', output_language='zh-CN')
print(facts.facts, facts.usage_info.credits_consumed)

coding = client.medical_coding.predict(
    '患者有2型糖尿病史。',
    coding_systems=['icd10cn', 'icd9cm3'],
    include_codes=['E11'],
    exclude_codes=['E11.0'],
    expand_categories=True,
)
print(coding['codes'], coding['filter_applied'])

# Development risk review only: authoritative/payment-bearing results fail closed.
drg_risk = client.drg_dip_risk_review.analyze(
    {'code': 'I10'},
    patient_age=58,
)
print(drg_risk['review_conclusion'], drg_risk['manual_review_required'])

run = client.runs.run_text(
    'note-completeness-agent',
    '去标识病历文本',
    idempotency_key=uuid.uuid4().hex,
)
print(run['run_id'], run['result'], run['trace_url'])
status = client.runs.get(run['run_id'])
cancellation = client.runs.cancel(run['run_id'], 'operator request')
```

For resilient consumers, use `stream_events_resilient()`. A purged trace or
cursor raises the terminal, non-retryable `RunEventRetentionError`; only its
safe `error_code` and `retention_days` are retained, never the raw clinical
response.

SDK 是同步 httpx 客户端。实时 STT 另提供 async WebSocket 会话；不要在异步事件循环中
直接执行同步方法。

A2A v1 长任务使用持久化 Task；订阅可从事件序号或 `Last-Event-ID` 恢复：

```python
submitted = client.a2a.message_send_v1(
    "note-completeness-agent",
    "去标识病历文本",
    return_immediately=True,
)
task_id = submitted["task"]["id"]
for event in client.a2a.subscribe_task_v1(
    "note-completeness-agent", task_id, after_sequence=0
):
    print(event["eventId"], event["eventType"])
terminal = client.a2a.wait_task_v1("note-completeness-agent", task_id)
```

`wait_task_v1()` 会如实返回 `completed`、`failed` 或 `canceled`，不会把失败或无法中途取消的 Provider 调用包装成成功。

中国编码入口可单独或同时接受 `icd10cn` 诊断和 `icd9cm3` 手术操作。类别展开开启时，
include/exclude 以不区分大小写的前缀匹配叶子编码；关闭时只做完整编码匹配。过滤由服务端
再次确定性执行。

`drg_dip_risk_review` 只公开非权威风险审查、规则和治理信息。SDK 会拒绝非零 DRG
权重、DIP 分值、支付估算、`billing_authoritative=True` 或
`manual_review_required=False`；`predicted_drg` 是开发候选兼容字段，不得用于医保
分组、结算或临床自动决策。

受控实网连通性检查必须先读取租户目录声明的策略，并且只有目录明确允许时才调用：

```python
catalog = client.models.get_catalog()
if catalog["live_canary_available"]:
    canary = client.models.live_canary(
        catalog["effective_deployment_id"],
        max_cost_cny=catalog["live_canary_policy"]["max_cost_cny"],
    )
    print(canary["status"], canary["latency_ms"])
```

`live_canary()` 不接受提示词或自由文本，只发送服务端固定的无患者数据载荷；完成正文不会
返回或写入审计。一次成功仅是连接观察，不等于模型质量、持续在线健康、SLA 或权威账单。

机器客户端的签名 `trace_url` 才包含事件 token；可将其 `token` 查询参数传给
`client.runs.stream_events(run_id, trace_token)`。取消必须读取 `outcome`；HTTP 202 +
`RECORDED_ONLY` 表示 Provider 仍在运行，应继续轮询 `get()`，不能显示“已取消”。
