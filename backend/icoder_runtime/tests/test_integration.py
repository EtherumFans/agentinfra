"""Integration tests: closed-loop AgentPackageV1 → publish → install → run → LLMGateway → result.

Covers the 10 acceptance criteria from the refactoring spec.
"""

import asyncio
import json

import pytest

from icoder_runtime.core.errors import (
    LLMProviderNotConfigured,
    ValidationError,
    AgentNotFoundError,
)
from icoder_runtime.core.llm_gateway import (
    LLMGateway,
    MockLLMProvider,
    MedicalCodingLLMProvider,
)
from icoder_runtime.core.agent_pack_v1 import AgentPackageV1
from icoder_runtime.agent_runner import AgentRunner
from icoder_runtime.embedded.platform_runtime import PlatformRuntime


# ── Test fixture: minimal valid pack ──

def _make_pack(name="Test Agent", version="1.0.0", agent_type="certified", **overrides):
    """Build a minimal valid .icoder-agent pack dict."""
    pack = {
        "format_version": "1.1",
        "agent_type": agent_type,
        "manifest": {
            "name": name,
            "version": version,
            "description": "A test agent for integration testing.",
            "category": "test",
            "icon": "Bot",
        },
        "system_prompt": "You are a test agent. Return structured JSON.",
        "experts": [],
        "tools": [],
        "permissions": {},
        "requirements": {"min_runtime_version": "1.0.0"},
        "llm_capabilities": {},
        "integrity": {},
    }
    pack.update(overrides)
    # Recalculate integrity
    from icoder_runtime.core.agent_pack_v1 import _sha256
    pack["integrity"] = {"sha256": _sha256(pack)}
    return pack


# ── Test: AgentPackageV1 Validation ──


class TestAgentPackageV1:
    def test_valid_pack(self):
        pack = _make_pack()
        pkg = AgentPackageV1.from_dict(pack)
        assert pkg.name == "Test Agent"
        assert pkg.version == "1.0.0"
        assert pkg.agent_type == "certified"

    def test_missing_manifest_name_fails(self):
        pack = _make_pack()
        pack["manifest"]["name"] = ""
        with pytest.raises(ValidationError) as exc:
            AgentPackageV1.from_dict(pack, verify_integrity=False)
        assert any("name" in e.lower() for e in exc.value.detail["errors"])

    def test_missing_manifest_version_fails(self):
        pack = _make_pack()
        pack["manifest"]["version"] = ""
        with pytest.raises(ValidationError) as exc:
            AgentPackageV1.from_dict(pack, verify_integrity=False)
        assert any("version" in e.lower() for e in exc.value.detail["errors"])

    def test_missing_system_prompt_fails(self):
        pack = _make_pack()
        pack["system_prompt"] = ""
        with pytest.raises(ValidationError) as exc:
            AgentPackageV1.from_dict(pack, verify_integrity=False)
        assert any("system_prompt" in e.lower() for e in exc.value.detail["errors"])

    def test_invalid_agent_type_fails(self):
        pack = _make_pack(agent_type="invalid")
        with pytest.raises(ValidationError) as exc:
            AgentPackageV1.from_dict(pack)
        assert any("agent_type" in e.lower() for e in exc.value.detail["errors"])

    def test_integrity_check(self):
        pack = _make_pack()
        # Tamper with description after integrity was computed
        pack["manifest"]["description"] = "Tampered!"
        with pytest.raises(ValidationError) as exc:
            AgentPackageV1.from_dict(pack, verify_integrity=True)
        assert any("integrity" in e.lower() for e in exc.value.detail["errors"])

    def test_skip_integrity_check(self):
        pack = _make_pack()
        pack["manifest"]["description"] = "Tampered!"
        # Should pass when verify_integrity=False
        pkg = AgentPackageV1.from_dict(pack, verify_integrity=False)
        assert pkg.description == "Tampered!"

    def test_invalid_tool_tier_fails(self):
        pack = _make_pack()
        pack["tools"] = [{"id": "t1", "name": "Bad Tool", "tier": 99}]
        with pytest.raises(ValidationError) as exc:
            AgentPackageV1.from_dict(pack, verify_integrity=False)
        assert any("tier" in e.lower() for e in exc.value.detail["errors"])

    def test_certified_rejects_code(self):
        pack = _make_pack(agent_type="certified")
        pack["code"] = {"test.py": "def run(p): return {}"}
        with pytest.raises(ValidationError) as exc:
            AgentPackageV1.from_dict(pack, verify_integrity=False)
        assert any("certified" in e.lower() for e in exc.value.detail["errors"])

    def test_llm_capabilities_validation(self):
        from icoder_runtime.core.agent_pack_v1 import _sha256
        pack = _make_pack()
        pack["llm_capabilities"] = {
            "required_models": [{"name": "deepseek-chat"}],
            "min_total_tokens": 4096,
            "supports_tool_calling": True,
            "supports_json_mode": True,
        }
        pack["integrity"] = {"sha256": _sha256(pack)}
        pkg = AgentPackageV1.from_dict(pack)
        assert pkg.llm_capabilities["min_total_tokens"] == 4096

    def test_llm_capabilities_bad_types(self):
        pack = _make_pack()
        pack["llm_capabilities"] = {
            "supports_tool_calling": "yes",  # should be bool
        }
        with pytest.raises(ValidationError) as exc:
            AgentPackageV1.from_dict(pack, verify_integrity=False)
        assert any("supports_tool_calling" in e.lower() for e in exc.value.detail["errors"])


# ── Test: AgentRunner + LLMGateway ──


class TestAgentRunnerGateway:
    def test_runner_with_mock_provider(self):
        gateway = LLMGateway()
        gateway.register(MockLLMProvider(), default=True)
        runner = AgentRunner(gateway=gateway)

        from icoder_runtime.types import AgentDefinition
        agent = AgentDefinition(name="Test", system_prompt="You are a tester.")
        result = asyncio.run(runner.run(agent, "test input"))

        assert "review_id" in result
        assert result["output"]  # mock returns content
        assert "MockLLM" in result["output"]

    def test_runner_without_provider_throws(self):
        runner = AgentRunner()  # no gateway, no llm_callable
        from icoder_runtime.types import AgentDefinition
        agent = AgentDefinition(name="Test", system_prompt="You are a tester.")
        with pytest.raises(LLMProviderNotConfigured):
            asyncio.run(runner.run(agent, "test"))

    def test_runner_legacy_llm_callable_still_works(self):
        """Backward compat: llm_callable should still work."""
        runner = AgentRunner(llm_callable=lambda p: "legacy output")
        from icoder_runtime.types import AgentDefinition
        agent = AgentDefinition(name="Test", system_prompt="You are a tester.")
        result = asyncio.run(runner.run(agent, "test"))
        assert "legacy output" in result["output"]


# ── Test: PlatformRuntime install/list/run ──


class TestPlatformRuntime:
    @staticmethod
    def _make_runtime(tmp_path):
        from icoder_runtime.core.registry import init_registry
        from icoder_runtime.core.runtime_config import RuntimeConfig
        # Use isolated registry per test
        reg = init_registry(str(tmp_path))
        config = RuntimeConfig(
            execution_mode="platform_runtime",
            fallback_to_legacy=False,
            registry_dir=str(tmp_path),
        )
        g = LLMGateway()
        g.register(MockLLMProvider(), default=True)
        rt = PlatformRuntime(gateway=g, config=config, registry=reg)
        asyncio.run(rt.start())
        return rt

    def test_install_agent(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        pack = _make_pack()
        result = rt.install_agent(pack)
        assert result["status"] == "installed"
        assert result["name"] == "Test Agent"

    def test_install_validates_pack(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        pack = _make_pack()
        pack["manifest"]["name"] = ""
        from icoder_runtime.core.agent_pack_v1 import _sha256
        pack["integrity"] = {"sha256": _sha256(pack)}
        with pytest.raises(ValidationError):
            rt.install_agent(pack)

    def test_list_agents(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        pack = _make_pack(name="Agent A")
        rt.install_agent(pack)
        from icoder_runtime.core.agent_pack_v1 import _sha256
        pack2 = _make_pack(name="Agent B", agent_type="community")
        pack2["integrity"] = {"sha256": _sha256(pack2)}
        rt.install_agent(pack2)

        agents = rt.list_agents()
        assert len(agents) == 2

        certified = rt.list_agents(agent_type="certified")
        assert len(certified) == 1

        community = rt.list_agents(agent_type="community")
        assert len(community) == 1

    def test_run_installed_agent(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        pack = _make_pack(name="Test Runner")
        result = rt.install_agent(pack)
        agent_id = result["agent_id"]

        output = asyncio.run(rt.run_agent(agent_id, "test input"))
        assert "review_id" in output
        assert output["output"]

    def test_run_unknown_agent_throws(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        with pytest.raises(AgentNotFoundError):
            asyncio.run(rt.run_agent("nonexistent", "test"))

    def test_status(self, tmp_path):
        rt = self._make_runtime(tmp_path)
        pack = _make_pack()
        rt.install_agent(pack)
        status = rt.status()
        assert status["started"] is True
        assert status["agents_installed"] == 1
        assert "mock" in status["providers"]


# ── Test: MedicalCodingLLMProvider as LLMGateway provider ──


class TestMedicalCodingProvider:
    @pytest.mark.asyncio
    async def test_mock_mode_returns_structured_result(self):
        provider = MedicalCodingLLMProvider()  # no real engine → mock mode
        result = await provider.generate([
            {"role": "user", "content": "Review diagnosis: I21.0 for 65F chest pain."}
        ])
        assert result["content"]
        assert "mock" in result["model"]
        structured = result["structured"]
        assert structured["primary_diagnosis"]["code"] == "I21.0"
        assert structured["is_mock"] is True  # Standard schema marks mock explicitly

    @pytest.mark.asyncio
    async def test_as_gateway_provider(self):
        gateway = LLMGateway()
        gateway.register(MedicalCodingLLMProvider(), default=True)
        result = await gateway.generate([
            {"role": "user", "content": "Coding review for patient with I21.0"}
        ])
        structured = result.get("structured", {})
        assert structured["is_mock"] is True

    def test_health_check_mock_mode(self):
        provider = MedicalCodingLLMProvider()
        health = provider.health_check()
        assert health["mode"] == "mock"
        assert health["status"] == "healthy"


# ── Test: Closed loop ──


class TestClosedLoop:
    """AgentPackageV1 → publish → install to Embedded Runtime → run → LLMGateway → structured result."""

    @pytest.mark.asyncio
    async def test_full_loop(self, tmp_path):
        # 1. Build a pack
        pack = _make_pack(name="Medical Coding Reviewer", agent_type="certified")
        pack["system_prompt"] = (
            "You are a medical coding auditor. Review the patient encounter "
            "and provide ICD-10 coding recommendations in JSON format."
        )
        from icoder_runtime.core.agent_pack_v1 import _sha256
        pack["integrity"] = {"sha256": _sha256(pack)}

        # 2. Validate
        pkg = AgentPackageV1.from_dict(pack)
        assert pkg.name == "Medical Coding Reviewer"

        # 3. Create isolated registry + config
        from icoder_runtime.core.registry import init_registry
        from icoder_runtime.core.runtime_config import RuntimeConfig
        reg = init_registry(str(tmp_path))
        config = RuntimeConfig(execution_mode="platform_runtime", fallback_to_legacy=False, registry_dir=str(tmp_path))
        gateway = LLMGateway()
        gateway.register(MockLLMProvider(), alias="mock")
        gateway.register(MedicalCodingLLMProvider(), default=True)

        # 4. Start Embedded Runtime
        rt = PlatformRuntime(gateway=gateway, config=config, registry=reg)
        await rt.start()

        # 5. Install agent
        install_result = rt.install_agent(pack)
        agent_id = install_result["agent_id"]
        assert install_result["status"] == "installed"

        # 6. List agents
        agents = rt.list_agents()
        assert len(agents) == 1

        # 7. Run agent
        run_result = await rt.run_agent(
            agent_id,
            "患者女性，65岁。胸痛3小时入院。心电图示ST段抬高。诊断为急性前壁心肌梗死。"
        )
        assert "review_id" in run_result
        assert run_result["output"]
        assert run_result["processing_time_ms"] >= 0

        # 8. Verify the output comes from the gateway (medical coding mock)
        # The output should contain structured medical coding data
        assert "I21.0" in run_result["output"] or "MockLLM" in run_result["output"]

        await rt.stop()


# ── Test: ReviewCodingService ──


class TestReviewCodingService:
    def test_fallback_review(self, tmp_path):
        """ReviewCodingService works even without an installed agent (fallback to provider)."""
        from app.services.review_coding_service import ReviewCodingService

        from icoder_runtime.core.registry import init_registry
        from icoder_runtime.core.runtime_config import RuntimeConfig
        reg = init_registry(str(tmp_path))
        config = RuntimeConfig(execution_mode="platform_runtime", fallback_to_legacy=False, registry_dir=str(tmp_path))
        gateway = LLMGateway()
        gateway.register(MedicalCodingLLMProvider(), default=True)
        rt = PlatformRuntime(gateway=gateway, config=config, registry=reg)
        asyncio.run(rt.start())

        svc = ReviewCodingService(rt)
        result = asyncio.run(svc.review({
            "patient": {"name": "Test", "gender": "F", "age": 65},
            "chief_complaint": "Chest pain",
            "documents": [{"doc_type": "Note", "content": "ST段抬高，诊断为急性前壁心肌梗死"}],
        }))

        assert "primary_diagnosis" in result
        assert result["primary_diagnosis"]["code"] == "I21.0"
        assert result["source"] in ("provider", "agent", "agent_fallback", "provider_raw")

        asyncio.run(rt.stop())

    def test_agent_based_review(self, tmp_path):
        """When a coding agent is installed, ReviewCodingService uses it."""
        from app.services.review_coding_service import ReviewCodingService

        from icoder_runtime.core.registry import init_registry
        from icoder_runtime.core.runtime_config import RuntimeConfig
        reg = init_registry(str(tmp_path))
        config = RuntimeConfig(execution_mode="platform_runtime", fallback_to_legacy=False, registry_dir=str(tmp_path))
        gateway = LLMGateway()
        gateway.register(MockLLMProvider(), default=True)
        rt = PlatformRuntime(gateway=gateway, config=config, registry=reg)
        asyncio.run(rt.start())

        # Install a coding agent
        from icoder_runtime.core.agent_pack_v1 import _sha256
        pack = _make_pack(name="Medical Coding Agent", agent_type="certified")
        pack["manifest"]["category"] = "coding"
        pack["integrity"] = {"sha256": _sha256(pack)}
        rt.install_agent(pack)

        svc = ReviewCodingService(rt)
        result = asyncio.run(svc.review({
            "patient": {"name": "Test", "gender": "M", "age": 45},
            "chief_complaint": "Chest pain",
        }))

        assert "primary_diagnosis" in result
        assert "review_id" in result

        asyncio.run(rt.stop())


# ── Test: Marketplace Service ──


class TestMarketplaceService:
    def test_publish_and_search(self, tmp_path):
        from marketplace_core.storage import FileSystemStorage
        from marketplace_core.service import MarketplaceService

        storage = FileSystemStorage(str(tmp_path))
        svc = MarketplaceService(storage)

        pack = _make_pack(name="Published Agent", version="2.0.0")
        result = svc.publish(pack, publisher_name="Tester")
        assert result["published"] is True

        # Search
        results = svc.search(query="Published")
        assert results["total"] == 1
        assert results["packages"][0]["name"] == "Published Agent"

        # Get
        pkg_id = result["id"]
        pkg = svc.get_package(pkg_id)
        assert pkg["name"] == "Published Agent"

        # Stats
        stats = svc.get_stats()
        assert stats["total_packages"] == 1

        # Categories
        cats = svc.list_categories()
        assert len(cats["categories"]) == 1

    def test_download_increments_count(self, tmp_path):
        from marketplace_core.storage import FileSystemStorage
        from marketplace_core.service import MarketplaceService

        storage = FileSystemStorage(str(tmp_path))
        svc = MarketplaceService(storage)

        pack = _make_pack(name="Download Test")
        result = svc.publish(pack)
        pkg_id = result["id"]

        # First download
        data = svc.download(pkg_id)
        assert data is not None

        # Second download
        svc.download(pkg_id)
        pkg = svc.get_package(pkg_id)
        assert pkg["downloads"] == 2
