"""API tests — auth gate, run -> report (PHI-safe), role-gated human review, Agent Card.

Uses the deterministic provider (conftest deletes ICODER_CREDENTIAL_LLM) so the whole
HTTP surface runs with no external model.
"""
from conftest import AUTH
from sample_data import SAMPLE_TEXT

AGENT_ID = "icoder/homepage-coding-review-agent"
DRG_AGENT_ID = "icoder/drg-grouping-review-agent"
REVENUE_AGENT_ID = "icoder/revenue-compliance-review-agent"


def test_run_requires_bearer_token(client):
    r = client.post("/api/coding-review/run", json={"text": SAMPLE_TEXT})
    assert r.status_code == 401


def test_run_then_fetch_report_is_phi_safe(client):
    r = client.post("/api/coding-review/run", json={"text": SAMPLE_TEXT}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    run_id = body["run_id"]
    assert body["production_writeback_blocked"] is True

    code_set = {c["code"] for c in body["codes"]}
    cand_set = {c["code"] for c in body["candidates"]}
    assert "I50.900" in code_set
    assert "M80.900" in cand_set
    assert "45.1600x001" in cand_set
    assert code_set.isdisjoint(cand_set)

    # JSON report
    rj = client.get(f"/api/coding-review/{run_id}/report", headers=AUTH)
    assert rj.status_code == 200
    assert rj.json()["run_id"] == run_id

    # HTML report — de-identified, but the codes are present
    rh = client.get(f"/api/coding-review/{run_id}/report", params={"format": "html"}, headers=AUTH)
    assert rh.status_code == 200
    html = rh.text
    assert "张三" not in html
    assert "13800001111" not in html
    assert "I50.900" in html


def test_human_review_is_role_gated_and_reviewer_from_token(client):
    run_id = client.post(
        "/api/coding-review/run", json={"text": SAMPLE_TEXT}, headers=AUTH
    ).json()["run_id"]

    payload = {"decision": "accept", "code": "I50.900"}

    # reviewer role -> forbidden
    forbidden = client.post(
        f"/api/coding-review/{run_id}/human-review",
        json=payload,
        headers={"Authorization": "Bearer demo:reviewer"},
    )
    assert forbidden.status_code == 403

    # coder role -> ok, reviewer_role injected from the token (not the body)
    ok = client.post(
        f"/api/coding-review/{run_id}/human-review", json=payload, headers=AUTH
    )
    assert ok.status_code == 200
    assert ok.json()["human_review"]["reviewer_role"] == "coder"


def test_agent_discovery_and_card(client):
    listing = client.get("/agents", headers=AUTH)
    assert listing.status_code == 200
    ids = {a["id"] for a in listing.json()["agents"]}
    assert AGENT_ID in ids
    assert DRG_AGENT_ID in ids          # the second thin Agent is discoverable too
    assert REVENUE_AGENT_ID in ids      # the capstone (4-domain) Agent too

    card = client.get(f"/agents/{AGENT_ID}/card", headers=AUTH)
    assert card.status_code == 200
    data = card.json()
    assert data["x-icoder"]["deployment"] == "on-prem"
    assert data["x-icoder"]["production_writeback_blocked"] is True
    assert data["capabilities"]["humanInTheLoop"] is True


def test_drg_agent_run_via_api(client):
    """Same endpoint, second Agent: composite ruleset + enriched DRG/DIP route."""
    r = client.post(
        "/api/coding-review/run",
        json={"text": SAMPLE_TEXT, "agent_id": DRG_AGENT_ID},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["agent_id"] == DRG_AGENT_ID
    assert body["compliance"]["rule_set"] == "medical_coding+drg_dip"
    drg = body["drg_route"]
    assert drg["mdc"] == "MDCF"
    assert drg["dip_code"] == "DIP-I50.900"
    assert any(h["rule_id"] == "DG-R004" for h in body["compliance"]["hits"])


def test_unknown_agent_card_is_404(client):
    r = client.get("/agents/icoder/nope/card", headers=AUTH)
    assert r.status_code == 404


def test_offline_run_signals_deterministic_local(client):
    """No key (conftest default) -> deterministic offline fallback. It is surfaced via
    versions.model_version so the UI can show the offline banner — and it is a 200, not a
    503: this slice degrades rather than refusing. The trace is the classic 7-stage one
    (an extract stage, no research tool events)."""
    r = client.post("/api/coding-review/run", json={"text": SAMPLE_TEXT}, headers=AUTH)
    assert r.status_code == 200
    body = r.json()
    assert body["versions"]["model_version"] == "deterministic-local"
    stage_names = [s["stage"] for s in body["stages"]]
    assert "extract" in stage_names
    assert "tool" not in stage_names  # no LLM research trace on the offline path


def test_run_503_when_llm_endpoint_unavailable(client, monkeypatch):
    """With a chat-capable provider whose endpoint errors, /run is a clean 503
    llm_unavailable — never a fabricated report — and leaks no credential material."""
    import icoder.api.routes_coding_review as mod
    from icoder.runtime.gateway import LLMGateway, ProviderError

    class _Raising:
        name = "fake"
        model = "fake-1"

        def chat(self, messages, tools=None, tool_choice=None):
            raise ProviderError("LLM endpoint https://unreachable.invalid is unreachable: ConnectError")

    monkeypatch.setattr(mod.LLMGateway, "from_env",
                        classmethod(lambda cls, lexicon: LLMGateway(_Raising())))
    r = client.post("/api/coding-review/run", json={"text": SAMPLE_TEXT}, headers=AUTH)
    assert r.status_code == 503
    assert r.json()["detail"]["code"] == "llm_unavailable"
    assert "Bearer" not in r.text and "api_key" not in r.text


def test_revenue_agent_run_via_api(client):
    """Capstone Agent over the same endpoint: 4-domain composite gate, route unchanged."""
    r = client.post(
        "/api/coding-review/run",
        json={"text": SAMPLE_TEXT, "agent_id": REVENUE_AGENT_ID},
        headers=AUTH,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["agent_id"] == REVENUE_AGENT_ID
    assert body["compliance"]["rule_set"] == \
        "medical_coding+drg_dip+insurance_audit+document_evidence"
    ids = {h["rule_id"] for h in body["compliance"]["hits"]}
    assert "IA-R002" in ids             # insurance_audit domain is live end-to-end
    assert body["compliance"]["passed"] is True
    assert body["drg_route"]["dip_code"] == "DIP-I50.900"
