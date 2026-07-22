# Journey 4: Medical Calculator (BMI + invalid-unit error path)

**Slug**: `calculator`
**Captured**: 2026-07-22T092838Z
**Verdict**: `API_WORKFLOW_VERIFIED`
**Provenance**: `ICODER_INTERNAL`

## Operation

```
medical_calculator.calculate('bmi', weight_kg=70, height_m=1.75) + invalid unit
```

## Observed response

- Status: `200`
- Response SHA-256: `7a32882b56cd1053cae2529723b56cf16b8ed9efad478f99626ba44f53b08ab0`

## Key observations

- BMI output: {'bmi': 22.86, 'category': 'normal'}
- Invalid-unit error path: correctly raised ValueError: weight_kg and height_m must be positive
- Deterministic — no LLM arithmetic
