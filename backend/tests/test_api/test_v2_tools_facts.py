"""Phase 1.2 cycle 1 (2026-06-30) — Corti §3.2 / §13.4 FactsR™ shape parity.

Plan reference: ``docs/PHASE_1_2_FACTSR_FACTS_EXTRACTION.md``

These tests assert the wire-shape contract of
``POST /api/v2/tools/extract-facts`` relative to the Corti documentation in
``docs/corti-reverse-engineered/feature-flows/ai-studio-fact-extraction/summary.json``.

Approach
--------
``llm_service.chat`` is stubbed via ``monkeypatch.setattr`` on the endpoint
module so the fixtures never touch a real LLM. Each test stages the raw
model ``content`` (and optional ``usage``) the stub should return.
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

# Must run before importing the app / endpoint modules to:
#   1. Bypass session auth (the v2 endpoint uses Depends(get_current_user)).
#   2. Mark the LLM credential present so the 503 hospital gate is skipped
#      (the chat call itself is replaced by an injected stub).
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")
os.environ.setdefault("ICODER_CREDENTIAL_LLM", "test-fake-key-p12")


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def stub_chat(monkeypatch):
    """Inject a stub ``llm_service.chat`` that returns a staged result.

    The returned dict has a ``staged`` slot the test fills before calling
    the endpoint. ``captured`` records the messages the endpoint sent so
    assertions about prompt composition / merging are possible.
    """
    from app.api import v2_tools_facts as api_mod

    state: dict[str, Any] = {"staged": {"content": "[]", "usage": None}, "captured": {}}

    async def _fake_chat(messages, *args, **kwargs):
        state["captured"]["messages"] = list(messages)
        state["captured"]["kwargs"] = kwargs
        return state["staged"]

    monkeypatch.setattr(api_mod.llm_service, "chat", _fake_chat)
    return state


# ─── Tests ───────────────────────────────────────────────────────────


def test_v2_facts_shape_minimal(client, stub_chat):
    """#1: standard Corti-shape request → 200 with ``facts/outputLanguage/usageInfo``."""
    stub_chat["staged"] = {
        "content": (
            '[{"group": "demographics", "text": "67-year-old male.", "value": "67-year-old male."},'
            ' {"group": "chief-complaint", "text": "Recurrent chest tightness.", "value": "Recurrent chest tightness."}]'
        ),
        "usage": {"prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600},
    }
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "患者男性,67 岁,因「反复胸闷」就诊。", "type": "text"}],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert set(j.keys()) >= {"facts", "outputLanguage", "usageInfo"}
    assert isinstance(j["facts"], list) and len(j["facts"]) == 2
    first = j["facts"][0]
    for key in ("group", "text", "value"):
        assert key in first, f"missing {key} in facts[0]"
    assert first["group"] == "demographics"
    assert j["outputLanguage"] == "en-US"
    assert "creditsConsumed" in j["usageInfo"]


def test_v2_facts_output_language_echo(client, stub_chat):
    """#2: ``outputLanguage`` is echoed; "en"/"EN-US" normalised to canonical."""
    stub_chat["staged"] = {"content": "[]", "usage": None}
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "示例文本。", "type": "text"}],
        "outputLanguage": "zh-CN",
    })
    assert r.status_code == 200, r.text
    assert r.json()["outputLanguage"] == "zh-CN"

    # Empty outputLanguage → defaults to en-US.
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "示例文本。", "type": "text"}],
        "outputLanguage": "",
    })
    assert r.status_code == 200, r.text
    assert r.json()["outputLanguage"] == "en-US"


def test_v2_facts_unknown_group_passthrough(client, stub_chat):
    """#3: a non-canonical ``group`` key is forwarded, not silently dropped."""
    stub_chat["staged"] = {
        "content": '[{"group": "custom-domain-group", "text": "X", "value": "X"}]',
        "usage": None,
    }
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "示例。", "type": "text"}],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 200, r.text
    facts = r.json()["facts"]
    assert len(facts) == 1
    assert facts[0]["group"] == "custom-domain-group"


def test_v2_facts_markdown_fence_stripped(client, stub_chat):
    """#4: a model that wraps JSON in a ```json fence still parses."""
    stub_chat["staged"] = {
        "content": '```json\n[{"group": "assessment", "text": "CHF.", "value": "CHF."}]\n```',
        "usage": None,
    }
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "诊断:慢性心力衰竭。", "type": "text"}],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 200, r.text
    facts = r.json()["facts"]
    assert len(facts) == 1 and facts[0]["group"] == "assessment"


def test_v2_facts_multi_context_merged(client, stub_chat):
    """#5: multiple context blocks are all forwarded to the model (merged)."""
    stub_chat["staged"] = {"content": "[]", "usage": None}
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [
            {"text": "第一段,主诉胸痛。", "type": "text"},
            {"text": "第二段,既往高血压。", "type": "text"},
        ],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 200, r.text
    user_msg = stub_chat["captured"]["messages"][-1]["content"]
    assert "第一段" in user_msg and "第二段" in user_msg


def test_v2_facts_credits_consumed_non_negative(client, stub_chat):
    """#6: ``usageInfo.creditsConsumed`` is always a non-negative float."""
    # With usage present → derived estimate > 0.
    stub_chat["staged"] = {
        "content": '[{"group": "vital-signs", "text": "BP 180/110.", "value": "180/110"}]',
        "usage": {"total_tokens": 1000},
    }
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "血压 180/110 mmHg。", "type": "text"}],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 200, r.text
    credits = r.json()["usageInfo"]["creditsConsumed"]
    assert isinstance(credits, (int, float)) and credits >= 0.0
    assert credits == pytest.approx(0.01, abs=1e-6)

    # Without usage → 0.0, still valid shape (no 5xx).
    stub_chat["staged"] = {"content": "[]", "usage": None}
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "示例。", "type": "text"}],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 200, r.text
    assert r.json()["usageInfo"]["creditsConsumed"] == 0.0


def test_v2_facts_empty_context_rejected(client, stub_chat):
    """#7: empty input → 400 ``empty_context`` (explicit [] and whitespace-only)."""
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 400
    assert r.json()["detail"].get("error") == "empty_context"

    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "   ", "type": "text"}, {"text": "", "type": "text"}],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 400
    assert r.json()["detail"].get("error") == "empty_context"


def test_v2_facts_no_llm_credential_returns_503(client, monkeypatch):
    """#8: no ``ICODER_CREDENTIAL_LLM`` and no dev opt-in → 503 hard-fail.

    Mirrors the hospital-pilot gate on the v2 coding endpoint; the caller
    must not silently receive a fabricated facts[] array.
    """
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    monkeypatch.delenv("ICODER_ALLOW_DEGRADED_NO_KEY", raising=False)
    r = client.post("/api/v2/tools/extract-facts", json={
        "context": [{"text": "示例", "type": "text"}],
        "outputLanguage": "en-US",
    })
    assert r.status_code == 503, r.text
    assert r.json()["detail"].get("reason") == "llm_credential_missing"
