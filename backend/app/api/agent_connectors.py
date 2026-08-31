"""Tenant-scoped Connector resources and server-governed execution graphs.

Resource mutation never performs network I/O. Enabled graphs are executed only
from the authenticated Agent Run path and remain subject to execution-time
egress, purpose-of-use, redaction, and prompt-injection policy.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.audit import log_action
from app.middleware.auth import get_current_organization, get_current_user, require_org_role
from app.models.agent_connector import AgentConnector, ConnectorCredential
from app.models.memory import ConversationMemory, MemoryConsent
from app.models.agent import Agent
from app.models.organization import Organization, OrganizationMember
from app.models.user import User
from app.schemas.agent_connector import (
    ConnectorCreateRequest,
    ConnectorListResponse,
    ConnectorResponse,
    ConnectorUpdateRequest,
    CredentialBindRequest,
    CredentialMetadataResponse,
)
from app.schemas.connector_graph import (
    ConnectorGraphPutRequest,
    ConnectorGraphResponse,
    ConnectorGraphSpec,
)
from app.schemas.memory import (
    MemoryConsentGrantRequest,
    MemoryConsentResponse,
    MemoryReadinessResponse,
)
from app.services.agent_connectors import (
    ConnectorValidationError,
    credential_fingerprint,
    normalize_config,
    require_agent_in_tenant,
    validate_agent_graph,
    validate_secret_ref,
)
from app.services.connector_graph import (
    ConnectorGraphError,
    load_connector_graph,
    validate_graph_bindings,
    validate_graph_node_binding,
)
from app.services.connector_memory_store import GovernedMemoryStore, MEMORY_PURPOSES
from app.services.phi_encryption import is_encryption_enabled
from app.config import settings


router = APIRouter(prefix="/api/v2/agentic/agents", tags=["agentic-connectors"])
_connector_admin = require_org_role("owner", "admin")
_memory_store = GovernedMemoryStore()


def _http_error(exc: ConnectorValidationError) -> HTTPException:
    status_code = (
        status.HTTP_404_NOT_FOUND
        if exc.code == "AGENT_NOT_FOUND"
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return HTTPException(status_code=status_code, detail={"code": exc.code})


def _graph_http_error(exc: ConnectorGraphError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail={"code": exc.code},
    )


async def _get_agent(
    db: AsyncSession,
    *,
    organization_id: str,
    agent_id: str,
    lock: bool = False,
) -> Agent:
    stmt = select(Agent).where(
        Agent.organization_id == organization_id,
        Agent.id == agent_id,
    )
    if lock:
        stmt = stmt.with_for_update()
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "AGENT_NOT_FOUND"},
        )
    return row


def _memory_consent_response(row: MemoryConsent) -> MemoryConsentResponse:
    return MemoryConsentResponse(
        id=row.id,
        agent_id=row.agent_id,
        user_id=row.user_id,
        purpose_of_use=row.purpose_of_use,
        legal_basis=row.legal_basis,
        authority_class="authenticated_user_self_service",
        patient_authority_verified=False,
        phi_storage_allowed=False,
        retention_days=row.retention_days,
        status=row.status,
        expires_at=row.expires_at,
        revoked_at=row.revoked_at,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post(
    "/{agent_id}/memory-consent",
    response_model=MemoryConsentResponse,
    summary=(
        "Grant or renew self-service persistent-memory authorization "
        "(not verified patient consent)"
    ),
)
async def grant_memory_consent(
    agent_id: str,
    body: MemoryConsentGrantRequest,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> MemoryConsentResponse:
    await _get_agent(db, organization_id=org.id, agent_id=agent_id)
    row = await _memory_store.grant(
        db,
        organization_id=org.id,
        user_id=user.id,
        agent_id=agent_id,
        purpose_of_use=body.purpose_of_use,
        retention_days=body.retention_days,
        expires_in_days=body.expires_in_days,
    )
    await log_action(
        db,
        user.id,
        user.username,
        "memory.consent.grant",
        "memory_consent",
        row.id,
        details={
            "agent_id": agent_id,
            "retention_days": body.retention_days,
            "expires_in_days": body.expires_in_days,
            "authority_class": "authenticated_user_self_service",
            "patient_authority_verified": False,
            "phi_storage_allowed": False,
        },
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
        purpose_of_use=body.purpose_of_use,
    )
    await db.flush()
    return _memory_consent_response(row)


@router.get(
    "/{agent_id}/memory-consent",
    response_model=MemoryConsentResponse,
    summary="Get self-service Memory authorization for one Agent and purpose",
)
async def get_memory_consent(
    agent_id: str,
    purpose_of_use: str = Query(default="treatment"),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> MemoryConsentResponse:
    if purpose_of_use not in MEMORY_PURPOSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "MEMORY_PURPOSE_NOT_ALLOWED"},
        )
    await _get_agent(db, organization_id=org.id, agent_id=agent_id)
    row = await _memory_store.get(
        db,
        organization_id=org.id,
        user_id=user.id,
        agent_id=agent_id,
        purpose_of_use=purpose_of_use,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEMORY_CONSENT_NOT_FOUND"},
        )
    await db.flush()
    return _memory_consent_response(row)


@router.get(
    "/{agent_id}/memory-readiness",
    response_model=MemoryReadinessResponse,
    summary="Get content-free operational readiness for governed Memory",
)
async def get_memory_readiness(
    agent_id: str,
    request: Request,
    purpose_of_use: str = Query(default="treatment"),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> MemoryReadinessResponse:
    if purpose_of_use not in MEMORY_PURPOSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "MEMORY_PURPOSE_NOT_ALLOWED"},
        )
    await _get_agent(db, organization_id=org.id, agent_id=agent_id)
    consent = await _memory_store.get(
        db,
        organization_id=org.id,
        user_id=user.id,
        agent_id=agent_id,
        purpose_of_use=purpose_of_use,
    )
    count = 0
    if consent is not None:
        count = int((await db.execute(
            select(func.count(ConversationMemory.id)).where(
                ConversationMemory.organization_id == org.id,
                ConversationMemory.user_id == user.id,
                ConversationMemory.agent_id == agent_id,
                ConversationMemory.consent_id == consent.id,
                ConversationMemory.purpose_of_use == purpose_of_use,
            )
        )).scalar_one())
    runtime = getattr(request.app.state, "connector_runtime", None)
    provider = getattr(runtime, "memory_embedding_provider", None)
    semantic_status = provider.status() if provider is not None else {
        "configured": False,
        "endpoint_configured": False,
        "credential_configured": False,
        "egress_approved": False,
        "identifiers_sent": False,
        "deidentified_text_only": True,
        "native_ml_in_api_process": False,
        "live_external_verified": False,
    }
    encryption_enabled = is_encryption_enabled()
    semantic_required = bool(settings.ICODER_MEMORY_SEMANTIC_REQUIRED)
    semantic_configured = bool(semantic_status.get("configured"))
    return MemoryReadinessResponse(
        agent_id=agent_id,
        purpose_of_use=purpose_of_use,
        consent_status=consent.status if consent is not None else "missing",
        persisted_memory_count=count,
        retention_days=consent.retention_days if consent is not None else None,
        expires_at=consent.expires_at if consent is not None else None,
        encryption_enabled=encryption_enabled,
        semantic_required=semantic_required,
        semantic_provider=semantic_status,
        lexical_fallback_available=True,
        native_ml_in_api_process=False,
        patient_authority_verified=False,
        phi_storage_allowed=False,
        operationally_configured=bool(
            encryption_enabled and (semantic_configured or not semantic_required)
        ),
    )


@router.delete(
    "/{agent_id}/memory-consent",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke consent and hard-delete memory created under it",
)
async def revoke_memory_consent(
    agent_id: str,
    request: Request,
    purpose_of_use: str = Query(default="treatment"),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    if purpose_of_use not in MEMORY_PURPOSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "MEMORY_PURPOSE_NOT_ALLOWED"},
        )
    await _get_agent(db, organization_id=org.id, agent_id=agent_id)
    row, deleted_count = await _memory_store.revoke(
        db,
        organization_id=org.id,
        user_id=user.id,
        agent_id=agent_id,
        purpose_of_use=purpose_of_use,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "MEMORY_CONSENT_NOT_FOUND"},
        )
    await log_action(
        db,
        user.id,
        user.username,
        "memory.consent.revoke",
        "memory_consent",
        row.id,
        details={"agent_id": agent_id, "deleted_memory_count": deleted_count},
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
        purpose_of_use=purpose_of_use,
    )
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _graph_state(agent: Agent) -> ConnectorGraphResponse:
    graph = load_connector_graph(agent)
    return graph or ConnectorGraphResponse(
        version="1.0",
        enabled=False,
        execution_mode="sequential",
        nodes=[],
        revision=0,
    )


def _graph_nodes_for_connector(
    graph: ConnectorGraphResponse,
    connector_id: str,
):
    return [node for node in graph.nodes if node.connector_id == connector_id]


@router.get(
    "/{agent_id}/connector-graph",
    response_model=ConnectorGraphResponse,
    summary="Get the server-governed Connector execution graph",
)
async def get_connector_graph(
    agent_id: str,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ConnectorGraphResponse:
    agent = await _get_agent(
        db, organization_id=org.id, agent_id=agent_id,
    )
    try:
        return _graph_state(agent)
    except ConnectorGraphError as exc:
        raise _graph_http_error(exc) from exc


@router.put(
    "/{agent_id}/connector-graph",
    response_model=ConnectorGraphResponse,
    summary="Replace a Connector graph with optimistic locking",
)
async def put_connector_graph(
    agent_id: str,
    body: ConnectorGraphPutRequest,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(_connector_admin),
    db: AsyncSession = Depends(get_db),
) -> ConnectorGraphResponse:
    agent = await _get_agent(
        db, organization_id=org.id, agent_id=agent_id, lock=True,
    )
    try:
        current = _graph_state(agent)
    except ConnectorGraphError as exc:
        raise _graph_http_error(exc) from exc
    if body.expected_revision != current.revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONNECTOR_GRAPH_REVISION_CONFLICT",
                "current_revision": current.revision,
            },
        )
    spec = ConnectorGraphSpec.model_validate(
        body.model_dump(exclude={"expected_revision"})
    )
    try:
        await validate_graph_bindings(
            db,
            organization_id=org.id,
            agent_id=agent_id,
            graph=spec,
        )
    except ConnectorGraphError as exc:
        raise _graph_http_error(exc) from exc
    next_state = ConnectorGraphResponse(
        **spec.model_dump(mode="json"),
        revision=current.revision + 1,
    )
    next_config = dict(agent.config or {})
    next_config["connector_graph"] = next_state.model_dump(mode="json")
    agent.config = next_config
    await log_action(
        db,
        user.id,
        user.username,
        "connector_graph.update",
        "agent",
        agent_id,
        details={
            "agent_id": agent_id,
            "connector_graph_revision": next_state.revision,
            "connector_node_count": len(next_state.nodes),
            "enabled": next_state.enabled,
        },
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return next_state


@router.delete(
    "/{agent_id}/connector-graph",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Disable and clear a Connector graph with optimistic locking",
)
async def delete_connector_graph(
    agent_id: str,
    request: Request,
    expected_revision: int = Query(ge=0),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(_connector_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    agent = await _get_agent(
        db, organization_id=org.id, agent_id=agent_id, lock=True,
    )
    try:
        current = _graph_state(agent)
    except ConnectorGraphError as exc:
        raise _graph_http_error(exc) from exc
    if expected_revision != current.revision:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "CONNECTOR_GRAPH_REVISION_CONFLICT",
                "current_revision": current.revision,
            },
        )
    next_state = ConnectorGraphResponse(
        version="1.0",
        enabled=False,
        execution_mode="sequential",
        nodes=[],
        revision=current.revision + 1,
    )
    next_config = dict(agent.config or {})
    next_config["connector_graph"] = next_state.model_dump(mode="json")
    agent.config = next_config
    await log_action(
        db,
        user.id,
        user.username,
        "connector_graph.delete",
        "agent",
        agent_id,
        details={
            "agent_id": agent_id,
            "connector_graph_revision": next_state.revision,
            "connector_node_count": 0,
            "enabled": False,
        },
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _get_connector(
    db: AsyncSession,
    *,
    organization_id: str,
    agent_id: str,
    connector_id: str,
    lock: bool = False,
) -> AgentConnector:
    stmt = select(AgentConnector).where(
        AgentConnector.organization_id == organization_id,
        AgentConnector.agent_id == agent_id,
        AgentConnector.id == connector_id,
        AgentConnector.deleted_at.is_(None),
    )
    if lock:
        stmt = stmt.with_for_update()
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONNECTOR_NOT_FOUND"},
        )
    return row


async def _credential_for(
    db: AsyncSession,
    *,
    organization_id: str,
    connector_id: str,
) -> ConnectorCredential | None:
    return (
        await db.execute(
            select(ConnectorCredential).where(
                ConnectorCredential.organization_id == organization_id,
                ConnectorCredential.connector_id == connector_id,
            )
        )
    ).scalar_one_or_none()


def _credential_metadata(row: ConnectorCredential | None) -> CredentialMetadataResponse:
    if row is None:
        return CredentialMetadataResponse(present=False)
    return CredentialMetadataResponse(
        present=True,
        provider=row.provider,
        secret_type=row.secret_type,
        fingerprint=row.fingerprint,
        status=row.status,
        version=row.version,
        rotated_at=row.rotated_at,
    )


async def _response(
    db: AsyncSession,
    row: AgentConnector,
) -> ConnectorResponse:
    credential = await _credential_for(
        db,
        organization_id=row.organization_id,
        connector_id=row.id,
    )
    return ConnectorResponse(
        id=row.id,
        agent_id=row.agent_id,
        type=row.type,
        name=row.name,
        description=row.description or "",
        enabled=row.enabled,
        config=row.config_json or {},
        target_agent_id=row.target_agent_id,
        normalized_url=row.normalized_url,
        schema_ref=row.schema_ref,
        schema_digest=row.schema_digest,
        version=row.version,
        credential=_credential_metadata(credential),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


async def _validate_binding_and_graph(
    db: AsyncSession,
    *,
    connector_type: str,
    organization_id: str,
    agent_id: str,
    normalized,
    replacing_connector_id: str | None = None,
) -> None:
    if connector_type == "agent":
        await validate_agent_graph(
            db,
            organization_id=organization_id,
            source_agent_id=agent_id,
            target_agent_id=normalized.target_agent_id or "",
            replacing_connector_id=replacing_connector_id,
        )


def _auth_policy(config: dict) -> str:
    return str(config.get("auth_policy") or "none")


@router.get(
    "/{agent_id}/connectors",
    response_model=ConnectorListResponse,
    summary="List an Agent's tenant-scoped connectors",
)
async def list_connectors(
    agent_id: str,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ConnectorListResponse:
    try:
        await require_agent_in_tenant(db, org.id, agent_id)
    except ConnectorValidationError as exc:
        raise _http_error(exc) from exc
    rows = (
        await db.execute(
            select(AgentConnector)
            .where(
                AgentConnector.organization_id == org.id,
                AgentConnector.agent_id == agent_id,
                AgentConnector.deleted_at.is_(None),
            )
            .order_by(AgentConnector.created_at, AgentConnector.id)
        )
    ).scalars().all()
    values = [await _response(db, row) for row in rows]
    return ConnectorListResponse(connectors=values, total=len(values))


@router.post(
    "/{agent_id}/connectors",
    response_model=ConnectorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a validated Agent connector",
)
async def create_connector(
    agent_id: str,
    body: ConnectorCreateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(_connector_admin),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    try:
        await require_agent_in_tenant(db, org.id, agent_id)
        normalized = normalize_config(
            body.type,
            body.config.model_dump(mode="json", exclude_none=True),
            enabled=body.enabled,
        )
        await _validate_binding_and_graph(
            db,
            connector_type=body.type,
            organization_id=org.id,
            agent_id=agent_id,
            normalized=normalized,
        )
        if body.enabled and _auth_policy(normalized.config) != "none":
            raise ConnectorValidationError(
                "CONNECTOR_CREDENTIAL_REQUIRED",
                "bind credential metadata before enabling this connector",
            )
    except ConnectorValidationError as exc:
        raise _http_error(exc) from exc
    row = AgentConnector(
        organization_id=org.id,
        agent_id=agent_id,
        type=body.type,
        name=body.name,
        description=body.description,
        enabled=body.enabled,
        config_json=normalized.config,
        target_agent_id=normalized.target_agent_id,
        normalized_url=normalized.normalized_url,
        schema_ref=normalized.schema_ref,
        schema_digest=normalized.schema_digest,
        version=1,
        created_by=user.id,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTOR_NAME_CONFLICT"},
        ) from exc
    await log_action(
        db,
        user.id,
        user.username,
        "connector.create",
        "agent_connector",
        row.id,
        details={
            "agent_id": agent_id,
            "connector_id": row.id,
            "connector_type": row.type,
            "enabled": row.enabled,
        },
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    await db.refresh(row)
    return await _response(db, row)


@router.get(
    "/{agent_id}/connectors/{connector_id}",
    response_model=ConnectorResponse,
    summary="Get one tenant-scoped Agent connector",
)
async def get_connector(
    agent_id: str,
    connector_id: str,
    _user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    row = await _get_connector(
        db,
        organization_id=org.id,
        agent_id=agent_id,
        connector_id=connector_id,
    )
    return await _response(db, row)


@router.patch(
    "/{agent_id}/connectors/{connector_id}",
    response_model=ConnectorResponse,
    summary="Update a connector with optimistic locking",
)
async def update_connector(
    agent_id: str,
    connector_id: str,
    body: ConnectorUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(_connector_admin),
    db: AsyncSession = Depends(get_db),
) -> ConnectorResponse:
    row = await _get_connector(
        db,
        organization_id=org.id,
        agent_id=agent_id,
        connector_id=connector_id,
        lock=True,
    )
    if body.expected_version != row.version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTOR_VERSION_CONFLICT", "current_version": row.version},
        )
    if body.type is not None and body.type != row.type:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTOR_TYPE_IMMUTABLE"},
        )
    next_enabled = body.enabled if body.enabled is not None else row.enabled
    next_config = (
        body.config.model_dump(mode="json", exclude_none=True)
        if body.config is not None
        else row.config_json
    )
    try:
        normalized = normalize_config(row.type, next_config, enabled=next_enabled)
        graph_agent = await _get_agent(
            db,
            organization_id=org.id,
            agent_id=agent_id,
        )
        graph = _graph_state(graph_agent)
        graph_nodes = _graph_nodes_for_connector(graph, row.id)
        if graph.enabled and graph_nodes and not next_enabled:
            raise ConnectorGraphError("CONNECTOR_GRAPH_ACTIVE_CONNECTOR_REQUIRED")
        for node in graph_nodes:
            validate_graph_node_binding(
                node,
                connector_type=row.type,
                config=normalized.config,
            )
        await _validate_binding_and_graph(
            db,
            connector_type=row.type,
            organization_id=org.id,
            agent_id=agent_id,
            normalized=normalized,
            replacing_connector_id=row.id,
        )
        credential = await _credential_for(
            db, organization_id=org.id, connector_id=row.id,
        )
        if next_enabled and _auth_policy(normalized.config) != "none" and (
            credential is None or credential.status != "active"
        ):
            raise ConnectorValidationError(
                "CONNECTOR_CREDENTIAL_REQUIRED",
                "active credential metadata is required before enablement",
            )
    except ConnectorValidationError as exc:
        raise _http_error(exc) from exc
    except ConnectorGraphError as exc:
        raise _graph_http_error(exc) from exc

    previous_enabled = row.enabled
    if body.name is not None:
        row.name = body.name
    if body.description is not None:
        row.description = body.description
    row.enabled = next_enabled
    row.config_json = normalized.config
    row.target_agent_id = normalized.target_agent_id
    row.normalized_url = normalized.normalized_url
    row.schema_ref = normalized.schema_ref
    row.schema_digest = normalized.schema_digest
    row.version += 1
    try:
        await db.flush()
    except IntegrityError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTOR_NAME_CONFLICT"},
        ) from exc
    await log_action(
        db,
        user.id,
        user.username,
        "connector.update",
        "agent_connector",
        row.id,
        details={
            "agent_id": agent_id,
            "connector_id": row.id,
            "connector_type": row.type,
            "enabled": row.enabled,
            "previous_enabled": previous_enabled,
            "version": row.version,
        },
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    await db.refresh(row)
    return await _response(db, row)


@router.delete(
    "/{agent_id}/connectors/{connector_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a disabled connector",
)
async def delete_connector(
    agent_id: str,
    connector_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(_connector_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = await _get_connector(
        db,
        organization_id=org.id,
        agent_id=agent_id,
        connector_id=connector_id,
        lock=True,
    )
    if row.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTOR_DISABLE_BEFORE_DELETE"},
        )
    try:
        graph_agent = await _get_agent(
            db,
            organization_id=org.id,
            agent_id=agent_id,
        )
        graph = _graph_state(graph_agent)
    except ConnectorGraphError as exc:
        raise _graph_http_error(exc) from exc
    if _graph_nodes_for_connector(graph, row.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTOR_GRAPH_REMOVE_NODE_BEFORE_DELETE"},
        )
    connector_type = row.type
    await db.execute(
        delete(ConnectorCredential).where(
            ConnectorCredential.organization_id == org.id,
            ConnectorCredential.connector_id == row.id,
        )
    )
    row.enabled = False
    row.credential_ref = None
    row.deleted_at = datetime.now(timezone.utc)
    # Release the per-Agent display name while retaining the tombstone and
    # its FK target for immutable execution-audit history.
    row.name = f"{row.name[:104]}~deleted~{row.id}"
    row.version += 1
    await log_action(
        db,
        user.id,
        user.username,
        "connector.delete",
        "agent_connector",
        connector_id,
        details={
            "agent_id": agent_id,
            "connector_id": connector_id,
            "connector_type": connector_type,
        },
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put(
    "/{agent_id}/connectors/{connector_id}/credential",
    response_model=CredentialMetadataResponse,
    summary="Bind or rotate a secret-manager reference",
)
async def bind_connector_credential(
    agent_id: str,
    connector_id: str,
    body: CredentialBindRequest,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(_connector_admin),
    db: AsyncSession = Depends(get_db),
) -> CredentialMetadataResponse:
    connector = await _get_connector(
        db,
        organization_id=org.id,
        agent_id=agent_id,
        connector_id=connector_id,
        lock=True,
    )
    policy = _auth_policy(connector.config_json or {})
    if policy == "none":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTOR_AUTH_POLICY_NONE"},
        )
    if (policy == "oauth2") != (body.secret_type == "oauth2-client"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "CONNECTOR_CREDENTIAL_TYPE_MISMATCH"},
        )
    try:
        secret_ref = validate_secret_ref(body.provider, body.secret_ref)
    except ConnectorValidationError as exc:
        raise _http_error(exc) from exc
    row = await _credential_for(
        db, organization_id=org.id, connector_id=connector.id,
    )
    now = datetime.now(timezone.utc)
    if row is None:
        if body.expected_version is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": "CONNECTOR_CREDENTIAL_VERSION_CONFLICT"},
            )
        row = ConnectorCredential(
            organization_id=org.id,
            connector_id=connector.id,
            provider=body.provider,
            secret_ref=secret_ref,
            fingerprint=credential_fingerprint(secret_ref),
            secret_type=body.secret_type,
            status="active",
            version=1,
            rotated_at=now,
            created_by=user.id,
        )
        db.add(row)
    else:
        if body.expected_version != row.version:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "CONNECTOR_CREDENTIAL_VERSION_CONFLICT",
                    "current_version": row.version,
                },
            )
        row.provider = body.provider
        row.secret_ref = secret_ref
        row.fingerprint = credential_fingerprint(secret_ref)
        row.secret_type = body.secret_type
        row.status = "active"
        row.version += 1
        row.rotated_at = now
    connector.credential_ref = secret_ref
    connector.version += 1
    await log_action(
        db,
        user.id,
        user.username,
        "connector.credential.rotate" if row.version > 1 else "connector.credential.bind",
        "connector_credential",
        connector.id,
        details={
            "agent_id": agent_id,
            "connector_id": connector.id,
            "connector_type": connector.type,
            "credential_provider": body.provider,
            "credential_version": row.version,
        },
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return _credential_metadata(row)


@router.delete(
    "/{agent_id}/connectors/{connector_id}/credential",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke and remove a connector credential reference",
)
async def delete_connector_credential(
    agent_id: str,
    connector_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
    _member: OrganizationMember = Depends(_connector_admin),
    db: AsyncSession = Depends(get_db),
) -> Response:
    connector = await _get_connector(
        db,
        organization_id=org.id,
        agent_id=agent_id,
        connector_id=connector_id,
        lock=True,
    )
    if connector.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "CONNECTOR_DISABLE_BEFORE_CREDENTIAL_DELETE"},
        )
    result = await db.execute(
        delete(ConnectorCredential).where(
            ConnectorCredential.organization_id == org.id,
            ConnectorCredential.connector_id == connector.id,
        )
    )
    if not result.rowcount:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "CONNECTOR_CREDENTIAL_NOT_FOUND"},
        )
    connector.credential_ref = None
    connector.version += 1
    await log_action(
        db,
        user.id,
        user.username,
        "connector.credential.delete",
        "connector_credential",
        connector.id,
        details={
            "agent_id": agent_id,
            "connector_id": connector.id,
            "connector_type": connector.type,
        },
        organization_id=org.id,
        ip_address=request.client.host if request.client else None,
    )
    await db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


__all__ = ["router", "_connector_admin"]
