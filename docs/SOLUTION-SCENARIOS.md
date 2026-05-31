# iCoDer 解决方案场景

## 产品定位

iCoDer 是**可审计的临床AI**——每条编码溯源到病历原文，每条决策链SHA-256哈希可重放。预置编码审核、语音转录、文书生成等临床AI能力，即开即用。同时提供SDK/API供HIS厂商和开发者深度集成。

**与 Corti 的差异**：Corti 和 iCoDer 都是医疗 AI 产品，面向不同市场优化：
- Corti 面向 EU/US 医院，快速 SaaS 部署
- iCoDer 的差异化在于**可审计**——原生支持 ICD-10-CN/ICD-9-CM-3，确定性 ICD 索引算法（非 LLM 幻觉），每条编码决策链可完整重放，满足医保纠纷举证和《数据安全法》合规要求

---

## 场景一：智能编码审核 Agent

### 客户痛点

医院病案科每月需人工审核数千份出院病历的 ICD 编码。编码错误导致医保拒付，年损失数百万。现有编码员工作量饱和，审核覆盖率不足 30%。

### iCoDer 方案

开发者使用 iCoDer Agent Runtime，组合 9 个合同约束工具构建"智能编码审核 Agent"：

```
extract_evidence → search_icd10_index → assign_diagnosis_code
    → rank_evidence → calibrate_confidence → analyze_drg_impact
    → format_report
```

**Tier1 确定性保障**：
- `search_icd10_index`：33,304 条 ICD-10-CN 字典模糊匹配，LLM 不能编造编码
- `rank_evidence`：每条编码的证据强度评分（0-100），无证据编码自动标记
- `calibrate_confidence`：AUTO/REVIEW/ESCALATE 三级分流，高风险编码强制人工审核

**Deny-First 权限**：`finalize_primary_diagnosis` 标记 `requires_human: true`，直接影响 DRG 分组的操作必须人工确认。

### 部署方式

```bash
# 1. 通过 API 创建 Agent
curl -X POST /api/agents -d '{
  "name": "骨科编码审核Agent",
  "system_prompt": "你是骨科专科编码审核专家...",
  "config": {
    "routing_strategy": "tool_native",
    "permission_preset": "medical_coding",
    "tools": {"enabled": ["extract_evidence","search_icd10_index",...], "tier1_enforce": true}
  }
}'

# 2. 对接 HIS/EMR 系统
# 出院时自动触发 → POST /api/encounters/text → POST /api/reviews → Webhook 推送结果
```

### 效果指标

| 指标 | 人工审核 | iCoDer Agent |
|------|---------|-------------|
| 单份病历审核时间 | 15-30 分钟 | 15-30 秒 |
| 审核覆盖率 | ~30% | 100% |
| 编码准确率 (F1) | ~85% | 94.5% (金标准验证) |
| 证据可追溯 | 无 | 每条编码→病历原文溯源 |

---

## 场景二：临床文档改进 (CDI) Agent

### 客户痛点

医保飞行检查发现大量病历存在"诊断特异性不足"问题——如仅写"肺炎"而非"细菌性肺炎（左下叶）"。这直接影响 DRG 权重和医院收入。临床医生没有时间逐份检查文档质量。

### iCoDer 方案

构建 CDI Agent，只读分析病历文档，自动生成符合规范的医师查询：

```
extract_evidence → check_documentation_gaps → cdi_review → generate_cdi_query
```

**权限策略**：`cdi_audit` 预置——只读分析，不允许编码分配。`search_icd10_index` 等编码工具被 Deny-First 拦截。

### 生成的 CDI 查询示例

```markdown
## 文档缺口查询

**患者**: 张三 (ENC-20260529-001)
**主治医师**: 李医生
**日期**: 2026-05-29

### 查询 1: 肺炎诊断特异性
**依据**: 入院记录诊断"肺炎"，但痰培养结果为"肺炎链球菌"
**影响**: 当前编码 J18.9（未特指肺炎）→ 可升级为 J13（肺炎链球菌肺炎）
**DRG 影响**: ES21 → ES22，权重增加 0.35
**建议**: 请在病程记录中明确：肺炎病原体是否为肺炎链球菌？
```

### 部署方式

```bash
curl -X POST /api/agents -d '{
  "name": "CDI文档改进Agent",
  "config": {"permission_preset": "cdi_audit", "routing_strategy": "tool_native"}
}'
```

---

## 场景三：DRG 支付风控 Agent

### 客户痛点

医保 DRG 付费改革后，编码组合直接影响支付金额。医院需要在上传医保结算清单前，预判编码方案的 DRG 分组结果和支付风险。

### iCoDer 方案

构建 DRG 风控 Agent，输入编码方案即可获取分组预测和风险分析：

```
extract_evidence → search_icd10_index → assign_diagnosis_code 
    → analyze_drg_impact → calibrate_confidence
```

**审计链价值**：每份 DRG 分析报告的决策链可重放——医保纠纷时可以完整复现"为什么选择编码 A 而非编码 B"。

### 输出示例

```json
{
  "drg_impact": {
    "expected_drg": "RU14",
    "drg_weight": 1.85,
    "estimated_payment": 18500.00,
    "risk_level": "medium",
    "risk_factors": [
      "MCC 可能遗漏：患者有低蛋白血症但未编码",
      "手术编码与诊断不完全对应"
    ]
  },
  "audit_trail": [
    {"event": "search_icd10_index", "term": "椎体压缩骨折", "result": "M80.900"},
    {"event": "assign_diagnosis_code", "selected": "M80.900", "evidence": "MRI报告第3行"},
    {"event": "contract_post_denied", "tool": "assign_diagnosis_code", "reason": "code not verified"}
  ]
}
```

---

## 场景四：多院区 Agent 市场

### 客户痛点

大型医院集团（如华西医院集团）下辖 10+ 个院区，每个院区的编码规范略有差异。集团信息科需要统一管理各院区的 AI Agent，同时允许院区定制。

### iCoDer 方案

利用多租户架构 + Agent 市场：

```
iCoDer Console (集团管理员)
├── 组织: 华西医院集团
│   ├── Agent: 骨科编码审核 v1.0  (发布到市场)
│   ├── Agent: 肿瘤编码审核 v1.0
│   └── Agent: CDI文档改进 v1.0
│
├── 组织: 华西-骨科专科医院
│   ├── Agent: 骨科编码审核 v1.0  (从市场安装)
│   ├── Agent: 骨科CDI v1.0      (院区定制)
│   └── 权限: restrictive (仅确定性工具)
│
├── 组织: 华西-肿瘤医院
│   ├── Agent: 肿瘤编码审核 v1.0
│   └── Agent: 化疗方案审核 v1.0  (院区定制)
```

**技术支撑**：
- 多租户：Organization + OrganizationMember + switch-org
- Agent 市场：publish → marketplace → install
- 权限隔离：每个院区独立 PermissionPolicy
- 审计独立：每个组织的 AuditChain 完全隔离

---

## 场景五：第三方 HIS 厂商集成

### 客户痛点

某 HIS 厂商（如东软、卫宁）的产品线覆盖 500+ 医院。每家医院都在问"你们的系统能接入 AI 编码吗"。HIS 厂商没有 AI 团队，也不想维护 AI 基础设施。

### iCoDer 方案

HIS 厂商通过 iCoDer SDK 在现有系统中嵌入 AI 能力：

```javascript
// 东软 HIS 系统中的集成代码
import { iCoDerClient } from '@icoder/sdk';

const client = new iCoDerClient({
    apiKey: process.env.ICODER_API_KEY,
    baseUrl: 'https://icoder.example.com',
});

// 出院结算时自动触发编码审核
async function onDischarge(encounter) {
    const agent = await client.agents.get('ortho-coding-audit');

    const review = await client.agents.messageSend(agent.id, {
        message: {
            role: 'user',
            parts: [
                { kind: 'text', text: encounter.rawText },
                { kind: 'data', data: { patientId: encounter.patientId, existingCodes: encounter.codes } }
            ],
            messageId: crypto.randomUUID(),
            kind: 'message',
        },
    });

    // 审核结果直接嵌入 HIS 界面
    return {
        suggestedCodes: review.artifacts[0].data.codes,
        drgImpact: review.artifacts[1].data.drgImpact,
        auditReport: review.artifacts[2].data.report,
    };
}
```

**为什么 HIS 厂商选择 iCoDer 而非 Corti**：
- Corti 是封闭 SaaS——数据经 Corti 服务器，HIS 厂商无法控制
- iCoDer 是开源 Runtime——可部署在 HIS 厂商自己的机房/VPC，数据不出院
- Corti 的 Expert 是黑盒——HIS 厂商无法定制
- iCoDer 的 Tool 是合同定义——HIS 厂商可以新增自有工具（如对接内部药典、医保规则库）

---

## 场景六：医联体同质化质控

### 客户痛点

市级卫健委要求辖区内 20 家医院的编码质量达到统一标准。但各医院编码员水平参差不齐，三甲医院和社区医院的编码一致率不足 60%。

### iCoDer 方案

卫健委部署一套 iCoDer Runtime，为每家医院创建一个 Organization + 统一配置的编码审核 Agent：

```
iCoDer Runtime (卫健委私有云)
├── 组织: 市人民医院 (三甲)
│   └── Agent: 卫健委标准编码审核 v1.0 (只读，不可修改)
├── 组织: 区中心医院 (二甲)
│   └── Agent: 卫健委标准编码审核 v1.0
├── 组织: 社区卫生中心
│   └── Agent: 卫健委标准编码审核 v1.0
...
└── 金标准病例库 (统一维护)
    ├── 骨科 50 例
    ├── 肿瘤 50 例
    └── 心血管 50 例
```

**统一标准 + 灵活定制**：
- Agent 核心配置（工具链、权限策略）由卫健委锁定
- 每家医院的 system_prompt 可以微调（如添加本院常见编码提示）
- 金标准病例库统一维护，季度更新
- 每家医院的 AuditChain 独立存储，卫健委可审计

---

## 场景七：科研数据标准化

### 客户痛点

某医学院附属医院正在进行"骨质疏松骨折患者预后研究"，需要从 5 年内 10,000 份病历中提取标准化的诊断编码、手术编码和临床特征。研究生手动提取耗时 6 个月，且一致性差。

### iCoDer 方案

构建"研究数据提取 Agent"，批量处理历史病历：

```
extract_evidence → search_icd10_index → assign_diagnosis_code 
    → search_icd9_index → assign_procedure_code → format_report
```

```bash
# 批量处理
curl -X POST /api/reviews/batch -d '{
  "encounter_ids": ["ENC-001", "ENC-002", ..., "ENC-10000"],
  "agent_id": "research-extraction-agent"
}'

# 输出: 标准化 CSV
# encounter_id, primary_diag, secondary_diags, procedures, evidence_binding
# ENC-001, M80.900, [E11.900,I10], [81.6600x001], "MRI示T7/T9/T12/L2压缩骨折"
```

**为什么 iCoDer 适合科研**：
- 每个编码有 `evidence_binding`（溯源到病历原文）——满足论文发表的可重复性要求
- AuditChain 可重放——满足伦理审查的数据处理透明度要求
- 确定性 ICD 索引查询——不同于直接问 LLM 的幻觉风险

---

## 与 Corti 的场景差异总结

| 维度 | Corti | iCoDer |
|------|-------|--------|
| **目标用户** | EU/US 医院临床用户直接使用 | 中国医院直接使用预置AI能力；HIS厂商通过SDK集成 |
| **部署方式** | Corti SaaS (EU/US) | 自部署 (医院私有云/HIS厂商机房) |
| **数据主权** | 数据经 Corti 服务器 | 数据不离开客户基础设施 |
| **医学编码** | ICD-10-WHO / ICD-10-CM | ICD-10-CN 国标版/医保版 + ICD-9-CM-3 |
| **定制能力** | 通过 MCP 注册自定义 Expert | 新增 Tool + 修改合同 + 自定义权限策略 + SDK嵌入 |
| **医学确定性** | Expert 内部约束 (不透明) | Tier1 合同强制 + 确定性ICD索引算法 (透明、可审计) |
| **多租户** | Tenant-Name header | Organization 模型 + 市场分发 |
| **审计能力** | 平台级审计 | 每条编码的决策链可重放 (SHA-256哈希链) |
| **定价** | 按 credit 消耗 | 自部署 (一次性部署成本) + 可选按量计费 |

---

## 客户选择 iCoDer 的核心理由

1. **即开即用**：预置编码审核管道、语音转录、文书生成、事实提取等临床AI能力，医院部署后直接使用
2. **数据不出院**：Runtime 部署在客户自己的基础设施，满足《数据安全法》和医院信息科合规要求
3. **中国编码原生支持**：ICD-10-CN（国标版+医保版）+ ICD-9-CM-3，33,304 + 23,165 条完整字典，确定性格索算法（非LLM幻觉）
4. **确定性保障**：合同强制工具系统——ICD索引是确定性算法，证据排名是纯算法，编码→病历原文可溯源，每条决策链SHA-256哈希链可审计重放
5. **可扩展**：HIS厂商和开发者通过 SDK/API 深度定制，新增自有工具、对接内部药典和医保规则库

**Corti 适合**：需要快速上线、不想维护基础设施的医院。
**iCoDer 适合**：需要数据主权、需要深度定制、需要确定性医学保障的医院集团和 HIS 厂商。
