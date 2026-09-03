from copy import deepcopy
from pathlib import Path

from app.icoder.agent_runtime.a2a.agent_card import (
    agent_card_from_pack,
    medical_coding_agent_card,
)
from app.api.icoder_agents_hub import _build_card, _is_visible
from icoder_runtime.core.agent_execution_paths import (
    DEDICATED_AGENT_EXECUTION_PATHS,
)
from icoder_runtime.core.agent_pack_loader import load_packs_from_dir
from scripts.corti_parity.build_agent_hub_runtime_matrix import build_matrix


BACKEND_ROOT = Path(__file__).resolve().parents[3]


def test_runtime_matrix_separates_visible_agents_from_hidden_packs() -> None:
    matrix = build_matrix(BACKEND_ROOT / "official_agents")
    summary = matrix["summary"]

    assert summary["disk_packs"] == 32
    assert summary["hub_declared_visible_packs"] == 26
    assert summary["hub_visible_agents"] == 26
    assert summary["hub_declared_visible_excluded"] == []
    assert summary["hidden_packs"] == 6
    assert summary["hidden_metadata_only"] == 5


def test_all_hub_visible_agents_pass_development_runtime_gates() -> None:
    matrix = build_matrix(BACKEND_ROOT / "official_agents")
    summary = matrix["summary"]

    assert summary["visible_executable"] == 26
    assert summary["visible_provider_resolvable"] == 26
    assert summary["visible_provider_registry_routes"] == 21
    assert summary["visible_dedicated_routes"] == 5
    assert summary["visible_legacy_default_routes"] == []
    assert summary["visible_launch_candidate_ready"] == 26
    assert summary["visible_external_llm_dependent"] == 2
    assert summary["visible_external_llm_optional"] == 1
    assert summary["visible_local_only_execution"] == 23
    assert summary["visible_local_baseline_available"] == 24
    assert summary["visible_offline_safe_fail_closed_expected"] == 2
    assert summary["visible_semantic_live_e2e_verified"] == 0
    assert len(summary["visible_semantic_live_e2e_pending"]) == 26
    assert summary["visible_production_ready_verified"] == 0
    assert summary["visible_with_contract_complete_examples"] == 26
    assert summary["visible_with_complete_type_contracts"] == 26
    assert summary["visible_with_type_valid_examples"] == 26
    assert summary["visible_with_strict_output_allowlists"] == 26
    assert summary["visible_evidence_binding_count"] == 30
    assert summary["visible_field_relation_count"] == 110
    assert summary["visible_with_valid_evidence_bindings"] == 26
    assert summary["visible_cross_agent_relation_count"] == 10
    assert summary["visible_with_valid_cross_agent_relations"] == 26
    assert summary["visible_not_ready"] == []


def test_runtime_matrix_does_not_misreport_resolution_as_semantic_evidence() -> None:
    matrix = build_matrix(BACKEND_ROOT / "official_agents")
    visible = [row for row in matrix["rows"] if row["hub_visible"]]

    assert matrix["schema_version"] == "icoder.agent-hub-runtime-matrix/v3"
    assert matrix["semantic_evidence"] == {
        "provided": False,
        "valid": False,
        "bundle_path": "",
        "bundle_sha256": "",
        "errors": [],
    }
    assert matrix["local_semantic_evidence"] == {
        "provided": False,
        "valid": False,
        "bundle_path": "",
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
    }
    assert matrix["summary"]["visible_local_semantic_e2e_verified"] == 0
    assert len(matrix["summary"]["visible_local_semantic_e2e_pending"]) == 24
    assert len(matrix["summary"]["visible_external_semantic_live_e2e_pending"]) == 2
    assert all(row["semantic_e2e_required"] is True for row in visible)
    assert all(row["semantic_live_e2e_verified"] is False for row in visible)
    assert all(not row["semantic_verification_source"] for row in visible)
    assert all(row["local_semantic_e2e_verified"] is False for row in visible)
    assert all(not row["local_semantic_verification_source"] for row in visible)

    external = [row for row in visible if row["external_llm_dependent"]]
    assert len(external) == 2
    assert all(
        row["offline_execution_expectation"]
        == "safe_fail_closed_without_external_provider"
        for row in external
    )

    local_only = [
        row for row in visible
        if row["offline_execution_expectation"] == "local_deterministic_execution"
    ]
    assert [row["agent_id"] for row in local_only] == [
        "claim-check",
        "clinical-education",
        "clinical-guidelines",
        "compliance-guardrail-agent",
        "denial-appeals",
        "diagnosis-extractor",
        "discharge-edu",
        "discharge-summary-structuring",
        "drg-analyzer",
        "evidence-ranker",
        "evidence-extractor",
        "icd10-navigator",
        "icu-summary",
        "med-reconciliation",
        "note-completeness-agent",
        "nursing-handoff",
        "principal-diagnosis-review",
        "prior-auth",
        "procedure-extractor",
        "referral-gen",
        "rule-explainer",
        "surgical-registry",
        "triage",
    ]
    optional = [row for row in visible if row["external_llm_optional"]]
    assert [row["agent_id"] for row in optional] == ["code-validation-agent"]
    assert optional[0]["offline_execution_expectation"] == (
        "local_baseline_with_optional_external_provider"
    )


def test_runtime_matrix_reports_the_exact_dedicated_execution_paths() -> None:
    matrix = build_matrix(BACKEND_ROOT / "official_agents")
    visible_rows = {
        row["agent_id"]: row
        for row in matrix["rows"]
        if row["hub_visible"]
    }

    assert {
        agent_id: {
            "execution_path": visible_rows[agent_id]["execution_path"],
            "execution_target": visible_rows[agent_id]["execution_target"],
        }
        for agent_id in DEDICATED_AGENT_EXECUTION_PATHS
    } == DEDICATED_AGENT_EXECUTION_PATHS

    provider_rows = [
        row for row in visible_rows.values()
        if row["agent_id"] not in DEDICATED_AGENT_EXECUTION_PATHS
    ]
    assert len(provider_rows) == 21
    assert all(row["execution_path"] == "provider_registry" for row in provider_rows)
    assert all(row["provider_resolution_mode"] == "explicit_pack" for row in provider_rows)


def test_hidden_metadata_packs_never_leak_into_hub_inventory() -> None:
    matrix = build_matrix(BACKEND_ROOT / "official_agents")
    offenders = [
        row["agent_id"]
        for row in matrix["rows"]
        if row["pack_status"] == "metadata_only" and row["hub_visible"]
    ]
    assert offenders == []


def test_hub_visibility_fails_closed_for_placeholder_and_unknown_provider() -> None:
    packs = load_packs_from_dir(BACKEND_ROOT / "official_agents")
    source = next(pack for pack in packs if pack.agent_ref.startswith("icoder/diagnosis-extractor@"))
    assert _is_visible(source.raw) is True

    placeholder = deepcopy(source.raw)
    placeholder.pop("integrity", None)
    placeholder["manifest"]["maturity"] = "metadata-only"
    assert _is_visible(placeholder) is False

    legacy_mvp = deepcopy(source.raw)
    legacy_mvp.pop("integrity", None)
    legacy_mvp["manifest"]["maturity"] = "mvp"
    assert _is_visible(legacy_mvp) is False

    unresolved = deepcopy(source.raw)
    unresolved.pop("integrity", None)
    unresolved["backend_provider"] = "icoder.provider-does-not-exist.v1"
    assert _is_visible(unresolved) is False


def test_every_visible_agent_card_declares_shared_streaming_transport() -> None:
    visible = [
        pack
        for pack in load_packs_from_dir(BACKEND_ROOT / "official_agents")
        if (pack.raw.get("manifest") or {}).get("hidden_from_hub") is not True
    ]

    assert len(visible) == 26
    assert all(agent_card_from_pack(pack.raw).capabilities.streaming for pack in visible)


def test_discovery_cards_expose_pack_maturity_and_execution_path() -> None:
    visible = [
        pack
        for pack in load_packs_from_dir(BACKEND_ROOT / "official_agents")
        if (pack.raw.get("manifest") or {}).get("hidden_from_hub") is not True
    ]

    for pack in visible:
        card = agent_card_from_pack(pack.raw)
        metadata = card.metadata["icoder"]
        manifest = pack.raw["manifest"]
        assert metadata["maturity"] == manifest["maturity"]
        assert metadata["production_ready"] is manifest["production_ready"]
        assert metadata["output_contract"] == pack.raw["output_contract"]
        assert metadata["execution_path"]
        assert metadata["execution_target"]

    medical = medical_coding_agent_card().metadata["icoder"]
    assert medical["maturity"] == "runnable"
    assert medical["execution_path"] == "dedicated.medical_coding_dispatcher"


def test_hub_cards_surface_machine_readable_field_types() -> None:
    visible = [
        pack
        for pack in load_packs_from_dir(BACKEND_ROOT / "official_agents")
        if (pack.raw.get("manifest") or {}).get("hidden_from_hub") is not True
    ]

    for pack in visible:
        card = _build_card(pack.raw)
        assert card["output_contract"]["field_types"] == (
            pack.raw["output_contract"]["field_types"]
        )
        assert card["output_contract"]["field_schemas"] == (
            pack.raw["output_contract"]["field_schemas"]
        )
        assert card["output_contract"]["cross_agent_relations"] == (
            pack.raw["output_contract"].get("cross_agent_relations") or []
        )
