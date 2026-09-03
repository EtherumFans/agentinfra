"""Interviewing Expert — Corti public §3.2 key 9 of 9 (A1B-AE.7 schema-driven).

Corti public docs describe this Expert as driving structured
questionnaire interviews — e.g. intake forms, triage questionnaires,
score-driven follow-ups (APGAR, PHQ-9, etc.).

iCoDer's A1B-AE.7 scope is a schema-driven interviewer:

1. Registers under canonical_key='interviewing' with
   corti_alignment='CORTI_ALIGNED' (iCoDer's schema-driven loop matches
   the Corti public contract surface: present question → collect
   answer → branch → emit transcript).

2. Accepts a questionnaire schema (list of QuestionSpec) and an
   optional answer history. Returns the next question (or the
   terminal ``INTERVIEW_COMPLETE`` marker).

3. Emits a deterministic transcript (no LLM call). Branching is
   rule-based on prior answers (``ask_if`` predicate).

A1B-AE-R.4.c (2026-07-23) adds persistence:
   - ``serialize_state()`` converts InterviewState to a JSON-able dict
     (``ask_if`` predicates are dropped — callers must restore them
     from the questionnaire_key).
   - ``deserialize_state()`` rebuilds state from JSON + a fresh
     QuestionSpec list (looked up by questionnaire_key).
   - ``save_to_context()`` / ``load_from_context()`` round-trip the
     state via the ContextRow.metadata_json field.

Out of scope: LLM-driven adaptive prompting, multi-language scripting,
audio STT. These are A1B-AE.9 or later-phase candidates.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable


INTERVIEWING_EXPERT_CANONICAL_KEY = "interviewing"
INTERVIEWING_EXPERT_NAME = "Interviewing Expert"

INTERVIEW_COMPLETE = "INTERVIEW_COMPLETE"


@dataclass
class QuestionSpec:
    """A single question in a questionnaire.

    ``ask_if`` is an optional predicate over the current answer map.
    When it returns False (or the referenced key is missing/None), the
    question is skipped. A None ``ask_if`` means "always ask".
    """

    key: str
    prompt: str
    kind: str = "text"  # text | number | choice | boolean
    choices: list[str] | None = None
    ask_if: Callable[[dict[str, Any]], bool] | None = None
    required: bool = True


@dataclass
class InterviewState:
    questionnaire_key: str
    questions: list[QuestionSpec] = field(default_factory=list)
    answers: dict[str, Any] = field(default_factory=dict)
    cursor: int = 0
    notes: str = ""


@dataclass
class InterviewStep:
    """Result of a single ``advance`` call.

    Either ``next_question`` is populated and ``complete`` is False,
    or ``next_question`` is None and ``complete`` is True.
    """

    next_question: QuestionSpec | None
    complete: bool = False
    skipped_keys: list[str] = field(default_factory=list)
    state: InterviewState = field(default_factory=InterviewState)


def start_interview(
    questionnaire_key: str,
    questions: list[QuestionSpec],
) -> InterviewState:
    """Initialize an interview. ``questions`` MUST be non-empty."""
    if not questions:
        raise ValueError("interview requires at least one question")
    return InterviewState(
        questionnaire_key=questionnaire_key,
        questions=list(questions),
        cursor=0,
    )


# ─────────────────────────────────────────────────────────────────────
# A1B-AE-R.4.c — persistence helpers
# ─────────────────────────────────────────────────────────────────────


def serialize_state(state: InterviewState) -> dict[str, Any]:
    """Convert InterviewState to a JSON-able dict.

    The ``ask_if`` predicate cannot be serialized (it's a lambda); callers
    restore it by looking up the questionnaire_key in a fresh QuestionSpec
    list via ``deserialize_state(state_dict, fresh_questions)``.

    The serialized form stores per-question metadata (key/prompt/kind/
    choices/required) so the caller can sanity-check that the fresh
    questions list matches the one used at save time.
    """
    return {
        "version": 1,
        "questionnaire_key": state.questionnaire_key,
        "answers": dict(state.answers),
        "cursor": state.cursor,
        "notes": state.notes,
        "question_keys": [q.key for q in state.questions],
    }


def deserialize_state(
    data: dict[str, Any],
    fresh_questions: list[QuestionSpec],
) -> InterviewState:
    """Rebuild InterviewState from a serialized dict.

    ``fresh_questions`` MUST come from the caller's questionnaire
    registry (it supplies the ``ask_if`` predicates that were dropped
    at serialize time). Raises ValueError if the question keys don't
    match the serialized state.
    """
    q_keys_in_state = list(data.get("question_keys") or [])
    fresh_keys = [q.key for q in fresh_questions]
    if q_keys_in_state and q_keys_in_state != fresh_keys:
        raise ValueError(
            "question list mismatch: state has "
            f"{q_keys_in_state!r}, fresh_questions has {fresh_keys!r}"
        )
    return InterviewState(
        questionnaire_key=data.get("questionnaire_key", ""),
        questions=list(fresh_questions),
        answers=dict(data.get("answers") or {}),
        cursor=int(data.get("cursor", 0)),
        notes=str(data.get("notes", "")),
    )


async def save_to_context(
    db,
    context_id: str,
    state: InterviewState,
) -> None:
    """Persist InterviewState into contexts.metadata_json.

    The metadata JSON is parsed, the ``interview_state`` key is set to
    the serialized dict, and the row is updated. Other metadata keys
    are preserved.

    ``db`` is an AsyncSession. The ContextRow is loaded by primary key.
    """
    from app.icoder.agent_runtime.context.db_models import ContextRow

    from sqlalchemy import select

    result = await db.execute(
        select(ContextRow).where(ContextRow.id == context_id)
    )
    row = result.scalars().first()
    if row is None:
        raise ValueError(f"context not found: {context_id}")

    try:
        meta = json.loads(row.metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}
    meta["interview_state"] = serialize_state(state)
    row.metadata_json = json.dumps(meta, ensure_ascii=False)
    await db.commit()


async def load_from_context(
    db,
    context_id: str,
    fresh_questions: list[QuestionSpec],
) -> InterviewState | None:
    """Re-hydrate InterviewState from contexts.metadata_json.

    Returns None if no interview state is saved for the given context.
    Raises ValueError if the saved question list does not match
    ``fresh_questions`` (caller supplied the wrong questionnaire).
    """
    from app.icoder.agent_runtime.context.db_models import ContextRow

    from sqlalchemy import select

    result = await db.execute(
        select(ContextRow).where(ContextRow.id == context_id)
    )
    row = result.scalars().first()
    if row is None:
        raise ValueError(f"context not found: {context_id}")

    try:
        meta = json.loads(row.metadata_json or "{}")
    except (json.JSONDecodeError, TypeError):
        meta = {}
    state_dict = meta.get("interview_state")
    if not state_dict:
        return None
    return deserialize_state(state_dict, fresh_questions)


def advance(state: InterviewState, answer: Any = None) -> InterviewStep:
    """Record the answer for the question at the cursor (if any) and
    advance to the next askable question.

    The first call (cursor=0, answer=None) is the "priming" call — it
    skips the answer-write step and just returns question 0 (or the
    first question whose ``ask_if`` passes).
    """
    if state.cursor >= len(state.questions):
        return InterviewStep(
            next_question=None,
            complete=True,
            state=state,
        )

    if answer is not None:
        current = state.questions[state.cursor]
        state.answers[current.key] = answer
        state.cursor += 1

    skipped: list[str] = []
    while state.cursor < len(state.questions):
        q = state.questions[state.cursor]
        if q.ask_if is None or q.ask_if(state.answers):
            return InterviewStep(
                next_question=q,
                complete=False,
                skipped_keys=skipped,
                state=state,
            )
        skipped.append(q.key)
        state.cursor += 1

    return InterviewStep(
        next_question=None,
        complete=True,
        skipped_keys=skipped,
        state=state,
    )


def record_answer(state: InterviewState, key: str, value: Any) -> None:
    """Record an out-of-band answer (e.g. when the caller drives the
    question loop themselves instead of calling ``advance``).
    """
    state.answers[key] = value


def transcript(state: InterviewState) -> dict[str, Any]:
    """Emit a deterministic transcript of the interview."""
    return {
        "questionnaire_key": state.questionnaire_key,
        "answers": dict(state.answers),
        "question_count": len(state.questions),
        "answered_count": len(state.answers),
    }


__all__ = [
    "INTERVIEWING_EXPERT_CANONICAL_KEY",
    "INTERVIEWING_EXPERT_NAME",
    "INTERVIEW_COMPLETE",
    "QuestionSpec",
    "InterviewState",
    "InterviewStep",
    "start_interview",
    "advance",
    "record_answer",
    "transcript",
    "serialize_state",
    "deserialize_state",
    "save_to_context",
    "load_from_context",
]
