"""ContextRepository — strict per-contextId data access (SPEC §6.2).

Every method takes ``context_id`` as a positional parameter; there is no
API surface that lets a caller read or write without supplying one.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from .context import Context, ContextArtifactRef, ContextMessage, ContextTaskRef
from .context_id import is_valid_context_id
from .context_isolation import ContextIsolationError, ContextNotFoundError
from .context_status import ContextStatus
from .db_models import (
    ContextArtifactRefRow,
    ContextMessageRow,
    ContextRow,
    ContextTaskRefRow,
    OriginalInputAuditRow,
)

# RV.3 — cross-store scrub imports.
# These are late imports inside the function body to keep the module
# import-time graph free of a context -> app.models dependency cycle
# (app.models.memory already imports app.icoder.agent_runtime.context
# indirectly via services). The function-body import is deterministic
# and cheap because Python caches module objects after first use.


def _as_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip; re-attach UTC if naive."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class ContextRepository:
    """Mandatory-contextId data access layer."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def _require_valid_id(self, context_id: str) -> None:
        if not is_valid_context_id(context_id):
            raise ContextIsolationError(
                f"context_id must be canonical UUID v4: {context_id!r}",
                context_id=context_id,
            )

    async def _require_context_exists(self, context_id: str) -> None:
        await self._require_valid_id(context_id)
        row = await self._session.get(ContextRow, context_id)
        if row is None:
            raise ContextNotFoundError(
                f"context {context_id!r} not found",
                context_id=context_id,
            )

    @staticmethod
    def _row_to_context(row: ContextRow) -> Context:
        metadata = json.loads(row.metadata_json) if row.metadata_json else {}
        return Context(
            id=row.id,
            created_at=_as_utc(row.created_at),
            updated_at=_as_utc(row.updated_at),
            expires_at=_as_utc(row.expires_at),
            agent_id=row.agent_id,
            organization_id=row.organization_id,
            status=ContextStatus(row.status),
            metadata=metadata,
            redacted_input_hash=row.redacted_input_hash,
            original_input_ref=row.original_input_ref,
        )

    async def create_context(self, ctx: Context) -> Context:
        await self._require_valid_id(ctx.id)
        row = ContextRow(
            id=ctx.id,
            created_at=ctx.created_at,
            updated_at=ctx.updated_at,
            expires_at=ctx.expires_at,
            agent_id=ctx.agent_id,
            organization_id=ctx.organization_id,
            status=ctx.status.value,
            metadata_json=ctx.metadata.model_dump_json(),
            redacted_input_hash=ctx.redacted_input_hash,
            original_input_ref=ctx.original_input_ref,
        )
        self._session.add(row)
        await self._session.commit()
        return ctx

    async def get_context(self, context_id: str) -> Context | None:
        await self._require_valid_id(context_id)
        row = await self._session.get(ContextRow, context_id)
        return self._row_to_context(row) if row else None

    async def update_status(
        self,
        context_id: str,
        status: ContextStatus,
        *,
        updated_at: datetime | None = None,
        expires_at: datetime | None = None,
    ) -> None:
        await self._require_context_exists(context_id)
        row = await self._session.get(ContextRow, context_id)
        assert row is not None
        row.status = status.value
        row.updated_at = updated_at or datetime.now(timezone.utc)
        if expires_at is not None:
            row.expires_at = expires_at
        await self._session.commit()

    async def delete_context(self, context_id: str) -> None:
        await self._require_context_exists(context_id)
        row = await self._session.get(ContextRow, context_id)
        assert row is not None
        await self._session.delete(row)
        await self._session.commit()

    async def get_for_org(
        self, context_id: str, organization_id: str
    ) -> ContextRow | None:
        """Tenant-scoped row lookup.

        Returns the ContextRow if ``context_id`` exists AND belongs to
        ``organization_id``; otherwise None. Callers should return 404
        on None — never distinguish "wrong tenant" from "does not exist"
        in user-facing responses (no tenant leakage).
        """
        await self._require_valid_id(context_id)
        stmt = select(ContextRow).where(
            ContextRow.id == context_id,
            ContextRow.organization_id == organization_id,
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def hard_delete_context(
        self,
        context_id: str,
        *,
        redaction_marker: str = "[REDACTED_BY_CONTEXT_DELETE]",
    ) -> dict[str, int]:
        """A1B-AE-R.1.b + A1B-AE-RV.3 — physical scrub + cross-store redaction.

        Deletes (in dependency order):

        * ``original_input_audit`` — no FK declared, manual delete
        * ``context_artifact_refs`` — FK CASCADE declared but SQLite
          runs with ``PRAGMA foreign_keys=OFF`` by default; we delete
          explicitly so the scrub is correct regardless of PRAGMA state
        * ``context_task_refs`` — same
        * ``context_messages`` — same
        * ``contexts`` — parent row last

        A1B-AE-RV.3 adds cross-store scrubbing for the 4 stores
        identified in CONTEXT_DATA_DEPENDENCY_GRAPH.json gaps
        RV3_GAP_01..04:

        * ``conversation_memories`` — HARD DELETE where
          ``session_id LIKE '{context_id}:%'`` (memory_expert.ingest
          creates rows with this composite key)
        * ``run_trace_events`` — REDACT ``safe_metadata_json`` where
          ``run_id IN (SELECT run_id FROM run_history WHERE
          context_id = :ctx_id)``; row retained for audit
        * ``run_history`` — REDACT ``input_text`` +
          ``output_summary`` + clear ``context_id`` where
          ``context_id = :ctx_id``; row retained for audit
        * ``audit_logs`` — REDACT ``details`` +
          ``model_input_summary`` + ``model_output_summary`` +
          ``tool_calls_made`` where ``resource_id = :ctx_id``; row
          retained for audit

        Use this for the user-facing ``DELETE /api/icoder/contexts/{id}``
        endpoint. The GC path (``destroy_expired``) continues to use
        ``delete_context`` because it operates on already-expired rows
        whose audit retention is still in force. ``delete_context``
        will gain the same child-scrub logic in a follow-up once a
        global SQLite ``PRAGMA foreign_keys=ON`` listener is wired.

        Returns a per-store delete/redact count dict so callers
        (and tests) can assert no store was silently missed.
        """
        await self._require_context_exists(context_id)
        counts: dict[str, int] = {}

        # ── Direct children: hard delete ──────────────────────────
        r = await self._session.execute(
            sa_delete(OriginalInputAuditRow).where(
                OriginalInputAuditRow.context_id == context_id
            )
        )
        counts["original_input_audit"] = r.rowcount or 0

        r = await self._session.execute(
            sa_delete(ContextArtifactRefRow).where(
                ContextArtifactRefRow.context_id == context_id
            )
        )
        counts["context_artifact_refs"] = r.rowcount or 0

        r = await self._session.execute(
            sa_delete(ContextTaskRefRow).where(
                ContextTaskRefRow.context_id == context_id
            )
        )
        counts["context_task_refs"] = r.rowcount or 0

        r = await self._session.execute(
            sa_delete(ContextMessageRow).where(
                ContextMessageRow.context_id == context_id
            )
        )
        counts["context_messages"] = r.rowcount or 0

        # ── RV3_GAP_01: conversation_memories (HARD DELETE) ───────
        # Late import to avoid a circular dependency at module load:
        # app.models.memory -> app.database -> ... (no cycle back here,
        # but keeping the import local makes the dependency explicit).
        from app.models.memory import ConversationMemory

        r = await self._session.execute(
            sa_delete(ConversationMemory).where(
                ConversationMemory.session_id.like(f"{context_id}:%")
            )
        )
        counts["conversation_memories"] = r.rowcount or 0

        # ── RV3_GAP_03: run_trace_events (REDACT metadata) ────────
        # Redaction runs BEFORE run_history update because we need
        # the run_id list from run_history.context_id.
        from app.models.run_history import RunHistoryModel
        from app.models.run_trace import RunTraceEventModel

        run_ids_stmt = select(RunHistoryModel.run_id).where(
            RunHistoryModel.context_id == context_id
        )
        run_ids = [
            row[0]
            for row in (await self._session.execute(run_ids_stmt)).all()
        ]
        if run_ids:
            r = await self._session.execute(
                sa_update(RunTraceEventModel)
                .where(RunTraceEventModel.run_id.in_(run_ids))
                .values(safe_metadata_json={"redacted": redaction_marker})
            )
            counts["run_trace_events_redacted"] = r.rowcount or 0
        else:
            counts["run_trace_events_redacted"] = 0

        # ── RV3_GAP_02: run_history (REDACT content, clear context_id) ──
        r = await self._session.execute(
            sa_update(RunHistoryModel)
            .where(RunHistoryModel.context_id == context_id)
            .values(
                input_text=redaction_marker,
                output_summary=redaction_marker,
                context_id=None,
            )
        )
        counts["run_history_redacted"] = r.rowcount or 0

        # ── RV3_GAP_04: audit_logs (REDACT PHI-bearing columns) ──
        # Row retained for compliance audit trail; only content redacted.
        from app.models.audit_log import AuditLog

        r = await self._session.execute(
            sa_update(AuditLog)
            .where(AuditLog.resource_id == context_id)
            .values(
                details={"redacted": redaction_marker},
                model_input_summary=redaction_marker,
                model_output_summary=redaction_marker,
                tool_calls_made={"redacted": redaction_marker},
            )
        )
        counts["audit_logs_redacted"] = r.rowcount or 0

        # ── Parent row: hard delete last ──────────────────────────
        row = await self._session.get(ContextRow, context_id)
        assert row is not None
        await self._session.delete(row)
        counts["contexts"] = 1

        await self._session.commit()
        return counts

    async def get_messages(
        self, context_id: str, *, message_id: str | None = None
    ) -> list[ContextMessage]:
        await self._require_valid_id(context_id)
        stmt = select(ContextMessageRow).where(
            ContextMessageRow.context_id == context_id
        )
        if message_id is not None:
            stmt = stmt.where(ContextMessageRow.message_id == message_id)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            ContextMessage(
                message_id=r.message_id,
                role=r.role,
                parts=json.loads(r.parts_json),
                timestamp=_as_utc(r.timestamp),
                redacted=r.redacted,
                metadata=json.loads(r.metadata_json) if r.metadata_json else {},
            )
            for r in rows
        ]

    async def add_message(
        self, context_id: str, message: ContextMessage
    ) -> ContextMessage:
        await self._require_context_exists(context_id)
        row = ContextMessageRow(
            context_id=context_id,
            message_id=message.message_id,
            role=message.role,
            parts_json=json.dumps(message.parts, ensure_ascii=False),
            timestamp=message.timestamp,
            redacted=message.redacted,
            metadata_json=message.metadata.model_dump_json()
            if hasattr(message.metadata, "model_dump_json")
            else json.dumps(message.metadata, ensure_ascii=False),
        )
        self._session.add(row)
        await self._session.commit()
        return message

    async def get_tasks(self, context_id: str) -> list[ContextTaskRef]:
        await self._require_valid_id(context_id)
        stmt = select(ContextTaskRefRow).where(
            ContextTaskRefRow.context_id == context_id
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            ContextTaskRef(
                task_id=r.task_id,
                state=r.state,
                started_at=_as_utc(r.started_at),
                completed_at=_as_utc(r.completed_at) if r.completed_at else None,
            )
            for r in rows
        ]

    async def add_task(
        self, context_id: str, task_ref: ContextTaskRef
    ) -> ContextTaskRef:
        await self._require_context_exists(context_id)
        row = ContextTaskRefRow(
            context_id=context_id,
            task_id=task_ref.task_id,
            state=task_ref.state,
            started_at=task_ref.started_at,
            completed_at=task_ref.completed_at,
        )
        self._session.add(row)
        await self._session.commit()
        return task_ref

    async def get_artifacts(self, context_id: str) -> list[ContextArtifactRef]:
        await self._require_valid_id(context_id)
        stmt = select(ContextArtifactRefRow).where(
            ContextArtifactRefRow.context_id == context_id
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [
            ContextArtifactRef(
                artifact_id=r.artifact_id,
                name=r.name,
                mime_type=r.mime_type,
                url=r.url,
            )
            for r in rows
        ]

    async def add_artifact(
        self, context_id: str, artifact_ref: ContextArtifactRef
    ) -> ContextArtifactRef:
        await self._require_context_exists(context_id)
        row = ContextArtifactRefRow(
            context_id=context_id,
            artifact_id=artifact_ref.artifact_id,
            name=artifact_ref.name,
            mime_type=artifact_ref.mime_type,
            url=artifact_ref.url,
        )
        self._session.add(row)
        await self._session.commit()
        return artifact_ref

    async def list_by_agent(
        self,
        agent_id: str,
        *,
        status: ContextStatus | None = None,
        limit: int = 100,
    ) -> list[Context]:
        """Admin/operator listing. NOT a cross-contextId read — returns whole Contexts."""
        stmt = select(ContextRow).where(ContextRow.agent_id == agent_id)
        if status is not None:
            stmt = stmt.where(ContextRow.status == status.value)
        stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._row_to_context(r) for r in rows]

    async def list_all(
        self,
        *,
        status: ContextStatus | None = None,
        limit: int = 1000,
    ) -> list[Context]:
        """GC sweep helper: list contexts across all agents."""
        stmt = select(ContextRow)
        if status is not None:
            stmt = stmt.where(ContextRow.status == status.value)
        stmt = stmt.limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._row_to_context(r) for r in rows]