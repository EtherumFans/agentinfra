# 文书聚合智能体 — 设计文档

## 核心洞察

```
之前编码的依据:
  单份入院记录文本 → LLM 提取事实 → 编码
  问题: 只有文本, 无签名, 无跨文档交叉验证

之后编码的依据:
  易企签归档的全部签署文书 → 文书聚合智能体 → 多源事实融合 → 编码
  优势: 有签名 = 有法律效力, 跨文档 = 可交叉验证
```

## 证据等级金字塔

```
         ┌──────────────┐
         │  已签署归档   │  ← 最强 (医师签名 + 时间戳)
         │  的版式文件   │
         ├──────────────┤
         │  CA 数据签名  │  ← 强 (过程数据, 含签名)
         │  的过程数据   │
         ├──────────────┤
         │  业务系统     │  ← 中 (结构化, 但未签署)
         │  结构化数据   │
         ├──────────────┤
         │  EMR 自由文本 │  ← 弱 (无结构, 无签名)
         └──────────────┘
```

## 文书聚合智能体设计

### Agent 配置

```yaml
名称: 文书聚合智能体
描述: 从易企签归档系统中拉取患者全部已签署文书，提取结构化事实，
      建立跨文档证据链，作为编码审核的权威输入
类别: 质控
路由策略: fixed_order (按文档时间顺序处理)

绑定的专家:
  1. 易企签文档检索专家 — 查询患者全部已签署文书
  2. 证据提取专家 — 从每份文书中提取临床事实
  3. 时序排列专家 — 按时间线排列所有事实
  4. 交叉验证专家 — 检查跨文档事实是否一致
  5. 完整性检查专家 — 标记缺失的必需文书
```

### 工作流

```
患者 ID / 就诊 ID
    │
    ▼
Step 1: 文档检索 (易企签文档检索专家)
    │
    ├─ 查询该患者/就诊的全部已签署文书:
    │   ├─ 入院记录 ✓  (签署: 主治医师 2026-05-10 08:30)
    │   ├─ 手术记录 ✓  (签署: 手术医生 2026-05-10 14:00)
    │   ├─ 麻醉记录 ✓  (签署: 麻醉医师 2026-05-10 13:45)
    │   ├─ 病理报告 ✓  (签署: 病理医师 2026-05-12 10:00)
    │   ├─ 检验报告 ✓  (签署: 检验医师 2026-05-10 11:00)
    │   ├─ 出院小结 ✓  (签署: 主治医师 2026-05-15 09:00)
    │   ├─ 知情同意书 ✓ (签署: 患者 + 医师 2026-05-09 16:00)
    │   └─ 病案首页 ✓  (签署: 编码员 + 科主任 2026-05-16 10:00)
    │
    ▼
Step 2: 事实提取 (证据提取专家)
    │
    │  对每份文书提取结构化事实:
    │
    │  入院记录     → 主诉、现病史、既往史、查体、初步诊断
    │  手术记录     → 手术名称、术式、入路、术中所见、植入物
    │  麻醉记录     → 麻醉方式、ASA 分级
    │  病理报告     → 病理诊断、组织学分型
    │  检验报告     → 检验项目、结果值、参考范围
    │  出院小结     → 出院诊断、出院医嘱
    │  知情同意书   → 手术名称 (同意书版本)、患者生物特征
    │  病案首页     → 主要诊断编码、主要手术编码、DRG
    │
    ▼
Step 3: 时序排列 (时序排列专家)
    │
    │  按时间线排列所有事实:
    │
    │  2026-05-09 16:00 [知情同意书] 拟行: 经皮椎体后凸成形术
    │  2026-05-10 08:30 [入院记录]   主诉: 腰痛4月余
    │  2026-05-10 11:00 [检验报告]   骨密度 T值=-3.2
    │  2026-05-10 13:45 [麻醉记录]   麻醉方式: 全麻, ASA II
    │  2026-05-10 14:00 [手术记录]   手术: T7/T9/T12/L2 椎体成形术
    │  2026-05-12 10:00 [病理报告]   病理: 骨质疏松改变
    │  2026-05-15 09:00 [出院小结]   出院诊断: 腰椎压缩性骨折...
    │
    ▼
Step 4: 交叉验证 (交叉验证专家)
    │
    │  检查跨文档一致性:
    │
    │  ✅ 知情同意书 "经皮椎体后凸成形术" = 手术记录 "椎体成形术" (一致)
    │  ⚠️ 入院诊断 "腰椎压缩性骨折" (T12, L2)
    │        手术记录 "T7/T9/T12/L2 椎体成形术" (多了 T7, T9)
    │        → 标记: 手术范围大于入院预期
    │  ✅ 骨密度 T值=-3.2 (严重骨质疏松) 支持 "重度骨质疏松症" 诊断
    │  ❌ 知情同意书缺少植入物品牌信息 (高值耗材需记录)
    │
    ▼
Step 5: 完整性检查 (完整性检查专家)
    │
    │  ✅ 入院记录 ✓
    │  ✅ 手术记录 ✓
    │  ✅ 麻醉记录 ✓
    │  ✅ 病理报告 ✓
    │  ✅ 出院小结 ✓
    │  ❌ 高值耗材条码记录 ✗ (植入物需追溯)
    │  ❌ 术后影像报告 ✗ (椎体成形术后应拍 X 光确认)
    │
    ▼
Step 6: 输出聚合结果
    │
    │  传入编码流水线:
    │  {
    │    "patient_id": "P20260001",
    │    "encounter_id": "ENC-xxx",
    │    "documents": [
    │      { "type": "入院记录", "signed_by": "主治医师", "signed_at": "..." },
    │      { "type": "手术记录", "signed_by": "手术医生", "signed_at": "..." },
    │      ...
    │    ],
    │    "aggregated_facts": {
    │      "diagnosis_facts": [...],     // 跨文档合并
    │      "procedure_facts": [...],
    │      "lab_results": [...],
    │      "pathology_results": [...]
    │    },
    │    "cross_validations": [...],     // 跨文档一致性检查
    │    "completeness_gaps": [...],     // 缺失的必需文书
    │    "evidence_strength": 0.95       // 基于签署状态的证据强度评分
    │  }
    │
    ▼
编码流水线 获取聚合结果 → 事实已齐全 + 已验证 → 编码更精准
```

## 与 iCoDer 现有架构的关系

```
当前: 入院记录 → EvidenceExpert → DiagnosisExpert → ProcedureExpert → ...

之后:
  易企签全部文书 → DocumentAggregationAgent → 聚合事实
       ↓
  EvidenceExpert (增强)
       ↓ 输入是 "聚合事实" 而非 "单份文本"
  DiagnosisExpert
       ↓ 有跨文档验证标记辅助判断
  ProcedureExpert
       ↓ 手术记录 + 知情同意书 + 麻醉记录 三者对照
  ...
```

## 证据强度评分逻辑

```python
def get_evidence_strength(facts, documents):
    score = 0.0
    for fact in facts:
        # 1. 来源文档是否已签署
        if fact["source_document"]["signed"]:
            score += 0.3

        # 2. 是否有多个文档支持同一事实
        if fact["cross_document_count"] >= 2:
            score += 0.2

        # 3. 是否有权威文档类型 (手术记录 > 病程记录)
        if fact["source_document"]["type"] in ["手术记录", "病理报告", "检验报告"]:
            score += 0.2

        # 4. 是否有时间戳
        if fact["source_document"]["timestamp"]:
            score += 0.1

    return min(1.0, score / len(facts))
```

## 技术实现

### 新增文件

```
backend/
├── app/
│   ├── agents/experts/
│   │   └── signit_retrieval_expert.py    # 易企签文档检索
│   ├── services/
│   │   ├── signit_client.py              # 易企签 API 客户端
│   │   └── document_aggregator.py        # 文书聚合引擎
│   └── api/
│       └── signit_callback.py            # 易企签回调 webhook
```

### SignIT Retrieval Expert

```python
class SignITRetrievalExpert(BaseExpert):
    name = "易企签文档检索专家"
    description = "从易企签归档系统检索患者全部已签署文书"

    async def run(self, context: dict) -> dict:
        patient_id = context.get("patient_id") or context.get("encounter", {}).get("patient_id")
        encounter_id = context.get("encounter_id")

        # 1. 查询患者全部已签署文书
        documents = await signit_client.search_documents(
            patient_id=patient_id,
            encounter_id=encounter_id,
            status="signed"  # 只取已签署的
        )

        # 2. 按类型分类
        by_type = {}
        for doc in documents:
            dtype = doc["document_type"]
            by_type.setdefault(dtype, []).append(doc)

        return {
            "expert": self.name,
            "total_documents": len(documents),
            "documents_by_type": by_type,
            "completeness": self._check_completeness(by_type),
            "evidence_strength": self._estimate_strength(documents),
            "documents": documents
        }

    def _check_completeness(self, by_type: dict) -> dict:
        """检查文书完整性"""
        required = {
            "入院记录": "必须",
            "病程记录": "必须",
            "手术记录": "有手术时必须",
            "出院小结": "必须",
            "病案首页": "必须",
            "知情同意书": "有手术/操作时必须",
            "麻醉记录": "有手术时必须",
            "病理报告": "有病理检查时必须",
        }
        missing = []
        for dtype, req in required.items():
            if dtype not in by_type or not by_type[dtype]:
                missing.append({"type": dtype, "requirement": req})
        return {"missing": missing, "complete": len(missing) == 0}
```

## 对编码准确率的预期影响

| 场景 | 之前 (单文档) | 之后 (文书聚合) | 提升 |
|------|-------------|---------------|------|
| 诊断编码 | 仅入院记录 | 入院 + 出院小结 + 检验 → 交叉验证 | +5-10% |
| 手术编码 | 仅手术记录 | 手术记录 + 知情同意书 + 麻醉记录 → 三者对照 | +8-12% |
| DRG 分组 | 诊断 + 手术 | 诊断 + 手术 + 检验 + 病理 → 更精准 CC/MCC | +3-5% |
| 证据追溯 | 单份文本引用 | 多文档 + 签署人 + 时间戳 → 完整证据链 | 质变 |
| 编码缺失 | 容易漏编码 | 出院小结与入院记录互为补充 → 减少漏编码 | -20% |
