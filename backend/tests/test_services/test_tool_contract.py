"""Test Tool Registry and Contract Engine"""
import pytest
from app.services.tool_registry import ToolDefinition, ToolRegistry, ToolTier
from app.services.contract_engine import (
    SymbolicState,
    evaluate_precondition,
    validate_postcondition,
    ContractViolation,
    ContractResult,
)


# ── Tool Registry Tests ──

def make_tool(**overrides) -> ToolDefinition:
    defaults = {
        "id": "test_tool", "name": "Test Tool", "description": "A test tool",
        "tier": ToolTier.DETERMINISTIC, "category": "coding",
    }
    defaults.update(overrides)
    return ToolDefinition(**defaults)


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        tool = make_tool(id="extract_evidence")
        reg.register(tool)
        assert reg.get("extract_evidence") is tool
        assert len(reg) == 1

    def test_list_by_tier(self):
        reg = ToolRegistry()
        t1 = make_tool(id="t1", tier=ToolTier.DETERMINISTIC)
        t2 = make_tool(id="t2", tier=ToolTier.LLM_REASONING)
        reg.register(t1)
        reg.register(t2)
        assert len(reg.list_by_tier(ToolTier.DETERMINISTIC)) == 1
        assert len(reg.list_by_tier(ToolTier.LLM_REASONING)) == 1

    def test_list_by_category(self):
        reg = ToolRegistry()
        reg.register(make_tool(id="t1", category="coding"))
        reg.register(make_tool(id="t2", category="verification"))
        assert len(reg.list_by_category("coding")) == 1
        assert len(reg.list_by_category("verification")) == 1
        assert len(reg.list_by_category("report")) == 0

    def test_list_by_tag(self):
        reg = ToolRegistry()
        reg.register(make_tool(id="t1", accuracy_tags=["evidence_binding"]))
        reg.register(make_tool(id="t2", accuracy_tags=["code_dict"]))
        assert len(reg.list_by_tag("evidence_binding")) == 1
        assert len(reg.list_by_tag("code_dict")) == 1
        assert len(reg.list_by_tag("nonexistent")) == 0

    def test_get_categories(self):
        reg = ToolRegistry()
        reg.register(make_tool(id="t1", category="coding"))
        reg.register(make_tool(id="t2", category="coding"))
        reg.register(make_tool(id="t3", category="verification"))
        cats = reg.get_categories()
        assert len(cats["coding"]) == 2
        assert len(cats["verification"]) == 1

    def test_get_injectable_by_tag(self):
        reg = ToolRegistry()
        reg.register(make_tool(id="t1", accuracy_tags=["code_dict"], is_injectable=True))
        reg.register(make_tool(id="t2", accuracy_tags=["code_dict"], is_injectable=False))
        injectable = reg.get_injectable_by_tag("code_dict")
        assert len(injectable) == 1
        assert injectable[0].id == "t1"

    def test_resolve_dependencies(self):
        reg = ToolRegistry()
        reg.register(make_tool(id="step_a"))
        reg.register(make_tool(id="step_b", requires=["step_a"], tier=ToolTier.DETERMINISTIC))
        reg.register(make_tool(id="step_c", requires=["step_b", "step_a"], tier=ToolTier.DETERMINISTIC))
        reg.register(make_tool(id="step_d", tier=ToolTier.LLM_REASONING))

        resolved = reg.resolve_dependencies(["step_c", "step_d"])
        # step_a -> step_b -> step_c (deps first), then step_d
        assert resolved.index("step_a") < resolved.index("step_b") < resolved.index("step_c")
        assert "step_d" in resolved

    def test_resolve_dependencies_no_duplicates(self):
        reg = ToolRegistry()
        reg.register(make_tool(id="step_a"))
        reg.register(make_tool(id="step_b", requires=["step_a"], tier=ToolTier.DETERMINISTIC))
        reg.register(make_tool(id="step_c", requires=["step_a"], tier=ToolTier.DETERMINISTIC))
        # Both step_b and step_c depend on step_a — step_a should appear once
        resolved = reg.resolve_dependencies(["step_b", "step_c"])
        assert resolved.count("step_a") == 1

    def test_contains(self):
        reg = ToolRegistry()
        reg.register(make_tool(id="my_tool"))
        assert "my_tool" in reg
        assert "nonexistent" not in reg

    def test_get_nonexistent(self):
        reg = ToolRegistry()
        assert reg.get("no_such_tool") is None

    def test_register_overwrite(self):
        reg = ToolRegistry()
        t1 = make_tool(id="same_id", name="First")
        t2 = make_tool(id="same_id", name="Second")
        reg.register(t1)
        reg.register(t2)
        assert reg.get("same_id").name == "Second"
        assert len(reg) == 1


# ── SymbolicState Tests ──

class TestSymbolicState:
    def test_get_and_has(self):
        s = SymbolicState({"evidence": {"diagnosis_facts": [{"name": "肺炎"}]}})
        assert s.has("evidence.diagnosis_facts")
        assert s.get("evidence.diagnosis_facts") == [{"name": "肺炎"}]
        assert not s.has("evidence.nonexistent")
        assert s.get("evidence.nonexistent") is None

    def test_has_empty_list(self):
        s = SymbolicState({"items": []})
        assert not s.has("items")
        s = SymbolicState({"items": [1, 2]})
        assert s.has("items")

    def test_has_none(self):
        s = SymbolicState({"key": None})
        assert not s.has("key")

    def test_merge(self):
        s = SymbolicState()
        s.merge({"new_key": "value"}, tool_id="test_tool")
        assert s.get("new_key") == "value"
        assert s._update_count == 1

    def test_snapshot(self):
        s = SymbolicState({"a": 1})
        snap = s.snapshot()
        snap["a"] = 2  # Should not mutate original
        assert s.get("a") == 1

    def test_merge_only_through_verified_path(self):
        """SymbolicState._data is internal — in production, only post_check merges."""
        s = SymbolicState()
        s.merge({"trusted": True}, tool_id="audited_tool")
        assert len(s._update_log) == 1
        assert s._update_log[0]["tool"] == "audited_tool"


# ── Precondition Tests ──

class TestPreconditionEvaluation:
    def test_empty_expr_allows(self):
        result, reason = evaluate_precondition("", SymbolicState())
        assert result == ContractResult.ALLOW

    def test_has_true(self):
        s = SymbolicState({"evidence": {"diagnosis_facts": [{"name": "肺炎"}]}})
        result, _ = evaluate_precondition("state.has('evidence.diagnosis_facts')", s)
        assert result == ContractResult.ALLOW

    def test_has_false(self):
        s = SymbolicState({})
        result, reason = evaluate_precondition("state.has('evidence.diagnosis_facts')", s)
        assert result == ContractResult.DENY
        assert "Precondition not met" in reason

    def test_and_both_true(self):
        s = SymbolicState({"a": [1], "b": [2]})
        result, _ = evaluate_precondition("state.has('a') and state.has('b')", s)
        assert result == ContractResult.ALLOW

    def test_and_one_false(self):
        s = SymbolicState({"a": [1]})
        result, _ = evaluate_precondition("state.has('a') and state.has('b')", s)
        assert result == ContractResult.DENY

    def test_or_one_true(self):
        s = SymbolicState({"a": [1]})
        result, _ = evaluate_precondition("state.has('a') or state.has('b')", s)
        assert result == ContractResult.ALLOW

    def test_or_both_false(self):
        s = SymbolicState({})
        result, _ = evaluate_precondition("state.has('a') or state.has('b')", s)
        assert result == ContractResult.DENY

    def test_multiple_and(self):
        s = SymbolicState({"a": [1], "b": [2], "c": [3]})
        result, _ = evaluate_precondition(
            "state.has('a') and state.has('b') and state.has('c')", s
        )
        assert result == ContractResult.ALLOW


# ── Postcondition Tests ──

class TestPostconditionValidation:
    def test_exists_present(self):
        result, _ = validate_postcondition("output.code", {"code": "J18.9"}, SymbolicState())
        assert result == ContractResult.ALLOW

    def test_exists_missing(self):
        result, reason = validate_postcondition("output.code", {}, SymbolicState())
        assert result == ContractResult.DENY
        assert "is None" in reason

    def test_non_empty_valid(self):
        result, _ = validate_postcondition("output.items: non-empty", {"items": [1, 2]}, SymbolicState())
        assert result == ContractResult.ALLOW

    def test_non_empty_invalid(self):
        result, reason = validate_postcondition("output.items: non-empty", {"items": []}, SymbolicState())
        assert result == ContractResult.DENY
        assert "empty" in reason

    def test_valid_icd10_code(self):
        result, _ = validate_postcondition(
            "output.code: valid icd10_code", {"code": "J18.9"}, SymbolicState()
        )
        assert result == ContractResult.ALLOW

    def test_invalid_icd10_code(self):
        result, reason = validate_postcondition(
            "output.code: valid icd10_code", {"code": "not_a_code"}, SymbolicState()
        )
        assert result == ContractResult.DENY

    def test_valid_list(self):
        result, _ = validate_postcondition(
            "output.candidates: valid list", {"candidates": [1, 2]}, SymbolicState()
        )
        assert result == ContractResult.ALLOW

    def test_invalid_list(self):
        result, reason = validate_postcondition(
            "output.candidates: valid list", {"candidates": "not_a_list"}, SymbolicState()
        )
        assert result == ContractResult.DENY

    def test_min_length_valid(self):
        result, _ = validate_postcondition(
            "output.items: min_length 2", {"items": [1, 2, 3]}, SymbolicState()
        )
        assert result == ContractResult.ALLOW

    def test_min_length_invalid(self):
        result, reason = validate_postcondition(
            "output.items: min_length 2", {"items": [1]}, SymbolicState()
        )
        assert result == ContractResult.DENY

    def test_invalid_guarantee_path(self):
        result, reason = validate_postcondition("bad_path.key", {}, SymbolicState())
        assert result == ContractResult.DENY
        assert "must start with 'output'" in reason


# ── ContractViolation Tests ──

class TestContractViolation:
    def test_to_feedback_precondition(self):
        v = ContractViolation("rank_evidence", "precondition",
                              "state.has('diagnosis_candidates') not met",
                              "Call extract_evidence and assign_diagnosis_code first")
        fb = v.to_feedback()
        assert "rank_evidence" in fb
        assert "precondition" in fb
        assert "extract_evidence" in fb

    def test_to_feedback_postcondition(self):
        v = ContractViolation("assign_diagnosis_code", "postcondition",
                              "output.code is not valid ICD-10",
                              "Ensure code comes from search_icd10_index results")
        fb = v.to_feedback()
        assert "assign_diagnosis_code" in fb
        assert "postcondition" in fb
        assert "search_icd10_index" in fb


# ── Integration: End-to-end contract flow ──

class TestContractFlow:
    """Simulate a complete Agent tool-calling flow with contract enforcement."""

    def test_happy_path_contract_flow(self):
        """LLM calls tools in correct order, all contracts pass."""
        reg = ToolRegistry()
        s = SymbolicState()

        # Simulate: extract_evidence → search_icd10 → assign_diagnosis → rank_evidence → report
        # After each tool call: pre_check → execute → post_check → merge

        # Step 1: extract_evidence (no preconditions)
        result, reason = evaluate_precondition("", s)
        assert result == ContractResult.ALLOW
        s.merge({"evidence": {"diagnosis_facts": [{"name": "肺炎"}]}}, tool_id="extract_evidence")
        assert s.has("evidence.diagnosis_facts")

        # Step 2: search_icd10_index (no preconditions)
        result, _ = evaluate_precondition("", s)
        assert result == ContractResult.ALLOW
        s.merge({"icd10_results": [{"code": "J18.9", "name": "肺炎"}]}, tool_id="search_icd10_index")
        assert s.has("icd10_results")

        # Step 3: assign_diagnosis_code (requires evidence and icd10 results)
        result, _ = evaluate_precondition(
            "state.has('evidence.diagnosis_facts') and state.has('icd10_results')", s
        )
        assert result == ContractResult.ALLOW
        output = {"code": "J18.9", "evidence_binding": "CT示右下肺感染"}
        result, _ = validate_postcondition("output.code: valid icd10_code", output, s)
        assert result == ContractResult.ALLOW
        s.merge({"diagnosis_candidates": [output]}, tool_id="assign_diagnosis_code")

        # Step 4: rank_evidence (requires diagnosis_candidates)
        result, _ = evaluate_precondition("state.has('diagnosis_candidates')", s)
        assert result == ContractResult.ALLOW
        s.merge({"evidence_ranking": {"scores": [{"code": "J18.9", "score": 85}]}}, tool_id="rank_evidence")

        # Step 5: format_report (requires evidence_ranking)
        result, _ = evaluate_precondition("state.has('evidence_ranking')", s)
        assert result == ContractResult.ALLOW

    def test_rejected_flow_llm_skips_dependency(self):
        """LLM tries to call rank_evidence before assign_diagnosis — harness rejects."""
        s = SymbolicState({"evidence": {"diagnosis_facts": [{"name": "肺炎"}]}})

        # LLM tries to call rank_evidence without diagnosis_candidates
        result, reason = evaluate_precondition("state.has('diagnosis_candidates')", s)
        assert result == ContractResult.DENY

        # LLM should now call assign_diagnosis_code first, then retry
        s.merge({"diagnosis_candidates": [{"code": "J18.9"}]}, tool_id="assign_diagnosis_code")
        result, _ = evaluate_precondition("state.has('diagnosis_candidates')", s)
        assert result == ContractResult.ALLOW  # Now passes

    def test_rejected_flow_invalid_output(self):
        """Tool produces invalid output — postcondition rejects, state not updated."""
        s = SymbolicState({"evidence": {"diagnosis_facts": [{"name": "肺炎"}]}})

        # Tool returns invalid ICD-10 code
        bad_output = {"code": "INVALID"}
        result, reason = validate_postcondition("output.code: valid icd10_code", bad_output, s)
        assert result == ContractResult.DENY

        # State must NOT be updated with invalid output
        s.merge({"diagnosis_candidates": []}, tool_id="assign_diagnosis_code")
        assert s.get("diagnosis_candidates") == []  # Empty, not the bad output
