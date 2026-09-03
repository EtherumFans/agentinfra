# Agent Hub semantic evidence bundle

Generated: `2026-08-25T15:01:42.538972+00:00`

Validation: **PASS**

Fresh synthetic live semantic evidence: **26/26**

## Source artifacts

- examples: `c81d5f713989bc3a1173c19d49d225e8e058975be9282e0d19ff05c05d2708f2` (icoder.agent-hub-examples-e2e/v3)
- adversarial: `9ce971a13f8e60ea485191c1f90372bdaafdafb87865fc304cf548e40e56edcd` (icoder.agent-hub-adversarial-e2e/v3)
- reference: `e3495fd1761b9a2cf7d5d4558d4f66a90567b65102025e99ec040baa802e2095` (icoder.agent-hub-reference-quality-replay/v1)
- stability: `0cceb71208cb20aad49ca457fb1c2eae5e74861ba78a62ce3d1215e19103e8fe` (icoder.agent-hub-stability-benchmark/v2)

## Limitations

- This proves fresh synthetic live semantic, adversarial, and stability gates; it is not an independent clinical-accuracy study.
- It does not prove Corti parity, hospital integration, regulatory approval, production SLOs, or clinician acceptance.
- Result tokens are HMAC-verified with the same ephemeral/server trust key; CI must keep that key process-scoped and out of artifacts.
