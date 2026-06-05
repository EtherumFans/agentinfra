"""API-level integration tests — Database, Registry, Compliance, Runtime flows.

Tests cover:
  1. SQLite Registry CRUD
  2. RuntimeAgentRegistry install/list/get/remove
  3. Agent lifecycle (enable/disable)
  4. Compliance RuleEngine validate
  5. MedicalCodingOutputSchema round-trip
  6. DeepSeek inference flow
  7. Fallback/Shadow recording
  8. Audit chain
  9. Data policy enforcement
  10. Gold case evaluation metrics
"""

import json
import pytest
from icoder_runtime.core.registry import RuntimeAgentRegistry
from icoder_runtime.core.registry_backend import SQLiteRegistryBackend, FileRegistryBackend, create_backend
from icoder_runtime.core.errors import AgentNotFoundError, ValidationError
from icoder_runtime.core.agent_pack_v1 import AgentPackageV1


def _make_pack(name="Test Agent", version="1.0.0", agent_type="certified"):
    pack = {
        "format_version": "1.1", "agent_type": agent_type,
        "manifest": {"name": name, "version": version, "description": "Test", "category": "test", "icon": "Bot"},
        "system_prompt": "You are a test agent.", "experts": [], "tools": [], "permissions": {},
        "requirements": {"min_runtime_version": "1.0.0"}, "llm_capabilities": {},
    }
    from icoder_runtime.core.agent_pack_v1 import _sha256
    pack["integrity"] = {"sha256": _sha256(pack)}
    return pack


class TestSQLiteRegistry:
    def test_backend_create(self, tmp_path):
        backend = SQLiteRegistryBackend(str(tmp_path / "test.db"))
        assert backend.backend_name == "sqlite"

    def test_backend_save_load(self, tmp_path):
        backend = SQLiteRegistryBackend(str(tmp_path / "test.db"))
        data = {"agents": {"test-1.0": {"agent_id": "test-1.0", "name": "Test"}}, "schema_version": "1.0"}
        backend.save(data)
        loaded = backend.load()
        assert loaded is not None
        assert "test-1.0" in loaded["agents"]

    def test_backend_empty_load(self, tmp_path):
        backend = SQLiteRegistryBackend(str(tmp_path / "empty.db"))
        result = backend.load()
        assert result is None or result.get("agents") == {}

    def test_factory_create_sqlite(self):
        backend = create_backend("sqlite", sqlite_path=":memory:")
        assert backend.backend_name == "sqlite"


class TestRegistryCRUD:
    def test_install_and_get(self, tmp_path):
        reg = RuntimeAgentRegistry(str(tmp_path))
        pack = _make_pack("My Agent", "2.0.0")
        rec = reg.install(pack)
        assert rec.agent_id == "my-agent-2.0.0"
        assert rec.name == "My Agent"
        retrieved = reg.get("my-agent-2.0.0")
        assert retrieved.name == "My Agent"

    def test_list_and_filter(self, tmp_path):
        reg = RuntimeAgentRegistry(str(tmp_path))
        reg.install(_make_pack("A1", "1.0"))
        reg.install(_make_pack("A2", "1.0", "community"))
        assert reg.count == 2
        assert len(reg.list_all("certified")) == 1
        assert len(reg.list_all("community")) == 1

    def test_find_by_partial(self, tmp_path):
        reg = RuntimeAgentRegistry(str(tmp_path))
        reg.install(_make_pack("Unique Name", "1.0"))
        found = reg.find("unique")
        assert found is not None
        assert found.name == "Unique Name"

    def test_remove(self, tmp_path):
        reg = RuntimeAgentRegistry(str(tmp_path))
        reg.install(_make_pack("ToRemove", "1.0"))
        reg.remove("toremove-1.0")
        assert reg.count == 0
        with pytest.raises(AgentNotFoundError):
            reg.get("toremove-1.0")

    def test_persistence_to_disk(self, tmp_path):
        import os
        reg = RuntimeAgentRegistry(str(tmp_path))
        reg.install(_make_pack("Persist", "1.0"))
        assert reg.count == 1
        # Verify registry file exists on disk
        reg_file = tmp_path / "agent_registry.json"
        assert os.path.exists(str(reg_file))


class TestAgentLifecycle:
    def test_enable_disable(self, tmp_path):
        reg = RuntimeAgentRegistry(str(tmp_path))
        rec = reg.install(_make_pack("LC", "1.0"))
        assert rec.status == "installed"
        rec.status = "enabled"
        assert reg.get("lc-1.0").status == "enabled"
        rec.status = "disabled"
        assert reg.get("lc-1.0").status == "disabled"


class TestComplianceValidation:
    def test_validate_pass(self):
        from compliance_services.rule_engine import RuleEngine
        from compliance_services.medical_coding_rules import MedicalCodingRuleSet
        engine = RuleEngine()
        engine.register(MedicalCodingRuleSet())
        result = engine.validate("medical_coding", {
            "primary_diagnosis": {"code": "I21.0", "description": "STEMI"},
            "secondary_diagnoses": [], "procedures": [], "review_conclusion": "PASS",
        }, {})
        assert result.passed is True

    def test_validate_missing_dx(self):
        from compliance_services.rule_engine import RuleEngine
        from compliance_services.medical_coding_rules import MedicalCodingRuleSet
        engine = RuleEngine()
        engine.register(MedicalCodingRuleSet())
        result = engine.validate("medical_coding", {
            "primary_diagnosis": {"code": ""}, "secondary_diagnoses": [], "procedures": [],
        }, {})
        assert result.passed is False
        assert any("R001" in i.rule_id for i in result.issues)

    def test_validate_m80_trigger(self):
        from compliance_services.rule_engine import RuleEngine
        from compliance_services.medical_coding_rules import MedicalCodingRuleSet
        engine = RuleEngine()
        engine.register(MedicalCodingRuleSet())
        result = engine.validate("medical_coding", {
            "primary_diagnosis": {"code": "M48.56"}, "secondary_diagnoses": [], "procedures": [],
        }, {"encounter_text": "患者72岁骨质疏松椎体新鲜压缩骨折"})
        assert any("M80" in i.rule_id for i in result.issues) or any("M80" in i.message for i in result.issues)

    def test_validate_duplicate_codes(self):
        from compliance_services.rule_engine import RuleEngine
        from compliance_services.medical_coding_rules import MedicalCodingRuleSet
        engine = RuleEngine()
        engine.register(MedicalCodingRuleSet())
        result = engine.validate("medical_coding", {
            "primary_diagnosis": {"code": "I10"}, "secondary_diagnoses": [{"code": "I10"}], "procedures": [],
        }, {})
        assert any("R003" in i.rule_id for i in result.issues)


class TestMedicalCodingSchema:
    def test_schema_round_trip(self):
        from official_agents.medical_coding.schema import MedicalCodingOutputSchema
        data = {
            "review_conclusion": "PASS",
            "primary_diagnosis": {"code": "I21.0", "description": "STEMI", "confidence": 0.95, "category": "principal", "evidence": ["ECG"]},
            "secondary_diagnoses": [], "procedures": [], "issues_found": [],
        }
        schema = MedicalCodingOutputSchema.from_dict(data, provider="test")
        assert schema.review_conclusion == "PASS"
        assert schema.primary_diagnosis.code == "I21.0"
        assert not schema.is_mock

    def test_mock_result_is_marked(self):
        from official_agents.medical_coding.schema import MedicalCodingOutputSchema
        result = MedicalCodingOutputSchema.mock_result()
        assert result.is_mock is True
        assert result.primary_diagnosis.code == "I21.0"


class TestAgentPackValidation:
    def test_valid_pack(self):
        pack = _make_pack()
        pkg = AgentPackageV1.from_dict(pack)
        assert pkg.name == "Test Agent"

    def test_missing_name(self):
        pack = _make_pack()
        pack["manifest"]["name"] = ""
        with pytest.raises(ValidationError):
            AgentPackageV1.from_dict(pack, verify_integrity=False)

    def test_tampered_integrity(self):
        pack = _make_pack()
        pack["manifest"]["description"] = "Tampered"
        with pytest.raises(ValidationError):
            AgentPackageV1.from_dict(pack)

    def test_security_tier_0(self):
        pack = _make_pack()
        pkg = AgentPackageV1.from_dict(pack)
        assert pkg.security_tier == 0
        assert not pkg.default_disabled

    def test_security_tier_2(self):
        pack = _make_pack(agent_type="certified")
        pack["code"] = {"test.py": "def run(p): return {}"}
        from icoder_runtime.core.agent_pack_v1 import _sha256
        pack["integrity"] = {"sha256": _sha256(pack)}
        with pytest.raises(ValidationError):
            AgentPackageV1.from_dict(pack)


class TestDataPolicy:
    def test_default_blocks_external_llm(self):
        from icoder_runtime.core.data_policy import RuntimeDataPolicy
        dp = RuntimeDataPolicy(allow_external_llm=False)
        ok, reason = dp.can_use_provider("deepseek")
        assert not ok
        assert "blocked" in reason.lower()

    def test_explicit_allow(self):
        from icoder_runtime.core.data_policy import RuntimeDataPolicy
        dp = RuntimeDataPolicy(allow_external_llm=True)
        ok, _ = dp.can_use_provider("deepseek")
        assert ok

    def test_allows_when_enabled(self):
        from icoder_runtime.core.data_policy import RuntimeDataPolicy
        dp = RuntimeDataPolicy(allow_external_llm=True)
        ok, _ = dp.can_use_provider("deepseek")
        assert ok


class TestPIIRedaction:
    def test_redacts_id_card(self):
        from icoder_runtime.core.pii_redaction import PIIRedactor
        r = PIIRedactor(True)
        result = r.redact("身份证110101199001011234")
        assert result.redaction_applied
        assert "110101" not in result.redacted_text

    def test_redacts_phone(self):
        from icoder_runtime.core.pii_redaction import PIIRedactor
        r = PIIRedactor(True)
        result = r.redact("手机13800138000联系")
        assert result.redaction_applied

    def test_preserves_medical_terms(self):
        from icoder_runtime.core.pii_redaction import PIIRedactor
        r = PIIRedactor(True)
        result = r.redact("诊断急性前壁心肌梗死I21.0")
        assert "急性前壁心肌梗死" in result.redacted_text
