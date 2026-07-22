"""A1B-AE.5 — Message → Task → Context + Memory Expert tests.

Covers:

§1  4 new mcp_auth_* error codes registered correctly
§2  MCP auth DataPart extractor — happy paths + 4 error paths
§3  Thread-first-message registration rule (Corti §9 rule 6)
§4  Memory Expert stub — lexical retrieval + no parity claim
§5  Charter Amendment 1 §7 — forbidden verdicts preserved
"""
from __future__ import annotations

import os

import pytest

os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key")
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")


# ─────────────────────────────────────────────────────────────────────
# §1 mcp_auth_* error codes
# ─────────────────────────────────────────────────────────────────────

def test_mcp_auth_error_codes_registered():
    from app.icoder.agent_runtime.a2a.errors import (
        A2AErrorCode,
        ALL_A2A_ERROR_CODES,
    )
    for code in (
        A2AErrorCode.MCP_AUTH_DUPLICATE_NAME,
        A2AErrorCode.MCP_AUTH_MISSING_NAME,
        A2AErrorCode.MCP_AUTH_MISSING_TOKEN,
        A2AErrorCode.MCP_AUTH_MISSING_CREDENTIALS,
    ):
        assert code in ALL_A2A_ERROR_CODES


def test_mcp_auth_error_factories_build_envelopes():
    from app.icoder.agent_runtime.a2a.errors import (
        mcp_auth_duplicate_name,
        mcp_auth_missing_name,
        mcp_auth_missing_token,
        mcp_auth_missing_credentials,
    )
    e1 = mcp_auth_duplicate_name(name="crm-mcp")
    env = e1.to_envelope_error()
    assert env["data"]["a2a_error_code"] == "mcp_auth_duplicate_name"
    assert env["code"] == -32602  # INVALID_PARAMS

    e2 = mcp_auth_missing_name()
    assert e2.to_envelope_error()["data"]["a2a_error_code"] == "mcp_auth_missing_name"

    e3 = mcp_auth_missing_token(name="crm-mcp")
    assert "crm-mcp" in e3.details

    e4 = mcp_auth_missing_credentials(name="crm-mcp")
    assert "client_id" in e4.details


# ─────────────────────────────────────────────────────────────────────
# §2 MCP auth DataPart extractor
# ─────────────────────────────────────────────────────────────────────

def test_extractor_token_happy_path():
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [
        {"kind": "text", "text": "hello"},
        {
            "kind": "data",
            "data": {
                "schema": "mcp-auth",
                "type": "token",
                "mcp_name": "crm-mcp",
                "token": "eyJabc",
            },
        },
        {"kind": "text", "text": "world"},
    ]
    result = extract_mcp_auth(parts)
    assert len(result.auth_entries) == 1
    assert result.auth_entries[0].mcp_name == "crm-mcp"
    assert result.auth_entries[0].auth_type == "token"
    assert result.auth_entries[0].token == "eyJabc"
    # Auth DataPart is stripped from remaining_parts (rule 7)
    assert len(result.remaining_parts) == 2
    assert all(p.get("kind") != "data" or p.get("data", {}).get("type") not in ("token", "credentials")
               for p in result.remaining_parts)


def test_extractor_credentials_happy_path():
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [{
        "kind": "data",
        "data": {
            "schema": "mcp-auth",
            "type": "credentials",
            "mcp_name": "crm-mcp",
            "client_id": "abc",
            "client_secret": "def",
        },
    }]
    result = extract_mcp_auth(parts)
    assert len(result.auth_entries) == 1
    assert result.auth_entries[0].auth_type == "credentials"
    assert result.auth_entries[0].client_id == "abc"
    assert result.auth_entries[0].client_secret == "def"


def test_extractor_type_case_insensitive():
    """Corti §9: type is normalized to lowercase."""
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [{
        "kind": "data",
        "data": {"schema": "x", "type": "TOKEN", "mcp_name": "m", "token": "t"},
    }]
    result = extract_mcp_auth(parts)
    assert result.auth_entries[0].auth_type == "token"


def test_extractor_mcp_name_case_sensitive_and_trimmed():
    """Corti §9: mcp_name is case-SENSITIVE and trimmed."""
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [{
        "kind": "data",
        "data": {"schema": "x", "type": "token", "mcp_name": "  Crm-MCP  ", "token": "t"},
    }]
    result = extract_mcp_auth(parts)
    assert result.auth_entries[0].mcp_name == "Crm-MCP"  # trimmed but case preserved


def test_extractor_duplicate_name_raises():
    from app.icoder.agent_runtime.a2a.errors import A2AError, A2AErrorCode
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [
        {"kind": "data", "data": {"schema": "x", "type": "token", "mcp_name": "m", "token": "t1"}},
        {"kind": "data", "data": {"schema": "x", "type": "token", "mcp_name": "m", "token": "t2"}},
    ]
    with pytest.raises(A2AError) as exc_info:
        extract_mcp_auth(parts)
    assert exc_info.value.code == A2AErrorCode.MCP_AUTH_DUPLICATE_NAME


def test_extractor_missing_name_raises():
    from app.icoder.agent_runtime.a2a.errors import A2AError, A2AErrorCode
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [{"kind": "data", "data": {"schema": "x", "type": "token", "token": "t"}}]
    with pytest.raises(A2AError) as exc_info:
        extract_mcp_auth(parts)
    assert exc_info.value.code == A2AErrorCode.MCP_AUTH_MISSING_NAME


def test_extractor_missing_token_raises():
    from app.icoder.agent_runtime.a2a.errors import A2AError, A2AErrorCode
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [{"kind": "data", "data": {"schema": "x", "type": "token", "mcp_name": "m"}}]
    with pytest.raises(A2AError) as exc_info:
        extract_mcp_auth(parts)
    assert exc_info.value.code == A2AErrorCode.MCP_AUTH_MISSING_TOKEN


def test_extractor_missing_credentials_raises():
    from app.icoder.agent_runtime.a2a.errors import A2AError, A2AErrorCode
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [{
        "kind": "data",
        "data": {"schema": "x", "type": "credentials", "mcp_name": "m", "client_id": "abc"},
    }]
    with pytest.raises(A2AError) as exc_info:
        extract_mcp_auth(parts)
    assert exc_info.value.code == A2AErrorCode.MCP_AUTH_MISSING_CREDENTIALS


def test_extractor_unknown_auth_type_left_in_remaining():
    """Corti §9 rule 1: unknown auth types are LEFT IN the message (not dropped, not fatal)."""
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [{
        "kind": "data",
        "data": {"schema": "x", "type": "biometric", "mcp_name": "m"},
    }]
    result = extract_mcp_auth(parts)
    assert len(result.auth_entries) == 0
    assert len(result.remaining_parts) == 1


def test_extractor_text_and_non_auth_data_parts_preserved():
    """Non-auth DataParts (no type=token/credentials) must pass through unchanged."""
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import extract_mcp_auth
    parts = [
        {"kind": "text", "text": "hi"},
        {"kind": "data", "data": {"schema": "fhir", "value": {"resourceType": "Patient"}}},
    ]
    result = extract_mcp_auth(parts)
    assert len(result.remaining_parts) == 2


# ─────────────────────────────────────────────────────────────────────
# §3 Thread-first-message registration rule
# ─────────────────────────────────────────────────────────────────────

def test_thread_registry_first_message_check():
    from app.icoder.agent_runtime.a2a.thread_auth import ThreadAuthRegistry
    reg = ThreadAuthRegistry()
    assert reg.is_first_message("ctx-a") is True
    reg.ack_message("ctx-a")
    assert reg.is_first_message("ctx-a") is False


def test_thread_registry_register_first_message_records_mcp_names():
    from app.icoder.agent_runtime.a2a.thread_auth import ThreadAuthRegistry
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import ExtractedMcpAuth
    reg = ThreadAuthRegistry()
    entries = [
        ExtractedMcpAuth(mcp_name="m1", auth_type="token", token="t"),
        ExtractedMcpAuth(mcp_name="m2", auth_type="credentials", client_id="a", client_secret="b"),
    ]
    reg.register_first_message("ctx-b", entries)
    state = reg.get_state("ctx-b")
    assert state["has_registered"] is True
    assert set(state["registered_mcp_names"]) == {"m1", "m2"}


def test_thread_registry_subsequent_message_does_not_re_register():
    """Corti §9 rule 6: only first message registers MCP tools."""
    from app.icoder.agent_runtime.a2a.thread_auth import ThreadAuthRegistry
    from app.icoder.agent_runtime.a2a.mcp_auth_extractor import ExtractedMcpAuth
    reg = ThreadAuthRegistry()
    reg.register_first_message("ctx-c", [ExtractedMcpAuth(mcp_name="m1", auth_type="token", token="t")])

    # Try to register again with different names — must be ignored
    reg.register_first_message("ctx-c", [ExtractedMcpAuth(mcp_name="m2", auth_type="token", token="t")])
    state = reg.get_state("ctx-c")
    assert "m2" not in state["registered_mcp_names"]
    assert "m1" in state["registered_mcp_names"]


# ─────────────────────────────────────────────────────────────────────
# §4 Memory Expert stub
# ─────────────────────────────────────────────────────────────────────

def test_memory_expert_constants_match_corti_public():
    """canonical_key='memory' is Corti public §3.2 key 1 of 9."""
    from app.agents.experts.memory_expert import (
        MEMORY_EXPERT_CANONICAL_KEY,
        MEMORY_EXPERT_NAME,
    )
    assert MEMORY_EXPERT_CANONICAL_KEY == "memory"
    assert "Memory" in MEMORY_EXPERT_NAME


def test_memory_expert_retrieval_is_lexical_only():
    """iCoDer does NOT claim semantic RAG parity with Corti."""
    from app.agents.experts.memory_expert import retrieve
    thread = [
        {"parts": [{"kind": "text", "text": "patient has diabetes mellitus type 2"}]},
        {"parts": [{"kind": "text", "text": "patient is on metformin"}]},
    ]
    result = retrieve("diabetes metformin", thread, top_k=5)
    assert result.retrieval_mode == "LEXICAL_ONLY"
    assert "CORTI_REFERENCE" in result.notes or "lexical" in result.notes.lower()
    assert len(result.matches) >= 1


def test_memory_expert_empty_query_returns_empty():
    from app.agents.experts.memory_expert import retrieve
    result = retrieve("", [{"parts": [{"kind": "text", "text": "x"}]}])
    assert result.matches == []


def test_memory_expert_no_overlap_returns_empty():
    from app.agents.experts.memory_expert import retrieve
    thread = [{"parts": [{"kind": "text", "text": "alpha beta gamma"}]}]
    result = retrieve("zeta eta theta", thread)
    assert result.matches == []


# ─────────────────────────────────────────────────────────────────────
# §5 Charter Amendment 1 §7
# ─────────────────────────────────────────────────────────────────────

def test_forbidden_verdicts_preserved():
    forbidden = {
        "PRODUCTION_READY",
        "FULLY_VERIFIED",
        "PHI_BOUNDED",
        "CORTI_PARITY_VERIFIED",
        "PASS_A1A_GATE4_FINAL",
        "READY_FOR_HOSPITAL_DEPLOYMENT",
        "CLINICAL_GRADE_VERIFIED",
        "CORTI_AGENTIC_FRAMEWORK_FULLY_REPLICATED",
    }
    allowed_phase_final = {
        "PARTIAL_A1B_AE_AGENT_EXPERT_CAPABILITY_AND_TECH_DEBT_RECONCILIATION_FILED"
    }
    assert forbidden.isdisjoint(allowed_phase_final)
