"""C8 — context_garbage_collector: GCResult + is_running state (no DB)."""

from __future__ import annotations

from app.icoder.agent_runtime.context.context_garbage_collector import GCResult


def test_gc_result_default_empty():
    r = GCResult()
    assert r.swept_ids == []
    assert r.destroyed_ids == []
    assert r.pruned_audit_ids == []
    assert r.total == 0


def test_gc_result_total_counts_all_three():
    r = GCResult(
        swept_ids=["a", "b"],
        destroyed_ids=["c"],
        pruned_audit_ids=["d", "e", "f"],
    )
    assert r.total == 6
    assert r.swept_ids == ["a", "b"]
    assert r.destroyed_ids == ["c"]
    assert r.pruned_audit_ids == ["d", "e", "f"]


def test_gc_result_total_zero_when_all_empty():
    assert GCResult().total == 0
    assert GCResult(swept_ids=[], destroyed_ids=[], pruned_audit_ids=[]).total == 0