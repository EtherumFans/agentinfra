# Agent Hub runtime matrix

Generated: `2026-08-24T15:08:09.810104+00:00`

## Summary

- Disk Packs: 32
- Hub-visible Agents: 26
- Visible executable: 26
- Visible provider-resolvable: 26
- Visible structural development launch candidates: 26
- Visible dependent on an external LLM: 3
- Visible with optional external-LLM enhancement: 1
- Visible with local-only execution: 22
- Visible with an offline local baseline: 23
- Offline safe-fail-closed expected: 3
- Semantic live E2E verified by a validated evidence bundle: 0
- Local-only semantic HTTP E2E verified (limited twenty-three-Agent scope): 23
- Production-ready verified: 0
- Visible with contract-complete examples: 26
- Visible with complete field-type contracts: 26
- Visible with type-valid examples: 26
- Visible with complete nested schemas: 26
- Visible with nested-schema-valid examples: 26
- Visible with valid cross-field relations: 26
- Visible with valid evidence bindings: 26
- Declared evidence bindings: 29
- Visible with valid cross-Agent relations: 26
- Declared cross-Agent relations: 10
- Declared cross-field relations: 106
- Visible with immutable registered contracts: 26
- Visible with strict output allowlists: 26
- Hidden Packs: 6 (metadata-only: 5)

> Development launch-candidate readiness does not satisfy the external
> clinical, hospital integration, security/privacy, compliance, or
> production-operations release gates listed per Pack.
> Provider resolution is structural only. It is not a clinical or
> semantic capability pass; live-provider evidence remains separate.
> Local semantic evidence covers only deterministic/governed-baseline
> Agents and cannot satisfy the strict 26-Agent live-provider gate.

## Inventory

| Agent | Visibility | Status | Execution path | Target | Offline expectation | Full semantic live E2E | Local semantic E2E | Candidate |
|---|---|---|---|---|---|---|---|---|
| cdi-review | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | n/a or pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; explicit backend_provider or a2a.endpoint is required; output_contract.schema_ref is required; output_contract.required_fields must be non-empty; output_contract.field_types must be an object; phi_redaction=required is required; recorder_required=true is required; metrics_required=true is required; permissions.production_writeback_blocked=true is required; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required; integrity.sha256 must be a 64-character lowercase hex digest |
| claim-check | Hub | executable | provider_registry | icoder.governed-claim-check.v1 | local_deterministic_execution | pending | verified | yes |
| clinical-documentation-improvement-agent | Hub | executable | dedicated.cdi_a2a_handler | icoder.cdi-real-orchestrator.v1 | safe_fail_closed_without_external_provider | pending | n/a or pending | yes |
| clinical-education | Hub | executable | provider_registry | icoder.governed-clinical-education.v1 | local_deterministic_execution | pending | verified | yes |
| clinical-guidelines | Hub | executable | provider_registry | icoder.governed-clinical-guidelines.v1 | local_deterministic_execution | pending | verified | yes |
| code-validation-agent | Hub | executable | dedicated.governed_code_validation | icoder.governed-code-validation.v1 | local_baseline_with_optional_external_provider | pending | verified | yes |
| code-reconciler | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | n/a or pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| compliance-guardrail-agent | Hub | executable | dedicated.compliance_mcp | icoder.rule-engine.v1 | local_deterministic_execution | pending | verified | yes |
| denial-appeals | Hub | executable | provider_registry | icoder.governed-denial-appeals.v1 | local_deterministic_execution | pending | verified | yes |
| diagnosis-extractor | Hub | executable | provider_registry | icoder.governed-diagnosis-extractor.v1 | local_deterministic_execution | pending | verified | yes |
| discharge-edu | Hub | executable | provider_registry | icoder.governed-discharge-education.v1 | local_deterministic_execution | pending | verified | yes |
| discharge-summary-structuring | Hub | executable | provider_registry | icoder.governed-discharge-summary.v1 | local_deterministic_execution | pending | verified | yes |
| documentation-gap | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | n/a or pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; explicit backend_provider or a2a.endpoint is required; output_contract.schema_ref is required; output_contract.required_fields must be non-empty; output_contract.field_types must be an object; phi_redaction=required is required; recorder_required=true is required; metrics_required=true is required; permissions.production_writeback_blocked=true is required; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required; integrity.sha256 must be a 64-character lowercase hex digest |
| drg-analyzer | Hub | executable | provider_registry | icoder.governed-drg-dip-risk-review.v1 | local_deterministic_execution | pending | verified | yes |
| evidence-ranker | Hub | executable | provider_registry | icoder.governed-evidence-ranker.v1 | local_deterministic_execution | pending | verified | yes |
| evidence-extractor | Hub | executable | provider_registry | icoder.governed-evidence-extractor.v1 | local_deterministic_execution | pending | verified | yes |
| icd10-navigator | Hub | executable | provider_registry | icoder.governed-icd-navigator.v1 | local_deterministic_execution | pending | verified | yes |
| icu-summary | Hub | executable | provider_registry | icoder.governed-icu-summary.v1 | local_deterministic_execution | pending | verified | yes |
| index-navigator | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | n/a or pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| med-reconciliation | Hub | executable | provider_registry | icoder.governed-medication-reconciliation.v1 | local_deterministic_execution | pending | verified | yes |
| medcoder-coding-review-agent | hidden | executable | legacy_default | missing_backend_provider | requires_runtime_e2e_classification | pending | n/a or pending | no — output_contract.field_types must be an object; at least one contract-complete example_output is required |
| medical-coding-agent | Hub | executable | dedicated.medical_coding_dispatcher | icoder.medical-coding-runtime.v2 | safe_fail_closed_without_external_provider | pending | n/a or pending | yes |
| note-completeness-agent | Hub | executable | dedicated.note_completeness_rules | icoder.documentation-rule-engine.v1 | local_deterministic_execution | pending | verified | yes |
| nursing-handoff | Hub | executable | provider_registry | icoder.governed-nursing-handoff.v1 | local_deterministic_execution | pending | verified | yes |
| principal-diagnosis-review | Hub | executable | provider_registry | icoder.governed-principal-diagnosis-review.v1 | local_deterministic_execution | pending | verified | yes |
| prior-auth | Hub | executable | provider_registry | icoder.governed-prior-authorization.v1 | local_deterministic_execution | pending | verified | yes |
| procedure-extractor | Hub | executable | provider_registry | icoder.governed-procedure-extractor.v1 | local_deterministic_execution | pending | verified | yes |
| referral-gen | Hub | executable | provider_registry | icoder.governed-referral.v1 | local_deterministic_execution | pending | verified | yes |
| rule-explainer | Hub | executable | provider_registry | icoder.governed-rule-explainer.v1 | local_deterministic_execution | pending | verified | yes |
| surgical-registry | Hub | executable | provider_registry | icoder.governed-surgical-registry.v1 | local_deterministic_execution | pending | verified | yes |
| tabular-validator | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | n/a or pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| triage | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | n/a or pending | yes |
