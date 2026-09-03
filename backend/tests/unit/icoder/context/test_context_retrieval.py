"""Bounded Chinese-aware Context memory selection."""

from datetime import datetime, timedelta, timezone

from app.icoder.agent_runtime.context.context import ContextMessage
from app.icoder.agent_runtime.context.context_retrieval import (
    select_context_memory,
)


def _message(message_id: str, text: str, offset: int) -> ContextMessage:
    return ContextMessage(
        message_id=message_id,
        role="user",
        parts=[{"kind": "text", "text": text}],
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=offset),
        redacted=True,
    )


def test_selects_relevant_chinese_history_and_preserves_chronology():
    messages = [
        _message("m1", "患者既往2型糖尿病控制欠佳", 1),
        _message("m2", "此次因左侧桡骨远端骨折入院", 2),
        _message("m3", "空腹血糖近期持续升高", 3),
    ]

    result = select_context_memory("继续分析糖尿病和血糖", messages)

    assert result.retrieval_mode == "LEXICAL_CJK_BIGRAM"
    assert [message.message_id for message in result.messages] == ["m1", "m3"]


def test_recent_fallback_and_character_budget_are_bounded():
    messages = [_message(f"m{index}", "骨折病史" * 20, index) for index in range(10)]

    result = select_context_memory(
        "完全无关词",
        messages,
        limit=3,
        recent_fallback=3,
        character_budget=50,
    )

    assert result.selected_count == 1
    assert result.selected_characters == 50
    assert len(result.messages[0].parts[0]["text"]) == 50
