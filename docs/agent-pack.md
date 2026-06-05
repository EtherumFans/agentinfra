# .icoder-agent 包格式规范 v1.1

## 包结构

```
my-agent/
  agent_pack.json    # 必需: 包定义文件
  system_prompt.md   # 可选: 系统提示词
```

## agent_pack.json 字段

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| format_version | string | 是 | 格式版本 "1.1" |
| agent_type | string | 是 | "certified" 或 "community" |
| agent_ref | string | 推荐 | 规范引用 "publisher/name@version" |
| manifest.name | string | 是 | Agent 显示名称 |
| manifest.version | string | 是 | 语义化版本 |
| manifest.description | string | 是 | 功能描述 |
| manifest.category | string | 是 | 分类 (编码/医保/质控/文书/急诊/护理/药学) |
| manifest.icon | string | 是 | 图标名称 |
| system_prompt | string | 是 | 系统提示词 |
| experts | list[dict] | 否 | Expert 定义列表 |
| tools | list[string] | 否 | 工具 ID 列表 |
| permissions | dict | 否 | 工具权限配置 |
| requirements.min_runtime_version | string | 是 | 最低 Runtime 版本 |
| llm_capabilities | dict | 否 | LLM 能力要求 |
| code | dict | 否 | 内联代码 (仅 community) |
| integrity.sha256 | string | 否 | 包完整性校验 |

## agent_type

- **certified**: iCoDer 官方审查过的 Agent，不允许代码执行
- **community**: 第三方 ISV Agent，允许代码执行 (Tier 2+)

## 安全层级

| Tier | 标签 | 说明 |
|------|------|------|
| 0 | 纯提示词 | 无工具，无代码 |
| 1 | 只读工具 | 代码字典、规则查找 |
| 2 | 沙箱代码 | 可执行 Python 代码 |
| 3 | 网络访问 | HTTP 外部 API 调用 |
| 4 | 系统回写 | HIS/EMR/医保 写操作 |

## 示例

```json
{
  "format_version": "1.1",
  "agent_type": "certified",
  "manifest": {
    "name": "合规护栏",
    "version": "1.0.0",
    "description": "评估编码集的医保合规性",
    "category": "医保",
    "icon": "Shield"
  },
  "system_prompt": "你是医保合规审核专家...",
  "tools": ["guard_input", "guard_output", "analyze_drg_impact"],
  "permissions": {
    "tools": {
      "guard_input": {"allowed": true},
      "analyze_drg_impact": {"allowed": true, "max_per_session": 5}
    }
  },
  "requirements": {"min_runtime_version": "1.0.0"},
  "llm_capabilities": {
    "required_models": [{"name": "deepseek-v4"}],
    "supports_json_mode": true
  }
}
```
