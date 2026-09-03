"""ContextBuilder — explicit RunContext construction (§8.1).

Extracts text from A2A Parts, builds RunContext with server-generated
context_id (Q4 — strict isolation), records request metadata. This was
previously inline in InboundHandler steps 2-3; pulling it out makes the
context-construction policy explicit and testable.

The ContextBuilder is pure logic — no I/O, no redaction (that's
PolicyGuard's job). It does:

  1. extract_text_from_parts()
  2. construct RunContext(run_id, context_id, agent_id, ...)
  3. preserve original_input for audit
  4. return a ContextArtifact that the Orchestrator passes forward
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from .inbound_handler import extract_text_from_parts
from .run_context import RunContext


@dataclass
class ContextArtifact:
    """Output of ContextBuilder — what the Orchestrator passes forward."""

    run_context: RunContext
    original_text: str
    request_metadata: dict[str, Any] = field(default_factory=dict)


class ContextBuilder:
    """Constructs RunContext from an A2A InboundRequest.

    Pure logic. Server-generated run_id + context_id (Q4). Keeps
    original_text for audit and redacted_text for the hot path.
    """

    def __init__(self, *, id_factory=None) -> None:
        self._id_factory = id_factory or (lambda: str(uuid.uuid4()))

    def build(
        self,
        *,
        agent_id: str,
        parts: list[dict],
        interaction_id: str = "",
        agent_definition: Any = None,
        request_metadata: dict[str, Any] | None = None,
    ) -> ContextArtifact:
        run_id = self._id_factory()
        context_id = self._id_factory()
        original_text = extract_text_from_parts(parts)
        ctx = RunContext(
            run_id=run_id,
            context_id=context_id,
            agent_id=agent_id,
            agent_definition=agent_definition,
            original_input=original_text,
            redacted_input="",  # PolicyGuard fills this in
        )
        return ContextArtifact(
            run_context=ctx,
            original_text=original_text,
            request_metadata={
                "interaction_id": interaction_id,
                **(request_metadata or {}),
            },
        )


__all__ = ["ContextArtifact", "ContextBuilder"]
