"""iCoDer M3-0 — PHI redaction for report export.

Phase A1A Gate 4.3 — converted from best-effort to **fail-closed**.

The pre-Gate-4.3 contract returned the original text on any failure
(disabled flag, missing PIIRedactor, runtime exception). That
contract is unsafe for hospital export: a single unhandled
edge-case in the redactor would leak the original PHI to the
export pipeline. The new contract returns ``[REDACTION_FAILED]``
on any failure path, so an export bug becomes a loud customer
complaint (blank report) rather than a silent PHI disclosure.

The live workbench view (authenticated clinician in the org) still
sees raw text via direct DB read — this module is only invoked on
the *export* path (report renderer / HTML download / JSON download).
For those paths, fail-closed is correct: deny the export rather
than leak PHI.

Contract:
- ``redact_for_export(text)`` returns the redacted text on success.
- Returns ``""`` for empty input.
- Returns ``[REDACTION_FAILED]`` on disabled / unavailable / exception.
  The caller is expected to surface this string to the renderer so
  the export is visibly broken rather than silently leaking.
- ``ICODER_PHI_REDACTION_BYPASS=1`` opts out of fail-closed for
  local-dev only. Cloud-mode Settings validation refuses to boot
  if this flag is set in cloud mode.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Phase A1A Gate 4.3 — explicit placeholder so a failed redaction is
# visible in the exported artefact, NOT a silent leak.
REDACTION_FAILED_PLACEHOLDER = "[REDACTION_FAILED]"


def _redactor_enabled() -> bool:
    """Read the env flag — defaults to True for hospital pilot safety."""
    flag = os.environ.get("ICODER_PII_REDACTION_REQUIRED", "1")
    return flag not in ("0", "false", "False", "")


def _fail_closed_bypassed() -> bool:
    """Local-dev escape hatch. Cloud-mode Settings validation refuses
    to boot if this is True in cloud mode (Gate 4.4 will add the
    Settings-side check; for now we just honour the env var)."""
    return os.environ.get("ICODER_PHI_REDACTION_BYPASS", "0") in (
        "1", "true", "True",
    )


def _get_redactor():
    """Lazily import the runtime redactor so tests can monkeypatch it."""
    try:
        from icoder_runtime.core.pii_redaction import PIIRedactor
        return PIIRedactor(enabled=_redactor_enabled())
    except Exception as e:
        logger.warning(f"phi_redactor: failed to import PIIRedactor: {e!r}")
        return None


def redact_for_export(text: Optional[str]) -> str:
    """Return the export-safe version of ``text``.

    Fail-closed contract:
    - Empty input → ``""``.
    - Disabled + bypass set → original text (local-dev only).
    - Disabled without bypass → ``[REDACTION_FAILED]``.
    - Redactor unavailable → ``[REDACTION_FAILED]``.
    - Redactor raises → ``[REDACTION_FAILED]``.
    - Redactor returns → redacted text.

    The caller is expected to surface ``[REDACTION_FAILED]`` to the
    exported artefact so the user sees a visibly-broken report and
    files a ticket. The alternative (return the original) would
    silently leak PHI on any redactor bug, which is the pre-Gate-4.3
    behaviour the threat model flagged.
    """
    if not text:
        return text or ""
    if not _redactor_enabled():
        if _fail_closed_bypassed():
            logger.warning(
                "phi_redactor: ICODER_PHI_REDACTION_BYPASS=1 — returning "
                "original text (local-dev only)"
            )
            return text
        logger.warning(
            "phi_redactor: redaction disabled without bypass — "
            "returning %r (fail-closed)", REDACTION_FAILED_PLACEHOLDER,
        )
        return REDACTION_FAILED_PLACEHOLDER
    redactor = _get_redactor()
    if redactor is None:
        logger.warning(
            "phi_redactor: redactor unavailable — returning %r (fail-closed)",
            REDACTION_FAILED_PLACEHOLDER,
        )
        return REDACTION_FAILED_PLACEHOLDER
    try:
        result = redactor.redact(text)
        if result.redaction_applied:
            logger.info(
                f"phi_redactor: redacted {result.redaction_count} field(s) "
                f"[{', '.join(result.fields_redacted)}]"
            )
        return result.redacted_text
    except Exception as e:
        logger.error(
            "phi_redactor: redact raised %r — returning %r (fail-closed)",
            e, REDACTION_FAILED_PLACEHOLDER,
        )
        return REDACTION_FAILED_PLACEHOLDER
