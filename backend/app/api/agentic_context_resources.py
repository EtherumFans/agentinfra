"""First-class Agentic v2 Context, Task, and Artifact resources.

The A2A message bindings own task execution.  This router exposes the same
durable, tenant-owned rows as independently addressable resources without
creating a second source of truth.  Only route-redacted, encrypted-at-rest
message content is projected; internal correlation metadata is never returned.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.icoder.agent_runtime.a2a.v1.protocol import (
    A2A_V1_HEADER,
    A2A_V1_VERSION,
    A2AV1ProtocolError,
    project_v0_3_message,
)
from app.icoder.agent_runtime.a2a.v1.routes import _task_to_v1
from app.icoder.agent_runtime.a2a.v1.artifact_store import load_task_artifact
from app.icoder.agent_runtime.a2a.v1.artifact_object_store import (
    ArtifactObjectError,
    ArtifactObjectIntegrityError,
    ArtifactObjectNotFound,
    DownloadGrantError,
    actor_fingerprint,
    authorize_download,
    consume_download,
    create_and_scan_object,
    decode_upload,
    delete_object,
    get_object,
    list_objects,
    project_artifact_objects,
    project_object,
)
from app.icoder.agent_runtime.context.context_isolation import ContextIsolationError
from app.icoder.agent_runtime.context.context_lifecycle import ContextLifecycle
from app.icoder.agent_runtime.context.context_repository import ContextRepository
from app.icoder.agent_runtime.context.db_models import (
    A2AArtifactObjectRow,
    A2ATaskExecutionRow,
    ContextRow,
    ContextTaskRefRow,
)
from app.middleware.audit import log_action
from app.middleware.auth import (
    get_current_organization,
    get_current_user_or_oauth_client,
)
from app.models.organization import Organization
from app.services.phi_encryption import decrypt_phi


router = APIRouter(
    prefix="/api/v2/agentic/contexts",
    tags=["agentic-context-resources"],
)
artifact_object_router = APIRouter(
    prefix="/api/v2/agentic/artifact-objects",
    tags=["agentic-artifact-objects"],
)

_CURSOR_MAX = 2048
_DEFAULT_PAGE_SIZE = 50
_MAX_PAGE_SIZE = 200


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AgenticTask(_StrictModel):
    id: str
    context_id: str = Field(alias="contextId")
    status: dict[str, Any]
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgenticContextSummary(_StrictModel):
    id: str
    agent_id: str = Field(alias="agentId")
    task_count: int = Field(alias="taskCount")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    expires_at: datetime | None = Field(alias="expiresAt")


class AgenticContext(AgenticContextSummary):
    tasks: list[AgenticTask]


class AgenticContextPage(_StrictModel):
    contexts: list[AgenticContextSummary]
    next_page_token: str | None = Field(alias="nextPageToken")
    total_size: int = Field(alias="totalSize")


class AgenticTaskPage(_StrictModel):
    tasks: list[AgenticTask]
    next_page_token: str | None = Field(alias="nextPageToken")
    total_size: int = Field(alias="totalSize")


class AgenticArtifact(_StrictModel):
    artifact_id: str = Field(alias="artifactId")
    name: str | None = None
    description: str | None = None
    parts: list[dict[str, Any]]
    metadata: dict[str, Any] = Field(default_factory=dict)
    extensions: list[str] = Field(default_factory=list)


class AgenticArtifactObjectUpload(_StrictModel):
    raw: str = Field(min_length=4, max_length=7_000_000)
    filename: str = Field(min_length=1, max_length=180)
    media_type: str = Field(alias="mediaType", min_length=1, max_length=128)
    data_classification: Literal["deidentified", "clinical-sensitive"] = Field(
        default="deidentified", alias="dataClassification"
    )


class AgenticArtifactObject(_StrictModel):
    object_id: str = Field(alias="objectId")
    artifact_id: str = Field(alias="artifactId")
    filename: str
    media_type: str = Field(alias="mediaType")
    size_bytes: int = Field(alias="sizeBytes")
    sha256: str
    status: Literal["quarantined", "available", "rejected"]
    malware_scan_status: Literal["pending", "clean", "infected", "error"] = Field(
        alias="malwareScanStatus"
    )
    dlp_scan_status: Literal["pending", "clear", "restricted", "blocked", "error"] = Field(
        alias="dlpScanStatus"
    )
    data_classification: Literal["deidentified", "clinical-sensitive"] = Field(
        alias="dataClassification"
    )
    rejection_code: str | None = Field(default=None, alias="rejectionCode")
    scan_engine: str = Field(alias="scanEngine")
    created_at: datetime = Field(alias="createdAt")
    scanned_at: datetime | None = Field(default=None, alias="scannedAt")


class AgenticArtifactObjectPage(_StrictModel):
    objects: list[AgenticArtifactObject]
    total_size: int = Field(alias="totalSize")


class AgenticDownloadAuthorizationRequest(_StrictModel):
    purpose_of_use: Literal["treatment", "payment", "healthcare_operations"] = Field(
        alias="purposeOfUse"
    )
    expires_in_seconds: int = Field(default=60, alias="expiresInSeconds", ge=1, le=300)


class AgenticDownloadAuthorization(_StrictModel):
    object_id: str = Field(alias="objectId")
    expires_at: datetime = Field(alias="expiresAt")
    single_use: bool = Field(alias="singleUse")
    purpose_of_use: str = Field(alias="purposeOfUse")
    part: dict[str, Any]


def _set_response_headers(response: Response) -> None:
    response.headers[A2A_V1_HEADER] = A2A_V1_VERSION
    response.headers["Cache-Control"] = "no-store"


def _require_any_scope(
    principal: tuple[Any, dict | None], allowed: tuple[str, ...]
) -> None:
    _user, client = principal
    if client is None:
        return
    granted = set(client.get("scopes") or [])
    if granted.isdisjoint(allowed):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "insufficient_scope",
                "required_any_scope": list(allowed),
                "granted_scopes": sorted(granted),
            },
        )


def _principal(
    principal: tuple[Any, dict | None],
) -> tuple[str, str | None, str | None]:
    user, client = principal
    if client:
        actor_type = (
            "runtime_token" if client.get("type") == "runtime_token" else "oauth_client"
        )
        actor_id = str(
            client.get("client_id") or client.get("preview_session_id") or "unknown"
        )
        return actor_type, getattr(user, "id", None), actor_id
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return "user", str(user.id), getattr(user, "email", None)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _db_timestamp(value: datetime) -> datetime:
    """Convert an API timestamp to the schema's UTC-naive representation."""
    return _utc(value).astimezone(timezone.utc).replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat().replace("+00:00", "Z")


def _cursor_key() -> bytes:
    return hashlib.sha256(
        (settings.SECRET_KEY + ":agentic-context-resource-cursor").encode("utf-8")
    ).digest()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def _encode_cursor(payload: dict[str, Any]) -> str:
    body = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    signature = hmac.new(_cursor_key(), body, hashlib.sha256).digest()
    return f"{_b64encode(body)}.{_b64encode(signature)}"


def _decode_cursor(
    token: str,
    *,
    resource: str,
    organization_id: str,
    context_id: str | None = None,
    filters: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    if not token or len(token) > _CURSOR_MAX or token.count(".") != 1:
        raise HTTPException(status_code=400, detail="pageToken is malformed")
    encoded_body, encoded_signature = token.split(".", 1)
    try:
        body = _b64decode(encoded_body)
        signature = _b64decode(encoded_signature)
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail="pageToken is malformed") from exc
    expected = hmac.new(_cursor_key(), body, hashlib.sha256).digest()
    canonical = (
        _b64encode(body) == encoded_body
        and _b64encode(signature) == encoded_signature
    )
    if (
        not canonical
        or not hmac.compare_digest(signature, expected)
        or not isinstance(payload, dict)
    ):
        raise HTTPException(status_code=400, detail="pageToken signature is invalid")
    if (
        payload.get("v") != 1
        or payload.get("resource") != resource
        or payload.get("org") != organization_id
        or payload.get("context") != context_id
        or payload.get("filters") != (filters or {})
    ):
        raise HTTPException(
            status_code=400,
            detail="pageToken does not belong to this resource query",
        )
    return payload


def _parse_cursor_time(value: Any) -> datetime:
    if not isinstance(value, str):
        raise HTTPException(status_code=400, detail="pageToken anchor is invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="pageToken anchor is invalid") from exc
    return _db_timestamp(parsed)


async def _require_context(
    db: AsyncSession, organization_id: str, context_id: str
) -> ContextRow:
    row = (
        await db.execute(
            select(ContextRow).where(
                ContextRow.id == context_id,
                ContextRow.organization_id == organization_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Context not found")
    return row


async def _require_task(
    db: AsyncSession,
    organization_id: str,
    context_id: str,
    task_id: str,
) -> tuple[ContextRow, ContextTaskRefRow]:
    context = await _require_context(db, organization_id, context_id)
    task = (
        await db.execute(
            select(ContextTaskRefRow).where(
                ContextTaskRefRow.context_id == context_id,
                ContextTaskRefRow.task_id == task_id,
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return context, task


def _context_summary(row: ContextRow, task_count: int) -> AgenticContextSummary:
    return AgenticContextSummary(
        id=row.id,
        agentId=row.agent_id,
        taskCount=task_count,
        createdAt=_utc(row.created_at),
        updatedAt=_utc(row.updated_at),
        expiresAt=_utc(row.expires_at) if row.expires_at else None,
    )


def _project_persisted_message(
    message: Any, *, context_id: str, task_id: str
) -> dict[str, Any]:
    projected = project_v0_3_message(
        {
            "messageId": message.message_id,
            "contextId": context_id,
            "role": "agent" if message.role == "agent" else "user",
            "parts": message.parts,
            # Context persistence metadata is server-internal correlation and
            # audit state.  It is intentionally not part of the public message.
            "metadata": {},
        }
    )
    projected["taskId"] = task_id
    return projected


async def _request_message_fallback(
    db: AsyncSession, task: ContextTaskRefRow
) -> dict[str, Any] | None:
    execution = await db.get(A2ATaskExecutionRow, task.task_id)
    if execution is None:
        return None
    try:
        payload = json.loads(decrypt_phi(execution.request_json) or "{}")
        legacy_params = payload.get("legacy_params")
        message = legacy_params.get("message") if isinstance(legacy_params, dict) else None
        if not isinstance(message, dict):
            return None
        safe_message = dict(message)
        safe_message["metadata"] = {}
        projected = project_v0_3_message(safe_message)
    except (A2AV1ProtocolError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500, detail="Task history is temporarily unavailable"
        ) from exc
    projected["contextId"] = task.context_id
    projected["taskId"] = task.task_id
    return projected


async def _project_task(
    db: AsyncSession,
    task: ContextTaskRefRow,
    *,
    history_length: int | None,
    context_messages: list[Any] | None = None,
) -> AgenticTask:
    try:
        projected = await _task_to_v1(db, task, include_artifacts=True)
    except A2AV1ProtocolError as exc:
        raise HTTPException(
            status_code=exc.http_status,
            detail=exc.message,
        ) from exc

    try:
        object_rows = list(
            (
                await db.execute(
                    select(A2AArtifactObjectRow).where(
                        A2AArtifactObjectRow.context_id == task.context_id,
                        A2AArtifactObjectRow.task_id == task.task_id,
                    )
                )
            ).scalars()
        )
        by_artifact: dict[str, list[A2AArtifactObjectRow]] = {}
        for row in object_rows:
            by_artifact.setdefault(row.artifact_id, []).append(row)
        projected["artifacts"] = [
            project_artifact_objects(
                artifact,
                sorted(
                    by_artifact.get(str(artifact.get("artifactId") or ""), []),
                    key=lambda row: (row.created_at, row.object_id),
                ),
            )
            for artifact in projected.get("artifacts", [])
        ]
    except ArtifactObjectError as exc:
        raise HTTPException(
            status_code=500,
            detail="Artifact object metadata is temporarily unavailable",
        ) from exc

    messages = context_messages
    if messages is None:
        try:
            messages = await ContextRepository(db).get_messages(task.context_id)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail="Task history is temporarily unavailable"
            ) from exc

    history = [
        _project_persisted_message(
            message, context_id=task.context_id, task_id=task.task_id
        )
        for message in messages
        if isinstance(message.metadata, dict)
        and str(message.metadata.get("a2a_v1_task_id") or "") == task.task_id
    ]

    if history_length != 0 and not any(
        item.get("role") == "ROLE_USER" for item in history
    ):
        fallback = await _request_message_fallback(db, task)
        if fallback is not None:
            history.insert(0, fallback)

    status_message = projected.get("status", {}).get("message")
    if isinstance(status_message, dict):
        status_message = dict(status_message)
        status_message["taskId"] = task.task_id
        # The durable result may contain server-owned run/connector metadata.
        # The public Context resource returns message content and stable A2A
        # identity only; operational metadata remains available through trace.
        status_message["metadata"] = {}
        projected["status"]["message"] = status_message
        known_message_ids = {item.get("messageId") for item in history}
        if status_message.get("messageId") not in known_message_ids:
            history.append(status_message)

    if history_length is not None:
        history = history[-history_length:] if history_length else []
    projected["history"] = history
    return AgenticTask.model_validate(projected)


async def _audit(
    db: AsyncSession,
    principal: tuple[Any, dict | None],
    organization_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    details: dict[str, Any],
) -> Any:
    actor_type, user_id, username = _principal(principal)
    return await log_action(
        db,
        user_id,
        username,
        action,
        resource_type,
        resource_id,
        details={"actor_type": actor_type, **details},
        organization_id=organization_id,
    )


@router.get("", response_model=AgenticContextPage)
async def list_contexts(
    response: Response,
    agent_id: str | None = Query(default=None, alias="agentId", max_length=128),
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    page_size: int = Query(
        default=_DEFAULT_PAGE_SIZE, alias="pageSize", ge=1, le=_MAX_PAGE_SIZE
    ),
    page_token: str | None = Query(
        default=None, alias="pageToken", max_length=_CURSOR_MAX
    ),
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgenticContextPage:
    _require_any_scope(principal, ("contexts:read", "api:read"))
    _set_response_headers(response)
    if from_time and to_time and _utc(from_time) >= _utc(to_time):
        raise HTTPException(status_code=400, detail="from must be earlier than to")

    filters = {
        "agentId": agent_id,
        "from": _iso(from_time),
        "to": _iso(to_time),
    }
    predicates = [ContextRow.organization_id == organization.id]
    if agent_id:
        predicates.append(ContextRow.agent_id == agent_id)
    if from_time:
        predicates.append(ContextRow.created_at >= _db_timestamp(from_time))
    if to_time:
        predicates.append(ContextRow.created_at < _db_timestamp(to_time))

    total_size = int(
        (
            await db.execute(
                select(func.count()).select_from(ContextRow).where(*predicates)
            )
        ).scalar_one()
    )
    page_predicates = list(predicates)
    if page_token:
        cursor = _decode_cursor(
            page_token,
            resource="contexts",
            organization_id=organization.id,
            filters=filters,
        )
        anchor_time = _parse_cursor_time(cursor.get("createdAt"))
        anchor_id = cursor.get("id")
        if not isinstance(anchor_id, str):
            raise HTTPException(status_code=400, detail="pageToken anchor is invalid")
        page_predicates.append(
            or_(
                ContextRow.created_at < anchor_time,
                and_(ContextRow.created_at == anchor_time, ContextRow.id < anchor_id),
            )
        )

    rows = list(
        (
            await db.execute(
                select(ContextRow)
                .where(*page_predicates)
                .order_by(ContextRow.created_at.desc(), ContextRow.id.desc())
                .limit(page_size + 1)
            )
        ).scalars()
    )
    has_more = len(rows) > page_size
    page = rows[:page_size]
    counts: dict[str, int] = {}
    if page:
        count_rows = (
            await db.execute(
                select(
                    ContextTaskRefRow.context_id,
                    func.count(ContextTaskRefRow.task_id),
                )
                .where(ContextTaskRefRow.context_id.in_([row.id for row in page]))
                .group_by(ContextTaskRefRow.context_id)
            )
        ).all()
        counts = {str(context_id): int(count) for context_id, count in count_rows}
    next_page_token = None
    if has_more and page:
        anchor = page[-1]
        next_page_token = _encode_cursor(
            {
                "v": 1,
                "resource": "contexts",
                "org": organization.id,
                "context": None,
                "filters": filters,
                "createdAt": _iso(anchor.created_at),
                "id": anchor.id,
            }
        )
    await _audit(
        db,
        principal,
        organization.id,
        "agentic.context.list",
        "context",
        None,
        {"page_size": page_size},
    )
    return AgenticContextPage(
        contexts=[_context_summary(row, counts.get(row.id, 0)) for row in page],
        nextPageToken=next_page_token,
        totalSize=total_size,
    )


@router.get("/{context_id}", response_model=AgenticContext)
async def get_context(
    context_id: str,
    response: Response,
    history_length: int | None = Query(
        default=None, alias="historyLength", ge=0, le=100
    ),
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgenticContext:
    _require_any_scope(principal, ("contexts:read", "api:read"))
    _set_response_headers(response)
    context = await _require_context(db, organization.id, context_id)
    task_rows = list(
        (
            await db.execute(
                select(ContextTaskRefRow)
                .where(ContextTaskRefRow.context_id == context_id)
                .order_by(ContextTaskRefRow.started_at, ContextTaskRefRow.task_id)
            )
        ).scalars()
    )
    try:
        messages = await ContextRepository(db).get_messages(context_id)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Context history is temporarily unavailable"
        ) from exc
    tasks = [
        await _project_task(
            db,
            task,
            history_length=history_length,
            context_messages=messages,
        )
        for task in task_rows
    ]
    await _audit(
        db,
        principal,
        organization.id,
        "agentic.context.read",
        "context",
        context_id,
        {"page_size": history_length} if history_length is not None else {},
    )
    summary = _context_summary(context, len(tasks))
    return AgenticContext(**summary.model_dump(by_alias=True), tasks=tasks)


@router.delete("/{context_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_context(
    context_id: str,
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_any_scope(principal, ("contexts:write", "api:write"))
    await _require_context(db, organization.id, context_id)
    try:
        await ContextLifecycle(ContextRepository(db)).destroy_now(
            context_id,
            organization_id=organization.id,
            reason="api_v2_user_requested",
        )
    except ContextIsolationError as exc:
        raise HTTPException(status_code=404, detail="Context not found") from exc
    await _audit(
        db,
        principal,
        organization.id,
        "agentic.context.delete",
        "context",
        context_id,
        {"reason_code": "api_v2_user_requested"},
    )
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={A2A_V1_HEADER: A2A_V1_VERSION, "Cache-Control": "no-store"},
    )


@router.get("/{context_id}/tasks", response_model=AgenticTaskPage)
async def list_context_tasks(
    context_id: str,
    response: Response,
    page_size: int = Query(
        default=_DEFAULT_PAGE_SIZE, alias="pageSize", ge=1, le=_MAX_PAGE_SIZE
    ),
    page_token: str | None = Query(
        default=None, alias="pageToken", max_length=_CURSOR_MAX
    ),
    history_length: int = Query(default=0, alias="historyLength", ge=0, le=100),
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgenticTaskPage:
    _require_any_scope(principal, ("contexts:read", "api:read"))
    _set_response_headers(response)
    await _require_context(db, organization.id, context_id)
    total_size = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ContextTaskRefRow)
                .where(ContextTaskRefRow.context_id == context_id)
            )
        ).scalar_one()
    )
    predicates = [ContextTaskRefRow.context_id == context_id]
    filters = {"historyLength": str(history_length)}
    if page_token:
        cursor = _decode_cursor(
            page_token,
            resource="context-tasks",
            organization_id=organization.id,
            context_id=context_id,
            filters=filters,
        )
        anchor_time = _parse_cursor_time(cursor.get("startedAt"))
        anchor_id = cursor.get("id")
        if not isinstance(anchor_id, str):
            raise HTTPException(status_code=400, detail="pageToken anchor is invalid")
        predicates.append(
            or_(
                ContextTaskRefRow.started_at > anchor_time,
                and_(
                    ContextTaskRefRow.started_at == anchor_time,
                    ContextTaskRefRow.task_id > anchor_id,
                ),
            )
        )
    rows = list(
        (
            await db.execute(
                select(ContextTaskRefRow)
                .where(*predicates)
                .order_by(ContextTaskRefRow.started_at, ContextTaskRefRow.task_id)
                .limit(page_size + 1)
            )
        ).scalars()
    )
    has_more = len(rows) > page_size
    page = rows[:page_size]
    messages = (
        await ContextRepository(db).get_messages(context_id)
        if history_length
        else []
    )
    tasks = [
        await _project_task(
            db,
            task,
            history_length=history_length,
            context_messages=messages,
        )
        for task in page
    ]
    next_page_token = None
    if has_more and page:
        anchor = page[-1]
        next_page_token = _encode_cursor(
            {
                "v": 1,
                "resource": "context-tasks",
                "org": organization.id,
                "context": context_id,
                "filters": filters,
                "startedAt": _iso(anchor.started_at),
                "id": anchor.task_id,
            }
        )
    await _audit(
        db,
        principal,
        organization.id,
        "agentic.context.task.list",
        "context",
        context_id,
        {"page_size": page_size},
    )
    return AgenticTaskPage(
        tasks=tasks,
        nextPageToken=next_page_token,
        totalSize=total_size,
    )


@router.get("/{context_id}/tasks/{task_id}", response_model=AgenticTask)
async def get_context_task(
    context_id: str,
    task_id: str,
    response: Response,
    history_length: int | None = Query(
        default=None, alias="historyLength", ge=0, le=100
    ),
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgenticTask:
    _require_any_scope(principal, ("contexts:read", "api:read"))
    _set_response_headers(response)
    _context, task = await _require_task(
        db, organization.id, context_id, task_id
    )
    projected = await _project_task(db, task, history_length=history_length)
    await _audit(
        db,
        principal,
        organization.id,
        "agentic.context.task.read",
        "agentic_task",
        task_id,
        {
            "context_id": context_id,
            **({"page_size": history_length} if history_length is not None else {}),
        },
    )
    return projected


@router.get(
    "/{context_id}/tasks/{task_id}/artifacts/{artifact_id}",
    response_model=AgenticArtifact,
)
async def get_task_artifact(
    context_id: str,
    task_id: str,
    artifact_id: str,
    response: Response,
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgenticArtifact:
    _require_any_scope(principal, ("contexts:read", "api:read"))
    _set_response_headers(response)
    _context, task = await _require_task(
        db, organization.id, context_id, task_id
    )
    try:
        artifact = await load_task_artifact(
            db,
            context_id=context_id,
            task_id=task_id,
            artifact_id=artifact_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Artifact is temporarily unavailable"
        ) from exc
    if artifact is None:
        # Compatibility-only lookup for Tasks completed before migration 050.
        projected = await _project_task(
            db, task, history_length=0, context_messages=[]
        )
        artifact = next(
            (
                item
                for item in projected.artifacts
                if str(item.get("artifactId") or "") == artifact_id
            ),
            None,
        )
    if artifact is None:
        # Do not fall back to context-level artifact references: the legacy
        # table cannot prove Task ownership and would weaken isolation.
        raise HTTPException(status_code=404, detail="Artifact not found")
    try:
        artifact = project_artifact_objects(
            artifact,
            await list_objects(
                db,
                organization_id=organization.id,
                context_id=context_id,
                task_id=task_id,
                artifact_id=artifact_id,
            ),
        )
    except ArtifactObjectError as exc:
        raise HTTPException(
            status_code=500,
            detail="Artifact object metadata is temporarily unavailable",
        ) from exc
    await _audit(
        db,
        principal,
        organization.id,
        "agentic.context.task.artifact.read",
        "agentic_artifact",
        artifact_id,
        {"context_id": context_id, "task_id": task_id},
    )
    return AgenticArtifact.model_validate(artifact)


def _object_error(exc: ArtifactObjectError) -> HTTPException:
    detail = {"code": exc.code, "message": str(exc)}
    if isinstance(exc, ArtifactObjectNotFound):
        return HTTPException(status_code=404, detail=detail)
    if isinstance(exc, ArtifactObjectIntegrityError):
        return HTTPException(status_code=500, detail=detail)
    if isinstance(exc, DownloadGrantError):
        status_code = 410 if exc.code in {
            "DOWNLOAD_GRANT_EXPIRED",
            "DOWNLOAD_GRANT_CONSUMED",
        } else 409
        if exc.code == "DOWNLOAD_GRANT_INVALID":
            status_code = 404
        return HTTPException(status_code=status_code, detail=detail)
    return HTTPException(status_code=400, detail=detail)


async def _require_object_audit(db: AsyncSession, entry: Any) -> None:
    if entry is None:
        raise HTTPException(
            status_code=503,
            detail="Artifact object audit trail is temporarily unavailable",
        )
    try:
        await db.flush()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Artifact object audit trail is temporarily unavailable",
        ) from exc


def _require_object_audit_enabled() -> None:
    if os.environ.get("ICODER_AUDIT_WRITE_PAUSED", "false").casefold() == "true":
        raise HTTPException(
            status_code=503,
            detail="Artifact object audit trail is temporarily unavailable",
        )


def _actor_fingerprint_from_principal(
    principal: tuple[Any, dict | None],
) -> tuple[str, str]:
    actor_type, user_id, actor_name = _principal(principal)
    # Machine grants belong to the exact OAuth/runtime client, not merely its
    # owner. Two clients owned by the same user must never consume each
    # other's one-time clinical object grant.
    actor_id = (
        actor_name
        if actor_type in {"oauth_client", "runtime_token"}
        else user_id or actor_name
    )
    if not actor_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return actor_type, actor_fingerprint(actor_type, actor_id)


async def _require_durable_artifact(
    db: AsyncSession, *, context_id: str, task_id: str, artifact_id: str
) -> dict[str, Any]:
    try:
        artifact = await load_task_artifact(
            db,
            context_id=context_id,
            task_id=task_id,
            artifact_id=artifact_id,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail="Artifact is temporarily unavailable"
        ) from exc
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return artifact


@router.post(
    "/{context_id}/tasks/{task_id}/artifacts/{artifact_id}/objects",
    response_model=AgenticArtifactObject,
    status_code=status.HTTP_201_CREATED,
)
async def upload_artifact_object(
    context_id: str,
    task_id: str,
    artifact_id: str,
    body: AgenticArtifactObjectUpload,
    response: Response,
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgenticArtifactObject:
    _require_any_scope(principal, ("contexts:write", "api:write"))
    _require_object_audit_enabled()
    _set_response_headers(response)
    context, _task = await _require_task(db, organization.id, context_id, task_id)
    if context.status != "active" or _utc(context.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=409, detail="Context no longer accepts Artifact objects"
        )
    await _require_durable_artifact(
        db, context_id=context_id, task_id=task_id, artifact_id=artifact_id
    )
    actor_type, actor_id_hash = _actor_fingerprint_from_principal(principal)
    try:
        content = decode_upload(body.raw)
        row = await create_and_scan_object(
            db,
            organization_id=organization.id,
            context_id=context_id,
            task_id=task_id,
            artifact_id=artifact_id,
            filename=body.filename,
            media_type=body.media_type,
            data_classification=body.data_classification,
            content=content,
            actor_type=actor_type,
            actor_id_hash=actor_id_hash,
        )
    except ArtifactObjectError as exc:
        raise _object_error(exc) from exc
    audit_entry = await _audit(
        db,
        principal,
        organization.id,
        "agentic.artifact.object.upload",
        "agentic_artifact_object",
        row.object_id,
        {
            "context_id": context_id,
            "task_id": task_id,
            "artifact_id": artifact_id,
            "status": row.status,
            "media_type": row.detected_media_type or row.declared_media_type,
            "size_bytes": row.size_bytes,
            "data_classification": row.data_classification,
            "malware_scan_status": row.malware_scan_status,
            "dlp_scan_status": row.dlp_scan_status,
            "rejection_code": row.rejection_code,
        },
    )
    await _require_object_audit(db, audit_entry)
    return AgenticArtifactObject.model_validate(project_object(row))


@router.get(
    "/{context_id}/tasks/{task_id}/artifacts/{artifact_id}/objects",
    response_model=AgenticArtifactObjectPage,
)
async def list_artifact_objects(
    context_id: str,
    task_id: str,
    artifact_id: str,
    response: Response,
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgenticArtifactObjectPage:
    _require_any_scope(principal, ("contexts:read", "api:read"))
    _set_response_headers(response)
    await _require_task(db, organization.id, context_id, task_id)
    await _require_durable_artifact(
        db, context_id=context_id, task_id=task_id, artifact_id=artifact_id
    )
    rows = await list_objects(
        db,
        organization_id=organization.id,
        context_id=context_id,
        task_id=task_id,
        artifact_id=artifact_id,
    )
    audit_entry = await _audit(
        db,
        principal,
        organization.id,
        "agentic.artifact.object.list",
        "agentic_artifact",
        artifact_id,
        {"context_id": context_id, "task_id": task_id, "total_size": len(rows)},
    )
    await _require_object_audit(db, audit_entry)
    return AgenticArtifactObjectPage(
        objects=[
            AgenticArtifactObject.model_validate(project_object(row)) for row in rows
        ],
        totalSize=len(rows),
    )


@router.post(
    "/{context_id}/tasks/{task_id}/artifacts/{artifact_id}/objects/"
    "{object_id}:authorize-download",
    response_model=AgenticDownloadAuthorization,
)
async def authorize_artifact_object_download(
    context_id: str,
    task_id: str,
    artifact_id: str,
    object_id: str,
    body: AgenticDownloadAuthorizationRequest,
    request: Request,
    response: Response,
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgenticDownloadAuthorization:
    _require_any_scope(principal, ("contexts:read", "api:read"))
    _require_object_audit_enabled()
    _set_response_headers(response)
    context, _task = await _require_task(db, organization.id, context_id, task_id)
    if context.status == "expired" or _utc(context.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Context has expired")
    await _require_durable_artifact(
        db, context_id=context_id, task_id=task_id, artifact_id=artifact_id
    )
    actor_type, actor_id_hash = _actor_fingerprint_from_principal(principal)
    try:
        row = await get_object(
            db,
            organization_id=organization.id,
            context_id=context_id,
            task_id=task_id,
            artifact_id=artifact_id,
            object_id=object_id,
        )
        grant = await authorize_download(
            db,
            row=row,
            actor_type=actor_type,
            actor_id_hash=actor_id_hash,
            purpose_of_use=body.purpose_of_use,
            ttl_seconds=body.expires_in_seconds,
        )
    except ArtifactObjectError as exc:
        raise _object_error(exc) from exc
    download_url = str(
        request.url_for(
            "download_managed_artifact_object",
            grant_id=grant.grant_id,
        )
    )
    audit_entry = await _audit(
        db,
        principal,
        organization.id,
        "agentic.artifact.object.download.authorize",
        "agentic_artifact_object",
        object_id,
        {
            "context_id": context_id,
            "task_id": task_id,
            "artifact_id": artifact_id,
            "purpose_of_use": body.purpose_of_use,
            "expires_in_seconds": body.expires_in_seconds,
            "single_use": True,
        },
    )
    await _require_object_audit(db, audit_entry)
    metadata = project_object(row)
    part = {
        "url": download_url,
        "filename": metadata["filename"],
        "mediaType": metadata["mediaType"],
        "metadata": {
            "objectId": object_id,
            "sha256": metadata["sha256"],
            "sizeBytes": metadata["sizeBytes"],
            "expiresAt": _iso(grant.expires_at),
            "singleUse": True,
        },
    }
    return AgenticDownloadAuthorization(
        objectId=object_id,
        expiresAt=_utc(grant.expires_at),
        singleUse=True,
        purposeOfUse=body.purpose_of_use,
        part=part,
    )


@router.delete(
    "/{context_id}/tasks/{task_id}/artifacts/{artifact_id}/objects/{object_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_artifact_object(
    context_id: str,
    task_id: str,
    artifact_id: str,
    object_id: str,
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_any_scope(principal, ("contexts:write", "api:write"))
    _require_object_audit_enabled()
    await _require_task(db, organization.id, context_id, task_id)
    await _require_durable_artifact(
        db, context_id=context_id, task_id=task_id, artifact_id=artifact_id
    )
    try:
        await delete_object(
            db,
            organization_id=organization.id,
            context_id=context_id,
            task_id=task_id,
            artifact_id=artifact_id,
            object_id=object_id,
        )
    except ArtifactObjectError as exc:
        raise _object_error(exc) from exc
    audit_entry = await _audit(
        db,
        principal,
        organization.id,
        "agentic.artifact.object.delete",
        "agentic_artifact_object",
        object_id,
        {"context_id": context_id, "task_id": task_id, "artifact_id": artifact_id},
    )
    await _require_object_audit(db, audit_entry)
    return Response(
        status_code=204,
        headers={A2A_V1_HEADER: A2A_V1_VERSION, "Cache-Control": "no-store"},
    )


@artifact_object_router.get(
    "/download/{grant_id}", name="download_managed_artifact_object"
)
async def download_managed_artifact_object(
    grant_id: str,
    principal: tuple[Any, dict | None] = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_any_scope(principal, ("contexts:read", "api:read"))
    _require_object_audit_enabled()
    actor_type, actor_id_hash = _actor_fingerprint_from_principal(principal)
    try:
        payload = await consume_download(
            db,
            grant_id=grant_id,
            organization_id=organization.id,
            actor_type=actor_type,
            actor_id_hash=actor_id_hash,
        )
    except ArtifactObjectError as exc:
        raise _object_error(exc) from exc
    audit_entry = await _audit(
        db,
        principal,
        organization.id,
        "agentic.artifact.object.download.consume",
        "agentic_artifact_object",
        payload.object_id,
        {
            "purpose_of_use": payload.purpose_of_use,
            "size_bytes": len(payload.content),
        },
    )
    await _require_object_audit(db, audit_entry)
    # Persist single-use consumption and audit before protected bytes leave.
    await db.commit()
    encoded_filename = quote(payload.filename, safe="")
    return Response(
        content=payload.content,
        media_type=payload.media_type,
        headers={
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "Expires": "0",
            "Content-Disposition": (
                "attachment; filename=download; "
                f"filename*=UTF-8''{encoded_filename}"
            ),
            "Content-Security-Policy": "sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Artifact-SHA256": payload.sha256,
        },
    )


__all__ = ["artifact_object_router", "router"]
