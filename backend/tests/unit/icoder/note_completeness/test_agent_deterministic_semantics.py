from __future__ import annotations

import pytest

from official_agents.note_completeness.agent import run_deterministic


COMPLETE_NON_SURGICAL_NOTE = (
    "主诉：腰痛。现病史：腰痛三月。既往史：高血压。"
    "体格检查：腰椎压痛。辅助检查：影像检查完成。"
    "入院诊断：L1 椎体压缩性骨折。出院诊断：L1 椎体压缩性骨折。"
    "治疗经过：保守治疗后好转。"
)


@pytest.mark.asyncio
async def test_complete_consistent_note_can_pass() -> None:
    result = await run_deterministic(COMPLETE_NON_SURGICAL_NOTE, run_id="run-complete")

    assert result["review_conclusion"] == "PASS"
    assert result["completeness_score"] == 1.0
    assert result["missing_sections"] == []
    assert result["incomplete_sections"] == []
    assert result["conflicts"] == []


@pytest.mark.asyncio
async def test_surgical_spinal_level_conflict_is_explicit_and_reviewable() -> None:
    text = (
        "主诉: 腰背部疼痛 3 月。现病史: 活动后加重。既往史: 高血压。"
        "体格检查: 腰椎压痛。辅助检查: X 线示 L1 椎体压缩性骨折。"
        "诊断: L1 椎体压缩性骨折。治疗经过: 行 T12 椎体切开复位内固定术，"
        "术后恢复良好。"
    )

    result = await run_deterministic(text, run_id="run-conflict")

    assert result["review_conclusion"] == "WARNING"
    assert result["completeness_score"] == 0.875
    assert result["missing_sections"] == ["手术记录"]
    assert {item["section"] for item in result["incomplete_sections"]} == {
        "诊断",
        "治疗经过",
    }
    assert len(result["conflicts"]) == 1
    assert "L1" in result["conflicts"][0]["note"]
    assert "T12" in result["conflicts"][0]["note"]
    assert result["manual_review_required"] is True


@pytest.mark.asyncio
async def test_spinal_level_rule_does_not_infer_conflict_without_both_sections() -> None:
    text = (
        "主诉：腰痛。现病史：腰痛三月。既往史：无。体格检查：压痛。"
        "辅助检查：L1 改变。诊断：L1 椎体压缩性骨折。治疗经过：保守治疗。"
    )

    result = await run_deterministic(text, run_id="run-one-sided")

    assert result["conflicts"] == []
