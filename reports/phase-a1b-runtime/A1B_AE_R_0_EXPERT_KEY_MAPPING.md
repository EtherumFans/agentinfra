# A1B-AE-R.0 — Expert Key Mapping (Corti §3.2 ↔ iCoDer ↔ Pack ↔ Preset)

**Sub-gate**: A1B-AE-R.0
**Captured at**: 2026-07-22T12:55:56Z
**Source**: `backend/agent_catalog/expert_catalog.json` (A1B-AE.2) + `backend/agent_catalog/icoder_preset_agents.json` (A1B-AE.8) + `backend/app/services/expert_registry.py` + `backend/app/models/expert.py`

---

## §1. Mapping table

9 个 Corti 公开 §3.2 Expert keys 映射到 iCoDer `canonical_key` + Pack slug + Preset Agent 引用 + A1B-AE-R 升级路径。

| # | Corti §3.2 key | iCoDer canonical_key | iCoDer 服务/模块 | Pack slug | 被引用的 Preset | A1B-AE tier | R 升级路径 |
|---|---|---|---|---|---|---|---|
| 1 | `memory` | `memory` / `memory-expert` | `backend/app/services/memory_expert.py` | (无 Pack,服务级) | medical-coding / cdi / drg-dip / intake-interview / claim-check(auxiliary) | CORTI_REFERENCE(lexical) | **R.4 升级**:已有 sentence-transformers 语义搜索(`memory_expert.py:8-22`),接到真实 Context persistence |
| 2 | `coding` | `coding-expert` | `backend/app/icoder/agent_runtime/experts/coding_expert.py` | `icoder/medical-coding-agent@2.0.0` | medical-coding(primary) / drg-dip / claim-check | CORTI_ALIGNED | **R.4 保持**:wrapper 正确 delegate 到 Pack |
| 3 | `medical-calculator` | `medical-calculator` / `medical-calculator-expert` | `backend/app/services/expert_runner.py` (无独立服务) | (无 Pack) | medical-coding / drg-dip(auxiliary) | CORTI_ADAPTED | **R.4 升级**:扩目录到 BMI + Cockcroft-Gault + CHADS₂-VASc + MELD-Na + eGFR (CKD-EPI 2021) + Wells DVT(全部确定性,不调 LLM) |
| 4 | `drugbank` | `drugbank-expert` | (无服务,licence-gated stub) | (无 Pack) | (无 preset 直接引用) | CORTI_REFERENCE | **R.3 保持**:LICENCE_REQUIRED,无授权不联网 |
| 5 | `posos` | `posos-expert` | (无服务,licence-gated stub) | (无 Pack) | (无 preset 直接引用) | CORTI_REFERENCE | **R.3 保持**:LICENCE_REQUIRED |
| 6 | `web-search` | `web-search-expert` | (无服务,policy-gated stub) | (无 Pack) | (无 preset) | CORTI_REFERENCE | **R.3 保持**:default-off,显式 `feature_flag=web_search_enabled` 才开启 |
| 7 | `pubmed` | `pubmed` / `pubmed-expert` | (无服务,offline stub) | (无 Pack) | cdi / claim-check(auxiliary) | CORTI_REFERENCE(offline) | **R.3 升级**:真实 EUtils API,VCR fixture,deny=0 egress |
| 8 | `clinical-trials` | `clinical-trials` / `clinical-trials-expert` | (无服务,offline stub) | (无 Pack) | cdi / claim-check(auxiliary) | CORTI_REFERENCE(offline) | **R.3 升级**:真实 clinicaltrials.gov v2 API,VCR fixture,deny=0 egress |
| 9 | `interviewing` | `interviewing-expert` | `backend/app/icoder/agent_runtime/cdi/cdi_expert_router.py`(部分) | (无 Pack) | intake-interview(primary) / cdi(auxiliary) | CORTI_ALIGNED(schema-driven) | **R.4 升级**:可恢复状态机(state 持久化到 `contexts.metadata_json` 或独立表) |

---

## §2. Preset Agent 引用图

5 个 iCoDer Preset Agents(`icoder_preset_agents.json`)及其 Expert 引用 + Pack delegate:

| Preset canonical_key | delegates_to_pack | corti_alignment | 引用的 Experts (role) | R.2 动作 |
|---|---|---|---|---|
| `icoder-medical-coding-preset` | `icoder/medical-coding-agent@2.0.0` | CORTI_ALIGNED | coding-expert(primary) / medical-calculator / memory(auxiliary) | 已有 Pack,**保持** |
| `icoder-cdi-preset` | `null` ❌ | CORTI_ADAPTED | interviewing / memory / pubmed / clinical-trials | **R.2 建 cdi Pack**(薄壳,包装 `cdi_expert_router.py`),set delegates |
| `icoder-drg-dip-preset` | `null` ❌ | CORTI_ADAPTED | coding-expert / medical-calculator / memory | **R.2 建 drg-dip Pack**(基于 `drg-analyzer` + DIP rules),set delegates |
| `icoder-intake-interview-preset` | `null` ❌ | CORTI_ALIGNED | interviewing(primary) / memory | **R.2 建 intake-interview Pack**(薄壳,包装 interviewing service) |
| `icoder-claim-check-preset` | `null` ❌ | CORTI_ADAPTED | coding-expert / memory / pubmed / clinical-trials | **R.2 建 claim-check Pack**(薄壳,包装 external-gate + Insurance Audit rule_set) |

R.2 完成后:5/5 Preset 都有 `delegates_to_pack` 非 null。

---

## §3. Dual-named legacy orphans

3 个 Pack 目录同时存在 underscore form 和 dash form(version shadowing 根因):

| Underscore dir(legacy) | Dash dir(canonical) | 处理 |
|---|---|---|
| `backend/official_agents/code_validation/` | `backend/official_agents/code-validation/` | R.2 删除 underscore form,migrate call site |
| `backend/official_agents/compliance_guardrail/` | `backend/official_agents/compliance-guardrail/` | 同上 |
| `backend/official_agents/note_completeness/` | `backend/official_agents/note-completeness/` | 同上 |

Canonical 规则:**dash form 胜出**(matches Corti 公开 convention + Pack metadata 较新版本 + `seed.py` key form)。Underscore form 在 A1B-AE.4 AliasResolver 下被 alias 到 dash form。

R.2 在删除前必须 grep:
```bash
grep -rn 'code_validation\|compliance_guardrail\|note_completeness' backend/app/
```
任何 importer / seed reference 必须先迁移到 dash form,再 `rm -rf` underscore 目录。

---

## §4. MCP server wiring(R.3 范围)

5 个 Preset 的 `mcp_servers` 字段当前全部为空 `[]`:

| Preset | mcp_servers | R.3 动作 |
|---|---|---|
| icoder-medical-coding-preset | `[]` | R.3 wire 内部 `icoder/mcp` server(tools/list + tools/call),让 medical-coding-agent 可以用 search_codes / verify_code / rerank_codes 等 handler |
| icoder-cdi-preset | `[]` | R.3 wire pubmed_expert + clinical_trials_expert 作为 MCP-style tool |
| icoder-drg-dip-preset | `[]` | R.3 可选 wire calculator MCP |
| icoder-intake-interview-preset | `[]` | (no MCP needed) |
| icoder-claim-check-preset | `[]` | R.3 wire pubmed_expert + clinical_trials_expert |

---

## §5. Corti alignment 聚合(R.0 baseline)

```
2  CORTI_ALIGNED     (coding-expert / interviewing)
1  CORTI_ADAPTED     (medical-calculator)
6  CORTI_REFERENCE   (memory / drugbank / posos / web-search / pubmed / clinical-trials)
```

R 终态期望(R.6 终态对齐):

```
5  CORTI_ALIGNED     (coding / interviewing / memory / pubmed / clinical-trials)
1  CORTI_ADAPTED     (medical-calculator — 目录扩充但仍是 iCoDer 内部)
3  CORTI_REFERENCE   (drugbank / posos / web-search — 保持 licence/policy gated)
```

即便 R.6 达到这个分布,**global Corti parity verdict 仍保持 NOT_DEMONSTRATED**(A1A-owned,Charter §3 明确 out-of-scope)。

---

## §6. 参考文件

- `backend/agent_catalog/expert_catalog.json` — A1B-AE.2 canonical Expert catalog(40 entries)
- `backend/agent_catalog/icoder_preset_agents.json` — A1B-AE.8 preset catalog(5 entries)
- `backend/agent_catalog/agent_catalog.json` — A1B-AE.2 canonical Agent catalog(29 entries)
- `backend/app/models/expert.py` — Expert ORM + `EXPERT_ORIGIN_VALUES` / `EXPERT_CORTI_ALIGNMENT_VALUES` / `MCP_AUTHORIZATION_TYPE_VALUES` 枚举
- `backend/app/services/expert_registry.py` — ExpertRegistry service
- `backend/app/api/experts.py` — A1B-AE.3 REST surface(`/api/v1/experts/*`)
- `backend/app/services/preset_agents.py` — A1B-AE.8 Preset service + `corti_agent_card()` emitter
- `reports/phase-a1b/A1B_AE_3_EXPERT_REGISTRY.md` — A1B-AE.3 Expert Registry provenance layer 报告
- `reports/phase-a1b/A1B_AE_8_ICODER_PRESET_AGENTS.md` — A1B-AE.8 Preset Agents 报告
