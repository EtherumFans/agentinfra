"""Phase 2 cycle 21 — v1.2 pack install path regression tests.

Covers the silent-skip bug surfaced when the runtime check
``click_code_highlights_evidence`` failed with 404 on
``medical-coding-agent-1.0.0``. Three fixes landed:

1. ``PlatformRuntime.install_agent`` skips the legacy
   ``AgentPackageV1.from_dict`` validator for v1.2 packs
   (the loader's permissive path is canonical for v1.2).
2. ``RuntimeAgentRegistry.install`` reads v1.2 fields directly
   from the pack dict (no ``AgentPackageV1`` round-trip).
3. ``PlatformRuntime.run_agent`` normalizes v1.2
   ``experts[].expert_id`` → ``id`` and filters to the
   ``ExpertDefinition`` whitelist before construction;
   ``tools[].type`` (mcp/function/builtin/guard) maps to
   ``ToolTier`` (1/1/1/2).

Without these, ``BuiltinAgentPackProvider.register_all`` would
log ``Failed to register pack`` for all 6 v1.2 official packs
and the medical-coding page could not call the agent end-to-end.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from icoder_runtime.agent_pack import import_pack
from icoder_runtime.core.registry import RuntimeAgentRegistry
from icoder_runtime.embedded.platform_runtime import PlatformRuntime
from icoder_runtime.core.llm_gateway import LLMGateway, MockLLMProvider
from icoder_runtime.core.runtime_config import RuntimeConfig


# ── Fixtures ──────────────────────────────────────────────────────


def _minimal_v12_pack() -> dict:
    """A v1.2 pack with v1.2-only fields (expert_id, tool type,
    pipeline/non_goals/output_contract). Mirrors the Phase D shape."""
    return {
        "format_version": "1.2",
        "agent_type": "certified",
        "manifest": {
            "name": "Test Med Agent",
            "version": "1.0.0",
            "description": "Test v1.2 pack for install path",
            "category": "general",
            "icon": "Bot",
        },
        "system_prompt": "You are a test agent.",
        "experts": [
            {
                "expert_id": "coding-expert",
                "name": "Coding Expert",
                "role": "primary",
                "description": "Test expert",
                "system_prompt": "You extract codes.",
                "model": "deepseek-chat",
                "tools": [],
                "non_goals": ["do not invent codes"],
                "output_contract": {
                    "schema": "MedicalCodingOutputSchema",
                    "required": ["primary_diagnosis"],
                },
            }
        ],
        "tools": [
            {"name": "search-icd", "type": "mcp", "description": "Search ICD"},
            {"name": "verify-code", "type": "function", "description": "Verify"},
            {"name": "builtin-tool", "type": "builtin", "description": "Builtin"},
            {"name": "safety-guard", "type": "guard", "description": "Safety check"},
        ],
        "permissions": {},
        "requirements": {"min_runtime_version": "1.0.0"},
    }


@pytest.fixture
def tmp_registry(tmp_path: Path) -> RuntimeAgentRegistry:
    """Fresh registry per test (no cross-test pollution)."""
    return RuntimeAgentRegistry(storage_dir=tmp_path)


@pytest.fixture
def platform_runtime(tmp_path: Path) -> PlatformRuntime:
    """PlatformRuntime with mock LLM + fresh registry."""
    gateway = LLMGateway()
    gateway.register(MockLLMProvider(), default=True)
    cfg = RuntimeConfig(execution_mode="platform_runtime", registry_dir=tmp_path)
    rt = PlatformRuntime(gateway=gateway, config=cfg, storage_dir=tmp_path)
    return rt


# ── Tests ────────────────────────────────────────────────────────


class TestV12RegistryInstall:
    """RuntimeAgentRegistry.install must accept v1.2 packs."""

    def test_v12_pack_installs_without_legacy_validator(self, tmp_registry):
        """v1.2 pack must NOT raise ValidationError from AgentPackageV1."""
        pack = _minimal_v12_pack()
        record = tmp_registry.install(pack, publisher_name="test")
        assert record.agent_id == "test-med-agent-1.0.0"
        assert record.name == "Test Med Agent"
        assert record.version == "1.0.0"
        assert record.agent_type == "certified"

    def test_v12_expert_ids_accept_expert_id_field(self, tmp_registry):
        """expert_ids must be derived from experts[].expert_id (Phase D)."""
        pack = _minimal_v12_pack()
        record = tmp_registry.install(pack)
        assert record.expert_ids == ["coding-expert"]

    def test_v11_pack_still_runs_through_legacy_validator(self, tmp_registry):
        """v1.1 pack path is preserved (no regression)."""
        v11 = {
            "format_version": "1.1",
            "manifest": {"name": "V11 Agent", "version": "1.0.0",
                         "description": "v1.1 test", "category": "general",
                         "icon": "Bot"},
            "system_prompt": "You are v1.1.",
            "experts": [{"id": "exp1", "name": "Expert 1",
                         "description": "desc", "system_prompt": "sp",
                         "capabilities": [], "config": {}}],
            "tools": [{"id": "tool1", "name": "Tool 1",
                       "description": "d", "tier": 1, "category": "general"}],
            "permissions": {},
            "requirements": {"min_runtime_version": "1.0.0"},
        }
        record = tmp_registry.install(v11)
        assert record.agent_id == "v11-agent-1.0.0"
        assert record.expert_ids == ["exp1"]


class TestV12ImportPack:
    """import_pack (agent_pack.py) must accept v1.2 expert_id + tool type."""

    def test_v12_expert_id_maps_to_definition_id(self):
        pack = _minimal_v12_pack()
        agent, experts, tools, _permissions = import_pack(pack)
        assert len(experts) == 1
        assert experts[0].id == "coding-expert"
        assert experts[0].name == "Coding Expert"

    def test_v12_tool_type_maps_to_tier(self):
        pack = _minimal_v12_pack()
        _agent, _experts, tools, _p = import_pack(pack)
        tier_map = {t.name: t.tier.value for t in tools}
        assert tier_map["search-icd"] == 1  # mcp → tier 1
        assert tier_map["verify-code"] == 1  # function → tier 1
        assert tier_map["builtin-tool"] == 1  # builtin → tier 1
        assert tier_map["safety-guard"] == 2  # guard → tier 2


class TestV12PlatformRuntimeInstall:
    """PlatformRuntime.install_agent must accept v1.2 packs end-to-end."""

    def test_install_agent_v12_returns_installed_status(self, platform_runtime):
        pack = _minimal_v12_pack()
        result = platform_runtime.install_agent(pack, publisher_name="test")
        assert result["status"] == "installed"
        assert result["agent_id"] == "test-med-agent-1.0.0"
        assert result["name"] == "Test Med Agent"

    def test_install_agent_v12_registers_in_registry(self, platform_runtime):
        pack = _minimal_v12_pack()
        platform_runtime.install_agent(pack, publisher_name="test")
        agents = platform_runtime.list_agents()
        assert any(a["id"] == "test-med-agent-1.0.0" for a in agents)


class TestV12BuiltinPackProviderRegisterAll:
    """BuiltinAgentPackProvider.register_all must install all EXECUTABLE
    v1.2 packs without raising — the original cycle 20 bug surfaced
    here as silent skip (logger.warning only)."""

    def test_register_all_installs_v12_executable_packs(self, platform_runtime):
        from icoder_runtime.core.builtin_pack_provider import BuiltinAgentPackProvider
        provider = BuiltinAgentPackProvider(
            agents_dir=Path(__file__).resolve().parents[3] / "official_agents"
        )
        normalized = provider.discover_all()
        executable = [np for np in normalized if np.status.value == "executable"]
        # Sanity: we have multiple v1.2 executable packs (medcoder-coding-review,
        # medical-coding-agent, plus D2 expert stubs). Before the fix, only
        # v1.1 packs were registered (6 v1.2 packs silently dropped).
        v12_executable = [np for np in executable if np.format_version == "1.2"]
        assert len(v12_executable) >= 2, (
            f"Expected at least 2 v1.2 executable packs in official_agents, "
            f"got {len(v12_executable)}"
        )
        count = provider.register_all(platform_runtime)
        # Every v1.2 executable pack must register successfully.
        assert count >= len(v12_executable)