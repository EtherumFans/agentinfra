"""Embedded Assistant must never publish a successful placeholder bundle."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_compiled_embedded_bundle_is_served() -> None:
    from app.main import app

    with TestClient(app) as client:
        response = client.get("/api/embedded/assistant.js")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/javascript")
    assert "customElements.define" in response.text
    assert "embedded_bundle_missing" not in response.text


def test_missing_embedded_bundle_fails_closed(monkeypatch, tmp_path) -> None:
    from app.api import embedded
    from app.main import app

    monkeypatch.setattr(embedded, "_DIST_JS", tmp_path / "missing-assistant.js")
    with TestClient(app) as client:
        response = client.get("/api/embedded/assistant.js")

    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-icoder-error"] == "embedded_bundle_missing"
    assert response.headers["content-type"].startswith("application/javascript")
    assert "verified release bundle is missing" in response.text

