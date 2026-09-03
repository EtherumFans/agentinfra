# Agent Hub semantic evidence bundle

Generated: `2026-08-26T22:48:18.452929+00:00`

Validation: **PASS**

Fresh synthetic live semantic evidence: **26/26**

## Source artifacts

- examples: `067987177c35c8e9f35657bc2e7e5291f4de33e71b57206a9ef1db75327f79a3` (icoder.agent-hub-examples-e2e/v3)
- adversarial: `7661be0d363573cfbd3efafe96b04704186ecb69fb58557640139baddcbc538a` (icoder.agent-hub-adversarial-e2e/v3)
- reference: `a529dba3710ba6333c35a90cd715e5cc0399296dd8733832a92c83ea793a6e6a` (icoder.agent-hub-reference-quality-replay/v1)
- stability: `3ecea7ccd269aa6579add3c7fa0d997d9af137617738041e233909c1a9d4c6e5` (icoder.agent-hub-stability-benchmark/v2)

## Limitations

- This proves fresh synthetic live semantic, adversarial, and stability gates; it is not an independent clinical-accuracy study.
- It does not prove Corti parity, hospital integration, regulatory approval, production SLOs, or clinician acceptance.
- Result tokens are HMAC-verified with the same ephemeral/server trust key; CI must keep that key process-scoped and out of artifacts.
