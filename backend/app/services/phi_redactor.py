"""iCoDer M3-0 — PHI redaction for report export.

Wraps the runtime ``PIIRedactor`` so the API layer can redact encounter
text, review notes, and reason codes before they reach the report
renderer / exported HTML / JSON file. The redactor is intentionally
simple (rule-based, see ``icoder_runtime/core/pii_redaction.py``) and
its docstring self-warns it is NOT production-grade medical
de-identification. For a hospital pilot the export path is the only
leak vector — the live workbench view continues to show the raw text
to the authenticated coder.

Contract:
- ``redact_for_export(text)`` returns the redacted text (or original
  if redactor disabled or text empty).
- The function is best-effort — failures are caught and the original
  text is returned so the export never blocks on a redactor bug.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


def _redactor_enabled() -> bool:
    """Read the env flag — defaults to True for hospital pilot safety."""
    flag = os.environ.get("ICODER_PII_REDACTION_REQUIRED", "1")
    return flag not in ("0", "false", "False", "")


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

    - Returns the original text when the redactor is unavailable.
    - Returns the original text when redaction is disabled.
    - Returns the redacted text + logs a count of fields redacted.

    The function never raises — failures are swallowed and the original
    text is returned so the export pipeline never blocks on a redactor
    bug.
    """
    if not text:
        return text or ""
    if not _redactor_enabled():
        return text
    redactor = _get_redactor()
    if redactor is None:
        return text
    try:
        result = redactor.redact(text)
        if result.redaction_applied:
            logger.info(
                f"phi_redactor: redacted {result.redaction_count} field(s) "
                f"[{', '.join(result.fields_redacted)}]"
            )
        return result.redacted_text
    except Exception as e:
        logger.warning(f"phi_redactor: redact failed, returning original: {e!r}")
        return text
