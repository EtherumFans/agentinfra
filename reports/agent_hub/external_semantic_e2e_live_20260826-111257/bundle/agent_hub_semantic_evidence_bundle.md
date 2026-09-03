# Agent Hub semantic evidence bundle

Generated: `2026-08-26T03:22:40.976704+00:00`

Validation: **PASS**

Fresh synthetic live semantic evidence: **26/26**

## Source artifacts

- examples: `11d16dea148c900d3ed5e01692c80167e3d0e0001f452b62578f642a00140eca` (icoder.agent-hub-examples-e2e/v3)
- adversarial: `bb5744fe2c2ddfb4055a3a249756937d315cd6f23898ef1871a6e2b517c6de80` (icoder.agent-hub-adversarial-e2e/v3)
- reference: `be5d34ec37cc522a2f197cacb296e0ab944ab5d329b4e6f23b94c2b5f9e89cb5` (icoder.agent-hub-reference-quality-replay/v1)
- stability: `111fc9c419897433dcd85614d8f4869d792baceaeb606150c6e36feff21d87f1` (icoder.agent-hub-stability-benchmark/v2)

## Limitations

- This proves fresh synthetic live semantic, adversarial, and stability gates; it is not an independent clinical-accuracy study.
- It does not prove Corti parity, hospital integration, regulatory approval, production SLOs, or clinician acceptance.
- Result tokens are HMAC-verified with the same ephemeral/server trust key; CI must keep that key process-scoped and out of artifacts.
