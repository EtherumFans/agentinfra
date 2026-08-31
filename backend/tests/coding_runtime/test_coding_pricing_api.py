"""Contract tests for the configuration-backed coding cost estimate."""

from __future__ import annotations

import os

from fastapi.testclient import TestClient


os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")


def test_pricing_is_a_range_and_does_not_require_llm_credential(monkeypatch) -> None:
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    from app.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "LLM_PRICE_INPUT_PER_1M", 1.0)
    monkeypatch.setattr(settings, "LLM_PRICE_OUTPUT_PER_1M", 2.0)
    monkeypatch.setattr(settings, "LLM_MAX_TOKENS", 4096)

    with TestClient(app) as client:
        response = client.get(
            "/api/v1/coding/pricing",
            params={"input_chars": 1200, "mode": "corti_like_fast"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["currency"] == "CNY"
    assert body["price_source"] == "server_configuration"
    assert body["billing_authoritative"] is False
    assert body["estimated_model_calls_min"] == 1
    assert body["estimated_model_calls_max"] == 1
    assert 0 < body["estimated_cost_min"] <= body["estimated_cost_max"]
    assert body["input_price_per_1m"] == 1.0
    assert body["output_price_per_1m"] == 2.0
    assert "provider-reported" in body["disclaimer"]


def test_deep_mode_reports_wider_multi_call_upper_bound(monkeypatch) -> None:
    monkeypatch.delenv("ICODER_CREDENTIAL_LLM", raising=False)
    from app.main import app

    with TestClient(app) as client:
        fast = client.get(
            "/api/v1/coding/pricing",
            params={"input_chars": 800, "mode": "corti_like_fast"},
        )
        deep = client.get(
            "/api/v1/coding/pricing",
            params={"input_chars": 800, "mode": "medcoder_deep"},
        )

    assert fast.status_code == 200
    assert deep.status_code == 200
    assert deep.json()["estimated_model_calls_min"] == 3
    assert deep.json()["estimated_model_calls_max"] == 7
    assert deep.json()["estimated_cost_max"] > fast.json()["estimated_cost_max"]


def test_pricing_rejects_unknown_mode_and_oversized_input() -> None:
    from app.main import app

    with TestClient(app) as client:
        bad_mode = client.get(
            "/api/v1/coding/pricing",
            params={"input_chars": 10, "mode": "fake-mode"},
        )
        too_large = client.get(
            "/api/v1/coding/pricing",
            params={"input_chars": 16001},
        )

    assert bad_mode.status_code == 422
    assert too_large.status_code == 422

