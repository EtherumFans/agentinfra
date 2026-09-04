"""Corti-compatible Agentic context trace export and Task feedback.

Trace export projects the existing durable run ledger into an
OpenInference-shaped hierarchy.  It deliberately omits raw model input and
output: Chinese medical deployments require a minimum-necessary export even
when the underlying Context contains route-redacted clinical text.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import uuid
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import and_, distinct, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.icoder.agent_runtime.context.db_models import (
    ContextMessageRow,
    ContextRow,
    ContextTaskRefRow,
)
from app.icoder.agent_runtime.orchestrator.phi_redactor import redact_payload
from app.middleware.audit import log_action
from app.middleware.auth import (
    get_current_organization,
    get_current_user_or_oauth_client,
    require_org_role,
)
from app.models.agent_feedback import (
    AgentTaskFeedback,
    FeedbackTrainingAuthorization,
)
from app.models.agent import Agent
from app.models.organization import Organization, OrganizationMember
from app.models.run_history import RunHistoryModel
from app.models.run_trace import RunTraceEventModel
from app.services.phi_encryption import decrypt_phi, encrypt_phi
from app.services.system_audit import tenant_owned_system_audit


router = APIRouter(prefix="/api/v2/agentic", tags=["agentic-observability"])

POSITIVE_LABELS = frozenset({"correct", "complete", "helpful", "wellPresented", "efficient"})
NEGATIVE_LABELS = frozenset({
    "incorrect", "missingInformation", "irrelevant", "misunderstoodRequest",
    "unsupportedClaim", "unsafeOrInappropriate", "poorlyPresented", "tooVerbose",
})
ALLOWED_LABELS = POSITIVE_LABELS | NEGATIVE_LABELS | {"other"}
COLLECTION_METHODS = frozenset({
    "thumbs", "survey", "caseReview", "automatedEvaluation", "other",
})
_PSEUDONYMOUS_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_TRACE_CURSOR_MAX = 2048
_TRAINING_AUTHORIZATION_MAX_DAYS = 30
_feedback_training_admin = require_org_role("owner", "admin")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BinaryRating(_StrictModel):
    scale: Literal["binary"] = "binary"
    value: Literal[0, 1]


class FeedbackTarget(_StrictModel):
    message_id: str = Field(alias="messageId", min_length=1, max_length=64)


class FeedbackActorMetadata(_StrictModel):
    external_id: str = Field(alias="externalId", min_length=1, max_length=128)


class FeedbackMetadata(_StrictModel):
    collection_method: str | None = Field(default=None, alias="collectionMethod", max_length=32)
    client_reference: str | None = Field(default=None, alias="clientReference", max_length=128)
    actor: FeedbackActorMetadata | None = None


class FeedbackCreate(_StrictModel):
    rating: BinaryRating
    labels: list[str] = Field(default_factory=list, max_length=5)
    reason: str | None = Field(default=None, max_length=2000)
    target: FeedbackTarget | None = None
    metadata: FeedbackMetadata | None = None

    @model_validator(mode="after")
    def validate_contract(self) -> "FeedbackCreate":
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("labels must not contain duplicates")
        unknown = sorted(set(self.labels) - ALLOWED_LABELS)
        if unknown:
            raise ValueError(f"unsupported feedback labels: {unknown}")
        if "other" in self.labels and not (self.reason or "").strip():
            raise ValueError("reason is required when labels contains 'other'")
        if self.metadata and self.metadata.collection_method:
            if self.metadata.collection_method not in COLLECTION_METHODS:
                raise ValueError("metadata.collectionMethod is unsupported")
        for value, field_name in (
            (self.metadata.client_reference if self.metadata else None, "clientReference"),
            (
                self.metadata.actor.external_id
                if self.metadata and self.metadata.actor else None,
                "actor.externalId",
            ),
        ):
            if value is not None and not _is_pseudonymous(value):
                raise ValueError(f"metadata.{field_name} must be a pseudonymous identifier")
        return self


class FeedbackView(_StrictModel):
    id: str
    task_id: str = Field(alias="taskId")
    rating: BinaryRating
    normalized_score: float = Field(alias="normalizedScore")
    labels: list[str]
    reason: str | None
    created_at: datetime = Field(alias="createdAt")
    target: FeedbackTarget | None = None


class FeedbackList(_StrictModel):
    feedbacks: list[FeedbackView]


class FeedbackTrainingAuthorizationInput(_StrictModel):
    purpose_of_use: Literal["quality_improvement"] = Field(alias="purposeOfUse")
    data_scope: Literal["feedback_metadata_only"] = Field(alias="dataScope")
    expires_at: datetime = Field(alias="expiresAt")
    approval_reference: str = Field(
        alias="approvalReference", min_length=8, max_length=128,
    )
    acknowledgement: Literal[True]

    @model_validator(mode="after")
    def validate_training_authorization(self) -> "FeedbackTrainingAuthorizationInput":
        if not _is_pseudonymous(self.approval_reference):
            raise ValueError("approvalReference must be an opaque pseudonymous identifier")
        if self.expires_at.tzinfo is None:
            raise ValueError("expiresAt must include a timezone")
        return self


class FeedbackTrainingAuthorizationView(_StrictModel):
    id: str
    feedback_id: str = Field(alias="feedbackId")
    task_id: str = Field(alias="taskId")
    training_authorized: bool = Field(alias="trainingAuthorized")
    authorization_status: Literal["active", "revoked", "expired", "stale"] = Field(
        alias="authorizationStatus"
    )
    purpose_of_use: Literal["quality_improvement"] = Field(alias="purposeOfUse")
    data_scope: Literal["feedback_metadata_only"] = Field(alias="dataScope")
    expires_at: datetime = Field(alias="expiresAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    revoked_at: datetime | None = Field(alias="revokedAt")
    version: int


class TraceDescriptor(_StrictModel):
    id: str
    name: str
    start_time: datetime
    thread_id: str


class TraceSpan(_StrictModel):
    name: str
    span_id: str
    parent_span_id: str | None = None
    start_time: datetime
    attributes: dict[str, Any]


class TraceExport(_StrictModel):
    trace: TraceDescriptor
    spans: list[TraceSpan]


class TracePage(_StrictModel):
    traces: list[TraceExport]
    next_page_token: str | None = Field(alias="nextPageToken")
    total_size: int | None = Field(default=None, alias="totalSize")


class AgentUsageTotals(_StrictModel):
    invocations: int
    unique_contexts: int = Field(alias="uniqueContexts")


class AgentUsageBucket(_StrictModel):
    period_start: datetime = Field(alias="periodStart")
    period_end: datetime = Field(alias="periodEnd")
    invocations: int
    unique_contexts: int = Field(alias="uniqueContexts")


class AgentUsage(_StrictModel):
    granularity: Literal["day"] = "day"
    from_time: datetime = Field(alias="from")
    to_time: datetime = Field(alias="to")
    totals: AgentUsageTotals
    buckets: list[AgentUsageBucket]


def _is_pseudonymous(value: str) -> bool:
    lowered = value.lower()
    if not _PSEUDONYMOUS_ID.fullmatch(value):
        return False
    if value.isdigit() and len(value) >= 6:
        return False
    return not any(marker in lowered for marker in ("mrn", "patient", "email", "name"))


def _principal(principal: tuple[Any, dict | None]) -> tuple[str, str, str | None, str | None]:
    user, client = principal
    if client:
        actor_type = "runtime_token" if client.get("type") == "runtime_token" else "oauth_client"
        actor_id = str(client.get("client_id") or client.get("preview_session_id") or "unknown")
        return actor_type, actor_id, getattr(user, "id", None), actor_id
    if user is None:  # defensive; the auth dependency never returns this shape
        raise HTTPException(status_code=401, detail="Not authenticated")
    return "user", str(user.id), str(user.id), getattr(user, "email", None)


def _require_any_scope(principal: tuple[Any, dict | None], allowed: tuple[str, ...]) -> None:
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


def _require_automated_evaluation_scope(
    principal: tuple[Any, dict | None],
) -> None:
    """Reserve automated feedback for an explicitly scoped machine identity.

    ``automatedEvaluation`` is a quality-evaluation provenance marker, not a
    synonym for an ordinary user review and never an implicit training grant.
    Requiring a dedicated OAuth scope makes that boundary independently
    revocable and prevents a broad ``api:write`` token from impersonating an
    evaluator.
    """

    _user, client = principal
    granted = set(client.get("scopes") or []) if client is not None else set()
    if client is None or "feedback:evaluate" not in granted:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "automated_evaluation_scope_required",
                "required_scope": "feedback:evaluate",
                "granted_scopes": sorted(granted),
            },
        )


async def _require_context_task(
    db: AsyncSession, organization_id: str, context_id: str, task_id: str,
) -> ContextTaskRefRow:
    context = (await db.execute(select(ContextRow).where(
        ContextRow.id == context_id,
        ContextRow.organization_id == organization_id,
    ))).scalar_one_or_none()
    if context is None:
        raise HTTPException(status_code=404, detail="Context not found")
    task = (await db.execute(select(ContextTaskRefRow).where(
        ContextTaskRefRow.context_id == context_id,
        ContextTaskRefRow.task_id == task_id,
    ))).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


def _cursor_key() -> bytes:
    return hashlib.sha256((settings.SECRET_KEY + ":agentic-trace-cursor").encode()).digest()


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64decode(raw: str) -> bytes:
    return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def _encode_trace_cursor(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    signature = hmac.new(_cursor_key(), body, hashlib.sha256).digest()
    return f"{_b64encode(body)}.{_b64encode(signature)}"


def _decode_trace_cursor(token: str, *, organization_id: str, context_id: str) -> dict[str, Any]:
    if not token or len(token) > _TRACE_CURSOR_MAX or token.count(".") != 1:
        raise HTTPException(status_code=400, detail="pageToken is malformed")
    encoded, signed = token.split(".", 1)
    try:
        body = _b64decode(encoded)
        signature = _b64decode(signed)
        value = json.loads(body.decode())
    except Exception as exc:
        raise HTTPException(status_code=400, detail="pageToken is malformed") from exc
    expected = hmac.new(_cursor_key(), body, hashlib.sha256).digest()
    # Reject non-canonical base64url encodings as well as bad signatures.
    # Without this check, changing unused low bits in the final character can
    # produce a different token string that decodes to the same signature.
    canonical = _b64encode(body) == encoded and _b64encode(signature) == signed
    if not canonical or not hmac.compare_digest(signature, expected) or not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="pageToken signature is invalid")
    if value.get("v") != 1 or value.get("org") != organization_id or value.get("context") != context_id:
        raise HTTPException(status_code=400, detail="pageToken does not belong to this Context")
    return value


def _hex_id(prefix: str, length: int) -> str:
    return hashlib.sha256(prefix.encode()).hexdigest()[:length]


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _db_timestamp(value: datetime) -> datetime:
    """Convert an API timestamp to the schema's UTC-naive representation."""
    return _utc(value).astimezone(timezone.utc).replace(tzinfo=None)


def _event_attributes(event: RunTraceEventModel) -> dict[str, Any]:
    metadata = event.safe_metadata_json if isinstance(event.safe_metadata_json, dict) else {}

    def _bounded_identifier(value: Any, *, limit: int = 256) -> str:
        text = str(value or "").strip()
        if not text or len(text) > limit:
            return ""
        return text if all(
            ch.isascii() and (ch.isalnum() or ch in "._:/@+-") for ch in text
        ) else ""

    tool_name = _bounded_identifier(
        metadata.get("tool_name")
        or metadata.get("connector_node_id")
        or metadata.get("connector_id")
    )
    model_provider = _bounded_identifier(
        metadata.get("model_provider") or metadata.get("provider")
    )
    model_system = _bounded_identifier(
        metadata.get("model_system") or model_provider
    )
    model_name = _bounded_identifier(
        metadata.get("model_name") or metadata.get("model")
    )
    backend_type = str(metadata.get("backend_type") or "")
    span_kind = "CHAIN"
    if event.step == "tools_call" or tool_name:
        span_kind = "TOOL"
    elif backend_type in {"pure_llm", "llm_with_tools"} or model_provider or model_name:
        span_kind = "LLM"
    attributes: dict[str, Any] = {
        "openinference.span.kind": span_kind,
        "icoder.trace.step": event.step,
        "icoder.trace.status": event.status,
        "icoder.trace.input_exported": False,
        "icoder.trace.output_exported": False,
    }
    safe_keys = {
        "agent_id", "connector_id", "connector_type", "tool_id", "tool_name",
        "connector_node_id", "connector_graph_revision", "provider", "model",
        "model_name", "model_provider", "model_system", "backend_provider",
        "backend_type", "provider_status", "model_deployment_id", "attempt",
        "attempts", "retry_count", "llm_call_count", "finish_reason",
    }
    for key in safe_keys:
        value = metadata.get(key)
        if isinstance(value, (str, int, float, bool)) and len(str(value)) <= 256:
            attributes[f"icoder.{key}"] = value
    if tool_name:
        attributes["tool.name"] = tool_name
    tool_id = _bounded_identifier(metadata.get("tool_id") or metadata.get("connector_id"))
    if tool_id:
        attributes["tool.id"] = tool_id
    if model_provider:
        attributes["llm.provider"] = model_provider
    if model_system:
        attributes["llm.system"] = model_system
    if model_name:
        attributes["llm.model_name"] = model_name
    for source, target in (
        ("input_tokens", "llm.token_count.prompt"),
        ("output_tokens", "llm.token_count.completion"),
        ("total_tokens", "llm.token_count.total"),
    ):
        value = metadata.get(source)
        if isinstance(value, int) and 0 <= value <= 100_000_000:
            attributes[target] = value
    model_cost = metadata.get("model_cost_usd")
    if (
        isinstance(model_cost, (int, float))
        and not isinstance(model_cost, bool)
        and model_cost == model_cost
        and 0.0 <= float(model_cost) <= 1_000_000.0
    ):
        attributes["llm.cost.total"] = float(model_cost)
    finish_reason = _bounded_identifier(metadata.get("finish_reason"), limit=128)
    if finish_reason:
        attributes["llm.finish_reason"] = finish_reason
    if event.duration_ms is not None:
        attributes["icoder.duration_ms"] = max(0.0, float(event.duration_ms))
    return attributes


def _project_trace(run: RunHistoryModel, events: list[RunTraceEventModel], context_id: str) -> TraceExport:
    trace_id = _hex_id(f"trace:{run.trace_id or run.run_id}", 32)
    root_span_id = _hex_id(f"span:{trace_id}:root", 16)
    root_attributes: dict[str, Any] = {
        "openinference.span.kind": "AGENT",
        "session.id": context_id,
        "icoder.run.id": run.run_id,
        "icoder.agent.id": run.agent_id,
        "icoder.run.status": run.status,
        "icoder.runtime.mode": run.runtime_mode,
        "icoder.trace.input_exported": False,
        "icoder.trace.minimum_necessary_policy": "china_medical",
    }
    if run.latency_ms is not None:
        root_attributes["icoder.latency_ms"] = max(0, int(run.latency_ms))
    if run.cost_usd is not None:
        root_attributes["icoder.cost_usd"] = max(0.0, float(run.cost_usd))
    if run.error_reason and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", run.error_reason):
        root_attributes["icoder.error.code"] = run.error_reason[:128]
    if run.trace_capture_status:
        root_attributes["icoder.trace.capture_status"] = run.trace_capture_status
    start = _utc(run.created_at)
    spans = [TraceSpan(
        name=f"agent.run/{run.agent_id}", span_id=root_span_id,
        start_time=start, attributes=root_attributes,
    )]
    for ordinal, event in enumerate(sorted(events, key=lambda item: (item.sequence_number or 0, item.ts or 0.0))):
        event_key = event.event_id or f"{event.sequence_number or ordinal}:{event.id}"
        event_start = (
            datetime.fromtimestamp(event.ts, tz=timezone.utc)
            if event.ts and event.ts > 0 else _utc(event.created_at)
        )
        spans.append(TraceSpan(
            name=event.step,
            span_id=_hex_id(f"span:{trace_id}:{event_key}", 16),
            parent_span_id=root_span_id,
            start_time=event_start,
            attributes=_event_attributes(event),
        ))
    return TraceExport(
        trace=TraceDescriptor(
            id=trace_id,
            name=f"agent.run/{run.agent_id}",
            start_time=start,
            thread_id=context_id,
        ),
        spans=spans,
    )


@lru_cache(maxsize=1)
def _official_agent_ids() -> frozenset[str]:
    """Return top-level Hub Agent ids without importing the Hub API module."""

    official_dir = Path(__file__).resolve().parents[2] / "official_agents"
    ids: set[str] = set()
    for path in official_dir.rglob("agent_pack.json") if official_dir.exists() else ():
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        reference = str(pack.get("agent_ref") or "")
        tail = reference.rsplit("/", 1)[-1].split("@", 1)[0].strip()
        if tail:
            ids.add(tail)
    return frozenset(ids)


async def _require_known_agent(
    db: AsyncSession,
    *,
    organization_id: str,
    agent_id: str,
) -> None:
    """Uniform 404 for unknown or another tenant's custom Agent."""

    if agent_id in _official_agent_ids():
        return
    row = (await db.execute(select(Agent.id).where(
        Agent.id == agent_id,
        Agent.organization_id == organization_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")


def _usage_window(
    from_time: datetime | None,
    to_time: datetime | None,
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    end = to_time or now
    start = from_time or (end - timedelta(days=30))
    if start.tzinfo is None or end.tzinfo is None:
        raise HTTPException(status_code=400, detail="from and to must include a UTC offset")
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)
    if start >= end:
        raise HTTPException(status_code=400, detail="from must be earlier than to")
    # A bounded analytical window prevents a tenant credential from turning a
    # read-only usage request into an unbounded database scan. Callers can page
    # historical reporting into one-year windows without losing exact counts.
    if end - start > timedelta(days=366):
        raise HTTPException(status_code=400, detail="usage window must not exceed 366 days")
    return start, end


def _usage_day(value: Any) -> datetime:
    if isinstance(value, datetime):
        current = value
    elif isinstance(value, date):
        current = datetime.combine(value, datetime_time.min)
    else:
        try:
            current = datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise RuntimeError("database returned an invalid usage bucket") from exc
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )


@router.get("/agents/{agent_id}/usage", response_model=AgentUsage)
async def get_agent_usage(
    agent_id: str,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    granularity: Literal["minute", "hour", "day", "week"] = Query(default="day"),
    principal: tuple = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> AgentUsage:
    """Return Corti-compatible per-Agent invocation and Context usage.

    Corti currently accepts four granularity values but returns day buckets for
    each of them. iCoDer preserves that wire contract while keeping every
    aggregate organization-scoped and excluding quarantined legacy rows.
    ``to`` is exclusive; ``from`` is inclusive.
    """

    del granularity  # accepted for current Corti compatibility; day is authoritative
    _require_any_scope(principal, ("usage:read", "api:read"))
    await _require_known_agent(
        db, organization_id=organization.id, agent_id=agent_id,
    )
    start, end = _usage_window(from_time, to_time)
    db_start, db_end = _db_timestamp(start), _db_timestamp(end)

    from app.services.tenant_read_policy import apply_tenant_visibility_filter

    base_filters = (
        RunHistoryModel.organization_id == organization.id,
        RunHistoryModel.agent_id == agent_id,
        RunHistoryModel.created_at >= db_start,
        RunHistoryModel.created_at < db_end,
    )
    totals_stmt = select(
        func.count(RunHistoryModel.run_id).label("invocations"),
        func.count(distinct(RunHistoryModel.context_id)).label("unique_contexts"),
    ).where(*base_filters)
    totals_stmt = apply_tenant_visibility_filter(
        totals_stmt, RunHistoryModel.tenancy_classification,
    )
    totals_row = (await db.execute(totals_stmt)).one()

    dialect = db.get_bind().dialect.name
    day_expression = (
        func.date_trunc("day", RunHistoryModel.created_at)
        if dialect == "postgresql"
        else func.date(RunHistoryModel.created_at)
    )
    bucket_stmt = (
        select(
            day_expression.label("period_start"),
            func.count(RunHistoryModel.run_id).label("invocations"),
            func.count(distinct(RunHistoryModel.context_id)).label("unique_contexts"),
        )
        .where(*base_filters)
        .group_by(day_expression)
        .order_by(day_expression.asc())
    )
    bucket_stmt = apply_tenant_visibility_filter(
        bucket_stmt, RunHistoryModel.tenancy_classification,
    )
    bucket_rows = (await db.execute(bucket_stmt)).all()
    buckets: list[AgentUsageBucket] = []
    for row in bucket_rows:
        period_start = _usage_day(row.period_start)
        buckets.append(AgentUsageBucket(
            periodStart=period_start,
            periodEnd=period_start + timedelta(days=1),
            invocations=int(row.invocations or 0),
            uniqueContexts=int(row.unique_contexts or 0),
        ))

    actor_type, _actor_id, user_id, username = _principal(principal)
    await log_action(
        db, user_id, username, "agentic.agent.usage.read", "agent", agent_id,
        details={
            "from": start.isoformat(), "to": end.isoformat(),
            "granularity": "day", "actor_type": actor_type,
        },
        organization_id=organization.id,
    )
    return AgentUsage(
        granularity="day", from_time=start, to_time=end,
        totals=AgentUsageTotals(
            invocations=int(totals_row.invocations or 0),
            uniqueContexts=int(totals_row.unique_contexts or 0),
        ),
        buckets=buckets,
    )


@router.get("/contexts/{context_id}/trace", response_model=TracePage)
async def export_context_trace(
    context_id: str,
    page_size: int = Query(default=50, alias="pageSize", ge=1, le=200),
    page_token: str | None = Query(default=None, alias="pageToken", max_length=_TRACE_CURSOR_MAX),
    principal: tuple = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> TracePage:
    _require_any_scope(principal, ("traces:read", "api:read"))
    context = (await db.execute(select(ContextRow).where(
        ContextRow.id == context_id,
        ContextRow.organization_id == organization.id,
    ))).scalar_one_or_none()
    if context is None:
        raise HTTPException(status_code=404, detail="Context not found")

    stmt = select(RunHistoryModel).where(
        RunHistoryModel.organization_id == organization.id,
        RunHistoryModel.context_id == context_id,
    )
    if page_token:
        cursor = _decode_trace_cursor(
            page_token, organization_id=organization.id, context_id=context_id,
        )
        try:
            cursor_time = _db_timestamp(
                datetime.fromisoformat(str(cursor["created_at"]).replace("Z", "+00:00"))
            )
            cursor_run = str(cursor["run_id"])
        except Exception as exc:
            raise HTTPException(status_code=400, detail="pageToken payload is invalid") from exc
        stmt = stmt.where(or_(
            RunHistoryModel.created_at < cursor_time,
            and_(RunHistoryModel.created_at == cursor_time, RunHistoryModel.run_id < cursor_run),
        ))
    rows = list((await db.execute(
        stmt.order_by(RunHistoryModel.created_at.desc(), RunHistoryModel.run_id.desc()).limit(page_size + 1)
    )).scalars())
    has_more = len(rows) > page_size
    page = rows[:page_size]
    run_ids = [row.run_id for row in page]
    events_by_run: dict[str, list[RunTraceEventModel]] = {run_id: [] for run_id in run_ids}
    if run_ids:
        events = (await db.execute(select(RunTraceEventModel).where(
            RunTraceEventModel.organization_id == organization.id,
            RunTraceEventModel.run_id.in_(run_ids),
        ))).scalars()
        for event in events:
            events_by_run.setdefault(event.run_id, []).append(event)
    next_token = None
    if has_more and page:
        anchor = page[-1]
        next_token = _encode_trace_cursor({
            "v": 1, "org": organization.id, "context": context_id,
            "created_at": _utc(anchor.created_at).isoformat(), "run_id": anchor.run_id,
        })
    actor_type, actor_id, user_id, username = _principal(principal)
    await log_action(
        db, user_id, username, "agentic.trace.export", "context", context_id,
        details={"trace_count": len(page), "page_size": page_size, "actor_type": actor_type},
        organization_id=organization.id,
    )
    return TracePage(
        traces=[_project_trace(row, events_by_run.get(row.run_id, []), context_id) for row in page],
        nextPageToken=next_token,
        totalSize=None,
    )


def _safe_feedback_metadata(metadata: FeedbackMetadata | None) -> dict[str, Any]:
    if metadata is None:
        return {}
    result: dict[str, Any] = {}
    if metadata.collection_method:
        result["collectionMethod"] = metadata.collection_method
    if metadata.client_reference:
        result["clientReferenceHash"] = hashlib.sha256(metadata.client_reference.encode()).hexdigest()
    if metadata.actor:
        result["actorExternalIdHash"] = hashlib.sha256(metadata.actor.external_id.encode()).hexdigest()
    return result


def _feedback_view(row: AgentTaskFeedback) -> FeedbackView:
    try:
        labels = json.loads(row.labels_json)
    except Exception:
        labels = []
    reason = decrypt_phi(row.reason_encrypted) if row.reason_encrypted else None
    return FeedbackView(
        id=row.id,
        taskId=row.task_id,
        rating=BinaryRating(scale="binary", value=row.rating_value),
        normalizedScore=float(row.rating_value),
        labels=labels if isinstance(labels, list) else [],
        reason=reason,
        createdAt=_utc(row.created_at),
        target=FeedbackTarget(messageId=row.message_id) if row.message_id else None,
    )


def _feedback_training_digest(row: AgentTaskFeedback) -> str:
    """Bind an authorization to the exact stored feedback snapshot."""

    payload = {
        "feedback_id": row.id,
        "target_key": row.target_key,
        "rating_scale": row.rating_scale,
        "rating_value": row.rating_value,
        "labels_json": row.labels_json,
        "reason_encrypted": row.reason_encrypted,
        "reason_redacted": bool(row.reason_redacted),
        "safe_metadata_json": row.safe_metadata_json,
        "updated_at": _utc(row.updated_at).isoformat(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _training_authorization_view(
    row: FeedbackTrainingAuthorization,
    feedback: AgentTaskFeedback,
    *,
    now: datetime | None = None,
) -> FeedbackTrainingAuthorizationView:
    current = now or datetime.now(timezone.utc)
    if row.status != "active" or row.revoked_at is not None:
        authorization_status = "revoked"
    elif _utc(row.expires_at) <= current:
        authorization_status = "expired"
    elif row.feedback_digest != _feedback_training_digest(feedback):
        authorization_status = "stale"
    else:
        authorization_status = "active"
    return FeedbackTrainingAuthorizationView(
        id=row.id,
        feedbackId=row.feedback_id,
        taskId=row.task_id,
        trainingAuthorized=authorization_status == "active",
        authorizationStatus=authorization_status,
        purposeOfUse=row.purpose_of_use,
        dataScope=row.data_scope,
        expiresAt=_utc(row.expires_at),
        createdAt=_utc(row.created_at),
        updatedAt=_utc(row.updated_at),
        revokedAt=_utc(row.revoked_at) if row.revoked_at else None,
        version=row.version,
    )


async def _revoke_feedback_training_authorizations(
    db: AsyncSession,
    *,
    organization_id: str,
    feedback_ids: list[str],
    now: datetime,
) -> int:
    if not feedback_ids:
        return 0
    rows = list((await db.execute(select(FeedbackTrainingAuthorization).where(
        FeedbackTrainingAuthorization.organization_id == organization_id,
        FeedbackTrainingAuthorization.feedback_id.in_(feedback_ids),
        FeedbackTrainingAuthorization.status == "active",
    ))).scalars())
    for authorization in rows:
        authorization.status = "revoked"
        authorization.revoked_at = now
        authorization.updated_at = now
        authorization.version += 1
    return len(rows)


async def _require_feedback_for_training_authorization(
    db: AsyncSession,
    *,
    organization_id: str,
    context_id: str,
    task_id: str,
    feedback_id: str,
) -> AgentTaskFeedback:
    row = (await db.execute(select(AgentTaskFeedback).where(
        AgentTaskFeedback.id == feedback_id,
        AgentTaskFeedback.organization_id == organization_id,
        AgentTaskFeedback.context_id == context_id,
        AgentTaskFeedback.task_id == task_id,
        AgentTaskFeedback.deleted_at.is_(None),
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return row


@router.post(
    "/contexts/{context_id}/tasks/{task_id}/feedback",
    response_model=FeedbackView,
    status_code=status.HTTP_201_CREATED,
)
async def submit_task_feedback(
    context_id: str,
    task_id: str,
    payload: FeedbackCreate,
    response: Response,
    principal: tuple = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> FeedbackView:
    collection_method = (
        payload.metadata.collection_method if payload.metadata is not None else None
    )
    if collection_method == "automatedEvaluation":
        _require_automated_evaluation_scope(principal)
    else:
        _require_any_scope(principal, ("feedback:write", "api:write"))
    await _require_context_task(db, organization.id, context_id, task_id)
    message_id = payload.target.message_id if payload.target else None
    if message_id:
        message = (await db.execute(select(ContextMessageRow).where(
            ContextMessageRow.context_id == context_id,
            ContextMessageRow.message_id == message_id,
        ))).scalar_one_or_none()
        metadata = json.loads(message.metadata_json or "{}") if message else {}
        if message is None or str(metadata.get("a2a_v1_task_id") or "") != task_id:
            raise HTTPException(status_code=404, detail="Target message not found for Task")
    actor_type, actor_id, user_id, username = _principal(principal)
    target_key = f"message:{message_id}" if message_id else "task"
    row = (await db.execute(select(AgentTaskFeedback).where(
        AgentTaskFeedback.organization_id == organization.id,
        AgentTaskFeedback.context_id == context_id,
        AgentTaskFeedback.task_id == task_id,
        AgentTaskFeedback.target_key == target_key,
        AgentTaskFeedback.actor_type == actor_type,
        AgentTaskFeedback.actor_id == actor_id,
    ))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    reason_redaction = redact_payload(payload.reason) if payload.reason is not None else None
    reason_result = reason_redaction.value if reason_redaction is not None else None
    redaction_applied = bool(reason_redaction and reason_redaction.redaction_applied)
    encrypted_reason = encrypt_phi(reason_result) if reason_result else None
    created = row is None
    revoked_training_authorizations = 0
    if row is None:
        row = AgentTaskFeedback(
            id=f"fb-{uuid.uuid4().hex}", organization_id=organization.id,
            context_id=context_id, task_id=task_id, message_id=message_id,
            target_key=target_key, actor_type=actor_type, actor_id=actor_id,
            rating_scale="binary", rating_value=payload.rating.value,
            labels_json=json.dumps(payload.labels, separators=(",", ":")),
            reason_encrypted=encrypted_reason, reason_redacted=redaction_applied,
            safe_metadata_json=json.dumps(_safe_feedback_metadata(payload.metadata), separators=(",", ":")),
            created_at=now, updated_at=now,
            retention_until=now + timedelta(days=settings.AGENTIC_FEEDBACK_RETENTION_DAYS),
        )
        db.add(row)
    else:
        revoked_training_authorizations = await _revoke_feedback_training_authorizations(
            db,
            organization_id=organization.id,
            feedback_ids=[row.id],
            now=now,
        )
        response.status_code = status.HTTP_200_OK
        row.rating_value = payload.rating.value
        row.labels_json = json.dumps(payload.labels, separators=(",", ":"))
        row.reason_encrypted = encrypted_reason
        row.reason_redacted = redaction_applied
        row.safe_metadata_json = json.dumps(_safe_feedback_metadata(payload.metadata), separators=(",", ":"))
        row.message_id = message_id
        row.deleted_at = None
        row.created_at = now
        row.updated_at = now
        row.retention_until = now + timedelta(days=settings.AGENTIC_FEEDBACK_RETENTION_DAYS)
    try:
        await db.flush()
    except IntegrityError:
        # The unique actor/target constraint is the final idempotency guard
        # under concurrent POSTs. Re-read and converge on the winning row;
        # unrelated integrity failures remain failures.
        await db.rollback()
        row = (await db.execute(select(AgentTaskFeedback).where(
            AgentTaskFeedback.organization_id == organization.id,
            AgentTaskFeedback.context_id == context_id,
            AgentTaskFeedback.task_id == task_id,
            AgentTaskFeedback.target_key == target_key,
            AgentTaskFeedback.actor_type == actor_type,
            AgentTaskFeedback.actor_id == actor_id,
        ))).scalar_one_or_none()
        if row is None:
            raise
        created = False
        response.status_code = status.HTTP_200_OK
        revoked_training_authorizations = await _revoke_feedback_training_authorizations(
            db,
            organization_id=organization.id,
            feedback_ids=[row.id],
            now=now,
        )
        row.rating_value = payload.rating.value
        row.labels_json = json.dumps(payload.labels, separators=(",", ":"))
        row.reason_encrypted = encrypted_reason
        row.reason_redacted = redaction_applied
        row.safe_metadata_json = json.dumps(
            _safe_feedback_metadata(payload.metadata), separators=(",", ":")
        )
        row.message_id = message_id
        row.deleted_at = None
        row.created_at = now
        row.updated_at = now
        row.retention_until = now + timedelta(
            days=settings.AGENTIC_FEEDBACK_RETENTION_DAYS
        )
        await db.flush()
    await log_action(
        db, user_id, username,
        "agentic.feedback.create" if created else "agentic.feedback.update",
        "agent_task_feedback", row.id,
        details={
            "task_id": task_id, "target_type": "message" if message_id else "task",
            "rating": payload.rating.value, "label_count": len(payload.labels),
            "reason_redacted": redaction_applied, "actor_type": actor_type,
            "collection_method": collection_method,
            "training_authorized": False,
            "training_authorizations_revoked": revoked_training_authorizations,
        },
        organization_id=organization.id,
    )
    return _feedback_view(row)


@router.put(
    "/contexts/{context_id}/tasks/{task_id}/feedback/{feedback_id}/training-authorization",
    response_model=FeedbackTrainingAuthorizationView,
)
async def authorize_feedback_for_training(
    context_id: str,
    task_id: str,
    feedback_id: str,
    payload: FeedbackTrainingAuthorizationInput,
    member: OrganizationMember = Depends(_feedback_training_admin),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> FeedbackTrainingAuthorizationView:
    """Authorize one exact feedback snapshot for metadata-only improvement use.

    The grant is deliberately independent from feedback submission, restricted
    to organization owners/admins, time-bounded, purpose-bound and incapable
    of authorizing Task/Message/model content or the encrypted reason.
    """

    await _require_context_task(db, organization.id, context_id, task_id)
    feedback = await _require_feedback_for_training_authorization(
        db,
        organization_id=organization.id,
        context_id=context_id,
        task_id=task_id,
        feedback_id=feedback_id,
    )
    now = datetime.now(timezone.utc)
    expires_at = payload.expires_at.astimezone(timezone.utc)
    if expires_at <= now + timedelta(minutes=5):
        raise HTTPException(
            status_code=422,
            detail="expiresAt must be more than five minutes in the future",
        )
    if expires_at > now + timedelta(days=_TRAINING_AUTHORIZATION_MAX_DAYS):
        raise HTTPException(
            status_code=422,
            detail=f"expiresAt cannot exceed {_TRAINING_AUTHORIZATION_MAX_DAYS} days",
        )
    row = (await db.execute(select(FeedbackTrainingAuthorization).where(
        FeedbackTrainingAuthorization.organization_id == organization.id,
        FeedbackTrainingAuthorization.feedback_id == feedback_id,
    ))).scalar_one_or_none()
    digest = _feedback_training_digest(feedback)
    approval_reference_hash = hashlib.sha256(
        payload.approval_reference.encode()
    ).hexdigest()
    if row is None:
        row = FeedbackTrainingAuthorization(
            id=f"ftg-{uuid.uuid4().hex}",
            organization_id=organization.id,
            context_id=context_id,
            task_id=task_id,
            feedback_id=feedback_id,
            purpose_of_use=payload.purpose_of_use,
            data_scope=payload.data_scope,
            feedback_digest=digest,
            approval_reference_hash=approval_reference_hash,
            authorized_by_user_id=member.user_id,
            status="active",
            version=1,
            created_at=now,
            updated_at=now,
            expires_at=expires_at,
            revoked_at=None,
        )
        db.add(row)
    else:
        row.purpose_of_use = payload.purpose_of_use
        row.data_scope = payload.data_scope
        row.feedback_digest = digest
        row.approval_reference_hash = approval_reference_hash
        row.authorized_by_user_id = member.user_id
        row.status = "active"
        row.version += 1
        row.updated_at = now
        row.expires_at = expires_at
        row.revoked_at = None
    await db.flush()
    await tenant_owned_system_audit(
        db,
        organization_id=organization.id,
        action="agentic.feedback.training_authorization.granted",
        resource_type="feedback_training_authorization",
        resource_id=row.id,
        user_id=member.user_id,
        details={
            "feedback_id": feedback_id,
            "task_id": task_id,
            "purpose_of_use": payload.purpose_of_use,
            "data_scope": payload.data_scope,
            "expires_at": expires_at.isoformat(),
            "version": row.version,
            "task_or_message_content_authorized": False,
            "feedback_reason_authorized": False,
        },
    )
    return _training_authorization_view(row, feedback, now=now)


@router.get(
    "/contexts/{context_id}/tasks/{task_id}/feedback/{feedback_id}/training-authorization",
    response_model=FeedbackTrainingAuthorizationView,
)
async def get_feedback_training_authorization(
    context_id: str,
    task_id: str,
    feedback_id: str,
    member: OrganizationMember = Depends(_feedback_training_admin),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> FeedbackTrainingAuthorizationView:
    await _require_context_task(db, organization.id, context_id, task_id)
    feedback = await _require_feedback_for_training_authorization(
        db,
        organization_id=organization.id,
        context_id=context_id,
        task_id=task_id,
        feedback_id=feedback_id,
    )
    row = (await db.execute(select(FeedbackTrainingAuthorization).where(
        FeedbackTrainingAuthorization.organization_id == organization.id,
        FeedbackTrainingAuthorization.feedback_id == feedback_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Training authorization not found")
    await log_action(
        db,
        member.user_id,
        None,
        "agentic.feedback.training_authorization.read",
        "feedback_training_authorization",
        row.id,
        details={"feedback_id": feedback_id, "task_id": task_id},
        organization_id=organization.id,
    )
    return _training_authorization_view(row, feedback)


@router.delete(
    "/contexts/{context_id}/tasks/{task_id}/feedback/{feedback_id}/training-authorization",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_feedback_training_authorization(
    context_id: str,
    task_id: str,
    feedback_id: str,
    member: OrganizationMember = Depends(_feedback_training_admin),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await _require_context_task(db, organization.id, context_id, task_id)
    await _require_feedback_for_training_authorization(
        db,
        organization_id=organization.id,
        context_id=context_id,
        task_id=task_id,
        feedback_id=feedback_id,
    )
    row = (await db.execute(select(FeedbackTrainingAuthorization).where(
        FeedbackTrainingAuthorization.organization_id == organization.id,
        FeedbackTrainingAuthorization.feedback_id == feedback_id,
    ))).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    changed = bool(row is not None and row.status == "active")
    if changed and row is not None:
        row.status = "revoked"
        row.revoked_at = now
        row.updated_at = now
        row.version += 1
    await tenant_owned_system_audit(
        db,
        organization_id=organization.id,
        action="agentic.feedback.training_authorization.revoked",
        resource_type="feedback_training_authorization",
        resource_id=row.id if row is not None else feedback_id,
        user_id=member.user_id,
        details={
            "feedback_id": feedback_id,
            "task_id": task_id,
            "changed": changed,
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/contexts/{context_id}/tasks/{task_id}/feedback",
    response_model=FeedbackList,
)
async def list_task_feedback(
    context_id: str,
    task_id: str,
    principal: tuple = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> FeedbackList:
    _require_any_scope(principal, ("feedback:read", "api:read"))
    await _require_context_task(db, organization.id, context_id, task_id)
    actor_type, actor_id, user_id, username = _principal(principal)
    rows = list((await db.execute(select(AgentTaskFeedback).where(
        AgentTaskFeedback.organization_id == organization.id,
        AgentTaskFeedback.context_id == context_id,
        AgentTaskFeedback.task_id == task_id,
        AgentTaskFeedback.actor_type == actor_type,
        AgentTaskFeedback.actor_id == actor_id,
        AgentTaskFeedback.deleted_at.is_(None),
    ).order_by(AgentTaskFeedback.created_at.desc(), AgentTaskFeedback.id.desc()))).scalars())
    await log_action(
        db, user_id, username, "agentic.feedback.list", "agentic_task", task_id,
        details={"feedback_count": len(rows), "actor_type": actor_type},
        organization_id=organization.id,
    )
    return FeedbackList(feedbacks=[_feedback_view(row) for row in rows])


@router.delete(
    "/contexts/{context_id}/tasks/{task_id}/feedback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_task_feedback(
    context_id: str,
    task_id: str,
    principal: tuple = Depends(get_current_user_or_oauth_client),
    organization: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    _require_any_scope(principal, ("feedback:write", "api:write"))
    await _require_context_task(db, organization.id, context_id, task_id)
    actor_type, actor_id, user_id, username = _principal(principal)
    rows = list((await db.execute(select(AgentTaskFeedback).where(
        AgentTaskFeedback.organization_id == organization.id,
        AgentTaskFeedback.context_id == context_id,
        AgentTaskFeedback.task_id == task_id,
        AgentTaskFeedback.actor_type == actor_type,
        AgentTaskFeedback.actor_id == actor_id,
        AgentTaskFeedback.deleted_at.is_(None),
    ))).scalars())
    now = datetime.now(timezone.utc)
    revoked_training_authorizations = await _revoke_feedback_training_authorizations(
        db,
        organization_id=organization.id,
        feedback_ids=[row.id for row in rows],
        now=now,
    )
    for row in rows:
        row.deleted_at = now
        row.updated_at = now
    await log_action(
        db, user_id, username, "agentic.feedback.delete", "agentic_task", task_id,
        details={
            "deleted_count": len(rows),
            "actor_type": actor_type,
            "training_authorizations_revoked": revoked_training_authorizations,
        },
        organization_id=organization.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router"]
