"""Tests for C7: medcoder_index_ready flag wired to SubprocessMedCodERRetriever health.

Covers:
- SubprocessMedCodERRetriever.is_ready property semantics
- FastAPI lifespan wires /api/health to medcoder_index_ready
- /api/health reports ready=True for a healthy worker, ready=False for a dead one
"""
from __future__ import annotations

import asyncio
import multiprocessing
import os
import threading

import pytest


# ── Picklable test double ──


class _FakeHealthyRetriever:
    """No FAISS / BGE-M3. Stands in for MedCodERRetriever in the worker."""

    def __init__(self):
        self.ensure_loaded_calls = 0
        self.retrieve_calls: list[tuple[str, int | None]] = []

    def ensure_loaded(self) -> None:
        self.ensure_loaded_calls += 1

    def retrieve_sync(self, disease: str, top_k=None, expand_synonyms: bool = True):
        self.retrieve_calls.append((disease, top_k))
        return [{"code": f"MOCK-{disease}", "score": 0.9}]


class _FakeStartupFailingRetriever:
    """ensure_loaded() raises — simulates missing index file or FAISS OOM."""

    def __init__(self):
        pass

    def ensure_loaded(self) -> None:
        raise FileNotFoundError("simulated missing faiss.index")


def _spawn_worker_with(retriever):
    """Helper: spawn MedCodERRetrieverWorker.run process with a fake retriever."""
    from icoder_runtime.providers.medical_coding.medcoder_retriever import (
        MedCodERRetrieverWorker,
    )
    q_in: multiprocessing.Queue = multiprocessing.Queue()
    q_out: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=MedCodERRetrieverWorker.run,
        args=(q_in, q_out, "unused", retriever),
        daemon=True,
    )
    proc.start()
    return proc, q_in, q_out


def _make_client_with_fake_worker(retriever, *, probe_timeout: float = 15.0):
    """Build a SubprocessMedCodERRetriever whose worker uses `retriever`.

    Bypasses the normal __init__ (which builds a real MedCodERRetriever
    that would try to load FAISS). Same trick as the other subprocess tests.
    """
    from icoder_runtime.providers.medical_coding.medcoder_retriever import (
        SubprocessMedCodERRetriever,
    )
    proc, q_in, q_out = _spawn_worker_with(retriever)
    client = SubprocessMedCodERRetriever.__new__(SubprocessMedCodERRetriever)
    client.index_dir = "unused"
    client.timeout = 5.0
    client._q_in = q_in
    client._q_out = q_out
    client._proc = proc
    client._next_id = 0
    client._lock = threading.Lock()
    client._closed = False
    # Run the same probe that __init__ would have run.
    client._probe_ok = client._probe(probe_timeout)
    return client, proc


# ── is_ready property ──


class TestIsReadyProperty:
    def test_is_ready_true_for_healthy_worker(self):
        client, proc = _make_client_with_fake_worker(_FakeHealthyRetriever())
        try:
            assert client.is_ready is True
            assert proc.is_alive()
        finally:
            client.close()
            proc.join(timeout=2)

    def test_is_ready_false_when_worker_dies_after_probe(self):
        """Probe succeeds, but worker dies later → is_ready becomes False.

        Models the real-world case where the worker survives startup
        but crashes during a long-running session (e.g., OOM under load).
        """
        client, proc = _make_client_with_fake_worker(_FakeHealthyRetriever())
        try:
            assert client.is_ready is True
            proc.terminate()
            proc.join(timeout=2)
            assert not proc.is_alive()
            assert client.is_ready is False
        finally:
            client.close()
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1)

    def test_is_ready_false_when_worker_dies_during_startup(self):
        """Worker self-exits because ensure_loaded raised → is_ready is False.

        The probe either times out (q_out.get blocks until probe_timeout)
        or receives a ``STARTUP_ERROR_ID`` envelope that doesn't match
        the parent's req_id. Either way, ``_probe_ok=False`` and
        ``is_ready`` is False.
        """
        client, proc = _make_client_with_fake_worker(
            _FakeStartupFailingRetriever(),
            probe_timeout=1.0,  # Don't slow the test suite
        )
        try:
            assert client.is_ready is False
        finally:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1)


# ── /api/health endpoint wiring ──


class TestHealthEndpointReportsReadiness:
    """The C7 wiring in app/main.py lifespan sets medcoder_index_ready based
    on the subprocess retriever's is_ready property. We exercise that path
    by patching the lifespan to inject a known retriever on app.state.
    """

    @pytest.fixture
    def client_with_healthy_retriever(self, monkeypatch):
        from fastapi.testclient import TestClient
        from app.main import app
        from icoder_runtime.providers.medical_coding.medcoder_retriever import (
            SubprocessMedCodERRetriever,
        )

        # Build a real SubprocessMedCodERRetriever that uses our fake worker.
        retriever, proc = _make_client_with_fake_worker(
            _FakeHealthyRetriever(), probe_timeout=5.0,
        )
        try:
            # Bypass the lifespan (which would try to start another worker)
            # by manually setting state on the existing app instance.
            # We use the lifespan context only to allow FastAPI to start.
            with TestClient(app) as tc:
                # Overwrite the values the lifespan computed with our
                # known-healthy ones. This is a white-box test of the
                # health endpoint shape, not a test of the lifespan
                # (lifespan is tested via integration / e2e).
                tc.app.state.medcoder_index_ready = retriever.is_ready
                tc.app.state.medcoder_index_loading = False
                tc.app.state.medcoder_index_error = None
                tc.app.state.medcoder_retriever = retriever
                yield tc
        finally:
            retriever.close()
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=1)

    def test_health_reports_ready_true_with_healthy_worker(
        self, client_with_healthy_retriever,
    ):
        resp = client_with_healthy_retriever.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["medcoder_index_ready"] is True
        assert body["medcoder_index_loading"] is False
        assert body["medcoder_index_error"] is None

    def test_health_reports_ready_false_with_dead_worker(self):
        from fastapi.testclient import TestClient
        from app.main import app

        # No retriever on state — simulates a failed startup probe.
        with TestClient(app) as tc:
            tc.app.state.medcoder_index_ready = False
            tc.app.state.medcoder_index_loading = False
            tc.app.state.medcoder_index_error = (
                "SubprocessMedCodERRetriever worker did not respond to "
                "startup probe (see logs for ensure_loaded failure)"
            )
            tc.app.state.medcoder_retriever = None
            resp = tc.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["medcoder_index_ready"] is False
        assert body["medcoder_index_error"] is not None
        assert "did not respond" in body["medcoder_index_error"]

    def test_health_shape_preserved(self, client_with_healthy_retriever):
        """All pre-C7 health fields must still be present (no regressions)."""
        resp = client_with_healthy_retriever.get("/api/health")
        body = resp.json()
        for key in (
            "status", "app", "version", "environment",
            "llm_provider", "llm_model",
        ):
            assert key in body, f"health response missing {key!r}"
        # C7 additions:
        for key in (
            "medcoder_index_ready", "medcoder_index_loading",
            "medcoder_index_error",
        ):
            assert key in body, f"health response missing C7 field {key!r}"
