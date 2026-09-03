# Agent Hub semantic evidence bundle

Generated: `2026-08-25T13:40:01.618221+00:00`

Validation: **PASS**

Fresh synthetic live semantic evidence: **26/26**

## Source artifacts

- examples: `34516b457334d98407c90121e09c95f9566fc3c4092331acf47e7499c6caf769` (icoder.agent-hub-examples-e2e/v3)
- adversarial: `5119f702bc05d00f8fdaf7a0e67e303809a9e74d0982058bc38ea04b1debdb84` (icoder.agent-hub-adversarial-e2e/v3)
- reference: `592907aff6fa520f4df704b77ce139355ff701ec51640c4940881be0f9e6f670` (icoder.agent-hub-reference-quality-replay/v1)
- stability: `86428dee23c6fabdba5528bad4808a59d8d095ec64a029b3ca7502c01a511f06` (icoder.agent-hub-stability-benchmark/v2)

## Limitations

- This proves fresh synthetic live semantic, adversarial, and stability gates; it is not an independent clinical-accuracy study.
- It does not prove Corti parity, hospital integration, regulatory approval, production SLOs, or clinician acceptance.
- Result tokens are HMAC-verified with the same ephemeral/server trust key; CI must keep that key process-scoped and out of artifacts.
