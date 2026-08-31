"""Static deployment-candidate preflight for environments without Docker.

This validator deliberately distinguishes artifact validation from a real
image build, registry scan, cloud provisioning, or disaster-recovery drill.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from icoder_runtime.backends.output_contract_validation import (
    validate_declared_field_schemas,
    validate_cross_agent_relations_definition,
    validate_evidence_bindings_definition,
    validate_field_relations_definition,
    validate_field_schema_definition,
)
from scripts.corti_parity.validate_corti_prebuilt_agent_parity import (
    validate_catalog as validate_corti_prebuilt_agent_catalog,
)
from scripts.corti_parity.build_agent_hub_runtime_matrix import (
    build_matrix as build_agent_hub_runtime_matrix,
)
EXPECTED_BGE_REVISION = "5617a9f61b028005a4858fdac845db406aefb181"
EXPECTED_INDEX_VERSION = "cn-catalog-2026-06-26-bge-m3-5617a9f6"
EXPECTED_MEDCODER_ASSETS = {
    "faiss.index",
    "metadata.pkl",
    "faiss_icd9cm3.index",
    "metadata_icd9cm3.pkl",
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_manifest_is_valid(index_dir: Path) -> bool:
    try:
        manifest = json.loads(_read(index_dir / "asset_manifest.json"))
        model = manifest["embedding_model"]
        artifacts = manifest["artifacts"]
        if not (
            manifest.get("schema_version") == "icoder.medcoder-assets/v1"
            and manifest.get("index_version") == EXPECTED_INDEX_VERSION
            and model.get("repository") == "BAAI/bge-m3"
            and model.get("revision") == EXPECTED_BGE_REVISION
            and model.get("dimension") == 1024
            and set(artifacts) == EXPECTED_MEDCODER_ASSETS
        ):
            return False
        for name, metadata in artifacts.items():
            path = index_dir / name
            if (
                not path.is_file()
                or path.stat().st_size != metadata.get("size_bytes")
                or _sha256(path) != str(metadata.get("sha256") or "").casefold()
            ):
                return False
    except (KeyError, OSError, TypeError, ValueError):
        return False
    return True


def _code_catalog_assets_are_image_owned_and_fail_closed(root: Path) -> bool:
    backend_root = root / "backend"
    asset_root = backend_root / "data" / "code_dicts" / "assets"
    manifest_path = asset_root / "catalog_manifest.json"
    loader_path = backend_root / "data" / "code_dicts" / "icd_data.py"
    dockerfile_path = backend_root / "Dockerfile"
    dockerignore_path = backend_root / ".dockerignore"
    expected = {
        "icd10_opendrg_v1.json": (
            11_417_099,
            "3edb02423b30fa408f983a02941979955a3c0a36950974d52d1ff7e99b3dba09",
            33_304,
        ),
        "icd10_cn_standard_names.json": (
            5_990_261,
            "7aa0c2acab61596eb5e8b304ee891b06b94d788f87a17b97660ab1043806f0f9",
            37_897,
        ),
        "procedure_icd9cm3_knowledge_v8_with_opendrg.json": (
            4_644_580,
            "59d0accce8660da9d98e933b50b391cebb9c29357ee767148c878d834f42ac87",
            17_436,
        ),
        "surgery_to_drg_mapping.json": (
            12_692_746,
            "e9f5b3a1c7a23b6063f336930f3d59c7def1b9ef5fbbc947f30982a64fe1675b",
            23_165,
        ),
        "icd9cm3_code_catalog.json": (
            5_658_170,
            "4d0af72f8d5c3da5008741378ab97373f87f13775487cf5adcee6974cb4bca69",
            13_617,
        ),
    }
    try:
        manifest = json.loads(_read(manifest_path))
        files = manifest.get("files")
        loader = _read(loader_path)
        dockerfile = _read(dockerfile_path)
        dockerignore = _read(dockerignore_path)
        if (
            manifest.get("schema_version") != "icoder.code-catalog-assets/v1"
            or manifest.get("catalog_release") != "icoder-cn-runtime-2026-08-27.2"
            or not isinstance(files, dict)
            or set(files) != set(expected)
            or "CatalogIntegrityError" not in loader
            or "TRUSTED_CATALOG_FILES" not in loader
            or "using fallback" in loader
            or ' / "iCoDerA" / "data"' in loader
            or "COPY --chown=icoder:icoder . ." not in dockerfile
            or "data/code_dicts" in dockerignore
            or "assets/" in dockerignore
        ):
            return False
        for filename, (size_bytes, sha256, record_count) in expected.items():
            metadata = files.get(filename)
            path = asset_root / filename
            if (
                not isinstance(metadata, dict)
                or metadata.get("size_bytes") != size_bytes
                or metadata.get("sha256") != sha256
                or metadata.get("record_count") != record_count
                or not path.is_file()
                or path.stat().st_size != size_bytes
                or _sha256(path) != sha256
            ):
                return False
    except (OSError, TypeError, ValueError):
        return False
    return True


def _environment_map(service: dict[str, Any]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in service.get("environment") or []:
        if isinstance(item, str) and "=" in item:
            key, value = item.split("=", 1)
            values[key] = value
    return values


def _agent_template_catalog_is_pack_mastered() -> bool:
    """Verify the New Agent catalog is an exact Hub projection plus blanks."""

    try:
        from app.api.agents import get_agent_template_catalog
        from app.api.icoder_agents_hub import (
            load_visible_launch_candidate_packs,
            runtime_agent_id_from_ref,
        )

        catalog = get_agent_template_catalog()
        governed = {
            str(item.get("id") or "")
            for item in catalog
            if item.get("template_kind") == "governed_prebuilt"
        }
        generic = {
            str(item.get("id") or "")
            for item in catalog
            if item.get("template_kind") == "generic_blank"
        }
        visible = {
            runtime_agent_id_from_ref(str(pack.get("agent_ref") or ""))
            for pack in load_visible_launch_candidate_packs()
        }
        governed_items = [
            item
            for item in catalog
            if item.get("template_kind") == "governed_prebuilt"
        ]
        return (
            len(catalog) == 28
            and len(governed) == 26
            and governed == visible
            and generic == {"translator-blank", "summarizer-blank"}
            and all(
                item.get("clone_transport") == "agent_hub"
                and item.get("clone_url")
                == f"/api/icoder/agents/{item.get('runtime_agent_id')}/clone"
                and str(item.get("source_agent_ref") or "").startswith("icoder/")
                for item in governed_items
            )
        )
    except Exception:
        return False


def _agent_hub_typed_contracts_valid(agents_dir: Path) -> bool:
    supported = {"string", "boolean", "integer", "number", "object", "array"}
    registry_path = agents_dir / "output_contract_registry.json"
    try:
        registered_contracts = json.loads(_read(registry_path)).get("contracts") or {}
    except (OSError, TypeError, ValueError):
        return False

    def matches(value: Any, expected: str) -> bool:
        if expected == "string":
            return isinstance(value, str)
        if expected == "boolean":
            return isinstance(value, bool)
        if expected == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if expected == "number":
            return (
                isinstance(value, int) and not isinstance(value, bool)
            ) or (
                isinstance(value, float) and math.isfinite(value)
            )
        if expected == "object":
            return isinstance(value, dict)
        if expected == "array":
            return isinstance(value, list)
        return False

    visible = 0
    try:
        for path in sorted(agents_dir.glob("*/agent_pack.json")):
            pack = json.loads(_read(path))
            if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
                continue
            visible += 1
            contract = pack.get("output_contract") or {}
            required = contract.get("required_fields") or []
            optional = contract.get("optional_fields") or []
            field_types = contract.get("field_types") or {}
            field_schemas = contract.get("field_schemas") or {}
            field_relations = contract.get("field_relations") or []
            evidence_bindings = contract.get("evidence_bindings") or []
            cross_agent_relations = contract.get("cross_agent_relations") or []
            declared = required + optional
            registered = registered_contracts.get(str(contract.get("schema_ref") or ""))
            current_contract = {
                "required_fields": required,
                "optional_fields": optional,
                "field_types": field_types,
                "field_schemas": field_schemas,
            }
            if "field_relations" in contract:
                current_contract["field_relations"] = field_relations
            if "evidence_bindings" in contract:
                current_contract["evidence_bindings"] = evidence_bindings
            if "cross_agent_relations" in contract:
                current_contract["cross_agent_relations"] = cross_agent_relations
            if (
                not required
                or not isinstance(optional, list)
                or len(set(declared)) != len(declared)
                or not isinstance(field_types, dict)
                or set(field_types) != set(declared)
                or any(field_types.get(field) not in supported for field in declared)
                or not isinstance(field_schemas, dict)
                or set(field_schemas) != set(declared)
                or bool(validate_field_relations_definition(contract))
                or bool(validate_evidence_bindings_definition(contract))
                or bool(validate_cross_agent_relations_definition(contract))
                or not isinstance(registered, dict)
                or registered.get("contract") != current_contract
            ):
                return False
            if any(
                validate_field_schema_definition(
                    field_schemas[field],
                    path=f"field_schemas.{field}",
                    expected_root_type=field_types[field],
                )
                for field in declared
            ):
                return False
            if not any(
                isinstance(example, dict)
                and all(field in example for field in required)
                and not (set(example) - set(declared))
                and all(matches(example[field], field_types[field]) for field in example)
                and not validate_declared_field_schemas(example, contract)
                for example in (pack.get("example_outputs") or [])
            ):
                return False
            if any(
                not any(field in example for example in (pack.get("example_outputs") or []))
                for field in optional
            ):
                return False
    except (OSError, TypeError, ValueError):
        return False
    return visible == 26


def _agent_hub_reference_quality_gate_valid(
    agents_dir: Path,
    cases_path: Path,
) -> bool:
    """Validate all Pack-owned synthetic references and critical prompt invariants."""

    try:
        from scripts.corti_parity.run_agent_hub_examples_e2e import (
            _agent_id,
            _visible_packs,
        )
        from scripts.corti_parity.run_agent_hub_reference_quality_replay import (
            evaluate_reference_output,
            load_reference_cases,
        )

        packs = _visible_packs(agents_dir)
        _document, cases = load_reference_cases(cases_path, packs)
        if len(packs) != 26 or len(cases) != 26:
            return False
        packs_by_id = {_agent_id(pack): pack for pack in packs}
        for agent_id, pack in packs_by_id.items():
            case = cases[agent_id]
            example_index = int(case["example_index"])
            reference = (pack.get("example_outputs") or [])[example_index]
            if not evaluate_reference_output(reference, case)[
                "assertions_passed"
            ]:
                return False

        evidence_pack = packs_by_id["evidence-extractor"]
        evidence_prompt = str(evidence_pack.get("system_prompt") or "")
        if not all(
            phrase in evidence_prompt
            for phrase in (
                "候选编码声明区本身必须屏蔽",
                "不得进行同义医学推理",
                "绝不代表诊断成立",
            )
        ):
            return False

        surgical_pack = packs_by_id["surgical-registry"]
        surgical_prompt = str(surgical_pack.get("system_prompt") or "")
        evidence_spans = (
            ((surgical_pack.get("output_contract") or {}).get("field_schemas") or {})
            .get("evidence_spans", {})
        )
        evidence_properties = set((evidence_spans.get("properties") or {}).keys())
        return (
            (surgical_pack.get("output_contract") or {}).get("schema_ref")
            == "icoder/SurgicalRegistryOutput/v4"
            and evidence_properties
            == {
                "procedure",
                "indications",
                "comorbidities",
                "operative_details",
                "anesthesia",
                "outcomes",
                "complications",
            }
            and "必须填写 anesthesia" in surgical_prompt
            and "必须填写 complications" in surgical_prompt
            and "非空字段不得同时出现在 missing_fields" in surgical_prompt
            and "evidence_spans 的同名键" in surgical_prompt
        )
    except (IndexError, KeyError, OSError, TypeError, ValueError):
        return False


def validate(root: Path = REPO_ROOT) -> dict[str, Any]:
    compose_path = root / "docker-compose.local-dev.yml"
    medcoder_compose_path = root / "docker-compose.medcoder.yml"
    backend_dockerfile = root / "backend" / "Dockerfile"
    backend_dev_requirements = root / "backend" / "requirements.txt"
    backend_api_requirements = root / "backend" / "requirements-api.txt"
    run_trace_path = (
        root
        / "backend"
        / "app"
        / "icoder"
        / "agent_runtime"
        / "orchestrator"
        / "run_trace.py"
    )
    retention_path = root / "backend" / "app" / "services" / "retention.py"
    retention_cli_path = root / "backend" / "scripts" / "purge_retention.py"
    run_sse_metrics_path = (
        root / "backend" / "app" / "services" / "run_sse_observability.py"
    )
    app_main_path = root / "backend" / "app" / "main.py"
    stt_api_path = root / "backend" / "app" / "api" / "v2_tools_stt.py"
    stt_websocket_path = root / "backend" / "app" / "api" / "websocket.py"
    stt_lifecycle_test_path = (
        root / "backend" / "tests" / "test_api" / "test_v2_stt_real_lifecycle.py"
    )
    stt_websocket_security_test_path = (
        root
        / "backend"
        / "tests"
        / "test_api"
        / "test_stt_websocket_security.py"
    )
    javascript_managed_stt_path = (
        root / "packages" / "icoder-sdk" / "src" / "managed-stt-session.ts"
    )
    javascript_managed_stt_test_path = (
        root / "packages" / "icoder-sdk" / "tests" / "managed-stt-session.test.mjs"
    )
    javascript_stt_resource_path = (
        root / "packages" / "icoder-sdk" / "src" / "resources" / "speech-to-text.ts"
    )
    javascript_stt_test_path = (
        root / "packages" / "icoder-sdk" / "tests" / "speech-to-text.test.mjs"
    )
    python_managed_stt_path = (
        root / "packages" / "icoder-python" / "icoder_sdk" / "managed_stt_session.py"
    )
    python_managed_stt_test_path = (
        root / "packages" / "icoder-python" / "tests" / "test_managed_stt_session.py"
    )
    python_stt_resource_path = (
        root / "packages" / "icoder-python" / "icoder_sdk" / "resources"
        / "speech_to_text.py"
    )
    python_stt_test_path = (
        root / "packages" / "icoder-python" / "tests" / "test_speech_to_text.py"
    )
    dotnet_realtime_stt_path = (
        root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk"
        / "RealtimeSttSession.cs"
    )
    dotnet_stt_models_path = (
        root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk" / "Models.cs"
    )
    dotnet_stt_resource_path = (
        root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk"
        / "SpeechToTextResource.cs"
    )
    dotnet_contract_test_path = (
        root / "packages" / "icoder-dotnet" / "tests" / "Icoder.Sdk.Tests"
        / "ClientContractTests.cs"
    )
    dotnet_sdk_project_path = (
        root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk"
        / "Icoder.Sdk.csproj"
    )
    dotnet_compatibility_path = dotnet_sdk_project_path.with_name("Compatibility.cs")
    dotnet_netstandard_consumer_path = (
        root / "packages" / "icoder-dotnet" / "tests"
        / "Icoder.Sdk.NetStandard20Consumer" / "Icoder.Sdk.NetStandard20Consumer.csproj"
    )
    dotnet_net462_consumer_path = (
        root / "packages" / "icoder-dotnet" / "tests"
        / "Icoder.Sdk.Net462Consumer" / "Icoder.Sdk.Net462Consumer.csproj"
    )
    stt_fault_proxy_path = root / "backend" / "scripts" / "sdk_stt_fault_proxy.py"
    stt_recovery_e2e_path = (
        root / "scripts" / "release" / "run-stt-recovery-e2e.ps1"
    )
    transcripts_dictation_e2e_app_path = (
        root / "backend" / "scripts" / "transcripts_dictation_e2e_app.py"
    )
    transcripts_dictation_e2e_client_path = (
        root / "backend" / "scripts" / "transcripts_dictation_e2e_client.py"
    )
    transcripts_dictation_e2e_runner_path = (
        root / "scripts" / "release" / "run-transcripts-dictation-e2e.ps1"
    )
    prerecorded_media_decoder_path = (
        root / "backend" / "app" / "services" / "prerecorded_media_decoder.py"
    )
    prerecorded_media_decoder_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_prerecorded_media_decoder.py"
    )
    streams_api_path = root / "backend" / "app" / "api" / "v2_tools_streams.py"
    streams_schema_path = root / "backend" / "app" / "schemas" / "v2_tools_streams.py"
    streams_test_path = (
        root / "backend" / "tests" / "test_api" / "test_v2_streams_consistency.py"
    )
    streams_ambient_path = (
        root / "backend" / "app" / "services" / "ambient_processing.py"
    )
    streams_audio_format_path = (
        root / "backend" / "app" / "services" / "stream_audio_format.py"
    )
    streams_audio_format_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_stream_audio_format.py"
    )
    streams_audio_health_path = (
        root / "backend" / "app" / "services" / "stream_audio_health.py"
    )
    streams_audio_health_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_stream_audio_health.py"
    )
    streams_ambient_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_ambient_processing.py"
    )
    streams_media_decoder_path = (
        root / "backend" / "app" / "services" / "stream_media_decoder.py"
    )
    streams_media_decoder_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_stream_media_decoder.py"
    )
    streams_malformed_e2e_client_path = (
        root / "backend" / "scripts" / "streams_malformed_media_e2e_client.py"
    )
    streams_media_soak_path = (
        root / "backend" / "scripts" / "stream_media_decoder_soak.py"
    )
    streams_media_soak_runner_path = (
        root / "scripts" / "release" / "run-stream-media-decoder-soak.ps1"
    )
    javascript_streams_path = (
        root / "packages" / "icoder-sdk" / "src" / "managed-streams-session.ts"
    )
    javascript_streams_test_path = (
        root / "packages" / "icoder-sdk" / "tests" / "managed-streams-session.test.mjs"
    )
    javascript_streams_resource_path = (
        root / "packages" / "icoder-sdk" / "src" / "resources" / "streams.ts"
    )
    python_streams_path = (
        root / "packages" / "icoder-python" / "icoder_sdk"
        / "managed_streams_session.py"
    )
    python_streams_test_path = (
        root / "packages" / "icoder-python" / "tests"
        / "test_managed_streams_session.py"
    )
    python_streams_resource_path = (
        root / "packages" / "icoder-python" / "icoder_sdk" / "resources" / "streams.py"
    )
    dotnet_streams_path = (
        root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk"
        / "StreamsSession.cs"
    )
    dotnet_streams_resource_path = (
        root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk"
        / "StreamsResource.cs"
    )
    streams_e2e_path = root / "scripts" / "release" / "run-streams-e2e.ps1"
    streams_pcm_events_e2e_client_path = (
        root / "backend" / "scripts" / "streams_pcm_audio_events_e2e_client.py"
    )
    streams_multichannel_e2e_client_path = (
        root / "backend" / "scripts" / "streams_multichannel_e2e_client.py"
    )
    streams_lease_model_path = root / "backend" / "app" / "models" / "stt_artifact.py"
    streams_lease_service_path = (
        root / "backend" / "app" / "services" / "stream_session_lease.py"
    )
    streams_lease_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "056_streams_cross_worker_leases.py"
    )
    streams_lease_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_stream_session_lease.py"
    )
    streams_multiworker_e2e_path = (
        root / "scripts" / "release" / "run-streams-multiworker-e2e.ps1"
    )
    streams_checkpoint_service_path = (
        root / "backend" / "app" / "services"
        / "stream_checkpoint_repository.py"
    )
    streams_checkpoint_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "057_streams_resumable_checkpoints.py"
    )
    streams_checkpoint_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_stream_checkpoint_repository.py"
    )
    a2a_compat_test_path = (
        root / "backend" / "tests" / "test_api" / "test_phase4f2_a2a_compatible.py"
    )
    three_agent_a2a_smoke_path = (
        root
        / "backend"
        / "tests"
        / "integration"
        / "icoder"
        / "test_phase3d1_three_agents_a2a_smoke.py"
    )
    external_registry_path = (
        root / "backend" / "app" / "services" / "connector_external_registry.py"
    )
    connector_transport_path = (
        root / "backend" / "app" / "services" / "connector_http_transport.py"
    )
    external_registry_doc_path = (
        root / "docs" / "cloud" / "EXTERNAL_REGISTRY_GATEWAYS.md"
    )
    memory_semantic_path = (
        root / "backend" / "app" / "services" / "connector_memory_semantic.py"
    )
    memory_store_path = (
        root / "backend" / "app" / "services" / "connector_memory_store.py"
    )
    memory_semantic_doc_path = (
        root / "docs" / "cloud" / "SEMANTIC_MEMORY_SERVICE.md"
    )
    auth_api_path = root / "backend" / "app" / "api" / "auth.py"
    auth_middleware_path = root / "backend" / "app" / "middleware" / "auth.py"
    rate_limit_middleware_path = (
        root / "backend" / "app" / "middleware" / "rate_limit.py"
    )
    rate_limit_middleware_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "middleware"
        / "test_rate_limit.py"
    )
    organization_api_path = root / "backend" / "app" / "api" / "organizations.py"
    team_api_path = root / "backend" / "app" / "api" / "team.py"
    admin_api_path = root / "backend" / "app" / "api" / "admin.py"
    bootstrap_admin_path = root / "backend" / "scripts" / "bootstrap_platform_admin.py"
    platform_access_page_path = root / "frontend" / "src" / "pages" / "PlatformAccessPage.tsx"
    frontend_app_path = root / "frontend" / "src" / "App.tsx"
    retention_migration_path = (
        root
        / "backend"
        / "alembic"
        / "versions"
        / "040_run_trace_retention_tombstone.py"
    )
    invite_migration_path = (
        root
        / "backend"
        / "alembic"
        / "versions"
        / "041_hash_organization_invite_tokens.py"
    )
    invite_outbox_migration_path = (
        root
        / "backend"
        / "alembic"
        / "versions"
        / "042_organization_invite_delivery_outbox.py"
    )
    invite_delivery_path = root / "backend" / "app" / "services" / "invite_delivery.py"
    invite_outbox_cli_path = root / "backend" / "scripts" / "process_invite_outbox.py"
    agent_run_path = root / "backend" / "app" / "api" / "agent_run.py"
    idempotency_service_path = (
        root / "backend" / "app" / "services" / "idempotency_service.py"
    )
    idempotency_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "app"
        / "services"
        / "test_phase7_gate3_idempotency.py"
    )
    medcoder_retriever_path = (
        root
        / "backend"
        / "icoder_runtime"
        / "providers"
        / "medical_coding"
        / "medcoder_retriever.py"
    )
    medcoder_strategy_path = (
        root
        / "backend"
        / "icoder_runtime"
        / "providers"
        / "medical_coding"
        / "medcoder_strategy.py"
    )
    medcoder_worker_test_path = (
        root
        / "backend"
        / "tests"
        / "test_services"
        / "test_medcoder_retriever_worker.py"
    )
    medcoder_procedure_test_path = (
        root
        / "backend"
        / "tests"
        / "test_services"
        / "test_medcoder_icd9cm3_retriever.py"
    )
    agent_examples_e2e_path = (
        root / "backend" / "scripts" / "corti_parity" / "run_agent_hub_examples_e2e.py"
    )
    agent_adversarial_e2e_path = (
        root / "backend" / "scripts" / "corti_parity" / "run_agent_hub_adversarial_e2e.py"
    )
    agent_live_evidence_path = (
        root / "backend" / "scripts" / "corti_parity" / "agent_hub_live_evidence.py"
    )
    agent_semantic_bundle_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "build_agent_hub_semantic_evidence_bundle.py"
    )
    agent_runtime_matrix_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "build_agent_hub_runtime_matrix.py"
    )
    agent_semantic_bundle_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "corti_parity"
        / "test_agent_hub_semantic_evidence_bundle.py"
    )
    agent_local_semantic_bundle_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "build_agent_hub_local_semantic_evidence_bundle.py"
    )
    agent_local_semantic_runner_path = (
        root / "scripts" / "release" / "run-agent-hub-local-semantic-e2e.ps1"
    )
    agent_external_semantic_bundle_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "build_agent_hub_external_semantic_evidence_bundle.py"
    )
    agent_composite_semantic_bundle_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "build_agent_hub_composite_semantic_evidence_bundle.py"
    )
    agent_external_semantic_runner_path = (
        root / "scripts" / "release" / "run-agent-hub-external-semantic-e2e.ps1"
    )
    agent_external_artifact_validator_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "validate_agent_hub_external_artifacts.py"
    )
    agent_clinical_calibration_plan_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "build_agent_hub_clinical_calibration_plan.py"
    )
    agent_clinical_calibration_runner_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "run_agent_hub_clinical_calibration_e2e.py"
    )
    agent_clinical_calibration_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "corti_parity"
        / "test_agent_hub_clinical_calibration_e2e.py"
    )
    ccl_local_dataset_audit_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "audit_ccl2026_local_dataset.py"
    )
    ccl_local_dataset_audit_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "corti_parity"
        / "test_ccl2026_local_dataset_audit.py"
    )
    ccl_local_prediction_evaluator_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "evaluate_ccl2026_local_predictions.py"
    )
    ccl_local_prediction_evaluator_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "corti_parity"
        / "test_ccl2026_local_prediction_evaluator.py"
    )
    ccl_local_prediction_evaluator_runner_path = (
        root
        / "scripts"
        / "release"
        / "run-ccl2026-local-evaluator-self-test.ps1"
    )
    ccl_local_baseline_generator_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "generate_ccl2026_local_baseline_predictions.py"
    )
    ccl_local_baseline_generator_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "corti_parity"
        / "test_ccl2026_local_baseline_predictions.py"
    )
    ccl_local_baseline_runner_path = (
        root
        / "scripts"
        / "release"
        / "run-ccl2026-local-baseline-evaluation.ps1"
    )
    ccl_local_supervised_oof_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "evaluate_ccl2026_local_supervised_oof.py"
    )
    ccl_local_supervised_oof_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "corti_parity"
        / "test_ccl2026_local_supervised_oof.py"
    )
    ccl_local_supervised_oof_runner_path = (
        root
        / "scripts"
        / "release"
        / "run-ccl2026-local-supervised-oof.ps1"
    )
    clinical_model_package_model_path = (
        root / "backend" / "app" / "models" / "clinical_model_package.py"
    )
    clinical_model_package_api_path = (
        root / "backend" / "app" / "api" / "clinical_model_packages.py"
    )
    clinical_model_package_policy_path = (
        root / "backend" / "app" / "services"
        / "clinical_model_package_governance.py"
    )
    clinical_model_package_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "058_clinical_model_package_governance.py"
    )
    clinical_model_package_test_path = (
        root / "backend" / "tests" / "test_api"
        / "test_clinical_model_packages.py"
    )
    clinical_model_bundle_path = (
        root / "backend" / "app" / "services" / "clinical_model_bundle.py"
    )
    clinical_model_shadow_probe_path = (
        root / "backend" / "app" / "services" / "clinical_model_shadow_probe.py"
    )
    clinical_model_shadow_worker_path = (
        root / "backend" / "scripts" / "clinical_model_shadow_probe_worker.py"
    )
    clinical_model_artifact_scan_path = (
        root / "backend" / "app" / "services" / "artifact_object_scan.py"
    )
    clinical_model_shadow_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "059_clinical_model_shadow_supply_chain.py"
    )
    clinical_model_bundle_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_clinical_model_bundle.py"
    )
    clinical_model_trust_anchors_path = (
        root / "backend" / "data" / "clinical_model_trust_anchors.json"
    )
    clinical_model_fixture_manifest_path = (
        root / "backend" / "tests" / "fixtures" / "clinical_model_bundle_v1"
        / "bundle.manifest.json"
    )
    clinical_model_shadow_evidence_cli_path = (
        root / "backend" / "scripts" / "corti_parity"
        / "verify_clinical_model_shadow_fixture.py"
    )
    clinical_model_shadow_runner_path = (
        root / "scripts" / "release"
        / "run-clinical-model-shadow-supply-chain.ps1"
    )
    clinical_model_observation_path = (
        root / "backend" / "app" / "services"
        / "clinical_model_shadow_observation.py"
    )
    clinical_model_observation_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_clinical_model_shadow_observation.py"
    )
    clinical_model_observation_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "060_clinical_model_shadow_observations.py"
    )
    clinical_model_observation_cli_path = (
        root / "backend" / "scripts" / "corti_parity"
        / "verify_clinical_model_shadow_observation.py"
    )
    clinical_model_observation_runner_path = (
        root / "scripts" / "release"
        / "run-clinical-model-shadow-observation.ps1"
    )
    clinical_model_shadow_job_service_path = (
        root / "backend" / "app" / "services"
        / "clinical_model_shadow_job.py"
    )
    clinical_model_shadow_job_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "061_clinical_model_shadow_evaluation_jobs.py"
    )
    clinical_model_shadow_job_worker_path = (
        root / "backend" / "scripts" / "clinical_model_shadow_job_worker.py"
    )
    clinical_model_shadow_job_evidence_path = (
        root / "backend" / "scripts" / "corti_parity"
        / "verify_clinical_model_shadow_job_evidence.py"
    )
    clinical_model_shadow_job_runner_path = (
        root / "scripts" / "release"
        / "run-clinical-model-shadow-job-evidence.ps1"
    )
    clinical_model_shadow_job_operations_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "062_clinical_model_shadow_job_operations.py"
    )
    clinical_model_shadow_job_operations_evidence_path = (
        root / "backend" / "scripts" / "corti_parity"
        / "verify_clinical_model_shadow_job_operations_evidence.py"
    )
    clinical_model_shadow_job_operations_runner_path = (
        root / "scripts" / "release"
        / "run-clinical-model-shadow-job-operations-evidence.ps1"
    )
    clinical_model_shadow_control_plane_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "063_clinical_model_shadow_operations_control_plane.py"
    )
    clinical_model_shadow_queue_path = (
        root / "backend" / "app" / "services"
        / "clinical_model_shadow_queue.py"
    )
    clinical_model_shadow_observability_path = (
        root / "backend" / "app" / "services"
        / "clinical_model_shadow_observability.py"
    )
    clinical_model_shadow_scheduler_path = (
        root / "backend" / "app" / "services"
        / "clinical_model_shadow_scheduler.py"
    )
    clinical_model_shadow_scheduler_cli_path = (
        root / "backend" / "scripts" / "clinical_model_shadow_scheduler.py"
    )
    clinical_model_shadow_control_plane_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_clinical_model_shadow_operations.py"
    )
    clinical_model_shadow_control_plane_evidence_path = (
        root / "backend" / "scripts" / "corti_parity"
        / "verify_clinical_model_shadow_control_plane_evidence.py"
    )
    clinical_model_shadow_control_plane_runner_path = (
        root / "scripts" / "release"
        / "run-clinical-model-shadow-control-plane-evidence.ps1"
    )
    javascript_models_path = (
        root / "packages" / "icoder-sdk" / "src" / "resources" / "models.ts"
    )
    python_models_path = (
        root / "packages" / "icoder-python" / "icoder_sdk" / "resources" / "models.py"
    )
    dotnet_models_path = (
        root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk" / "ModelsResource.cs"
    )
    frontend_models_page_path = root / "frontend" / "src" / "pages" / "ModelsPage.tsx"
    ccl_local_model_runtime_audit_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "audit_ccl2026_local_model_runtime.py"
    )
    ccl_local_model_runtime_audit_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "corti_parity"
        / "test_ccl2026_local_model_runtime_audit.py"
    )
    bilingual_gold_review_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "bilingual_coding_gold_review.py"
    )
    bilingual_gold_review_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "corti_parity"
        / "test_bilingual_coding_gold_review.py"
    )
    note_completeness_rules_path = (
        root
        / "backend"
        / "official_agents"
        / "note_completeness"
        / "agent_legacy.py"
    )
    note_completeness_semantic_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "note_completeness"
        / "test_agent_deterministic_semantics.py"
    )
    diagnosis_extractor_pack_path = (
        root
        / "backend"
        / "official_agents"
        / "diagnosis-extractor"
        / "agent_pack.json"
    )
    diagnosis_extractor_rules_path = (
        root
        / "backend"
        / "official_agents"
        / "diagnosis_extractor"
        / "agent.py"
    )
    diagnosis_extractor_provider_path = (
        root
        / "backend"
        / "icoder_runtime"
        / "backends"
        / "governed_diagnosis_extractor_provider.py"
    )
    diagnosis_extractor_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "backends"
        / "test_governed_diagnosis_extractor_provider.py"
    )
    procedure_extractor_pack_path = (
        root
        / "backend"
        / "official_agents"
        / "procedure-extractor"
        / "agent_pack.json"
    )
    procedure_extractor_rules_path = (
        root
        / "backend"
        / "official_agents"
        / "procedure_extractor"
        / "agent.py"
    )
    procedure_extractor_provider_path = (
        root
        / "backend"
        / "icoder_runtime"
        / "backends"
        / "governed_procedure_extractor_provider.py"
    )
    procedure_extractor_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "backends"
        / "test_governed_procedure_extractor_provider.py"
    )
    medical_coding_page_path = (
        root / "frontend" / "src" / "pages" / "MedicalCodingPage.tsx"
    )
    medical_coding_safety_path = (
        root / "frontend" / "src" / "utils" / "medicalCodingSafety.ts"
    )
    result_attestation_path = (
        root / "backend" / "app" / "services" / "result_attestation.py"
    )
    trace_attestation_path = (
        root / "backend" / "app" / "services" / "trace_attestation.py"
    )
    run_trace_api_path = root / "backend" / "app" / "api" / "run_trace.py"
    a2a_v1_routes_path = (
        root
        / "backend"
        / "app"
        / "icoder"
        / "agent_runtime"
        / "a2a"
        / "v1"
        / "routes.py"
    )
    a2a_v1_task_runtime_path = a2a_v1_routes_path.with_name("task_runtime.py")
    a2a_v1_artifact_store_path = a2a_v1_routes_path.with_name("artifact_store.py")
    a2a_task_state_path = a2a_v1_routes_path.parent.parent / "task_state.py"
    a2a_v1_state_migration_path = (
        root / "backend" / "alembic" / "versions"
        / "055_a2a_v1_interrupted_task_states.py"
    )
    task_artifact_migration_path = (
        root
        / "backend"
        / "alembic"
        / "versions"
        / "050_task_owned_a2a_artifacts.py"
    )
    standard_artifact_event_migration_path = (
        root
        / "backend"
        / "alembic"
        / "versions"
        / "051_a2a_standard_artifact_events.py"
    )
    artifact_event_payload_migration_path = (
        root
        / "backend"
        / "alembic"
        / "versions"
        / "052_a2a_artifact_event_payloads.py"
    )
    artifact_object_migration_path = (
        root
        / "backend"
        / "alembic"
        / "versions"
        / "053_a2a_managed_artifact_objects.py"
    )
    a2a_v1_artifact_object_store_path = a2a_v1_routes_path.with_name(
        "artifact_object_store.py"
    )
    access_log_privacy_path = (
        root / "backend" / "app" / "services" / "access_log_privacy.py"
    )
    a2a_v1_runtime_test_path = (
        root
        / "backend"
        / "tests"
        / "integration"
        / "icoder"
        / "a2a"
        / "test_v1_async_runtime.py"
    )
    task_artifact_test_path = a2a_v1_runtime_test_path.with_name(
        "test_task_artifact_store.py"
    )
    a2a_v1_endpoint_test_path = a2a_v1_runtime_test_path.with_name(
        "test_endpoints.py"
    )
    agentic_context_resources_path = (
        root / "backend" / "app" / "api" / "agentic_context_resources.py"
    )
    agentic_context_resources_test_path = (
        root
        / "backend"
        / "tests"
        / "integration"
        / "icoder"
        / "a2a"
        / "test_agentic_context_resources.py"
    )
    javascript_a2a_path = (
        root / "packages" / "icoder-sdk" / "src" / "resources" / "a2a.ts"
    )
    javascript_ai_adapter_path = (
        root / "packages" / "icoder-sdk" / "src" / "ai-sdk-adapter.ts"
    )
    javascript_ai_adapter_test_path = (
        root / "packages" / "icoder-sdk" / "tests" / "ai-sdk-adapter.test.mjs"
    )
    javascript_sdk_package_path = (
        root / "packages" / "icoder-sdk" / "package.json"
    )
    javascript_official_a2a_helper_path = (
        root / "packages" / "icoder-sdk" / "tests" / "helpers"
        / "official-a2a-live-client.mjs"
    )
    python_a2a_path = (
        root
        / "packages"
        / "icoder-python"
        / "icoder_sdk"
        / "resources"
        / "a2a.py"
    )
    dotnet_a2a_path = (
        root
        / "packages"
        / "icoder-dotnet"
        / "src"
        / "Icoder.Sdk"
        / "A2AResource.cs"
    )
    dotnet_a2a_models_path = dotnet_a2a_path.with_name("Models.cs")
    provider_a2a_path = (
        root / "backend" / "app" / "icoder" / "agent_runtime" / "provider_a2a_handler.py"
    )
    provider_a2a_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "test_provider_a2a_streaming.py"
    )
    visible_agent_contract_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder_runtime"
        / "test_visible_agent_contract_roundtrip.py"
    )
    native_provider_stream_test_path = (
        root
        / "backend"
        / "tests"
        / "integration"
        / "icoder"
        / "a2a"
        / "test_native_provider_stream_e2e.py"
    )
    agentic_observability_path = (
        root / "backend" / "app" / "api" / "agentic_observability.py"
    )
    run_trace_path = (
        root
        / "backend"
        / "app"
        / "icoder"
        / "agent_runtime"
        / "orchestrator"
        / "run_trace.py"
    )
    run_trace_backend_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "backends"
        / "test_run_trace_backend_metadata.py"
    )
    specialized_telemetry_path = (
        root
        / "backend"
        / "app"
        / "icoder"
        / "agent_runtime"
        / "specialized_telemetry.py"
    )
    cdi_real_runner_path = (
        root
        / "backend"
        / "app"
        / "icoder"
        / "agent_runtime"
        / "cdi"
        / "real_runner.py"
    )
    cdi_real_runner_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "cdi"
        / "test_real_runner.py"
    )
    medical_coding_adapter_path = (
        root
        / "backend"
        / "icoder_runtime"
        / "providers"
        / "medical_coding"
        / "deepseek_coding_adapter.py"
    )
    medical_coding_adapter_test_path = (
        root
        / "backend"
        / "tests"
        / "test_services"
        / "test_deepseek_coding_adapter_rag.py"
    )
    a2a_facade_path = specialized_telemetry_path.with_name("a2a_facade.py")
    specialized_telemetry_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "agent_runtime"
        / "test_specialized_telemetry.py"
    )
    stt_service_path = root / "backend" / "app" / "services" / "stt_service.py"
    stt_jobs_path = root / "backend" / "app" / "services" / "stt_jobs.py"
    stt_schema_path = root / "backend" / "app" / "schemas" / "v2_tools_stt.py"
    stt_jobs_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_stt_jobs.py"
    )
    speaker_diarizer_path = (
        root / "backend" / "app" / "services" / "speaker_diarizer.py"
    )
    stt_artifact_repository_path = (
        root / "backend" / "app" / "services" / "stt_artifact_repository.py"
    )
    stt_artifact_repository_test_path = (
        root / "backend" / "tests" / "unit" / "app" / "services"
        / "test_stt_artifact_repository.py"
    )
    stt_telemetry_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "app"
        / "services"
        / "test_stt_inference_telemetry.py"
    )
    feedback_model_path = (
        root / "backend" / "app" / "models" / "agent_feedback.py"
    )
    feedback_training_migration_path = (
        root
        / "backend"
        / "alembic"
        / "versions"
        / "054_feedback_training_authorizations.py"
    )
    feedback_training_test_path = (
        root
        / "backend"
        / "tests"
        / "integration"
        / "icoder"
        / "a2a"
        / "test_agentic_observability_feedback.py"
    )
    a2a_routes_path = (
        root / "backend" / "app" / "icoder" / "agent_runtime" / "a2a" / "routes_inbound.py"
    )
    output_contract_validation_path = (
        root / "backend" / "icoder_runtime" / "backends" / "output_contract_validation.py"
    )
    llm_gateway_path = root / "backend" / "icoder_runtime" / "core" / "llm_gateway.py"
    llm_data_policy_path = root / "backend" / "icoder_runtime" / "core" / "data_policy.py"
    llm_provider_factory_path = (
        root / "backend" / "icoder_runtime" / "core" / "llm_provider_factory.py"
    )
    backend_config_path = root / "backend" / "app" / "config.py"
    backend_database_path = root / "backend" / "app" / "database.py"
    sqlite_reconciliation_path = (
        root / "backend" / "scripts" / "stage_sqlite_migration.py"
    )
    legacy_llm_service_path = root / "backend" / "app" / "services" / "llm_service.py"
    model_catalog_api_path = root / "backend" / "app" / "api" / "model_catalog.py"
    model_catalog_service_path = root / "backend" / "app" / "services" / "model_catalog.py"
    tenant_model_routing_path = (
        root / "backend" / "app" / "services" / "tenant_model_routing.py"
    )
    pure_llm_provider_path = (
        root / "backend" / "icoder_runtime" / "backends" / "pure_llm_provider.py"
    )
    llm_with_tools_provider_path = (
        root / "backend" / "icoder_runtime" / "backends" / "llm_with_tools_provider.py"
    )
    models_page_path = root / "frontend" / "src" / "pages" / "ModelsPage.tsx"
    frontend_api_path = root / "frontend" / "src" / "services" / "api.ts"
    javascript_models_path = (
        root / "packages" / "icoder-sdk" / "src" / "resources" / "models.ts"
    )
    python_models_path = (
        root
        / "packages"
        / "icoder-python"
        / "icoder_sdk"
        / "resources"
        / "models.py"
    )
    dotnet_models_path = (
        root
        / "packages"
        / "icoder-dotnet"
        / "src"
        / "Icoder.Sdk"
        / "ModelsResource.cs"
    )
    run_trace_page_path = root / "frontend" / "src" / "pages" / "RunTracePage.tsx"
    official_agents_dir = root / "backend" / "official_agents"
    agent_hub_reference_cases_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "agent_hub_reference_quality_cases.json"
    )
    corti_prebuilt_catalog_path = (
        root
        / "backend"
        / "scripts"
        / "corti_parity"
        / "corti_prebuilt_agent_catalog.json"
    )
    agent_hub_api_path = root / "backend" / "app" / "api" / "icoder_agents_hub.py"
    agent_definitions_api_path = root / "backend" / "app" / "api" / "agents.py"
    agent_runtime_pack_path = (
        root / "backend" / "app" / "services" / "agent_runtime_pack.py"
    )
    audit_detail_redactor_path = (
        root / "backend" / "app" / "services" / "audit_detail_redactor.py"
    )
    a2a_errors_path = (
        root / "backend" / "app" / "icoder" / "agent_runtime" / "a2a" / "errors.py"
    )
    new_agent_page_path = root / "frontend" / "src" / "pages" / "NewAgentPage.tsx"
    agent_detail_page_path = (
        root / "frontend" / "src" / "pages" / "AgentDetailPage.tsx"
    )
    agent_lifecycle_test_path = (
        root
        / "backend"
        / "tests"
        / "integration"
        / "icoder"
        / "test_agent_definition_lifecycle_e2e.py"
    )
    agent_detail_contract_test_path = (
        root
        / "frontend"
        / "src"
        / "pages"
        / "__tests__"
        / "AgentDetailPage.lifecycleRunHistoryContract.test.ts"
    )
    new_agent_template_test_path = (
        root
        / "frontend"
        / "src"
        / "pages"
        / "__tests__"
        / "NewAgentPage.governedTemplateCloneContract.test.ts"
    )
    agent_hub_matrix_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder_runtime"
        / "test_agent_hub_runtime_matrix.py"
    )
    frontend_agent_hub_api_path = (
        root / "frontend" / "src" / "services" / "agentHubApi.ts"
    )
    frontend_agent_hub_visibility_path = (
        root / "frontend" / "src" / "services" / "agentHubVisibility.ts"
    )
    frontend_agent_hub_test_path = (
        root
        / "frontend"
        / "src"
        / "services"
        / "__tests__"
        / "agentHubContract.test.ts"
    )
    javascript_agent_hub_types_path = (
        root / "packages" / "icoder-sdk" / "src" / "types.ts"
    )
    javascript_agent_hub_resource_path = (
        root / "packages" / "icoder-sdk" / "src" / "resources" / "agents.ts"
    )
    python_agent_hub_types_path = (
        root / "packages" / "icoder-python" / "icoder_sdk" / "types.py"
    )
    python_agent_hub_resource_path = (
        root / "packages" / "icoder-python" / "icoder_sdk" / "resources" / "agents.py"
    )
    dotnet_agent_hub_resource_path = (
        root / "packages" / "icoder-dotnet" / "src" / "Icoder.Sdk" / "AgentResources.cs"
    )
    committed_openapi_path = root / "docs" / "openapi" / "openapi.json"
    orchestrator_wiring_path = (
        root
        / "backend"
        / "app"
        / "icoder"
        / "agent_runtime"
        / "orchestrator"
        / "wiring.py"
    )
    orchestrator_wiring_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "orchestrator"
        / "test_wiring.py"
    )
    orchestrator_delegator_path = orchestrator_wiring_path.with_name("delegator.py")
    orchestrator_init_path = orchestrator_wiring_path.with_name("__init__.py")
    cdi_domain_path = (
        root / "backend" / "app" / "icoder" / "agent_runtime" / "cdi" / "domain.py"
    )
    cdi_orchestrator_path = cdi_domain_path.with_name("orchestrator.py")
    cdi_api_path = root / "backend" / "app" / "api" / "cdi.py"
    cdi_a2a_handler_path = (
        root
        / "backend"
        / "app"
        / "icoder"
        / "agent_runtime"
        / "cdi_a2a_handler.py"
    )
    cdi_orchestrator_test_path = (
        root
        / "backend"
        / "tests"
        / "unit"
        / "icoder"
        / "cdi"
        / "test_orchestrator.py"
    )
    cdi_public_handler_test_path = cdi_orchestrator_test_path.with_name(
        "test_cdi_a2a_handler.py"
    )
    system_audit_path = root / "backend" / "app" / "services" / "system_audit.py"
    legacy_tenancy_attribution_path = (
        root
        / "backend"
        / "app"
        / "services"
        / "legacy_tenancy_attribution.py"
    )
    accept_invite_page_path = root / "frontend" / "src" / "pages" / "AcceptInvitePage.tsx"
    backend_ml_requirements = root / "backend" / "requirements-ml.txt"
    backend_ml_worker_requirements = root / "backend" / "requirements-ml-worker.txt"
    backend_ml_dockerfile = root / "backend" / "Dockerfile.ml"
    backend_medcoder_index_dir = root / "backend" / "data" / "medcoder"
    frontend_dockerfile = root / "frontend" / "Dockerfile"
    embedded_bundle = root / "packages" / "icoder-embedded" / "dist" / "icoder-assistant.js"
    backend_ignore = root / "backend" / ".dockerignore"
    frontend_ignore = root / "frontend" / ".dockerignore"
    nginx_path = root / "frontend" / "nginx.conf"
    local_nginx_path = root / "frontend" / "nginx.local.conf"
    regions_path = root / "deploy" / "cloud" / "regions.yaml"
    env_path = root / ".env.cloud.example"
    e2e_workflow_path = root / ".github" / "workflows" / "e2e.yml"
    integration_workflow_path = root / ".github" / "workflows" / "ci-integration.yml"
    pr_workflow_path = root / ".github" / "workflows" / "ci-pr.yml"
    release_workflow_path = root / ".github" / "workflows" / "release-candidate.yml"

    compose = yaml.safe_load(_read(compose_path))
    services = compose.get("services") or {}
    medcoder_compose = yaml.safe_load(_read(medcoder_compose_path))
    medcoder_overlay_services = medcoder_compose.get("services") or {}
    backend_env = _environment_map(services.get("backend") or {})
    ml_worker_env = _environment_map(services.get("medcoder-retriever") or {})
    overlay_backend = medcoder_overlay_services.get("backend") or {}
    overlay_worker = medcoder_overlay_services.get("medcoder-retriever") or {}
    overlay_backend_env = _environment_map(overlay_backend)
    overlay_worker_env = _environment_map(overlay_worker)
    backend_df = _read(backend_dockerfile)
    dev_requirements = _read(backend_dev_requirements).lower()
    api_requirements = _read(backend_api_requirements).lower()
    run_trace = _read(run_trace_path)
    retention = _read(retention_path)
    retention_cli = _read(retention_cli_path)
    retention_migration = _read(retention_migration_path)
    run_sse_metrics = _read(run_sse_metrics_path)
    app_main = _read(app_main_path)
    external_registry = _read(external_registry_path)
    connector_transport = _read(connector_transport_path)
    external_registry_doc = _read(external_registry_doc_path)
    memory_semantic = _read(memory_semantic_path)
    memory_store = _read(memory_store_path)
    memory_semantic_doc = _read(memory_semantic_doc_path)
    auth_api = _read(auth_api_path)
    auth_middleware = _read(auth_middleware_path)
    rate_limit_middleware = _read(rate_limit_middleware_path)
    rate_limit_middleware_test = _read(rate_limit_middleware_test_path)
    organization_api = _read(organization_api_path)
    team_api = _read(team_api_path)
    admin_api = _read(admin_api_path)
    bootstrap_admin = _read(bootstrap_admin_path)
    platform_access_page = _read(platform_access_page_path)
    frontend_app = _read(frontend_app_path)
    invite_migration = _read(invite_migration_path)
    invite_outbox_migration = _read(invite_outbox_migration_path)
    invite_delivery = _read(invite_delivery_path)
    invite_outbox_cli = _read(invite_outbox_cli_path)
    agent_run = _read(agent_run_path)
    idempotency_service = _read(idempotency_service_path)
    idempotency_test = _read(idempotency_test_path)
    medcoder_retriever = _read(medcoder_retriever_path)
    medcoder_strategy = _read(medcoder_strategy_path)
    medcoder_worker_test = _read(medcoder_worker_test_path)
    medcoder_procedure_test = _read(medcoder_procedure_test_path)
    agent_examples_e2e = _read(agent_examples_e2e_path)
    agent_adversarial_e2e = _read(agent_adversarial_e2e_path)
    agent_live_evidence = _read(agent_live_evidence_path)
    agent_semantic_bundle = _read(agent_semantic_bundle_path)
    agent_runtime_matrix_source = _read(agent_runtime_matrix_path)
    agent_semantic_bundle_test = _read(agent_semantic_bundle_test_path)
    agent_local_semantic_bundle = _read(agent_local_semantic_bundle_path)
    agent_local_semantic_runner = _read(agent_local_semantic_runner_path)
    agent_external_semantic_bundle = _read(agent_external_semantic_bundle_path)
    agent_composite_semantic_bundle = _read(agent_composite_semantic_bundle_path)
    agent_external_semantic_runner = _read(agent_external_semantic_runner_path)
    agent_external_artifact_validator = _read(
        agent_external_artifact_validator_path
    )
    agent_clinical_calibration_plan = _read(agent_clinical_calibration_plan_path)
    agent_clinical_calibration_runner = _read(agent_clinical_calibration_runner_path)
    agent_clinical_calibration_test = _read(agent_clinical_calibration_test_path)
    ccl_local_dataset_audit = _read(ccl_local_dataset_audit_path)
    ccl_local_dataset_audit_test = _read(ccl_local_dataset_audit_test_path)
    ccl_local_prediction_evaluator = _read(ccl_local_prediction_evaluator_path)
    ccl_local_prediction_evaluator_test = _read(
        ccl_local_prediction_evaluator_test_path
    )
    ccl_local_prediction_evaluator_runner = _read(
        ccl_local_prediction_evaluator_runner_path
    )
    ccl_local_baseline_generator = _read(ccl_local_baseline_generator_path)
    ccl_local_baseline_generator_test = _read(
        ccl_local_baseline_generator_test_path
    )
    ccl_local_baseline_runner = _read(ccl_local_baseline_runner_path)
    ccl_local_supervised_oof = _read(ccl_local_supervised_oof_path)
    ccl_local_supervised_oof_test = _read(ccl_local_supervised_oof_test_path)
    ccl_local_supervised_oof_runner = _read(ccl_local_supervised_oof_runner_path)
    clinical_model_package_model = _read(clinical_model_package_model_path)
    clinical_model_package_api = _read(clinical_model_package_api_path)
    clinical_model_package_policy = _read(clinical_model_package_policy_path)
    clinical_model_package_migration = _read(clinical_model_package_migration_path)
    clinical_model_package_test = _read(clinical_model_package_test_path)
    clinical_model_bundle = _read(clinical_model_bundle_path)
    clinical_model_shadow_probe = _read(clinical_model_shadow_probe_path)
    clinical_model_shadow_worker = _read(clinical_model_shadow_worker_path)
    clinical_model_artifact_scan = _read(clinical_model_artifact_scan_path)
    clinical_model_shadow_migration = _read(clinical_model_shadow_migration_path)
    clinical_model_bundle_test = _read(clinical_model_bundle_test_path)
    clinical_model_trust_anchors = _read(clinical_model_trust_anchors_path)
    clinical_model_fixture_manifest = _read(clinical_model_fixture_manifest_path)
    clinical_model_shadow_evidence_cli = _read(clinical_model_shadow_evidence_cli_path)
    clinical_model_shadow_runner = _read(clinical_model_shadow_runner_path)
    clinical_model_observation = _read(clinical_model_observation_path)
    clinical_model_observation_test = _read(clinical_model_observation_test_path)
    clinical_model_observation_migration = _read(
        clinical_model_observation_migration_path
    )
    clinical_model_observation_cli = _read(clinical_model_observation_cli_path)
    clinical_model_observation_runner = _read(
        clinical_model_observation_runner_path
    )
    clinical_model_shadow_job_service = _read(
        clinical_model_shadow_job_service_path
    )
    clinical_model_shadow_job_migration = _read(
        clinical_model_shadow_job_migration_path
    )
    clinical_model_shadow_job_worker = _read(
        clinical_model_shadow_job_worker_path
    )
    clinical_model_shadow_job_evidence = _read(
        clinical_model_shadow_job_evidence_path
    )
    clinical_model_shadow_job_runner = _read(
        clinical_model_shadow_job_runner_path
    )
    clinical_model_shadow_job_operations_migration = _read(
        clinical_model_shadow_job_operations_migration_path
    )
    clinical_model_shadow_job_operations_evidence = _read(
        clinical_model_shadow_job_operations_evidence_path
    )
    clinical_model_shadow_job_operations_runner = _read(
        clinical_model_shadow_job_operations_runner_path
    )
    clinical_model_shadow_control_plane_migration = _read(
        clinical_model_shadow_control_plane_migration_path
    )
    clinical_model_shadow_queue = _read(clinical_model_shadow_queue_path)
    clinical_model_shadow_observability = _read(
        clinical_model_shadow_observability_path
    )
    clinical_model_shadow_scheduler = _read(clinical_model_shadow_scheduler_path)
    clinical_model_shadow_scheduler_cli = _read(
        clinical_model_shadow_scheduler_cli_path
    )
    clinical_model_shadow_control_plane_test = _read(
        clinical_model_shadow_control_plane_test_path
    )
    clinical_model_shadow_control_plane_evidence = _read(
        clinical_model_shadow_control_plane_evidence_path
    )
    clinical_model_shadow_control_plane_runner = _read(
        clinical_model_shadow_control_plane_runner_path
    )
    javascript_models = _read(javascript_models_path)
    python_models = _read(python_models_path)
    dotnet_models = _read(dotnet_models_path)
    frontend_models_page = _read(frontend_models_page_path)
    ccl_local_model_runtime_audit = _read(ccl_local_model_runtime_audit_path)
    ccl_local_model_runtime_audit_test = _read(
        ccl_local_model_runtime_audit_test_path
    )
    bilingual_gold_review = _read(bilingual_gold_review_path)
    bilingual_gold_review_test = _read(bilingual_gold_review_test_path)
    note_completeness_rules = _read(note_completeness_rules_path)
    note_completeness_semantic_test = _read(note_completeness_semantic_test_path)
    diagnosis_extractor_pack = _read(diagnosis_extractor_pack_path)
    diagnosis_extractor_rules = _read(diagnosis_extractor_rules_path)
    diagnosis_extractor_provider = _read(diagnosis_extractor_provider_path)
    diagnosis_extractor_test = _read(diagnosis_extractor_test_path)
    procedure_extractor_pack = _read(procedure_extractor_pack_path)
    procedure_extractor_rules = _read(procedure_extractor_rules_path)
    procedure_extractor_provider = _read(procedure_extractor_provider_path)
    procedure_extractor_test = _read(procedure_extractor_test_path)
    medical_coding_page = _read(medical_coding_page_path)
    medical_coding_safety = _read(medical_coding_safety_path)
    agent_hub_api = _read(agent_hub_api_path)
    agent_definitions_api = _read(agent_definitions_api_path)
    agent_runtime_pack = _read(agent_runtime_pack_path)
    audit_detail_redactor = _read(audit_detail_redactor_path)
    a2a_errors = _read(a2a_errors_path)
    new_agent_page = _read(new_agent_page_path)
    agent_detail_page = _read(agent_detail_page_path)
    agent_lifecycle_test = _read(agent_lifecycle_test_path)
    agent_detail_contract_test = _read(agent_detail_contract_test_path)
    new_agent_template_test = _read(new_agent_template_test_path)
    agent_hub_matrix_test = _read(agent_hub_matrix_test_path)
    frontend_agent_hub_api = _read(frontend_agent_hub_api_path)
    frontend_agent_hub_visibility = _read(frontend_agent_hub_visibility_path)
    frontend_agent_hub_test = _read(frontend_agent_hub_test_path)
    javascript_agent_hub_types = _read(javascript_agent_hub_types_path)
    javascript_agent_hub_resource = _read(javascript_agent_hub_resource_path)
    python_agent_hub_types = _read(python_agent_hub_types_path)
    python_agent_hub_resource = _read(python_agent_hub_resource_path)
    dotnet_agent_hub_resource = _read(dotnet_agent_hub_resource_path)
    dotnet_sdk_project = _read(dotnet_sdk_project_path)
    dotnet_compatibility = _read(dotnet_compatibility_path)
    dotnet_netstandard_consumer = _read(dotnet_netstandard_consumer_path)
    dotnet_net462_consumer = _read(dotnet_net462_consumer_path)
    committed_openapi = _read(committed_openapi_path)
    orchestrator_wiring = _read(orchestrator_wiring_path)
    orchestrator_wiring_test = _read(orchestrator_wiring_test_path)
    orchestrator_delegator = _read(orchestrator_delegator_path)
    orchestrator_init = _read(orchestrator_init_path)
    cdi_domain = _read(cdi_domain_path)
    cdi_orchestrator = _read(cdi_orchestrator_path)
    cdi_api = _read(cdi_api_path)
    cdi_a2a_handler = _read(cdi_a2a_handler_path)
    cdi_orchestrator_test = _read(cdi_orchestrator_test_path)
    cdi_public_handler_test = _read(cdi_public_handler_test_path)
    system_audit_service = _read(system_audit_path)
    legacy_tenancy_attribution = _read(legacy_tenancy_attribution_path)
    agent_hub_matrix = build_agent_hub_runtime_matrix(official_agents_dir)
    agent_hub_summary = agent_hub_matrix["summary"]
    result_attestation = _read(result_attestation_path)
    trace_attestation = _read(trace_attestation_path)
    run_trace_api = _read(run_trace_api_path)
    a2a_v1_routes = _read(a2a_v1_routes_path)
    a2a_v1_task_runtime = _read(a2a_v1_task_runtime_path)
    a2a_v1_artifact_store = _read(a2a_v1_artifact_store_path)
    a2a_task_state = _read(a2a_task_state_path)
    a2a_v1_state_migration = _read(a2a_v1_state_migration_path)
    task_artifact_migration = _read(task_artifact_migration_path)
    standard_artifact_event_migration = _read(
        standard_artifact_event_migration_path
    )
    artifact_event_payload_migration = _read(
        artifact_event_payload_migration_path
    )
    artifact_object_migration = _read(artifact_object_migration_path)
    a2a_v1_artifact_object_store = _read(a2a_v1_artifact_object_store_path)
    access_log_privacy = _read(access_log_privacy_path)
    a2a_v1_runtime_test = _read(a2a_v1_runtime_test_path)
    task_artifact_test = _read(task_artifact_test_path)
    a2a_v1_endpoint_test = _read(a2a_v1_endpoint_test_path)
    agentic_context_resources = _read(agentic_context_resources_path)
    agentic_context_resources_test = _read(agentic_context_resources_test_path)
    javascript_a2a = _read(javascript_a2a_path)
    javascript_ai_adapter = _read(javascript_ai_adapter_path)
    javascript_ai_adapter_test = _read(javascript_ai_adapter_test_path)
    javascript_sdk_package = _read(javascript_sdk_package_path)
    javascript_official_a2a_helper = _read(javascript_official_a2a_helper_path)
    python_a2a = _read(python_a2a_path)
    dotnet_a2a = _read(dotnet_a2a_path)
    dotnet_a2a_models = _read(dotnet_a2a_models_path)
    provider_a2a = _read(provider_a2a_path)
    provider_a2a_test = _read(provider_a2a_test_path)
    visible_agent_contract_test = _read(visible_agent_contract_test_path)
    native_provider_stream_test = _read(native_provider_stream_test_path)
    agentic_observability = _read(agentic_observability_path)
    run_trace = _read(run_trace_path)
    run_trace_backend_test = _read(run_trace_backend_test_path)
    specialized_telemetry = _read(specialized_telemetry_path)
    cdi_real_runner = _read(cdi_real_runner_path)
    cdi_real_runner_test = _read(cdi_real_runner_test_path)
    medical_coding_adapter = _read(medical_coding_adapter_path)
    medical_coding_adapter_test = _read(medical_coding_adapter_test_path)
    a2a_facade = _read(a2a_facade_path)
    specialized_telemetry_test = _read(specialized_telemetry_test_path)
    stt_service = _read(stt_service_path)
    stt_jobs = _read(stt_jobs_path)
    stt_schema = _read(stt_schema_path)
    stt_jobs_test = _read(stt_jobs_test_path)
    speaker_diarizer = _read(speaker_diarizer_path)
    stt_artifact_repository = _read(stt_artifact_repository_path)
    stt_artifact_repository_test = _read(stt_artifact_repository_test_path)
    stt_telemetry_test = _read(stt_telemetry_test_path)
    feedback_model = _read(feedback_model_path)
    feedback_training_migration = _read(feedback_training_migration_path)
    feedback_training_test = _read(feedback_training_test_path)
    a2a_routes = _read(a2a_routes_path)
    output_contract_validation = _read(output_contract_validation_path)
    llm_gateway = _read(llm_gateway_path)
    llm_data_policy = _read(llm_data_policy_path)
    llm_provider_factory = _read(llm_provider_factory_path)
    backend_config = _read(backend_config_path)
    backend_database = _read(backend_database_path)
    stt_api = _read(stt_api_path)
    stt_websocket = _read(stt_websocket_path)
    stt_lifecycle_test = _read(stt_lifecycle_test_path)
    stt_websocket_security_test = _read(stt_websocket_security_test_path)
    javascript_managed_stt = _read(javascript_managed_stt_path)
    javascript_managed_stt_test = _read(javascript_managed_stt_test_path)
    javascript_stt_resource = _read(javascript_stt_resource_path)
    javascript_stt_test = _read(javascript_stt_test_path)
    python_managed_stt = _read(python_managed_stt_path)
    python_managed_stt_test = _read(python_managed_stt_test_path)
    python_stt_resource = _read(python_stt_resource_path)
    python_stt_test = _read(python_stt_test_path)
    dotnet_realtime_stt = _read(dotnet_realtime_stt_path)
    dotnet_stt_models = _read(dotnet_stt_models_path)
    dotnet_stt_resource = _read(dotnet_stt_resource_path)
    dotnet_contract_test = _read(dotnet_contract_test_path)
    stt_fault_proxy = _read(stt_fault_proxy_path)
    stt_recovery_e2e = _read(stt_recovery_e2e_path)
    transcripts_dictation_e2e_app = _read(transcripts_dictation_e2e_app_path)
    transcripts_dictation_e2e_client = _read(transcripts_dictation_e2e_client_path)
    transcripts_dictation_e2e_runner = _read(transcripts_dictation_e2e_runner_path)
    prerecorded_media_decoder = _read(prerecorded_media_decoder_path)
    prerecorded_media_decoder_test = _read(prerecorded_media_decoder_test_path)
    streams_api = _read(streams_api_path)
    streams_schema = _read(streams_schema_path)
    streams_test = _read(streams_test_path)
    streams_ambient = _read(streams_ambient_path)
    streams_audio_format = _read(streams_audio_format_path)
    streams_audio_format_test = _read(streams_audio_format_test_path)
    streams_audio_health = _read(streams_audio_health_path)
    streams_audio_health_test = _read(streams_audio_health_test_path)
    streams_ambient_test = _read(streams_ambient_test_path)
    streams_media_decoder = _read(streams_media_decoder_path)
    streams_media_decoder_test = _read(streams_media_decoder_test_path)
    streams_malformed_e2e_client = _read(streams_malformed_e2e_client_path)
    streams_media_soak = _read(streams_media_soak_path)
    streams_media_soak_runner = _read(streams_media_soak_runner_path)
    javascript_streams = _read(javascript_streams_path)
    javascript_streams_test = _read(javascript_streams_test_path)
    javascript_streams_resource = _read(javascript_streams_resource_path)
    python_streams = _read(python_streams_path)
    python_streams_test = _read(python_streams_test_path)
    python_streams_resource = _read(python_streams_resource_path)
    dotnet_streams = _read(dotnet_streams_path)
    dotnet_streams_resource = _read(dotnet_streams_resource_path)
    streams_e2e = _read(streams_e2e_path)
    streams_pcm_events_e2e_client = _read(streams_pcm_events_e2e_client_path)
    streams_multichannel_e2e_client = _read(streams_multichannel_e2e_client_path)
    streams_lease_model = _read(streams_lease_model_path)
    streams_lease_service = _read(streams_lease_service_path)
    streams_lease_migration = _read(streams_lease_migration_path)
    streams_lease_test = _read(streams_lease_test_path)
    streams_multiworker_e2e = _read(streams_multiworker_e2e_path)
    streams_checkpoint_service = _read(streams_checkpoint_service_path)
    streams_checkpoint_migration = _read(streams_checkpoint_migration_path)
    streams_checkpoint_test = _read(streams_checkpoint_test_path)
    a2a_compat_test = _read(a2a_compat_test_path)
    three_agent_a2a_smoke = _read(three_agent_a2a_smoke_path)
    sqlite_reconciliation = _read(sqlite_reconciliation_path)
    legacy_llm_service = _read(legacy_llm_service_path)
    model_catalog_api = _read(model_catalog_api_path)
    model_catalog_service = _read(model_catalog_service_path)
    tenant_model_routing = _read(tenant_model_routing_path)
    pure_llm_provider = _read(pure_llm_provider_path)
    llm_with_tools_provider = _read(llm_with_tools_provider_path)
    models_page = _read(models_page_path)
    frontend_api = _read(frontend_api_path)
    javascript_models = _read(javascript_models_path)
    python_models = _read(python_models_path)
    dotnet_models = _read(dotnet_models_path)
    run_trace_page = _read(run_trace_page_path)
    accept_invite_page = _read(accept_invite_page_path)
    ml_requirements = _read(backend_ml_requirements).lower()
    ml_worker_requirements = _read(backend_ml_worker_requirements).lower()
    ml_worker_df = _read(backend_ml_dockerfile)
    frontend_df = _read(frontend_dockerfile)
    nginx = _read(nginx_path)
    local_nginx = _read(local_nginx_path)
    regions = yaml.safe_load(_read(regions_path))
    env_template = _read(env_path)
    e2e_workflow = _read(e2e_workflow_path)
    integration_workflow = _read(integration_workflow_path)
    pr_workflow = yaml.safe_load(_read(pr_workflow_path))
    release_workflow = _read(release_workflow_path)
    sdk_js_steps = ((pr_workflow.get("jobs") or {}).get("sdk-js") or {}).get("steps") or []
    sdk_js_runs = [str(step.get("run") or "") for step in sdk_js_steps]
    dotnet_steps = ((pr_workflow.get("jobs") or {}).get("sdk-dotnet") or {}).get("steps") or []
    dotnet_setup = next(
        (step for step in dotnet_steps if step.get("uses") == "actions/setup-dotnet@v4"),
        {},
    )
    dotnet_versions = {
        item.strip()
        for item in str((dotnet_setup.get("with") or {}).get("dotnet-version") or "").splitlines()
        if item.strip()
    }
    dotnet_runs = [str(step.get("run") or "") for step in dotnet_steps]

    environments = regions.get("environments") or []
    all_regions = [region for env in environments for region in env.get("regions") or []]
    cn = next((item for item in environments if item.get("code") == "cn"), {})
    canary_response_match = re.search(
        r"class ModelLiveCanaryResponse\(BaseModel\):(?P<body>.*?)"
        r"\n\nclass ModelLiveCanaryPolicy",
        model_catalog_api,
        re.DOTALL,
    )
    canary_response_contract = (
        canary_response_match.group("body") if canary_response_match else ""
    )

    checks = {
        "cn_code_catalog_assets_are_image_owned_integrity_checked_and_fail_closed": (
            _code_catalog_assets_are_image_owned_and_fail_closed(root)
        ),
        "ccl2026_local_dataset_is_source_bound_aggregate_only_and_egress_blocked": (
            "def read_sheet_rows" in ccl_local_dataset_audit
            and "exact_ordered_canonical_match" in ccl_local_dataset_audit
            and '"raw_clinical_text_emitted": False' in ccl_local_dataset_audit
            and '"encounter_identifiers_emitted": False' in ccl_local_dataset_audit
            and '"case_level_labels_emitted": False' in ccl_local_dataset_audit
            and '"external_provider_egress_allowed": False'
            in ccl_local_dataset_audit
            and '"source_workbook_copy_allowed": False' in ccl_local_dataset_audit
            and '"independent_clinical_gold_proven": False'
            in ccl_local_dataset_audit
            and "def validate_report" in ccl_local_dataset_audit
            and "test_exact_source_fixture_match_emits_only_aggregate_governance"
            in ccl_local_dataset_audit_test
            and "test_mismatch_and_catalog_gap_fail_closed"
            in ccl_local_dataset_audit_test
            and "test_authorized_root_and_report_digest_are_fail_closed"
            in ccl_local_dataset_audit_test
        ),
        "ccl2026_local_prediction_evaluator_is_exact_aggregate_only_and_fail_closed": (
            'REPORT_SCHEMA = "icoder.ccl2026-local-aggregate-evaluation/v1"'
            in ccl_local_prediction_evaluator
            and "def _exact_code" in ccl_local_prediction_evaluator
            and "never collapse code subdivisions" in ccl_local_prediction_evaluator
            and "prediction packet escapes the explicitly isolated root"
            in ccl_local_prediction_evaluator
            and '"case_level_predictions_emitted": False'
            in ccl_local_prediction_evaluator
            and '"external_network_used_by_evaluator": False'
            in ccl_local_prediction_evaluator
            and '"prediction_generation_no_network_independently_verified": False'
            in ccl_local_prediction_evaluator
            and '"independent_held_out_evaluation": False'
            in ccl_local_prediction_evaluator
            and '"corti_capability_parity_proven": False'
            in ccl_local_prediction_evaluator
            and '"model_capability_proven": False'
            in ccl_local_prediction_evaluator
            and "invalid aggregate report must not expose trusted metrics"
            in ccl_local_prediction_evaluator
            and "test_parent_child_codes_are_not_collapsed"
            in ccl_local_prediction_evaluator_test
            and "test_tamper_duplicate_and_missing_binding_fail_closed"
            in ccl_local_prediction_evaluator_test
            and "test_forbidden_case_payload_and_out_of_catalog_code_fail_closed"
            in ccl_local_prediction_evaluator_test
            and "test_external_egress_attestation_and_path_escape_fail_closed"
            in ccl_local_prediction_evaluator_test
            and "oracle_contract_self_test_only"
            in ccl_local_prediction_evaluator_runner
            and "Remove-Item -LiteralPath $resolvedTemp -Recurse -Force"
            in ccl_local_prediction_evaluator_runner
        ),
        "ccl2026_local_deterministic_baseline_is_gold_blind_offline_and_transient": (
            "label fields are never read for prediction"
            in ccl_local_baseline_generator
            and 'BASELINE_ID = "catalog-exact-name-frequency-recency-v1"'
            in ccl_local_baseline_generator
            and '"provider_class": "local_deterministic_baseline"'
            in ccl_local_baseline_generator
            and '"network_used": False' in ccl_local_baseline_generator
            and '"external_provider_used": False' in ccl_local_baseline_generator
            and '"clinical_text_included": False' in ccl_local_baseline_generator
            and "test_prediction_codes_do_not_depend_on_gold_fields"
            in ccl_local_baseline_generator_test
            and "test_no_exact_diagnosis_match_is_a_safe_failure"
            in ccl_local_baseline_generator_test
            and "local_deterministic_training_set_baseline_measured"
            in ccl_local_baseline_runner
            and "Remove-Item -LiteralPath $resolvedTemp -Recurse -Force"
            in ccl_local_baseline_runner
        ),
        "ccl2026_local_supervised_oof_is_leakage_bounded_aggregate_only_and_offline": (
            'REPORT_SCHEMA = "icoder.ccl2026-local-supervised-oof/v1"'
            in ccl_local_supervised_oof
            and 'MODEL_ID = "bounded-char-ngram-neighbor-v1"'
            in ccl_local_supervised_oof
            and "class EvaluationInput" in ccl_local_supervised_oof
            and "expected_principal_diagnosis" not in (
                ccl_local_supervised_oof.split("class EvaluationInput", 1)[1]
                .split("class TrainingExample", 1)[0]
            )
            and "training_row_self_exposure_count" in ccl_local_supervised_oof
            and '"case_level_predictions_emitted": False'
            in ccl_local_supervised_oof
            and '"independent_clinical_gold_proven": False'
            in ccl_local_supervised_oof
            and '"external_generalization_proven": False'
            in ccl_local_supervised_oof
            and '"corti_capability_parity_proven": False'
            in ccl_local_supervised_oof
            and '"clinical_production_readiness_proven": False'
            in ccl_local_supervised_oof
            and "validate_persisted_report" in ccl_local_supervised_oof
            and "test_stratified_folds_are_deterministic_balanced_and_text_group_safe"
            in ccl_local_supervised_oof_test
            and "test_evaluation_prediction_has_no_gold_label_input"
            in ccl_local_supervised_oof_test
            and "test_persisted_report_digest_is_fail_closed"
            in ccl_local_supervised_oof_test
            and "Authorized workbook no longer matches the governed audit"
            in ccl_local_supervised_oof_runner
            and 'SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null'
            in ccl_local_supervised_oof_runner
            and "protected_database_unchanged = $true"
            in ccl_local_supervised_oof_runner
            and "case_level_artifacts_emitted = $false"
            in ccl_local_supervised_oof_runner
        ),
        "clinical_model_packages_are_metadata_only_four_eyes_and_fail_closed": (
            "class ClinicalModelPackage(Base)" in clinical_model_package_model
            and "class ClinicalModelActivation(Base)" in clinical_model_package_model
            and "aggregate_manifest_only" in clinical_model_package_model
            and 'revision = "058"' in clinical_model_package_migration
            and 'down_revision = "057"' in clinical_model_package_migration
            and "def activation_blockers(" in clinical_model_package_policy
            and "independent_gold_not_validated" in clinical_model_package_policy
            and "four_eyes_review_missing" in clinical_model_package_policy
            and "CLINICAL_MODEL_PACKAGE_FOUR_EYES_REQUIRED" in clinical_model_package_api
            and 'runtime_loading_enabled: Literal[False] = False'
            in clinical_model_package_api
            and "test_oof_only_package_cannot_be_activated"
            in clinical_model_package_test
            and "activateClinicalPackage(" in javascript_models
            and "activate_clinical_package(" in python_models
            and "ActivateClinicalPackageAsync(" in dotnet_models
            and "运行时模型装载：关闭" in frontend_models_page
        ),
        "clinical_model_artifact_supply_chain_is_signed_scanned_and_shadow_only": (
            "class ClinicalModelArtifactAttestation(Base)"
            in clinical_model_package_model
            and "class ClinicalModelShadowBinding(Base)" in clinical_model_package_model
            and 'revision = "059"' in clinical_model_shadow_migration
            and 'down_revision = "058"' in clinical_model_shadow_migration
            and "Ed25519PublicKey" in clinical_model_bundle
            and "BUNDLE_MEMBER_PATH_INVALID" in clinical_model_bundle
            and "BUNDLE_FILE_INTEGRITY_FAILED" in clinical_model_bundle
            and "BUNDLE_CONTENT_SCAN_FAILED" in clinical_model_bundle
            and "validate_verification_report" in clinical_model_bundle
            and "scan_deidentified_json" in clinical_model_artifact_scan
            and '"-I", "-S"' in clinical_model_shadow_probe
            and "CREATE_NO_WINDOW" in clinical_model_shadow_probe
            and "network_used" in clinical_model_shadow_worker
            and "predictions_emitted" in clinical_model_shadow_worker
            and "icoder.clinical-model-trust-anchors/v1"
            in clinical_model_trust_anchors
            and "public_key_b64" in clinical_model_trust_anchors
            and "private_key" not in clinical_model_trust_anchors
            and "icoder.clinical-model-bundle/v1" in clinical_model_fixture_manifest
            and '"patient_data_allowed":false' in clinical_model_fixture_manifest
            and "ICODER_CLINICAL_MODEL_SYNTHETIC_PROBE_ENABLED"
            in clinical_model_package_api
            and "production_inference_enabled: Literal[False] = False"
            in clinical_model_package_api
            and "runtime_inference_enabled: Literal[False] = False"
            in clinical_model_package_api
            and "test_resigned_phi_or_executable_payload_is_scanner_blocked"
            in clinical_model_bundle_test
            and "test_development_signing_key_cannot_verify_for_production"
            in clinical_model_bundle_test
            and "test_signed_synthetic_bundle_probe_is_metadata_only_and_shadow_bound"
            in clinical_model_package_test
            and "probeSyntheticClinicalArtifact(" in javascript_models
            and "probe_synthetic_clinical_artifact(" in python_models
            and "ProbeSyntheticClinicalArtifactAsync(" in dotnet_models
            and "不接收患者数据、不输出预测，也不接入生产 Runtime"
            in frontend_models_page
            and '"case_level_artifacts_emitted": False'
            in clinical_model_shadow_evidence_cli
            and '"corti_capability_parity_proven": False'
            in clinical_model_shadow_evidence_cli
            and 'SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null'
            in clinical_model_shadow_runner
            and "Protected database changed" in clinical_model_shadow_runner
        ),
        "clinical_model_shadow_observations_are_aggregate_fail_closed_and_auto_rollback": (
            "class ClinicalModelShadowEvaluation(Base)" in clinical_model_package_model
            and 'revision = "060"' in clinical_model_observation_migration
            and 'down_revision = "059"' in clinical_model_observation_migration
            and "ICODER_CLINICAL_MODEL_SHADOW_EVALUATION_ENABLED"
            in clinical_model_package_api
            and "clinical_model_shadow_binding.auto_rolled_back"
            in clinical_model_package_api
            and "run_verified_shadow_suite" in clinical_model_observation
            and '"patient_data_allowed": False' in clinical_model_observation
            and '"predictions_allowed": False' in clinical_model_observation
            and "stop_and_rollback" in clinical_model_observation
            and "test_controlled_faults_stop_and_require_rollback"
            in clinical_model_observation_test
            and "/synthetic-evaluation" in clinical_model_package_test
            and "evaluateSyntheticClinicalShadow(" in javascript_models
            and "evaluate_synthetic_clinical_shadow(" in python_models
            and "EvaluateSyntheticClinicalShadowAsync(" in dotnet_models
            and "自动回滚" in frontend_models_page
            and '"real_shadow_traffic_used": False'
            in clinical_model_observation_cli
            and 'SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null'
            in clinical_model_observation_runner
            and "Authorized workbook changed" in clinical_model_observation_runner
        ),
        "clinical_model_shadow_jobs_are_idempotent_fenced_recoverable_and_aggregate_only": (
            "class ClinicalModelShadowEvaluationJob(Base)" in clinical_model_package_model
            and 'revision = "061"' in clinical_model_shadow_job_migration
            and 'down_revision = "060"' in clinical_model_shadow_job_migration
            and "active_binding_id" in clinical_model_shadow_job_migration
            and "claim_next_shadow_job" in clinical_model_shadow_job_service
            and "renew_shadow_job_lease" in clinical_model_shadow_job_service
            and "finalize_exhausted_shadow_jobs" in clinical_model_shadow_job_service
            and "lease_token == claim.lease_token" in clinical_model_shadow_job_service
            and "Idempotency-Key" in clinical_model_package_api
            and "/shadow-evaluation-jobs/{job_id}" in clinical_model_package_api
            and "ICODER_CLINICAL_MODEL_SHADOW_JOB_SIMULATION_ENABLED"
            in clinical_model_package_api
            and "recovered_claim.lease_token != first_claim.lease_token"
            in clinical_model_package_test
            and "assert stale_result is None" in clinical_model_package_test
            and "createClinicalShadowEvaluationJob(" in javascript_models
            and "create_clinical_shadow_evaluation_job(" in python_models
            and "CreateClinicalShadowEvaluationJobAsync(" in dotnet_models
            and "fencing token" in frontend_models_page
            and "SHADOW_JOB_WORKER_DEVELOPMENT_ONLY" in clinical_model_shadow_job_worker
            and '"stale_worker_terminal_mutation_blocked": True'
            in clinical_model_shadow_job_evidence
            and 'SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null'
            in clinical_model_shadow_job_runner
            and "Protected database changed" in clinical_model_shadow_job_runner
            and "Authorized workbook changed" in clinical_model_shadow_job_runner
        ),
        "clinical_model_shadow_job_operations_are_cancellable_observable_and_tenant_safe": (
            'revision = "062"' in clinical_model_shadow_job_operations_migration
            and 'down_revision = "061"' in clinical_model_shadow_job_operations_migration
            and "ck_clinical_model_shadow_job_cancellation_shape"
            in clinical_model_shadow_job_operations_migration
            and "cancel_shadow_job" in clinical_model_shadow_job_service
            and "summarize_shadow_job_health" in clinical_model_shadow_job_service
            and "status=\"cancelled\"" in clinical_model_shadow_job_service
            and "lease_token=None" in clinical_model_shadow_job_service
            and "identifiers_emitted" in clinical_model_package_api
            and "/shadow-evaluation-jobs/health/summary" in clinical_model_package_api
            and "/shadow-evaluation-jobs/maintenance/run" in clinical_model_package_api
            and "assert stale_cancelled_result is None" in clinical_model_package_test
            and "assert cross_tenant_cancel.status_code == 404"
            in clinical_model_package_test
            and "cancelClinicalShadowEvaluationJob(" in javascript_models
            and "cancel_clinical_shadow_evaluation_job(" in python_models
            and "CancelClinicalShadowEvaluationJobAsync(" in dotnet_models
            and "Shadow 作业健康" in frontend_models_page
            and '"cancelled_worker_settlement_fenced": True'
            in clinical_model_shadow_job_operations_evidence
            and 'SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null'
            in clinical_model_shadow_job_operations_runner
            and "Protected database changed"
            in clinical_model_shadow_job_operations_runner
            and "Authorized workbook changed"
            in clinical_model_shadow_job_operations_runner
        ),
        "clinical_model_shadow_control_plane_has_dlq_alerts_metrics_and_fenced_scheduler": (
            'revision = "063"' in clinical_model_shadow_control_plane_migration
            and 'down_revision = "062"' in clinical_model_shadow_control_plane_migration
            and "clinical_model_shadow_dead_letters"
            in clinical_model_shadow_control_plane_migration
            and "clinical_model_shadow_alert_states"
            in clinical_model_shadow_control_plane_migration
            and "clinical_model_shadow_scheduler_leases"
            in clinical_model_shadow_control_plane_migration
            and "database polling as durable fallback" in clinical_model_shadow_queue
            and "patient_labels_present" in clinical_model_shadow_observability
            and "evaluate_persistent_shadow_alerts" in clinical_model_shadow_scheduler
            and "generation == lease.generation" in clinical_model_shadow_scheduler
            and "evaluate_persistent_shadow_alerts" in clinical_model_shadow_scheduler_cli
            and "replay_shadow_dead_letter" in clinical_model_shadow_job_service
            and "test_database_queue_is_phi_free_durable_fallback"
            in clinical_model_shadow_control_plane_test
            and '"database_is_durable_queue_authority": True'
            in clinical_model_shadow_control_plane_evidence
            and '"production_broker_exercised": False'
            in clinical_model_shadow_control_plane_evidence
            and 'SetEnvironmentVariable("ICODER_CREDENTIAL_LLM", $null'
            in clinical_model_shadow_control_plane_runner
            and "Protected database changed"
            in clinical_model_shadow_control_plane_runner
            and "Authorized workbook changed"
            in clinical_model_shadow_control_plane_runner
        ),
        "ccl2026_local_model_readiness_audit_blocks_unsafe_native_and_embedding_only_stacks": (
            "without importing native ML stacks" in ccl_local_model_runtime_audit
            and "assess_bge_runtime_safety" in ccl_local_model_runtime_audit
            and "assess_pyarrow_runtime_safety" in ccl_local_model_runtime_audit
            and '"embedding_retriever_is_generative_model": False'
            in ccl_local_model_runtime_audit
            and '"approved_local_generative_clinical_coding_model_configured": False'
            in ccl_local_model_runtime_audit
            and '"native_model_loaded_by_audit": False'
            in ccl_local_model_runtime_audit
            and '"unsafe_runtime_override_used": False'
            in ccl_local_model_runtime_audit
            and "test_unsafe_native_stack_and_missing_generative_model_are_blocked"
            in ccl_local_model_runtime_audit_test
            and "test_embedding_only_assets_do_not_become_a_generative_model"
            in ccl_local_model_runtime_audit_test
            and "test_asset_tamper_and_report_tamper_are_detected"
            in ccl_local_model_runtime_audit_test
        ),
        "compose_scope_is_explicitly_local": (
            backend_env.get("ICODER_DEPLOYMENT_MODE") == "local"
            and backend_env.get("APP_ENV") == "local"
            and backend_env.get("SEED_ON_STARTUP") == "true"
            and backend_env.get("ICODER_ALLOW_DEGRADED_NO_KEY")
            == "${ICODER_ALLOW_DEGRADED_NO_KEY:-1}"
        ),
        "compose_has_required_services": set(services) == {
            "db", "redis", "backend", "medcoder-retriever", "frontend"
        },
        "compose_dependencies_are_health_gated": all(
            ((services.get("backend") or {}).get("depends_on") or {}).get(name, {}).get("condition")
            == "service_healthy"
            for name in ("db", "redis")
        ),
        "compose_uses_persistent_trace_store": (
            backend_env.get("RUNTRACE_STORE") == "${RUNTRACE_STORE:-db}"
            and backend_env.get("RUNTRACE_FAIL_CLOSED")
            == "${RUNTRACE_FAIL_CLOSED:-0}"
            and backend_env.get("DATABASE_URL", "").startswith(
                "${DATABASE_URL:-postgresql+asyncpg://"
            )
            and backend_env.get("ICODER_RUN_TRACE_EVENTS_TTL_DAYS")
            == "${ICODER_RUN_TRACE_EVENTS_TTL_DAYS:-90}"
            and backend_env.get("ICODER_RUN_HISTORY_TTL_DAYS")
            == "${ICODER_RUN_HISTORY_TTL_DAYS:-90}"
        ),
        "run_trace_retention_is_executable_and_audited": (
            "def purge_expired_run_trace_events" in retention
            and 'table_name="run_trace_events"' in retention
            and "trace_events_purged_at" in retention
            and '"--execute"' in retention_cli
            and "dry_run=not execute" in retention_cli
            and "trace_events_purged_at" in retention_migration
            and "trace_events_purged_count" in retention_migration
        ),
        "run_sse_metrics_are_phi_safe_bounded_and_scrapeable": (
            '"icoder.run-sse-metrics/v1"' in run_sse_metrics
            and '"scope": "single_api_process"' in run_sse_metrics
            and "deque(maxlen=self._sample_limit)" in run_sse_metrics
            and "_safe_label" in run_sse_metrics
            and "SSE_RESUME_RECOVERY_P95_HIGH" in run_sse_metrics
            and '"ICODER_METRICS_BEARER_TOKEN"' in app_main
            and "hmac.compare_digest" in app_main
            and 'http_response.headers["Cache-Control"] = "no-store"' in app_main
            and backend_env.get("ICODER_METRICS_BEARER_TOKEN")
            == "${ICODER_METRICS_BEARER_TOKEN:-}"
            and "run_sse_metrics_process_snapshots" in _read(
                root / "packages" / "icoder-dotnet" / "scripts" / "run-local-e2e.ps1"
            )
        ),
        "public_registration_cannot_self_assign_platform_role": (
            "if data.role != UserRole.CODER" in auth_api
            and "SELF_ASSIGNED_ROLE_FORBIDDEN" in auth_api
            and "role=UserRole.CODER" in auth_api
            and "auth.register.denied.role_escalation" in auth_api
            and ("token=" + "{raw_token}") not in auth_api
        ),
        "user_tokens_are_type_checked_versioned_and_membership_bound": (
            'payload.get("type") != "access"' in auth_middleware
            and "user.token_version != token_version" in auth_middleware
            and "Organization membership required" in auth_middleware
            and "Refresh token revoked" in auth_api
            and "token_version=current_user.token_version" in auth_api
        ),
        "organization_paths_and_legacy_team_api_are_tenant_scoped": (
            "def _require_path_context" in organization_api
            and "_require_path_context(org_id, current_org)" in organization_api
            and "Only the owner can grant or change administrator access" in organization_api
            and "from app.models.team import" not in team_api
            and "OrganizationMember.organization_id == current_org.id" in team_api
        ),
        "organization_invites_are_hashed_one_time_and_audited": (
            'OrganizationInvite.token == _token_digest(data.token)' in organization_api
            and "token=_token_digest(raw_token)" in organization_api
            and 'response.headers["Cache-Control"] = "no-store"' in organization_api
            and 'invite.status = "accepted"' in organization_api
            and 'invite.status = "revoked"' in organization_api
            and 'invite.status = "expired"' in organization_api
            and "hashlib.sha256(token.encode" in invite_migration
        ),
        "organization_invite_delivery_is_encrypted_durable_and_bounded": (
            "organization_invite_deliveries" in invite_outbox_migration
            and 'revision = "042"' in invite_outbox_migration
            and 'down_revision = "041"' in invite_outbox_migration
            and "is_encrypted_value(encrypted)" in invite_delivery
            and 'status="queued"' in invite_delivery
            and 'row.status = "dead_letter"' in invite_delivery
            and "ICODER_INVITE_MAX_ATTEMPTS" in invite_delivery
            and "ICODER_INVITE_CLAIM_TIMEOUT_SECONDS" in invite_delivery
            and 'row.encrypted_payload = ""' in invite_delivery
        ),
        "organization_invite_webhook_is_signed_idempotent_and_fail_closed": (
            '"Authorization": f"Bearer {credential}"' in invite_delivery
            and '"Idempotency-Key": f"invite-delivery-{delivery_id}"' in invite_delivery
            and '"X-iCoDer-Signature": f"sha256={signature}"' in invite_delivery
            and "follow_redirects=False" in invite_delivery
            and "recipient_domain_allowed" in organization_api
            and "INVITE_EMAIL_DOMAIN_FORBIDDEN" in organization_api
            and "INVITE_DELIVERY_UNAVAILABLE" in organization_api
            and 'result["invite_token"] = raw_token' in organization_api
            and 'if delivery is None:' in organization_api
        ),
        "organization_invite_processor_is_explicit_and_secret_free": (
            '"--execute"' in invite_outbox_cli
            and '"mode": "dry_run"' in invite_outbox_cli
            and "claim_due_deliveries" in invite_outbox_cli
            and "process_delivery_claim" in invite_outbox_cli
            and "aggregate counts only" in invite_outbox_cli
        ),
        "machine_idempotency_is_bound_to_delegated_subject_and_purpose": (
            "def _bind_request_hash_to_delegation(" in idempotency_service
            and '"delegated_subject_id": subject' in idempotency_service
            and '"purpose_of_use": purpose' in idempotency_service
            and "hashlib.sha256(" in idempotency_service
            and "delegated_subject_id=(delegated_subject_id or None)"
            in agent_run
            and "purpose_of_use=run_purpose_of_use if is_machine_client else None"
            in agent_run
            and "test_machine_replay_is_bound_to_delegated_subject_and_purpose"
            in idempotency_test
            and 'not hasattr(first.record, "delegated_subject_id")'
            in idempotency_test
        ),
        "native_medcoder_worker_handshake_and_confidence_are_bounded": (
            'STARTUP_READY_ID = "__startup_ready__"' in medcoder_retriever
            and "probe_timeout: float = 60.0" in medcoder_retriever
            and "def _bounded_confidence(value: Any) -> float:"
            in medcoder_strategy
            and "math.isfinite(parsed)" in medcoder_strategy
            and "test_worker_emits_ready_only_after_retriever_loads"
            in medcoder_worker_test
            and "test_procedure_confidence_bounds_raw_retrieval_scores"
            in medcoder_procedure_test
        ),
        "starlette_testclient_uses_pinned_httpx2_backend": (
            "httpx2==2.12.0" in dev_requirements
            and "httpx2" not in api_requirements
            and "httpx==0.27.2" in api_requirements
        ),
        "organization_invite_browser_flow_uses_fragment_and_scrubs_history": (
            'path="/accept-invite"' in frontend_app
            and "window.location.hash" in accept_invite_page
            and "window.history.replaceState" in accept_invite_page
            and "/login#token=" in accept_invite_page
            and "sessionStorage" not in accept_invite_page
            and "orgApi.acceptInvite(token)" in accept_invite_page
        ),
        "agent_hub_typed_contracts_are_complete_and_fail_closed": (
            _agent_hub_typed_contracts_valid(official_agents_dir)
            and "validate_required_field_types" in agent_run
            and "validate_declared_field_schemas" in agent_run
            and '"invalid_field_types": invalid_field_types' in agent_run
            and "or undeclared_output_fields" in agent_run
            and '"contract_output_suppressed": True' in agent_run
            and '"undeclared_output_fields": undeclared_output_fields' in agent_run
            and 'extraction.get("invalid_field_types")' in provider_a2a
            and 'extraction.get("invalid_field_schemas")' in provider_a2a
            and 'extraction.get("undeclared_output_fields")' in provider_a2a
            and "SUPPORTED_FIELD_TYPES" in output_contract_validation
            and "not isinstance(value, bool)" in output_contract_validation
            and "validate_field_relations_definition" in output_contract_validation
            and '"fieldRelation"' in output_contract_validation
            and "SUPPORTED_RELATION_OPERATORS" in output_contract_validation
            and "validate_evidence_bindings_definition" in output_contract_validation
            and 'keyword="evidenceBinding"' in output_contract_validation
            and "validate_evidence_bindings" in agent_run
            and "source_text=primary_text" in provider_a2a
            and "validate_cross_agent_relations_definition" in output_contract_validation
            and 'keyword="crossAgentRelation"' in output_contract_validation
            and "upstream_results=upstream_results" in provider_a2a
            and "verify_upstream_result_attestations" in agent_run
            and "issue_result_attestation" in agent_run
            and "verify_upstream_result_attestations" in provider_a2a
            and "issue_result_attestation" in provider_a2a
            and "Authenticate upstream Agent outputs against their exact pre-redaction" in a2a_routes
            and "upstream_result_attestations_verified" in a2a_routes
            and "allow_nan=False" in result_attestation
            and "expected_organization_id" in result_attestation
            and "result attestation identity or digest mismatch" in result_attestation
        ),
        "agent_hub_pack_reference_semantics_are_complete_and_self_validating": (
            _agent_hub_reference_quality_gate_valid(
                official_agents_dir,
                agent_hub_reference_cases_path,
            )
        ),
        "agent_hub_live_semantic_evidence_is_fresh_non_mock_and_fail_closed": (
            agent_hub_summary["visible_semantic_live_e2e_verified"] == 0
            and agent_hub_matrix["semantic_evidence"]["provided"] is False
            and "capture_trace_artifact" in agent_examples_e2e
            and "row_execution_evidence" in agent_adversarial_e2e
            and "seeded_artifacts" in agent_live_evidence
            and "mock/test model telemetry is forbidden" in agent_semantic_bundle
            and "artifact_source must be a fresh HTTP run or bound fresh seed"
            in agent_semantic_bundle
            and "server result attestation is absent, unbound, or has an invalid signature"
            in agent_semantic_bundle
            and "verify_bundle_digest" in agent_semantic_bundle
            and "trace_attestation_signature_verified" in agent_semantic_bundle
            and "issue_trace_attestation" in run_trace_api
            and "trace attestation identity or digest mismatch" in trace_attestation
            and "semantic_evidence_path" in agent_runtime_matrix_source
            and "visible_semantic_live_e2e_verified" in agent_runtime_matrix_source
            and "test_mock_trace_telemetry_cannot_inflate_live_count"
            in agent_semantic_bundle_test
            and "test_tampered_bundle_or_source_is_rejected_at_matrix_ingestion"
            in agent_semantic_bundle_test
        ),
        "agent_hub_local_semantic_evidence_is_strictly_scoped_and_e2e_tested": (
            agent_hub_summary["visible_local_semantic_e2e_verified"] == 0
            and len(agent_hub_summary["visible_local_semantic_e2e_pending"]) == 24
            and len(agent_hub_summary["visible_external_semantic_live_e2e_pending"])
            == 2
            and agent_hub_matrix["local_semantic_evidence"]["provided"] is False
            and "EXPECTED_LOCAL_AGENT_COUNT = 24" in agent_local_semantic_bundle
            and "external-model-dependent Agents were not evaluated"
            in agent_local_semantic_bundle
            and "cannot satisfy or replace the strict 26-Agent live-provider gate"
            in agent_local_semantic_bundle
            and "validate_local_bundle_file" in agent_local_semantic_bundle
            and "local_semantic_evidence_path" in agent_runtime_matrix_source
            and "visible_local_semantic_e2e_verified" in agent_runtime_matrix_source
            and "visible_semantic_live_e2e_verified" in agent_runtime_matrix_source
            and "derived_from_semantic_evidence" in agent_runtime_matrix_source
            and "structural_local_deterministic_subset_only"
            in agent_runtime_matrix_source
            and "composite_validated_local_component"
            in agent_runtime_matrix_source
            and '"visible_local_semantic_e2e_verified"] == 23'
            in agent_semantic_bundle_test
            and "Remove-Item \"Env:$name\"" in agent_local_semantic_runner
            and "ICODER_ALLOW_EXTERNAL_LLM = \"false\""
            in agent_local_semantic_runner
            and "run_agent_hub_examples_e2e.py" in agent_local_semantic_runner
            and "run_agent_hub_adversarial_e2e.py" in agent_local_semantic_runner
            and "run_agent_hub_reference_quality_replay.py"
            in agent_local_semantic_runner
            and "run_agent_hub_stability_benchmark.py" in agent_local_semantic_runner
            and "strict_26_agent_semantic_verified = 0"
            in agent_local_semantic_runner
            and "test_local_semantic_bundle_is_strictly_scoped_and_cannot_inflate_full_gate"
            in agent_semantic_bundle_test
            and "_semantic_findings" in note_completeness_rules
            and "diagnosis_levels != treatment_levels" in note_completeness_rules
            and "test_surgical_spinal_level_conflict_is_explicit_and_reviewable"
            in note_completeness_semantic_test
            and '"backend_provider": "icoder.governed-procedure-extractor.v1"'
            in procedure_extractor_pack
            and '"code": "03.5304"' in procedure_extractor_pack
            and '"code": "81.0100"' not in procedure_extractor_pack
            and "explicit_spinal_level_catalog_normalization"
            in procedure_extractor_rules
            and "authority_status=source_unverified" in procedure_extractor_rules
            and "class GovernedProcedureExtractorProvider"
            in procedure_extractor_provider
            and "clinical_asset_integrity_verified=bool(governance)"
            in procedure_extractor_provider
            and "test_explicit_t12_procedure_maps_to_actual_pinned_catalog_entry"
            in procedure_extractor_test
            and "test_planned_then_cancelled_is_never_promoted_to_performed"
            in procedure_extractor_test
            and '"procedure-extractor"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-diagnosis-extractor.v1"'
            in diagnosis_extractor_pack
            and '"status": "WARNING"' in diagnosis_extractor_pack
            and "exact_catalog_name_unique" in diagnosis_extractor_rules
            and '"assertion_status": "unresolved"' in diagnosis_extractor_rules
            and "authority_status=source_unverified" in diagnosis_extractor_rules
            and "class GovernedDiagnosisExtractorProvider"
            in diagnosis_extractor_provider
            and "clinical_asset_integrity_verified=bool(governance)"
            in diagnosis_extractor_provider
            and "test_explicit_current_diagnosis_uses_unique_catalog_entry_and_exact_spans"
            in diagnosis_extractor_test
            and "test_suspected_excluded_and_denied_diagnoses_remain_noncodable"
            in diagnosis_extractor_test
            and '"diagnosis-extractor"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-rule-explainer.v1"'
            in _read(official_agents_dir / "rule_explainer" / "agent_pack.json")
            and '"rule-explainer"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-medication-reconciliation.v1"'
            in _read(official_agents_dir / "med_reconciliation" / "agent_pack.json")
            and "NOT_ASSESSED_LICENSED_SOURCE_REQUIRED"
            in _read(official_agents_dir / "med_reconciliation" / "agent_pack.json")
            and '"med-reconciliation"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-nursing-handoff.v1"'
            in _read(official_agents_dir / "nursing_handoff" / "agent_pack.json")
            and '"schema_ref": "icoder/NursingHandoffOutput/v4"'
            in _read(official_agents_dir / "nursing_handoff" / "agent_pack.json")
            and "class GovernedNursingHandoffProvider"
            in _read(
                root
                / "backend"
                / "icoder_runtime"
                / "backends"
                / "governed_nursing_handoff_provider.py"
            )
            and '"nursing-handoff"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-icu-summary.v1"'
            in _read(official_agents_dir / "icu_summary" / "agent_pack.json")
            and '"schema_ref": "icoder/IcuSummaryOutput/v3"'
            in _read(official_agents_dir / "icu_summary" / "agent_pack.json")
            and "NOT_CALCULATED_GOVERNED_CALCULATOR_REQUIRED"
            in _read(official_agents_dir / "icu_summary" / "agent_pack.json")
            and "NOT_SCREENED_LICENSED_DRUG_SOURCE_REQUIRED"
            in _read(official_agents_dir / "icu_summary" / "agent_pack.json")
            and "class GovernedIcuSummaryProvider"
            in _read(
                root
                / "backend"
                / "icoder_runtime"
                / "backends"
                / "governed_icu_summary_provider.py"
            )
            and '"icu-summary"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-discharge-education.v1"'
            in _read(official_agents_dir / "discharge_edu" / "agent_pack.json")
            and '"schema_ref": "icoder/DischargeEducationOutput/v3"'
            in _read(official_agents_dir / "discharge_edu" / "agent_pack.json")
            and "NOT_RECONCILED_GOVERNED_MEDICATION_RECONCILIATION_REQUIRED"
            in _read(official_agents_dir / "discharge_edu" / "agent_pack.json")
            and "VERBATIM_DOCUMENTED_CONTENT_ONLY"
            in _read(official_agents_dir / "discharge_edu" / "agent_pack.json")
            and "class GovernedDischargeEducationProvider"
            in _read(
                root
                / "backend"
                / "icoder_runtime"
                / "backends"
                / "governed_discharge_education_provider.py"
            )
            and '"discharge-edu"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-discharge-summary.v1"'
            in _read(
                official_agents_dir
                / "discharge_summary_structuring"
                / "agent_pack.json"
            )
            and '"schema_ref": "icoder/DischargeSummaryStructured/v5"'
            in _read(
                official_agents_dir
                / "discharge_summary_structuring"
                / "agent_pack.json"
            )
            and "VERBATIM_SECTION_REORGANIZATION_ONLY"
            in _read(
                official_agents_dir
                / "discharge_summary_structuring"
                / "agent_pack.json"
            )
            and "class GovernedDischargeSummaryProvider"
            in _read(
                root
                / "backend"
                / "icoder_runtime"
                / "backends"
                / "governed_discharge_summary_provider.py"
            )
            and '"discharge-summary-structuring"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-referral.v1"'
            in _read(official_agents_dir / "referral_gen" / "agent_pack.json")
            and '"schema_ref": "icoder/ReferralOutput/v3"'
            in _read(official_agents_dir / "referral_gen" / "agent_pack.json")
            and "VERBATIM_TEMPLATE_ASSEMBLY_ONLY"
            in _read(official_agents_dir / "referral_gen" / "agent_pack.json")
            and "class GovernedReferralProvider"
            in _read(
                root
                / "backend"
                / "icoder_runtime"
                / "backends"
                / "governed_referral_provider.py"
            )
            and '"referral-gen"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-prior-authorization.v1"'
            in _read(official_agents_dir / "prior_auth" / "agent_pack.json")
            and '"schema_ref": "icoder/PriorAuthorizationOutput/v5"'
            in _read(official_agents_dir / "prior_auth" / "agent_pack.json")
            and "NOT_ASSESSED_POLICY_AND_CLINICAL_REVIEW_REQUIRED"
            in _read(official_agents_dir / "prior_auth" / "agent_pack.json")
            and "class GovernedPriorAuthorizationProvider"
            in _read(
                root
                / "backend"
                / "icoder_runtime"
                / "backends"
                / "governed_prior_authorization_provider.py"
            )
            and '"prior-auth"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-claim-check.v1"'
            in _read(official_agents_dir / "claim-check" / "agent_pack.json")
            and '"schema_ref": "icoder/ClaimCheckOutput/v4"'
            in _read(official_agents_dir / "claim-check" / "agent_pack.json")
            and "NOT_ASSESSED_LITERAL_PACKET_ONLY"
            in _read(official_agents_dir / "claim-check" / "agent_pack.json")
            and "class GovernedClaimCheckProvider"
            in _read(
                root
                / "backend"
                / "icoder_runtime"
                / "backends"
                / "governed_claim_check_provider.py"
            )
            and '"claim-check"' in agent_local_semantic_runner
            and '"backend_provider": "icoder.governed-triage-questionnaire.v1"'
            in _read(official_agents_dir / "triage" / "agent_pack.json")
            and '"schema_ref": "icoder/TriageOutput/v5"'
            in _read(official_agents_dir / "triage" / "agent_pack.json")
            and "final_acuity_assignment_performed"
            in _read(official_agents_dir / "triage" / "agent_pack.json")
            and "class GovernedTriageQuestionnaireProvider"
            in _read(
                root
                / "backend"
                / "icoder_runtime"
                / "backends"
                / "governed_triage_questionnaire_provider.py"
            )
            and '"triage"' in agent_local_semantic_runner
        ),
        "agent_hub_external_semantic_evidence_is_scoped_real_model_and_composable": (
            "EXPECTED_EXTERNAL_AGENT_COUNT = 2" in agent_external_semantic_bundle
            and "real model provider/name telemetry is absent"
            in agent_semantic_bundle
            and "validate_external_bundle_file" in agent_external_semantic_bundle
            and "EXPECTED_AGENT_COUNT = 26" in agent_composite_semantic_bundle
            and "scoped bundle union does not equal the 26 visible Agents"
            in agent_composite_semantic_bundle
            and "validate_composite_bundle_file" in agent_composite_semantic_bundle
            and "icoder.agent-hub-composite-semantic-evidence-bundle/v1"
            in agent_runtime_matrix_source
            and "ICODER_CREDENTIAL_LLM is not set in this PowerShell process"
            in agent_external_semantic_runner
            and "$env:ICODER_CREDENTIAL_LLM = $credential"
            in agent_external_semantic_runner
            and "-WindowStyle Hidden" in agent_external_semantic_runner
            and "ICODER_ALLOW_EXTERNAL_LLM = \"true\""
            in agent_external_semantic_runner
            and "ICODER_DISABLE_NATIVE_MEDCODER = \"true\""
            in agent_external_semantic_runner
            and "$agentCount -ne 26" in agent_external_semantic_runner
            and "Assert-CredentialAbsent" in agent_external_semantic_runner
            and "CREDENTIAL_DETECTED:" in agent_external_semantic_runner
            and "CREDENTIAL_SCAN_IO_ERROR:" in agent_external_semantic_runner
            and "Credential material was detected;"
            in agent_external_semantic_runner
            and "Credential scan could not complete;"
            in agent_external_semantic_runner
            and "$executionSucceeded" in agent_external_semantic_runner
            and "The primary E2E failure remains authoritative."
            in agent_external_semantic_runner
            and "external_semantic_e2e_failure.json"
            in agent_external_semantic_runner
            and 'diagnostic_content_scope = "bounded_first_line_credential_redacted_error_and_stderr_tail"'
            in agent_external_semantic_runner
            and 'credential_value_recorded = $false'
            in agent_external_semantic_runner
            and "$name -in $credentialEnvironmentNames"
            in agent_external_semantic_runner
            and "SetEnvironmentVariable($name, $null, \"Process\")"
            in agent_external_semantic_runner
            and "strict_26_agent_semantic_verified = 26"
            in agent_external_semantic_runner
            and '"--agent-p95-budget", "clinical-documentation-improvement-agent=30"'
            in agent_external_semantic_runner
            and '"--agent-p95-budget", "medical-coding-agent=10"'
            in agent_external_semantic_runner
            and "independent_clinical_gold_used = if ($IncludeClinicalCalibration)"
            in agent_external_semantic_runner
            and "clinical_independent_gold_claim_is_governed"
            in agent_external_artifact_validator
            and "validate_clinical_calibration_report_file"
            in agent_external_artifact_validator
            and "validate_agent_hub_external_artifacts.py"
            in agent_external_semantic_runner
            and "$artifactValidation.valid" in agent_external_semantic_runner
            and "Windows PowerShell 5.1" in agent_external_semantic_runner
            and "icoder.agent-hub-external-artifact-validation/v1"
            in agent_external_artifact_validator
            and '"matrix_external_pending_empty"' in agent_external_artifact_validator
            and '"source_artifacts"' in agent_external_artifact_validator
            and "test_external_bundle_rejects_absent_model_call_telemetry"
            in agent_semantic_bundle_test
            and "test_composite_bundle_is_only_valid_for_disjoint_current_24_plus_2"
            in agent_semantic_bundle_test
        ),
        "agent_hub_clinical_calibration_is_serial_attested_and_egress_governed": (
            "synthetic_development_calibration_not_independent_clinical_gold"
            in agent_clinical_calibration_plan
            and '"external_provider_egress_allowed": False'
            in agent_clinical_calibration_plan
            and "de-identification certificate not present"
            in agent_clinical_calibration_plan
            and "total_agent_invocations" in agent_clinical_calibration_plan
            and "EXPECTED_INVOCATIONS = 50" in agent_clinical_calibration_runner
            and "--acknowledge-external-provider-egress"
            in agent_clinical_calibration_runner
            and "clinical calibration is restricted to loopback transport"
            in agent_clinical_calibration_runner
            and "evaluate_single_dimension" in agent_clinical_calibration_runner
            and 'trace.get("model_call_observed") is True'
            in agent_clinical_calibration_runner
            and 'trace.get("trace_attestation_signature_verified") is True'
            in agent_clinical_calibration_runner
            and "CCL-derived 1,800/201/100-case records were not read"
            in agent_clinical_calibration_runner
            and "test_cdi_scoring_recomputes_multi_dimension_final_queries"
            in agent_clinical_calibration_test
            and "test_execution_checks_require_real_signed_non_degraded_model_trace"
            in agent_clinical_calibration_test
            and "IncludeClinicalCalibration" in agent_external_semantic_runner
            and "run_agent_hub_clinical_calibration_e2e.py"
            in agent_external_semantic_runner
            and "expected_serial_invocations = 50" in agent_external_semantic_runner
            and "independent_clinical_gold_used = if ($IncludeClinicalCalibration)"
            in agent_external_semantic_runner
            and "clinical_independent_gold_claim_is_governed"
            in agent_external_artifact_validator
            and "clinical_artifact_integrity_valid"
            in agent_external_artifact_validator
        ),
        "bilingual_coding_gold_review_is_blinded_dual_adjudicated_and_fail_closed": (
            "icoder.bilingual-coding-blind-review-packet/v1"
            in bilingual_gold_review
            and "icoder.bilingual-coding-independent-review/v1"
            in bilingual_gold_review
            and "icoder.bilingual-coding-gold-adjudication/v1"
            in bilingual_gold_review
            and "engineering_expected_codes_removed" in bilingual_gold_review
            and "model_outputs_included" in bilingual_gold_review
            and "def validate_blind_packet(" in bilingual_gold_review
            and "def validate_completed_review(" in bilingual_gold_review
            and "def compare_completed_reviews(" in bilingual_gold_review
            and "def validate_completed_adjudication(" in bilingual_gold_review
            and "independent reviews must use distinct reviewer IDs"
            in bilingual_gold_review
            and "adjudication_and_external_identity_verification_required"
            in bilingual_gold_review
            and "test_blind_packet_excludes_engineering_gold_and_is_digest_bound"
            in bilingual_gold_review_test
            and "test_completed_review_requires_catalog_codes_and_exact_bilingual_evidence"
            in bilingual_gold_review_test
            and "test_disagreement_is_routed_to_adjudication"
            in bilingual_gold_review_test
            and "test_completed_adjudication_is_bound_to_reviews_identity_and_final_codes"
            in bilingual_gold_review_test
            and "test_same_reviewer_cannot_satisfy_independence"
            in bilingual_gold_review_test
            and "--gold-adjudication" in agent_clinical_calibration_runner
            and "validate_completed_adjudication"
            in agent_clinical_calibration_runner
            and "apply_adjudicated_coding_gold" in agent_clinical_calibration_runner
            and "independent gold governance failed"
            in agent_clinical_calibration_runner
            and "test_validated_adjudication_replaces_engineering_gold_without_changing_charts"
            in agent_clinical_calibration_test
            and "BlindReviewPacketPath" in agent_external_semantic_runner
            and "ReviewerAResponsePath" in agent_external_semantic_runner
            and "ReviewerBResponsePath" in agent_external_semantic_runner
            and "GoldAdjudicationPath" in agent_external_semantic_runner
            and "All four independent gold review paths must be supplied together"
            in agent_external_semantic_runner
        ),
        "agent_failure_envelopes_are_suppressed_and_measured_separately": (
            agent_run.count('{"contract_output_suppressed": True}') >= 3
            and "manual_review_required=True" in agent_run
            and '"capability_passed": capability_passed' in agent_examples_e2e
            and '"safe_fail_closed": safe_fail_closed' in agent_examples_e2e
            and '"unsafe_or_invalid": unsafe_or_invalid' in agent_examples_e2e
            and '"semantic_capability_passed": semantic_passed' in agent_adversarial_e2e
            and '"safe_fail_closed": safe_fail_closed' in agent_adversarial_e2e
            and "shouldRenderCodingReviewSummary(result)" in medical_coding_page
            and "return !Boolean" in medical_coding_safety
        ),
        "provider_failures_have_bounded_retry_diagnostics_without_raw_content": (
            "class LLMProviderCallError(RuntimeError)" in legacy_llm_service
            and "def _classify_provider_error(" in legacy_llm_service
            and 'category="circuit_open"' in legacy_llm_service
            and "LLM call failed transiently: attempt=%s category=%s status=%s type=%s"
            in legacy_llm_service
            and "sensitive provider payload" not in legacy_llm_service
            and "provider_error_category: str = \"\"" in cdi_real_runner
            and "def _record_provider_failure(" in cdi_real_runner
            and '"provider_error_category", "provider_http_status"' in run_trace
            and '"provider_attempt_count", "provider_retryable"' in run_trace
            and "provider_error_category=" in specialized_telemetry
            and "provider_attempt_count=" in specialized_telemetry
            and "test_cdi_persists_only_bounded_provider_failure_diagnostics"
            in specialized_telemetry_test
            and "def _cdi_async_bridge()" in cdi_orchestrator
            and "class _CDIAsyncBridge:" in cdi_orchestrator
            and "asyncio.run_coroutine_threadsafe(coro, self.loop)"
            in cdi_orchestrator
            and 'name="icoder-cdi-async-bridge"' in cdi_orchestrator
            and "begin_run = getattr(self.runner, \"begin_run\", None)"
            in cdi_orchestrator
            and "end_run = getattr(self.runner, \"end_run\", None)"
            in cdi_orchestrator
            and "from app.services.llm_service import LLMService"
            in cdi_real_runner
            and "self._owns_llm = True" in cdi_real_runner
            and "self.llm = _run_async(create_client())" in cdi_real_runner
            and "_run_async(close())" in cdi_real_runner
            and "test_cdi_run_reuses_one_event_loop_across_all_llm_stages"
            in cdi_real_runner_test
            and "test_default_cdi_runner_closes_request_scoped_llm_client"
            in cdi_real_runner_test
            and 'category = "invalid_response"' in cdi_real_runner
            and "for structured_attempt in range(2)" in cdi_real_runner
            and "test_cdi_invalid_structured_response_fails_closed_after_one_retry"
            in cdi_real_runner_test
            and "structured_retry_used = False" in medical_coding_adapter
            and 'schema.degraded_reason = "invalid_response"'
            in medical_coding_adapter
            and "failed to parse structured response: length=%s"
            in medical_coding_adapter
            and "test_invalid_structured_response_fails_closed_after_one_retry"
            in medical_coding_adapter_test
        ),
        "corti_20_agent_catalog_is_mapped_and_development_verified": (
            validate_corti_prebuilt_agent_catalog(
                corti_prebuilt_catalog_path, official_agents_dir
            )["passed"]
        ),
        "agent_hub_visibility_is_launch_candidate_and_provider_fail_closed": (
            agent_hub_summary["hub_declared_visible_packs"] == 26
            and agent_hub_summary["hub_visible_agents"] == 26
            and agent_hub_summary["hub_declared_visible_excluded"] == []
            and agent_hub_summary["visible_not_ready"] == []
            and agent_hub_summary["visible_provider_resolvable"] == 26
            and agent_hub_summary["visible_legacy_default_routes"] == []
            and "normalized.launch_candidate_ready" in agent_hub_api
            and "resolve_from_agent_pack(normalized.raw)" in agent_hub_api
            and 'if maturity not in ("runnable", "production-ready", "production")'
            in agent_hub_api
            and 'schema_version: Literal["1.3"]' in agent_hub_api
            and '"runtime_readiness": {' in agent_hub_api
            and '"structural_status"' in agent_hub_api
            and '"configuration_status"' in agent_hub_api
            and '"semantic_validation_status": "not_verified"' in agent_hub_api
            and '"production_approval_status"' in agent_hub_api
            and '"live_health_verified": False' in agent_hub_api
            and "_attach_public_runtime_readiness(cards)" in agent_hub_api
            and '"/hub/readiness"' in agent_hub_api
            and "latest_tenant_canary_evidence(" in agent_hub_api
            and "tenant_cached_probe(" in agent_hub_api
            and "AgentHubTenantReadinessResponse" in agent_hub_api
            and "configured_not_live_verified" in agent_hub_api
            and "AgentHubListResponse" in agent_hub_api
            and "AgentHubRuntimeReadiness" in committed_openapi
            and "AgentHubTenantRuntimeReadiness" in committed_openapi
            and "AgentHubTenantReadinessResponse" in committed_openapi
            and '"/api/icoder/agents/hub/readiness"' in committed_openapi
            and '"$ref": "#/components/schemas/AgentHubListResponse"'
            in committed_openapi
            and "disabled={isCloningThis || !runActionEnabled}"
            in frontend_agent_hub_test
            and "listWithTenantReadiness" in frontend_agent_hub_test
            and "mergeHubTenantReadiness" in frontend_agent_hub_test
            and "AgentHubRuntimeReadiness" in javascript_agent_hub_types
            and "assertAgentHubResponse(data)" in javascript_agent_hub_resource
            and "async hubReadiness(options?: iCoDerRequestOptions):"
            in javascript_agent_hub_resource
            and "assertAgentHubTenantReadinessResponse(data)"
            in javascript_agent_hub_resource
            and "A2ALegacyAgentCard" in javascript_agent_hub_types
            and "AgentHubRuntimeReadiness" in python_agent_hub_types
            and "validate_agent_hub_response(resp.json())"
            in python_agent_hub_resource
            and "def hub_readiness(" in python_agent_hub_resource
            and "validate_agent_hub_tenant_readiness_response(resp.json())"
            in python_agent_hub_resource
            and "A2ALegacyAgentCard" in python_agent_hub_types
            and "AgentHubRuntimeReadiness" in dotnet_a2a_models
            and "ValidateReadiness(response)" in dotnet_agent_hub_resource
            and "GetReadinessAsync(" in dotnet_agent_hub_resource
            and "ValidateTenantReadiness(response)" in dotnet_agent_hub_resource
            and "A2ALegacyAgentCard" in dotnet_a2a_models
            and "test_hub_visibility_fails_closed_for_placeholder_and_unknown_provider"
            in agent_hub_matrix_test
            and "filterHubLaunchCandidateCards" in frontend_agent_hub_api
            and "HUB_LAUNCH_MATURITIES" in frontend_agent_hub_visibility
            and "candidate.launch_candidate_ready === true"
            in frontend_agent_hub_visibility
            and "fails closed to executable non-MVP launch candidates"
            in frontend_agent_hub_test
        ),
        "agent_template_catalog_is_pack_mastered_and_clone_safe": (
            _agent_template_catalog_is_pack_mastered()
            and "load_visible_launch_candidate_packs()" in agent_hub_api
            and "get_agent_template_catalog()" in agent_definitions_api
            and '"governed_template_clone_endpoint_required"'
            in agent_definitions_api
            and "selected.template_kind === 'governed_prebuilt'"
            in new_agent_page
            and "await agentHubApi.clone(" in new_agent_page
            and "routes Pack-mastered templates through Agent Hub clone"
            in new_agent_template_test
        ),
        "agent_definition_lifecycle_is_audited_fail_closed_and_ui_truthful": (
            "def assert_agent_published(" in agent_runtime_pack
            and '"agent_not_published"' in agent_runtime_pack
            and "assert_agent_published(db_agent)" in agent_runtime_pack
            and "assert_agent_published(db_agent)" in provider_a2a
            and '@router.post("/{agent_id}/publish")' in agent_definitions_api
            and '@router.post("/{agent_id}/archive")' in agent_definitions_api
            and '@router.post("/{agent_id}/restore")' in agent_definitions_api
            and 'for field in ("status", "is_published", "version")'
            in agent_definitions_api
            and '"A draft Agent cannot be archived; publish or delete it."'
            in agent_definitions_api
            and 'action="agent.lifecycle.created_published"'
            in agent_definitions_api
            and 'action="agent.lifecycle.updated"' in agent_definitions_api
            and 'action="agent.lifecycle.archived"' in agent_definitions_api
            and 'action="agent.lifecycle.restored"' in agent_definitions_api
            and 'action="agent.lifecycle.deleted"' in agent_definitions_api
            and 'action="agent.lifecycle.cloned_published"' in agent_hub_api
            and '"source_agent_ref", "source_runtime_agent_id", "changed_fields"'
            in audit_detail_redactor
            and 'AGENT_NOT_PUBLISHED = "AGENT_NOT_PUBLISHED"' in a2a_errors
            and "/rest/v1/agent_definitions/${id}/publish" in frontend_api
            and "/rest/v1/agent_definitions/${id}/archive" in frontend_api
            and "/rest/v1/agent_definitions/${id}/restore" in frontend_api
            and "runtimeAgentApi.getRunHistory" in agent_detail_page
            and "setRunHistoryError(message)" in agent_detail_page
            and 'role="alert"' in agent_detail_page
            and "catch { /* silently fail */ }" not in agent_detail_page
            and "agent.lifecycle.run_action_enabled !== true" in agent_detail_page
            and "runEvaluation" not in agent_detail_page
            and "primary_dx_accuracy" not in agent_detail_page
            and "test_project_agent_lifecycle_is_explicit_audited_and_fail_closed"
            in agent_lifecycle_test
            and '"is_published": False' in agent_lifecycle_test
            and 'invalid_archive.status_code == 409' in agent_lifecycle_test
            and "has no user-facing fake gold-standard evaluation action"
            in agent_detail_contract_test
            and '"/api/rest/v1/agent_definitions/{agent_id}/publish"'
            in committed_openapi
            and '"/api/rest/v1/agent_definitions/{agent_id}/archive"'
            in committed_openapi
            and '"/api/rest/v1/agent_definitions/{agent_id}/restore"'
            in committed_openapi
        ),
        "orchestrator_missing_llm_is_retryable_503_without_stub_response": (
            "def _unavailable_llm_call" in orchestrator_wiring
            and "raise PlannerError(" in orchestrator_wiring
            and 'code="planning_failed"' in orchestrator_wiring
            and "http_status=503" in orchestrator_wiring
            and "retryable=True" in orchestrator_wiring
            and orchestrator_wiring.count("return _unavailable_llm_call") == 2
            and "return _stub_llm_call" not in orchestrator_wiring
            and "test_build_llm_call_fails_closed_when_gateway_is_none"
            in orchestrator_wiring_test
            and "test_build_llm_call_fails_closed_when_gateway_not_configured"
            in orchestrator_wiring_test
            and "gw.generate.assert_not_called()" in orchestrator_wiring_test
        ),
        "orchestrator_missing_expert_is_503_without_noop_or_stub_success": (
            "def unavailable_expert_invoker" in orchestrator_wiring
            and "raise ExpertInvocationError(" in orchestrator_wiring
            and 'code="expert_failed"' in orchestrator_wiring
            and "http_status=503" in orchestrator_wiring
            and "def _stub_expert_invoker" not in orchestrator_wiring
            and "phase1_stub" not in orchestrator_wiring
            and "def noop_invoker" not in orchestrator_delegator
            and "noop_invoker" not in orchestrator_init
            and "test_e1_invoker_unknown_expert_id_fails_closed"
            in orchestrator_wiring_test
            and "test_e1_invoker_coding_expert_fails_closed_without_hybrid"
            in orchestrator_wiring_test
        ),
        "a2a_regressions_reject_mock_clinical_success_and_stale_fields": (
            "test_f2_3_a2a_message_send_fails_closed_without_provider"
            in a2a_compat_test
            and "assert resp.status_code == 503" in a2a_compat_test
            and 'assert "result" not in envelope' in a2a_compat_test
            and "test_f2_3_a2a_message_send_defaults_to_corti_like_fast"
            not in a2a_compat_test
            and "assert set(data) == expected_fields" in three_agent_a2a_smoke
            and 'data["trace_refs"]["run_id"] == result["metadata"]["run_id"]'
            in three_agent_a2a_smoke
        ),
        "provider_a2a_datapart_is_exact_pack_output_allowlist": (
            "declared_optional_fields" in provider_a2a
            and "declared_result_fields" in provider_a2a
            and "for field in declared_result_fields" in provider_a2a
            and "if field in public.result" in provider_a2a
            and 'assert "structured_extraction" not in data'
            in provider_a2a_test
            and 'assert "backend_provider" not in data' in provider_a2a_test
            and "assert required.issubset(data)" in visible_agent_contract_test
            and "assert set(data).issubset(allowed)" in visible_agent_contract_test
            and "public_result = {" in app_main
            and "for field in declared_fields" in app_main
            and "if field in public.result" in app_main
            and '"data": public_result' in app_main
        ),
        "native_provider_stream_keeps_provisional_content_private_and_terminal_exact": (
            'set(item) == {"kind", "characters", "native", "provisional"}'
            in native_provider_stream_test
            and '"validated native stream" not in json.dumps(progress)'
            in native_provider_stream_test
            and "assert required.issubset(data)" in native_provider_stream_test
            and "assert set(data).issubset(allowed)" in native_provider_stream_test
            and 'assert "structured_extraction" not in data'
            in native_provider_stream_test
            and 'assert "backend_provider" not in data'
            in native_provider_stream_test
        ),
        "openinference_export_uses_standard_bounded_provider_tool_and_usage_attributes": (
            '"openinference.span.kind": "AGENT"' in agentic_observability
            and 'attributes["tool.name"] = tool_name' in agentic_observability
            and 'attributes["llm.provider"] = model_provider' in agentic_observability
            and 'attributes["llm.system"] = model_system' in agentic_observability
            and 'attributes["llm.model_name"] = model_name' in agentic_observability
            and 'attributes["llm.cost.total"] = float(model_cost)'
            in agentic_observability
            and '"icoder.trace.input_exported": False' in agentic_observability
            and '"icoder.trace.output_exported": False' in agentic_observability
            and '"model_provider", "model_system", "model_name", "input_tokens"'
            in run_trace
            and "def _model_telemetry_from_raw" in pure_llm_provider
            and "_accumulate_model_telemetry" in llm_with_tools_provider
            and 'result.setdefault("provider", primary_name)' in llm_gateway
            and 'assert event.safe_metadata["model_provider"] == "deepseek"'
            in run_trace_backend_test
            and 'assert llm_span["attributes"]["llm.provider"] == "deepseek"'
            in feedback_training_test
            and 'assert "must-not-export" not in serialized'
            in feedback_training_test
        ),
        "dedicated_clinical_runtimes_emit_bounded_content_free_telemetry": (
            "def build_medical_coding_telemetry_event" in specialized_telemetry
            and "def build_cdi_telemetry_event" in specialized_telemetry
            and 'backend_type="medical_coding"' in specialized_telemetry
            and 'backend_type="cdi_orchestrator"' in specialized_telemetry
            and "if provider.lower() == \"mock\" or degraded"
            in specialized_telemetry
            and "complete_usage = bool(calls)" in specialized_telemetry
            and "build_backend_safe_metadata" in specialized_telemetry
            and "def build_configured_cny_cost" in specialized_telemetry
            and '"source": "configured_usage_pricing_estimate"'
            in specialized_telemetry
            and '"billing_authoritative": False' in specialized_telemetry
            and '"cost_amount", "cost_currency", "cost_source", "billing_authoritative"'
            in run_trace
            and '"orchestration_latency_ms", "instrumented_stage_latency_ms"'
            in run_trace
            and '"model_call_latency_sum_ms", "non_provider_wall_latency_ms"'
            in run_trace
            and '"non_provider_wall_latency_known", "parallel_model_calls_observed"'
            in run_trace
            and "class CDIModelCallTrace" in cdi_domain
            and "safety_gate_model_traces: list[CDIModelCallTrace]"
            in cdi_domain
            and "stage_duration_ms: dict[str, int]" in cdi_domain
            and "class _SafetyGateTelemetryLLM" in cdi_orchestrator
            and cdi_orchestrator.count("case.safety_gate_model_traces") >= 2
            and "case.stage_duration_ms[stage]" in cdi_orchestrator
            and "build_medical_coding_telemetry_event" in a2a_facade
            and "build_cdi_telemetry_event" in cdi_a2a_handler
            and "build_configured_cny_cost(" in cdi_a2a_handler
            and "safety_gate_traces=list(" in cdi_a2a_handler
            and "orchestration_latency_ms=orchestration_latency_ms"
            in cdi_a2a_handler
            and "gate_max_concurrency=settings.ICODER_CDI_GATE_MAX_CONCURRENCY"
            in cdi_a2a_handler
            and "ICODER_CDI_LATENCY_BUDGET_MS: int = 30_000"
            in backend_config
            and "ICODER_CDI_GATE_MAX_CONCURRENCY: int = 3"
            in backend_config
            and "async def _bounded_gate_map" in cdi_orchestrator
            and "limit = min(max(configured_limit, 1), 4)" in cdi_orchestrator
            and "asyncio.Semaphore(limit)" in cdi_orchestrator
            and "cost = _normalized_runtime_cost" in agent_run
            and "def transcribe_bytes_with_telemetry" in stt_service
            and '"icoder/stt-inference-telemetry/v1"' in stt_service
            and 'request_data["_runtimeTelemetry"] = safe'
            in stt_artifact_repository
            and 'for key in ("schema", "provider", "model", "status")'
            in stt_artifact_repository
            and "test_medical_coding_degraded_mock_does_not_publish_fake_llm_usage"
            in specialized_telemetry_test
            and "test_cdi_omits_partial_token_aggregate_and_marks_degraded_failed"
            in specialized_telemetry_test
            and "test_configured_cost_rejects_untrusted_prices_and_unobserved_calls"
            in specialized_telemetry_test
            and "test_cdi_includes_gate_calls_and_content_free_latency_attribution"
            in specialized_telemetry_test
            and "test_cdi_serial_latency_keeps_non_provider_wall_attribution"
            in specialized_telemetry_test
            and "test_gate_internal_llm_calls_are_accounted_without_clinical_content"
            in cdi_orchestrator_test
            and "test_per_query_gate_calls_use_bounded_concurrency_and_preserve_order"
            in cdi_orchestrator_test
            and "[(3, 3), (99, 4), (0, 1)]" in cdi_orchestrator_test
            and 'assert response.metadata["cost"] == {'
            in cdi_public_handler_test
            and 'assert metadata["cost_source"] == "configured_usage_pricing_estimate"'
            in cdi_public_handler_test
            and "test_repository_persists_only_bounded_stt_telemetry_allowlist"
            in stt_telemetry_test
            and 'assert "patient-audio-canary" not in serialized'
            in stt_telemetry_test
        ),
        "a2a_structural_task_artifact_ids_bypass_free_text_phi_redaction_safely": (
            'client_metadata.pop("_a2a_v1_task_id", None)' in a2a_routes
            and 'server_task_id: str = ""' in a2a_routes
            and '{"_a2a_v1_task_id": server_task_id}' in a2a_routes
            and "server_task_id=task_id" in a2a_v1_routes
            and "server_task_id=execution.task_id" in a2a_v1_task_runtime
            and "test_v1_http_stream_is_a2a_sse" in a2a_v1_endpoint_test
            and 'task_hex = "edfdd29b4af138001380002c2f27ae1"'
            in a2a_v1_endpoint_test
            and "test_v0_client_cannot_inject_internal_v1_task_correlation"
            in a2a_v1_endpoint_test
        ),
        "feedback_training_requires_independent_bounded_owner_authorization": (
            'purpose_of_use = \'quality_improvement\'' in feedback_model
            and 'data_scope = \'feedback_metadata_only\'' in feedback_model
            and "feedback_digest" in feedback_model
            and 'down_revision = "053"' in feedback_training_migration
            and "Depends(_feedback_training_admin)" in agentic_observability
            and '_TRAINING_AUTHORIZATION_MAX_DAYS = 30' in agentic_observability
            and "_feedback_training_digest" in agentic_observability
            and "_revoke_feedback_training_authorizations" in agentic_observability
            and '"training_authorized": False' in agentic_observability
            and '"feedback_reason_authorized": False' in agentic_observability
            and '"task_or_message_content_authorized": False' in agentic_observability
            and '"agentic.feedback.training_authorization.granted"'
            in system_audit_service
            and '"agentic.feedback.training_authorization.revoked"'
            in system_audit_service
            and "assert denied.status_code == 403" in feedback_training_test
            and 'assert body["trainingAuthorized"] is True'
            in feedback_training_test
            and 'state.json()["authorizationStatus"] == "revoked"'
            in feedback_training_test
            and "authorizeFeedbackForTraining" in javascript_a2a
            and "authorize_feedback_for_training" in python_a2a
            and "AuthorizeFeedbackForTrainingAsync" in dotnet_a2a
            and "FeedbackTrainingAuthorizationInput" in dotnet_a2a_models
        ),
        "cdi_required_safety_gate_degradation_is_structured_and_unpublished": (
            "degraded_safety_gates: dict[str, str]" in cdi_domain
            and 'case.degraded_safety_gates["claim_evidence_alignment_gate"]'
            in cdi_orchestrator
            and 'case.degraded_safety_gates["semantic_necessity_gate"]'
            in cdi_orchestrator
            and "if gate.degraded" in cdi_orchestrator
            and cdi_api.index(
                "degraded_safety_gates = dict(case.degraded_safety_gates)"
            ) < cdi_api.index("# Gate 3: persist case + gaps + queries atomically")
            and '"degraded_safety_gates": sorted(degraded_safety_gates)'
            in cdi_api
            and "await tenant_owned_system_audit(" in cdi_api
            and 'action="cdi.run.failed.required_gate_degraded"' in cdi_api
            and '"clinical_result_published": False' in cdi_api
            and "await db.commit()" in cdi_api
            and "await db.rollback()" in cdi_api
            and '"cdi.run.failed.required_gate_degraded"' in system_audit_service
            and '"cdi.run.failed.required_gate_degraded"'
            in legacy_tenancy_attribution
            and "degraded = bool(degraded_safety_gates)" in cdi_a2a_handler
            and '"degraded_safety_gates": sorted(degraded_safety_gates)'
            in cdi_a2a_handler
            and "test_semantic_gate_degradation_is_structured_on_case"
            in cdi_orchestrator_test
            and "test_claim_evidence_gate_degradation_is_structured_on_case"
            in cdi_orchestrator_test
            and "test_required_safety_gate_degradation_publishes_no_a2a_result"
            in cdi_public_handler_test
            and "test_required_safety_gate_degradation_is_not_persisted_by_rest"
            in cdi_public_handler_test
            and "test_required_gate_audit_failure_still_publishes_no_rest_result"
            in cdi_public_handler_test
            and 'audit_kwargs["details"]["clinical_result_published"] is False'
            in cdi_public_handler_test
        ),
        "llm_egress_policy_is_enforced_at_gateway_and_legacy_boundaries": (
            "def _egress_denial" in llm_gateway
            and "self._data_policy.egress_decision" in llm_gateway
            and "denied = self._egress_denial(provider)" in llm_gateway
            and "denied = self._egress_denial(candidate)" in llm_gateway
            and "data_policy=data_policy" in app_main
            and "tenant_provider_resolver=resolve_tenant_model_route" in app_main
            and "def _ensure_llm_call_allowed" in legacy_llm_service
            and legacy_llm_service.count("_ensure_llm_call_allowed()") >= 4
            and "EXTERNAL_LLM_PROVIDERS" in llm_data_policy
            and '"qwen": "cn"' in llm_data_policy
        ),
        "model_provider_selection_is_explicit_and_fails_closed": (
            "SUPPORTED_PRIMARY_PROVIDERS" in llm_provider_factory
            and "unsupported LLM_PROVIDER" in llm_provider_factory
            and "provider_endpoint_mismatch" in model_catalog_service
            and "create_primary_llm_provider" in app_main
            and "Primary LLM registration failed closed" in app_main
            and re.search(r"(?m)^ICODER_ALLOW_EXTERNAL_LLM=false$", env_template)
            is not None
            and re.search(r"(?m)^ICODER_REGION=cn$", env_template) is not None
            and re.search(r"(?m)^ICODER_EGRESS_POLICY=strict$", env_template)
            is not None
        ),
        "database_sql_logging_is_opt_in_and_parameter_safe": (
            '"echo": settings.ICODER_DATABASE_SQL_ECHO' in backend_database
            and '"hide_parameters": True' in backend_database
            and "ICODER_DATABASE_SQL_ECHO: bool = False" in backend_config
            and "ICODER_DATABASE_SQL_ECHO=true is forbidden in cloud mode"
            in backend_config
            and backend_env.get("ICODER_DATABASE_SQL_ECHO")
            == "${ICODER_DATABASE_SQL_ECHO:-false}"
            and "ICODER_DATABASE_SQL_ECHO=false" in env_template
        ),
        "sqlite_reconciliation_is_read_only_staged_and_fail_closed": (
            "?mode=ro" in sqlite_reconciliation
            and "source_connection.backup(destination)" in sqlite_reconciliation
            and '"--stage-copy-upgrade"' in sqlite_reconciliation
            and '"--quarantine-orphan-organizations"' in sqlite_reconciliation
            and "refusing to overwrite staged artifact" in sqlite_reconciliation
            and '"source_unchanged": source_unchanged' in sqlite_reconciliation
            and '"preexisting_data_preserved"' in sqlite_reconciliation
            and '"candidate_matches_orm"' in sqlite_reconciliation
            and "(id, name, slug, plan, settings, is_active)" in sqlite_reconciliation
            and '(organization_id, name, slug, "free", settings, 0)'
            in sqlite_reconciliation
            and '"cutover_performed": False' in sqlite_reconciliation
        ),
        "a2a_local_working_task_cancellation_is_truthful_and_audited": (
            "async def cancel_running" in a2a_v1_task_runtime
            and "task.cancel()" in a2a_v1_task_runtime
            and "return task.cancelled()" in a2a_v1_task_runtime
            and "canceled_here = await task_runtime.cancel_running(task_id)"
            in a2a_v1_routes
            and "already executing outside this runtime" in a2a_v1_routes
            and "test_local_working_task_can_be_canceled_without_late_result"
            in a2a_v1_runtime_test
            and "execution.result_json is None" in a2a_v1_runtime_test
        ),
        "agentic_v2_context_task_artifact_resources_are_real_and_isolated": (
            'prefix="/api/v2/agentic/contexts"' in agentic_context_resources
            and "async def list_contexts" in agentic_context_resources
            and "async def get_context" in agentic_context_resources
            and "async def delete_context" in agentic_context_resources
            and "async def list_context_tasks" in agentic_context_resources
            and "async def get_context_task" in agentic_context_resources
            and "async def get_task_artifact" in agentic_context_resources
            and "ContextRow.organization_id == organization_id"
            in agentic_context_resources
            and "Do not fall back to context-level artifact references"
            in agentic_context_resources
            and '"agentic.context.delete"' in agentic_context_resources
            and "test_context_detail_has_oldest_first_full_task_history_and_artifact"
            in agentic_context_resources_test
            and "test_context_resources_are_tenant_and_scope_isolated_and_delete_is_audited"
            in agentic_context_resources_test
            and "listContextsV2" in javascript_a2a
            and "getTaskArtifactV2" in javascript_a2a
            and "def list_contexts_v2" in python_a2a
            and "def get_task_artifact_v2" in python_a2a
            and "ListContextsV2Async" in dotnet_a2a
            and "GetTaskArtifactV2Async" in dotnet_a2a
        ),
        "task_artifacts_are_durable_encrypted_integrity_checked_and_owned": (
            '"a2a_task_artifacts"' in task_artifact_migration
            and '["context_id", "task_id"]' in task_artifact_migration
            and 'ondelete="CASCADE"' in task_artifact_migration
            and 'down_revision = "049"' in task_artifact_migration
            and "encrypt_phi" in a2a_v1_artifact_store
            and "payload_sha256" in a2a_v1_artifact_store
            and "Artifact digest integrity check failed" in a2a_v1_artifact_store
            and "Part.url must be an HTTPS URL" in a2a_v1_artifact_store
            and "await persist_artifacts(" in a2a_v1_task_runtime
            and "await load_task_artifacts(" in a2a_v1_routes
            and "test_artifact_is_encrypted_and_owned_by_exact_context_and_task"
            in task_artifact_test
            and "test_artifact_digest_corruption_fails_closed" in task_artifact_test
        ),
        "a2a_v1_streams_use_standard_status_and_artifact_update_events": (
            'down_revision = "050"' in standard_artifact_event_migration
            and '"artifact_id"' in standard_artifact_event_migration
            and '"artifact_append"' in standard_artifact_event_migration
            and '"artifact_last_chunk"' in standard_artifact_event_migration
            and 'stream_response = {"artifactUpdate"' in a2a_v1_routes
            and 'stream_response = {"statusUpdate"' in a2a_v1_routes
            and 'initial_response = {"task": initial_task}' in a2a_v1_routes
            and 'sse_event = "artifact-update"' in a2a_v1_routes
            and 'artifact_last_chunk=True' in a2a_v1_task_runtime
            and "A2AV1TaskArtifactUpdateEvent" in javascript_a2a
            and "A2AV1StreamResponse" in javascript_a2a
            and "A2AV1TaskArtifactUpdateEvent" in dotnet_a2a_models
            and '"artifact-update"' in a2a_v1_endpoint_test
            and 'artifact_update["lastChunk"] is True' in a2a_v1_endpoint_test
        ),
        "a2a_v1_interrupted_tasks_resume_and_ai_sdk_adapter_is_fail_closed": (
            'down_revision = "054"' in a2a_v1_state_migration
            and "'input-required'" in a2a_v1_state_migration
            and "'auth-required'" in a2a_v1_state_migration
            and "'rejected'" in a2a_v1_state_migration
            and "Cannot downgrade revision 055" in a2a_v1_state_migration
            and "INPUT_REQUIRED = \"input-required\"" in a2a_task_state
            and "AUTH_REQUIRED = \"auth-required\"" in a2a_task_state
            and "REJECTED = \"rejected\"" in a2a_task_state
            and "SETTLED_STATES" in a2a_task_state
            and "current in INTERRUPTED_STATES" in a2a_v1_routes
            and '.values(state=TaskState.WORKING.value, completed_at=None)'
            in a2a_v1_routes
            and "settled_state_from_result" in a2a_v1_task_runtime
            and "test_input_required_task_is_durable_resumable_and_completes"
            in a2a_v1_runtime_test
            and "export function convertToParams" in javascript_ai_adapter
            and "export function toUIMessageStream" in javascript_ai_adapter
            and "export function createA2AClientFactory" in javascript_ai_adapter
            and "export function createFetchImplementation" in javascript_ai_adapter
            and "configured SDK origin" in javascript_ai_adapter
            and "credentials: 'omit'" in javascript_ai_adapter
            and "headers.set('Authorization'" in javascript_ai_adapter
            and "headers.delete('Cookie')" in javascript_ai_adapter
            and "A2A stream conversion failed" in javascript_ai_adapter
            and "fails closed without leaking upstream errors"
            in javascript_ai_adapter_test
            and "actual Vercel AI SDK response consumes official StreamResponse objects"
            in javascript_ai_adapter_test
            and "@a2a-js/sdk" in javascript_sdk_package
            and '">=1.0.0 <2.0.0"' in javascript_sdk_package
            and "new JsonRpcTransportFactory" in javascript_ai_adapter
            and "new DefaultAgentCardResolver" in javascript_ai_adapter
            and "return new ClientFactory" in javascript_ai_adapter
            and "official ClientFactory discovers the iCoDer card"
            in javascript_ai_adapter_test
            and "client.sendMessageStream" in javascript_official_a2a_helper
            and "test_official_a2a_js_sdk_package_interoperates_with_live_backend"
            in a2a_v1_endpoint_test
            and "Install official A2A JavaScript interoperability dependency"
            in integration_workflow
            and "npm test" in sdk_js_runs
            and "taskId?: string" in javascript_a2a
            and "task_id: Optional[str] = None" in python_a2a
            and "TaskId = taskId" in dotnet_a2a
            and 'JsonPropertyName("taskId")' in dotnet_a2a_models
        ),
        "a2a_v1_artifact_streams_persist_exact_encrypted_chunks_and_sdk_entrypoints": (
            'down_revision = "051"' in artifact_event_payload_migration
            and '"artifact_payload_json"' in artifact_event_payload_migration
            and '"artifact_payload_sha256"' in artifact_event_payload_migration
            and '"artifact_payload_size_bytes"' in artifact_event_payload_migration
            and "encode_event_artifact" in a2a_v1_artifact_store
            and "decode_event_artifact" in a2a_v1_artifact_store
            and "load_completed_stream_artifact" in a2a_v1_artifact_store
            and "validated_stream_artifact_chunks" in a2a_routes
            and '"a2a_validated_artifact_chunk"' in a2a_routes
            and "await self._persist_artifact_chunk" in a2a_v1_task_runtime
            and "initial_replay_sequence=submitted_sequence" in a2a_v1_routes
            and "async messageStreamV1(" in javascript_a2a
            and "def message_stream_v1(" in python_a2a
            and "MessageStreamV1Async(" in dotnet_a2a
            and "test_validated_response_is_persisted_as_exact_multi_chunk_stream"
            in a2a_v1_runtime_test
            and "test_artifact_event_replay_uses_exact_encrypted_chunks_and_detects_tamper"
            in task_artifact_test
        ),
        "managed_artifact_objects_are_quarantined_scanned_single_use_and_sdk_visible": (
            'down_revision = "052"' in artifact_object_migration
            and '"a2a_artifact_objects"' in artifact_object_migration
            and '"a2a_artifact_download_grants"' in artifact_object_migration
            and "payload_ciphertext" in artifact_object_migration
            and "MALWARE_TEST_SIGNATURE" in a2a_v1_artifact_object_store
            and "DEIDENTIFICATION_POLICY_BLOCKED" in a2a_v1_artifact_object_store
            and "PDF_ACTIVE_CONTENT" in a2a_v1_artifact_object_store
            and "Fernet(_object_key()).encrypt" in a2a_v1_artifact_object_store
            and "consumed_at.is_(None)" in a2a_v1_artifact_object_store
            and "synchronize_session=False" in a2a_v1_artifact_object_store
            and "_require_object_audit_enabled" in agentic_context_resources
            and "Persist single-use consumption and audit before protected bytes leave"
            in agentic_context_resources
            and "test_managed_artifact_object_full_lifecycle_is_single_use_and_audited"
            in agentic_context_resources_test
            and "test_managed_artifact_object_dlp_malware_tenant_and_context_deletion"
            in agentic_context_resources_test
            and "uploadTaskArtifactObjectV2" in javascript_a2a
            and "authorizeTaskArtifactObjectDownloadV2" in javascript_a2a
            and "def upload_task_artifact_object_v2" in python_a2a
            and "def authorize_task_artifact_object_download_v2" in python_a2a
            and "UploadTaskArtifactObjectV2Async" in dotnet_a2a
            and "AuthorizeTaskArtifactObjectDownloadV2Async" in dotnet_a2a
        ),
        "artifact_download_grants_are_actor_bound_and_query_secret_free": (
            "DOWNLOAD_GRANT_INVALID" in a2a_v1_artifact_object_store
            and "A2AArtifactDownloadGrantRow.organization_id == organization_id"
            in a2a_v1_artifact_object_store
            and "A2AArtifactDownloadGrantRow.actor_type == actor_type"
            in a2a_v1_artifact_object_store
            and "A2AArtifactDownloadGrantRow.actor_id_hash == actor_id_hash"
            in a2a_v1_artifact_object_store
            and "hmac.compare_digest(grant.actor_id_hash, actor_id_hash)"
            in a2a_v1_artifact_object_store
            and '"/download/{grant_id}"' in agentic_context_resources
            and "get_current_user_or_oauth_client" in agentic_context_resources
            and "?token=" not in agentic_context_resources
            and "install_uvicorn_access_log_privacy()" in app_main
            and 'split("?", 1)[0]' in access_log_privacy
            and "[grant-redacted]" in access_log_privacy
            and all(
                all(
                    token in config
                    for token in (
                        "log_format icoder_safe",
                        '"$request_method $uri $server_protocol"',
                        "artifact-objects/download/",
                        "access_log off",
                        "proxy_set_header Authorization $http_authorization",
                        "proxy_buffering off",
                        "proxy_cache off",
                    )
                )
                and "$http_referer" not in config
                for config in (nginx, local_nginx)
            )
            and "test_managed_artifact_download_requires_authenticated_principal"
            in agentic_context_resources_test
        ),
        "models_catalog_is_authenticated_secret_free_and_sdk_visible": (
            'Depends(get_current_user)' in model_catalog_api
            and 'response.headers["Cache-Control"] = "no-store"' in model_catalog_api
            and "live_health_verified: Literal[False]" in model_catalog_api
            and "credential_configured" in model_catalog_service
            and "configured_base_url" in model_catalog_service
            and "LLM_BASE_URL" not in models_page
            and "ICODER_CREDENTIAL_LLM" not in models_page
            and 'path="models" element={<ModelsPage />}' in frontend_app
            and javascript_models_path.is_file()
            and python_models_path.is_file()
            and dotnet_models_path.is_file()
        ),
        "model_live_canary_is_fixed_phi_free_budgeted_and_cooled": (
            "ICODER_MODEL_LIVE_CANARY_ENABLED: bool = False" in backend_config
            and "ICODER_MODEL_LIVE_CANARY_MAX_COST_CNY: float = 0.05"
            in backend_config
            and "ICODER_MODEL_LIVE_CANARY_MAX_OUTPUT_TOKENS: int = 8"
            in backend_config
            and "ICODER_MODEL_LIVE_CANARY_TIMEOUT_SECONDS: float = 15.0"
            in backend_config
            and "ICODER_MODEL_LIVE_CANARY_COOLDOWN_SECONDS: int = 300"
            in backend_config
            and re.search(
                r"(?m)^ICODER_MODEL_LIVE_CANARY_ENABLED=false$", env_template
            ) is not None
            and 'model_config = ConfigDict(extra="forbid")' in model_catalog_api
            and "acknowledge_external_call: Literal[True]" in model_catalog_api
            and 'purpose: Literal["connectivity_only_no_patient_data"]'
            in model_catalog_api
            and "max_cost_cny: float = Field(gt=0, le=1.0)" in model_catalog_api
            and "_LIVE_CANARY_MESSAGES" in model_catalog_api
            and '"ICODER_SYNTHETIC_CONNECTIVITY_CANARY"' in model_catalog_api
            and 'Depends(require_org_role("owner", "admin"))' in model_catalog_api
            and ".with_for_update()" in model_catalog_api
            and '"model.live_canary.started"' in model_catalog_api
            and 'headers={"Retry-After": str(cooldown_seconds)}'
            in model_catalog_api
            and '"max_attempts": 1' in model_catalog_api
            and "asyncio.wait_for(" in model_catalog_api
            and "estimated_max_cost > body.max_cost_cny" in model_catalog_api
            and "reported_cost > body.max_cost_cny" in model_catalog_api
            and "patient_data_sent: Literal[False] = False" in model_catalog_api
            and bool(canary_response_contract)
            and "prompt" not in canary_response_contract.casefold()
            and "content" not in canary_response_contract.casefold()
            and "def _bounded_request_limits(" in llm_gateway
            and "request_max_tokens" in llm_gateway
            and "request_timeout" in llm_gateway
            and "liveCanary:" in frontend_api
            and "acknowledge_external_call: true" in frontend_api
            and "window.confirm" in models_page
            and "No free text is accepted" in models_page
            and "async liveCanary(" in javascript_models
            and "def live_canary(" in python_models
            and "LiveCanaryAsync(" in dotnet_models
            and all(
                "prompt" not in source.casefold()
                for source in (javascript_models, python_models, dotnet_models)
            )
        ),
        "tenant_model_selection_is_versioned_audited_and_fail_closed": (
            "MODEL_SELECTION_VERSION_CONFLICT" in model_catalog_api
            and 'Depends(require_org_role("owner", "admin"))' in model_catalog_api
            and '"model.selection.update"' in model_catalog_api
            and "MODEL_DEPLOYMENT_NOT_SELECTABLE" in model_catalog_api
            and '"_model_routing"' in organization_api
            and "def selection_from_settings" in tenant_model_routing
            and "select(Organization.settings)" in tenant_model_routing
            and "def get_exact" in llm_gateway
            and "tenant_model_deployment_unavailable" in llm_gateway
            and "Pinned deployments never silently" in models_page
            and "create_configured_llm_deployments" in llm_provider_factory
            and "Inline LLM credentials are forbidden" in llm_provider_factory
            and "ICODER_LLM_DEPLOYMENTS_JSON" in env_template
            and '"model_deployment_id"' in run_trace
            and '"model_selection_version"' in run_trace
            and "model_routing=model_routing" in pure_llm_provider
            and "_model_routing_from_raw" in llm_with_tools_provider
            and "model deployment:" in run_trace_page
            and "selection version:" in run_trace_page
        ),
        "platform_user_access_is_versioned_audited_and_revoking": (
            "class PlatformUserAccessUpdate" in admin_api
            and "expected_token_version" in admin_api
            and "STALE_USER_ACCESS_VERSION" in admin_api
            and "Platform administrators cannot modify their own access" in admin_api
            and "Cannot remove the last active platform administrator" in admin_api
            and 'action="platform_admin.user_access_updated"' in admin_api
            and "_revoke_user_tokens" in admin_api
            and "client.is_active = False" in admin_api
        ),
        "platform_organization_control_is_validated_audited_and_revoking": (
            "class PlatformOrganizationUpdate" in admin_api
            and 'Literal["free", "pro", "enterprise"]' in admin_api
            and 'action="platform_admin.organization_updated"' in admin_api
            and "user.token_version += 1" in admin_api
            and "token.is_revoked = True" in admin_api
        ),
        "first_platform_admin_bootstrap_is_explicit_one_time_and_dry_run": (
            "dry-run by default" in bootstrap_admin
            and "if active_admins:" in bootstrap_admin
            and 'parser.add_argument("--execute", action="store_true"' in bootstrap_admin
            and 'reason_code": "initial_bootstrap"' in bootstrap_admin
            and 'action="platform_admin.user_access_updated"' in bootstrap_admin
        ),
        "platform_access_console_is_admin_gated": (
            "function PlatformAdminRoute" in frontend_app
            and "user?.role !== 'admin'" in frontend_app
            and "<PlatformAdminRoute><PlatformAccessPage /></PlatformAdminRoute>" in frontend_app
            and "expected_token_version: user.token_version" in platform_access_page
            and "平台角色与组织角色相互独立" in platform_access_page
        ),
        "stateful_services_have_healthchecks": all(
            bool((services.get(name) or {}).get("healthcheck")) for name in ("db", "redis", "backend")
        ),
        "backend_image_runs_non_root": bool(
            re.search(r"(?m)^USER\s+icoder\s*$", backend_df)
            and "adduser --system" in backend_df
            and "COPY --chown=icoder:icoder" in backend_df
        ),
        "backend_image_has_healthcheck": "HEALTHCHECK" in backend_df and "/api/health" in backend_df,
        "backend_image_excludes_native_ml_stack": (
            "-r requirements-api.txt" in backend_df
            and "COPY requirements-ml" not in backend_df
            and "-r requirements-ml" not in backend_df
            and all(
                package not in api_requirements
                for package in ("sentence-transformers", "faiss-cpu", "torch", "pyarrow")
            )
            and "sentence-transformers" in ml_requirements
            and "faiss-cpu" in ml_requirements
        ),
        "backend_image_has_explicit_postgres_trace_driver": (
            "psycopg[binary]==3.3.4" in api_requirements
            and "postgresql+psycopg://" in run_trace
            and "def to_sync_database_url" in run_trace
        ),
        "ml_worker_image_is_minimal_and_isolated": (
            "-r requirements-ml.txt" in ml_worker_requirements
            and "requirements-api.txt" not in ml_worker_requirements
            and "requirements-api.txt" not in ml_worker_df
            and "-r requirements-ml-worker.txt" in ml_worker_df
            and re.search(r"(?m)^USER\s+icoder-ml\s*$", ml_worker_df) is not None
            and '"--workers", "1"' in ml_worker_df
            and "MEDCODER_WORKER_WARMUP=1" in ml_worker_df
            and f"MEDCODER_BGE_REVISION={EXPECTED_BGE_REVISION}"
            in ml_worker_df
            and "MEDCODER_BGE_LOCAL_FILES_ONLY=1" in ml_worker_df
            and "HF_HUB_OFFLINE=1" in ml_worker_df
            and "TRANSFORMERS_OFFLINE=1" in ml_worker_df
        ),
        "compose_ml_worker_is_internal_and_fail_closed": (
            (services.get("medcoder-retriever") or {}).get("profiles") == ["ml"]
            and not (services.get("medcoder-retriever") or {}).get("ports")
            and (services.get("medcoder-retriever") or {}).get("expose") == ["8100"]
            and "./backend/data/medcoder:/app/data/medcoder:ro" in _read(compose_path)
            and "MEDCODER_RETRIEVER_TOKEN=${MEDCODER_RETRIEVER_TOKEN:-}"
            in _read(compose_path)
            and "MEDCODER_INDEX_VERSION=${MEDCODER_INDEX_VERSION:-"
            in _read(compose_path)
            and "MEDCODER_WORKER_WARMUP=${MEDCODER_WORKER_WARMUP:-1}"
            in _read(compose_path)
            and "/readyz" in str(
                ((services.get("medcoder-retriever") or {}).get("healthcheck") or {}).get("test")
            )
        ),
        "ml_assets_are_hash_verified_and_version_aligned": (
            ml_worker_env.get("MEDCODER_INDEX_VERSION")
            == f"${{MEDCODER_INDEX_VERSION:-{EXPECTED_INDEX_VERSION}}}"
            and _asset_manifest_is_valid(backend_medcoder_index_dir)
        ),
        "api_compose_exposes_remote_retriever_contract": all(
            key in backend_env
            for key in (
                "MEDCODER_RETRIEVER_URL",
                "MEDCODER_RETRIEVER_TOKEN",
                "MEDCODER_RETRIEVER_ALLOW_HTTP",
            )
        ),
        "medcoder_overlay_wires_backend_to_healthy_worker": (
            overlay_backend_env.get("MEDCODER_RETRIEVER_URL")
            == "http://medcoder-retriever:8100"
            and overlay_backend_env.get("MEDCODER_RETRIEVER_ALLOW_HTTP") == "1"
            and overlay_backend_env.get("ICODER_DISABLE_NATIVE_MEDCODER") == "true"
            and overlay_backend_env.get("MEDCODER_RETRIEVER_TOKEN", "").startswith(
                "${MEDCODER_RETRIEVER_TOKEN:?"
            )
            and overlay_worker_env.get("MEDCODER_RETRIEVER_TOKEN", "").startswith(
                "${MEDCODER_RETRIEVER_TOKEN:?"
            )
            and overlay_worker.get("profiles") == []
            and (
                (overlay_backend.get("depends_on") or {})
                .get("medcoder-retriever", {})
                .get("condition")
                == "service_healthy"
            )
        ),
        "external_registry_gateways_are_governed_and_fail_closed": (
            all(
                key in backend_env
                for key in (
                    "ICODER_DRUGBANK_GATEWAY_URL",
                    "ICODER_CREDENTIAL_DRUGBANK",
                    "ICODER_POSOS_GATEWAY_URL",
                    "ICODER_CREDENTIAL_POSOS",
                    "ICODER_WEB_SEARCH_GATEWAY_URL",
                    "ICODER_CREDENTIAL_WEB_SEARCH",
                    "ICODER_WEB_SEARCH_PROVIDER_OPT_IN",
                    "ICODER_WEB_SEARCH_TENANT_OPT_IN_ORGANIZATIONS",
                )
            )
            and "GATEWAY_REQUEST_CONTRACT" in external_registry
            and "CONNECTOR_REGISTRY_DEIDENTIFICATION_REQUIRED" in external_registry
            and "CONNECTOR_REGISTRY_OPT_IN_REQUIRED" in external_registry
            and "commercial_licence_required" in external_registry
            and "async def post_json" in connector_transport
            and "allow_loopback_http_for_testing" in connector_transport
            and "真实供应商许可" in external_registry_doc
            and "ICODER_WEB_SEARCH_TENANT_OPT_IN_ORGANIZATIONS" in env_template
        ),
        "semantic_memory_is_remote_encrypted_and_patient_authority_honest": (
            all(
                key in backend_env
                for key in (
                    "ICODER_MEMORY_SEMANTIC_URL",
                    "ICODER_CREDENTIAL_MEMORY_SEMANTIC",
                    "ICODER_MEMORY_SEMANTIC_REQUIRED",
                )
            )
            and "MEMORY_EMBEDDING_REQUEST_CONTRACT" in memory_semantic
            and "deidentified_text_only" in memory_semantic
            and '"native_ml_in_api_process": False' in memory_semantic
            and "encrypted_vectors_at_rest" in memory_store
            and '"patient_phi_storage_allowed": False' in memory_store
            and '"patient_authority_verified": False' in memory_store
            and "ICODER_MEMORY_SEMANTIC_REQUIRED=true is required in cloud mode"
            in backend_config
            and "ICODER_MEMORY_SEMANTIC_URL" in env_template
            and "ICODER_CREDENTIAL_MEMORY_SEMANTIC" in env_template
            and "ICODER_MEMORY_SEMANTIC_REQUIRED=true" in env_template
            and "患者权威授权" in memory_semantic_doc
            and "test_memory_semantic_remote_http_e2e.py" in release_workflow
        ),
        "frontend_image_has_healthcheck": "HEALTHCHECK" in frontend_df,
        "embedded_assistant_release_bundle_is_present": (
            embedded_bundle.is_file()
            and embedded_bundle.stat().st_size > 1024
            and "customElements.define" in _read(embedded_bundle)
        ),
        "docker_context_excludes_env_files": all(
            ".env.*" in _read(path) and "node_modules/" in _read(path)
            if path == frontend_ignore
            else ".env.*" in _read(path)
            for path in (backend_ignore, frontend_ignore)
        ),
        "frontend_tls_and_security_headers_declared": all(
            token in nginx
            for token in (
                "ssl_protocols TLSv1.2 TLSv1.3",
                "Strict-Transport-Security",
                "Content-Security-Policy",
                "X-Content-Type-Options",
                "Referrer-Policy",
            )
        ),
        "local_frontend_http_is_explicit_and_isolated": (
            "listen 80" in local_nginx
            and "listen 443" not in local_nginx
            and "./frontend/nginx.local.conf:/etc/nginx/conf.d/default.conf:ro"
            in _read(compose_path)
            and "443:443" not in _read(compose_path)
        ),
        "nginx_sse_proxy_is_streaming_and_bounded": all(
            all(
                token in config
                for token in (
                    "api/v1/runs/[^/]+/events",
                    "api/icoder/agents/[^/]+/v1/message:stream",
                    "proxy_http_version 1.1",
                    'proxy_set_header Connection ""',
                    "proxy_buffering off",
                    "proxy_request_buffering off",
                    "proxy_cache off",
                    "gzip off",
                    "proxy_read_timeout 75s",
                    'add_header X-Accel-Buffering "no" always',
                )
            )
            for config in (nginx, local_nginx)
        ),
        "ci_e2e_is_fail_closed_and_uses_vault_credential": (
            "ICODER_CREDENTIAL_LLM:" in e2e_workflow
            and "LLM_API_KEY:" not in e2e_workflow
            and "curl -sf http://localhost:8000/api/health > /dev/null" in e2e_workflow
            and "curl -sf http://localhost/ > /dev/null" in e2e_workflow
            and "ICODER_CREDENTIAL_LLM:" in integration_workflow
            and "continue-on-error: true" not in integration_workflow
            and "run_agent_hub_stability_benchmark.py" in integration_workflow
            and "--repetitions 2" in integration_workflow
            and "--happy-seed-dir" in integration_workflow
            and "--adversarial-seed-dir" in integration_workflow
            and "build_agent_hub_semantic_evidence_bundle.py" in integration_workflow
            and "run_agent_hub_reference_quality_replay.py" in integration_workflow
            and "--semantic-evidence" in integration_workflow
            and "secrets.token_urlsafe(64)" in integration_workflow
            and "::add-mask::$attestation_key" in integration_workflow
            and "ICODER_SECRET_KEY=$attestation_key" in integration_workflow
        ),
        "dotnet_sdk_ci_tests_packs_and_compiles_all_supported_frameworks": (
            dotnet_versions == {"8.0.x", "10.0.x"}
            and "netstandard2.0;net8.0;net10.0" in dotnet_sdk_project
            and "System.Net.Http.Json" in dotnet_sdk_project
            and "System.Text.Json" in dotnet_sdk_project
            and "#if NETSTANDARD2_0" in dotnet_compatibility
            and "CancellationToken" in dotnet_compatibility
            and "<TargetFramework>netstandard2.0</TargetFramework>"
            in dotnet_netstandard_consumer
            and "<TargetFramework>net462</TargetFramework>" in dotnet_net462_consumer
            and "Microsoft.NETFramework.ReferenceAssemblies.net462"
            in dotnet_net462_consumer
            and any(
                "dotnet test tests/Icoder.Sdk.Tests/Icoder.Sdk.Tests.csproj -c Release"
                in command
                and "TargetFrameworks" not in command
                for command in dotnet_runs
            )
            and any(
                "dotnet pack src/Icoder.Sdk/Icoder.Sdk.csproj -c Release" in command
                and "TargetFrameworks" not in command
                for command in dotnet_runs
            )
            and any(
                "lib/netstandard2.0/Icoder.Sdk.dll" in command
                and "lib/net8.0/Icoder.Sdk.dll" in command
                and "lib/net10.0/Icoder.Sdk.dll" in command
                for command in dotnet_runs
            )
            and any(
                "Icoder.Sdk.NetStandard20Consumer" in command
                and "Icoder.Sdk.Net462Consumer" in command
                for command in dotnet_runs
            )
            and all(
                token in release_workflow
                for token in (
                    "Icoder.Sdk.NetStandard20Consumer",
                    "Icoder.Sdk.Net462Consumer",
                    "lib/netstandard2.0/Icoder.Sdk.dll",
                    "lib/net8.0/Icoder.Sdk.dll",
                    "lib/net10.0/Icoder.Sdk.dll",
                )
            )
            and any(
                step.get("uses") == "actions/upload-artifact@v4"
                and (step.get("with") or {}).get("if-no-files-found") == "error"
                for step in dotnet_steps
            )
        ),
        "region_catalog_covers_eu_us_cn": {item.get("code") for item in environments} == {"eu", "us", "cn"},
        "cross_environment_replication_forbidden": all(
            item.get("cross_environment_replication") == "forbidden" for item in environments
        ),
        "all_regions_honestly_unprovisioned": bool(all_regions) and all(
            region.get("enabled") is False for region in all_regions
        ),
        "china_region_and_compliance_declared": (
            {region.get("code") for region in cn.get("regions") or []}
            == {"cn-hangzhou", "cn-beijing"}
            and {"数据安全法", "个人信息保护法"}.issubset(set(cn.get("compliance") or []))
        ),
        "cloud_template_has_no_live_secret": not any(
            re.match(
                r"^(ICODER_SECRET_KEY|ICODER_PHI_ENCRYPTION_KEY|"
                r"ICODER_CREDENTIAL_LLM|MEDCODER_RETRIEVER_TOKEN|"
                r"ICODER_CREDENTIAL_MEMORY_SEMANTIC|"
                r"ICODER_METRICS_BEARER_TOKEN|ICODER_INVITE_WEBHOOK_BEARER_TOKEN)=.+",
                line,
            )
            for line in env_template.splitlines()
        ),
        "cloud_template_defaults_to_local": "ICODER_DEPLOYMENT_MODE=local" in env_template,
        "cloud_template_disables_protocol_fixtures": (
            re.search(r"(?m)^APP_ENV=cloud$", env_template) is not None
            and re.search(
                r"(?m)^ICODER_ENABLE_PROTOCOL_FIXTURES=0$", env_template
            )
            is not None
        ),
        "stt_protocol_fixtures_are_pytest_only_and_cloud_disabled": (
            'and "pytest" in sys.modules' in stt_api
            and "ICODER_ENABLE_PROTOCOL_FIXTURES" in stt_api
            and "app_env in" in stt_api
            and "test_protocol_fixtures_cannot_be_enabled_outside_pytest"
            in stt_lifecycle_test
            and 'sys.modules.pop("pytest", None)' in stt_lifecycle_test
            and re.search(r"(?m)^APP_ENV=cloud$", env_template) is not None
            and re.search(
                r"(?m)^ICODER_ENABLE_PROTOCOL_FIXTURES=0$", env_template
            )
            is not None
        ),
        "realtime_stt_is_tenant_scoped_bounded_local_only_and_phi_safe": (
            'token_payload.get("type") not in' in stt_websocket
            and '{"streams", "transcribe"}.intersection(granted)' in stt_websocket
            and "_MAX_STT_WEBSOCKET_BYTES" in stt_websocket
            and '"code": "transcription_failed"' in stt_websocket
            and '"code": "internal_error"' in stt_websocket
            and "type(diar_error).__name__" in stt_websocket
            and "recognize_google" not in stt_websocket
            and "speech_recognition" not in stt_websocket
            and "ICODER_ENABLE_LOCAL_STT: bool = False" in backend_config
            and stt_websocket.count("if not settings.ICODER_ENABLE_LOCAL_STT") >= 2
            and stt_service.count("if not settings.ICODER_ENABLE_LOCAL_STT") >= 3
            and "Preview:" not in stt_service
            and 'return "", str(' not in stt_service
            and '"The STT background job failed."' in stt_jobs
            and "str(exc)" not in stt_jobs
            and "Diarization failed type=%s" in speaker_diarizer
            and "test_stt_websocket_discards_transcriber_failure_detail"
            in stt_websocket_security_test
            and "test_stt_websocket_discards_unhandled_exception_detail"
            in stt_websocket_security_test
            and "test_stt_websocket_removes_diarization_audio_after_native_failure"
            in stt_websocket_security_test
            and "test_realtime_stt_has_no_implicit_public_provider_fallback"
            in stt_websocket_security_test
            and "test_disabled_local_stt_returns_before_audio_tempfile_or_native_load"
            in stt_websocket_security_test
        ),
        "transcripts_dictation_is_explicit_localized_durable_and_cross_sdk": (
            "def apply_dictation_punctuation(" in stt_service
            and 'primary_language=request_data["primaryLanguage"]' in stt_api
            and "apply_dictation_punctuation(" in stt_jobs
            and "test_dictation_punctuation_is_explicit_and_chinese_localized"
            in stt_lifecycle_test
            and "test_dictation_punctuation_is_not_applied_without_opt_in"
            in stt_lifecycle_test
            and "test_current_punctuation_fields_override_legacy_is_dictation"
            in stt_lifecycle_test
            and "test_spoken_punctuation_overrides_disabled_automatic_punctuation"
            in stt_lifecycle_test
            and '"isDictation": True' in stt_jobs_test
            and "isDictation?: boolean" in javascript_stt_resource
            and "transcriptRequest.isDictation" in javascript_stt_test
            and "is_dictation: bool = False" in python_stt_resource
            and "automatic_punctuation: Optional[bool] = None" in python_stt_resource
            and 'transcript_request["isDictation"]' in python_stt_test
            and '[JsonPropertyName("isDictation")]' in dotnet_stt_models
            and 'GetProperty("isDictation")' in dotnet_contract_test
            and 'APP_ENV=local' in transcripts_dictation_e2e_app
            and "ICODER_E2E_ALLOW_SYNTHETIC_STT" in transcripts_dictation_e2e_app
            and '"synchronous_spoken_punctuation": True'
            in transcripts_dictation_e2e_client
            and '"asynchronous_legacy_is_dictation": True'
            in transcripts_dictation_e2e_client
            and '"real_stt_used": False' in transcripts_dictation_e2e_client
            and "scripts.transcripts_dictation_e2e_app:app"
            in transcripts_dictation_e2e_runner
        ),
        "transcripts_keyterms_are_bounded_encrypted_forwarded_and_cross_sdk": (
            "class TranscriptsCreateKeyterm" in stt_schema
            and "max_length=50" in stt_schema
            and '"keyterms": [item.term for item in body.keyterms.terms]'
            in stt_api
            and 'keyterms=tuple(request_data["keyterms"])' in stt_api
            and 'request_data.get("keyterms", [])' in stt_jobs
            and "keyterms=keyterms" in stt_jobs
            and "encrypt_phi(json.dumps(request_data" in stt_artifact_repository
            and "test_prerecorded_keyterms_are_forwarded_ordered_and_case_sensitive"
            in stt_lifecycle_test
            and 'observed["keyterms"] == ("房颤", "Corti Health")'
            in stt_lifecycle_test
            and "test_batch_stt_forwards_ordered_case_sensitive_keyterms_to_funasr"
            in stt_telemetry_test
            and "keyterms?: { terms: Array<{ term: string }> }" in javascript_stt_resource
            and "transcriptRequest.keyterms" in javascript_stt_test
            and "keyterms: Optional[dict[str, list[dict[str, str]]]] = None"
            in python_stt_resource
            and 'transcript_request["keyterms"]' in python_stt_test
            and '[JsonPropertyName("keyterms")]' in dotnet_stt_models
            and "Each keyterm must contain 1 to 50 characters." in dotnet_stt_resource
            and 'GetProperty("keyterms")' in dotnet_contract_test
            and '"prerecorded_keyterms_forwarded_in_order": True'
            in transcripts_dictation_e2e_client
            and "synthetic_e2e_keyterms_mismatch" in transcripts_dictation_e2e_app
        ),
        "transcripts_stereo_pcm_is_split_encrypted_attributed_and_cross_sdk": (
            "def inspect_multichannel_pcm_wav(" in stt_service
            and "def _split_multichannel_wav_to_temporary_mono_files(" in stt_service
            and "async def transcribe_multichannel_bytes_with_telemetry(" in stt_service
            and "class STTChannelTranscript" in stt_service
            and '"type": "invalid_multichannel_configuration"' in stt_api
            and '"type": "invalid_multichannel_audio"' in stt_api
            and "transcribe_multichannel_bytes_with_telemetry(" in stt_api
            and '"isMultichannel": body.isMultichannel is True' in stt_api
            and "set_transcript_completed_segments" in stt_jobs
            and "transcribe_multichannel_bytes_with_telemetry(" in stt_jobs
            and "_TRANSCRIPT_PAYLOAD_PREFIX" in stt_artifact_repository
            and "encrypt_phi(_encode_transcript_segments(segments))"
            in stt_artifact_repository
            and "test_structured_multichannel_transcript_is_encrypted_and_round_trips"
            in stt_artifact_repository_test
            and "test_multichannel_pcm_wav_is_split_and_transcribed_with_bounded_telemetry"
            in stt_telemetry_test
            and "test_prerecorded_stereo_channels_are_persisted_and_returned_with_roles"
            in stt_lifecycle_test
            and "test_async_multichannel_transcription_preserves_channel_attribution"
            in stt_lifecycle_test
            and "test_recover_pending_multichannel_job_preserves_structured_rows"
            in stt_jobs_test
            and "multichannel transcription requires participants for channels 0 and 1"
            in javascript_stt_resource
            and "is_multichannel: bool = False" in python_stt_resource
            and "multichannel transcription requires participants for channels 0 and 1"
            in python_stt_resource
            and "Multichannel transcription requires participants for channels 0 and 1."
            in dotnet_stt_resource
            and '"prerecorded_stereo_pcm_split_without_crosstalk": True'
            in transcripts_dictation_e2e_client
            and '"prerecorded_multichannel_attribution_sync_async": True'
            in transcripts_dictation_e2e_client
            and "_synthetic_transcribe_audio" in transcripts_dictation_e2e_app
        ),
        "transcripts_encoded_multichannel_is_isolated_bounded_timestamped_and_cross_sdk": (
            "asyncio.create_subprocess_exec" in prerecorded_media_decoder
            and '"-protocol_whitelist"' in prerecorded_media_decoder
            and '"pipe"' in prerecorded_media_decoder
            and "_minimal_environment" in prerecorded_media_decoder
            and "_MAX_INPUT_BYTES" in prerecorded_media_decoder
            and "_max_duration_seconds" in prerecorded_media_decoder
            and "channels != _EXPECTED_CHANNELS" in prerecorded_media_decoder
            and "test_decode_writes_bounded_channels_and_context_cleans_paths"
            in prerecorded_media_decoder_test
            and "test_probe_rejects_channel_duration_and_declared_type_mismatch"
            in prerecorded_media_decoder_test
            and "test_encoded_multichannel_is_probed_then_returns_phrase_timestamps"
            in stt_lifecycle_test
            and "test_multichannel_uses_phrase_rows_when_provider_timestamps_are_valid"
            in stt_telemetry_test
            and "audio/flac" in javascript_stt_resource
            and "audio/flac" in python_stt_resource
            and "audio/flac" in dotnet_stt_resource
            and '"prerecorded_encoded_stereo_decoded_without_crosstalk": True'
            in transcripts_dictation_e2e_client
            and '"prerecorded_phrase_timestamps_are_milliseconds": True'
            in transcripts_dictation_e2e_client
            and "ICODER_TRANSCRIPTS_MEDIA_DECODER_PATH" in transcripts_dictation_e2e_runner
            and "ICODER_TRANSCRIPTS_MEDIA_PROBE_PATH" in transcripts_dictation_e2e_runner
        ),
        "streams_test_client_and_reader_threads_are_explicitly_closed": (
            "client = TestClient(app)" in streams_test
            and "yield client" in streams_test
            and "client.close()" in streams_test
            and "thread.join(timeout=2.0)" in streams_test
            and 'raise AssertionError("stream response reader did not terminate")'
            in streams_test
        ),
        "login_rate_limit_is_isolated_from_general_api_traffic": (
            'bucket = "login" if request.url.path == "/api/auth/login" else "general"'
            in rate_limit_middleware
            and 'key = f"ratelimit:{bucket}:{client_ip}"' in rate_limit_middleware
            and 'counter_key = f"{bucket}:{client_ip}"' in rate_limit_middleware
            and "test_general_requests_do_not_consume_login_window"
            in rate_limit_middleware_test
        ),
        "realtime_stt_resume_is_sequenced_bounded_cross_sdk_and_fault_tested": (
            '_STT_RESUME_PROTOCOL = "icoder.stt-resume.v1"' in stt_websocket
            and '_STT_AUDIO_FRAME_MAGIC = b"ICR1"' in stt_websocket
            and '"code": "audio_sequence_gap"' in stt_websocket
            and '"code": "audio_sequence_incomplete"' in stt_websocket
            and '"type": "audio_ack"' in stt_websocket
            and "test_stt_websocket_resume_protocol_acknowledges_and_deduplicates_audio"
            in stt_websocket_security_test
            and "test_stt_websocket_resume_protocol_rejects_sequence_gap"
            in stt_websocket_security_test
            and "const RESUME_PROTOCOL = 'icoder.stt-resume.v1'"
            in javascript_managed_stt
            and "invalid_resume_cursor" in javascript_managed_stt
            and "managed STT replays bounded audio after disconnect"
            in javascript_managed_stt_test
            and '_RESUME_PROTOCOL = "icoder.stt-resume.v1"' in python_managed_stt
            and "invalid_resume_cursor" in python_managed_stt
            and "test_managed_stt_replays_audio_after_disconnect"
            in python_managed_stt_test
            and 'ResumeProtocol = "icoder.stt-resume.v1"' in dotnet_realtime_stt
            and "Compatibility.ZeroMemory" in dotnet_realtime_stt
            and "RealtimeSttReplaysAudioAndEndAfterDisconnect" in dotnet_contract_test
            and "close_after_sequence_1_ack" in stt_recovery_e2e
            and 'proxy=None' in stt_fault_proxy
            and 'action="append"' in stt_fault_proxy
        ),
        "streams_is_current_tenant_safe_truthful_cross_sdk_and_e2e_tested": (
            "async def _authenticate_stream" in streams_api
            and "_MAX_AUDIO_CHUNK_BYTES = 64_000" in streams_api
            and "_MAX_STREAM_AUDIO_BYTES = 32 * 1024 * 1024" in streams_api
            and "CONFIG_ALREADY_RECEIVED" in streams_api
            and "test-fake-token" not in streams_api
            and "extract_stream_facts_with_usage" in streams_api
            and "StreamFlushedMessage(type=\"flushed\")" in streams_api
            and "StreamDeltaUsageMessage(type=\"delta_usage\", credits=0.0)" in streams_api
            and "ConfigDict(extra=\"forbid\"" in streams_schema
            and "sessionId" in streams_schema
            and "class StreamFlushedMessage" in streams_schema
            and "type: Literal[\"delta_usage\"]" in streams_schema
            and 'getattr(application.state, "platform_gateway", None)' in streams_ambient
            and "result = await gateway.generate" in streams_ambient
            and 'result.get("degraded") is True or result.get("is_mock") is True'
            in streams_ambient
            and "test_invalid_token_is_rejected_before_websocket_acceptance" in streams_test
            and "test_audio_chunk_and_total_buffer_are_bounded" in streams_test
            and "audio_resume_unsupported" in javascript_streams
            and "Streams rejects malformed CONFIG_ACCEPTED" in javascript_streams_test
            and "audio_resume_unsupported" in python_streams
            and "test_streams_fails_closed_after_audio_disconnect" in python_streams_test
            and "audio_resume_unsupported" in dotnet_streams
            and "StreamsFailsClosedWhenConnectionDropsAfterAudio" in dotnet_contract_test
            and "Remove-Item Env:ICODER_CREDENTIAL_LLM" in streams_e2e
            and "ICODER_ENABLE_LOCAL_STT = \"false\"" in streams_e2e
            and "retained_recording_retrieved" in streams_e2e
        ),
        "streams_audio_containers_are_declared_detected_and_cross_sdk_validated": (
            '\"audio/pcm\": \"pcm\"' in streams_audio_format
            and '\"audio/ogg\": \"ogg\"' in streams_audio_format
            and '\"audio/webm\": \"webm\"' in streams_audio_format
            and '\"audio/flac\": \"flac\"' in streams_audio_format
            and "data.startswith(b\"OggS\")" in streams_audio_format
            and "StreamAudioProbeStatus.MISMATCH" in streams_audio_format
            and "stream_audio_pcm_parameter_required" in streams_audio_format
            and "AUDIO_FORMAT_MISMATCH" in streams_api
            and "AUDIO_FORMAT_INVALID" in streams_api
            and "test_raw_wav_unknown_parameters_and_mismatched_codecs_are_rejected"
            in streams_audio_format_test
            and "test_probe_accepts_declared_pcm_and_requires_complete_frames"
            in streams_audio_format_test
            and "STREAM_AUDIO_FORMATS" in javascript_streams
            and "accepts recommended PCM audio health and validates typed events"
            in javascript_streams_test
            and "_STREAM_AUDIO_FORMATS" in python_streams
            and "test_streams_accepts_recommended_pcm_and_validates_audio_events"
            in python_streams_test
            and "ValidateAudioFormat" in dotnet_streams_resource
            and "StreamsAcceptsRecommendedPcmAndValidatesTypedAudioEvents"
            in dotnet_contract_test
            and "imageio_ffmpeg.get_ffmpeg_exe" in streams_e2e
            and "synthetic_generated_silence_ogg_opus = $true" in streams_e2e
            and "audio_container_validated = $true" in streams_e2e
            and "synthetic_non_audio_bytes_only" not in streams_e2e
        ),
        "streams_recommended_pcm_and_audio_events_are_typed_bounded_and_e2e_tested": (
            "PcmS16leMonoHealthMonitor" in streams_audio_health
            and all(
                event_name in streams_audio_health
                for event_name in (
                    "speechQualityIssueDetected",
                    "speechQualityIssueRecovered",
                    "longSilenceDetected",
                    "longSilenceRecovered",
                )
            )
            and "test_high_zero_crossing_noise_detects_quality_issue"
            in streams_audio_health_test
            and "test_chunk_boundaries_do_not_change_window_results"
            in streams_audio_health_test
            and "raw_pcm_profile_not_available" in streams_api
            and "audio_events_require_pcm" in streams_api
            and '\"stt.stream.audio_event\"' in streams_api
            and "test_pcm_audio_events_are_typed_deterministic_and_content_free"
            in streams_test
            and "test_pcm_final_frame_alignment_fails_before_decoder_or_asr"
            in streams_test
            and "test_recommended_pcm_is_wrapped_as_wave_before_local_asr"
            in streams_ambient_test
            and 'normalized == "audio/pcm"' in stt_service
            and "writer.setnchannels(1)" in stt_service
            and "writer.setframerate(16000)" in stt_service
            and "STREAM_AUDIO_EVENTS" in javascript_streams
            and "_STREAM_AUDIO_EVENTS" in python_streams
            and "IsAudioEventName" in dotnet_streams
            and "decoder_reached" in streams_pcm_events_e2e_client
            and "asr_adapter_reached" in streams_pcm_events_e2e_client
            and '\"expected_error_code\": \"STT_UNAVAILABLE\"'
            in streams_pcm_events_e2e_client
            and "pcm_audio_events_execution = $audioEventsResult" in streams_e2e
            and "audio_event_audits_content_free" in streams_e2e
            and "$decoderHealth.attempts -ne 6" in streams_e2e
        ),
        "streams_multichannel_pcm_and_fast_init_are_attributed_and_e2e_tested": (
            "PcmS16leMultichannelHealthMonitor" in streams_audio_health
            and "deinterleave_pcm_s16le" in streams_ambient
            and "multichannel_pcm_format_required" in streams_api
            and "multichannel_participants_must_match_channels" in streams_api
            and "_fact_generation_interval_seconds" in streams_api
            and "test_declared_pcm_multichannel_is_deinterleaved_and_attributed"
            in streams_test
            and "test_multichannel_checkpoint_roundtrip_preserves_channel_state"
            in streams_test
            and "test_multichannel_monitor_preserves_channel_identity_across_partial_frames"
            in streams_audio_health_test
            and "accepts governed PCM multichannel and fast-init" in javascript_streams_test
            and "test_streams_accepts_governed_multichannel_and_fast_init"
            in python_streams_test
            and "StreamsAcceptsGovernedMultichannelAndFastInit" in dotnet_contract_test
            and "participant_mapping_verified" in streams_multichannel_e2e_client
            and "channel_audio_event_verified" in streams_multichannel_e2e_client
            and "multichannel_execution = $multichannelResult" in streams_e2e
        ),
        "streams_keyterms_are_bounded_forwarded_current_shape_and_e2e_tested": (
            'serialization_alias="diarize"' in streams_schema
            and 'AliasChoices("diarize", "isDiarization")' in streams_schema
            and "keyterm_count" in streams_api
            and "keyterms=keyterms" in streams_ambient
            and 'generate_options["hotword"] = list(keyterms)' in stt_service
            and "test_keyterms_are_accepted_and_forwarded_to_each_channel"
            in streams_test
            and "test_stream_keyterms_are_forwarded_without_logging_or_rewriting"
            in streams_ambient_test
            and "test_batch_stt_forwards_ordered_case_sensitive_keyterms_to_funasr"
            in stt_telemetry_test
            and "accepts ordered case-sensitive keyterms before transport"
            in javascript_streams_test
            and "test_streams_accepts_ordered_case_sensitive_keyterms"
            in python_streams_test
            and "StreamsAcceptsOrderedCaseSensitiveKeytermsAndUsesCurrentDiarizeField"
            in dotnet_contract_test
            and "keyterms_accepted" in streams_multichannel_e2e_client
        ),
        "streams_media_decode_is_isolated_bounded_fail_closed_and_e2e_tested": (
            "asyncio.create_subprocess_exec" in streams_media_decoder
            and "stdin=asyncio.subprocess.PIPE" in streams_media_decoder
            and "stdout=asyncio.subprocess.DEVNULL" in streams_media_decoder
            and "stderr=asyncio.subprocess.DEVNULL" in streams_media_decoder
            and "env=_decoder_environment(decoder)" in streams_media_decoder
            and '"-protocol_whitelist",' in streams_media_decoder
            and "close_fds=True" in streams_media_decoder
            and '"-frames:a",' in streams_media_decoder
            and '"-max_alloc",' in streams_media_decoder
            and "process.kill()" in streams_media_decoder
            and "StreamMediaDecodeStatus.TIMEOUT" in streams_media_decoder
            and "AUDIO_DECODE_INVALID" in streams_api
            and "AUDIO_VALIDATION_TIMEOUT" in streams_api
            and "AUDIO_VALIDATION_UNAVAILABLE" in streams_api
            and "AUDIO_VALIDATION_BUSY" in streams_api
            and "asyncio.Semaphore" in streams_media_decoder
            and "ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY"
            in streams_media_decoder
            and "ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS"
            in streams_media_decoder
            and "except asyncio.CancelledError" in streams_media_decoder
            and "stream_media_decoder_snapshot" in app_main
            and "test_decoder_timeout_kills_and_reaps_process"
            in streams_media_decoder_test
            and "test_decoder_concurrency_is_bounded_and_queue_fails_busy"
            in streams_media_decoder_test
            and "test_cancellation_kills_reaps_and_releases_capacity"
            in streams_media_decoder_test
            and "test_decoder_result_is_bounded_and_content_free"
            in streams_media_decoder_test
            and "test_isolated_decoder_failure_never_reaches_asr_or_retention"
            in streams_test
            and 'ICODER_STREAM_MEDIA_VALIDATION_MODE: str = "decoder"'
            in backend_config
            and "ICODER_STREAM_MEDIA_VALIDATION_MODE=decoder is required in cloud mode"
            in backend_config
            and "ffmpeg" in backend_df
            and backend_env.get("ICODER_STREAM_MEDIA_VALIDATION_MODE") == "decoder"
            and backend_env.get("ICODER_STREAM_MEDIA_DECODER_PATH") == "/usr/bin/ffmpeg"
            and backend_env.get("ICODER_STREAM_MEDIA_DECODER_MAX_CONCURRENCY") == "2"
            and backend_env.get("ICODER_STREAM_MEDIA_DECODER_QUEUE_TIMEOUT_SECONDS") == "0.5"
            and re.search(
                r"(?m)^ICODER_STREAM_MEDIA_VALIDATION_MODE=decoder$",
                env_template,
            )
            is not None
            and "plausible_header_rejected_by_decoder" in streams_malformed_e2e_client
            and "isolated_decoder_validation = $true" in streams_e2e
            and "malformed_media_execution = $malformedResult" in streams_e2e
            and '"ogg_opus"' in streams_media_soak
            and '"webm_opus"' in streams_media_soak
            and '"mp3"' in streams_media_soak
            and '"flac"' in streams_media_soak
            and '"mp4_aac"' in streams_media_soak
            and "PLAUSIBLE_INVALID" in streams_media_soak
            and "decoder_processes_remaining" in streams_media_soak
            and "Remove-Item Env:ICODER_CREDENTIAL_LLM" in streams_media_soak_runner
            and "Streams media decoder soak left ffmpeg processes running"
            in streams_media_soak_runner
        ),
        "streams_cross_worker_leases_are_fenced_and_crash_recoverable": (
            "class STTStreamLease" in streams_lease_model
            and 'UniqueConstraint("session_id", name="uq_stt_stream_lease_session")'
            in streams_lease_model
            and "class StreamLeaseScope" in streams_lease_service
            and "STTStreamLease.lease_expires_at <= current" in streams_lease_service
            and "STTStreamLease.session_id == session_id" in streams_lease_service
            and "MINIMUM_LEASE_SECONDS = 6" in streams_lease_service
            and "MAXIMUM_LEASE_SECONDS = 300" in streams_lease_service
            and 'revision = "056"' in streams_lease_migration
            and 'down_revision = "055"' in streams_lease_migration
            and 'op.create_table(\n        "stt_stream_leases"' in streams_lease_migration
            and "test_concurrent_acquire_has_exactly_one_winner" in streams_lease_test
            and "test_expired_lease_is_reclaimed_and_stale_owner_is_fenced"
            in streams_lease_test
            and "_stream_lease_heartbeat" in streams_api
            and "if not await _confirm_stream_lease(state)" in streams_api
            and "await _release_stream_lease(state.lease_scope, state.session_id)"
            in streams_api
            and "ICODER_STREAM_LEASE_SECONDS: int = 30" in backend_config
            and backend_env.get("ICODER_STREAM_LEASE_SECONDS")
            == "${ICODER_STREAM_LEASE_SECONDS:-30}"
            and re.search(
                r"(?m)^ICODER_STREAM_LEASE_SECONDS=30$", env_template
            )
            is not None
            and "api_processes = 2" in streams_multiworker_e2e
            and "duplicate_rejected_across_workers = $true"
            in streams_multiworker_e2e
            and "stale_lease_recovered_by_secondary = $true"
            in streams_multiworker_e2e
            and "Remove-Item Env:ICODER_CREDENTIAL_LLM"
            in streams_multiworker_e2e
            and '"--token"' not in streams_multiworker_e2e
        ),
        "streams_unfinished_interactions_are_encrypted_fenced_and_restart_resumable": (
            "class STTStreamCheckpoint(Base)" in streams_lease_model
            and "class STTStreamCheckpointChunk(Base)" in streams_lease_model
            and 'revision = "057"' in streams_checkpoint_migration
            and 'down_revision = "056"' in streams_checkpoint_migration
            and '"stt_stream_checkpoints"' in streams_checkpoint_migration
            and '"stt_stream_checkpoint_chunks"' in streams_checkpoint_migration
            and "is_encryption_enabled()" in streams_checkpoint_service
            and "StreamCheckpointEncryptionRequired" in streams_checkpoint_service
            and "STTStreamCheckpoint.session_id == session_id"
            in streams_checkpoint_service
            and "stream checkpoint chunk digest mismatch"
            in streams_checkpoint_service
            and "await _resume_or_initialize_checkpoint(state)" in streams_api
            and "await _append_checkpoint_chunk(state, chunk)" in streams_api
            and "await _discard_checkpoint(state)" in streams_api
            and "test_checkpoint_restores_exact_encrypted_audio_and_state"
            in streams_checkpoint_test
            and "test_checkpoint_fences_stale_writer_after_resume"
            in streams_checkpoint_test
            and "test_checkpoint_detects_tampered_audio_chunk"
            in streams_checkpoint_test
            and "retained_audio_checkpoint_recovered = $true"
            in streams_multiworker_e2e
            and "checkpoint_encryption_required = $true"
            in streams_multiworker_e2e
            and "remaining_checkpoint_chunks" in streams_multiworker_e2e
            and "recording_bytes -ne 640" in streams_multiworker_e2e
            and "requireCheckpointResume" in javascript_streams
            and "stream_resume_required" in javascript_streams
            and "async resume(" in javascript_streams_resource
            and "stream_checkpoint_not_found" in javascript_streams_test
            and "_require_checkpoint_resume" in python_streams
            and '"stream_resume_required"' in python_streams
            and "resume_async(" in python_streams_resource
            and "stream_checkpoint_not_found" in python_streams_test
            and "RequireCheckpointResume" in dotnet_streams
            and '"stream_resume_required"' in dotnet_streams
            and "ResumeSessionAsync(" in dotnet_streams_resource
            and "StreamsResumeRequiresServerAckAndExposesRecoveryCounts"
            in dotnet_contract_test
        ),
        "cloud_template_uses_persistent_trace_store": all(
            re.search(pattern, env_template) is not None
            for pattern in (
                r"(?m)^RUNTRACE_STORE=db$",
                r"(?m)^RUNTRACE_FAIL_CLOSED=0$",
                r"(?m)^RUNTRACE_DEPLOYMENT_PROFILE=BEST_EFFORT_DB$",
                r"(?m)^ICODER_RUN_TRACE_EVENTS_TTL_DAYS=90$",
                r"(?m)^ICODER_RUN_HISTORY_TTL_DAYS=90$",
            )
        ),
        "cloud_template_requires_webhook_invite_delivery": all(
            re.search(pattern, env_template) is not None
            for pattern in (
                r"(?m)^ICODER_INVITE_DELIVERY_MODE=webhook$",
                r"(?m)^ICODER_INVITE_ALLOWED_EMAIL_DOMAINS=\[.+\]$",
                r"(?m)^ICODER_INVITE_MAX_ATTEMPTS=5$",
                r"(?m)^ICODER_INVITE_RETRY_BASE_SECONDS=30$",
                r"(?m)^ICODER_INVITE_CLAIM_TIMEOUT_SECONDS=120$",
                r"(?m)^ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS=10$",
            )
        ),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "schema_version": "icoder.deployment-candidate-preflight/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "static_without_docker_cli",
        "checks": checks,
        "passed": not failed,
        "failed_checks": failed,
        "limitations": [
            "No image was built or started because Docker CLI is unavailable.",
            "No image vulnerability/SBOM/registry-signature scan was performed.",
            "No cloud region was provisioned; regions.yaml declares every region enabled=false.",
            "No disaster recovery, capacity, latency, or availability SLA was exercised.",
            "The PostgreSQL cross-process contract is conditional on the Linux CI service and was not exercised by this static preflight.",
            "No production retention scheduler or CronJob was installed or executed; the verified purge CLI must be scheduled by the target platform.",
            "No production metrics collector, cross-process aggregation, alert delivery route, or operational SLA was installed or exercised.",
            "The CCL supervised result is deterministic five-fold development OOF on one governed training workbook, not an untouched external cohort, independent clinical gold, Corti head-to-head, or production-quality proof.",
            "Clinical model package activation is currently a metadata-only governance selection: it does not load or execute a model. Real package binaries, independent clinical validation, licence/redistribution authority, hospital approval, runtime integration and production rollback drills remain external or later gates.",
            "Clinical shadow evaluation jobs were exercised only against repository synthetic fixtures and a temporary test database. A durable production queue, real shadow traffic, multi-host load/chaos testing, regional metrics export/alert delivery and hospital rollback drills remain external or later gates.",
            "Streams transport/authentication/retention, cross-worker lease recovery, governed 16 kHz signed little-endian PCM up to eight declared channels, deterministic per-channel audio-health events, participant attribution, fast-init scheduling, bounded ordered keyterm forwarding, plus prerecorded opt-in Chinese dictation punctuation, encrypted ordered keyterm forwarding, stereo 16 kHz/16-bit PCM WAV channel attribution, isolated encoded two-channel decoding, and provider-grounded millisecond phrase timestamps were exercised locally; real ASR/fact quality, provider billing, diarization, keyterm accuracy, multichannel clinical quality, compressed-format audio events, other PCM profiles, and same-audio Corti comparison remain external gates.",
            "Local development defaults to manual invitation credentials; cloud mode fails closed unless the encrypted signed webhook outbox is configured.",
            "The webhook transport was exercised only against a local test receiver; a real regional email provider, production scheduler, bounce handling, template approval, and delivery SLA remain external integration gates.",
            "Platform access changes are single-admin operations in development; production MFA, dual approval, SSO/SCIM, and independent access review remain external gates.",
        ],
    }


def _write_report(report: dict[str, Any], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "deployment_preflight.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Deployment candidate preflight",
        "",
        f"Generated: `{report['generated_at']}`",
        "",
        f"Result: **{'PASS' if report['passed'] else 'FAIL'}**",
        "",
        "| Check | Result |",
        "|---|---:|",
    ]
    lines.extend(
        f"| {name} | {'pass' if passed else 'fail'} |"
        for name, passed in report["checks"].items()
    )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    (output_dir / "deployment_preflight.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "reports" / "deployment" / "development_preflight_20260813",
    )
    args = parser.parse_args()
    report = validate(args.root.resolve())
    _write_report(report, args.output_dir.resolve())
    print(json.dumps({"passed": report["passed"], "failed_checks": report["failed_checks"]}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
