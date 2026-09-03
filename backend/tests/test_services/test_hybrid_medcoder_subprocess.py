"""Tests for SubprocessMedCodERRetriever and its integration with HybridCodingAdapter.

Covers Commit 5: the subprocess client + the env-var / platform-based
selection in HybridCodingAdapter._get_retriever.
"""
import asyncio
import multiprocessing
import os
import threading
import time

import pytest

from icoder_runtime.providers.medical_coding.medcoder_retriever import (
    MedCodERRetrieverWorker,
    SubprocessMedCodERRetriever,
)


# ── Picklable test doubles ──


class FakeRetriever:
    """Drop-in retriever for the worker process. No FAISS / BGE-M3."""

    def __init__(self):
        self.ensure_loaded_calls = 0
        self.retrieve_calls: list[tuple[str, int | None]] = []

    def ensure_loaded(self) -> None:
        self.ensure_loaded_calls += 1

    def retrieve_sync(self, disease: str, top_k: int | None = None, expand_synonyms: bool = True) -> list:
        self.retrieve_calls.append((disease, top_k))
        return [{"code": f"MOCK-{disease}", "score": 0.99}]


def _spawn_worker_process(retriever: FakeRetriever):
    """Spawn a MedCodERRetrieverWorker.run process with a pre-built retriever."""
    q_in: multiprocessing.Queue = multiprocessing.Queue()
    q_out: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=MedCodERRetrieverWorker.run,
        args=(q_in, q_out, "unused", retriever),
        daemon=True,
    )
    proc.start()
    return proc, q_in, q_out


# ── SubprocessMedCodERRetriever unit tests ──


def _make_subprocess_with_fake_worker():
    """Create a SubprocessMedCodERRetriever whose worker uses a FakeRetriever.

    We bypass the normal spawn (which would build a real
    MedCodERRetriever) by replacing the queues + process after __init__.
    """
    fake = FakeRetriever()
    q_in: multiprocessing.Queue = multiprocessing.Queue()
    q_out: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=MedCodERRetrieverWorker.run,
        args=(q_in, q_out, "unused", fake),
        daemon=True,
    )
    proc.start()
    try:
        startup_id, startup_payload = q_out.get(timeout=30.0)
    except Exception as exc:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2)
        raise TimeoutError(
            "fake MedCodER worker did not complete startup within 30s "
            f"(alive={proc.is_alive()}, exitcode={proc.exitcode})"
        ) from exc
    if startup_id != MedCodERRetrieverWorker.STARTUP_READY_ID:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2)
        raise RuntimeError(
            f"fake MedCodER worker startup failed: {startup_id!r} "
            f"{startup_payload!r}"
        )
    assert startup_payload == {"ready": True}
    client = SubprocessMedCodERRetriever.__new__(SubprocessMedCodERRetriever)
    client.index_dir = "unused"
    client.timeout = 5.0
    client._q_in = q_in
    client._q_out = q_out
    client._proc = proc
    client._next_id = 0
    client._lock = threading.Lock()
    client._closed = False
    return client, fake, proc


@pytest.mark.asyncio
async def test_subprocess_retriever_round_trip_returns_candidates():
    """A retrieve_async call returns the candidates produced by the worker."""
    client, _fake, proc = _make_subprocess_with_fake_worker()
    try:
        cands = await client.retrieve_async("心衰", top_k=5)
        # The response is keyed on the request disease, so we can
        # verify the right call was made without observing the
        # worker's per-process state.
        assert cands == [{"code": "MOCK-心衰", "score": 0.99}]
    finally:
        client.close()
        proc.join(timeout=2)
        assert not proc.is_alive()


@pytest.mark.asyncio
async def test_subprocess_retriever_worker_stays_alive_across_requests():
    """Worker is reused across multiple requests (FAISS index stays loaded)."""
    client, _fake, proc = _make_subprocess_with_fake_worker()
    try:
        for d in ("心衰", "高血压", "糖尿病"):
            cands = await client.retrieve_async(d, top_k=3)
            assert cands[0]["code"] == f"MOCK-{d}"
        assert proc.is_alive()
    finally:
        client.close()
        proc.join(timeout=2)


@pytest.mark.asyncio
async def test_subprocess_retriever_returns_empty_on_dead_worker():
    """If the worker has died, retrieve_async returns [] and logs a warning."""
    client, _fake, proc = _make_subprocess_with_fake_worker()
    # Kill the worker first
    proc.terminate()
    proc.join(timeout=2)
    assert not proc.is_alive()

    # Now ask for something — should not raise, should return []
    cands = await client.retrieve_async("心衰", top_k=5)
    assert cands == []


@pytest.mark.asyncio
async def test_subprocess_retriever_close_terminates_worker():
    """close() sends sentinel and joins the worker."""
    client, _fake, proc = _make_subprocess_with_fake_worker()
    assert proc.is_alive()
    client.close()
    proc.join(timeout=3)
    assert not proc.is_alive()


@pytest.mark.asyncio
async def test_subprocess_retriever_retrieve_sync_via_inline_path():
    """retrieve_sync inside a running event loop uses the inline (queue) path."""
    client, _fake, proc = _make_subprocess_with_fake_worker()
    try:
        # We're inside pytest-asyncio, so get_event_loop returns a running one.
        cands = client.retrieve_sync("高血压", top_k=2)
        assert cands == [{"code": "MOCK-高血压", "score": 0.99}]
    finally:
        client.close()
        proc.join(timeout=2)


# ── HybridCodingAdapter integration ──


def test_get_retriever_uses_subprocess_when_env_var_set(monkeypatch):
    """MEDCODER_SUBPROCESS=1 → adapter creates SubprocessMedCodERRetriever."""
    monkeypatch.setenv("MEDCODER_SUBPROCESS", "1")
    monkeypatch.setenv("MEDCODER_ALLOW_UNSAFE_WINDOWS_BGE", "1")
    # This is a constructor-selection test with both implementations replaced
    # by no-op classes; it never imports Torch/FAISS or starts a worker. Remove
    # the operator kill switch only within this test so the routing branch is
    # observable under the full suite's safety environment.
    monkeypatch.delenv("ICODER_DISABLE_NATIVE_MEDCODER", raising=False)

    from icoder_runtime.providers.medical_coding.hybrid_adapter import (
        HybridCodingAdapter,
    )
    from icoder_runtime.providers.medical_coding.medcoder_retriever import (
        MedCodERRetriever,
        SubprocessMedCodERRetriever,
    )

    # Use a mock LLM gateway so we don't need real network access.
    adapter = HybridCodingAdapter(gateway=_MockGateway(), mode="medcoder")
    # Don't actually call _get_retriever yet — it spawns a real worker
    # which loads FAISS. We patch MedCodERRetriever and SubprocessMedCodERRetriever
    # to a no-op class that records which one was selected.
    created = {"subprocess": False, "inprocess": False}

    class FakeSubprocess:
        def __init__(self, *args, **kwargs):
            created["subprocess"] = True
            self._proc = type("P", (), {"is_alive": lambda s: True, "join": lambda s, **kw: None})()

    class FakeInprocess:
        def __init__(self, *args, **kwargs):
            created["inprocess"] = True

    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.SubprocessMedCodERRetriever",
        FakeSubprocess,
    )
    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.MedCodERRetriever",
        FakeInprocess,
    )
    # Re-import so the adapter sees the patched classes
    import importlib
    import icoder_runtime.providers.medical_coding.hybrid_adapter as ha
    importlib.reload(ha)
    adapter = ha.HybridCodingAdapter(gateway=_MockGateway(), mode="medcoder")

    # M1: retriever selection moved to MedCodERStrategy; reach it through
    # the adapter's owned strategy.
    retriever = adapter._strategy._get_retriever()
    assert created["subprocess"] is True
    assert created["inprocess"] is False
    assert isinstance(retriever, FakeSubprocess)


def test_get_retriever_uses_inprocess_when_unix_and_no_env(monkeypatch):
    """On non-Windows with no env var, adapter creates in-process MedCodERRetriever."""
    if os.name == "nt":
        pytest.skip("In-process selection is platform-specific; this test runs on Unix")
    monkeypatch.delenv("MEDCODER_SUBPROCESS", raising=False)

    from icoder_runtime.providers.medical_coding.medcoder_retriever import (
        MedCodERRetriever,
        SubprocessMedCodERRetriever,
    )

    created = {"subprocess": False, "inprocess": False}

    class FakeSubprocess:
        def __init__(self, *args, **kwargs):
            created["subprocess"] = True

    class FakeInprocess:
        def __init__(self, *args, **kwargs):
            created["inprocess"] = True

    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.SubprocessMedCodERRetriever",
        FakeSubprocess,
    )
    monkeypatch.setattr(
        "icoder_runtime.providers.medical_coding.medcoder_retriever.MedCodERRetriever",
        FakeInprocess,
    )
    import importlib
    import icoder_runtime.providers.medical_coding.hybrid_adapter as ha
    importlib.reload(ha)
    adapter = ha.HybridCodingAdapter(gateway=_MockGateway(), mode="medcoder")

    # M1: retriever selection moved to MedCodERStrategy; reach it through
    # the adapter's owned strategy.
    retriever = adapter._strategy._get_retriever()
    assert created["subprocess"] is False
    assert created["inprocess"] is True
    assert isinstance(retriever, FakeInprocess)


# ── Test fixtures ──


class _MockGateway:
    """Minimal mock LLM gateway for the integration tests."""
    name = "mock"

    async def generate(self, *args, **kwargs):
        # Return a generic valid response — _medcoder_pipeline will use it.
        return {
            "content": '{"items": []}',
            "model": "mock",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
