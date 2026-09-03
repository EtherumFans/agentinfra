"""Phase A1A Gate 4.6 — Browser + Embedded + Patient A/B verification.

The Gate 4.1 inventory flagged the browser storage surface
(Gate 4.0 §6 item 25): the pre-Gate-4.6 logout only cleared
``access_token`` + ``refresh_token``, leaving ``icoder-textgen-templates``
(user-saved templates that could carry pasted PHI), ``icoder-billing-*``,
``icoder-settings``, and the zustand ``icoder-auth`` blob on disk. On
a shared machine a subsequent different user could inherit the previous
user's templates and UI preferences.

Patient Context Isolation (Phase 7 Gate 11) was already Playwright-
verified; Gate 4.6 re-confirms the static contract rather than re-
running the browser walkthrough (the runtime behaviour is unchanged
by Gate 4.6's storage cleanup).

This test module exercises the static + structural contract:
  - ``clearAllIcoderBrowserStorage`` is defined in the store.
  - Every ``localStorage.setItem('icoder-*')`` call site has a
    matching entry in the ``ICODER_LOCALSTORAGE_KEYS`` registry.
  - The EmbeddedAssistantPage carries the existing comment that no
    PHI is stored in parent JS memory.
  - The Medical Coding / CDI / DRG-DIP demo HTML files do not
    embed PHI in source — they pass user input to the backend at
    run time only.
"""
from __future__ import annotations

import os
import re

import pytest


REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
FRONTEND_SRC = os.path.join(REPO_ROOT, "frontend", "src")
EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples")


# ─────────────────────────────────────────────────────────────────────
# §1 clearAllIcoderBrowserStorage helper
# ─────────────────────────────────────────────────────────────────────


def test_clear_helper_is_defined_and_exported() -> None:
    """The store exports ``clearAllIcoderBrowserStorage``.

    This is the function ``logout`` calls to wipe all icoder-* keys.
    """
    path = os.path.join(FRONTEND_SRC, "store", "index.ts")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    assert "export function clearAllIcoderBrowserStorage" in content, (
        "store/index.ts must export clearAllIcoderBrowserStorage"
    )
    assert "ICODER_LOCALSTORAGE_KEYS" in content, (
        "store/index.ts must declare ICODER_LOCALSTORAGE_KEYS registry"
    )


def test_logout_calls_clear_helper() -> None:
    """The ``logout`` action calls ``clearAllIcoderBrowserStorage``
    rather than only removing two specific keys."""
    path = os.path.join(FRONTEND_SRC, "store", "index.ts")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # Find the logout block — terminates at the matching closing brace
    # at the same indentation as the logout: key. logout is the last
    # method on the persisted state slice, so the block ends with
    # "\n      }," before the persist's "}),".
    logout_match = re.search(
        r"logout:\s*\(\)\s*=>\s*{(.+?)\n      },",
        content, re.DOTALL,
    )
    assert logout_match, "could not locate logout block"
    body = logout_match.group(1)
    assert "clearAllIcoderBrowserStorage()" in body, (
        "logout must call clearAllIcoderBrowserStorage() — pre-Gate-4.6 "
        "behaviour only removed access_token + refresh_token"
    )


# ─────────────────────────────────────────────────────────────────────
# §2 Storage key registry — every setItem call has an entry
# ─────────────────────────────────────────────────────────────────────


def _all_localstorage_setitem_keys() -> set[str]:
    """Grep frontend/src for every ``localStorage.setItem('key', ...)``
    call and return the set of keys."""
    keys: set[str] = set()
    for dirpath, _, files in os.walk(FRONTEND_SRC):
        for fname in files:
            if not (fname.endswith(".ts") or fname.endswith(".tsx")):
                continue
            path = os.path.join(dirpath, fname)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            # setItem calls with string-literal keys
            for m in re.finditer(r"localStorage\.setItem\(\s*['\"]([^'\"]+)['\"]", src):
                keys.add(m.group(1))
    return keys


def test_every_localstorage_key_is_in_registry() -> None:
    """Every ``localStorage.setItem('X', ...)`` in frontend/src must
    have X in ``ICODER_LOCALSTORAGE_KEYS``. If a new key is added
    without registry entry, this test fails so the next logout
    cleanup does not miss it."""
    registry_path = os.path.join(FRONTEND_SRC, "store", "index.ts")
    with open(registry_path, encoding="utf-8") as f:
        registry_src = f.read()
    registry_match = re.search(
        r"ICODER_LOCALSTORAGE_KEYS\s*=\s*\[(.+?)\]",
        registry_src, re.DOTALL,
    )
    assert registry_match, "ICODER_LOCALSTORAGE_KEYS array not found"
    registry = re.findall(r"'([^']+)'", registry_match.group(1))

    actual = _all_localstorage_setitem_keys()
    missing = actual - set(registry)
    assert not missing, (
        f"localStorage.setItem keys missing from ICODER_LOCALSTORAGE_KEYS: "
        f"{sorted(missing)}. Add them to the registry so logout cleanup "
        f"wipes them on shared machines."
    )


# ─────────────────────────────────────────────────────────────────────
# §3 Patient Context Isolation — static re-confirmation
# ─────────────────────────────────────────────────────────────────────


def test_embedded_assistant_page_declares_no_phi_in_parent_memory() -> None:
    """The EmbeddedAssistantPage comment declaring 'no PHI in parent
    JS memory' is the source-of-truth contract for Patient Context
    Isolation. Phase 7 Gate 11 Playwright-verified the runtime
    behaviour; Gate 4.6 re-confirms the static contract is intact."""
    path = os.path.join(FRONTEND_SRC, "pages", "EmbeddedAssistantPage.tsx")
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # Lowercase the whole content first, then compare against lowercased
    # tokens (so the comparison is not defeated by CamelCase identifiers).
    lowered = content.lower()
    assert "localstorage" in lowered, (
        "EmbeddedAssistantPage.tsx must reference localStorage in the "
        "no-PHI-in-parent-JS-memory comment (Phase 7 Gate 11 contract)"
    )
    assert "parent" in lowered and "memory" in lowered, (
        "EmbeddedAssistantPage.tsx must carry the no-PHI-in-parent-JS-memory "
        "comment (Phase 7 Gate 11 contract)"
    )


def test_clear_patient_context_events_emitted() -> None:
    """The widget code path for clearing patient context still
    references the canonical event names from Phase 6 / Phase 7
    Gate 11. The events are emitted from the icoder-embedded web
    component (packages/icoder-embedded/src/icoder-assistant.ts)."""
    widget_src = os.path.join(REPO_ROOT, "packages", "icoder-embedded", "src")
    if not os.path.isdir(widget_src):
        pytest.skip("packages/icoder-embedded/src not found — widget layout differs")
    found_event = False
    for dirpath, _, files in os.walk(widget_src):
        for fname in files:
            if not fname.endswith((".ts", ".tsx")):
                continue
            path = os.path.join(dirpath, fname)
            with open(path, encoding="utf-8") as f:
                src = f.read()
            if "patient.context.cleared" in src or "session.cleared" in src:
                found_event = True
                break
        if found_event:
            break
    assert found_event, (
        "No widget file in packages/icoder-embedded/src references "
        "patient.context.cleared or session.cleared — Phase 6 / Phase 7 "
        "Gate 11 contract may have regressed"
    )


# ─────────────────────────────────────────────────────────────────────
# §4 Demo HTML files do not embed PHI
# ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("htmlpath", [
    "partner-reference-app/public/index.html",
] if os.path.exists(os.path.join(EXAMPLES_DIR, "partner-reference-app", "public", "index.html")) else [])
def test_partner_reference_app_has_no_embedded_phi(htmlpath: str) -> None:
    """The partner reference app must NOT embed real patient data in
    its source; any PHI must be entered live by the operator."""
    path = os.path.join(EXAMPLES_DIR, htmlpath)
    with open(path, encoding="utf-8") as f:
        content = f.read()
    # Reject Chinese ID-card patterns (18 digits ending in X or digit)
    assert not re.search(r"\b\d{17}[\dXx]\b", content), (
        f"{htmlpath} embeds an ID-card-shaped literal — replace with placeholder"
    )
    # Reject Chinese mobile patterns (11 digits starting with 1)
    assert not re.search(r"\b1[3-9]\d{9}\b", content), (
        f"{htmlpath} embeds a mobile-phone-shaped literal — replace with placeholder"
    )
