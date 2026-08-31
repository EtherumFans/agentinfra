# Deployment candidate preflight

Generated: `2026-08-22T16:49:27.094093+00:00`

Result: **PASS**

| Check | Result |
|---|---:|
| compose_scope_is_explicitly_local | pass |
| compose_has_required_services | pass |
| compose_dependencies_are_health_gated | pass |
| compose_uses_persistent_trace_store | pass |
| run_trace_retention_is_executable_and_audited | pass |
| run_sse_metrics_are_phi_safe_bounded_and_scrapeable | pass |
| public_registration_cannot_self_assign_platform_role | pass |
| user_tokens_are_type_checked_versioned_and_membership_bound | pass |
| organization_paths_and_legacy_team_api_are_tenant_scoped | pass |
| organization_invites_are_hashed_one_time_and_audited | pass |
| organization_invite_delivery_is_encrypted_durable_and_bounded | pass |
| organization_invite_webhook_is_signed_idempotent_and_fail_closed | pass |
| organization_invite_processor_is_explicit_and_secret_free | pass |
| machine_idempotency_is_bound_to_delegated_subject_and_purpose | pass |
| native_medcoder_worker_handshake_and_confidence_are_bounded | pass |
| organization_invite_browser_flow_uses_fragment_and_scrubs_history | pass |
| agent_hub_typed_contracts_are_complete_and_fail_closed | pass |
| agent_hub_pack_reference_semantics_are_complete_and_self_validating | pass |
| agent_failure_envelopes_are_suppressed_and_measured_separately | pass |
| corti_20_agent_catalog_is_mapped_and_development_verified | pass |
| agent_hub_visibility_is_launch_candidate_and_provider_fail_closed | pass |
| orchestrator_missing_llm_is_retryable_503_without_stub_response | pass |
| orchestrator_missing_expert_is_503_without_noop_or_stub_success | pass |
| a2a_regressions_reject_mock_clinical_success_and_stale_fields | pass |
| provider_a2a_datapart_is_exact_pack_output_allowlist | pass |
| native_provider_stream_keeps_provisional_content_private_and_terminal_exact | pass |
| openinference_export_uses_standard_bounded_provider_tool_and_usage_attributes | pass |
| dedicated_clinical_runtimes_emit_bounded_content_free_telemetry | pass |
| a2a_structural_task_artifact_ids_bypass_free_text_phi_redaction_safely | pass |
| feedback_training_requires_independent_bounded_owner_authorization | pass |
| cdi_required_safety_gate_degradation_is_structured_and_unpublished | pass |
| llm_egress_policy_is_enforced_at_gateway_and_legacy_boundaries | pass |
| model_provider_selection_is_explicit_and_fails_closed | pass |
| database_sql_logging_is_opt_in_and_parameter_safe | pass |
| sqlite_reconciliation_is_read_only_staged_and_fail_closed | pass |
| a2a_local_working_task_cancellation_is_truthful_and_audited | pass |
| agentic_v2_context_task_artifact_resources_are_real_and_isolated | pass |
| task_artifacts_are_durable_encrypted_integrity_checked_and_owned | pass |
| a2a_v1_streams_use_standard_status_and_artifact_update_events | pass |
| a2a_v1_artifact_streams_persist_exact_encrypted_chunks_and_sdk_entrypoints | pass |
| managed_artifact_objects_are_quarantined_scanned_single_use_and_sdk_visible | pass |
| artifact_download_grants_are_actor_bound_and_query_secret_free | pass |
| models_catalog_is_authenticated_secret_free_and_sdk_visible | pass |
| model_live_canary_is_fixed_phi_free_budgeted_and_cooled | pass |
| tenant_model_selection_is_versioned_audited_and_fail_closed | pass |
| platform_user_access_is_versioned_audited_and_revoking | pass |
| platform_organization_control_is_validated_audited_and_revoking | pass |
| first_platform_admin_bootstrap_is_explicit_one_time_and_dry_run | pass |
| platform_access_console_is_admin_gated | pass |
| stateful_services_have_healthchecks | pass |
| backend_image_runs_non_root | pass |
| backend_image_has_healthcheck | pass |
| backend_image_excludes_native_ml_stack | pass |
| backend_image_has_explicit_postgres_trace_driver | pass |
| ml_worker_image_is_minimal_and_isolated | pass |
| compose_ml_worker_is_internal_and_fail_closed | pass |
| ml_assets_are_hash_verified_and_version_aligned | pass |
| api_compose_exposes_remote_retriever_contract | pass |
| medcoder_overlay_wires_backend_to_healthy_worker | pass |
| external_registry_gateways_are_governed_and_fail_closed | pass |
| semantic_memory_is_remote_encrypted_and_patient_authority_honest | pass |
| frontend_image_has_healthcheck | pass |
| embedded_assistant_release_bundle_is_present | pass |
| docker_context_excludes_env_files | pass |
| frontend_tls_and_security_headers_declared | pass |
| local_frontend_http_is_explicit_and_isolated | pass |
| nginx_sse_proxy_is_streaming_and_bounded | pass |
| ci_e2e_is_fail_closed_and_uses_vault_credential | pass |
| dotnet_sdk_ci_tests_and_packs_both_supported_frameworks | pass |
| region_catalog_covers_eu_us_cn | pass |
| cross_environment_replication_forbidden | pass |
| all_regions_honestly_unprovisioned | pass |
| china_region_and_compliance_declared | pass |
| cloud_template_has_no_live_secret | pass |
| cloud_template_defaults_to_local | pass |
| cloud_template_disables_protocol_fixtures | pass |
| stt_protocol_fixtures_are_pytest_only_and_cloud_disabled | pass |
| cloud_template_uses_persistent_trace_store | pass |
| cloud_template_requires_webhook_invite_delivery | pass |

## Limitations

- No image was built or started because Docker CLI is unavailable.
- No image vulnerability/SBOM/registry-signature scan was performed.
- No cloud region was provisioned; regions.yaml declares every region enabled=false.
- No disaster recovery, capacity, latency, or availability SLA was exercised.
- The PostgreSQL cross-process contract is conditional on the Linux CI service and was not exercised by this static preflight.
- No production retention scheduler or CronJob was installed or executed; the verified purge CLI must be scheduled by the target platform.
- No production metrics collector, cross-process aggregation, alert delivery route, or operational SLA was installed or exercised.
- Local development defaults to manual invitation credentials; cloud mode fails closed unless the encrypted signed webhook outbox is configured.
- The webhook transport was exercised only against a local test receiver; a real regional email provider, production scheduler, bounce handling, template approval, and delivery SLA remain external integration gates.
- Platform access changes are single-admin operations in development; production MFA, dual approval, SSO/SCIM, and independent access review remain external gates.
