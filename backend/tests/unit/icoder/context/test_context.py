"""C2 — Context / ContextMessage / ContextTaskRef / ContextArtifactRef."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.icoder.agent_runtime.context import (
    Context,
    ContextArtifactRef,
    ContextMessage,
    ContextMetadata,
    ContextStatus,
    ContextTaskRef,
    generate_context_id,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ctx(**overrides) -> Context:
    now = _now()
    defaults = dict(
        id=generate_context_id(),
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(hours=24),
        agent_id="homepage-coding-review",
        status=ContextStatus.ACTIVE,
    )
    defaults.update(overrides)
    return Context(**defaults)


def test_context_minimal_construction():
    ctx = _ctx()
    assert ctx.status == ContextStatus.ACTIVE
    assert ctx.messages == []
    assert ctx.tasks == []
    assert ctx.artifacts == []
    assert ctx.metadata.production_writeback_blocked is True
    assert ctx.metadata.phi_redacted is True
    assert ctx.redacted_input_hash == ""
    assert ctx.original_input_ref == ""


def test_context_id_must_be_canonical_uuid_v4():
    with pytest.raises(ValidationError):
        _ctx(id="not-a-uuid")
    with pytest.raises(ValidationError):
        _ctx(id="550e8400-e29b-11d4-a716-446655440000")  # v1


def test_context_id_accepts_fresh_uuid_v4():
    ctx = _ctx(id=generate_context_id())
    assert ctx.id is not None


def test_metadata_hard_invariants_default_to_true():
    md = ContextMetadata()
    assert md.production_writeback_blocked is True
    assert md.phi_redacted is True


def test_metadata_invariants_cannot_be_unset():
    with pytest.raises(ValidationError):
        ContextMetadata(production_writeback_blocked=False)
    with pytest.raises(ValidationError):
        ContextMetadata(phi_redacted=False)


def test_metadata_invariants_cannot_be_changed_after_creation():
    md = ContextMetadata(phi_redacted_entities=["NAME"])
    with pytest.raises(ValidationError):
        md.production_writeback_blocked = False
    with pytest.raises(ValidationError):
        md.phi_redacted = False


def test_metadata_phi_entities_and_custom_round_trip():
    md = ContextMetadata(
        phi_redacted_entities=["NAME", "ID_CARD"],
        user_id="u-1",
        tenant_id="t-1",
        custom={"encounter_id": "enc-42"},
    )
    assert md.phi_redacted_entities == ["NAME", "ID_CARD"]
    assert md.user_id == "u-1"
    assert md.tenant_id == "t-1"
    assert md.custom == {"encounter_id": "enc-42"}


def test_metadata_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ContextMetadata(unknown_field="x")


def test_context_message_redacted_default_true():
    msg = ContextMessage(
        message_id="m-1",
        role="user",
        parts=[{"type": "text", "text": "hello"}],
        timestamp=_now(),
    )
    assert msg.redacted is True


def test_context_message_redacted_cannot_be_set_false():
    with pytest.raises(ValidationError):
        ContextMessage(
            message_id="m-1",
            role="user",
            parts=[],
            timestamp=_now(),
            redacted=False,
        )


def test_context_message_redacted_cannot_be_changed_after_creation():
    msg = ContextMessage(
        message_id="m-1",
        role="user",
        parts=[],
        timestamp=_now(),
    )
    with pytest.raises(ValidationError):
        msg.redacted = False


def test_context_message_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ContextMessage(
            message_id="m-1",
            role="user",
            parts=[],
            timestamp=_now(),
            unknown_field="x",
        )


def test_context_task_ref_completed_at_optional():
    started = _now()
    completed = started + timedelta(minutes=5)
    ref = ContextTaskRef(task_id="t-1", state="working", started_at=started)
    assert ref.completed_at is None
    ref2 = ContextTaskRef(
        task_id="t-2", state="completed", started_at=started, completed_at=completed
    )
    assert ref2.completed_at == completed


def test_context_artifact_ref_required_fields():
    art = ContextArtifactRef(
        artifact_id="a-1",
        name="evidence.json",
        mime_type="application/json",
        url="https://example.com/evidence/a-1",
    )
    assert art.artifact_id == "a-1"


def test_context_messages_tasks_artifacts_round_trip():
    ctx = _ctx(
        messages=[
            ContextMessage(
                message_id="m-1",
                role="user",
                parts=[{"type": "text", "text": "hi"}],
                timestamp=_now(),
            )
        ],
        tasks=[
            ContextTaskRef(task_id="t-1", state="submitted", started_at=_now())
        ],
        artifacts=[
            ContextArtifactRef(
                artifact_id="a-1",
                name="out.json",
                mime_type="application/json",
                url="https://x/a-1",
            )
        ],
    )
    assert len(ctx.messages) == 1
    assert len(ctx.tasks) == 1
    assert len(ctx.artifacts) == 1
    assert ctx.messages[0].redacted is True


def test_context_status_lifecycle_values():
    assert ContextStatus.ACTIVE.value == "active"
    assert ContextStatus.COMPLETED.value == "completed"
    assert ContextStatus.FAILED.value == "failed"
    assert ContextStatus.EXPIRED.value == "expired"