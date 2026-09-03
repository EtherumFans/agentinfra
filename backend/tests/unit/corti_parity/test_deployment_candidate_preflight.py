from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "corti_parity"
    / "validate_deployment_candidate.py"
)
SPEC = importlib.util.spec_from_file_location("deployment_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_repository_deployment_candidate_static_preflight_passes() -> None:
    report = MODULE.validate()

    assert report["passed"] is True
    assert report["failed_checks"] == []
    assert report["mode"] == "static_without_docker_cli"
    assert len(report["checks"]) >= 18
    assert report["checks"][
        "cn_code_catalog_assets_are_image_owned_integrity_checked_and_fail_closed"
    ] is True
    assert report["checks"][
        "ccl2026_local_dataset_is_source_bound_aggregate_only_and_egress_blocked"
    ] is True
    assert report["checks"][
        "ccl2026_local_prediction_evaluator_is_exact_aggregate_only_and_fail_closed"
    ] is True
    assert report["checks"][
        "ccl2026_local_deterministic_baseline_is_gold_blind_offline_and_transient"
    ] is True
    assert report["checks"][
        "ccl2026_local_supervised_oof_is_leakage_bounded_aggregate_only_and_offline"
    ] is True
    assert report["checks"][
        "clinical_model_packages_are_metadata_only_four_eyes_and_fail_closed"
    ] is True
    assert report["checks"][
        "clinical_model_artifact_supply_chain_is_signed_scanned_and_shadow_only"
    ] is True
    assert report["checks"][
        "ccl2026_local_model_readiness_audit_blocks_unsafe_native_and_embedding_only_stacks"
    ] is True
    assert report["checks"][
        "dotnet_sdk_ci_tests_packs_and_compiles_all_supported_frameworks"
    ] is True
    assert report["checks"]["nginx_sse_proxy_is_streaming_and_bounded"] is True
    assert report["checks"]["compose_uses_persistent_trace_store"] is True
    assert report["checks"][
        "backend_image_has_explicit_postgres_trace_driver"
    ] is True
    assert report["checks"]["cloud_template_uses_persistent_trace_store"] is True
    assert report["checks"][
        "run_trace_retention_is_executable_and_audited"
    ] is True
    assert report["checks"][
        "corti_20_agent_catalog_is_mapped_and_development_verified"
    ] is True
    assert report["checks"][
        "agent_hub_visibility_is_launch_candidate_and_provider_fail_closed"
    ] is True
    assert report["checks"][
        "agent_hub_pack_reference_semantics_are_complete_and_self_validating"
    ] is True
    assert report["checks"][
        "agent_hub_external_semantic_evidence_is_scoped_real_model_and_composable"
    ] is True
    assert report["checks"][
        "agent_hub_clinical_calibration_is_serial_attested_and_egress_governed"
    ] is True
    assert report["checks"][
        "bilingual_coding_gold_review_is_blinded_dual_adjudicated_and_fail_closed"
    ] is True
    assert report["checks"][
        "orchestrator_missing_llm_is_retryable_503_without_stub_response"
    ] is True
    assert report["checks"][
        "orchestrator_missing_expert_is_503_without_noop_or_stub_success"
    ] is True
    assert report["checks"][
        "a2a_regressions_reject_mock_clinical_success_and_stale_fields"
    ] is True
    assert report["checks"][
        "provider_a2a_datapart_is_exact_pack_output_allowlist"
    ] is True
    assert report["checks"][
        "native_provider_stream_keeps_provisional_content_private_and_terminal_exact"
    ] is True
    assert report["checks"][
        "openinference_export_uses_standard_bounded_provider_tool_and_usage_attributes"
    ] is True
    assert report["checks"][
        "dedicated_clinical_runtimes_emit_bounded_content_free_telemetry"
    ] is True
    assert report["checks"][
        "a2a_structural_task_artifact_ids_bypass_free_text_phi_redaction_safely"
    ] is True
    assert report["checks"][
        "feedback_training_requires_independent_bounded_owner_authorization"
    ] is True
    assert report["checks"][
        "cdi_required_safety_gate_degradation_is_structured_and_unpublished"
    ] is True
    assert report["checks"][
        "stt_protocol_fixtures_are_pytest_only_and_cloud_disabled"
    ] is True
    assert report["checks"][
        "realtime_stt_is_tenant_scoped_bounded_local_only_and_phi_safe"
    ] is True
    assert report["checks"][
        "streams_is_current_tenant_safe_truthful_cross_sdk_and_e2e_tested"
    ] is True
    assert report["checks"][
        "streams_audio_containers_are_declared_detected_and_cross_sdk_validated"
    ] is True
    assert report["checks"][
        "streams_media_decode_is_isolated_bounded_fail_closed_and_e2e_tested"
    ] is True
    assert report["checks"][
        "streams_recommended_pcm_and_audio_events_are_typed_bounded_and_e2e_tested"
    ] is True
    assert report["checks"][
        "streams_multichannel_pcm_and_fast_init_are_attributed_and_e2e_tested"
    ] is True
    assert report["checks"][
        "streams_keyterms_are_bounded_forwarded_current_shape_and_e2e_tested"
    ] is True
    assert report["checks"][
        "transcripts_dictation_is_explicit_localized_durable_and_cross_sdk"
    ] is True
    assert report["checks"][
        "transcripts_keyterms_are_bounded_encrypted_forwarded_and_cross_sdk"
    ] is True
    assert report["checks"][
        "transcripts_stereo_pcm_is_split_encrypted_attributed_and_cross_sdk"
    ] is True
    assert report["checks"][
        "transcripts_encoded_multichannel_is_isolated_bounded_timestamped_and_cross_sdk"
    ] is True
    assert report["checks"][
        "streams_test_client_and_reader_threads_are_explicitly_closed"
    ] is True
    assert report["checks"][
        "login_rate_limit_is_isolated_from_general_api_traffic"
    ] is True
    assert report["checks"][
        "streams_cross_worker_leases_are_fenced_and_crash_recoverable"
    ] is True
    assert report["checks"][
        "streams_unfinished_interactions_are_encrypted_fenced_and_restart_resumable"
    ] is True
    assert report["checks"][
        "llm_egress_policy_is_enforced_at_gateway_and_legacy_boundaries"
    ] is True
    assert report["checks"][
        "model_provider_selection_is_explicit_and_fails_closed"
    ] is True
    assert report["checks"][
        "models_catalog_is_authenticated_secret_free_and_sdk_visible"
    ] is True
    assert report["checks"][
        "model_live_canary_is_fixed_phi_free_budgeted_and_cooled"
    ] is True
    assert report["checks"][
        "medcoder_overlay_wires_backend_to_healthy_worker"
    ] is True
    assert report["checks"][
        "external_registry_gateways_are_governed_and_fail_closed"
    ] is True
    assert report["checks"][
        "semantic_memory_is_remote_encrypted_and_patient_authority_honest"
    ] is True
    assert report["checks"][
        "agent_failure_envelopes_are_suppressed_and_measured_separately"
    ] is True
    assert report["checks"][
        "database_sql_logging_is_opt_in_and_parameter_safe"
    ] is True
    assert report["checks"][
        "sqlite_reconciliation_is_read_only_staged_and_fail_closed"
    ] is True
    assert report["checks"][
        "a2a_local_working_task_cancellation_is_truthful_and_audited"
    ] is True
    assert report["checks"][
        "agentic_v2_context_task_artifact_resources_are_real_and_isolated"
    ] is True
    assert report["checks"][
        "task_artifacts_are_durable_encrypted_integrity_checked_and_owned"
    ] is True
    assert report["checks"][
        "a2a_v1_streams_use_standard_status_and_artifact_update_events"
    ] is True
    assert report["checks"][
        "a2a_v1_artifact_streams_persist_exact_encrypted_chunks_and_sdk_entrypoints"
    ] is True
    assert report["checks"][
        "managed_artifact_objects_are_quarantined_scanned_single_use_and_sdk_visible"
    ] is True
    assert report["checks"][
        "artifact_download_grants_are_actor_bound_and_query_secret_free"
    ] is True
    assert report["checks"][
        "machine_idempotency_is_bound_to_delegated_subject_and_purpose"
    ] is True
    assert report["checks"][
        "native_medcoder_worker_handshake_and_confidence_are_bounded"
    ] is True
    assert report["checks"][
        "starlette_testclient_uses_pinned_httpx2_backend"
    ] is True
    assert any("No image was built" in item for item in report["limitations"])
