"""Build the authoritative Agent Hub runtime/readiness inventory.

The report deliberately separates user-visible Agents from hidden internal or
compatibility Packs.  It is safe to run in a development environment: no app
server, LLM, browser, database, or network connection is required.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from icoder_runtime.backends.registry import get_default_registry
from icoder_runtime.backends.output_contract_validation import (
    declared_evidence_bindings,
    declared_cross_agent_relations,
    declared_field_relations,
    declared_field_schemas,
    declared_field_types,
    validate_declared_field_schemas,
    validate_cross_agent_relations_definition,
    validate_evidence_bindings_definition,
    validate_field_relations_definition,
    validate_required_field_types,
)
from icoder_runtime.core.agent_pack_loader import load_packs_from_dir
from icoder_runtime.core.agent_pack_schema import PackStatus
from icoder_runtime.core.agent_execution_paths import (
    DEDICATED_AGENT_EXECUTION_PATHS,
    EXTERNAL_LLM_EXECUTION_TARGETS,
    LOCAL_BASELINE_EXECUTION_TARGETS,
    LOCAL_DETERMINISTIC_EXECUTION_TARGETS,
    OPTIONAL_EXTERNAL_LLM_EXECUTION_TARGETS,
    runtime_dependencies_for_target,
)


DEFAULT_AGENTS_DIR = BACKEND_ROOT / "official_agents"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT.parent / "reports" / "agent_hub"


def _agent_id(agent_ref: str) -> str:
    return agent_ref.rsplit("/", 1)[-1].split("@", 1)[0]


def _provider_resolution(pack: Any, agent_id: str) -> tuple[bool, str, str, str]:
    if pack.status != PackStatus.EXECUTABLE:
        return False, "not_executable", "unroutable", "not_executable"
    dedicated = DEDICATED_AGENT_EXECUTION_PATHS.get(agent_id)
    if dedicated is not None:
        return (
            True,
            dedicated["execution_target"],
            dedicated["execution_path"],
            "dedicated_handler",
        )
    if not pack.backend_provider:
        return False, "missing_backend_provider", "legacy_default", "legacy_default"
    try:
        provider = get_default_registry().resolve_from_agent_pack(pack.raw)
    except Exception as exc:  # the exception type belongs in the report only
        return False, type(exc).__name__, "provider_registry", "explicit_pack"
    return (
        True,
        str(getattr(provider, "provider_id", "")),
        "provider_registry",
        "explicit_pack",
    )


def _runtime_dependency(target: str) -> tuple[list[str], str]:
    """Describe what provider resolution alone cannot prove.

    This inventory is intentionally offline.  Importing a provider class is a
    structural routing check, not evidence that an external model produced a
    clinically meaningful result.  Keep that distinction machine-readable so
    downstream release reports cannot turn a resolvable class into a semantic
    capability pass.
    """
    dependencies = runtime_dependencies_for_target(target)
    if target in EXTERNAL_LLM_EXECUTION_TARGETS:
        return (dependencies, "safe_fail_closed_without_external_provider")
    if target in LOCAL_DETERMINISTIC_EXECUTION_TARGETS:
        return (dependencies, "local_deterministic_execution")
    if target in OPTIONAL_EXTERNAL_LLM_EXECUTION_TARGETS:
        return (dependencies, "local_baseline_with_optional_external_provider")
    return (dependencies, "requires_runtime_e2e_classification")


def _refresh_semantic_summaries(matrix: dict[str, Any]) -> None:
    """Refresh evidence counters after one or more validated bundles are applied."""
    visible = [row for row in matrix["rows"] if row["hub_visible"]]
    matrix["summary"]["visible_semantic_live_e2e_verified"] = sum(
        row["semantic_live_e2e_verified"] for row in visible
    )
    matrix["summary"]["visible_semantic_live_e2e_pending"] = [
        row["agent_id"]
        for row in visible
        if not row["semantic_live_e2e_verified"]
    ]
    matrix["summary"]["visible_external_semantic_live_e2e_pending"] = [
        row["agent_id"]
        for row in visible
        if row["external_llm_dependent"]
        and not row["semantic_live_e2e_verified"]
    ]
    matrix["summary"]["visible_local_semantic_e2e_verified"] = sum(
        row["local_semantic_e2e_verified"] for row in visible
    )
    matrix["summary"]["visible_local_semantic_e2e_pending"] = [
        row["agent_id"]
        for row in visible
        if row["offline_execution_expectation"]
        in {
            "local_deterministic_execution",
            "local_baseline_with_optional_external_provider",
        }
        and not row["local_semantic_e2e_verified"]
    ]


def build_matrix(
    agents_dir: Path,
    *,
    semantic_evidence_path: Path | None = None,
    semantic_max_age_hours: float = 24.0,
    local_semantic_evidence_path: Path | None = None,
    local_semantic_max_age_hours: float = 24.0,
    semantic_now: datetime | None = None,
) -> dict[str, Any]:
    packs = load_packs_from_dir(agents_dir)
    registry_path = agents_dir / "output_contract_registry.json"
    registry_payload = (
        json.loads(registry_path.read_text(encoding="utf-8"))
        if registry_path.exists() else {}
    )
    registered_contracts = registry_payload.get("contracts") or {}
    rows: list[dict[str, Any]] = []
    for pack in packs:
        manifest = pack.raw.get("manifest") or {}
        hidden = manifest.get("hidden_from_hub") is True
        declared_visible = not hidden and pack.agent_type not in {
            "expert-stub",
            "internal_engine",
        }
        agent_id = _agent_id(pack.agent_ref)
        (
            provider_resolves,
            resolved_provider,
            execution_path,
            provider_resolution_mode,
        ) = _provider_resolution(pack, agent_id)
        runtime_dependencies, offline_execution_expectation = _runtime_dependency(
            resolved_provider
        )
        maturity = str(manifest.get("maturity") or "")
        runnable = (
            pack.status == PackStatus.EXECUTABLE
            and maturity in {"runnable", "production-ready", "production"}
            and bool(pack.backend_provider or pack.a2a.get("endpoint") or pack.experts or pack.code)
        )
        hub_visible = (
            declared_visible
            and runnable
            and pack.launch_candidate_ready
            and provider_resolves
        )
        required_fields = list(pack.output_contract.get("required_fields") or [])
        optional_fields = list(pack.output_contract.get("optional_fields") or [])
        field_types = declared_field_types(pack.output_contract)
        field_schemas = declared_field_schemas(pack.output_contract)
        field_relations = declared_field_relations(pack.output_contract)
        evidence_bindings = declared_evidence_bindings(pack.output_contract)
        cross_agent_relations = declared_cross_agent_relations(pack.output_contract)
        declared_fields = required_fields + optional_fields
        contract_complete_examples = [
            example
            for example in pack.example_outputs
            if isinstance(example, dict)
            and all(field in example for field in required_fields)
        ]
        type_complete_examples = [
            example
            for example in contract_complete_examples
            if not validate_required_field_types(example, pack.output_contract)
        ]
        schema_complete_examples = [
            example
            for example in type_complete_examples
            if not validate_declared_field_schemas(example, pack.output_contract)
        ]
        registered = registered_contracts.get(
            str(pack.output_contract.get("schema_ref") or "")
        )
        public_contract = {
            "required_fields": required_fields,
            "optional_fields": optional_fields,
            "field_types": field_types,
            "field_schemas": field_schemas,
        }
        if "field_relations" in pack.output_contract:
            public_contract["field_relations"] = field_relations
        if "evidence_bindings" in pack.output_contract:
            public_contract["evidence_bindings"] = evidence_bindings
        if "cross_agent_relations" in pack.output_contract:
            public_contract["cross_agent_relations"] = cross_agent_relations
        rows.append({
            "agent_id": agent_id,
            "agent_ref": pack.agent_ref,
            "name": pack.name,
            "agent_type": pack.agent_type,
            "pack_status": pack.status.value,
            "maturity": maturity,
            "manifest_production_ready": bool(manifest.get("production_ready", False)),
            "hidden_from_hub": hidden,
            "hub_declared_visible": declared_visible,
            "hub_visible": hub_visible,
            "enabled_by_default": pack.enabled_by_default,
            "backend_provider": pack.backend_provider,
            "provider_resolves": provider_resolves,
            "resolved_provider": resolved_provider,
            "execution_path": execution_path,
            "execution_target": resolved_provider,
            "provider_resolution_mode": provider_resolution_mode,
            "runtime_dependencies": runtime_dependencies,
            "external_llm_dependent": resolved_provider
            in EXTERNAL_LLM_EXECUTION_TARGETS,
            "external_llm_optional": resolved_provider
            in OPTIONAL_EXTERNAL_LLM_EXECUTION_TARGETS,
            "local_baseline_available": resolved_provider
            in LOCAL_BASELINE_EXECUTION_TARGETS,
            "offline_execution_expectation": offline_execution_expectation,
            # A static inventory never establishes semantic or clinical
            # quality.  Live evidence must be attached by the dedicated E2E
            # and clinical evaluation reports instead of inferred here.
            "semantic_e2e_required": True,
            "semantic_live_e2e_verified": False,
            "semantic_verification_source": "",
            # This narrower signal is intentionally independent of the strict
            # 26-Agent live-provider gate above.  Only the authoritative local
            # deterministic/baseline subset may ever receive it.
            "local_semantic_e2e_verified": False,
            "local_semantic_verification_source": "",
            "output_schema_ref": str(pack.output_contract.get("schema_ref") or ""),
            "required_output_fields": required_fields,
            "optional_output_fields": optional_fields,
            "declared_output_field_types": field_types,
            "declared_output_field_schemas": field_schemas,
            "declared_output_field_relations": field_relations,
            "field_relation_count": len(field_relations),
            "field_relations_valid": not validate_field_relations_definition(
                pack.output_contract
            ),
            "declared_evidence_bindings": evidence_bindings,
            "evidence_binding_count": len(evidence_bindings),
            "evidence_bindings_valid": not validate_evidence_bindings_definition(
                pack.output_contract
            ),
            "declared_cross_agent_relations": cross_agent_relations,
            "cross_agent_relation_count": len(cross_agent_relations),
            "cross_agent_relations_valid": not validate_cross_agent_relations_definition(
                pack.output_contract
            ),
            "type_contract_complete": bool(required_fields)
            and all(
                field in field_types for field in required_fields + optional_fields
            ),
            "example_input_count": len(pack.example_inputs),
            "example_output_count": len(pack.example_outputs),
            "contract_complete_example_outputs": len(contract_complete_examples),
            "type_complete_example_outputs": len(type_complete_examples),
            "value_schema_contract_complete": set(field_schemas) == set(declared_fields),
            "nested_schema_contract_complete": set(field_schemas) == set(declared_fields),
            "nested_schema_valid_example_outputs": len(schema_complete_examples),
            "contract_registry_match": bool(
                isinstance(registered, dict)
                and registered.get("contract") == public_contract
            ),
            "optional_fields_with_examples": sum(
                any(field in example for example in pack.example_outputs)
                for field in optional_fields
            ),
            "undeclared_example_output_fields": sorted({
                field
                for example in pack.example_outputs
                if isinstance(example, dict)
                for field in example
                if field not in set(required_fields + optional_fields)
            }),
            "phi_redaction": pack.phi_redaction,
            "context_required": pack.context_required,
            "recorder_required": pack.recorder_required,
            "metrics_required": pack.metrics_required,
            "production_writeback_blocked": bool(
                pack.permissions.get("production_writeback_blocked", False)
            ),
            "launch_candidate_ready": pack.launch_candidate_ready,
            "launch_candidate_blockers": list(pack.launch_candidate_blockers),
            "external_release_gates": list(pack.external_release_gates),
        })

    declared_visible = [row for row in rows if row["hub_declared_visible"]]
    visible = [row for row in rows if row["hub_visible"]]
    hidden = [row for row in rows if not row["hub_visible"]]
    visible_not_ready = [
        row["agent_id"]
        for row in declared_visible
        if (
            not row["hub_visible"]
            or not row["launch_candidate_ready"]
            or not row["provider_resolves"]
            or not row["type_contract_complete"]
            or row["type_complete_example_outputs"] == 0
            or not row["nested_schema_contract_complete"]
            or row["nested_schema_valid_example_outputs"] == 0
            or not row["contract_registry_match"]
            or not row["field_relations_valid"]
            or not row["evidence_bindings_valid"]
            or not row["cross_agent_relations_valid"]
            or row["optional_fields_with_examples"]
            != len(row["optional_output_fields"])
            or bool(row["undeclared_example_output_fields"])
        )
    ]
    matrix = {
        "schema_version": "icoder.agent-hub-runtime-matrix/v3",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(agents_dir),
        "semantic_evidence": {
            "provided": semantic_evidence_path is not None,
            "valid": False,
            "bundle_path": str(semantic_evidence_path.resolve())
            if semantic_evidence_path is not None
            else "",
            "bundle_sha256": "",
            "errors": [],
        },
        "local_semantic_evidence": {
            "provided": local_semantic_evidence_path is not None,
            "valid": False,
            "bundle_path": str(local_semantic_evidence_path.resolve())
            if local_semantic_evidence_path is not None
            else "",
            "bundle_sha256": "",
            "errors": [],
            "derived_from_semantic_evidence": False,
            "derived_scope": "",
            "derived_bundle_path": "",
            "derived_bundle_sha256": "",
            "scope": (
                "twenty_four_local_deterministic_or_governed_baseline_agents_only;"
                "not_the_strict_26_agent_live_provider_gate"
            ),
        },
        "summary": {
            "disk_packs": len(rows),
            "hub_declared_visible_packs": len(declared_visible),
            "hub_visible_agents": len(visible),
            "hub_declared_visible_excluded": [
                row["agent_id"] for row in declared_visible if not row["hub_visible"]
            ],
            "hidden_packs": len(hidden),
            "visible_executable": sum(
                row["pack_status"] == PackStatus.EXECUTABLE.value for row in visible
            ),
            "visible_provider_resolvable": sum(
                row["provider_resolves"] for row in visible
            ),
            "visible_provider_registry_routes": sum(
                row["execution_path"] == "provider_registry" for row in visible
            ),
            "visible_dedicated_routes": sum(
                row["provider_resolution_mode"] == "dedicated_handler"
                for row in visible
            ),
            "visible_legacy_default_routes": [
                row["agent_id"]
                for row in visible
                if row["provider_resolution_mode"] == "legacy_default"
            ],
            "visible_launch_candidate_ready": sum(
                row["launch_candidate_ready"] for row in visible
            ),
            "visible_external_llm_dependent": sum(
                row["external_llm_dependent"] for row in visible
            ),
            "visible_external_llm_optional": sum(
                row["external_llm_optional"] for row in visible
            ),
            "visible_local_only_execution": sum(
                row["execution_target"] in LOCAL_DETERMINISTIC_EXECUTION_TARGETS
                for row in visible
            ),
            "visible_local_baseline_available": sum(
                row["local_baseline_available"] for row in visible
            ),
            "visible_offline_safe_fail_closed_expected": sum(
                row["offline_execution_expectation"]
                == "safe_fail_closed_without_external_provider"
                for row in visible
            ),
            "visible_semantic_live_e2e_verified": sum(
                row["semantic_live_e2e_verified"] for row in visible
            ),
            "visible_semantic_live_e2e_pending": [
                row["agent_id"]
                for row in visible
                if not row["semantic_live_e2e_verified"]
            ],
            "visible_local_semantic_e2e_verified": sum(
                row["local_semantic_e2e_verified"] for row in visible
            ),
            "visible_local_semantic_e2e_pending": [
                row["agent_id"]
                for row in visible
                if row["offline_execution_expectation"]
                in {
                    "local_deterministic_execution",
                    "local_baseline_with_optional_external_provider",
                }
                and not row["local_semantic_e2e_verified"]
            ],
            "visible_external_semantic_live_e2e_pending": [
                row["agent_id"]
                for row in visible
                if row["external_llm_dependent"]
                and not row["semantic_live_e2e_verified"]
            ],
            "visible_production_ready_verified": sum(
                row["manifest_production_ready"] for row in visible
            ),
            "visible_with_contract_complete_examples": sum(
                row["contract_complete_example_outputs"] > 0
                for row in visible
            ),
            "visible_with_complete_type_contracts": sum(
                row["type_contract_complete"] for row in visible
            ),
            "visible_with_type_valid_examples": sum(
                row["type_complete_example_outputs"] > 0 for row in visible
            ),
            "visible_with_complete_nested_schemas": sum(
                row["nested_schema_contract_complete"] for row in visible
            ),
            "visible_with_nested_schema_valid_examples": sum(
                row["nested_schema_valid_example_outputs"] > 0 for row in visible
            ),
            "visible_with_valid_field_relations": sum(
                row["field_relations_valid"] for row in visible
            ),
            "visible_with_valid_evidence_bindings": sum(
                row["evidence_bindings_valid"] for row in visible
            ),
            "visible_evidence_binding_count": sum(
                row["evidence_binding_count"] for row in visible
            ),
            "visible_with_valid_cross_agent_relations": sum(
                row["cross_agent_relations_valid"] for row in visible
            ),
            "visible_cross_agent_relation_count": sum(
                row["cross_agent_relation_count"] for row in visible
            ),
            "visible_field_relation_count": sum(
                row["field_relation_count"] for row in visible
            ),
            "visible_with_immutable_registered_contracts": sum(
                row["contract_registry_match"] for row in visible
            ),
            "visible_with_strict_output_allowlists": sum(
                row["type_contract_complete"]
                and row["nested_schema_contract_complete"]
                and row["nested_schema_valid_example_outputs"] > 0
                and row["optional_fields_with_examples"]
                == len(row["optional_output_fields"])
                and not row["undeclared_example_output_fields"]
                for row in visible
            ),
            "visible_not_ready": visible_not_ready,
            "hidden_metadata_only": sum(
                row["pack_status"] == PackStatus.METADATA_ONLY.value for row in hidden
            ),
        },
        "rows": rows,
    }
    if semantic_evidence_path is not None:
        try:
            evidence_payload = json.loads(
                semantic_evidence_path.resolve().read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            evidence_payload = {}
        is_composite_bundle = evidence_payload.get("schema_version") == (
            "icoder.agent-hub-composite-semantic-evidence-bundle/v1"
        )
        if is_composite_bundle:
            from scripts.corti_parity.build_agent_hub_composite_semantic_evidence_bundle import (
                validate_composite_bundle_file as validate_bundle_file,
            )
        else:
            from scripts.corti_parity.build_agent_hub_semantic_evidence_bundle import (
                validate_bundle_file,
            )

        validation = validate_bundle_file(
            semantic_evidence_path.resolve(),
            agents_dir=agents_dir,
            max_age_hours=semantic_max_age_hours,
            now=semantic_now,
            matrix=matrix,
        )
        matrix["semantic_evidence"].update({
            "valid": validation["valid"],
            "bundle_sha256": validation.get("bundle_sha256", ""),
            "errors": list(validation.get("errors") or []),
        })
        verified = set(validation.get("verified_agent_ids") or [])
        source = (
            f"{semantic_evidence_path.resolve()}#"
            f"{validation.get('bundle_sha256', '')}"
        )
        for row in matrix["rows"]:
            row["semantic_live_e2e_verified"] = bool(
                row["hub_visible"] and row["agent_id"] in verified
            )
            row["semantic_verification_source"] = (
                source if row["semantic_live_e2e_verified"] else ""
            )
        if validation["valid"]:
            # A strict full bundle proves semantic execution for every verified
            # Agent.  It also proves the local path for execution targets that
            # are structurally deterministic and cannot call an external LLM.
            # The optional-provider Agent is deliberately excluded unless the
            # full bundle is a composite containing a separately validated
            # 24-Agent local component.
            derived_expectations = {"local_deterministic_execution"}
            derived_scope = "structural_local_deterministic_subset_only"
            if is_composite_bundle:
                derived_expectations.add(
                    "local_baseline_with_optional_external_provider"
                )
                derived_scope = "composite_validated_local_component"
            matrix["local_semantic_evidence"].update({
                "derived_from_semantic_evidence": True,
                "derived_scope": derived_scope,
                "derived_bundle_path": str(semantic_evidence_path.resolve()),
                "derived_bundle_sha256": validation.get("bundle_sha256", ""),
            })
            for row in matrix["rows"]:
                row["local_semantic_e2e_verified"] = bool(
                    row["hub_visible"]
                    and row["agent_id"] in verified
                    and row["offline_execution_expectation"]
                    in derived_expectations
                )
                row["local_semantic_verification_source"] = (
                    source if row["local_semantic_e2e_verified"] else ""
                )
        _refresh_semantic_summaries(matrix)
    if local_semantic_evidence_path is not None:
        from scripts.corti_parity.build_agent_hub_local_semantic_evidence_bundle import (
            validate_local_bundle_file,
        )

        validation = validate_local_bundle_file(
            local_semantic_evidence_path.resolve(),
            agents_dir=agents_dir,
            max_age_hours=local_semantic_max_age_hours,
            now=semantic_now,
            matrix=matrix,
        )
        matrix["local_semantic_evidence"].update({
            "valid": validation["valid"],
            "bundle_sha256": validation.get("bundle_sha256", ""),
            "errors": list(validation.get("errors") or []),
        })
        verified = set(validation.get("verified_agent_ids") or [])
        source = (
            f"{local_semantic_evidence_path.resolve()}#"
            f"{validation.get('bundle_sha256', '')}"
        )
        if validation["valid"]:
            for row in matrix["rows"]:
                is_local_scope = row["offline_execution_expectation"] in {
                    "local_deterministic_execution",
                    "local_baseline_with_optional_external_provider",
                }
                row["local_semantic_e2e_verified"] = bool(
                    row["hub_visible"]
                    and is_local_scope
                    and row["agent_id"] in verified
                )
                row["local_semantic_verification_source"] = (
                    source if row["local_semantic_e2e_verified"] else ""
                )
        _refresh_semantic_summaries(matrix)
    return matrix


def render_markdown(matrix: dict[str, Any]) -> str:
    summary = matrix["summary"]
    lines = [
        "# Agent Hub runtime matrix",
        "",
        f"Generated: `{matrix['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Disk Packs: {summary['disk_packs']}",
        f"- Hub-visible Agents: {summary['hub_visible_agents']}",
        f"- Visible executable: {summary['visible_executable']}",
        f"- Visible provider-resolvable: {summary['visible_provider_resolvable']}",
        f"- Visible structural development launch candidates: {summary['visible_launch_candidate_ready']}",
        f"- Visible dependent on an external LLM: {summary['visible_external_llm_dependent']}",
        f"- Visible with optional external-LLM enhancement: {summary['visible_external_llm_optional']}",
        f"- Visible with local-only execution: {summary['visible_local_only_execution']}",
        f"- Visible with an offline local baseline: {summary['visible_local_baseline_available']}",
        f"- Offline safe-fail-closed expected: {summary['visible_offline_safe_fail_closed_expected']}",
        f"- Semantic live E2E verified by a validated evidence bundle: {summary['visible_semantic_live_e2e_verified']}",
        f"- Local deterministic/baseline semantic HTTP E2E verified (limited twenty-four-Agent scope): {summary['visible_local_semantic_e2e_verified']}",
        f"- Production-ready verified: {summary['visible_production_ready_verified']}",
        f"- Visible with contract-complete examples: {summary['visible_with_contract_complete_examples']}",
        f"- Visible with complete field-type contracts: {summary['visible_with_complete_type_contracts']}",
        f"- Visible with type-valid examples: {summary['visible_with_type_valid_examples']}",
        f"- Visible with complete nested schemas: {summary['visible_with_complete_nested_schemas']}",
        f"- Visible with nested-schema-valid examples: {summary['visible_with_nested_schema_valid_examples']}",
        f"- Visible with valid cross-field relations: {summary['visible_with_valid_field_relations']}",
        f"- Visible with valid evidence bindings: {summary['visible_with_valid_evidence_bindings']}",
        f"- Declared evidence bindings: {summary['visible_evidence_binding_count']}",
        f"- Visible with valid cross-Agent relations: {summary['visible_with_valid_cross_agent_relations']}",
        f"- Declared cross-Agent relations: {summary['visible_cross_agent_relation_count']}",
        f"- Declared cross-field relations: {summary['visible_field_relation_count']}",
        f"- Visible with immutable registered contracts: {summary['visible_with_immutable_registered_contracts']}",
        f"- Visible with strict output allowlists: {summary['visible_with_strict_output_allowlists']}",
        f"- Hidden Packs: {summary['hidden_packs']} (metadata-only: {summary['hidden_metadata_only']})",
        "",
        "> Development launch-candidate readiness does not satisfy the external",
        "> clinical, hospital integration, security/privacy, compliance, or",
        "> production-operations release gates listed per Pack.",
        "> Provider resolution is structural only. It is not a clinical or",
        "> semantic capability pass; live-provider evidence remains separate.",
        "> Local semantic evidence covers only deterministic/governed-baseline",
        "> Agents and cannot satisfy the strict 26-Agent live-provider gate.",
        "",
        "## Inventory",
        "",
        "| Agent | Visibility | Status | Execution path | Target | Offline expectation | Full semantic live E2E | Local semantic E2E | Candidate |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for row in matrix["rows"]:
        blockers = "; ".join(row["launch_candidate_blockers"])
        candidate = "yes" if row["launch_candidate_ready"] else f"no — {blockers}"
        lines.append(
            "| {agent_id} | {visibility} | {status} | {path} | {provider} | {offline} | {semantic} | {local_semantic} | {candidate} |".format(
                agent_id=row["agent_id"],
                visibility="Hub" if row["hub_visible"] else "hidden",
                status=row["pack_status"],
                path=row["execution_path"],
                provider=row["resolved_provider"] or row["backend_provider"] or "—",
                offline=row["offline_execution_expectation"],
                semantic=(
                    "verified" if row["semantic_live_e2e_verified"] else "pending"
                ),
                local_semantic=(
                    "verified" if row["local_semantic_e2e_verified"] else "n/a or pending"
                ),
                candidate=candidate.replace("|", "\\|"),
            )
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--assert-visible-ready", action="store_true")
    parser.add_argument("--semantic-evidence", type=Path)
    parser.add_argument("--semantic-max-age-hours", type=float, default=24.0)
    parser.add_argument("--local-semantic-evidence", type=Path)
    parser.add_argument("--local-semantic-max-age-hours", type=float, default=24.0)
    args = parser.parse_args()

    matrix = build_matrix(
        args.agents_dir.resolve(),
        semantic_evidence_path=args.semantic_evidence,
        semantic_max_age_hours=args.semantic_max_age_hours,
        local_semantic_evidence_path=args.local_semantic_evidence,
        local_semantic_max_age_hours=args.local_semantic_max_age_hours,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / "agent_hub_runtime_matrix.json"
    md_path = args.output_dir / "agent_hub_runtime_matrix.md"
    json_path.write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md_path.write_text(render_markdown(matrix), encoding="utf-8")
    print(json.dumps(matrix["summary"], ensure_ascii=False))
    print(json_path)
    print(md_path)

    if args.assert_visible_ready and matrix["summary"]["visible_not_ready"]:
        return 1
    if args.semantic_evidence is not None and not matrix["semantic_evidence"]["valid"]:
        return 1
    if (
        args.local_semantic_evidence is not None
        and not matrix["local_semantic_evidence"]["valid"]
    ):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
