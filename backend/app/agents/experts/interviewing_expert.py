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

Out of scope: LLM-driven adaptive prompting, multi-language scripting,
audio STT. These are A1B-AE.9 or later-phase candidates.
"""
from __future__ import annotations

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
]
