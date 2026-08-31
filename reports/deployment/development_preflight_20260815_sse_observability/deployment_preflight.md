# Deployment candidate preflight

Generated: `2026-08-14T21:23:00.731130+00:00`

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
| stateful_services_have_healthchecks | pass |
| backend_image_runs_non_root | pass |
| backend_image_has_healthcheck | pass |
| backend_image_excludes_native_ml_stack | pass |
| backend_image_has_explicit_postgres_trace_driver | pass |
| ml_worker_image_is_minimal_and_isolated | pass |
| compose_ml_worker_is_internal_and_fail_closed | pass |
| ml_assets_are_hash_verified_and_version_aligned | pass |
| api_compose_exposes_remote_retriever_contract | pass |
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
| cloud_template_uses_persistent_trace_store | pass |

## Limitations

- No image was built or started because Docker CLI is unavailable.
- No image vulnerability/SBOM/registry-signature scan was performed.
- No cloud region was provisioned; regions.yaml declares every region enabled=false.
- No disaster recovery, capacity, latency, or availability SLA was exercised.
- The PostgreSQL cross-process contract is conditional on the Linux CI service and was not exercised by this static preflight.
- No production retention scheduler or CronJob was installed or executed; the verified purge CLI must be scheduled by the target platform.
- No production metrics collector, cross-process aggregation, alert delivery route, or operational SLA was installed or exercised.
