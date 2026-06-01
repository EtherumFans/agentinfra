"""Tests for sandbox execution and community Agent packs."""
import json
import pytest
from icoder_runtime.sandbox import execute, SandboxTimeout, SandboxError
from icoder_runtime.agent_pack import export_pack, validate_pack, import_pack
from icoder_runtime.types import AgentDefinition, ToolDefinition, ToolTier


class TestSandbox:
    def test_basic_execution(self):
        code = """
def run(params):
    return {"result": params.get("x", 0) + params.get("y", 0)}
"""
        result = execute(code, {"x": 3, "y": 4})
        assert result == {"result": 7}

    def test_timeout(self):
        code = """
def run(params):
    import time
    time.sleep(10)
    return {"ok": True}
"""
        with pytest.raises(SandboxTimeout):
            execute(code, {}, timeout=1)

    def test_restricted_import(self):
        code = """
def run(params):
    import requests
    return {"ok": True}
"""
        with pytest.raises(SandboxError):
            execute(code, {})

    def test_missing_run_function(self):
        code = "x = 1"
        with pytest.raises(SandboxError, match="No run"):
            execute(code, {})

    def test_non_dict_return(self):
        code = """
def run(params):
    return ["list", "not", "dict"]
"""
        with pytest.raises(SandboxError, match="dict"):
            execute(code, {})

    def test_json_types(self):
        code = """
def run(params):
    return {
        "string": "hello",
        "number": 42,
        "float": 3.14,
        "bool": True,
        "list": [1, 2, 3],
        "nested": {"key": "value"},
    }
"""
        result = execute(code, {})
        assert result["string"] == "hello"
        assert result["number"] == 42


class TestCommunityAgentPack:
    def test_community_pack_validation(self):
        code = {
            "custom_check.py": "def run(params):\n    return {'ok': True}\n",
        }
        tools = [
            ToolDefinition(
                id="custom-check", name="Custom Check",
                description="Custom compliance check",
                tier=ToolTier.DETERMINISTIC, category="compliance",
                requires=["input must be dict"],
                guarantees={"output": "ok status"},
                input_schema={"type": "object", "properties": {"x": {"type": "int"}}},
            )
        ]
        # Manually set executor_file (not in ToolDefinition constructor)
        tools[0].__dict__["executor_file"] = "custom_check.py"

        agent = AgentDefinition(name="Test Community", system_prompt="You are a tester.")
        pack = export_pack(agent, tools=tools)
        pack["agent_type"] = "community"
        pack["code"] = code
        # Patch tools in pack to have executor_file
        pack["tools"][0]["executor_file"] = "custom_check.py"

        errors = validate_pack(pack)
        assert errors == []

        agent2, experts, imported_tools, _ = import_pack(pack)
        assert len(imported_tools) == 1
        assert imported_tools[0].executor is not None

    def test_certified_rejects_code(self):
        agent = AgentDefinition(name="Test", system_prompt="You are a tester.")
        pack = export_pack(agent)
        pack["code"] = {"test.py": "def run(p): return {}"}
        errors = validate_pack(pack)
        assert any("certified" in e.lower() for e in errors)

    def test_executor_file_must_exist_in_code(self):
        agent = AgentDefinition(name="Test", system_prompt="You are a tester.")
        pack = export_pack(agent)
        pack["agent_type"] = "community"
        pack["tools"] = [{"id": "t", "name": "T", "description": "",
                          "tier": 1, "category": "test",
                          "executor_file": "missing.py"}]
        errors = validate_pack(pack)
        assert any("executor_file" in e for e in errors)


class TestSandboxIntegration:
    def test_executor_runs_in_sandbox(self):
        code = {
            "age_check.py": "def run(params):\n    age = params.get('age',0)\n    return {'valid': age >= 18}\n",
        }
        tools = [
            ToolDefinition(
                id="age-check", name="Age Check",
                description="Check patient age",
                tier=ToolTier.DETERMINISTIC, category="compliance",
                requires=["age must be int"],
                guarantees={"output": "valid bool"},
                input_schema={"type":"object","properties":{"age":{"type":"int"}}},
            )
        ]
        agent = AgentDefinition(name="Age Agent", system_prompt="Age checker")
        pack = export_pack(agent, tools=tools)
        pack["agent_type"] = "community"
        pack["code"] = code
        pack["tools"][0]["executor_file"] = "age_check.py"

        _, _, imported_tools, _ = import_pack(pack)
        tool = imported_tools[0]
        assert tool.executor is not None

        result = tool.executor(age=25)
        assert result == {"valid": True}

        result = tool.executor(age=12)
        assert result == {"valid": False}
