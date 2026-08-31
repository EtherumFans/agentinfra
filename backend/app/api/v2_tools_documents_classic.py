"""iCoDer ``GET /api/v2/tools/interactions/{id}/documents/`` — Corti §13.4 Documents Classic.

The Corti docs tag this family as "Documents (Classic)". iCoDer implements
generation plus a compatibility lifecycle over encrypted saved documents.

Spec source (ground truth, never inferred):
- ``docs/corti-reverse-engineered/documents-classic-list.md`` (7,235
  bytes, fetched 2026-07-01 from
  ``https://docs.corti.ai/api-reference/documents-classic/list-documents.md``).
  Path: ``GET /interactions/{id}/documents/`` → operationId
  ``documents_list``.

What this endpoint IS
---------------------
- Generation from facts, transcript, or string context using static or dynamic
  templates, with global-sequential or facts-only routed-parallel execution.
- Sentence-indexed, per-section guardrail checks and a scoped
  list/get/update/delete lifecycle over encrypted saved documents, including
  the legacy ``{data: [...]}`` list envelope.

What this endpoint is NOT
--------------------------
- NOT a claim of quality equivalence to Corti's private document models,
  routing model, or guardrail model.
- NOT a deprecation-banner surface. Banners are a frontend
  concern; the backend wire contract here matches the live Corti
  envelope 1:1, including the lack of a deprecation marker in the
  response body.

Filter / scope behavior
-----------------------
The Corti spec scopes the LIST to a single ``{id}`` (the interaction
UUID). No other query params are accepted in Cycle 5 — the captured
spec declares only the path param + ``Tenant-Name`` header.

"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization
from app.models.template import Template
from app.models.user import User
from app.schemas.v2_tools_documents_classic import (
    CommonUsageInfo,
    DocumentsCreateRequest,
    DocumentsGetResponse,
    DocumentsListResponse,
    DocumentsSection,
    DocumentsUpdateRequest,
)
from app.middleware.audit import log_action
from app.services.guided_document_repository import guided_document_repository
from app.services.guided_section_catalog import resolve_curated_section
from app.services.guided_section_repository import guided_section_repository
from app.services.guided_template_catalog import public_template_id, template_definition

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])


def _classic_projection(row) -> DocumentsGetResponse:
    created_at = row.created_at.isoformat()
    updated_at = row.updated_at.isoformat()
    sections = [
        DocumentsSection(
            key=item["key"],
            name=item["name"],
            text=item["text"],
            sort=item["sort"],
            createdAt=created_at,
            updatedAt=updated_at,
        )
        for item in guided_document_repository.classic_sections(row)
    ]
    return DocumentsGetResponse(
        id=row.document_id,
        name=row.name,
        templateRef=row.template_id,
        isStream=row.is_stream,
        sections=sections,
        createdAt=created_at,
        updatedAt=updated_at,
        outputLanguage=row.language,
        usageInfo=CommonUsageInfo(creditsConsumed=row.credits_consumed),
    )


def _error(status: int, type_: str, detail: str) -> dict[str, Any]:
    return {
        "requestid": str(uuid.uuid4()),
        "status": status,
        "type": type_,
        "detail": detail,
    }


def _flatten_classic_context(body: DocumentsCreateRequest) -> str:
    parts: list[str] = []
    for item in body.context:
        if item.type == "string":
            parts.append(f"String context:\n{item.data}")
        elif item.type == "transcript":
            parts.append(f"Transcript context:\n{item.data.text}")
        else:
            facts = [
                f"- [{fact.group or 'other'}; source={fact.source or 'core'}] {fact.text}"
                for fact in item.data
            ]
            parts.append("Facts context:\n" + "\n".join(facts))
    return "\n\n".join(parts)


async def _resolve_static_template(
    db: AsyncSession,
    *,
    organization_id: str,
    template_key: str,
) -> tuple[str, str, dict[str, Any]]:
    rows = list((await db.scalars(select(Template).where(
        Template.organization_id == organization_id,
        Template.deleted_at.is_(None),
    ))).all())
    normalized = template_key.casefold()
    row = next((
        item for item in rows
        if template_key in {item.id, public_template_id(item)}
        or item.name.casefold() == normalized
    ), None)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=_error(404, "template_not_found", "Referenced template was not found."),
        )
    definition = template_definition(row)
    if not definition or not isinstance(definition.get("sections"), list) or not definition["sections"]:
        definition = {
            "instructions": {
                "prompt": row.content or "Generate a grounded clinical document from the supplied context."
            },
            "sections": [
                {
                    "sectionId": row.id,
                    "heading": row.name,
                    "instructions": {
                        "contentPrompt": row.description or "Summarize only documented facts."
                    },
                    "outputSchema": {"type": "string"},
                }
            ],
        }
    return public_template_id(row), row.name, definition


async def _resolve_dynamic_template(
    db: AsyncSession,
    *,
    organization_id: str,
    body: DocumentsCreateRequest,
) -> tuple[str, str, dict[str, Any]]:
    assert body.template is not None
    refs = (
        [(key, None) for key in body.template.sectionKeys]
        if body.template.sectionKeys is not None
        else [(item.key, item) for item in body.template.sections or []]
    )
    sections: list[dict[str, Any]] = []
    for key, override in refs:
        section = await guided_section_repository.resolve(
            db,
            organization_id=organization_id,
            section_id=key,
            version_id=None,
        )
        if section is None:
            section = resolve_curated_section(key)
        if section is None:
            raise HTTPException(
                status_code=404,
                detail=_error(404, "section_not_found", f"Section {key!r} was not found."),
            )
        section = json.loads(json.dumps(section))
        if override is not None:
            if override.nameOverride is not None:
                section["heading"] = override.nameOverride
            instructions = section.setdefault("instructions", {})
            for source, target in [
                (override.writingStyleOverride, "writingStylePrompt"),
                (override.formatRuleOverride, "formatRulePrompt"),
                (override.additionalInstructionsOverride, "additionalInstructionsPrompt"),
                (override.contentOverride, "contentPrompt"),
            ]:
                if source is not None:
                    instructions[target] = source
        sections.append(section)
    headings = [str(item.get("heading", "")).strip() for item in sections]
    if any(not item for item in headings) or len(headings) != len(set(headings)):
        raise HTTPException(
            status_code=422,
            detail=_error(422, "duplicate_section_heading", "Section headings must be unique."),
        )
    instructions = (
        body.template.additionalInstructionsOverride
        or body.template.additionalInstructions
        or "Generate only content supported by the supplied clinical context."
    )
    definition = {
        "description": body.template.description,
        "instructions": {"prompt": instructions},
        "sections": sections,
    }
    serialized = json.dumps(definition, ensure_ascii=False, sort_keys=True)
    template_ref = "dynamic-" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]
    template_name = body.template.documentName or body.name or "Dynamic document"
    return template_ref, template_name, definition


def _redact_classic_messages(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    try:
        from app.main import app as application

        data_policy = getattr(application.state, "data_policy", None)
    except Exception:
        data_policy = None
    if data_policy is None or not getattr(data_policy, "pii_redaction_required", False):
        return messages
    try:
        from icoder_runtime.core.pii_redaction import PIIRedactor

        redacted, _ = PIIRedactor(enabled=True).redact_messages(messages)
        return redacted
    except Exception as exc:
        logger.error("classic-document PHI redaction failed error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail=_error(503, "phi_redaction_failed", "PHI redaction failed."),
        ) from exc


async def _invoke_classic_model(
    messages: list[dict[str, str]],
    *,
    operation: str,
    response_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.main import app as application

    gateway = getattr(application.state, "platform_gateway", None)
    if gateway is None:
        raise RuntimeError("platform_gateway_unavailable")
    result = await gateway.generate(
        _redact_classic_messages(messages),
        response_schema=response_schema or {"type": "object"},
        context={"operation": operation, "clinical": True},
    )
    if not isinstance(result, dict):
        raise RuntimeError("classic_document_provider_response_invalid")
    if result.get("degraded") is True or result.get("is_mock") is True:
        raise RuntimeError("classic_document_provider_degraded")
    return result


def _decode_provider_object(result: dict[str, Any]) -> dict[str, Any]:
    content = result.get("content", "")
    try:
        raw = content.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:])
            if raw.rstrip().endswith("```"):
                raw = raw.rstrip()[:-3]
        parsed = json.loads(raw)
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=503,
            detail=_error(503, "invalid_provider_response", "Provider returned invalid JSON."),
        ) from exc
    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=503,
            detail=_error(503, "invalid_provider_response", "Provider response must be an object."),
        )
    return parsed


def _usage_tokens(result: dict[str, Any]) -> float:
    usage = result.get("usage")
    total: Any = 0
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total is None:
            total = (usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0) + (
                usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
            )
    try:
        return max(0.0, float(total))
    except (TypeError, ValueError):
        return 0.0


def _credits_from_tokens(total_tokens: float) -> float:
    return round(max(0.0, total_tokens) / 1000.0 * 0.011, 6)


def _sections_from_document_object(
    parsed: dict[str, Any], definition: dict[str, Any]
) -> list[dict[str, Any]]:
    expected = definition.get("sections", [])
    expected_by_heading = {item["heading"]: item for item in expected}
    if set(parsed) != set(expected_by_heading):
        raise HTTPException(
            status_code=503,
            detail=_error(
                503,
                "invalid_provider_response",
                "Provider section headings do not match the resolved template.",
            ),
        )
    sections: list[dict[str, Any]] = []
    for sort, section in enumerate(expected):
        heading = section["heading"]
        value = parsed[heading]
        if not isinstance(value, str):
            raise HTTPException(
                status_code=503,
                detail=_error(503, "invalid_provider_response", f"Section {heading!r} is not text."),
            )
        sections.append({
            "key": str(section.get("sectionId") or heading),
            "name": heading,
            "text": value,
            "sort": sort,
        })
    return sections


async def _generate_global_sequential(
    body: DocumentsCreateRequest,
    definition: dict[str, Any],
) -> tuple[list[dict[str, Any]], float]:
    context = _flatten_classic_context(body)
    system_prompt = (
        "You are the iCoDer Documents Classic clinical note generator. "
        f"Template definition: {json.dumps(definition, ensure_ascii=False)}. "
        f"Output language: {body.outputLanguage}. "
        "Return exactly one JSON object whose keys exactly match the section headings and whose values "
        "are strings. Preserve uncertainty and never add facts unsupported by the supplied context."
    )
    result = await _invoke_classic_model(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ],
        operation="corti_classic_document",
    )
    return _sections_from_document_object(
        _decode_provider_object(result), definition
    ), _usage_tokens(result)


def _routed_fact_lines(body: DocumentsCreateRequest) -> list[str]:
    if any(item.type != "facts" for item in body.context):
        raise HTTPException(
            status_code=422,
            detail=_error(
                422,
                "routed_parallel_requires_facts",
                "documentationMode routed_parallel supports facts context only.",
            ),
        )
    return [
        f"[{fact.group or 'other'}; source={fact.source or 'core'}] {fact.text}"
        for item in body.context
        for fact in item.data
    ]


async def _generate_routed_parallel(
    body: DocumentsCreateRequest,
    definition: dict[str, Any],
) -> tuple[list[dict[str, Any]], float]:
    facts = _routed_fact_lines(body)
    template_sections = definition.get("sections", [])
    headings = [section["heading"] for section in template_sections]
    numbered_facts = "\n".join(f"{index}: {fact}" for index, fact in enumerate(facts))
    route_result = await _invoke_classic_model(
        [
            {
                "role": "system",
                "content": (
                    "Route each supplied fact to every clinically relevant document section. "
                    "Return JSON as {\"assignments\": {<heading>: [zero-based fact indexes]}}. "
                    "The assignment object must contain every heading exactly once. Do not generate note text. "
                    f"Sections: {json.dumps(template_sections, ensure_ascii=False)}"
                ),
            },
            {"role": "user", "content": numbered_facts},
        ],
        operation="corti_classic_route_facts",
    )
    routed = _decode_provider_object(route_result)
    assignments = routed.get("assignments")
    if not isinstance(assignments, dict) or set(assignments) != set(headings):
        raise HTTPException(
            status_code=503,
            detail=_error(
                503,
                "invalid_provider_response",
                "Fact routing assignments do not match template headings.",
            ),
        )
    normalized: dict[str, list[int]] = {}
    for heading in headings:
        indexes = assignments[heading]
        if (
            not isinstance(indexes, list)
            or any(not isinstance(index, int) or isinstance(index, bool) for index in indexes)
            or any(index < 0 or index >= len(facts) for index in indexes)
            or len(indexes) != len(set(indexes))
        ):
            raise HTTPException(
                status_code=503,
                detail=_error(
                    503,
                    "invalid_provider_response",
                    f"Fact routing indexes for section {heading!r} are invalid.",
                ),
            )
        normalized[heading] = indexes

    async def _generate_section(section: dict[str, Any]) -> tuple[dict[str, Any], float]:
        heading = section["heading"]
        indexes = normalized[heading]
        base = {
            "key": str(section.get("sectionId") or heading),
            "name": heading,
            "sort": headings.index(heading),
        }
        if not indexes:
            return {**base, "text": ""}, 0.0
        assigned = "\n".join(f"{index}: {facts[index]}" for index in indexes)
        result = await _invoke_classic_model(
            [
                {
                    "role": "system",
                    "content": (
                        "Generate one clinical document section using only the assigned facts. "
                        "Return JSON as {\"text\": <string>}. Preserve uncertainty and do not add facts. "
                        f"Output language: {body.outputLanguage}. "
                        f"Section definition: {json.dumps(section, ensure_ascii=False)}"
                    ),
                },
                {"role": "user", "content": assigned},
            ],
            operation="corti_classic_generate_section",
        )
        parsed = _decode_provider_object(result)
        if set(parsed) != {"text"} or not isinstance(parsed["text"], str):
            raise HTTPException(
                status_code=503,
                detail=_error(
                    503,
                    "invalid_provider_response",
                    f"Generated section {heading!r} is not a text object.",
                ),
            )
        return {**base, "text": parsed["text"]}, _usage_tokens(result)

    generated = await asyncio.gather(*[
        _generate_section(section) for section in template_sections
    ])
    return [item[0] for item in generated], _usage_tokens(route_result) + sum(
        item[1] for item in generated
    )


def _indexed_segments(text: str) -> list[str]:
    return [
        segment.strip()
        for segment in re.split(r"(?<=[。！？.!?])\s*|\n+", text)
        if segment.strip()
    ]


async def _apply_sentence_guardrails(
    body: DocumentsCreateRequest,
    sections: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, float]:
    source_context = _flatten_classic_context(body)

    async def _guard_section(
        section: dict[str, Any],
    ) -> tuple[dict[str, Any], int, float]:
        if not section["text"]:
            return section, 0, 0.0
        segments = _indexed_segments(section["text"])
        numbered = "\n".join(f"{index}: {text}" for index, text in enumerate(segments))
        result = await _invoke_classic_model(
            [
                {
                    "role": "system",
                    "content": (
                        "Audit the generated section against the source context. Correct only unsupported or "
                        "misstated content while preserving format. Return JSON with correctedText:string and "
                        "issues:[{segmentIndex:integer,reason:string}]. Every correction must cite a valid "
                        "zero-based segment index; return an empty issues array when no correction is needed."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Source context:\n{source_context}\n\nSection: {section['name']}\n"
                        f"Indexed generated segments:\n{numbered}"
                    ),
                },
            ],
            operation="corti_classic_guardrail",
        )
        parsed = _decode_provider_object(result)
        corrected = parsed.get("correctedText")
        issues = parsed.get("issues")
        if not isinstance(corrected, str) or not isinstance(issues, list):
            raise HTTPException(
                status_code=503,
                detail=_error(503, "invalid_provider_response", "Guardrail response is malformed."),
            )
        for issue in issues:
            if (
                not isinstance(issue, dict)
                or not isinstance(issue.get("segmentIndex"), int)
                or isinstance(issue.get("segmentIndex"), bool)
                or issue["segmentIndex"] < 0
                or issue["segmentIndex"] >= len(segments)
                or not isinstance(issue.get("reason"), str)
                or not issue["reason"].strip()
            ):
                raise HTTPException(
                    status_code=503,
                    detail=_error(
                        503,
                        "invalid_provider_response",
                        "Guardrail issue does not reference a valid segment.",
                    ),
                )
        if corrected != section["text"] and not issues:
            raise HTTPException(
                status_code=503,
                detail=_error(
                    503,
                    "invalid_provider_response",
                    "Guardrail changed text without indexed evidence.",
                ),
            )
        return {**section, "text": corrected}, len(issues), _usage_tokens(result)

    guarded = await asyncio.gather(*[_guard_section(section) for section in sections])
    return (
        [item[0] for item in guarded],
        sum(item[1] for item in guarded),
        sum(item[2] for item in guarded),
    )


# ─── Endpoint ────────────────────────────────────────────────────────


@router.post(
    "/interactions/{interaction_id}/documents/",
    response_model=DocumentsGetResponse,
    status_code=201,
)
@router.post(
    "/interactions/{interaction_id}/documents",
    response_model=DocumentsGetResponse,
    status_code=201,
)
async def create_v2_tools_interaction_document(
    interaction_id: str,
    body: DocumentsCreateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    x_corti_retention_policy: str | None = Header(
        default=None,
        alias="X-Corti-Retention-Policy",
    ),
) -> DocumentsGetResponse:
    """Generate a Corti Documents Classic document from facts, transcript, or text."""
    try:
        normalized_interaction_id = str(uuid.UUID(interaction_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=_error(400, "invalid_interaction", "Interaction id must be a valid UUID."),
        ) from exc
    if x_corti_retention_policy not in {None, "none"}:
        raise HTTPException(
            status_code=422,
            detail=_error(
                422,
                "unsupported_retention_policy",
                "X-Corti-Retention-Policy supports only 'none' or omission.",
            ),
        )
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        raise HTTPException(
            status_code=503,
            detail=_error(503, "service_unavailable", "LLM credential is not configured."),
        )

    if body.templateKey is not None:
        template_ref, template_name, definition = await _resolve_static_template(
            db,
            organization_id=str(current_org.id),
            template_key=body.templateKey,
        )
    else:
        template_ref, template_name, definition = await _resolve_dynamic_template(
            db,
            organization_id=str(current_org.id),
            body=body,
        )

    documentation_mode = body.documentationMode or "global_sequential"
    try:
        if documentation_mode == "routed_parallel":
            sections, total_tokens = await _generate_routed_parallel(body, definition)
        else:
            sections, total_tokens = await _generate_global_sequential(body, definition)
        guardrail_issue_count = 0
        if not body.disableGuardrails:
            sections, guardrail_issue_count, guardrail_tokens = await _apply_sentence_guardrails(
                body, sections
            )
            total_tokens += guardrail_tokens
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("classic-document gateway failed error_type=%s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail=_error(503, "service_unavailable", "LLM generation failed."),
        ) from exc
    credits = _credits_from_tokens(total_tokens)
    document_name = body.name or template_name or f"document-{uuid.uuid4().hex[:8]}"
    string_document = {item["name"]: item["text"] for item in sections}

    if x_corti_retention_policy is None:
        row = await guided_document_repository.create(
            db,
            organization_id=str(current_org.id),
            owner_id=str(current_user.id),
            interaction_id=normalized_interaction_id,
            name=document_name,
            template_id=template_ref,
            template_version_id=template_ref,
            language=body.outputLanguage,
            string_document=string_document,
            structured_document=None,
            labels=[
                {"key": "documentation_mode", "value": documentation_mode},
                {
                    "key": "guardrails_applied",
                    "value": str(not body.disableGuardrails).lower(),
                },
                {"key": "guardrail_issue_count", "value": str(guardrail_issue_count)},
            ],
            credits_consumed=credits,
            classic_sections=sections,
        )
        await log_action(
            db,
            str(current_user.id),
            current_user.username,
            "document.generate",
            "document",
            row.document_id,
            organization_id=str(current_org.id),
        )
        return _classic_projection(row)

    now = datetime.now(timezone.utc).isoformat()
    if response is not None:
        response.headers["X-Corti-Retention-Policy"] = "acknowledged"
    ephemeral_id = str(uuid.uuid4())
    await log_action(
        db,
        str(current_user.id),
        current_user.username,
        "document.generate.ephemeral",
        "document",
        ephemeral_id,
        organization_id=str(current_org.id),
    )
    return DocumentsGetResponse(
        id=ephemeral_id,
        name=document_name,
        templateRef=template_ref,
        isStream=False,
        sections=[
            DocumentsSection(**item, createdAt=now, updatedAt=now) for item in sections
        ],
        createdAt=now,
        updatedAt=now,
        outputLanguage=body.outputLanguage,
        usageInfo=CommonUsageInfo(creditsConsumed=credits),
    )


@router.get(
    "/interactions/{interaction_id}/documents/",
    response_model=DocumentsListResponse,
    status_code=200,
)
@router.get(
    "/interactions/{interaction_id}/documents",
    response_model=DocumentsListResponse,
    status_code=200,
)
async def list_v2_tools_interaction_documents(
    interaction_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> DocumentsListResponse:
    """Corti §13.4 Documents Classic — ``GET /interactions/{id}/documents/``.

    Path-scoped to a single interaction UUID. Returns the
    ``{data: DocumentsGetResponse[]}`` envelope over real saved documents.
    """
    if not interaction_id or not interaction_id.strip():
        raise HTTPException(
            status_code=400,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 400,
                "type": "invalid_request",
                "detail": "interaction_id is required.",
            },
        )

    rows = await guided_document_repository.list_for_interaction(
        db,
        organization_id=str(current_org.id),
        owner_id=str(current_user.id),
        interaction_id=interaction_id.strip(),
    )
    return DocumentsListResponse(data=[_classic_projection(row) for row in rows])


async def _scoped_document_or_404(
    db: AsyncSession,
    *,
    current_org: Organization,
    current_user: User,
    interaction_id: str,
    document_id: str,
):
    row = await guided_document_repository.get_for_interaction(
        db,
        organization_id=str(current_org.id),
        owner_id=str(current_user.id),
        interaction_id=interaction_id,
        document_id=document_id,
    )
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "requestid": str(uuid.uuid4()),
                "status": 404,
                "type": "document_not_found",
                "detail": "Document was not found in this interaction scope.",
            },
        )
    return row


@router.get(
    "/interactions/{interaction_id}/documents/{document_id}",
    response_model=DocumentsGetResponse,
)
async def get_v2_tools_interaction_document(
    interaction_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> DocumentsGetResponse:
    row = await _scoped_document_or_404(
        db,
        current_org=current_org,
        current_user=current_user,
        interaction_id=interaction_id,
        document_id=document_id,
    )
    return _classic_projection(row)


@router.patch(
    "/interactions/{interaction_id}/documents/{document_id}",
    response_model=DocumentsGetResponse,
)
async def patch_v2_tools_interaction_document(
    interaction_id: str,
    document_id: str,
    body: DocumentsUpdateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> DocumentsGetResponse:
    row = await _scoped_document_or_404(
        db,
        current_org=current_org,
        current_user=current_user,
        interaction_id=interaction_id,
        document_id=document_id,
    )
    sections = None
    if body.sections is not None:
        sections = [item.model_dump(mode="json") for item in body.sections]
        keys = [item["key"] for item in sections]
        sorts = [item["sort"] for item in sections]
        if len(keys) != len(set(keys)) or len(sorts) != len(set(sorts)):
            raise HTTPException(
                status_code=422,
                detail={
                    "requestid": str(uuid.uuid4()),
                    "status": 422,
                    "type": "duplicate_document_section",
                    "detail": "Section keys and sort positions must be unique.",
                },
            )
    row = await guided_document_repository.update_classic(
        db,
        row,
        name=body.name.strip() if body.name is not None else None,
        sections=sections,
    )
    return _classic_projection(row)


@router.delete(
    "/interactions/{interaction_id}/documents/{document_id}",
    status_code=204,
)
async def delete_v2_tools_interaction_document(
    interaction_id: str,
    document_id: str,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
) -> Response:
    row = await _scoped_document_or_404(
        db,
        current_org=current_org,
        current_user=current_user,
        interaction_id=interaction_id,
        document_id=document_id,
    )
    await guided_document_repository.delete(db, row)
    return Response(status_code=204)
