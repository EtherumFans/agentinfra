# Fresh Corti Re-gate — Reviewer Pack (Phase A1E-GP2 prep)

> **状态**: PARTIAL_FRESH_REGATE_REVIEWER_PACK_PREPARED_FILED (NOT a re-gate result)
> **日期**: 2026-08-08
> **目的**: 准备 fresh Corti re-gate 所需证据与上下文, 供独立人类 reviewer 接手执行
> **Charter 引用**: §Gate 7 final clause — Codex 不能 self-substitute 独立人类验收

---

## 0. 本文件能做什么 / 不能做什么

**能做 (Codex 已 prepare)**:
- 汇总当前 iCoDer 状态 + 4 个 sprint commits + Corti 源引用
- 列出 21/24 charter §十七 conditions DONE + 3 BLK-1 blocked
- 列出 5 个 Corti 对比解禁前提 + 当前状态
- 提供 reviewer checklist

**不能做 (Charter §Gate 7 明令禁止)**:
- 执行 fresh Corti re-gate 重跑
- 自称 PROVEN_SUPERIOR_KEEP / CORTI_PARITY_DEMONSTRATED
- 替代独立人类 reviewer 做判定

---

## 1. iCoDer 当前状态 snapshot (2026-08-08)

| 字段 | 值 |
|---|---|
| Git 分支 | `phase-a1a/emergency-containment` (NEVER pushed) |
| HEAD commit | `4f914a8` (audit/pilot-prep: A1D.7 KMS rotation) |
| Base commit | `e8c115e` (G10-002 agent_pack model id consolidation) |
| 5-tuple | GATE4_8_NO_NEW_REGRESSION=NOT_MUTATED, GATE4_9_FINAL_PASS=NOT_MUTATED, GATE4_ACCEPTANCE=REOPENED, CORTI_PARITY=NOT_DEMONSTRATED, PRODUCTION_READINESS=NOT_VERIFIED |
| Verdict (当前) | CORTI_PARITY=NOT_DEMONSTRATED (per A1A Gate 4R-I + R1+R2) |
| Corti live 浏览器 | BLOCKED (无法登录 corti.ai 验证 — A1E-GP1 memory) |

### 1.1 4 个 sprint commits 汇总

| Commit | 主题 | 文件 | 关键交付 |
|---|---|---|---|
| `1ff7973` | A1E Sprint 2 Developer Golden Path | 16 (+2738/-70) | Goals A-F: templates + DB-pack fallback + 14-field envelope + rotate/disable UI + Code Tab SDK + external-agent-consumer script |
| `b70c7ba` | A1E.7 run-agent.mjs live-verify 4-fix | 1 (+29/-13) | arg parser / OAuth scope / payload shape / output_preview — caught by real DeepSeek dry-run |
| `6d29d52` | A1E.8 NewAgentPage + ErrorBoundary logging | 2 (+21/-8) | dev-mode error stack disclosure + Array.isArray defense |
| `4f914a8` | A1D.7 KMS rotation admin endpoint | 4 (+325/-1) | global token wiring + POST /api/admin/kms/rotate + audit row + 6 tests |

### 1.2 Live verification 状态 (real DeepSeek `sk-***3ff4924`)

| 验证项 | 结果 | 证据 |
|---|---|---|
| Verify-1 (Generic Agent via REST) | PASS | model=`deepseek-v4-flash`, latency=1.8s, output=`今天天气很好。` |
| Verify-2 (External Consumer script) | PASS | node run-agent.mjs --mode rest 端到端, real translation `使用真实的DeepSeek进行外部消费者验证。` |
| Verify-3 (Browser UX Goals A/C/D/E) | PASS | templates API + Test Console 14-field + Rotate/Disable + Code Tab canonical SDK |
| Browser New Agent page | DIAGNOSIS-FILED | 不能复现; dev-mode error disclosure 已加 (commit 6d29d52) |

---

## 2. Corti 源引用 (reference baseline)

| 资源 | 路径 / 来源 | 状态 |
|---|---|---|
| Corti 官方文档 | `docs/corti-reverse-engineered/docs-site/_extracted/` | 19 files (per A1A Gate 4R-I memory) |
| Corti agent 源码 reverse-engineered | `docs/corti-reverse-engineered/` (top-level .md) | codes-predict-codes.md 等 |
| Corti safety page | corti.ai/safety (R1 added verbatim per ICODER-CORTI-AGENT-DEV-GAP-01 memory) | FIPS AES + per-customer keys + Azure AD + DRATA + HIPAA/GDPR/SOC2/ISO27001 |
| Corti live 浏览器访问 | BLOCKED | 5-min token TTL + Cloudflare bot detection (A1E-GP1 memory BLK-1) |
| Corti 评测数据 | 无 (iCoDer 不持有 Corti 评测数据, 不能跨厂商比较 — R2 memory) | — |

### 2.1 Corti 不能访问的影响

- 0 PROVEN_SUPERIOR_KEEP claims (cannot claim iCoDer feature > Corti without Corti evidence)
- A2A timing comparison 引用 A1D.5R 数据 (iCoDer 4.77s vs Corti 3.88s), but Corti timing 是历史抓取, 不是 fresh
- A1E-GP1 10×3×3 capability matrix 需独立 reviewer 在 Corti 浏览器在场时执行 (currently BLK-1)

---

## 3. Charter §十七 conditions 状态 (per A1E-GP1 memory)

| # | Condition | 状态 | 备注 |
|---|---|---|---|
| 1-7 | 工程层 (templates, runtime, pack format, etc.) | DONE | Sprint 2 commit 1ff7973 |
| 8-14 | 测试覆盖 (9/9 new + 86/86 regression) | DONE | Sprint 2 commit 1ff7973 |
| 15-20 | 集成层 (SDK, Code Tab, external consumer) | DONE | Sprint 2 commits 1ff7973+b70c7ba |
| 21 | Live DeepSeek verify | DONE | Verify-1/2/3 (本会话, commit b70c7ba) |
| 22 | Browser UX Goals A/C/D/E | DONE | Verify-3 (本会话, commit b70c7ba) |
| 23 | ErrorBoundary 诊断能力 | DONE | commit 6d29d52 |
| 24 | KMS rotation operator hook | DONE | commit 4f914a8 |
| 25 | 独立人类 reviewer 验收 | **BLK-1 BLOCKED** | Charter §Gate 7: Codex 不能 self-substitute |
| 26 | Corti live 浏览器对照 | **BLK-1 BLOCKED** | Corti 访问受限 |
| 27 | 双语 100-case 评测 | **PARTIAL** | 仅 5-case seed (held_out_bilingual_v1.json) |

总计: 24/27 conditions DONE (89%), 3 BLK-1/PARTIAL blocked on 独立 reviewer + Corti 访问 + 双语集扩充.

---

## 4. Corti 对比解禁 5 前提 (per R2 memory EVALUATION_CITATION_POLICY.md §2 rule 3)

| # | 前提 | 当前状态 | 阻塞 |
|---|---|---|---|
| 1 | 双语评测集 ≥100 cases | 5/100 (held_out_bilingual_v1.json) | Phase A 合成 5→30, Phase B MIMIC-IV 30→60, Phase C Pilot 医院 60→100+ (per HELD_OUT_BILINGUAL_EVALUATION_STRATEGY.md) |
| 2 | 双语 gold standard | 未启动 | 需医学双语专家人工标注 |
| 3 | 同 LLM 跑双语 | 工程就绪 (LLMGateway 支持), 缺评测数据 | 依赖 #1+#2 |
| 4 | 独立 reviewer | 未指派 | Charter §Gate 7 强制 |
| 5 | Pilot 医院反馈 | 未启动 | Pilot 上线后 30-90 天 |

**结论**: 5/5 前提都未满足. Corti 对比目前仍然 DEFERRED. 本 reviewer pack 不是 Corti 对比结果.

---

## 5. Reviewer Checklist (独立人类 reviewer 接手时执行)

### 5.1 接手前确认 (reviewer self-check)

- [ ] 我是独立 reviewer (未参与 iCoDer 这 4 个 commits 的开发)
- [ ] 我有 corti.ai 有效账号 (或同等 Corti 访问途径)
- [ ] 我读过 Charter §Gate 7 + §十七
- [ ] 我读过 EVALUATION_CITATION_POLICY.md 5 规则
- [ ] 我读过 HELD_OUT_BILINGUAL_EVALUATION_STRATEGY.md 三阶段

### 5.2 证据审计 (review 4 commits)

- [ ] `1ff7973` Sprint 2 9/9 新测试 + 86/86 回归 PASS — 复跑 `pytest tests/test_api/test_sprint2_developer_golden_path.py`
- [ ] `b70c7ba` run-agent.mjs 4-fix 与 live verify 一致 — 复跑 `node examples/external-agent-consumer/run-agent.mjs --mode rest`
- [ ] `6d29d52` ErrorBoundary dev-mode disclosure 生效 — 在 dev env 故意触发 render error, 看 stack
- [ ] `4f914a8` KMS rotation 6 测试 PASS + audit row 写入 — 复跑 `pytest tests/test_api/test_a1d_7_kms_rotation_endpoint.py`

### 5.3 Capability matrix (需 Corti live 浏览器在场)

按 A1E-GP1 memory: 10×3×3 matrix (10 capabilities × 3 iCoDer agent types × 3 Corti agent types).
- [ ] 登录 corti.ai
- [ ] 对每个 capability, 在 iCoDer 与 Corti 同时执行相同 input
- [ ] 记录双方输出 + latency + cost
- [ ] 标记 PROVEN_SUPERIOR_KEEP / TIE / PROVEN_INFERIOR
- [ ] **禁忌**: 任何一方失败时不能给 PROVEN_SUPERIOR_KEEP

### 5.4 双语评测集扩充 (需医学双语专家)

- [ ] Phase A 合成: 5→30 cases (UpToDate / 黃沙醫療科全書 / 中華人民共和國衛生部臨床路徑)
- [ ] Phase B MIMIC-IV: 30→60 cases (需 MIMIC-IV access)
- [ ] Phase C Pilot 医院: 60→100+ cases (需 Pilot 上线)
- [ ] 同 LLM (DeepSeek) 跑双语 (iCoDer 中文 / Corti 英文)
- [ ] Wilson 区间半宽 ≈ 0.05 验证

### 5.5 最终判定 (reviewer 签字)

reviewer 在完成 5.1-5.4 后, 给出三选一:

- [ ] `PASS_FRESH_REGATE_VERIFIED` — 24+ conditions 全 DONE + capability matrix 没有压倒性 PROVEN_INFERIOR + 双语 100-case 通过 Wilson 区间
- [ ] `PARTIAL_FRESH_REGATE_*_FILED` — 部分 condition 仍 blocked, 列出具体 BLK
- [ ] `FAIL_FRESH_REGATE_*` — capability matrix 显示压倒性 PROVEN_INFERIOR 或 critical regression

**reviewer 签字栏** (留空):
```
Reviewer name:        ____________________________________
Reviewer affiliation: ____________________________________
Date:                 ____________________________________
Verdict:              ____________________________________
Conditions DONE:      ___ / 27
Capability matrix:    PROVEN_SUPERIOR ___ / TIE ___ / PROVEN_INFERIOR ___
Bilingual 100-case:   PASS ___ / PARTIAL ___ / FAIL ___
Notes:                ____________________________________
```

---

## 6. 本 pack 的局限性 (诚实声明)

1. **不是 Corti 对比结果** — 0 PROVEN_SUPERIOR_KEEP, 0 PROVEN_INFERIOR, 0 TIE claims.
2. **不能升级 verdict** — 当前 CORTI_PARITY=NOT_DEMONSTRATED 不变, 直到 reviewer 完成签字.
3. **不替代 reviewer** — Codex 不能 self-substitute (Charter §Gate 7 final clause, per A1E-GP1 memory).
4. **依赖外部资源** — Corti 账号 + MIMIC-IV access + 医学双语专家 + Pilot 医院, 都超出 Codex 工程范围.
5. **可能过时** — 任何后续 commit 都可能让本 pack 的 evidence 失效; reviewer 应基于 pack HEAD `4f914a8` + 任何后续 commit 一起审.

---

## 7. 引用

- Charter §Gate 7 + §十七 (项目章程, 不在 repo)
- `MEMORY.md` → `project_a1e_sprint2_2026_08_07.md` (Sprint 2 + A1E.7 live verify)
- `MEMORY.md` → `project_a1e_gp1_2026_07_30.md` (10×3×3 capability matrix + BLK-1)
- `MEMORY.md` → `project_icoder_corti_agent_dev_gap_2026_07_29.md` (12-sub-gate G.0..G.11)
- `docs/governance/EVALUATION_CITATION_POLICY.md` (5 规则)
- `docs/governance/HELD_OUT_BILINGUAL_EVALUATION_STRATEGY.md` (三阶段 5→100)
- `backend/tests/fixtures/held_out_bilingual_v1.json` (5-case seed)
- `docs/corti_parity/P1_3_CORTI_PARITY_AUDIT_FINAL_REPORT.md` (2026-07-02 baseline)
- `docs/corti_parity/CORTI_PARITY_GAP_ANALYSIS.md`
- 4 commits: `1ff7973` `b70c7ba` `6d29d52` `4f914a8`
