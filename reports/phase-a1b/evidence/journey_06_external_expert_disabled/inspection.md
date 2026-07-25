# Journey 6: External Expert (DrugBank) LICENSE_REQUIRED gate

**Slug**: `external_expert_disabled`
**Captured**: 2026-07-22T092838Z
**Verdict**: `API_WORKFLOW_VERIFIED`
**Provenance**: `ICODER_INTERNAL`

## Operation

```
GET /api/v1/experts/external-gate/evaluate?expert_key=drugbank
```

## Observed response

- Status: `200`
- Response SHA-256: `7c3168e780ffe0695a333a25cd27203b65ddc4a8d7d585301f19481b91b39f36`

## Key observations

- Gate reason: LICENCE_REQUIRED
- Permitted: False
- No LLM fallback (patient-safety red line)
- No network call performed (gate rules only)

## Red-line checks

- no_llm_fallback: `PASS`
- no_network_call: `PASS`
- licence_required_blocked: `PASS`
