# Agent Hub semantic evidence bundle

Generated: `2026-08-26T04:55:57.217837+00:00`

Validation: **PASS**

Fresh synthetic live semantic evidence: **26/26**

## Source artifacts

- examples: `1f95f9d94f03c81504d6f9982d6e3d352ce4c7a5f6634e52fb540b146284658c` (icoder.agent-hub-examples-e2e/v3)
- adversarial: `86e691b2efcea4145d77733291852ee307004cc0b57bf00c4db4b880d74793b1` (icoder.agent-hub-adversarial-e2e/v3)
- reference: `b25f8bb29fc2052cd5e5d7c0ab08be881fe6018100881b4d66840a20e8dcb27d` (icoder.agent-hub-reference-quality-replay/v1)
- stability: `2630b247519a3d921c00ac3f14a4d0d5cd5c652ea2667bc798f5c268c865a908` (icoder.agent-hub-stability-benchmark/v2)

## Limitations

- This proves fresh synthetic live semantic, adversarial, and stability gates; it is not an independent clinical-accuracy study.
- It does not prove Corti parity, hospital integration, regulatory approval, production SLOs, or clinician acceptance.
- Result tokens are HMAC-verified with the same ephemeral/server trust key; CI must keep that key process-scoped and out of artifacts.
