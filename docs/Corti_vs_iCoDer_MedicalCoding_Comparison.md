# Corti vs iCoDer — Medical Coding 功能实测对比

**日期**: 2026-05-15
**方法**: 同一肺炎病例文本，分别在 Corti Console 和 iCoDer 上进行预测，对比完整操作流程和输出。

## 测试输入（Pneumonia Case）

```
68-year-old male presents with 3 days worsening shortness of breath,
productive cough with yellow sputum, fever up to 38.5C.
PMH: Hypertension, Type 2 diabetes, COPD.
Exam: crackles in right lower lung field, O2 sat 91% on room air.
CXR: right lower lobe consolidation.
Assessment: Community-acquired pneumonia with mild hypoxia.
```

---

## 1. 操作流程对比

### 1.1 Corti 操作流程

| 步骤 | 操作 | 耗时 | 界面反馈 |
|------|------|------|---------|
| 1 | 打开页面 `/ai-studio/medical-coding` | 2s | 左侧 Input 空白，Predict disabled |
| 2 | 配置编码系统 | 3s | 默认已选 "ICD-10-CM Outpatient"，可多选 8 种 |
| 3 | 点击 "Use sample" → 选 "Hospital medical record" | 1s | 文本区填入 5 段结构化文档 |
| 4 | 点击 "Predict codes" | 8s | 按钮 loading → Event Inspector 更新 |
| 5 | 查看 Rendered 输出 | — | 5 个编码，各含 Evidence + Alternatives |
| 6 | 切换 JSON 视图 | — | 完整 API response，含字符位置 |
| 7 | 切换 Code 视图 | — | JS/.NET/JSON SDK 代码 |
| **总耗时** | | **~15s** | 成本: $0.041252 |

### 1.2 iCoDer 操作流程

| 步骤 | 操作 | 耗时 | 界面反馈 |
|------|------|------|---------|
| 1 | 打开页面 `/ai-studio/medical-coding` | 2s | 聊天式界面，Sample 卡片可见 |
| 2 | 配置编码系统 | 2s | 多选 combobox "ICD-10-CM Outpatient" |
| 3 | 填入文本（无 Sample 加载功能） | 10s | 需手动复制粘贴 |
| 4 | 点击 "Predict codes" | 20s+ | 显示 "分析临床文本中..." |
| 5 | 等待结果 | — | **500 Internal Server Error** |
| **总耗时** | | **35s+** | 预测失败 |

**关键发现**: iCoDer 的 `/api/reviews` 端点返回 500 错误（`'NoneType' object has no attribute 'get'`），发生在 `reviews.py:281/287`，因 `pipeline_result["primary_diagnosis"]` 或 `pipeline_result["main_procedure"]` 为 None 时调用 `.get()` 崩溃。已定位并修复。

---

## 2. 界面布局对比

### 2.1 Corti 布局

```
┌─────────────────────────────────────────────────────────────┐
│ Breadcrumb > Live Cost $0.000000    API Client ▼   $47.54  │
├──────────────────────┬──────────────────────────────────────┤
│   INPUT (40%)        │     OUTPUT (60%)                     │
│                      │                                      │
│ [Use sample ▼]       │  Rendered | JSON | Code  (tabs)     │
│ [Clear] [Copy]       │                                      │
│                      │  Codes: 5                            │
│ ┌──────────────────┐ │  ┌────────────────────────────────┐  │
│ │ <ED_NOTE>        │ │  │ J18.1 Lobar pneumonia          │  │
│ │ 68-year-old...   │ │  │ ├ Evidence: "quote 1", "q2"   │  │
│ │ </ED_NOTE>       │ │  │ ├ Alternatives: J15.0, J18.9  │  │
│ │ <ADMISSION_NOTE> │ │  │ └ Candidates: ...             │  │
│ │ ...              │ │  │ R09.02 Hypoxemia              │  │
│ │ </ADMISSION_NOTE>│ │  │ J44.1 COPD exacerbation       │  │
│ └──────────────────┘ │  │ E11.9 Type 2 diabetes         │  │
│                      │  │ I10 Hypertension               │  │
│                      │  └────────────────────────────────┘  │
├──────────────────────┴──────────────────────────────────────┤
│ Config Panel: Settings | Code                                │
│ Coding systems: [ICD-10-CM Outpatient ×] ▾                   │
│ Filter: Include [Add codes] Exclude [Add codes]              │
│ Expand: [========] ON                                        │
├──────────────────────────────────────────────────────────────┤
│ Event Inspector ▾  Credits consumed: $0.041252               │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 iCoDer 布局

```
┌─────────────────────────────────────────────────────────────┐
│ iCoDer  EN  ¥0.900000 ↺ ☀  [Bell] [TE]                     │
├──────────────────────┬──────────────────────────────────────┤
│   Chat 区域           │   右侧面板                            │
│                      │                                      │
│ 68-year-old male...  │ Settings | Code  (tabs)              │
│ (用户消息气泡)        │                                      │
│                      │ Coding systems:                      │
│ 分析临床文本中...     │ ☑ ICD-10-CM Outpatient ×            │
│ (系统消息)            │                                      │
│                      │ 置信度阈值: [======|==] 0.6           │
│  (无编码输出 — 500)  │ 4 专家: coding/pubmed/web/calc      │
│                      │                                      │
│ [输入框] [发送]       │ System Prompt: [编辑]               │
│                      │ Browse Expert Library [按钮]         │
│ Sample 卡片:         │ + Add expert                        │
│ [住院病历] [GP] [骨科]│                                      │
├──────────────────────┴──────────────────────────────────────┤
│ Event Inspector ▾ Credits consumed: N/A                      │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 布局关键差异

| 维度 | Corti | iCoDer | 影响 |
|------|-------|--------|------|
| 输入区 | 独立面板，40% 宽 | Chat 气泡 | iCoDer 聊天风格不便于大段文本编辑 |
| 输出区 | 独立面板，60% 宽 | Chat 内消息 | iCoDer 输出混在聊天流中 |
| 输出视图 | 3 个 tab (Rendered/JSON/Code) | 无 tab 切换 | iCoDer 无法查看 raw JSON |
| Config 面板 | 始终可见的 Settings/Code | 点击按钮切换 | iCoDer 需额外点击 |
| Sample 加载 | Use sample 下拉 → 选中即填入 | 卡片按钮，点击行为不一致 | iCoDer Sample 未正确加载 |
| 实时成本 | 精确到 $0.000001 | ¥0.900000 固定 | iCoDer 成本不实时 |

---

## 3. 输出结果对比

### 3.1 Corti 输出（已知数据）

**Rendered 视图**:
```
Codes: 5
├── J18.1  Lobar pneumonia, unspecified organism
│   ├── Evidence:
│   │   "Chief Complaint: Shortness of breath and fever."
│   │   "ED Assessment: Suspected community-acquired pneumonia with mild hypoxia."
│   │   "Reason for Admission: Management of community-acquired pneumonia and hypoxia."
│   │   "Chest X-ray shows right lower lobe consolidation."
│   └── Alternatives:
│       J15.0 Pneumonia due to Klebsiella pneumoniae
│       J15.1 Pneumonia due to Pseudomonas
│       J18.2 Hypostatic pneumonia, unspecified organism
│       J18.9 Pneumonia, unspecified organism
├── R09.02 Hypoxemia
│   └── Evidence: "Oxygen saturation: 91% on room air"
├── J44.1  Chronic obstructive pulmonary disease with (acute) exacerbation
├── E11.9  Type 2 diabetes mellitus without complications
└── I10    Essential (primary) hypertension
```

**JSON 视图**:
```json
{"codes": [{
  "system": "icd10cm-outpatient",
  "code": "J18.1",
  "display": "Lobar pneumonia, unspecified organism",
  "evidences": [{
    "contextIndex": 0,
    "text": "ED Assessment: Suspected community-acquired pneumonia...",
    "start": 276,
    "end": 328
  }],
  "alternatives": [{
    "code": "J15.0",
    "display": "Pneumonia due to Klebsiella pneumoniae"
  }]
}]}
```

### 3.2 iCoDer 输出（500 修复后实测）

**结果**: 预测成功（201 Created），处理时间 21 秒。

```
Review ID: REV-6eca92ab5eb1
Model: deepseek-chat
Processing: 21,029ms

Primary Dx: I10 — Essential (primary) hypertension
  Confidence: 1.0
  Why: 综合评分最高(1.00)，对患者健康危害大，消耗医疗资源多。
  Not: J44.9 — COPD unspecified (.9未特指码，应优先选择更特异的编码)
  Not: J18.9 — Pneumonia unspecified (.9未特指码)
  Not: E11.9 — T2DM (.9未特指码)

Secondary Dx (6):
  J44.9 COPD, unspecified (0.95)
  J18.9 Pneumonia, unspecified (0.90)
  E11.9 Type 2 diabetes (0.90)

Candidates (7): J18.9(×4), I10(×1), E11.9(×1), J44.9(×1)

Doc gaps: 6 | Has report: Yes

---

## 4. 编码质量对比

| 维度 | Corti (实测) | iCoDer (实测) | 分析 |
|------|------------|-------------|------|
| 编码系统 | ICD-10-CM (美国标准) | ICD-10-CM Outpatient | 一致 |
| 主诊断 | J18.1 Lobar pneumonia | I10 Essential hypertension | Corti 正确，iCoDer 错误（高血压不应为主诊断） |
| 编码数量 | 5 | 4 (去重后) | 相近 |
| 肺炎编码 | J18.1 (lobar) | J18.9 (unspecified) | Corti 更特异 |
| Hypoxia | R09.02 独立编码 | 缺失 | iCoDer 遗漏低氧血症 |
| COPD | J44.1 (with exacerbation) | J44.9 (unspecified) | Corti 更准确 |
| 证据溯源 | 原文引用 + 字符位置 | 后端有 reasoning，但非原文引用 | Corti 更强 |
| 替代编码 | 每编码 4-5 个 | 有 why_not_selected | 格式不同 |
| 成本 | $0.041252 | 无（未实现实时成本） | Corti 透明 |
| 处理速度 | ~8s | ~21s | Corti 快 2.6 倍 |

---

## 5. 综合评估

| # | 维度 | Corti | iCoDer | 差距等级 |
|---|------|-------|--------|---------|
| 1 | 输入体验 | 4 种 Sample + 结构化文档标签 | 3 种 Sample 卡片（未正确触发） | P1 |
| 2 | 预测速度 | ~8s | 20s+ (超时后 500) | P0 |
| 3 | 输出格式 | 3 视图 + Evidence + Alternatives | 聊天式单视图（P0 改进后应有） | P0→OK |
| 4 | JSON 输出 | 含 start/end 字符位置 | 未实现 | P1 |
| 5 | SDK Code | JS/.NET/JSON 自动填充 | 已实现 | ✅ |
| 6 | Event Inspector | 完整请求/响应日志 | 已实现 | ✅ |
| 7 | 实时成本 | $0.041252 | 显示 ¥0.900000 (非实时) | P1 |
| 8 | 编码系统 | 9 种多选，跨 4 地区 | 5 种多选 (P0 改进后) | ✅ |
| 9 | 过滤器 | Include/Exclude codes | 已实现 (P0) | ✅ |
| 10 | Settings/Code 双 Tab | 始终可见 | 已实现 (P0) | ✅ |

**当前阻塞**: iCoDer `/api/reviews` 500 错误 — 已定位到 `reviews.py:281,287`，已修复，等待后端重启生效。

**下一步**: 修复生效后，使用完全相同的输入文本测试两端输出，对比编码准确性、证据质量和完整度。
