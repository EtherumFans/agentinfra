# iCoDer Medical Coding Backend Decoupling Plan

**Document type:** Concrete decoupling plan (Part B)
**Date:** 2026-07-07
**Authors:** SONG Luhua
**Parent doc:** `ICODER_AGENT_BACKEND_COMPATIBILITY_ARCHITECTURE.md` (Item 10)

## 1. Goal

Unbundle the Medical Coding Agent from its current hard-wired `HybridCodingAdapter` / `MedCodERRetrievalRuleSet` coupling, so it can switch between rule-based, LLM-based, and hybrid backends via `backend_provider` in `agent_pack.json` — without regressing the F1 baseline.

**F1 baseline invariant:** `python scripts/e2e_runtime_validation.py --base-url http://localhost:8000` must produce F1 ≥ current baseline (per-case micro-F1 over primary + secondary dx, subdivision-tolerant: I50.900 ≡ I50.9 ≡ I50.x00).

## 2. Current state

### 2.1 Code structure (pre-decoupling)

```
backend/app/icoder/agents/medical_coding/
├── runtime_endpoint.py          # MedicalCodingRuntimeEndpoint (HTTP layer)
├── hybrid_adapter.py            # HybridCodingAdapter (5-stage pipeline, hardcoded)
├── medcoder_retrieval_ruleset.py  # MedCodERRetrievalRuleSet (rule-based Stage 5)
├── icd10cn_catalog.py           # 37,897-code catalog
└── ...

backend/app/icoder/agents/medical_coding/hybrid_adapter.py:
class HybridCodingAdapter:
    async def infer_async(self, req: CodingRequest, mode: str = "medcoder") -> CodingResult:
        if mode == "prompt":
            return await self._stage1_extract_only(req)  # LLM only
        elif mode == "retrieve":
            return await self._stage2_retrieve_only(req)  # RAG only
        elif mode == "prompt+retrieve":
            return await self._stage1_plus_2(req)  # LLM + RAG, no rerank
        elif mode == "medcoder":
            return await self._full_5_stage(req)  # all 5 stages
        elif mode == "hybrid":
            return await self._hybrid_with_rule_check(req)  # 5-stage + rule validation
```

### 2.2 Issues with current state

1. **No `backend_provider` field** in `medical_coding/agent_pack.json` — backend is implicit
2. **Hardcoded mode switching** — `mode="medcoder"|"hybrid"|"prompt"` is a runtime parameter, not declarative
3. **5-stage pipeline not exposed as MCP tools** — each stage is a private Python method
4. **Cannot swap LLM without code changes** — DeepSeek V4 is hardcoded in `LLMGateway`
5. **Cannot use cached provider** — no cache layer between `MedicalCodingRuntimeEndpoint` and `HybridCodingAdapter`
6. **No fallback chain** — if DeepSeek is down, the agent fails (no rule-engine fallback)
7. **RunTrace doesn't capture per-stage events** — stages 1-5 are opaque to the trace viewer
8. **Test variants require code changes** — `scripts/e2e_medcoder_validation.py --variant full|prompt|retrieve|prompt+retrieve` switches mode via flag, not via agent pack

## 3. Target state (post-decoupling)

### 3.1 Code structure (post-decoupling)

```
backend/app/icoder/backends/medcoder/
├── __init__.py
├── extract_tool.py              # MCP tool: icoder_medcoder_extract (Stage 1)
├── retrieve_tool.py             # MCP tool: icoder_medcoder_retrieve (Stage 2)
├── merge_tool.py                # MCP tool: icoder_medcoder_merge (Stage 3)
├── rerank_tool.py               # MCP tool: icoder_medcoder_rerank (Stage 4)
├── compliance_tool.py           # MCP tool: icoder_medcoder_compliance (Stage 5)
├── rule_engine_provider.py      # MedCodERRuleEngineProvider (Stage 2+5 only)
├── llm_with_tools_provider.py   # MedCodERLLMWithToolsProvider (full 5-stage via tools)
├── hybrid_provider.py           # MedCodERHybridProvider (rule-first + LLM-summary)
└── medcoder_output_contract.py  # MedicalCodingOutputContract

backend/app/icoder/agents/medical_coding/
├── runtime_endpoint.py          # MedicalCodingRuntimeEndpoint (delegates to AgentRunner)
└── ...                          # (hybrid_adapter.py DELETED — stages extracted to backends/medcoder/)

backend/official_agents/medical_coding/agent_pack.json:
{
  "schema_version": "1.2",
  "agent": {
    "name": "Medical Coding Agent",
    "backend_provider": "icoder.hybrid.medcoder.v1",
    "backend_config": {
      "rule_provider": "icoder.rule-engine.medcoder.v1",
      "llm_provider": "icoder.llm-with-tools.medcoder.v1",
      "merge_strategy": "rule_first_llm_summarize"
    },
    ...
  }
}
```

### 3.2 Behavioral contract (post-decoupling)

| Mode (legacy) | `backend_provider` (new) | Behavior |
|---------------|--------------------------|----------|
| `mode=prompt` (Stage 1 only) | `icoder.llm-with-tools.medcoder.v1` with `tools.scope=[extract]` | LLM extraction only, no RAG |
| `mode=retrieve` (Stage 2 only) | `icoder.rule-engine.medcoder.v1` with `tools.scope=[retrieve, compliance]` | RAG + rule check, no LLM |
| `mode=prompt+retrieve` (Stages 1+2, no rerank) | `icoder.llm-with-tools.medcoder.v1` with `tools.scope=[extract, retrieve, merge, compliance]` (no rerank) | LLM + RAG, no rerank |
| `mode=medcoder` (full 5-stage) | `icoder.llm-with-tools.medcoder.v1` with `tools.scope=[extract, retrieve, merge, rerank, compliance]` | Full 5-stage pipeline |
| `mode=hybrid` (5-stage + rule validation) | `icoder.hybrid.medcoder.v1` (default) | Rule-first + LLM-summary |

The `mode=` parameter is **deprecated**; `backend_provider` + `backend_config.tools.scope` replaces it declaratively.

## 4. Migration steps (concrete file changes)

### Step 1 — Extract Stage 1 (Extraction) to MCP tool

**New file:** `backend/app/icoder/backends/medcoder/extract_tool.py`

```python
from mcp.server import MCPTool
from icoder_runtime.mcp.tool_registry import register_tool

@register_tool(
    name="icoder_medcoder_extract",
    description="Stage 1 of MedCodER pipeline — extract diagnoses from EMR text using LLM",
    input_schema={
        "type": "object",
        "properties": {
            "emr_text": {"type": "string"},
            "encounter_context": {"type": "object"}
        },
        "required": ["emr_text"]
    }
)
class MedCoderExtractTool(MCPTool):
    def __init__(self, llm: LLMClient):
        self.llm = llm

    async def call(self, args: dict, ctx: AgentRunContext) -> dict:
        # Move HybridCodingAdapter._stage1_extract_only() body here
        prompt = build_extraction_prompt(args["emr_text"], args.get("encounter_context"))
        response = await self.llm.complete(prompt, temperature=0.0)
        diagnoses = parse_extraction_response(response)
        return {
            "diagnoses": [{"disease": d.name, "evidence": d.evidence, "llm_initial_code": d.code} for d in diagnoses],
            "raw_response": response
        }
```

**Migration action:**
- Move `HybridCodingAdapter._stage1_extract_only()` body to `MedCoderExtractTool.call()`
- Replace `rapidfuzz` sentence-span snapping with `redacted_view`-aware span computation (PHI redaction at boundary)
- Add tool to `MCPToolRegistry` at startup

### Step 2 — Extract Stage 2 (Retrieval) to MCP tool

**New file:** `backend/app/icoder/backends/medcoder/retrieve_tool.py`

```python
@register_tool(
    name="icoder_medcoder_retrieve",
    description="Stage 2 of MedCodER pipeline — BGE-M3 embed + FAISS top-20 retrieval",
    input_schema={
        "type": "object",
        "properties": {
            "diagnoses": {"type": "array"},
            "top_k": {"type": "integer", "default": 20}
        },
        "required": ["diagnoses"]
    }
)
class MedCoderRetrieveTool(MCPTool):
    def __init__(self, embedder: BGEM3Embedder, faiss_index: FAISSIndex, catalog: ICD10Catalog):
        self.embedder = embedder
        self.faiss = faiss_index
        self.catalog = catalog

    async def call(self, args: dict, ctx: AgentRunContext) -> dict:
        # Move HybridCodingAdapter._stage2_retrieve_only() body here
        candidates = []
        for dx in args["diagnoses"]:
            synonyms = expand_synonyms(dx["disease"])
            embeddings = await self.embedder.embed_batch(synonyms)
            top_indices = await self.faiss.search(embeddings, top_k=args["top_k"])
            for idx in top_indices:
                code = self.catalog.get(idx)
                candidates.append({
                    "code": code.icd10,
                    "description": code.description,
                    "similarity": float(top_indices[idx]),
                    "source": "retrieval"
                })
        return {"candidates": candidates}
```

**Migration action:**
- Move `HybridCodingAdapter._stage2_retrieve_only()` body to `MedCoderRetrieveTool.call()`
- Lazy-load `data/medcoder/models/` + `data/medcoder/faiss.index` on first call (existing pattern)
- Add tool to `MCPToolRegistry`

### Step 3 — Extract Stage 3 (Merge) to MCP tool

**New file:** `backend/app/icoder/backends/medcoder/merge_tool.py`

```python
@register_tool(
    name="icoder_medcoder_merge",
    description="Stage 3 of MedCodER pipeline — merge LLM codes + retrieved candidates, cap 30, inject differentiation hints",
    input_schema={
        "type": "object",
        "properties": {
            "llm_diagnoses": {"type": "array"},
            "retrieved_candidates": {"type": "array"}
        },
        "required": ["llm_diagnoses", "retrieved_candidates"]
    }
)
class MedCoderMergeTool(MCPTool):
    def __init__(self, diff_kb: CodingDifferentiationKB):
        self.diff_kb = diff_kb

    async def call(self, args: dict, ctx: AgentRunContext) -> dict:
        # Move HybridCodingAdapter._stage3_merge() body here
        merged = merge_and_dedupe(args["llm_diagnoses"], args["retrieved_candidates"], cap=30)
        for dx in merged:
            dx["differentiation_hints"] = self.diff_kb.get_hints(dx["code"])
        return {"candidate_set": merged}
```

**Migration action:**
- Move `HybridCodingAdapter._stage3_merge()` body to `MedCoderMergeTool.call()`
- Lazy-load `coding_differentiation_kb.json` (existing pattern)
- Add tool to `MCPToolRegistry`

### Step 4 — Extract Stage 4 (Re-rank) to MCP tool

**New file:** `backend/app/icoder/backends/medcoder/rerank_tool.py`

```python
@register_tool(
    name="icoder_medcoder_rerank",
    description="Stage 4 of MedCodER pipeline — RankGPT-style LLM re-rank with few-shot CoT",
    input_schema={
        "type": "object",
        "properties": {
            "candidate_set": {"type": "array"},
            "few_shot_examples": {"type": "array"}
        },
        "required": ["candidate_set"]
    }
)
class MedCoderRerankTool(MCPTool):
    def __init__(self, llm: LLMClient, few_shot_kb: CotGenerationProgress):
        self.llm = llm
        self.few_shot_kb = few_shot_kb

    async def call(self, args: dict, ctx: AgentRunContext) -> dict:
        # Move HybridCodingAdapter._stage4_rerank() body here
        prompt = build_rerank_prompt(args["candidate_set"], self.few_shot_kb.get_examples())
        response = await self.llm.complete(prompt, temperature=0.0)
        ranked = parse_rerank_response(response, args["candidate_set"])
        return {
            "ranked_diagnoses": [{"code": d.code, "confidence": d.confidence, "evidence": d.evidence} for d in ranked[:5]]
        }
```

**Migration action:**
- Move `HybridCodingAdapter._stage4_rerank()` body to `MedCoderRerankTool.call()`
- Lazy-load `cot_generation_progress_v2.json` (existing pattern)
- Add tool to `MCPToolRegistry`

### Step 5 — Extract Stage 5 (Compliance + Calibration) to MCP tool

**New file:** `backend/app/icoder/backends/medcoder/compliance_tool.py`

```python
@register_tool(
    name="icoder_medcoder_compliance",
    description="Stage 5 of MedCodER pipeline — MedCodERRetrievalRuleSet + per-diagnosis calibration",
    input_schema={
        "type": "object",
        "properties": {
            "ranked_diagnoses": {"type": "array"}
        },
        "required": ["ranked_diagnoses"]
    }
)
class MedCoderComplianceTool(MCPTool):
    def __init__(self, rule_set: MedCodERRetrievalRuleSet):
        self.rule_set = rule_set

    async def call(self, args: dict, ctx: AgentRunContext) -> dict:
        # Move HybridCodingAdapter._stage5_compliance() body here
        verdicts = await self.rule_set.evaluate(args["ranked_diagnoses"])
        calibrated = apply_per_diagnosis_calibration(verdicts)
        return {
            "final_diagnoses": [{"code": d.code, "confidence": d.confidence, "verdict": d.verdict} for d in calibrated]
        }
```

**Migration action:**
- Move `HybridCodingAdapter._stage5_compliance()` body to `MedCoderComplianceTool.call()`
- Add tool to `MCPToolRegistry`

### Step 6 — Implement `MedCodERRuleEngineProvider`

**New file:** `backend/app/icoder/backends/medcoder/rule_engine_provider.py`

```python
class MedCodERRuleEngineProvider:
    """Stage 2 + Stage 5 only — no LLM. For 'retrieve' mode."""
    provider_id = "icoder.rule-engine.medcoder.v1"
    backend_type = "rule_engine"
    supports_tool_calling = True  # calls retrieve + compliance MCP tools
    supports_streaming = False
    deterministic = True

    def __init__(self, retrieve_tool: MedCoderRetrieveTool, compliance_tool: MedCoderComplianceTool):
        self.retrieve_tool = retrieve_tool
        self.compliance_tool = compliance_tool

    async def invoke(self, req, ctx):
        # Stage 2
        retrieved = await self.retrieve_tool.call({"diagnoses": req.input.diagnoses}, ctx)
        # Stage 5 (no rerank — direct to compliance)
        verdicts = await self.compliance_tool.call({"ranked_diagnoses": retrieved["candidates"]}, ctx)
        return BackendResponse(
            status="complete",
            summary="Rule-engine retrieval + compliance",
            issues=[],
            raw={"final_diagnoses": verdicts["final_diagnoses"]},
            finish_state="completed",
            latency_ms=...
        )

    def output_contract(self):
        return MedicalCodingOutputContract
```

**Migration action:**
- Register in `ProviderRegistry` at startup
- Implement `output_contract()` returning `MedicalCodingOutputContract`

### Step 7 — Implement `MedCodERLLMWithToolsProvider`

**New file:** `backend/app/icoder/backends/medcoder/llm_with_tools_provider.py`

```python
class MedCodERLLMWithToolsProvider:
    """Full 5-stage pipeline via MCP tools. For 'medcoder' mode."""
    provider_id = "icoder.llm-with-tools.medcoder.v1"
    backend_type = "llm_with_tools"
    supports_tool_calling = True
    supports_streaming = True
    deterministic = False

    def __init__(self, llm: LLMClient, mcp: ToolMCPCompatLayer):
        self.llm = llm
        self.mcp = mcp

    async def stream(self, req, ctx):
        # Stage 1
        extract_resp = await self.mcp.call({"name": "icoder_medcoder_extract", "args": {"emr_text": req.input.emr_text}}, ctx)
        yield RunTraceEvent(step=6, name="tool_calls", payload={"tool": "extract", "result": extract_resp})
        # Stage 2
        retrieve_resp = await self.mcp.call({"name": "icoder_medcoder_retrieve", "args": {"diagnoses": extract_resp["diagnoses"]}}, ctx)
        yield RunTraceEvent(step=6, name="tool_calls", payload={"tool": "retrieve", "result": retrieve_resp})
        # Stage 3
        merge_resp = await self.mcp.call({"name": "icoder_medcoder_merge", "args": {"llm_diagnoses": extract_resp["diagnoses"], "retrieved_candidates": retrieve_resp["candidates"]}}, ctx)
        yield RunTraceEvent(step=6, name="tool_calls", payload={"tool": "merge", "result": merge_resp})
        # Stage 4
        rerank_resp = await self.mcp.call({"name": "icoder_medcoder_rerank", "args": {"candidate_set": merge_resp["candidate_set"]}}, ctx)
        yield RunTraceEvent(step=6, name="tool_calls", payload={"tool": "rerank", "result": rerank_resp})
        # Stage 5
        compliance_resp = await self.mcp.call({"name": "icoder_medcoder_compliance", "args": {"ranked_diagnoses": rerank_resp["ranked_diagnoses"]}}, ctx)
        yield RunTraceEvent(step=6, name="tool_calls", payload={"tool": "compliance", "result": compliance_resp})
        # Output
        yield RunTraceEvent(step=7, name="output_normalized", payload=compliance_resp)
        yield RunTraceEvent(step=9, name="finished", payload={"state": "completed"})

    def output_contract(self):
        return MedicalCodingOutputContract
```

**Migration action:**
- Register in `ProviderRegistry`
- Add `backend_config.tools.scope` enforcement — e.g., `prompt` mode has scope `[extract]`, `medcoder` mode has scope `[extract, retrieve, merge, rerank, compliance]`

### Step 8 — Implement `MedCodERHybridProvider`

**New file:** `backend/app/icoder/backends/medcoder/hybrid_provider.py`

```python
class MedCodERHybridProvider:
    """Default — rule engine drives code assignment, LLM summarizes."""
    provider_id = "icoder.hybrid.medcoder.v1"
    backend_type = "hybrid"
    supports_tool_calling = True
    supports_streaming = True
    deterministic = False

    def __init__(self, rule: MedCodERRuleEngineProvider, llm: MedCodERLLMWithToolsProvider):
        self.rule = rule
        self.llm = llm

    async def invoke(self, req, ctx):
        # Rule engine first (Stage 2 + 5) — preserves F1
        rule_resp = await self.rule.invoke(req, ctx)
        # LLM summarizes (Stage 1 + 3 + 4) — explainability
        llm_req = req.with_extra_context({"rule_verdict": rule_resp.raw})
        llm_resp = await self.llm.invoke(llm_req, ctx)
        return self._merge(rule_resp, llm_resp)

    def _merge(self, rule_resp, llm_resp):
        # Rule wins on code assignment; LLM wins on summary
        return BackendResponse(
            status="complete",
            summary=llm_resp.summary,
            issues=rule_resp.issues + llm_resp.issues,
            raw={
                "final_diagnoses": rule_resp.raw["final_diagnoses"],
                "llm_summary": llm_resp.raw
            },
            finish_state="completed"
        )
```

**Migration action:**
- Register in `ProviderRegistry`
- Implement merge strategy with rule-wins-on-codes, LLM-wins-on-summary policy

### Step 9 — Update `medical_coding/agent_pack.json`

**Modified file:** `backend/official_agents/medical_coding/agent_pack.json`

```json
{
  "schema_version": "1.2",
  "agent": {
    "name": "Medical Coding Agent",
    "version": "1.3.0",
    "backend_provider": "icoder.hybrid.medcoder.v1",
    "backend_config": {
      "rule_provider": "icoder.rule-engine.medcoder.v1",
      "llm_provider": "icoder.llm-with-tools.medcoder.v1",
      "merge_strategy": "rule_first_llm_summarize",
      "llm": {
        "provider": "deepseek",
        "model": "deepseek-v4-flash",
        "temperature": 0.0
      },
      "tools": {
        "scope": ["icoder_medcoder_extract", "icoder_medcoder_retrieve", "icoder_medcoder_merge", "icoder_medcoder_rerank", "icoder_medcoder_compliance"],
        "mandatory": [],
        "forbidden": []
      }
    },
    "experts": [{"name": "coding-expert", "type": "reference"}],
    "system_prompt": "...",
    "output_contract": "icoder.contracts.MedicalCodingOutputContract"
  }
}
```

### Step 10 — Update `MedicalCodingRuntimeEndpoint`

**Modified file:** `backend/app/icoder/agents/medical_coding/runtime_endpoint.py`

```python
@router.post("/v2/tools/coding")
async def code_endpoint(req: CodingRequest, ctx: AgentRunContext = Depends(...):
    # OLD: result = await hybrid_adapter.infer_async(req, mode=req.mode or "medcoder")
    # NEW: delegate to AgentRunner
    output = await agent_runner.run(
        BackendRequest(input=req),
        agent_id="medical-coding-agent",
        ctx=ctx
    )
    return project_to_v2_response(output)  # existing v2 schema
```

**Migration action:**
- Delete hardcoded `HybridCodingAdapter` import
- Delegate to `AgentRunner.run()` (which resolves `backend_provider` from agent pack)
- Keep `project_to_v2_response()` for backwards compat with frontend

### Step 11 — Delete `hybrid_adapter.py`

**Deleted file:** `backend/app/icoder/agents/medical_coding/hybrid_adapter.py`

After all 5 stages are extracted to MCP tools (Steps 1-5) and providers route through them (Steps 6-8), the `HybridCodingAdapter` class is fully superseded. Delete it.

### Step 12 — Update `scripts/e2e_medcoder_validation.py`

**Modified file:** `backend/scripts/e2e_medcoder_validation.py`

```python
# OLD: result = await hybrid_adapter.infer_async(req, mode=variant_to_mode(args.variant))
# NEW: switch backend_provider via agent pack override
async def run_variant(variant: str, cases: list):
    backend_provider = {
        "prompt": "icoder.llm-with-tools.medcoder.v1",  # scope=[extract]
        "retrieve": "icoder.rule-engine.medcoder.v1",
        "prompt+retrieve": "icoder.llm-with-tools.medcoder.v1",  # scope=[extract,retrieve,merge,compliance]
        "full": "icoder.llm-with-tools.medcoder.v1",  # scope=[all 5]
    }[variant]
    agent_override = agent_pack_with_scope(medical_coding_pack, backend_provider, variant)
    for case in cases:
        output = await agent_runner.run(BackendRequest(input=case), agent_override, ctx)
        # ... F1 computation
```

**Migration action:**
- Replace `mode=` parameter with `backend_provider` + `tools.scope` override
- Verify all 4 variants produce same F1 as before (regression test)

## 5. Acceptance criteria

| # | Criterion | Verification |
|---|-----------|--------------|
| 1 | F1 baseline does not regress | `python scripts/e2e_runtime_validation.py --base-url http://localhost:8000` produces F1 ≥ baseline |
| 2 | 4 ablation variants produce same F1 as before | `python scripts/e2e_medcoder_validation.py --variant {full,prompt,retrieve,prompt+retrieve}` produces F1 within ±0.005 of pre-decoupling |
| 3 | `hybrid_adapter.py` deleted | `find backend -name hybrid_adapter.py` returns nothing |
| 4 | 5 new MCP tools registered | `GET /api/v1/agent-runtime/mcp/tools` includes `icoder_medcoder_extract/retrieve/merge/rerank/compliance` |
| 5 | 3 new providers registered | `GET /api/v1/agent-runtime/providers/health` includes 3 medcoder providers |
| 6 | `medical_coding/agent_pack.json` v1.2 with `backend_provider` | `icoder pack validate medical_coding/agent_pack.json` passes |
| 7 | RunTrace captures per-stage events | RunTraceViewer shows 5 tool_calls for `medcoder` mode, 2 for `retrieve` mode, 1 for `prompt` mode |
| 8 | Frontend still renders DiagnosisCard | `MedicalCodingPage` end-to-end test passes |
| 9 | Cached provider reduces repeat-query cost | Repeat query on same EMR text returns in <100ms with `raw.cache_hit=true` |
| 10 | Cascade provider falls back on LLM outage | Inject LLM failure, verify rule-engine fallback succeeds with `raw.cascade_winner=icoder.rule-engine.medcoder.v1` |

## 6. Rollback plan

If any acceptance criterion fails:

1. **Revert `medical_coding/agent_pack.json`** to v1.1 (no `backend_provider` field) — agent uses legacy hardcoded path
2. **Restore `hybrid_adapter.py`** from git history (file preserved in `icoder_runtime/legacy/` for 1 release cycle)
3. **Revert `MedicalCodingRuntimeEndpoint`** to call `hybrid_adapter.infer_async()` directly
4. **Keep new MCP tools registered** — they don't interfere with legacy path
5. **Investigate root cause** before retry

## 7. Test plan

### Unit tests (per provider)

- `tests/unit/backends/medcoder/test_extract_tool.py` — extraction prompt + parsing
- `tests/unit/backends/medcoder/test_retrieve_tool.py` — embedding + FAISS search
- `tests/unit/backends/medcoder/test_merge_tool.py` — deduplication + cap
- `tests/unit/backends/medcoder/test_rerank_tool.py` — rank prompt + parsing
- `tests/unit/backends/medcoder/test_compliance_tool.py` — rule evaluation + calibration
- `tests/unit/backends/medcoder/test_rule_engine_provider.py` — Stage 2+5 only
- `tests/unit/backends/medcoder/test_llm_with_tools_provider.py` — full 5-stage
- `tests/unit/backends/medcoder/test_hybrid_provider.py` — rule + LLM merge

### Integration tests

- `tests/integration/test_medical_coding_endpoint.py` — `/api/v2/tools/coding` end-to-end
- `tests/integration/test_medical_coding_runtrace.py` — 9-step trace + 5 tool_calls
- `tests/integration/test_medical_coding_cascade.py` — LLM outage → rule fallback

### E2E / regression tests

- `scripts/e2e_runtime_validation.py` — 201 cases, F1 ≥ baseline
- `scripts/e2e_medcoder_validation.py --variant full` — 100 cases, F1 within ±0.005 of pre-decoupling
- `scripts/e2e_medcoder_validation.py --variant {prompt,retrieve,prompt+retrieve}` — 100 cases each, F1 within ±0.005

### Browser walkthrough (per `feedback_browser_walkthrough_required.md`)

- Start dev server (`uvicorn :8000 + vite :3002`)
- Open MedicalCodingPage in Chrome :9222
- Submit a cardiology note
- Verify DiagnosisCard renders with evidence chips + TopKChips + override
- Verify RunTraceViewer shows 5 tool_calls for full mode
- Screenshot saved to `docs/corti_parity/phase4_e/medical_coding_decoupled_browser_walkthrough.png`

## 8. Effort estimate

| Step | Effort | Owner |
|------|--------|-------|
| 1-5 (extract 5 stages to MCP tools) | 2 days | backend |
| 6-8 (3 providers) | 1.5 days | backend |
| 9 (agent_pack.json v1.2) | 0.5 days | backend |
| 10 (runtime endpoint) | 0.5 days | backend |
| 11 (delete hybrid_adapter) | 0.5 days | backend |
| 12 (test script update) | 0.5 days | QA |
| Tests (unit + integration) | 1.5 days | backend |
| E2E + browser walkthrough | 0.5 days | QA |
| Buffer | 0.5 days | — |
| **Total** | **5 days** | — |

This matches the Phase 4-E estimate in `ICODER_AGENT_BACKEND_COMPATIBILITY_ARCHITECTURE.md` §5.

## 9. Post-decoupling benefits

1. **Declarative backend switching** — change `backend_provider` in agent_pack.json, no code changes
2. **Per-stage observability** — RunTraceViewer shows each of 5 stages as separate tool_call
3. **Composable resilience** — `icoder.cascade.medcoder.v1` (LLM → rule fallback) without code changes
4. **Caching layer** — `icoder.cached.medcoder.v1` for repeat queries (batch processing)
5. **A/B canary** — `ShadowDiffService` compares `icoder.hybrid.medcoder.v1` vs `icoder.llm-with-tools.medcoder.v1` on same input
6. **Corti-parity** — Code Validation / Compliance Guardrail / Note Completeness agents can reuse the same 5 MCP tools (e.g., `icoder_medcoder_extract` doubles as Note Completeness's Step 1)
7. **Test matrix clarity** — `backend_provider` × `tools.scope` matrix replaces `mode=` flag, easier to enumerate test cases
8. **F1 baseline preserved** — rule engine still drives code assignment; LLM only adds explainability

## 10. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| F1 regression after decoupling | Acceptance criterion #1 + #2; rollback plan §6 |
| MCP tool latency > hardcoded call | Acceptance criterion #7 (per-stage trace); MCP calls are async, parallel where possible |
| `tools.scope` enforcement gap | `ToolMCPCompatLayer` whitelist at boundary (Phase 3-C1 pattern) |
| Backward compat for v1.0 packs | Default `backend_provider=icoder.rule-engine.v1` if missing |
| LLM cost spike on full 5-stage | `icoder.cached.medcoder.v1` for repeat queries; `icoder.hybrid.medcoder.v1` (rule-first) as default |
| Stage 4 rerank few-shot KB drift | Lazy-load `cot_generation_progress_v2.json` on every call; version-pin in agent_pack |
| BGE-M3 model file corruption | `data/medcoder/models/` integrity check at startup; rebuild via `scripts/build_medcoder_index.py` |
| PHI leak via MCP tool args | `DataPolicy` redaction at `AgentRunContext` boundary; `redacted_view` in audit log |
