"""iCoDer ``POST /api/v2/tools/guided-documents/`` — Corti Guided Documents.

Wire-shape parity with the captured Corti OpenAPI contract includes all three
template supply variants (reference, assembly, and dynamic), authenticated
Facts/STT interaction context resolution, ephemeral generation, and encrypted
default-retention persistence. Runtime overrides and auto-generated aggregate
metadata are retained for later template discovery.

What this endpoint IS
---------------------
- A thin HTTP wrapper around iCoDer's canonical LLM Gateway that projects the model
  output to Corti's ``{document: {...}, usageInfo: {...}}`` envelope.
- Mock/degraded providers, failed PHI redaction, malformed JSON and empty
  documents fail closed instead of being returned as clinical output.

What this endpoint is NOT
--------------------------
- NOT a generic M3-0 document-generation endpoint. The legacy
  ``/api/text-gen/*`` surface stays untouched (M3-0 register-compatible).
- NOT a claim that every template/section administration endpoint is present.
  Generation and the implemented discovery/Classic lifecycle remain separate
  from the outstanding publish/version administration surface.
"""

from __future__ import annotations

import logging
import json
import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth import get_current_organization, get_current_user
from app.models.organization import Organization
from app.models.user import User
from app.schemas.v2_tools_guided_document import (
    CommonUsageInfo,
    ErrorResponse,
    GuidedDocument,
    GuidedDocumentsCreateResponse,
    GuidedDocumentsCreateEphemeralResponse,
    GuidedDocumentsGenerateRequest,
    GuidedEphemeralDocument,
    GuidedLabel,
)
from app.services.clinical_fact_repository import clinical_fact_repository
from app.services.guided_document_repository import guided_document_repository
from app.services.guided_template_catalog import (
    create_auto_template,
    public_template_id,
    public_template_version_id,
    resolve_public_template,
    template_definition,
)
from app.services.guided_section_catalog import resolve_curated_section
from app.services.guided_section_repository import guided_section_repository
from app.services.stt_artifact_repository import stt_artifact_repository
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/tools", tags=["v2-tools"])


# ─── Helpers ─────────────────────────────────────────────────────────


def _err(status_code: int, type_: str, detail: str, validation: list | None = None) -> dict[str, Any]:
    """Corti-shape ErrorResponse envelope (for HTTPException detail).

    Per the Corti OpenAPI, ``validationErrors`` is ``type: array`` (NOT
    nullable), so we either drop the key entirely (when we have no
    per-field errors) or emit an empty list — never ``null``.
    """
    payload = ErrorResponse(
        requestid=str(uuid.uuid4()),
        status=status_code,
        type=type_,
        detail=detail,
        validationErrors=validation if validation is not None else [],
    )
    dumped = payload.model_dump(mode="json", exclude_none=False)
    if validation is None:
        dumped.pop("validationErrors", None)
    return dumped


def _flatten_context(context: list[Any] | None) -> str:
    """Flatten Corti text, transcript and facts context variants."""
    if not context:
        return ""
    parts: list[str] = []
    for item in context:
        context_type = getattr(item, "type", None)
        if context_type == "text" and getattr(item, "text", ""):
            parts.append(f"Text context:\n{item.text}")
        elif context_type == "transcript":
            segments = [segment.text for segment in item.transcript.transcripts]
            parts.append("Transcript context:\n" + "\n".join(segments))
        elif context_type == "facts":
            facts = [
                f"- [{fact.group or 'other'}] {fact.text}"
                for fact in item.facts
            ]
            parts.append("Facts context:\n" + "\n".join(facts))
    return "\n\n".join(parts)


def _merge_section_override(
    section: dict[str, Any], override: dict[str, Any] | None
) -> dict[str, Any]:
    if not override:
        return section
    merged = json.loads(json.dumps(section))
    if override.get("heading") is not None:
        merged["heading"] = override["heading"]
    instructions = override.get("instructions")
    if isinstance(instructions, dict):
        merged.setdefault("instructions", {}).update(instructions)
    if "outputSchema" in override:
        merged["outputSchema"] = override["outputSchema"]
    return merged


def _validate_schema_definition(node: Any, path: str = "outputSchema") -> None:
    if not isinstance(node, dict):
        raise ValueError(f"{path} must be an object")
    node_type = node.get("type")
    if node_type not in {"string", "number", "boolean", "array", "object"}:
        raise ValueError(f"{path}.type is unsupported")
    if node_type == "array":
        if "items" not in node:
            raise ValueError(f"{path}.items is required")
        _validate_schema_definition(node["items"], f"{path}.items")
        minimum = node.get("minItems")
        maximum = node.get("maxItems")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValueError(f"{path}.minItems exceeds maxItems")
    if node_type == "object":
        keys: set[str] = set()
        for index, field in enumerate(node.get("fields", [])):
            if not isinstance(field, dict) or not str(field.get("key", "")).strip():
                raise ValueError(f"{path}.fields[{index}].key is required")
            key = str(field["key"])
            if key in keys:
                raise ValueError(f"{path}.fields contains duplicate key {key}")
            keys.add(key)
            _validate_schema_definition(field.get("value"), f"{path}.fields[{index}].value")


def _validate_generated_value(value: Any, node: dict[str, Any], path: str) -> None:
    node_type = node["type"]
    valid = (
        (node_type == "string" and isinstance(value, str))
        or (node_type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
        or (node_type == "boolean" and isinstance(value, bool))
        or (node_type == "array" and isinstance(value, list))
        or (node_type == "object" and isinstance(value, dict))
    )
    if not valid:
        raise ValueError(f"{path} does not match type {node_type}")
    if "enum" in node and value not in node["enum"]:
        raise ValueError(f"{path} is outside enum")
    if node_type == "number":
        if node.get("minimum") is not None and value < node["minimum"]:
            raise ValueError(f"{path} is below minimum")
        if node.get("maximum") is not None and value > node["maximum"]:
            raise ValueError(f"{path} exceeds maximum")
    elif node_type == "array":
        if node.get("minItems") is not None and len(value) < node["minItems"]:
            raise ValueError(f"{path} has too few items")
        if node.get("maxItems") is not None and len(value) > node["maxItems"]:
            raise ValueError(f"{path} has too many items")
        for index, item in enumerate(value):
            _validate_generated_value(item, node["items"], f"{path}[{index}]")
    elif node_type == "object":
        for field in node.get("fields", []):
            key = field["key"]
            if key in value:
                _validate_generated_value(value[key], field["value"], f"{path}.{key}")
            elif field.get("default") is None:
                raise ValueError(f"{path}.{key} is required")


def _definition_sections(definition: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not definition:
        return []
    value = definition.get("sections", [])
    return value if isinstance(value, list) else []


async def _resolve_template_supply(
    db: AsyncSession,
    *,
    organization_id: str,
    owner_id: str,
    body: GuidedDocumentsGenerateRequest,
):
    """Resolve or persist exactly one template supply path."""
    if body.templateRef is not None:
        base = await resolve_public_template(
            db,
            organization_id=organization_id,
            template_id=body.templateRef.templateId,
        )
        if base is None:
            raise HTTPException(
                status_code=404,
                detail=_err(404, "template_not_found", "Referenced template was not found."),
            )
        base_version = public_template_version_id(base)
        if (
            body.templateRef.templateVersionId is not None
            and body.templateRef.templateVersionId != base_version
        ):
            raise HTTPException(
                status_code=404,
                detail=_err(404, "template_version_not_found", "Template version was not found."),
            )
        definition = template_definition(base) or {
            "instructions": {"prompt": base.content},
            "sections": [],
        }
        overrides = body.templateRef.overrides
        if not overrides:
            return base, definition, "templateRef"
        patched = json.loads(json.dumps(definition))
        if isinstance(overrides.get("instructions"), dict):
            prompt = str(overrides["instructions"].get("prompt", "")).strip()
            if not prompt:
                raise HTTPException(
                    status_code=422,
                    detail=_err(422, "invalid_template_override", "instructions.prompt is required."),
                )
            patched["instructions"] = {"prompt": prompt}
        section_overrides = overrides.get("sections", [])
        if section_overrides:
            sections = _definition_sections(patched)
            by_id = {section.get("sectionId"): section for section in sections}
            for override in section_overrides:
                section_id = override.get("sectionId") if isinstance(override, dict) else None
                if section_id not in by_id:
                    raise HTTPException(
                        status_code=422,
                        detail=_err(
                            422,
                            "section_override_invalid",
                            "Override section is not linked to the base template.",
                        ),
                    )
                patched_section = _merge_section_override(
                    by_id[section_id], override.get("generation")
                )
                sections[sections.index(by_id[section_id])] = patched_section
                by_id[section_id] = patched_section
        patched["inheritedFromId"] = public_template_id(base)
        aggregate = await create_auto_template(
            db,
            organization_id=organization_id,
            name=f"{base.name} (runtime override)",
            output_language=body.outputLanguage,
            definition=patched,
        )
        return aggregate, patched, "templateRef-overrides"

    if body.dynamicTemplate is not None:
        definition = body.dynamicTemplate.generation.model_dump(mode="json")
        seen_headings: set[str] = set()
        for index, section in enumerate(_definition_sections(definition)):
            heading = section["heading"].strip()
            if heading.casefold() in seen_headings:
                raise HTTPException(
                    status_code=422,
                    detail=_err(422, "duplicate_section_heading", heading),
                )
            seen_headings.add(heading.casefold())
            try:
                _validate_schema_definition(section["outputSchema"], f"sections[{index}].outputSchema")
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail=_err(422, "invalid_output_schema", str(exc)),
                ) from exc
        persisted_sections: list[dict[str, Any]] = []
        for section in _definition_sections(definition):
            row = await guided_section_repository.create(
                db,
                organization_id=organization_id,
                owner_id=owner_id,
                language=body.outputLanguage,
                definition=section,
            )
            persisted_sections.append(guided_section_repository.definition(row))
        definition["sections"] = persisted_sections
        aggregate = await create_auto_template(
            db,
            organization_id=organization_id,
            name=body.dynamicTemplate.name,
            output_language=body.outputLanguage,
            definition=definition,
        )
        return aggregate, definition, "dynamicTemplate"

    assert body.assemblyTemplate is not None
    sections: list[dict[str, Any]] = []
    for index, ref in enumerate(body.assemblyTemplate.sectionRefs):
        section = await guided_section_repository.resolve(
            db,
            organization_id=organization_id,
            section_id=ref.sectionId,
            version_id=ref.sectionVersionId,
        )
        if section is None:
            section = resolve_curated_section(ref.sectionId, ref.sectionVersionId)
        if section is None:
            raise HTTPException(
                status_code=404,
                detail=_err(404, "section_not_found", f"sectionRefs[{index}] was not found."),
            )
        section = _merge_section_override(section, ref.overrides)
        try:
            _validate_schema_definition(section["outputSchema"], f"sectionRefs[{index}].outputSchema")
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail=_err(422, "invalid_output_schema", str(exc)),
            ) from exc
        sections.append(section)
    definition = {
        "instructions": (
            body.assemblyTemplate.instructions.model_dump(mode="json")
            if body.assemblyTemplate.instructions
            else {"prompt": "Generate only the documented content for each section."}
        ),
        "sections": sections,
    }
    aggregate = await create_auto_template(
        db,
        organization_id=organization_id,
        name=body.assemblyTemplate.name,
        output_language=body.outputLanguage,
        definition=definition,
    )
    return aggregate, definition, "assemblyTemplate"


async def _interaction_context(
    db: AsyncSession,
    *,
    organization_id: str,
    owner_id: str,
    interaction_id: str,
) -> str:
    """Resolve completed transcripts and non-discarded facts in tenant scope."""
    scope = {
        "organization_id": organization_id,
        "owner_id": owner_id,
        "interaction_id": interaction_id,
    }
    facts = await clinical_fact_repository.list(db, **scope)
    transcripts = await stt_artifact_repository.list_transcripts(db, **scope)
    parts: list[str] = []
    usable_facts = [row for row in facts if not row.is_discarded]
    if usable_facts:
        fact_lines = [
            f"- [{row.group_key}] {clinical_fact_repository.text(row)}"
            for row in usable_facts
        ]
        parts.append("Persisted clinical facts:\n" + "\n".join(fact_lines))
    usable_transcripts = [
        stt_artifact_repository.transcript_text(row).strip()
        for row in transcripts
        if row.status == "completed" and stt_artifact_repository.transcript_text(row).strip()
    ]
    if usable_transcripts:
        parts.append("Completed transcripts:\n" + "\n\n".join(usable_transcripts))
    return "\n\n".join(parts)


async def _invoke_guided_document_model(
    messages: list[dict[str, str]],
) -> dict[str, Any]:
    """Invoke the canonical gateway and reject mock/degraded output."""
    from app.main import app as application

    gateway = getattr(application.state, "platform_gateway", None)
    if gateway is None:
        raise RuntimeError("platform_gateway_unavailable")
    result = await gateway.generate(
        messages,
        response_schema={"type": "object"},
        context={"operation": "corti_guided_document", "clinical": True},
    )
    if not isinstance(result, dict):
        raise RuntimeError("guided_document_provider_response_invalid")
    if result.get("degraded") is True or result.get("is_mock") is True:
        raise RuntimeError("guided_document_provider_degraded")
    return result


# ─── Endpoint ────────────────────────────────────────────────────────


@router.post(
    "/guided-documents/",
    response_model=GuidedDocumentsCreateEphemeralResponse | GuidedDocumentsCreateResponse,
    status_code=200,
)
@router.post(
    "/guided-documents",
    response_model=GuidedDocumentsCreateEphemeralResponse | GuidedDocumentsCreateResponse,
    status_code=200,
)
async def post_v2_tools_guided_documents(
    body: GuidedDocumentsGenerateRequest,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    response: Response = None,
    x_corti_retention_policy: str | None = Header(
        default=None,
        alias="X-Corti-Retention-Policy",
        description="Pass 'none' for 200 ephemeral; omit for saved 201 retention.",
    ),
):
    """Generate through templateRef, assemblyTemplate, or dynamicTemplate.

    Validates the request shape, then synthesizes a structured document by
    calling the canonical LLM Gateway and projecting the output to the Corti envelope.

    Default retention persists an encrypted document and returns 201.
    """
    # ── 1. Hospital-pilot gate ────────────────────────────────────────
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        raise HTTPException(
            status_code=503,
            detail=_err(
                503,
                "service_unavailable",
                "ICODER_CREDENTIAL_LLM is not configured through CredentialVault.",
            ),
        )

    # ── 2. Validate retention and context invariants ─────────────────
    if x_corti_retention_policy not in {None, "none"}:
        raise HTTPException(
            status_code=422,
            detail=_err(
                422,
                "unsupported_retention_policy",
                "X-Corti-Retention-Policy supports only 'none' or omission.",
            ),
        )

    # ── 3. Validate required input context ───────────────────────────
    if not body.context and not body.interactionId:
        raise HTTPException(
            status_code=422,
            detail=_err(
                422,
                "missing_context",
                "At least one of `context` or `interactionId` must be supplied.",
            ),
        )
    if body.context and body.interactionId:
        raise HTTPException(
            status_code=422,
            detail=_err(
                422,
                "ambiguous_context",
                "Exactly one of `context` or `interactionId` must be supplied.",
            ),
        )

    template, definition, supply_path = await _resolve_template_supply(
        db,
        organization_id=str(current_org.id),
        owner_id=str(current_user.id),
        body=body,
    )
    resolved_template_id = public_template_id(template)
    resolved_version_id = public_template_version_id(template)

    # ── 4. Build LLM prompt ──────────────────────────────────────────
    context_parts: list[str] = []
    explicit_context = _flatten_context(body.context or []).strip()
    if explicit_context:
        context_parts.append("Request context:\n" + explicit_context)
    if body.interactionId:
        interaction_id = body.interactionId.strip()
        if not interaction_id or len(interaction_id) > 160:
            raise HTTPException(
                status_code=422,
                detail=_err(422, "invalid_interaction", "interactionId is invalid."),
            )
        resolved = await _interaction_context(
            db,
            organization_id=str(current_org.id),
            owner_id=str(current_user.id),
            interaction_id=interaction_id,
        )
        if resolved:
            context_parts.append(resolved)
    user_prompt = "\n\n".join(context_parts)
    if not user_prompt and body.interactionId:
        raise HTTPException(
            status_code=422,
            detail=_err(
                422,
                "interaction_context_unavailable",
                "The interaction has no completed transcript or active persisted facts.",
            ),
        )
    if not user_prompt.strip():
        raise HTTPException(
            status_code=422,
            detail=_err(422, "empty_context", "context[].text is empty after flattening."),
        )

    system_prompt = (
        f"You are iCoDer Guided Document generator ({supply_path} path). "
        f"Template: {template.name} ({resolved_template_id}, version: {resolved_version_id}). "
        f"Resolved template definition: {json.dumps(definition, ensure_ascii=False)}. "
        f"Output language: {body.outputLanguage}. "
        "Return one JSON object. When sections are defined, top-level keys must exactly match their headings "
        "and each value must satisfy that section's outputSchema. Do not invent undocumented facts."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # ── 5. PII redaction (best-effort; never blocks) ─────────────────
    try:
        from app.main import app as _app
        _data_policy = getattr(_app.state, "data_policy", None) if _app else None
    except Exception:
        _data_policy = None
    if _data_policy is not None and getattr(_data_policy, "pii_redaction_required", False):
        try:
            from icoder_runtime.core.pii_redaction import PIIRedactor
            redactor = PIIRedactor(enabled=True)
            messages, _ = redactor.redact_messages(messages)
        except Exception as _pii_err:
            logger.error(
                "guided-document PHI redaction failed error_type=%s",
                type(_pii_err).__name__,
            )
            raise HTTPException(
                status_code=503,
                detail=_err(503, "phi_redaction_failed", "PHI redaction failed."),
            ) from _pii_err

    # ── 6. Run LLM ────────────────────────────────────────────────────
    try:
        result = await _invoke_guided_document_model(messages)
    except Exception as exc:
        logger.error(
            "/api/v2/tools/guided-documents gateway failed error_type=%s",
            type(exc).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail=_err(503, "service_unavailable", f"LLM generation failed: {str(exc)[:200]}"),
        ) from exc

    content = result.get("content", "") if isinstance(result, dict) else ""
    usage = result.get("usage", None) if isinstance(result, dict) else None

    # ── 7. Parse model output → stringDocument map ───────────────────
    string_document: dict[str, str] = {}
    structured_document: dict[str, Any] | None = None
    try:
        t = content.strip()
        if t.startswith("```"):
            lines = t.split("\n")
            t = "\n".join(lines[1:]) if len(lines) > 1 else t
            if t.rstrip().endswith("```"):
                t = t.rstrip()[:-3]
        parsed = json.loads(t)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=503,
            detail=_err(503, "invalid_provider_response", "Provider returned invalid JSON."),
        ) from exc
    if not isinstance(parsed, dict) or not parsed:
        raise HTTPException(
            status_code=503,
            detail=_err(503, "invalid_provider_response", "Provider returned no document sections."),
        )
    resolved_sections = _definition_sections(definition)
    if resolved_sections:
        expected = {section["heading"]: section for section in resolved_sections}
        if set(parsed) != set(expected):
            raise HTTPException(
                status_code=503,
                detail=_err(
                    503,
                    "invalid_provider_response",
                    "Provider section headings do not match the resolved template.",
                ),
            )
        try:
            for heading, section in expected.items():
                _validate_generated_value(
                    parsed[heading], section["outputSchema"], f"document.{heading}"
                )
        except ValueError as exc:
            raise HTTPException(
                status_code=503,
                detail=_err(503, "invalid_provider_response", str(exc)),
            ) from exc
    for key, value in parsed.items():
        if not isinstance(key, str) or not key.strip():
            continue
        if isinstance(value, str):
            if value.strip():
                string_document[key] = value
        else:
            string_document[key] = json.dumps(value, ensure_ascii=False)
            structured_document = structured_document or {}
            structured_document[key] = value
    if not string_document and not structured_document:
        raise HTTPException(
            status_code=503,
            detail=_err(503, "invalid_provider_response", "Provider document sections were empty."),
        )

    # ── 8. Estimate credits (deterministic for test reproducibility) ─
    credits = 0.0
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total is None:
            total = (
                usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0
            ) + (
                usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
            )
        try:
            credits = round(max(0.0, float(total) / 1000.0 * 0.011), 6)
        except (TypeError, ValueError):
            credits = 0.0

    # ── 9. Corti-shape projection ────────────────────────────────────
    document_name = f"guided-{template.name}-{uuid.uuid4().hex[:8]}"
    labels = [item.model_dump(mode="json") for item in (body.labels or [])]
    if x_corti_retention_policy is None:
        row = await guided_document_repository.create(
            db,
            organization_id=str(current_org.id),
            owner_id=str(current_user.id),
            interaction_id=body.interactionId,
            name=document_name,
            template_id=resolved_template_id,
            template_version_id=resolved_version_id,
            language=body.outputLanguage,
            string_document=string_document,
            structured_document=structured_document,
            labels=labels,
            credits_consumed=credits,
        )
        if response is not None:
            response.status_code = 201
        saved = GuidedDocument(
            id=row.document_id,
            name=row.name,
            templateId=row.template_id,
            templateVersionId=row.template_version_id,
            language=row.language,
            interactionId=row.interaction_id,
            stringDocument=guided_document_repository.string_document(row),
            structuredDocument=guided_document_repository.structured_document(row),
            labels=guided_document_repository.labels(row),
            createdAt=row.created_at.isoformat(),
            updatedAt=row.updated_at.isoformat(),
        )
        return GuidedDocumentsCreateResponse(
            document=saved,
            usageInfo=CommonUsageInfo(creditsConsumed=credits),
        )

    ephemeral_doc = GuidedEphemeralDocument(
        name=document_name,
        templateId=resolved_template_id,
        templateVersionId=resolved_version_id,
        language=body.outputLanguage,
        interactionId=body.interactionId,
        stringDocument=string_document,
        structuredDocument=structured_document,
        labels=body.labels or [],
    )
    return GuidedDocumentsCreateEphemeralResponse(
        document=ephemeral_doc,
        usageInfo=CommonUsageInfo(creditsConsumed=credits),
    )
