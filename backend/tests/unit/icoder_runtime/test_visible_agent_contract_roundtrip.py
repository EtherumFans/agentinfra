"""Every Hub-visible Pack contract must survive the public API projection.

This is a framework gate, not a clinical-quality claim. It proves that a
provider which emits all Pack-declared fields will not lose them in the
markdown projector or be rejected by the unified Agent Run envelope.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest

from app.api.agent_run import _map_backend_response
from app.icoder.agent_runtime.orchestrator.inbound_handler import (
    InboundMessage,
    InboundRequest,
)
from app.icoder.agent_runtime.provider_a2a_handler import ProviderA2AHandler
from icoder_runtime.core.agent_execution_paths import (
    DEDICATED_AGENT_EXECUTION_PATHS,
)
from icoder_runtime.backends.contracts import BackendResponse
from icoder_runtime.backends.output_contract_validation import (
    declared_optional_fields,
)
from icoder_runtime.backends.structured_output_projector import project


OFFICIAL_AGENTS = Path(__file__).resolve().parents[3] / "official_agents"


def _visible_packs() -> list[dict]:
    packs: list[dict] = []
    for path in sorted(OFFICIAL_AGENTS.glob("*/agent_pack.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        if (pack.get("manifest") or {}).get("hidden_from_hub") is True:
            continue
        packs.append(pack)
    return packs


def _sentinel(field: str, expected: str):
    if expected == "boolean":
        return True
    if expected == "integer":
        return 2
    if expected == "number":
        return 0.5
    if expected == "object":
        return {}
    if expected == "array":
        return []
    if expected == "string":
        return f"sentinel:{field}"
    raise AssertionError(f"unsupported declared type {expected!r} for {field}")


def test_all_26_visible_pack_contracts_round_trip_without_field_loss() -> None:
    packs = _visible_packs()
    assert len(packs) == 26

    for pack in packs:
        agent_id = pack["agent_ref"].rsplit("/", 1)[-1].split("@", 1)[0]
        contract = pack["output_contract"]["schema_ref"]
        required = list(pack["output_contract"]["required_fields"])
        example = pack["example_outputs"][0]
        payload = {field: example[field] for field in required}
        markdown = "```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"

        projection = project(markdown, contract, agent_id)
        assert set(required).issubset(projection.result), (
            f"{agent_id}: projector lost Pack fields "
            f"{sorted(set(required) - set(projection.result))}"
        )

        public = _map_backend_response(
            agent_id=agent_id,
            run_id=f"run-{agent_id}",
            trace_id=f"trace-{agent_id}",
            runtime_mode=pack.get("default_runtime_mode") or "test",
            resp=BackendResponse(
                status="requires_review",
                summary="contract round-trip",
                markdown=markdown,
                backend_provider="test.provider.v1",
                backend_type="contract_test",
                trace_refs=[f"run-{agent_id}:contract-test"],
            ),
            include_trace=False,
            include_evidence=False,
            agent_pack=pack,
            t0=time.perf_counter(),
        )
        extraction = public.result["structured_extraction"]
        assert extraction["contract"] == contract
        assert extraction["missing_required_fields"] == [], (
            f"{agent_id}: {extraction['missing_required_fields']}"
        )
        assert extraction["invalid_field_types"] == []
        assert extraction["invalid_field_schemas"] == []
        assert extraction["undeclared_output_fields"] == []
        assert extraction["valid"] is True
        assert public.error is False
        if (pack.get("manifest") or {}).get("human_review") == "required":
            assert public.manual_review_required is True, agent_id
            assert public.result["manual_review_required"] is True, agent_id


@pytest.mark.asyncio
async def test_all_provider_backed_a2a_agents_return_their_declared_contract(
    monkeypatch,
) -> None:
    """Every generic Provider A2A route returns domain fields, not a shell."""
    import app.icoder.agent_runtime.provider_a2a_handler as handler_module

    class _ContractProvider:
        supports_streaming = False

        def __init__(self, pack: dict) -> None:
            self._pack = pack

        async def invoke(self, req, ctx, *, request=None):
            required = self._pack["output_contract"]["required_fields"]
            example = self._pack["example_outputs"][0]
            payload = {
                field: copy.deepcopy(example[field]) for field in required
            }
            # Evidence-bearing examples were authored against their own
            # source notes. Rebind them to this test request so the A2A
            # round-trip proves the runtime quote/span gate, not stale fixture
            # coordinates.
            for binding_index, binding in enumerate(
                self._pack["output_contract"].get("evidence_bindings", [])
            ):
                evidence_text = f"binding{binding_index}"
                start = req.user_input.index(evidence_text)
                for item in payload.get(binding["for_each"], []):
                    item[binding["text_path"]] = evidence_text
                    item[binding["span_path"]] = [start, start + len(evidence_text)]
            return BackendResponse(
                status="requires_review",
                summary="contract round-trip",
                markdown=json.dumps(payload, ensure_ascii=False),
                backend_provider=str(self._pack.get("backend_provider") or ""),
                backend_type="contract_test",
                finish_state="completed",
                trace_refs=[ctx.run_id],
            )

    class _Registry:
        def resolve_from_agent_pack(self, pack):
            return _ContractProvider(pack)

        def get_backend_config(self, pack):
            return pack.get("backend_config") or {}

    monkeypatch.setattr(
        handler_module, "get_default_registry", lambda: _Registry(),
    )
    handler = ProviderA2AHandler(OFFICIAL_AGENTS)
    # 26 visible minus CDI, Medical Coding and the three dedicated simple
    # handlers. These 21 Packs use ProviderA2AHandler at runtime.
    assert len(handler.agent_ids) == 21
    assert all(
        not handler.supports(agent_id)
        for agent_id in DEDICATED_AGENT_EXECUTION_PATHS
    )

    for agent_id in handler.agent_ids:
        pack = handler.pack_for(agent_id)
        assert pack is not None
        output_contract = pack["output_contract"]
        required = set(output_contract["required_fields"])
        allowed = required | set(declared_optional_fields(output_contract))
        response = await handler._handle_async(
            agent_id,
            InboundRequest(
                message=InboundMessage(
                    parts=[{
                        "kind": "text",
                        "text": "binding0 binding1 binding2 binding3 binding4",
                    }],
                    context_id=f"context-{agent_id}",
                ),
                metadata={"organization_id": "org-contract-gate"},
            ),
        )

        assert response.kind == "message", (agent_id, response.error)
        data = response.parts[0]["data"]
        assert required.issubset(data), (
            agent_id,
            {"missing": sorted(required - set(data))},
        )
        assert set(data).issubset(allowed), (
            agent_id,
            {"undeclared": sorted(set(data) - allowed)},
        )
        assert response.parts[0]["metadata"]["schema_ref"] == (
            pack["output_contract"]["schema_ref"]
        )
