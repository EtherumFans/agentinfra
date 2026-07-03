"""POST /api/agents/{id}/run — the tool-surface agent run endpoint (offline-guarded).

The tool agents require an external LLM (prose synthesis has no deterministic fallback), so
the no-key path is a clean 503 — never a fabricated report. These tests cover the auth / 404 /
503 contract with NO key (the default in conftest), then monkeypatch a chat-capable fake
provider for the 200 and ProviderError (503 llm_unavailable) paths. They also assert the tool
agent's Agent Card advertises surface=="tool", the right run endpoint, and no human-in-the-loop.
"""
import icoder.api.routes_agent_run as mod
from sample_data import SAMPLE_TEXT

from icoder.runtime.gateway import ChatResult, ProviderError, ToolCall

AUTH = {"Authorization": "Bearer demo:coder"}
TOOL_ID = "icoder/code-validation-agent"


class _FakeGateway:
    def __init__(self, provider):
        self.provider = provider


def _patch_provider(monkeypatch, provider):
    monkeypatch.setattr(mod.LLMGateway, "from_env", classmethod(lambda cls, lexicon: _FakeGateway(provider)))


class _ChatFake:
    name = "fake"
    model = "fake-1"

    def __init__(self, script):
        self._script = list(script)

    def chat(self, messages, tools=None, tool_choice=None):
        if self._script:
            return self._script.pop(0)
        return ChatResult(content="done", tool_calls=[])


class _Raising:
    name = "fake"
    model = "fake-1"

    def chat(self, messages, tools=None, tool_choice=None):
        raise ProviderError("LLM endpoint https://unreachable.invalid is unreachable: ConnectError")


# ---- auth / 404 / 422 / 503-no-key: all hold with NO external key (conftest default) ----

def test_no_token_401(client):
    r = client.post(f"/api/agents/{TOOL_ID}/run", json={"text": SAMPLE_TEXT})
    assert r.status_code == 401


def test_no_key_503_credential_missing(client):
    r = client.post(f"/api/agents/{TOOL_ID}/run", json={"text": SAMPLE_TEXT}, headers=AUTH)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "llm_credential_missing"


def test_unknown_agent_404(client):
    r = client.post("/api/agents/icoder/nope-agent/run", json={"text": SAMPLE_TEXT}, headers=AUTH)
    assert r.status_code == 404


def test_non_tool_surface_404(client):
    # extract + coding-review agents own their own endpoints; they must 404 here.
    for aid in ("icoder/diagnostic-entity-extractor-agent", "icoder/homepage-coding-review-agent"):
        r = client.post(f"/api/agents/{aid}/run", json={"text": SAMPLE_TEXT}, headers=AUTH)
        assert r.status_code == 404, aid


def test_empty_text_422(client):
    r = client.post(f"/api/agents/{TOOL_ID}/run", json={"text": "   "}, headers=AUTH)
    assert r.status_code == 422


# ---- 200 + 503-unavailable: monkeypatch a chat-capable provider ----

def test_run_200_returns_report_stages_redaction(client, monkeypatch):
    provider = _ChatFake([
        ChatResult(tool_calls=[ToolCall(id="c1", name="verify", arguments={"code": "I50.900"})]),
        ChatResult(content="# 校验小结\n**已核：** 1", tool_calls=[]),
    ])
    _patch_provider(monkeypatch, provider)
    r = client.post(f"/api/agents/{TOOL_ID}/run", json={"text": SAMPLE_TEXT}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "fake"
    assert body["report"].startswith("# 校验小结")
    assert [s["tool"] for s in body["stages"]] == ["verify"]
    # PHI redacted server-side before the model; the returned de-identified text proves it.
    assert body["redaction"]["spans"] >= 3
    assert "张三" not in body["redaction"]["text"]


def test_provider_error_503_unavailable(client, monkeypatch):
    _patch_provider(monkeypatch, _Raising())
    r = client.post(f"/api/agents/{TOOL_ID}/run", json={"text": SAMPLE_TEXT}, headers=AUTH)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "llm_unavailable"
    # the error must not leak any credential material
    assert "Bearer" not in r.text and "api_key" not in r.text


# ---- Agent Card: tool surface advertised declaratively ----

def test_tool_agent_card_surface(client):
    card = client.get(f"/agents/{TOOL_ID}/card", headers=AUTH).json()
    assert card["x-icoder"]["surface"] == "tool"
    assert card["endpoints"]["run"] == f"/api/agents/{TOOL_ID}/run"
    assert card["capabilities"]["humanInTheLoop"] is False
    assert card["x-icoder"]["production_writeback_blocked"] is True
