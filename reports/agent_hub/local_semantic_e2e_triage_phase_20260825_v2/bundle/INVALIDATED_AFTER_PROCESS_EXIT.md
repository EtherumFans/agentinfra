# Historical bundle invalidation notice

This directory no longer contains the authoritative passing bundle.

An offline rebuild after the original server process exited correctly failed HMAC result/trace attestation verification because the original ephemeral trust key was never persisted. The failed rebuild was retained instead of being presented as fresh evidence. No signature was bypassed or regenerated.

The replacement fresh, newly signed run is:

`reports/agent_hub/local_semantic_e2e_external_gate_phase_20260825_v3/bundle/agent_hub_local_semantic_evidence_bundle.json`
