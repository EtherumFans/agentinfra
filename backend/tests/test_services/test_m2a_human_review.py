"""M2a Task 4 — Human Review writeback tests.

Verifies:
- test_human_review_rejects_sample_run
- test_human_review_requires_reason_code
- test_human_review_primary_dx_change_marked_as_human
- test_learning_loop_accepts_only_real_human_review
"""

from __future__ import annotations

import pytest
import tempfile
import shutil
from pathlib import Path

from icoder_runtime.m2a.human_review import HumanReviewService, VALID_REASON_CODES
from icoder_runtime.m2a.run_trace import RunTraceService
from icoder_runtime.m2a.store import M2aStore


@pytest.fixture
def m2a_dir():
    tmp = tempfile.mkdtemp(prefix="m2a_hr_")
    yield Path(tmp)
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def setup(m2a_dir):
    store = M2aStore(m2a_dir)
    trace = RunTraceService(store=store)
    review = HumanReviewService(store=store, run_trace=trace)
    return store, trace, review


def test_human_review_rejects_sample_run(setup):
    """sample run 的人工复核写回必须被拒绝。"""
    store, trace_svc, review_svc = setup
    # 启动一个 sample run
    sample = trace_svc.start_run(agent_ref="agent.demo", is_sample=True, data_source="sample")
    trace_svc.finalize_run(sample.run_id, "ok")

    # 试图人工写回 → 必须 ValueError
    with pytest.raises(ValueError, match="sample run .* REJECTED"):
        review_svc.submit_review(
            run_id=sample.run_id,
            reviewer="tester",
            decision="approve",
            reason_code="primary_dx_confirmed",
            rationale="测试",
        )


def test_human_review_requires_reason_code(setup):
    """reason_code 必须是合法枚举。"""
    store, trace_svc, review_svc = setup
    real = trace_svc.start_run(agent_ref="agent.test")
    trace_svc.finalize_run(real.run_id, "success")

    with pytest.raises(ValueError, match="Invalid reason_code"):
        review_svc.submit_review(
            run_id=real.run_id,
            reviewer="tester",
            decision="approve",
            reason_code="totally_made_up",
            rationale="bad",
        )
    # 也校验 decision 非法
    with pytest.raises(ValueError, match="Invalid decision"):
        review_svc.submit_review(
            run_id=real.run_id,
            reviewer="tester",
            decision="maybe",
            reason_code="primary_dx_confirmed",
            rationale="bad",
        )


def test_human_review_primary_dx_change_marked_as_human(setup):
    """主诊断变更的人工复核必须标记 primary_dx_change=True + is_human=True。"""
    store, trace_svc, review_svc = setup
    real = trace_svc.start_run(agent_ref="agent.test")
    trace_svc.finalize_run(real.run_id, "success")

    rec = review_svc.submit_review(
        run_id=real.run_id,
        reviewer="reviewer-001",
        decision="modify",
        reason_code="primary_dx_confirmed",
        rationale="主诊断确认：I50.900 → I50.901",
        primary_dx_change=True,
        modifications={"primary_dx": {"from": "I50.900", "to": "I50.901"}},
    )
    assert rec.is_human is True
    assert rec.is_sample is False
    assert rec.primary_dx_change is True
    assert rec.decision == "modify"
    assert rec.reason_code == "primary_dx_confirmed"


def test_learning_loop_accepts_only_real_human_review(setup):
    """Learning Loop 只接受真实人工修改。"""
    store, trace_svc, review_svc = setup
    real = trace_svc.start_run(agent_ref="agent.test")
    trace_svc.finalize_run(real.run_id, "success")

    # 1. 真实人工修改 → 进入 learning loop
    review_svc.submit_review(
        run_id=real.run_id,
        reviewer="reviewer-001",
        decision="modify",
        reason_code="code_correction",
        rationale="真实修改",
        primary_dx_change=False,
        modifications={"secondary": {"add": "E11.901"}},
    )
    loop = review_svc.list_learning_loop()
    assert len(loop) == 1
    assert loop[0]["reason_code"] == "code_correction"
    # is_human + is_sample 字段（通过 review 间接验证）
    assert loop[0]["modifications"]["secondary"]["add"] == "E11.901"

    # 2. 尝试 sample 写回 → 拒绝，绝不进 learning loop
    sample = trace_svc.start_run(agent_ref="agent.demo", is_sample=True, data_source="sample")
    trace_svc.finalize_run(sample.run_id, "ok")
    with pytest.raises(ValueError):
        review_svc.submit_review(
            run_id=sample.run_id,
            reviewer="reviewer-002",
            decision="approve",
            reason_code="add_missing",
            rationale="不应该被接受",
        )
    # learning loop 仍然只有 1 条
    loop2 = review_svc.list_learning_loop()
    assert len(loop2) == 1


def test_human_review_reason_code_enum_complete(setup):
    """枚举完整性：13 类 reason_code 都必须合法。"""
    expected = {
        "code_correction", "rule_triggered", "evidence_strengthened",
        "terminology_corrected", "remove_redundant", "add_missing",
        "primary_dx_confirmed", "rule_conflict_resolved",
        "payment_risk_reviewed", "insurance_alignment",
        "data_quality_issue", "rule_upgrade_suggested", "error_taxonomy_corrected",
    }
    assert expected == VALID_REASON_CODES
    assert len(VALID_REASON_CODES) == 13
