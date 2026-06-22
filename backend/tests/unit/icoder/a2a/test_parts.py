"""A2A Part parsing tests (SPEC §5) + iCoDer metadata + schema_registry."""

from __future__ import annotations

import pytest

from app.icoder.agent_runtime.a2a import (
    ALL_ICODER_SCHEMAS,
    A2AError,
    A2AErrorCode,
    DataPart,
    DelegationMetadata,
    FilePart,
    PartKind,
    RunMetadata,
    SCHEMA_COMPLIANCE_OUTPUT,
    SCHEMA_DRG_GROUPING_OUTPUT,
    SCHEMA_EVIDENCE_SPAN,
    SCHEMA_MEDICAL_CODING_INPUT,
    SCHEMA_MEDICAL_CODING_OUTPUT,
    TextPart,
    known_schema,
    list_schemas,
    parse_part,
    parse_parts,
    parts_to_envelope_dicts,
    resolve_schema,
)


# ---------------------------------------------------------------------------
# PartKind enum
# ---------------------------------------------------------------------------


def test_part_kind_enum_values():
    assert PartKind.TEXT.value == "text"
    assert PartKind.DATA.value == "data"
    assert PartKind.FILE.value == "file"


def test_part_kind_is_str_subclass():
    assert isinstance(PartKind.TEXT, str)
    assert PartKind.TEXT == "text"


# ---------------------------------------------------------------------------
# TextPart
# ---------------------------------------------------------------------------


def test_text_part_minimal():
    p = TextPart(text="hello")
    assert p.kind == "text"
    assert p.text == "hello"


def test_text_part_serialize_roundtrip():
    p = TextPart(text="hi")
    assert p.model_dump() == {"kind": "text", "text": "hi"}


def test_parse_part_text():
    p = parse_part({"kind": "text", "text": "hi"})
    assert isinstance(p, TextPart)
    assert p.text == "hi"


def test_parse_part_text_empty():
    # Empty text is allowed (callers can decide to reject)
    p = parse_part({"kind": "text", "text": ""})
    assert p.text == ""


# ---------------------------------------------------------------------------
# DataPart
# ---------------------------------------------------------------------------


def test_data_part_minimal():
    p = DataPart(data={"schema": "icoder/MedicalCodingOutputSchema/v1", "value": {"x": 1}})
    assert p.kind == "data"
    assert p.data["schema"] == "icoder/MedicalCodingOutputSchema/v1"


def test_data_part_missing_schema_raises():
    with pytest.raises(Exception):
        DataPart(data={"value": {"x": 1}})


def test_data_part_empty_schema_raises():
    with pytest.raises(Exception):
        DataPart(data={"schema": "", "value": {}})


def test_data_part_non_dict_raises():
    with pytest.raises(Exception):
        DataPart(data="not a dict")


def test_parse_part_data():
    p = parse_part({"kind": "data", "data": {"schema": "icoder/X/v1", "value": {"a": 1}}})
    assert isinstance(p, DataPart)


def test_parse_part_data_no_schema_raises_a2a_error():
    with pytest.raises(A2AError) as ei:
        parse_part({"kind": "data", "data": {"value": {}}})
    assert ei.value.code == A2AErrorCode.INVALID_PARAMS


# ---------------------------------------------------------------------------
# FilePart rejection (Q-A9)
# ---------------------------------------------------------------------------


def test_parse_part_file_rejected():
    with pytest.raises(A2AError) as ei:
        parse_part({"kind": "file", "file": {"name": "x.png"}})
    assert ei.value.code == A2AErrorCode.INVALID_PARAMS
    assert "FilePart" in ei.value.details


def test_file_part_model_still_defined_for_type_checkers():
    # Phase 1 parses reject it, but the model exists for future use.
    p = FilePart(file={"name": "x.png"})
    assert p.kind == "file"


# ---------------------------------------------------------------------------
# parse_part — invalid inputs
# ---------------------------------------------------------------------------


def test_parse_part_non_dict_raises():
    with pytest.raises(A2AError):
        parse_part("string")


def test_parse_part_missing_kind_raises():
    with pytest.raises(A2AError) as ei:
        parse_part({"text": "x"})
    assert "kind" in ei.value.details


def test_parse_part_unknown_kind_raises():
    with pytest.raises(A2AError) as ei:
        parse_part({"kind": "audio", "url": "x"})
    assert "audio" in ei.value.details
    assert ei.value.code == A2AErrorCode.INVALID_PARAMS


def test_parse_parts_empty_list_raises():
    with pytest.raises(A2AError) as ei:
        parse_parts([])
    assert "at least one" in ei.value.details


def test_parse_parts_none_returns_empty():
    assert parse_parts(None) == []


def test_parse_parts_non_list_raises():
    with pytest.raises(A2AError):
        parse_parts({"kind": "text", "text": "x"})


def test_parse_parts_mixed_kinds():
    parts = parse_parts([
        {"kind": "text", "text": "hi"},
        {"kind": "data", "data": {"schema": "icoder/X/v1", "value": {}}},
    ])
    assert len(parts) == 2
    assert isinstance(parts[0], TextPart)
    assert isinstance(parts[1], DataPart)


def test_parts_to_envelope_dicts_roundtrip():
    parts = [TextPart(text="hi"), DataPart(data={"schema": "x", "value": {}})]
    out = parts_to_envelope_dicts(parts)
    assert out[0] == {"kind": "text", "text": "hi"}
    assert out[1]["kind"] == "data"


# ---------------------------------------------------------------------------
# RunMetadata
# ---------------------------------------------------------------------------


def test_run_metadata_minimal():
    m = RunMetadata(run_id="r1", trace_id="t1", trace_url="/api/m2a/runs/r1")
    assert m.phi_redacted is True
    assert m.production_writeback_blocked is True


def test_run_metadata_to_envelope_drops_empty():
    m = RunMetadata(run_id="r1", trace_id="t1", trace_url="/api/m2a/runs/r1")
    env = m.to_envelope()
    assert env["run_id"] == "r1"
    assert env["phi_redacted"] is True
    assert env["production_writeback_blocked"] is True
    assert env["state_history"] == []
    # Optional empty fields dropped
    assert "expert_invocations" not in env
    assert "llm_model" not in env
    assert "total_duration_ms" not in env


def test_run_metadata_to_envelope_includes_optional():
    m = RunMetadata(
        run_id="r1",
        trace_id="t1",
        trace_url="/url",
        expert_invocations=[{"expert_id": "x", "latency_ms": 100, "status": "ok"}],
        llm_model="deepseek-v4",
        total_duration_ms=1500,
        interaction_id="corr-1",
        agent_id="homepage-coding-review",
        state_history=["received", "completed"],
    )
    env = m.to_envelope()
    assert env["llm_model"] == "deepseek-v4"
    assert env["total_duration_ms"] == 1500
    assert env["expert_invocations"][0]["expert_id"] == "x"
    assert env["interaction_id"] == "corr-1"
    assert env["agent_id"] == "homepage-coding-review"
    assert env["state_history"] == ["received", "completed"]


def test_run_metadata_from_envelope_roundtrip():
    m = RunMetadata(
        run_id="r1", trace_id="t1", trace_url="/url",
        llm_model="m", total_duration_ms=100, agent_id="a",
        state_history=["received", "completed"],
    )
    env = m.to_envelope()
    m2 = RunMetadata.from_envelope(env)
    assert m2.run_id == "r1"
    assert m2.llm_model == "m"
    assert m2.total_duration_ms == 100
    assert m2.agent_id == "a"
    assert m2.state_history == ["received", "completed"]


def test_run_metadata_from_envelope_handles_missing():
    m = RunMetadata.from_envelope({})
    assert m.run_id == ""
    assert m.phi_redacted is True  # default
    assert m.production_writeback_blocked is True  # default


# ---------------------------------------------------------------------------
# DelegationMetadata
# ---------------------------------------------------------------------------


def test_delegation_metadata_minimal():
    m = DelegationMetadata(delegated_by="orchestrator-r1")
    assert m.expert_required is True
    assert m.timeout_ms == 30000


def test_delegation_metadata_to_envelope():
    m = DelegationMetadata(
        delegated_by="orchestrator-r1",
        expert_required=False,
        tool_constraints=["search_icd", "verify_code"],
        timeout_ms=15000,
    )
    env = m.to_envelope()
    assert env["delegated_by"] == "orchestrator-r1"
    assert env["expert_required"] is False
    assert env["tool_constraints"] == ["search_icd", "verify_code"]
    assert env["timeout_ms"] == 15000


def test_delegation_metadata_to_envelope_drops_empty():
    m = DelegationMetadata(delegated_by="orchestrator-r1")
    env = m.to_envelope()
    # timeout_ms=30000 is the meaningful default — keep it.
    # Only optional lists/policies are dropped when empty.
    assert env == {
        "delegated_by": "orchestrator-r1",
        "expert_required": True,
        "timeout_ms": 30000,
    }


def test_delegation_metadata_from_envelope_roundtrip():
    m = DelegationMetadata(
        delegated_by="orch-r1",
        expert_required=False,
        tool_constraints=["t1"],
        timeout_ms=5000,
        retry_policy={"max_attempts": 2},
    )
    env = m.to_envelope()
    m2 = DelegationMetadata.from_envelope(env)
    assert m2.delegated_by == "orch-r1"
    assert m2.expert_required is False
    assert m2.tool_constraints == ["t1"]
    assert m2.timeout_ms == 5000
    assert m2.retry_policy == {"max_attempts": 2}


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------


def test_list_schemas_returns_five():
    schemas = list_schemas()
    assert len(schemas) == 5


def test_all_icoder_schemas_constants():
    assert SCHEMA_MEDICAL_CODING_OUTPUT == "icoder/MedicalCodingOutputSchema/v1"
    assert SCHEMA_MEDICAL_CODING_INPUT == "icoder/MedicalCodingInputSchema/v1"
    assert SCHEMA_DRG_GROUPING_OUTPUT == "icoder/DrgGroupingOutputSchema/v1"
    assert SCHEMA_COMPLIANCE_OUTPUT == "icoder/ComplianceOutputSchema/v1"
    assert SCHEMA_EVIDENCE_SPAN == "icoder/EvidenceSpan/v1"


def test_known_schema_for_each():
    for sid in ALL_ICODER_SCHEMAS:
        assert known_schema(sid), f"{sid} should be known"


def test_known_schema_rejects_unknown():
    assert not known_schema("icoder/UnknownSchema/v1")
    assert not known_schema("not-icoder/foo")


def test_resolve_schema_returns_dict_for_known():
    schema = resolve_schema(SCHEMA_MEDICAL_CODING_OUTPUT)
    assert isinstance(schema, dict)
    assert "properties" in schema


def test_resolve_schema_returns_none_for_unknown():
    assert resolve_schema("icoder/Unknown/v1") is None


def test_resolve_schema_evidence_required_fields():
    schema = resolve_schema(SCHEMA_EVIDENCE_SPAN)
    assert "code" in schema["required"]
    assert "text" in schema["required"]


def test_resolve_schema_drg_has_drg_code():
    schema = resolve_schema(SCHEMA_DRG_GROUPING_OUTPUT)
    assert "drg_code" in schema["properties"]


def test_resolve_schema_compliance_has_violations():
    schema = resolve_schema(SCHEMA_COMPLIANCE_OUTPUT)
    assert "violations" in schema["properties"]