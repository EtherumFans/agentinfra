# Agent Hub runtime matrix

Generated: `2026-08-23T02:43:52.160508+00:00`

## Summary

- Disk Packs: 32
- Hub-visible Agents: 26
- Visible executable: 26
- Visible provider-resolvable: 26
- Visible structural development launch candidates: 26
- Visible dependent on an external LLM: 20
- Visible with optional external-LLM enhancement: 1
- Visible with local-only execution: 5
- Visible with an offline local baseline: 6
- Offline safe-fail-closed expected: 20
- Semantic live E2E verified by this inventory: 0
- Production-ready verified: 0
- Visible with contract-complete examples: 26
- Visible with complete field-type contracts: 26
- Visible with type-valid examples: 26
- Visible with complete nested schemas: 26
- Visible with nested-schema-valid examples: 26
- Visible with valid cross-field relations: 26
- Visible with valid evidence bindings: 26
- Declared evidence bindings: 12
- Visible with valid cross-Agent relations: 26
- Declared cross-Agent relations: 8
- Declared cross-field relations: 34
- Visible with immutable registered contracts: 26
- Visible with strict output allowlists: 26
- Hidden Packs: 6 (metadata-only: 5)

> Development launch-candidate readiness does not satisfy the external
> clinical, hospital integration, security/privacy, compliance, or
> production-operations release gates listed per Pack.
> Provider resolution is structural only. It is not a clinical or
> semantic capability pass; live-provider evidence remains separate.

## Inventory

| Agent | Visibility | Status | Execution path | Target | Offline expectation | Semantic live E2E | Candidate |
|---|---|---|---|---|---|---|---|
| cdi-review | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; explicit backend_provider or a2a.endpoint is required; output_contract.schema_ref is required; output_contract.required_fields must be non-empty; output_contract.field_types must be an object; phi_redaction=required is required; recorder_required=true is required; metrics_required=true is required; permissions.production_writeback_blocked=true is required; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required; integrity.sha256 must be a 64-character lowercase hex digest |
| claim-check | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| clinical-documentation-improvement-agent | Hub | executable | dedicated.cdi_a2a_handler | icoder.cdi-real-orchestrator.v1 | safe_fail_closed_without_external_provider | pending | yes |
| clinical-education | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| clinical-guidelines | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| code-validation-agent | Hub | executable | dedicated.governed_code_validation | icoder.governed-code-validation.v1 | local_baseline_with_optional_external_provider | pending | yes |
| code-reconciler | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| compliance-guardrail-agent | Hub | executable | dedicated.compliance_mcp | icoder.rule-engine.v1 | local_deterministic_execution | pending | yes |
| denial-appeals | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| diagnosis-extractor | Hub | executable | provider_registry | icoder.llm-with-tools.v1 | safe_fail_closed_without_external_provider | pending | yes |
| discharge-edu | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| discharge-summary-structuring | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| documentation-gap | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; explicit backend_provider or a2a.endpoint is required; output_contract.schema_ref is required; output_contract.required_fields must be non-empty; output_contract.field_types must be an object; phi_redaction=required is required; recorder_required=true is required; metrics_required=true is required; permissions.production_writeback_blocked=true is required; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required; integrity.sha256 must be a 64-character lowercase hex digest |
| drg-analyzer | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| evidence-ranker | Hub | executable | provider_registry | icoder.governed-evidence-ranker.v1 | local_deterministic_execution | pending | yes |
| evidence-extractor | Hub | executable | provider_registry | icoder.governed-evidence-extractor.v1 | local_deterministic_execution | pending | yes |
| icd10-navigator | Hub | executable | provider_registry | icoder.governed-icd-navigator.v1 | local_deterministic_execution | pending | yes |
| icu-summary | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| index-navigator | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| med-reconciliation | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| medcoder-coding-review-agent | hidden | executable | legacy_default | missing_backend_provider | requires_runtime_e2e_classification | pending | no — output_contract.field_types must be an object; at least one contract-complete example_output is required |
| medical-coding-agent | Hub | executable | dedicated.medical_coding_dispatcher | icoder.medical-coding-runtime.v2 | safe_fail_closed_without_external_provider | pending | yes |
| note-completeness-agent | Hub | executable | dedicated.note_completeness_rules | icoder.documentation-rule-engine.v1 | local_deterministic_execution | pending | yes |
| nursing-handoff | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| principal-diagnosis-review | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| prior-auth | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| procedure-extractor | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| referral-gen | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| rule-explainer | Hub | executable | provider_registry | icoder.llm-with-tools.v1 | safe_fail_closed_without_external_provider | pending | yes |
| surgical-registry | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
| tabular-validator | hidden | metadata_only | unroutable | not_executable | requires_runtime_e2e_classification | pending | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| triage | Hub | executable | provider_registry | icoder.pure-llm.v1 | safe_fail_closed_without_external_provider | pending | yes |
