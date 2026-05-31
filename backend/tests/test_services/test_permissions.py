"""Test Deny-First Permission Model"""
import pytest
from app.services.permissions import (
    ToolPermission,
    PermissionPolicy,
    PermissionOutcome,
    PRESET_POLICIES,
)


class TestToolPermission:
    def test_default_deny(self):
        """Every tool defaults to DENY."""
        p = ToolPermission("test_tool")
        assert p.allowed is False
        assert p.check() == PermissionOutcome.DENY

    def test_explicit_allow(self):
        p = ToolPermission("test_tool", allowed=True)
        assert p.check() == PermissionOutcome.ALLOW

    def test_requires_human(self):
        p = ToolPermission("finalize_diagnosis", allowed=True, requires_human=True)
        assert p.check() == PermissionOutcome.NEEDS_HUMAN

    def test_rate_limit_exceeded(self):
        p = ToolPermission("extract_evidence", allowed=True, max_per_session=3)
        for _ in range(3):
            assert p.check() == PermissionOutcome.ALLOW
            p.record_invocation()
        # 4th call denied
        assert p.check() == PermissionOutcome.DENY

    def test_rate_limit_not_exceeded(self):
        p = ToolPermission("extract_evidence", allowed=True, max_per_session=3)
        for _ in range(2):
            assert p.check() == PermissionOutcome.ALLOW
            p.record_invocation()
        assert p.check() == PermissionOutcome.ALLOW

    def test_record_invocation(self):
        p = ToolPermission("test", allowed=True, max_per_session=2)
        p.record_invocation()
        assert p._invocation_count == 1
        p.record_invocation()
        assert p._invocation_count == 2


class TestPermissionPolicy:
    def test_unknown_tool_denied(self):
        policy = PermissionPolicy()
        assert policy.check("nonexistent_tool") == PermissionOutcome.DENY

    def test_allowed_tool(self):
        policy = PermissionPolicy(permissions={
            "extract_evidence": ToolPermission("extract_evidence", allowed=True),
        })
        assert policy.check("extract_evidence") == PermissionOutcome.ALLOW

    def test_denied_tool(self):
        policy = PermissionPolicy(permissions={
            "dangerous_tool": ToolPermission("dangerous_tool", allowed=False),
        })
        assert policy.check("dangerous_tool") == PermissionOutcome.DENY

    def test_record_tracks_invocation(self):
        policy = PermissionPolicy(permissions={
            "test": ToolPermission("test", allowed=True, max_per_session=2),
        })
        policy.record("test")
        policy.record("test")
        assert policy.check("test") == PermissionOutcome.DENY  # rate limit

    def test_serialize_roundtrip(self):
        original = PermissionPolicy.medical_coding()
        config = original.to_config()
        restored = PermissionPolicy.from_config(config)
        # Verify key tools are present
        assert restored.check("extract_evidence") == PermissionOutcome.ALLOW
        assert restored.check("search_icd10_index") == PermissionOutcome.ALLOW
        assert restored.check("nonexistent") == PermissionOutcome.DENY

    def test_to_config_output_format(self):
        policy = PermissionPolicy(permissions={
            "test_tool": ToolPermission("test_tool", allowed=True, max_per_session=5, requires_human=False),
        })
        config = policy.to_config()
        assert config["test_tool"]["allowed"] is True
        assert config["test_tool"]["max_per_session"] == 5
        assert config["test_tool"]["requires_human"] is False


class TestPresetPolicies:
    def test_medical_coding_has_all_deterministic_tools(self):
        policy = PermissionPolicy.medical_coding()
        # Tier 1 deterministic tools must be allowed
        for tid in ["search_icd10_index", "rank_evidence", "calibrate_confidence", "guard_input"]:
            assert policy.check(tid) == PermissionOutcome.ALLOW, f"{tid} should be allowed"

    def test_medical_coding_blocks_unknown(self):
        policy = PermissionPolicy.medical_coding()
        assert policy.check("invented_tool") == PermissionOutcome.DENY

    def test_cdi_audit_no_coding_tools(self):
        policy = PermissionPolicy.cdi_audit()
        # CDI audit should NOT include coding assignment tools
        assert policy.check("assign_diagnosis_code") == PermissionOutcome.DENY
        # But SHOULD include documentation analysis
        assert policy.check("check_documentation_gaps") == PermissionOutcome.ALLOW

    def test_restrictive_only_deterministic(self):
        policy = PermissionPolicy.restrictive()
        # deterministic tools allowed
        assert policy.check("search_icd10_index") == PermissionOutcome.ALLOW
        # LLM tools denied
        assert policy.check("extract_evidence") == PermissionOutcome.DENY
        assert policy.check("assign_diagnosis_code") == PermissionOutcome.DENY

    def test_full_access_all_17_tools(self):
        policy = PermissionPolicy.full_access()
        all_tools = [
            "extract_evidence", "reconstruct_timeline",
            "search_icd10_index", "search_icd9_index",
            "assign_diagnosis_code", "assign_procedure_code",
            "rank_evidence", "calibrate_confidence",
            "verify_evidence", "analyze_disagreements",
            "analyze_drg_impact", "check_documentation_gaps",
            "cdi_review", "format_report", "generate_cdi_query",
            "guard_input", "guard_output",
        ]
        for tid in all_tools:
            assert policy.check(tid) == PermissionOutcome.ALLOW, f"{tid} should be allowed"

    def test_drg_analysis_permissions(self):
        policy = PermissionPolicy.drg_analysis()
        assert policy.check("analyze_drg_impact") == PermissionOutcome.ALLOW
        assert policy.check("calibrate_confidence") == PermissionOutcome.ALLOW

    def test_all_preset_policies_registered(self):
        assert len(PRESET_POLICIES) == 5
        for key in ["medical_coding", "cdi_audit", "drg_analysis", "restrictive", "full_access"]:
            assert key in PRESET_POLICIES
            assert "name" in PRESET_POLICIES[key]
            assert "description" in PRESET_POLICIES[key]
