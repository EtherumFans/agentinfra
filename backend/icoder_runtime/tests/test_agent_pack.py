"""Tests for .icoder-agent package format."""
import json
import tempfile
from pathlib import Path
from icoder_runtime.types import AgentDefinition, ExpertDefinition, ToolDefinition, ToolTier
from icoder_runtime.agent_pack import (
    export_pack, save_pack, load_pack, validate_pack, import_pack, FORMAT_VERSION,
)


def _sample_agent():
    return AgentDefinition(
        id="ortho-coding",
        name="骨科编码审核 Agent",
        version="1.0.0",
        description="骨科专科 ICD 编码审核",
        category="编码",
        icon="Stethoscope",
        system_prompt="你是骨科编码审核专家。",
        expert_ids=["dx-expert", "proc-expert"],
    )


def _sample_experts():
    return [
        ExpertDefinition(id="dx-expert", name="诊断提取专家",
                         description="提取骨科诊断", system_prompt="..."),
        ExpertDefinition(id="proc-expert", name="手术提取专家",
                         description="提取骨科手术", system_prompt="..."),
    ]


def _sample_tools():
    return [
        ToolDefinition(
            id="implant-check", name="骨科内置物检查",
            description="检查骨科手术编码与内置物一致性",
            tier=ToolTier.DETERMINISTIC, category="compliance",
            requires=["procedure_code must be valid"],
            guarantees={"output": "implant match status"},
            input_schema={"type": "object", "properties": {
                "procedure_code": {"type": "string", "required": True},
            }},
            accuracy_tags=["orthopedic"],
        ),
    ]


class TestExportPack:
    def test_basic_export(self):
        agent = _sample_agent()
        pack = export_pack(agent)
        assert pack["format_version"] == FORMAT_VERSION
        assert pack["manifest"]["name"] == "骨科编码审核 Agent"
        assert pack["manifest"]["version"] == "1.0.0"
        assert "integrity" in pack
        assert pack["integrity"]["sha256"]

    def test_export_with_experts_and_tools(self):
        pack = export_pack(_sample_agent(), _sample_experts(), _sample_tools())
        assert len(pack["experts"]) == 2
        assert len(pack["tools"]) == 1
        assert pack["tools"][0]["tier"] == 1

    def test_export_with_permissions(self):
        perm = {"key": "ortho", "name": "Ortho Preset",
                "tools": {"implant-check": {"action": "require_human"}}}
        pack = export_pack(_sample_agent(), permission=perm)
        assert pack["permissions"]["key"] == "ortho"


class TestSaveAndLoad:
    def test_save_and_load(self):
        pack = export_pack(_sample_agent(), _sample_experts())
        with tempfile.NamedTemporaryFile(suffix=".icoder-agent", delete=False) as f:
            path = save_pack(pack, f.name)
        try:
            loaded = load_pack(path)
            assert loaded["manifest"]["name"] == pack["manifest"]["name"]
            assert loaded["integrity"]["sha256"] == pack["integrity"]["sha256"]
        finally:
            Path(path).unlink()

    def test_auto_suffix(self):
        pack = export_pack(_sample_agent())
        with tempfile.NamedTemporaryFile(suffix=".icoder-agent", delete=False) as f:
            path = save_pack(pack, f.name)
        try:
            assert path.suffix == ".icoder-agent"
        finally:
            Path(path).unlink()


class TestValidate:
    def test_valid_pack(self):
        pack = export_pack(_sample_agent(), _sample_experts())
        errors = validate_pack(pack)
        assert errors == []

    def test_missing_name(self):
        pack = export_pack(_sample_agent())
        pack["manifest"]["name"] = ""
        errors = validate_pack(pack)
        assert any("name" in e for e in errors)

    def test_missing_system_prompt(self):
        pack = export_pack(_sample_agent())
        pack["system_prompt"] = ""
        errors = validate_pack(pack)
        assert any("system_prompt" in e for e in errors)

    def test_invalid_tool_tier(self):
        pack = export_pack(_sample_agent(), tools=_sample_tools())
        pack["tools"][0]["tier"] = 3
        errors = validate_pack(pack)
        assert any("tier" in e for e in errors)

    def test_invalid_format_version(self):
        pack = export_pack(_sample_agent())
        pack["format_version"] = "0.1"
        errors = validate_pack(pack)
        assert len(errors) >= 1


class TestImport:
    def test_import_roundtrip(self):
        agent = _sample_agent()
        experts = _sample_experts()
        tools = _sample_tools()
        perm = {"key": "ortho", "name": "Ortho Preset",
                "tools": {"implant-check": {"action": "allow"}}}

        pack = export_pack(agent, experts, tools, perm)
        imported_agent, imported_experts, imported_tools, imported_perm = import_pack(pack)

        assert imported_agent.name == agent.name
        assert len(imported_experts) == 2
        assert imported_experts[0].id == "dx-expert"
        assert len(imported_tools) == 1
        assert imported_tools[0].tier == ToolTier.DETERMINISTIC
        assert imported_perm == perm

    def test_import_minimal(self):
        pack = export_pack(_sample_agent())
        agent, experts, tools, perm = import_pack(pack)
        assert agent.name == "骨科编码审核 Agent"
        assert experts == []
        assert tools == []


class TestIntegrity:
    def test_tampered_pack(self):
        pack = export_pack(_sample_agent(), _sample_experts())
        original_hash = pack["integrity"]["sha256"]
        pack["manifest"]["name"] = "Tampered"
        # Hash should change
        import hashlib, json
        raw = json.dumps(pack, sort_keys=True, ensure_ascii=False, default=str)
        new_hash = hashlib.sha256(raw.encode()).hexdigest()
        assert new_hash != original_hash
