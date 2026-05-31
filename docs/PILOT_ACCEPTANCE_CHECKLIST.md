# Pilot Acceptance Checklist

**版本**: v1.0-pilot
**日期**: 2026-05-12
**用途**: 医院试点验收标准检查清单
**通过条件**: 全部 MUST 项通过，SHOULD 项 ≤ 2 项不通过

---

## 验收说明

- 标记 `[MUST]` 的项为必须通过项，任一项不通过则整体验收不通过
- 标记 `[SHOULD]` 的项为建议通过项，≤ 2 项不通过可接受
- 每个检查项由验收方 (医院方/实施方) 逐项确认并签字

---

## 1. 环境启动验收

| # | 检查项 | 优先级 | 验收方法 | 通过标准 | 结果 |
|---|--------|--------|---------|---------|------|
| 1.1 | 后端服务可启动 | MUST | 执行 `uvicorn app.main:app --host 0.0.0.0 --port 8000` | 服务监听 8000 端口，无 crash | ☐ |
| 1.2 | 前端服务可启动 | MUST | 执行 `npm run dev` | 服务监听 5173 端口，页面可访问 | ☐ |
| 1.3 | 数据库连接正常 | MUST | `GET /api/health` 返回 200 | `{"status": "ok", "database": "connected"}` | ☐ |
| 1.4 | 种子数据可导入 | MUST | 执行 `python -m app.seed` | 输出确认 10 demo cases + 10 gold cases 导入成功 | ☐ |
| 1.5 | 浏览器可正常渲染页面 | MUST | 访问 `http://localhost:5173` | 页面无白屏、无 JS 报错 | ☐ |
| 1.6 | 登录功能正常 | MUST | 输入任意 demo 账号登录 | 跳转至首页，侧边栏显示完整菜单 | ☐ |

---

## 2. 数据导入验收

| # | 检查项 | 优先级 | 验收方法 | 通过标准 | 结果 |
|---|--------|--------|---------|---------|------|
| 2.1 | Encounter 数据导入 | MUST | `GET /api/encounters?page=1&page_size=10` | 返回 ≥ 10 条 encounter 记录，含 encounter_id 和 department | ☐ |
| 2.2 | Gold Case 数据导入 | MUST | `GET /api/gold-cases` | 返回 10 条 gold case，含 gold_diagnosis_codes 和 gold_procedure_codes | ☐ |
| 2.3 | 编码字典可用 | MUST | `GET /api/codes/icd10/search?q=Z51` | 返回 Z51.x 相关 ICD-10 编码列表 | ☐ |
| 2.4 | 编码规则可加载 | SHOULD | `GET /api/codes/rules?category=diagnosis` | 返回非空规则列表 | ☐ |
| 2.5 | 病历文书字段完整 | SHOULD | 检查 DEMO-001 encounter 详情 | 含 admission_record, progress_notes, discharge_summary 等字段 | ☐ |

---

## 3. 编码审核流程验收

| # | 检查项 | 优先级 | 验收方法 | 通过标准 | 结果 |
|---|--------|--------|---------|---------|------|
| 3.1 | 可发起 Coding Review | MUST | POST `/api/reviews` `{"encounter_id": "DEMO-001"}` | 返回 200，含 review_id | ☐ |
| 3.2 | Pipeline 完整执行 | MUST | 等待 review 完成，检查返回数据 | 返回含 diagnosis_candidates, procedure_candidates, evidence, report_markdown, drg_impact | ☐ |
| 3.3 | Evidence 证据链非空 | MUST | 检查 review 返回的 evidence 字段 | diagnosis_facts 或 procedure_facts 至少一个非空 | ☐ |
| 3.4 | Coding Candidates 合法 | MUST | 检查 review 返回的 diagnosis_candidates | 每个 candidate 含 code, name, confidence, rule_valid | ☐ |
| 3.5 | DRG 影响分析存在 | SHOULD | 检查 review 返回的 drg_impact | 包含 expected_drg 或 grouped_drg 字段 | ☐ |
| 3.6 | Report 可生成 | MUST | 检查 review 返回的 report_markdown | 非空字符串，≥ 100 字符 | ☐ |
| 3.7 | 异步模式 + WebSocket 进度 | SHOULD | POST review 时传 async_mode=true，通过 WS 接收进度 | 收到 ≥ 3 条进度消息 | ☐ |
| 3.8 | 编码工作台 UI 可展示结果 | MUST | CodingWorkbenchPage 选择 DEMO-001 并 Run Review | Evidence/Candidates/Report/DRG/Audit 5 个 tab 均有内容 | ☐ |

---

## 4. Runtime 审计验收

| # | 检查项 | 优先级 | 验收方法 | 通过标准 | 结果 |
|---|--------|--------|---------|---------|------|
| 4.1 | 状态流转记录完整 | MUST | `GET /api/runtime/audit/{pipeline_id}` | events 包含全部状态转换 (INGESTED → … → ARCHIVED) | ☐ |
| 4.2 | Guard 结果可查询 | MUST | `GET /api/runtime/summary/{review_id}` | guard_outcomes 含 ALLOW/REVIEW/DENY 计数 | ☐ |
| 4.3 | 审计事件时间有序 | SHOULD | 检查审计事件列表 | 事件 timestamp 严格递增 | ☐ |
| 4.4 | 非法状态转换被拒绝 | MUST | 模拟非法状态转换请求 | 返回 400/403，审计记录包含 DENY 事件 | ☐ |
| 4.5 | DUC 操作需人工确认 | SHOULD | 触发 writeback_to_emr 操作 | 返回 REVIEW 要求，等待 human_confirm | ☐ |
| 4.6 | Timeout 自动升级 | SHOULD | 设置 REVIEW_REQUIRED 状态超过 4h 超时 | 自动转为 ESCALATED 状态 | ☐ |
| 4.7 | 高风险输出被拦截 | MUST | 提交含"处方"关键词的输出 | 返回 DENY，不通过 guard_post | ☐ |
| 4.8 | Audit tab 前端可展示 | MUST | CodingWorkbenchPage → Audit tab | 5 个子面板均有数据 | ☐ |

---

## 5. 人工复核验收

| # | 检查项 | 优先级 | 验收方法 | 通过标准 | 结果 |
|---|--------|--------|---------|---------|------|
| 5.1 | 可进入 CaseReviewPage | MUST | CodingWorkbenchPage 点击 Human Review 按钮 | 跳转至 CaseReviewPage，展示编码候选列表 | ☐ |
| 5.2 | 可确认编码候选 | MUST | 对某个 candidate 点击 Confirm | candidate 状态变更为 confirmed | ☐ |
| 5.3 | 可拒绝编码候选 | MUST | 对某个 candidate 点击 Reject | candidate 状态变更为 rejected | ☐ |
| 5.4 | 可修正编码 | MUST | 对某个 candidate 点击 Modify，输入新编码 | candidate 状态变更为 modified，记录修正后编码 | ☐ |
| 5.5 | Decision Summary 更新 | SHOULD | 完成多个 Confirm/Reject/Modify 操作 | Shield 面板显示 correct 的总决策数、通过数、拒绝数 | ☐ |
| 5.6 | 复核后 Audit 更新 | SHOULD | 完成复核后查看 Audit tab | 新增 human_confirm 相关审计事件 | ☐ |

---

## 6. Evaluation 验收

| # | 检查项 | 优先级 | 验收方法 | 通过标准 | 结果 |
|---|--------|--------|---------|---------|------|
| 6.1 | Evaluation 可运行 | MUST | `POST /api/evaluation/run` | 返回 200，含 per_case_results 列表 | ☐ |
| 6.2 | 主要诊断准确率达标 | MUST | 检查 primary_diag_accuracy | ≥ 0.5 (baseline) | ☐ |
| 6.3 | Hallucination 率达标 | MUST | 检查 hallucination_rate | ≤ 0.3 (baseline) | ☐ |
| 6.4 | Evidence 完整度达标 | MUST | 检查 evidence_completeness_avg | ≥ 0.5 (baseline) | ☐ |
| 6.5 | 每病例均有评估结果 | MUST | 检查 per_case_results | 10 个 demo case 全有结果 | ☐ |
| 6.6 | EvaluationPage 前端可展示 | SHOULD | 导航到 EvaluationPage | 展示评估指标卡片 + 每病例结果表 | ☐ |

---

## 7. 异常处理验收

| # | 检查项 | 优先级 | 验收方法 | 通过标准 | 结果 |
|---|--------|--------|---------|---------|------|
| 7.1 | 不存在的 encounter 请求 | MUST | POST review 传 `encounter_id: "NOTEXIST"` | 返回 404，错误信息清晰 | ☐ |
| 7.2 | 空数据请求 | MUST | POST review 传空的 encounter_data | 返回 422 或 400，错误信息清晰 | ☐ |
| 7.3 | 重复运行不污染数据 | SHOULD | 对同一 DEMO-001 连续运行 3 次 review | 每次生成新的 review_id，不覆盖历史记录 | ☐ |
| 7.4 | 后端重启后数据不丢失 | MUST | 重启后端，再次查询 encounter/gold-cases | 数据完整，与重启前一致 | ☐ |
| 7.5 | 并发请求不崩溃 | SHOULD | 同时提交 3 个不同 encounter 的 review | 3 个请求均正常完成，互不影响 | ☐ |

---

## 8. 不通过判定标准

以下情况判定为验收不通过:

| # | 不通过条件 | 说明 |
|---|-----------|------|
| 8.1 | 任一项 [MUST] 检查不通过 | 必须项为系统基本功能，不通过则无法进入试点 |
| 8.2 | [SHOULD] 项不通过 > 2 项 | 超过 2 项建议项不通过表示系统质量不足 |
| 8.3 | 后端服务无法启动或频繁 crash | 稳定性不满足试点要求 |
| 8.4 | Coding Review Pipeline 无法完成 | 核心业务能力不可用 |
| 8.5 | 安全护栏失效 (guard_post 未拦截高风险输出) | 安全风险不可接受 |
| 8.6 | 数据丢失 (重启后数据不可恢复) | 数据可靠性不满足 |

---

## 验收结论

| 项目 | 结果 |
|------|------|
| MUST 项总数 | 20 |
| MUST 通过数 | ___ |
| SHOULD 项总数 | 11 |
| SHOULD 通过数 | ___ |
| **验收结论** | ☐ 通过 / ☐ 不通过 |

---

**验收方签字**:

| 角色 | 姓名 | 签名 | 日期 |
|------|------|------|------|
| 医院方代表 | | | |
| 实施方代表 | | | |

---

**附件**: 验收过程中产生的截图、API 响应记录、异常记录
