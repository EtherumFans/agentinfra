"""iCoDer ``POST /api/v2/tools/guided-documents/`` — Corti §13.4 Guided Documents.

Cycle 3 (2026-06-30) — wire-shape parity with the Corti OpenAPI spec at
``docs/corti-reverse-engineered/guided-documents-generate.md`` for the
**simplest path** only:

  - ``templateRef`` supply variant (no overrides)
  - ``X-Corti-Retention-Policy: none`` header → 200 with
    ``GuidedDocumentsCreateEphemeralResponse``
  - The other two supply variants (``assemblyTemplate``,
    ``dynamicTemplate``) and the saved-retention 201 response are
    explicitly 422-rejected with a clear "future cycle" hint. They're
    documented in the OpenAPI; we don't fake-implement them in Cycle 3.

What this endpoint IS
---------------------
- A thin HTTP wrapper around iCoDer's LLM service that projects the model
  output to Corti's ``{document: {...}, usageInfo: {...}}`` envelope.

What this endpoint is NOT
--------------------------
- NOT a generic M3-0 document-generation endpoint. The legacy
  ``/api/text-gen/*`` surface stays untouched (M3-0 register-compatible).
- NOT a full implementation of all 21 guided-document CRUD endpoints
  (Sections, Templates, Documents Classic). Only this single generate
  action lands in Cycle 3.
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import ValidationError

from app.middleware.auth import get_current_user
from app.models.user import User
from app.schemas.v2_tools_guided_document import (
    CommonTextContext,
    CommonUsageInfo,
    ErrorResponse,
    GuidedDocumentsCreateEphemeralResponse,
    GuidedDocumentsGenerateByTemplateRef,
    GuidedEphemeralDocument,
    GuidedLabel,
)
from app.services.llm_service import llm_service

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


def _flatten_context(context: list[CommonTextContext] | None) -> str:
    """Concatenate text-shaped context items into one user prompt.

    Cycle 3 only supports the ``text`` context variant in the oneOf envelope
    (transcript/facts contexts land with assemblyTemplate/dynamicTemplate in
    a later cycle).
    """
    if not context:
        return ""
    parts: list[str] = []
    for item in context:
        if getattr(item, "type", None) == "text" and getattr(item, "text", ""):
            parts.append(item.text)
    return "\n\n".join(parts)


# ─── Endpoint ────────────────────────────────────────────────────────


@router.post(
    "/guided-documents/",
    response_model=GuidedDocumentsCreateEphemeralResponse,
    status_code=200,
)
@router.post(
    "/guided-documents",
    response_model=GuidedDocumentsCreateEphemeralResponse,
    status_code=200,
)
async def post_v2_tools_guided_documents(
    body: GuidedDocumentsGenerateByTemplateRef,
    current_user: User = Depends(get_current_user),
    x_corti_retention_policy: str | None = Header(
        default=None,
        alias="X-Corti-Retention-Policy",
        description="Pass 'none' to generate without saving (200 ephemeral). Omit to save (201 — Cycle 3 rejects with 422).",
    ),
):
    """Corti §13.4 Guided Documents — templateRef + ephemeral path (Cycle 3).

    Validates the request shape, then synthesizes a structured document by
    calling the LLM service and projecting the output to the Corti envelope.

    Returns 422 for paths outside Cycle 3 scope (saved retention,
    assemblyTemplate, dynamicTemplate, transcript/facts context variants).
    """
    # ── 1. Hospital-pilot gate ────────────────────────────────────────
    if not os.environ.get("ICODER_CREDENTIAL_LLM", "").strip():
        if os.environ.get("ICODER_ALLOW_DEGRADED_NO_KEY", "") != "1":
            raise HTTPException(
                status_code=503,
                detail=_err(
                    503,
                    "service_unavailable",
                    "ICODER_CREDENTIAL_LLM not set; hospital-pilot gate refuses to generate.",
                ),
            )

    # ── 2. Validate retention-policy header ──────────────────────────
    if x_corti_retention_policy is None or x_corti_retention_policy != "none":
        raise HTTPException(
            status_code=422,
            detail=_err(
                422,
                "unsupported_retention_policy",
                "Cycle 3 supports only ephemeral retention (X-Corti-Retention-Policy: none). "
                "Saved retention (201) lands in a later cycle.",
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

    # ── 4. Build LLM prompt ──────────────────────────────────────────
    user_prompt = _flatten_context(body.context or [])
    if not user_prompt and body.interactionId:
        # Cycle 3 cannot fetch facts/transcripts from an interactionId; tell
        # the caller clearly rather than silently producing an empty document.
        raise HTTPException(
            status_code=422,
            detail=_err(
                422,
                "interaction_unsupported",
                f"Cycle 3 cannot resolve context from interactionId={body.interactionId!r}; "
                "pass `context` instead. Full interaction-aware generation lands in a later cycle.",
            ),
        )
    if not user_prompt.strip():
        raise HTTPException(
            status_code=422,
            detail=_err(422, "empty_context", "context[].text is empty after flattening."),
        )

    system_prompt = (
        "You are iCoDer Guided Document generator (Cycle 3, templateRef path). "
        f"Template: {body.templateRef.templateId} (version: {body.templateRef.templateVersionId or 'published'}). "
        f"Output language: {body.outputLanguage}. "
        "Return a structured clinical document as a single JSON object whose top-level keys are section headings "
        "(e.g. 'subjective', 'objective', 'assessment', 'plan') and whose values are strings."
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
            logger.warning(f"PII redaction skipped (non-fatal): {_pii_err!r}")

    # ── 6. Run LLM ────────────────────────────────────────────────────
    try:
        result = await llm_service.chat(messages=messages, temperature=0.1, max_tokens=2048)
    except Exception as exc:
        logger.error(f"/api/v2/tools/guided-documents/ llm_service.chat failed: {exc!r}")
        raise HTTPException(
            status_code=500,
            detail=_err(500, "internal_error", f"LLM generation failed: {str(exc)[:200]}"),
        )

    content = result.get("content", "") if isinstance(result, dict) else ""
    usage = result.get("usage", None) if isinstance(result, dict) else None

    # ── 7. Parse model output → stringDocument map ───────────────────
    import json
    string_document: dict[str, str] = {}
    structured_document: dict[str, Any] | None = None
    if content and content.strip():
        try:
            # strip markdown fence if present
            t = content.strip()
            if t.startswith("```"):
                lines = t.split("\n")
                t = "\n".join(lines[1:]) if len(lines) > 1 else t
                if t.rstrip().endswith("```"):
                    t = t.rstrip()[:-3]
            parsed = json.loads(t)
            if isinstance(parsed, dict):
                # All string values map into stringDocument (Corti shape).
                for k, v in parsed.items():
                    if isinstance(v, str):
                        string_document[k] = v
                    else:
                        # Non-string values fall into structuredDocument
                        # so we never lose information.
                        structured_document = structured_document or {}
                        structured_document[k] = v
            elif isinstance(parsed, list):
                string_document["body"] = "\n".join(str(x) for x in parsed)
        except (json.JSONDecodeError, ValueError):
            # Model did not return JSON; keep the raw content under 'body'.
            string_document["body"] = content
    if not string_document:
        # Worst-case fallback: keep the raw content rather than return empty doc.
        string_document["body"] = content or "(empty)"

    # ── 8. Estimate credits (deterministic for test reproducibility) ─
    credits = 0.0
    if isinstance(usage, dict):
        total = usage.get("total_tokens")
        if total is None:
            total = (usage.get("prompt_tokens", 0) or 0) + (usage.get("completion_tokens", 0) or 0)
        try:
            credits = round(max(0.0, float(total) / 1000.0 * 0.011), 6)
        except (TypeError, ValueError):
            credits = 0.0

    # ── 9. Corti-shape projection ────────────────────────────────────
    ephemeral_doc = GuidedEphemeralDocument(
        name=f"guided-{body.templateRef.templateId}-{uuid.uuid4().hex[:8]}",
        templateId=body.templateRef.templateId,
        templateVersionId=body.templateRef.templateVersionId or "00000000-0000-0000-0000-000000000000",
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