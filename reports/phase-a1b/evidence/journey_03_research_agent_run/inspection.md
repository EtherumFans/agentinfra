# Journey 3: Run Research Agent (coding-expert delegation)

**Slug**: `research_agent_run`
**Captured**: 2026-07-22T092838Z
**Verdict**: `API_WORKFLOW_VERIFIED`
**Provenance**: `ICODER_INTERNAL`

## Operation

```
coding_expert.delegate(input_text='T12 fracture synthetic')
```

## Observed response

- Status: `200`
- Response SHA-256: `5fd7368f5635c0dcffdfbe028fb58b65d9b6c31920ee5ccf3d3af5a132b7a783`

## Key observations

- Delegates to: icoder/medical-coding-agent@2.0.0
- human_review_required: True
- phi_redacted: True
- production_writeback_blocked: True

## Red-line checks

- no_auto_writeback: `PASS`
- phi_redacted: `PASS`
