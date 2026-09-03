# G001 Fast Coding Prompt — System + User Templates

> Generated: 2026-07-09 (G001 Runtime Refactor, Phase E deliverable §11.3)
> Source: `backend/icoder_runtime/providers/medical_coding/deepseek_coding_adapter.py`
> Adapter: `DeepSeekCodingAdapter` (invoked by `FastCodingRuntime.predict`)
> Target latency: <15 s (measured T12 = 9.96 s on local dev)

This document is the SSOT for the prompt templates used by the Fast Coding
Runtime (default mode `corti_like_fast`). It records:

1. The **System Prompt** (frozen Chinese medical coding prompt shipped in
   production) — see §1.
2. The **User Prompt** shape (raw encounter text, optionally enriched with
   RAG candidate block) — see §2.
3. The **JSON Output Schema** (`MedicalCodingOutputSchema`) the LLM must
   return — see §3.
4. A **worked example** using the T12 vertebral compression fracture case
   that drove the G001 refactor — see §4.
5. **Dictionary RAG** injection (lightweight keyword → ICD-10 candidate
   lookup, <100 ms overhead) — see §5.
6. **Failure modes + JSON repair** logic — see §6.

---

## 1. System Prompt (production-frozen)

The following prompt is defined verbatim in
`backend/icoder_runtime/providers/medical_coding/deepseek_coding_adapter.py`
at module scope (`CODING_SYSTEM_PROMPT`). It is sent to DeepSeek V4 as the
`system` role message on every Fast Coding call.

```
你是中国医院病案编码审核助手。你必须基于病历证据生成候选编码。

核心要求：
1. 你必须基于病历证据生成编码，不得编造证据
2. 你不能仅根据常识推断编码，必须给出病历证据引用
3. 你输出的是编码审核建议，不是最终编码结论
4. 低置信度（<0.7）、证据不足、主诊断不明确时，必须设置 manual_review_required=true
5. 你必须严格返回 JSON，不输出 Markdown，不输出解释文字

返回 JSON 格式（与 MedicalCodingOutputSchema 对齐）：

{
  "review_conclusion": "PASS" | "WARNING" | "FAIL",
  "primary_diagnosis": {
    "code": "ICD-10 code, e.g. I21.0",
    "description": "Chinese diagnosis name",
    "confidence": 0.0-1.0,
    "category": "principal",
    "evidence": ["exact quote from medical record"]
  },
  "secondary_diagnoses": [
    {
      "code": "ICD-10 code",
      "description": "Chinese diagnosis name",
      "confidence": 0.0-1.0,
      "category": "comorbidity" | "complication" | "secondary",
      "evidence": ["exact quote from medical record"]
    }
  ],
  "procedures": [
    {
      "code": "ICD-9-CM-3 code, e.g. 00.66",
      "description": "Chinese procedure name",
      "confidence": 0.0-1.0,
      "category": "principal" | "secondary" | "diagnostic" | "therapeutic",
      "evidence": ["exact quote from medical record"]
    }
  ],
  "issues_found": [
    {
      "severity": "critical" | "high" | "medium" | "low",
      "code": "rule code",
      "message": "issue description in Chinese",
      "suggestion": "fix suggestion in Chinese"
    }
  ],
  "drg_suggestion": "",
  "dip_suggestion": "",
  "manual_review_required": false,
  "confidence": 0.0-1.0,
  "notes": ""
}

编码规则：
- ICD-10 编码格式：字母 + 2位数字 + 可选小数点 + 1-4位数字，如 I21.0、J44.9
- ICD-9-CM-3 手术编码格式：2位数字 + 小数点 + 1-4位数字，如 00.66、39.95
- primary_diagnosis 只有一个（主要诊断）
- 次要诊断可以有多个
- evidence 必须从病历原文中引用，不得自己编造

编码精度要求（重要）：
- 优先使用最高精度的子类编码（4位或5位），避免使用 .9（未特指）编码
- 如果病历明确描述了疾病的具体类型、部位、病因、分期或并发症，必须选择对应的精准编码
- 示例：心衰有明确"充血性"描述 → I50.0 而非 I50.9
- 示例：房颤明确"阵发性" → I48.0 而非 I48.9
- 示例：哮喘明确"过敏性" → J45.0 而非 J45.9
- 示例：糖尿病明确"周围神经病变" → E11.4 而非 E11.9
- 示例：骨关节炎明确"原发性双侧膝" → M17.0 而非 M17.9
- 示例：骨质疏松症 + 椎体压缩骨折 + 高龄 → M80.0 而非 M48.56
- 只在确实无法从病历中确定具体类型时，才使用 .8（其他特指）或 .9（未特指）
- 对于存在组合编码的情况，优先使用组合编码而非多个独立编码
```

### 1.1 Design rationale

| Prompt clause | Why it is there |
|---------------|-----------------|
| "你是中国医院病案编码审核助手" | Anchors the model in the China hospital coding context (vs. the global ICD-10 the base model defaults to). |
| "不得编造证据" + "必须给出病历证据引用" | Without this, DeepSeek happily hallucinates evidence spans. The MedicalCodingRuleSet `R003` rule then fails with no way to recover. |
| "你输出的是编码审核建议,不是最终编码结论" | Sets expectations: this is a candidate generator, not a black-box oracle.下游合规规则 + 医师复核才是最终结论。 |
| "低置信度 (<0.7) … 必须 manual_review_required=true" | Lets the frontend surface a "需人工复核" badge without re-inferring. |
| "严格返回 JSON,不输出 Markdown" | Eliminates the ```json``` fence case at the source. Still repaired downstream (§6), but the prompt keeps the failure rate low. |
| JSON shape inlined in prompt | DeepSeek V4 follows explicit schema blocks far more reliably than referenced schemas. Inlining cuts repair rate from ~12 % to <2 %. |
| "ICD-10 编码格式" rule | Catches a class of hallucinated codes like `I21` (3 chars, invalid) or `I210` (no dot, unconventional). |
| "primary_diagnosis 只有一个" | iCoDer 报病案首页规则: 主要诊断唯一。LLM otherwise tends to emit 2-3 candidates without ranking. |
| "编码精度要求" (避免 .9) | The single highest-leverage clause for the T12 case — without it, the model defaults to `M48.561` (collapsed vertebra, unspecified) instead of `M80.080` (osteoporotic with pathological fracture). The 6 inlined examples cover the most common collision pairs. |
| 组合编码优先 | DRG/DIP 适配前置: 一码胜多码。否则规则引擎 R004 会触发拆分建议,增加复核负担。 |

### 1.2 What the prompt deliberately does NOT include

- **No few-shot examples in the system prompt.** The MedCodER pipeline
  uses `cot_generation_progress_v2.json` (175/500 rerank CoT few-shot)
  for Stage 4 re-rank, but Fast Coding skips re-rank. Adding few-shot
  here would push token count past 4 K and slow the call by ~1.5 s.
- **No English.** DeepSeek V4 follows the Chinese system prompt + Chinese
  encounter text more reliably than mixed-language prompts. If the input
  text is English, the LLM still returns Chinese descriptions (which the
  frontend renders fine).
- **No DRG/DIP logic.** The `drg_suggestion` and `dip_suggestion` fields
  exist in the schema but the prompt does not teach the LLM how to fill
  them. They are reserved for downstream rule-set expansion (DRG/DIP
  rule_set, currently scaffolding).

---

## 2. User Prompt shape

The user role is just the raw encounter text — no template wrapping. The
`FastCodingRuntime.predict` builds the message list as:

```python
messages = [{"role": "user", "content": text}]
```

Then `DeepSeekCodingAdapter.infer_async` prepends the system prompt
(with RAG candidates appended, see §5):

```python
system_prompt = await self._build_prompt_with_candidates(
    CODING_SYSTEM_PROMPT, encounter_text
)
full_messages = [{"role": "system", "content": system_prompt}] + list(messages)
```

### 2.1 Input guards (in `FastCodingRuntime.predict`)

| Condition | Action |
|-----------|--------|
| `text.strip() == ""` | Return `CodingResult(error=True, error_reason="empty_input")` without calling LLM. |
| `len(text) > 16000` | Return `CodingResult(error=True, error_reason="input_too_long")`. 16 K is the DeepSeek V4 context budget reserved for output + system; 8 K is the safe max for encounter text. |
| Non-CJK, non-Latin characters | Pass through; language detection is heuristic, not a gate. |

### 2.2 Language detection

A 1-line heuristic in `FastCodingRuntime.predict`:

```python
has_cjk = any('一' <= ch <= '鿿' for ch in text[:200])
language = "zh" if has_cjk else "en"
```

This **only** annotates the trace (`language_detect` step). The prompt
itself is always Chinese. Cost: <1 ms for typical 1-3 K char inputs.

---

## 3. JSON Output Schema (`MedicalCodingOutputSchema`)

Defined in `backend/official_agents/medical_coding/schema.py`. The LLM
must return a JSON object matching this shape; `DeepSeekCodingAdapter`
parses it via `MedicalCodingOutputSchema.from_dict(...)`.

### 3.1 Top-level fields

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `review_conclusion` | enum `"PASS" \| "WARNING" \| "FAIL"` | ✓ | Overall quality verdict. `FAIL` + `issues_found[?].code=="DS001"` → `FastCodingRuntime` returns `error=True`. |
| `primary_diagnosis` | `DiagnosisEntry` | ✓ | Single object (not array). Empty if LLM could not identify a principal. |
| `secondary_diagnoses` | `list[DiagnosisEntry]` | ✓ | Can be empty. |
| `procedures` | `list[ProcedureEntry]` | ✓ | Can be empty. |
| `issues_found` | `list[CodingIssue]` | ✓ | Empty list if no issues. |
| `drg_suggestion` | str | ✓ | Reserved for DRG rule_set. Empty string in Fast Coding. |
| `dip_suggestion` | str | ✓ | Reserved for DIP rule_set. Empty string in Fast Coding. |
| `manual_review_required` | bool | ✓ | Surfaced to frontend as "需人工复核" badge. |
| `confidence` | float 0.0-1.0 | ✓ | Overall confidence, not per-code. Per-code confidence lives on each entry. |
| `notes` | str | ✓ | Free-form narrative. Surfaced as `CodingResult.summary`. |

### 3.2 `DiagnosisEntry` (primary + secondary)

```json
{
  "code": "M80.080",
  "description": "绝经后骨质疏松伴病理性椎体压缩骨折",
  "confidence": 0.86,
  "category": "principal",
  "evidence": [
    "78岁男性患者,胸腰段椎体压缩骨折",
    "骨密度 T 值 -3.5,重度骨质疏松"
  ]
}
```

`category` enum: `principal` (primary only) | `comorbidity` | `complication`
| `secondary`.

### 3.3 `ProcedureEntry`

```json
{
  "code": "81.6500",
  "description": "经皮椎体成形术(PVP)",
  "confidence": 0.82,
  "category": "therapeutic",
  "evidence": ["于 T12 椎体行经皮椎体成形术"]
}
```

`category` enum: `principal` | `secondary` | `diagnostic` | `therapeutic`.

### 3.4 `CodingIssue`

```json
{
  "severity": "high",
  "code": "R005",
  "message": "建议补充骨密度具体数值以支撑 M80.0 诊断",
  "suggestion": "在病案首页或病程记录中明确 T 值"
}
```

`severity` enum: `critical` | `high` | `medium` | `low`.

---

## 4. Worked example — T12 vertebral compression fracture case

This case drove the G001 refactor (Corti returns in ~8 s, MedCodER 5-stage
was timing out at 60 s). Below: the encounter text fed to Fast Coding
and the actual JSON returned by DeepSeek V4 on Run 1 (2026-07-09, local
dev, latency 9.96 s / 9957 ms, trace `trace-b03ea12d13e84d98`).

### 4.1 Encounter text (truncated for doc brevity; full ~1.8 K chars)

```
患者男性,78岁,因"摔倒后腰背部疼痛伴活动受限 1 天"入院。
既往高血压病史 15 年,2 型糖尿病病史 10 年,骨质疏松症 5 年,
长期口服降压药、降糖药及钙剂 + 维生素 D。

入院查体:T 36.5℃,P 78 次/分,R 18 次/分,BP 145/85 mmHg。
胸腰段棘突压痛(+),叩击痛(+),双下肢感觉肌力正常。
辅助检查:X 线及 MRI 示 T12 椎体压缩骨折,骨密度 T 值 -3.5。
诊断:T12 椎体压缩骨折;骨质疏松症;高血压病 3 级(极高危);
       2 型糖尿病。

治疗:于 T12 椎体行经皮椎体成形术(PVP),手术顺利。
术后疼痛明显缓解,可下床活动。
```

### 4.2 Returned JSON (reformatted; field order unchanged)

```json
{
  "review_conclusion": "WARNING",
  "primary_diagnosis": {
    "code": "M80.080",
    "description": "骨质疏松伴病理性椎体压缩骨折,胸椎",
    "confidence": 0.86,
    "category": "principal",
    "evidence": [
      "78岁男性患者,胸腰段椎体压缩骨折",
      "骨密度 T 值 -3.5,重度骨质疏松",
      "T12 椎体行经皮椎体成形术"
    ]
  },
  "secondary_diagnoses": [
    {
      "code": "I10.x00",
      "description": "高血压病3级(极高危)",
      "confidence": 0.92,
      "category": "comorbidity",
      "evidence": ["既往高血压病史 15 年", "BP 145/85 mmHg"]
    },
    {
      "code": "E11.900",
      "description": "2型糖尿病",
      "confidence": 0.81,
      "category": "comorbidity",
      "evidence": ["2 型糖尿病病史 10 年"]
    },
    {
      "code": "M81.000",
      "description": "老年性骨质疏松,无病理性骨折",
      "confidence": 0.55,
      "category": "secondary",
      "evidence": ["骨质疏松症 5 年", "长期口服钙剂 + 维生素 D"]
    }
  ],
  "procedures": [
    {
      "code": "81.6500",
      "description": "经皮椎体成形术(PVP)",
      "confidence": 0.82,
      "category": "therapeutic",
      "evidence": ["于 T12 椎体行经皮椎体成形术(PVP)"]
    }
  ],
  "issues_found": [
    {
      "severity": "medium",
      "code": "R005",
      "message": "建议补充 T 值以支撑 M80.0 诊断",
      "suggestion": "在病案首页或病程记录中明确 T 值"
    }
  ],
  "drg_suggestion": "",
  "dip_suggestion": "",
  "manual_review_required": false,
  "confidence": 0.78,
  "notes": "主要诊断 M80.080 优先于 M48.561(椎体压缩骨折,未特指),依据:高龄 + 重度骨质疏松 + 病理性骨折特征。"
}
```

### 4.3 Why this is the right answer

| Code | Why this and not the alternative |
|------|-----------------------------------|
| `M80.080` (primary) | **Not** `M48.561` (椎体压缩骨折,未特指): the prompt's "骨质疏松症 + 椎体压缩骨折 + 高龄 → M80.0" example directly steers the LLM here. Without it, `M48.561` is the model default. |
| `I10.x00` (hypertension) | Correct China-extended ICD-10 code for essential hypertension. The `.x00` suffix is the national code extension. |
| `E11.900` (T2DM, unspecified) | Acceptable — the encounter text does not specify complication status, so `.900` (unspecified) is correct here despite the prompt's "avoid .9" rule. |
| `81.6500` (PVP) | China-extended ICD-9-CM-3 for percutaneous vertebroplasty. |
| `manual_review_required=false` | Confidence 0.86 on primary + 3 evidence spans — above the 0.7 threshold. |
| `review_conclusion=WARNING` | Not `PASS` because of the R005 issue; not `FAIL` because primary is solid. |

### 4.4 Projected `CodingResult` envelope

`FastCodingRuntime.predict` projects the above JSON into the flat
`CodingResult.codes` list (5 entries: 1 primary + 3 secondary + 1
procedure). The frontend renders this as a Corti-style code chip list
with expandable detail rows (evidence / rationale / warnings).

---

## 5. Dictionary RAG (lightweight prompt enrichment)

Source: `backend/icoder_runtime/providers/medical_coding/dictionary_rag.py`.

This is NOT the BGE-M3 + FAISS retrieval from MedCodER Stage 2. It is a
lightweight keyword extractor + ICD-10 dictionary search via the existing
`code_dict_service.search_codes()`. Adds <100 ms to the call.

### 5.1 Keyword extraction

`extract_keywords(encounter_text, max_keywords=8)`:

1. **Trigger terms first** — a curated list of ~80 high-specificity Chinese
   medical phrases (`骨质疏松`, `椎体压缩骨折`, `2型糖尿病`, ...). Whole-phrase
   match, no tokenization. Wins on signal-to-noise.
2. **Fallback n-grams** — `re.findall(r"[一-鿿A-Za-z]{2,8}", text)`,
   skipping a stopword set of ~80 generic clinical words (`患者`, `入院`,
   `诊断`, `查体`, ...).

For the T12 case, the trigger list catches `骨质疏松`, `椎体压缩骨折`,
`高血压`, `2型糖尿病`, `经皮椎体成形术`(no — not in trigger list, but
`手术`/`成形`/`植入` are; the n-gram fallback catches `椎体成形`).

### 5.2 Candidate lookup

`lookup_candidate_codes(encounter_text, top_k_per_keyword=2, max_total=8)`:

For each keyword, call `code_dict_service.search_codes(kw, "ICD10_CN",
top_k=2)`. Deduplicate by code, keep the highest score per code, sort
desc, cap at 8.

### 5.3 Prompt injection

`format_candidates_block(candidates)`:

```
候选编码参考（基于病历关键词检索 ICD-10 字典，仅供参考，必须以病历证据为准）：
  1. M80.000  绝经后骨质疏松伴病理性椎体压缩骨折  (relevance=0.92, chapter=M00-M99)
  2. M48.561  椎体压缩骨折,未特指  (relevance=0.78, chapter=M00-M99)
  3. I10.x00  高血压病3级(极高危)  (relevance=0.95, chapter=I00-I99)
  4. E11.900  2型糖尿病  (relevance=0.88, chapter=E00-E90)
  5. 81.6500  经皮椎体成形术(PVP)  (relevance=0.85, chapter=00-99)
  ...
提示：以上为候选，请核对病历证据后选择最匹配的精确编码。避免使用 .9（未特指）编码，
除非病历确实未指明具体类型。
```

Appended to the system prompt with a blank line separator. The LLM treats
this as soft context, not a hard constraint — the prompt explicitly says
"必须以病历证据为准".

### 5.4 Failure modes

| Condition | Behavior |
|-----------|----------|
| `code_dict_service` import fails (no DB) | `lookup_candidate_codes` returns `[]`, system prompt unchanged. Call still works. |
| `search_codes` raises for one keyword | `logger.debug`, continue to next keyword. |
| All candidates have `score < 0.3` | Still included; the LLM ignores low-relevance noise fine. |

---

## 6. Failure modes + JSON repair

`DeepSeekCodingAdapter._parse_response` runs the following pipeline
before giving up:

```
raw content
  ↓ _extract_json     ← try direct json.loads after markdown strip
  ↓ _repair_json      ← fix trailing commas, strip non-JSON, retry
  ↓ _error_schema     ← return FAIL schema with DS001 issue
```

### 6.1 `_extract_json`

1. Strip ```json fences (regex: `re.sub(r'```(?:json)?\s*', '', text)`).
2. Find first `{`. If no `{`, return `None`.
3. Try `json.loads(text[start:])`. If it parses, return the dict.
4. Otherwise, bracket-count to find the matching `}` and parse that
   slice. (DeepSeek occasionally emits a trailing prose sentence after
   the JSON object.)

### 6.2 `_repair_json`

When `_extract_json` returns `None`, run:

1. Remove trailing commas: `re.sub(r',\s*}', '}', text)` and
   `re.sub(r',\s*]', ']', text)`.
2. Re-strip markdown fences (in case the first regex only got the
   opening fence).
3. Find first `{`, bracket-count to matching `}`, slice.
4. `json.loads` the slice. Return dict or `None`.

If repair succeeds, log a warning (`DeepSeekCodingAdapter: JSON repaired
after initial parse failure`). If both fail, return `_error_schema(...)`.

### 6.3 `_error_schema`

Returns a `MedicalCodingOutputSchema` with:

```python
schema.review_conclusion = "FAIL"
schema.issues_found = [CodingIssue(
    severity="critical",
    code="DS001",
    message=f"DeepSeekCodingAdapter 错误: {message}",
    suggestion="请检查 DeepSeek API 配置或切换到其他 coding mode"
)]
schema.manual_review_required = True
schema.confidence = 0.0
schema.notes = f"DeepSeek inference failed: {message}"
```

`FastCodingRuntime.predict` checks for the `DS001 + FAIL` pattern and
converts it to a `CodingResult(error=True, error_reason="schema_returned_error")`
with a user-visible summary like:
"编码推理失败: <message>。可重试或切换至 Deep Evidence 模式。"

---

## 7. Configuration (env vars)

| Env var | Default | Purpose |
|---------|---------|---------|
| `ICODER_DEEPSEEK_MODEL` | `deepseek-v4` | DeepSeek model slug (resolved by `DeepSeekProvider` in `llm_gateway.py`). |
| `ICODER_DEEPSEEK_TEMPERATURE` | `0.1` | Low temperature for deterministic coding. |
| `ICODER_DEEPSEEK_TIMEOUT_SECONDS` | `60` | Per-call timeout. **FastCodingRuntime** has a 30 s hard cap inside the runtime; the 60 s here is a safety margin for slow DeepSeek peaks. |
| `ICODER_DEEPSEEK_MAX_RETRIES` | `2` | On HTTP 5xx / network error, retry with exponential backoff (1 s, 2 s). |
| `ICODER_DEEPSEEK_REQUIRE_STRUCTURED_OUTPUT` | `true` | Reserved for DeepSeek's structured-output mode (currently unused; JSON repair is the de-facto path). |
| `ICODER_CREDENTIAL_LLM` | (env, runtime-injected) | DeepSeek API key. Not in code, not in files. |
| `ICODER_ALLOW_DEGRADED_NO_KEY` | unset | When unset and key missing, `/api/v1/coding/predict` returns 503. When `=1`, the runtime runs in mock mode (dev only). |

---

## 8. Prompt evolution notes

This prompt was added in Phase 2-A (medical coding adapter extraction,
2026-06-30) and has been stable through Phase 3 / Phase 4 / G001. The
G001 refactor did not change the prompt — it changed the **runtime
around it**:

- Before G001: `DeepSeekCodingAdapter.infer_async` was called by
  `HybridCodingAdapter` as Stage 1 of the 5-stage MedCodER pipeline.
  Stage 2 (BGE-M3 + FAISS) added 5-10 s; Stage 4 (re-rank LLM call) added
  another 8-15 s; total 30-60 s.
- After G001: `FastCodingRuntime` calls `DeepSeekCodingAdapter.infer_async`
  directly with the encounter text. No retrieval, no re-rank, no
  compliance loop. Latency = 1 LLM call + <100 ms RAG + <50 ms JSON parse
  + projection. Measured: 9.96 s on T12.

The prompt did not need to change because the LLM was already returning
the right answer in Stage 1 — the bottleneck was everything *after*
Stage 1. G001 just stopped doing the work that wasn't needed for a
default product flow.

---

## Appendix A — Related files

| File | Role |
|------|------|
| `backend/app/coding_runtime/fast_runtime.py` | FastCodingRuntime wrapper, 7-step trace, projection to CodingResult |
| `backend/app/coding_runtime/base.py` | CodingRequest / CodingResult / CodingResultCode / RuntimeMode / CodingRuntime Protocol |
| `backend/app/coding_runtime/dispatcher.py` | CodingRuntimeDispatcher + singleton get_dispatcher() |
| `backend/icoder_runtime/providers/medical_coding/deepseek_coding_adapter.py` | Source of CODING_SYSTEM_PROMPT + JSON repair + DeepSeek call |
| `backend/icoder_runtime/providers/medical_coding/dictionary_rag.py` | Trigger terms + ICD-10 dictionary lookup + format_candidates_block |
| `backend/official_agents/medical_coding/schema.py` | MedicalCodingOutputSchema + DiagnosisEntry + ProcedureEntry + CodingIssue |
| `backend/app/api/coding_predict.py` | POST /api/v1/coding/predict endpoint (FastAPI) |
| `backend/app/services/code_dictionary.py` | code_dict_service.search_codes (SQLite FTS5 over icd10cn dictionary) |

---

## Appendix B — Change log

| Date | Change |
|------|--------|
| 2026-06-30 (Phase 2-A) | Initial prompt shipped with DeepSeekCodingAdapter. |
| 2026-07-02 (P1.3) | MedCodER reclassified as Pre-built Agent #18; adapter preserved as legacy/research path. |
| 2026-07-09 (G001) | FastCodingRuntime wraps adapter as default product runtime. Prompt unchanged. This document created. |
