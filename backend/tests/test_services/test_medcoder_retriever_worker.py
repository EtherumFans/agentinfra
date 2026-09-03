"""Unit tests for MedCodERRetrieverWorker — the subprocess isolation layer.

Covers Commit 4: the worker runs in its own process, owns a retriever,
and translates ``(req_id, disease, top_k)`` request tuples into
``(req_id, candidates)`` response tuples — with the FAISS/BGE-M3
imports happening only inside the worker process, never in the parent.
"""
import multiprocessing
import sys
import time

import pytest

from icoder_runtime.providers.medical_coding.medcoder_retriever import (
    MedCodERRetrieverWorker,
)


# ── Test doubles ──


class FakeRetriever:
    """Picklable drop-in retriever — no FAISS/BGE-M3 dependency.

    Uses ``multiprocessing.Value`` for counters so the parent process
    can observe the worker's call counts across the process boundary
    (a regular int attribute is per-process and stays at 0 in the
    parent after pickling).
    """

    def __init__(self, responses_by_disease: dict | None = None, raise_on: str | None = None):
        self._responses = responses_by_disease or {}
        self._raise_on = raise_on
        # Shared counters so the parent can observe worker activity.
        self._ensure_loaded_counter = multiprocessing.Value("i", 0)
        self._retrieve_counter = multiprocessing.Value("i", 0)
        # Per-process call log (worker's view only — useful for debugging).
        self._retrieve_calls: list[tuple[str, int | None]] = []

    def ensure_loaded(self) -> None:
        with self._ensure_loaded_counter.get_lock():
            self._ensure_loaded_counter.value += 1

    def retrieve_sync(self, disease: str, top_k: int | None = None, expand_synonyms: bool = True) -> list:
        self._retrieve_calls.append((disease, top_k))
        with self._retrieve_counter.get_lock():
            self._retrieve_counter.value += 1
        if self._raise_on is not None and disease == self._raise_on:
            raise RuntimeError(f"simulated retrieve failure for {disease!r}")
        return list(self._responses.get(disease, []))


class FailingStartupRetriever:
    """Picklable retriever that fails its ensure_loaded() call."""
    def ensure_loaded(self) -> None:
        raise FileNotFoundError("index missing")
    def retrieve_sync(self, disease: str, top_k: int | None = None, expand_synonyms: bool = True) -> list:
        return []


# ── Test helpers ──


def _spawn_worker(
    retriever: FakeRetriever,
    *,
    await_ready: bool = True,
) -> tuple[multiprocessing.Process, multiprocessing.Queue, multiprocessing.Queue]:
    q_in: multiprocessing.Queue = multiprocessing.Queue()
    q_out: multiprocessing.Queue = multiprocessing.Queue()
    proc = multiprocessing.Process(
        target=MedCodERRetrieverWorker.run,
        args=(q_in, q_out, "unused", retriever),
        daemon=True,
    )
    proc.start()
    if await_ready:
        try:
            startup_id, payload = q_out.get(timeout=15.0)
        except Exception as exc:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2)
            raise TimeoutError(
                "worker did not emit an explicit startup result within 15s "
                f"(alive={proc.is_alive()}, exitcode={proc.exitcode})"
            ) from exc
        if startup_id != MedCodERRetrieverWorker.STARTUP_READY_ID:
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=2)
            raise RuntimeError(
                f"worker startup failed: id={startup_id!r}, payload={payload!r}, "
                f"exitcode={proc.exitcode}"
            )
        assert payload == {"ready": True}
    return proc, q_in, q_out


def _recv_with_timeout(q: multiprocessing.Queue, timeout: float = 5.0):
    """Receive one message with a hard timeout, else fail."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return q.get(timeout=0.5)
        except Exception:
            continue
    raise TimeoutError(f"No message within {timeout}s")


# ── Tests ──


def test_worker_processes_three_requests_in_order():
    """3 requests → 3 responses in the same order, with matching req_ids."""
    retriever = FakeRetriever({
        "心衰": ["I50.900", "I50.0", "I50.1"],
        "高血压": ["I10", "I10.x00"],
        "糖尿病": ["E11.900", "E11.9"],
    })
    proc, q_in, q_out = _spawn_worker(retriever)
    try:
        q_in.put(("req-1", "心衰", 3))
        q_in.put(("req-2", "高血压", 2))
        q_in.put(("req-3", "糖尿病", 2))

        r1 = _recv_with_timeout(q_out)
        r2 = _recv_with_timeout(q_out)
        r3 = _recv_with_timeout(q_out)

        assert r1[0] == "req-1"
        assert r2[0] == "req-2"
        assert r3[0] == "req-3"
        # Each response is a list (the FakeRetriever returns lists of code strings;
        # the real retriever returns CandidateCode objects — both pickle cleanly).
        assert r1[1] == ["I50.900", "I50.0", "I50.1"]
        assert r2[1] == ["I10", "I10.x00"]
        assert r3[1] == ["E11.900", "E11.9"]
        # ensure_loaded was called once at startup, not per request
        assert retriever._ensure_loaded_counter.value == 1
        assert retriever._retrieve_counter.value == 3
    finally:
        q_in.put(None)
        proc.join(timeout=5)
        assert not proc.is_alive(), "worker did not exit on sentinel"


def test_worker_emits_ready_only_after_retriever_loads():
    """The parent gets an explicit startup boundary before sending work."""

    retriever = FakeRetriever({})
    proc, q_in, _q_out = _spawn_worker(retriever)
    try:
        assert proc.is_alive()
        assert retriever._ensure_loaded_counter.value == 1
        assert retriever._retrieve_counter.value == 0
    finally:
        q_in.put(None)
        proc.join(timeout=5)
        assert not proc.is_alive()


def test_worker_returns_error_envelope_on_retrieve_failure():
    """If retrieve_sync raises, worker sends {error: repr(exc)} and stays alive."""
    retriever = FakeRetriever(
        responses_by_disease={"正常": ["I10"]},
        raise_on="爆炸",
    )
    proc, q_in, q_out = _spawn_worker(retriever)
    try:
        # A normal request first — confirms the loop survives the failure
        q_in.put(("ok", "正常", 5))
        ok = _recv_with_timeout(q_out)
        assert ok[0] == "ok"
        assert ok[1] == ["I10"]

        # Now a request that triggers the simulated error
        q_in.put(("bad", "爆炸", 5))
        bad = _recv_with_timeout(q_out)
        assert bad[0] == "bad"
        assert isinstance(bad[1], dict)
        assert "error" in bad[1]
        assert "simulated retrieve failure" in bad[1]["error"]

        # Worker is still alive and can serve more requests
        q_in.put(("ok2", "正常", 1))
        ok2 = _recv_with_timeout(q_out)
        assert ok2[0] == "ok2"
    finally:
        q_in.put(None)
        proc.join(timeout=5)


def test_worker_does_not_load_faiss_in_parent_process():
    """Sanity check: importing the worker module does not pull faiss into the parent.

    The real FAISS/BGE-M3 imports happen only inside the worker
    process. If the parent test process gains ``faiss`` in sys.modules
    after importing the worker module, this is a leak and the
    subprocess isolation promise is broken.
    """
    pre_state = "faiss" in sys.modules

    retriever = FakeRetriever({"a": ["I10"]})
    proc, q_in, q_out = _spawn_worker(retriever)
    try:
        q_in.put(("r", "a", 1))
        out = _recv_with_timeout(q_out)
        assert out[0] == "r"
    finally:
        q_in.put(None)
        proc.join(timeout=5)

    # Parent's faiss import state is unchanged.
    assert ("faiss" in sys.modules) == pre_state, (
        "faiss was imported in the parent process — subprocess isolation broken"
    )


def test_worker_ensure_loaded_called_exactly_once():
    """ensure_loaded() runs at startup, never on each request — important for
    the FAISS memory-mapped index (loading it per call would be O(seconds)).
    """
    retriever = FakeRetriever({"x": ["I10"]})
    proc, q_in, q_out = _spawn_worker(retriever)
    try:
        for i in range(5):
            q_in.put((f"r{i}", "x", 1))
        for _ in range(5):
            assert _recv_with_timeout(q_out)[0].startswith("r")
        # 5 requests served, but only 1 ensure_loaded() call.
        assert retriever._ensure_loaded_counter.value == 1
        assert retriever._retrieve_counter.value == 5
    finally:
        q_in.put(None)
        proc.join(timeout=5)


def test_worker_sentinel_none_terminates_cleanly():
    """Pushing None to queue_in causes the worker to exit with code 0."""
    retriever = FakeRetriever({})
    proc, q_in, _q_out = _spawn_worker(retriever)
    q_in.put(None)
    proc.join(timeout=5)
    assert not proc.is_alive()
    assert proc.exitcode == 0, f"worker exited with code {proc.exitcode}"


def test_worker_exits_when_parent_watch_pipe_closes():
    """An abruptly terminated parent must not leave a native model worker."""
    # The production worker is a Windows/spawn isolation boundary. Using
    # Linux fork here leaks the pipe's write descriptor into the child, so
    # closing the parent writer can never produce EOF in the worker.
    context = multiprocessing.get_context("spawn")
    q_in = context.Queue()
    q_out = context.Queue()
    watch_recv, watch_send = context.Pipe(duplex=False)
    proc = context.Process(
        target=MedCodERRetrieverWorker.run,
        args=(q_in, q_out, "unused", FakeRetriever({}), None, watch_recv),
        daemon=True,
    )
    proc.start()
    watch_recv.close()
    try:
        # Closing the only parent-side writer simulates parent process exit.
        watch_send.close()
        proc.join(timeout=4)
        assert not proc.is_alive(), "worker ignored parent-watch EOF"
        assert proc.exitcode == 0
    finally:
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=2)


def test_worker_startup_error_reported_via_special_id():
    """If ensure_loaded() raises at startup, the worker pushes a special
    ``STARTUP_ERROR_ID`` tuple and exits (no further requests served).
    """
    proc, q_in, q_out = _spawn_worker(
        FailingStartupRetriever(),
        await_ready=False,
    )
    try:
        # Worker should send STARTUP_ERROR_ID and exit
        msg = _recv_with_timeout(q_out)
        assert msg[0] == MedCodERRetrieverWorker.STARTUP_ERROR_ID
        assert "FileNotFoundError" in msg[1]
        assert "index missing" in msg[1]
        # Worker has exited (it returns after startup failure)
        proc.join(timeout=2)
        assert not proc.is_alive()
    finally:
        if proc.is_alive():
            q_in.put(None)
            proc.join(timeout=5)
