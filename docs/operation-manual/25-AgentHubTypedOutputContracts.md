# Agent Hub 机器可读输出契约

## 适用范围

本规则适用于 Agent Hub 中所有面向用户的 Agent Pack。它是开发环境发布门禁，不代表临床批准。

## Pack 声明

`output_contract` 必须同时声明：

- `schema_ref`：稳定的契约标识；
- `required_fields`：每次公共输出都必须存在的顶层字段；
- `optional_fields`：允许出现、但不要求每次出现的顶层字段；没有可选字段时使用空数组；
- `field_types`：每个必填及可选字段的 JSON 类型，键集合必须与两类字段的并集完全一致。
- `field_schemas`：每个必填及可选字段的递归结构和值约束，键集合必须与两类字段的并集完全一致。
- `field_relations`（可选）：由稳定 `id`、`when` 和 `must` 组成的跨字段蕴含关系；一旦声明即属于版本化公共契约。
- `evidence_bindings`（可选）：声明对象数组中 `evidence_text` 与两整数 `[start,end)` span 对本次已脱敏输入的精确绑定。

允许的类型只有 `string`、`boolean`、`integer`、`number`、`object`、`array`。`boolean` 不会被当作 `integer` 或 `number`；`number` 接受整数或浮点数。

示例：

```json
{
  "schema_ref": "icoder/TriageOutput/v1",
  "required_fields": ["acuity_level", "red_flags", "manual_review_required"],
  "optional_fields": ["supporting_notes"],
  "field_types": {
    "acuity_level": "string",
    "red_flags": "array",
    "manual_review_required": "boolean",
    "supporting_notes": "array"
  },
  "field_schemas": {
    "acuity_level": {"type": "string", "maxLength": 32768},
    "red_flags": {
      "type": "array",
      "maxItems": 100,
      "items": {"type": "string", "maxLength": 32768}
    },
    "manual_review_required": {"type": "boolean", "const": true},
    "supporting_notes": {
      "type": "array",
      "maxItems": 100,
      "items": {"type": "string", "maxLength": 32768}
    }
  }
}
```

跨字段关系示例：

```json
{
  "field_relations": [
    {
      "id": "procedure_count_matches_items",
      "when": [{"path": "procedures", "operator": "present"}],
      "must": [
        {
          "path": "procedures",
          "operator": "length_equals",
          "other_path": "total_count"
        }
      ]
    }
  ]
}
```

路径只能引用已由 `field_schemas` 声明的顶层字段或嵌套对象字段，不允许数组通配、属性访问、表达式或代码执行。每个契约最多 32 条关系，每个 `when`/`must` 最多 8 个谓词。受支持运算为 `equals`、`not_equals`、`present`、`absent`、`empty`、`non_empty`、`equals_path`、`not_equals_path` 和 `length_equals`。关系失败通过 `invalid_field_schemas` 返回声明路径、`fieldRelation`、稳定关系 ID 和抽象失败原因，不返回患者值。

`field_schemas` 使用受控 JSON Schema 子集：

- 结构：`type`、`properties`、`required`、`additionalProperties`、`items`；
- 值域：`enum`、`const`、`minimum`、`maximum`；
- 字符串：`minLength`、`maxLength`、`pattern`；
- 数组：`minItems`、`maxItems`、`uniqueItems`；
- 医疗证据区间扩展：`x-order`，只允许 `nondecreasing` 或 `strictly_increasing`。

对象必须声明非空 `properties`，且 `additionalProperties` 只能为 `false` 或一个有类型的动态值 schema；数组必须声明有类型的 `items`。当前不支持用空对象或 `additionalProperties: true` 逃避约束。首批统一值约束包括：字符串最长 32768 字符、数组最多 100 项、数值置信度范围 0–1、`char_span` 必须是两个非负且非递减整数，以及 `human_review=required` Pack 的 `manual_review_required=true`。

## 运行时行为

统一 Agent Run 和 Provider A2A 在公共输出边界执行同一校验：

1. 缺少必填字段时填充 `missing_required_fields`；
2. 字段类型错误时填充 `invalid_field_types`；
3. 模型或投影器输出未声明的顶层字段时填充 `undeclared_output_fields`；
4. 嵌套字段缺失、错类型、值域/长度/范围/顺序不合法或出现未声明属性时填充 `invalid_field_schemas`；
5. 任一列表非空时，`structured_extraction.valid=false`，运行失败关闭并要求人工复核；
6. 公共错误响应抑制畸形模型 markdown、领域字段、issue、tool payload 和 evidence，只保留安全的传输及校验元数据；
7. A2A 返回 `OUTPUT_CONTRACT_VIOLATION`，不得发布“成功外壳”。

未知顶层或嵌套属性名由 Provider 控制，可能被滥用为患者值载体，因此公共错误元数据只返回 `<redacted>`、数量和声明路径，不回显未知属性名或值。

领域输出与传输元数据必须分别构建。通用的 `status`、`markdown`、`corrected_draft` 等传输默认值，即使与 Pack 必填字段同名，也不能满足领域契约。只有当前 Pack 在 `required_fields` 或 `optional_fields` 中声明的投影结果，才能进入公共领域结果。

`invalid_field_types` 只包含字段名、期望类型和实际类型，不包含患者值。例如：

```json
{
  "field": "review_conclusion",
  "expected": "string",
  "actual": "array"
}
```

## Pack 维护

从 `backend` 目录执行：

```powershell
Remove-Item Env:ICODER_CREDENTIAL_LLM -ErrorAction SilentlyContinue
Remove-Item Env:DEEPSEEK_API_KEY -ErrorAction SilentlyContinue
$env:LLM_PROVIDER = "mock"
python scripts/corti_parity/sync_agent_pack_field_types.py
python scripts/corti_parity/sync_agent_pack_field_types.py --write
python scripts/corti_parity/sync_agent_pack_field_schemas.py
python scripts/corti_parity/sync_agent_pack_field_schemas.py --write
python scripts/corti_parity/bump_agent_pack_output_contract_versions.py --agent <agent-id> --write
python scripts/corti_parity/validate_agent_contract_compatibility.py
```

命令默认 dry-run。它只使用已经提交且覆盖全部必填字段的示例输出推导初始类型；示例缺字段、包含未声明字段、含空值、类型不支持或多个示例类型冲突时会拒绝执行。可选字段也必须至少有一个类型正确的示例证据。递归 schema 生成器对示例中的空数组要求显式维护 item schema，禁止生成无约束通配，并为所有声明字段生成值 schema。`--write` 会更新声明并刷新已存在的 Pack 完整性摘要。

`official_agents/output_contract_registry.json` 是追加式公共契约登记表。同一 `schema_ref` 的字段及递归 schema 必须完全不可变；任何变更都必须先提升 `/vN` 后缀，再用 `validate_agent_contract_compatibility.py --write` 登记新引用。该命令不会覆盖已有引用。

发布前必须运行：

```powershell
python scripts/corti_parity/build_agent_hub_runtime_matrix.py --assert-visible-ready
python scripts/corti_parity/validate_corti_prebuilt_agent_parity.py --assert-pass
python scripts/corti_parity/replay_agent_hub_typed_contracts.py
python scripts/corti_parity/replay_agent_hub_field_relations.py
python scripts/corti_parity/replay_agent_hub_evidence_bindings.py
python scripts/corti_parity/validate_agent_contract_compatibility.py
python scripts/corti_parity/validate_deployment_candidate.py --root ..
```

离线重放使用已脱敏的历史成功 Provider 输出，通过当前投影、人工复核和类型边界，不调用真实 LLM。真实模型质量、延迟和成本仍需使用新建的临时凭证另行验证，完成后必须注销凭证并关闭服务进程。

## 变更注意事项

### 数组逐项关系

当规则必须对数组中的每个对象分别成立时，在关系上声明 `for_each`。它必须指向 `field_schemas` 中已声明的对象数组，`when` 与 `must` 的路径均相对于单个数组项：

```json
{
  "id": "supported_code_requires_direct_high_confidence_evidence",
  "for_each": "supported_codes",
  "when": [{"path": "code", "operator": "present"}],
  "must": [
    {"path": "evidence_strength", "operator": "equals", "value": "direct"},
    {"path": "confidence", "operator": "gte", "value": 0.7},
    {"path": "evidence_text", "operator": "non_empty"}
  ]
}
```

集合操作符 `in`/`not_in` 要求非空、元素唯一且类型一致的 `value` 数组；数值操作符 `gt`/`gte`/`lt`/`lte` 要求有限数值阈值。省略 `for_each` 时仍按顶层对象关系执行。运行时检查每一个数组对象，失败只记录 `supported_codes[].confidence` 形式的声明路径，不记录数组下标或患者值。

空数组 item schema 模板的每个属性必须持有独立 schema 对象，禁止复用可变 leaf 引用，避免一个属性的枚举或范围约束污染同级属性。

### 集合不变量与证据绑定

根作用域关系还支持三个受控集合操作符：

- `count_where_equals`：对象数组中满足 `where` 的项目数必须等于非负整数 `value`；
- `contains_field_equals_path`：可带 `where` 筛选的数组项目，其 `item_path` 必须至少有一个等于根对象的 `other_path`；
- `disjoint_fields`：两个对象数组分别按 `item_path` 与 `other_item_path` 取值后必须互斥。

`where` 只允许使用普通标量/存在性谓词，禁止嵌套集合操作。集合操作只能用于根作用域，并且所有数组、项目路径和比较类型都必须由 `field_schemas` 声明。

精确证据绑定示例：

```json
{
  "evidence_bindings": [
    {
      "id": "diagnosis_evidence_matches_input",
      "for_each": "diagnoses",
      "text_path": "evidence_text",
      "span_path": "char_span"
    }
  ]
}
```

统一 Run 与 Provider A2A 使用同一份已脱敏输入执行绑定：`char_span` 必须是非空且位于输入边界内的 `[start,end)`，并且 `input[start:end]` 必须与 `evidence_text` 完全一致。失败只返回 `array[].evidence_text` 或 `array[].char_span`、`evidenceBinding`、稳定绑定 ID 和抽象原因，不返回引文、患者值或数组下标。没有运行输入的纯合同重放不伪造绑定成功；必须同时运行独立 evidence binding 对抗回放和带合成输入的 Run/A2A 测试。

- 修改字段类型属于公共 API 变更；应同时更新 Pack 示例、提示词、SDK 文档和兼容性测试。
- 新增公共顶层字段时必须先加入 `required_fields` 或 `optional_fields`；禁止依赖运行时透传未知字段。
- 新增、删除或修改任何公共字段/嵌套约束时必须升级 `schema_ref` 版本；兼容性门禁禁止静默修改已登记引用。
- 不得为了让历史 Provider 输出通过而放宽医疗安全字段或人工复核策略。
- 真实患者值不得出现在校验错误、日志、指标标签或部署报告中。

## 多文档证据坐标

统一 Run 输入可携带最多 32 个 `documents`。每个文档必须提供唯一 `document_id`、文本和可选的 `document_version`、`document_type`、`normalization`。单文档最多 64,000 字符，总计最多 256,000 字符；`normalization` 仅允许 `none`、`NFC`、`NFKC`。证据坐标始终指向脱敏后、按声明方式规范化的 Unicode 文本，不指向原始 PHI 文本或 OCR 像素坐标。

多文档绑定使用 `document_id_path`，需要版本消歧时再声明 `document_version_path`。运行时必须同时验证文档身份、版本、`[start,end)` 边界和精确引文；文档缺失、版本不匹配、同 ID 多版本歧义、跨文档同引文歧义或切片不一致均失败关闭。

## 跨 Agent 一致性与结果证明

`cross_agent_relations` 是受控的本地输出/上游输出关系 DSL。当前支持：

- `equals_upstream`；
- `scalar_in_upstream_items`；
- `local_items_subset_upstream_items`；
- `local_items_overlap_upstream_items`。

`medical_code` 规范化会执行 NFKC、去首尾空白、转大写并移除内部空白，只用于代码比较，不做临床同义词推断。冲突、缺失的必需上游结果或同 Agent 多个上游结果均失败关闭；错误元数据只包含声明路径、关系 ID 和抽象原因。

Compliance Guardrail 的当前契约还要求输出 `reviewed_codes`，逐项记录本次
规则实际检查的 `code`、`code_system` 和 `role`。当请求包含 Code Validation
上游结果时，以下关系强制审查集合来自上游已验证集合：

```json
{
  "id": "reviewed_codes_match_code_validation",
  "local_path": "reviewed_codes",
  "local_item_path": "code",
  "upstream_agent_id": "code-validation-agent",
  "upstream_path": "validated_codes",
  "upstream_item_path": "code",
  "operator": "local_items_subset_upstream_items",
  "normalization": "medical_code",
  "required": false
}
```

`required=false` 表示护栏仍允许独立运行；一旦提交该上游 Agent 的结果，
证明和集合关系都必须通过，不能把 optional 解释为“提交后可忽略冲突”。

跨 Agent 输入不得仅凭客户端声明的 `agent_id`、`run_id` 和 `schema_ref` 建立信任。每个成功的官方 Agent Run 返回 `schema_ref` 与 `result_attestation`；证明以 HMAC-SHA256 绑定组织、Agent、Run、Schema、完整结果摘要和有效期，不包含临床正文。后续请求必须把它作为上游项的 `attestation` 提交。统一 Run 在脱敏前验证；A2A 路由同样在路由脱敏前验证并向下游传递服务器拥有的验证标记。证明无效、过期、跨租户、身份不匹配或结果被篡改时，不调用 Provider。

发布前还必须运行：

```powershell
python scripts/corti_parity/replay_agent_hub_cross_agent_relations.py
```

`validate_corti_prebuilt_agent_parity.py` 固定校验登录态只读观察到的
Corti 20 个预置 Agent：名称和顺序、20 个一对一 iCoDer 映射、运行路径、
类型/递归契约、示例、不可变登记、禁止生产写回以及逐 Agent 中国适配标记。
该门禁必须把 `clinical_quality_verified` 和 `production_ready_verified`
保持为 false；开发门禁通过不得自动提升临床或生产声明。
