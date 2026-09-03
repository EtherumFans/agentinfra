"""Phase A1A Gate 4.3 — Audit-log detail redaction.

The audit_log table has three free-form columns that historically
accepted any value from the emit site:

  - ``details`` (JSON) — action-specific data
  - ``model_input_summary`` (Text) — LLM prompt preview
  - ``model_output_summary`` (Text) — LLM completion preview

The emit sites do not consistently strip PHI from these columns —
``log_action(... details={"patient_name": "张三", ...})`` would
persist the patient name in the audit row. Gate 4.3 introduces
this redactor as a chokepoint so the storage layer enforces a
minimum-necessary-data policy regardless of what the caller passes.

Policy:

  - For ``details`` (dict): walk the top-level keys. Allow only
    non-PHI metadata (``"action"``, ``"status"``, ``"run_id"``,
    etc.). Replace PHI-carrying keys (``"patient_name"``,
    ``"mrn"``, ``"input_text"``, etc.) with ``"[REDACTED]"``.
    Nested dicts/lists are redacted whole (deep walk is too
    expensive for the audit hot path; the allowlist covers the
    top level which is where emit sites put PHI by accident).
  - For ``model_input_summary`` / ``model_output_summary``: cap
    to ``MAX_SUMMARY_LEN`` chars (default 200) and pass through
    ``redact_for_export`` to strip common patterns (Chinese
    ID-card numbers, phone numbers, MRN patterns).

This module is a defence-in-depth layer — the *authoritative*
fix is at the emit sites, which Gate 4.3 reviews but cannot
fully rewrite (70+ call sites). The redactor here guarantees
that even an unreviewed emit site cannot leak PHI to the audit
table.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Top-level keys that may appear in audit ``details`` without redaction.
# Anything NOT on this list is replaced with ``"[REDACTED]"``.
#
# The list is deliberately permissive about operational metadata
# (run_id, agent_id, status, reason) and deliberately strict about
# anything that could carry patient context (input_text, output_text,
# patient_*, mrn, encounter_id is ALLOWED because it's already
# tenant-scoped and the value is an internal id, not PHI).
_ALLOWED_DETAIL_KEYS: frozenset[str] = frozenset({
    # Run / agent identity (operational metadata)
    "run_id", "trace_id", "agent_id", "agent_version", "expert_id",
    # Agent-definition lifecycle provenance. These values are server-owned
    # identifiers, enum states, semantic versions, or bounded field-name lists;
    # prompt/config values are intentionally never included.
    "source_agent_ref", "source_runtime_agent_id", "changed_fields",
    "previous_status",
    "connector_id", "connector_type", "credential_provider", "credential_version",
    "connector_graph_revision", "connector_node_count",
    "api_client_id", "embedded_app_id", "session_id", "context_id",
    "request_id", "correlation_id",
    # Resource identity (operational metadata, NOT PHI)
    "encounter_id", "case_id", "document_id", "review_id", "code_id",
    "resource_type", "resource_id", "organization_id", "org_id",
    "invite_id", "target_user_id",
    # Action context (operational metadata)
    "action", "endpoint", "method", "status", "status_code",
    "reason", "reason_code", "error_code", "stage", "step", "outcome", "duration_ms", "latency_ms",
    "attempts", "retry_delay_seconds",
    "tokens_used", "cost", "currency", "model_version",
    # Auth context (operational metadata)
    "role", "old_role", "new_role", "old_active", "new_active",
    "ticket_id", "expected_token_version", "actual_token_version",
    "tokens_revoked", "clients_disabled", "scope", "scopes_granted", "scopes_required",
    "auth_type", "ip_address_hashed",
    # System metadata
    "version", "deployment_mode", "runtime_mode", "environment", "region",
    # Tenant model routing (enumerated mode + operator-defined deployment ID).
    "selection_mode", "previous_selection_mode",
    "model_deployment_id", "previous_model_deployment_id",
    # Model deployment health probe metadata. These values are bounded
    # identifiers/enums/booleans; no credential or endpoint value is ever
    # accepted here.
    "deployment_id", "provider_id", "probe_mode", "egress_decision",
    "circuit_open", "credential_configured", "max_cost", "estimated_max_cost",
    "max_output_tokens", "timeout_seconds", "cooldown_seconds",
    "synthetic_payload", "patient_data_sent", "acknowledged",
    "expected_token_matched", "billing_authoritative",
    # Development billing ledger simulation metadata. Amounts are bounded
    # numeric values; reference is an operator-supplied non-PHI identifier.
    "amount", "balance", "balance_before", "new_balance", "simulation", "source",
    "reference", "reserved_amount", "settled_amount", "held_amount",
    "available_balance",
    # Boolean flags
    "success", "is_retry", "is_test", "is_system_event",
    "enabled", "previous_enabled",
    # Counts (no PHI in a count)
    "input_tokens", "output_tokens", "token_count",
    "expert_count", "tool_count", "issue_count",
    # Agentic observability and caller-feedback events. Values are bounded
    # enums, booleans, numeric counts, or server-owned identifiers.
    "trace_count", "page_size", "actor_type", "task_id", "target_type",
    "feedback_count",
    "rating", "label_count", "reason_redacted", "deleted_count",
    # Phase A1D.3 (A1C-B-010 + A1C-B-011) — policy_decision + ABAC purpose.
    # Structured fields emitted by the allow-side audit path; none can
    # carry PHI (rbac_role / abac_purpose_match are enum literals).
    "decision", "decision_reason", "rbac_role",
    "abac_purpose_match", "tenant_match", "purpose_of_use",
    # Phase A1D.5 — OAuth client identity (operational metadata, NOT PHI).
    # ``client_id`` is the public API client identifier (not a secret);
    # ``realm`` is the auth domain (e.g. "corti-cn"). Both are required
    # by the OAuth rejection audit path (test_oauth_audit_rejection.py).
    "client_id", "realm",
    # Phase A1D.7 (Pilot Prep Step 5a) — KMS rotation event metadata.
    # All three are integers (version numbers + cache entry count);
    # none can carry PHI. Required by the kms.key_rotated audit path
    # so operators can verify previous_version → current_version deltas.
    "previous_version", "current_version", "invalidated_entries",
    # Clinical-model governance, aggregate shadow observations and fenced
    # worker jobs. These are server-owned IDs, digests, enums, counts and
    # booleans only; bundle bytes, vectors, predictions and patient text are
    # never valid audit-detail values.
    "package_id", "package_key", "package_version", "package_sha256",
    "attestation_id", "binding_id", "evaluation_id", "job_id",
    "previous_package_id", "previous_attestation_id",
    "failed_package_id", "failed_attestation_id",
    "restored_package_id", "restored_attestation_id",
    "review_reference_sha256", "bundle_content_sha256", "manifest_sha256",
    "verification_report_sha256", "model_sha256", "suite_sha256",
    "observation_report_sha256", "request_sha256",
    "use_case", "fault_mode", "result", "artifact_source", "mode",
    "binding_version", "binding_record_version", "binding_version_after",
    "record_version", "four_eyes", "metadata_only", "bundle_stored",
    "patient_data_used", "patient_data_allowed", "raw_input_stored",
    "runtime_inference_enabled", "production_inference_enabled",
    "predictions_emitted", "network_used", "aggregate_only",
    "rollback_performed", "attempt_count", "max_attempts",
    "cancellation_reason", "cancelled_by_user_id",
    "dead_letter_status", "dead_letter_id", "source_job_id",
    "scheduler_name", "generation", "alert_code", "alert_state",
    "organizations_evaluated", "alerts_fired", "alerts_resolved",
    "recovered_after_expiry", "lease_seconds", "retry_scheduled",
    "test_vector_count", "run_count", "vector_observation_count",
    "success_count", "error_count", "mismatch_count",
})

# Keys that are explicitly PHI and always redacted at the top level.
# Listed separately so the log message can name them precisely.
_KNOWN_PHI_KEYS: frozenset[str] = frozenset({
    "patient_name", "patient_id", "patient_dob", "patient_address",
    "patient_phone", "patient_id_card_number",
    "mrn", "medical_record_number",
    "input_text", "output_text", "input_summary", "output_summary",
    "model_input", "model_output",
    "model_input_summary", "model_output_summary",
    "evidence_quote", "query_text", "free_text_response",
    "discharge_summary", "admission_reason",
    "raw_prompt", "raw_completion",
    "phi", "phi_fields",
})

# Maximum length of audit ``model_*_summary`` columns. Anything beyond
# this is truncated before redaction; the audit summary should be a
# preview, not a transcript.
MAX_SUMMARY_LEN = 200

_REDACTED = "[REDACTED]"


def redact_audit_details(details: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Return an audit-safe copy of ``details``.

    Top-level strategy:
      - ``None`` → ``None`` (preserve nullable column).
      - Empty dict → empty dict.
      - For each top-level key:
        * key in ``_ALLOWED_DETAIL_KEYS`` → keep value as-is.
        * key in ``_KNOWN_PHI_KEYS`` → replace value with ``"[REDACTED]"``
          and log a warning (emit-site bug).
        * any other key → replace value with ``"[REDACTED]"`` and log
          at info level (defensive; treats unknown as PHI).

    Nested values (dicts/lists inside a top-level value) are NOT
    deep-walked — the audit hot path can't afford that cost. The
    contract is that emit sites put operational metadata at the top
    level and free-form content under a known PHI key (which is
    redacted wholesale).
    """
    if details is None:
        return None
    if not isinstance(details, dict) or not details:
        return details if isinstance(details, dict) else {}
    scrubbed: dict[str, Any] = {}
    for key, value in details.items():
        if key in _ALLOWED_DETAIL_KEYS:
            scrubbed[key] = value
            continue
        if key in _KNOWN_PHI_KEYS:
            logger.warning(
                "audit_detail_redactor: redacting known PHI key %r "
                "(emit-site should not write this to details)",
                key,
            )
        else:
            logger.info(
                "audit_detail_redactor: redacting unknown key %r "
                "(defensive — not in _ALLOWED_DETAIL_KEYS)",
                key,
            )
        scrubbed[key] = _REDACTED
    return scrubbed


def redact_audit_summary(text: Optional[str]) -> Optional[str]:
    """Return a truncated + redacted audit-safe preview of ``text``.

    Used for ``model_input_summary`` / ``model_output_summary``.
    Returns ``None`` for ``None`` input (preserve nullable column).
    """
    if text is None:
        return None
    if not text:
        return text
    # Truncate BEFORE redacting so the redactor doesn't pay the cost
    # of processing a huge transcript. The preview contract is "first
    # N chars", not "first N chars of redacted text".
    truncated = text[:MAX_SUMMARY_LEN]
    # Use the fail-closed phi_redactor. If it returns the placeholder,
    # the audit row will visibly show the redaction failure rather
    # than leak the original.
    from app.services.phi_redactor import redact_for_export
    return redact_for_export(truncated)


__all__ = [
    "redact_audit_details",
    "redact_audit_summary",
    "MAX_SUMMARY_LEN",
]
