# Agent Hub runtime matrix

Generated: `2026-08-22T17:55:30.704808+00:00`

## Summary

- Disk Packs: 32
- Hub-visible Agents: 26
- Visible executable: 26
- Visible provider-resolvable: 26
- Visible development launch candidates: 26
- Visible with contract-complete examples: 26
- Visible with complete field-type contracts: 26
- Visible with type-valid examples: 26
- Visible with complete nested schemas: 26
- Visible with nested-schema-valid examples: 26
- Visible with valid cross-field relations: 26
- Visible with valid evidence bindings: 26
- Declared evidence bindings: 15
- Visible with valid cross-Agent relations: 26
- Declared cross-Agent relations: 8
- Declared cross-field relations: 34
- Visible with immutable registered contracts: 26
- Visible with strict output allowlists: 26
- Hidden Packs: 6 (metadata-only: 5)

> Development launch-candidate readiness does not satisfy the external
> clinical, hospital integration, security/privacy, compliance, or
> production-operations release gates listed per Pack.

## Inventory

| Agent | Visibility | Status | Execution path | Target | Output contract | Candidate |
|---|---|---|---|---|---|---|
| cdi-review | hidden | metadata_only | unroutable | not_executable | — | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; explicit backend_provider or a2a.endpoint is required; output_contract.schema_ref is required; output_contract.required_fields must be non-empty; output_contract.field_types must be an object; phi_redaction=required is required; recorder_required=true is required; metrics_required=true is required; permissions.production_writeback_blocked=true is required; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required; integrity.sha256 must be a 64-character lowercase hex digest |
| claim-check | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/ClaimCheckOutput/v3 | yes |
| clinical-documentation-improvement-agent | Hub | executable | dedicated.cdi_a2a_handler | icoder.cdi-real-orchestrator.v1 | icoder/CDIAgentOutputV1/v6 | yes |
| clinical-education | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/ClinicalEducationOutput/v3 | yes |
| clinical-guidelines | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/ClinicalGuidelinesOutput/v4 | yes |
| code-validation-agent | Hub | executable | dedicated.code_validation_v2 | icoder.llm-with-tools.v1 | icoder/CodeValidationOutput/v6 | yes |
| code-reconciler | hidden | metadata_only | unroutable | not_executable | icoder/CodeReconciliation/v1 | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| compliance-guardrail-agent | Hub | executable | dedicated.compliance_mcp | icoder.rule-engine.v1 | icoder/ComplianceGuardrailOutput/v4 | yes |
| denial-appeals | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/DenialAppealOutput/v2 | yes |
| diagnosis-extractor | Hub | executable | provider_registry | icoder.llm-with-tools.v1 | icoder/DiagnosisExtractionOutput/v6 | yes |
| discharge-edu | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/DischargeEducationOutput/v2 | yes |
| discharge-summary-structuring | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/DischargeSummaryStructured/v3 | yes |
| documentation-gap | hidden | metadata_only | unroutable | not_executable | — | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; explicit backend_provider or a2a.endpoint is required; output_contract.schema_ref is required; output_contract.required_fields must be non-empty; output_contract.field_types must be an object; phi_redaction=required is required; recorder_required=true is required; metrics_required=true is required; permissions.production_writeback_blocked=true is required; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required; integrity.sha256 must be a 64-character lowercase hex digest |
| drg-analyzer | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/DRGDIPRiskReview/v4 | yes |
| evidence-ranker | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/EvidenceRankerOutput/v2 | yes |
| evidence-extractor | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/CodedEvidence/v10 | yes |
| icd10-navigator | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/Icd10NavigatorOutput/v2 | yes |
| icu-summary | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/IcuSummaryOutput/v2 | yes |
| index-navigator | hidden | metadata_only | unroutable | not_executable | icoder/CandidateSet/v1 | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| med-reconciliation | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/MedicationReconciliationOutput/v2 | yes |
| medcoder-coding-review-agent | hidden | executable | legacy_default | missing_backend_provider | icoder/MedicalCodingOutputSchema/v1 | no — output_contract.field_types must be an object; at least one contract-complete example_output is required |
| medical-coding-agent | Hub | executable | dedicated.medical_coding_dispatcher | icoder.medical-coding-runtime.v2 | icoder/MedicalCodingAgentOutputV2/v8 | yes |
| note-completeness-agent | Hub | executable | dedicated.note_completeness_mcp | icoder.pure-llm.v1 | icoder/NoteCompletenessOutput/v2 | yes |
| nursing-handoff | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/NursingHandoffOutput/v2 | yes |
| principal-diagnosis-review | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/PrincipalDxReview/v10 | yes |
| prior-auth | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/PriorAuthorizationOutput/v2 | yes |
| procedure-extractor | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/ProcedureCodingOutput/v8 | yes |
| referral-gen | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/ReferralOutput/v2 | yes |
| rule-explainer | Hub | executable | provider_registry | icoder.llm-with-tools.v1 | icoder/RuleExplanationOutput/v3 | yes |
| surgical-registry | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/SurgicalRegistryOutput/v4 | yes |
| tabular-validator | hidden | metadata_only | unroutable | not_executable | icoder/ValidationResult/v1 | no — pack_status=metadata_only; executable required; placeholder/deprecated maturity or tag must be removed; output_contract.field_types must be an object; human review policy or explicit review triggers are required; at least one example_input is required for smoke/E2E tests; at least one contract-complete example_output is required |
| triage | Hub | executable | provider_registry | icoder.pure-llm.v1 | icoder/TriageOutput/v2 | yes |
