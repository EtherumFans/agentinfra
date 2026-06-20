# iCoDer ISV 开发指南

从零到发布：在 iCoDer Runtime 上构建合规 Agent。

> **【2026-06-17 定位更新】** 本指南的"`pip install icoder-runtime` → 本地运行"流程基于早期独立 Runtime 模型，已废弃。
> 现行方向：**Runtime 是 iCoDer Server 的内核，v1 以托管云（hosted cloud）交付**；ISV 通过注册账户 + API Client / SDK + `.icoder-agent` 包在托管平台上构建、测试、发布 Agent，而非在本地 pip 安装 Runtime。
> 下方的安装 / 初始化命令以本说明为准；Agent 结构（agent.json / system_prompt / tools / permissions）与 pack 协议仍然适用。

## 1. 安装

```bash
pip install icoder-runtime
```

## 2. 创建 Agent 项目

```bash
icoder init my-audit-agent
cd my-audit-agent
```

生成的文件：
```
my-audit-agent/
├── agent.json          # Agent 元数据
├── system_prompt.md    # System prompt
├── tools/              # 自定义 Tool（每个 Tool 一个 JSON）
├── permissions.json    # 权限预设
└── README.md
```

## 3. 编写 System Prompt

编辑 `system_prompt.md`：

```markdown
# 医保编码审核 Agent

你是医保结算清单审核专家。你的职责是检查诊断编码和手术编码是否符合医保规则。

## 检查要点
1. 主要诊断与主要手术的一致性
2. 性别特定编码的正确性
3. 年龄相关编码的合理性
4. DRG 入组的编码完整性

## 输出格式
1. 审核结论：PASS / WARNING / FAIL
2. 发现的问题（如有）
3. 建议修改的编码
```

## 4. 添加自定义 Tool

在 `tools/` 目录创建 JSON 文件：

```json
{
    "id": "gender-consistency-check",
    "name": "性别一致性检查",
    "description": "检查诊断编码和手术编码与患者性别的兼容性",
    "tier": 1,
    "category": "compliance",
    "requires": ["diagnosis_code and procedure_code must be valid"],
    "guarantees": "returns list of gender-mismatch violations",
    "params": {
        "gender": {"type": "string", "required": true},
        "diagnosis_codes": {"type": "array", "required": true}
    },
    "accuracy_tags": ["compliance", "gender-check"]
}
```

Tool 合同说明：
- `tier: 1` = 确定性检查（Runtime 强制执行合同，不依赖 LLM）
- `tier: 2` = LLM 辅助推理
- `requires` = 前置条件（调用前必须满足）
- `guarantees` = 后置条件（工具承诺的输出）

## 5. 配置权限

编辑 `permissions.json`：

```json
{
    "key": "coding-audit",
    "name": "编码审核权限",
    "description": "允许编码查询和合规检查，禁止修改编码",
    "tools": {
        "extract_evidence": {"action": "allow", "max_per_session": 10},
        "search_icd10_index": {"action": "allow", "max_per_session": 200},
        "gender-consistency-check": {"action": "allow"},
        "assign_diagnosis_code": {"action": "require_human"}
    }
}
```

- `action: allow` = 允许
- `action: deny` = 禁止
- `action: require_human` = 需要人工确认

## 6. 本地测试

```bash
icoder test .
```

输出：
```
Loaded: my-audit-agent v1.0.0
  Experts: 0
  Tools: 1

Test input: 患者女性65岁胸痛3小时...

Result:
  Review ID: a1b2c3d4
  Processing: 2ms
  Audit entries: 3
  Chain valid: True

Test PASSED.
```

## 7. 启动 Dashboard 可视化测试

```bash
icoder dashboard
```

浏览器打开 http://127.0.0.1:8766/dashboard — 可以在 UI 中导入 Agent、运行、查看审计链。

## 8. 打包

```bash
icoder pack .
```

生成 `my-audit-agent.icoder-agent` 文件。这是一个自包含的 JSON 包——包含 Agent 定义、Tools、Permissions 和完整性校验。

## 9. 分发

- **HIS 厂商集成**：将 .icoder-agent 文件放在 HIS 部署脚本的预置目录中，HIS 后端通过 Runtime HTTP API 调用
- **直接分享**：通过邮件/微信发送给客户，客户在本地 Runtime 中导入
- **Marketplace 发布**：上传到 [iCoDer Marketplace](/marketplace) 供搜索和下载。在 Marketplace 页面点击「Publish Agent」上传 .icoder-agent 文件即可

## 10. Runtime HTTP API

如果不使用 CLI，可以直接调用 HTTP API：

```bash
# 启动 Runtime
icoder-runtime serve --port 8765

# 导入 Agent
curl -X POST http://127.0.0.1:8765/api/agents/import \
  -H "Content-Type: application/json" \
  -d '{"pack": {...}}'

# 运行 Agent
curl -X POST http://127.0.0.1:8765/api/runs \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "...", "input": "病历文本..."}'

# 查看运行历史
curl http://127.0.0.1:8765/api/runs
```

---

## Tool 合同编写规范

每个 Tool 必须声明：

| 字段 | 必填 | 说明 |
|------|------|------|
| id | ✅ | 唯一标识符 |
| name | ✅ | 展示名称 |
| description | ✅ | 功能描述 |
| tier | ✅ | 1=确定性核心, 2=LLM推理 |
| category | ✅ | 分类标签 |
| requires | ✅ | 前置条件列表 |
| guarantees | ✅ | 后置条件 |
| params | — | 参数 schema |
| accuracy_tags | — | 准确度标签（用于自动注入） |

Runtime 在调用 Tool 前强制检查 requires，调用后验证 guarantees。违反合同 = Agent 执行中止并记录违规。
