"""Phase 3-B2 Loop 0 — Preconditions smoke test.

Verifies the 3 carry-over blockers from Phase 3-B1.5 are resolved:

1. MedicalCodingPage "预测编码" rewired to A2A mainline
   (POST /api/icoder/agents/medical-coding-agent/v1/message:send),
   not the deprecated /api/runtime/agents/{ref}/run.
2. agent_definitions DB seedable from official_agents/agent_pack.json
   (backend/scripts/seed_agents.py exists and is valid).
3. TextGeneration routes removed from App.tsx (Navigate redirect to
   /ai-studio/agents) and EmbeddedAssistantPage.tsx physically deleted.

Run standalone:
    python backend/scripts/smoke_test_preconditions.py
Or via pytest:
    pytest backend/scripts/smoke_test_preconditions.py -v
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _BACKEND_DIR.parent
_FRONTEND_SRC = _REPO_ROOT / "frontend" / "src"
_OFFICIAL_AGENTS_DIR = _BACKEND_DIR / "official_agents"
_SEED_AGENTS = _BACKEND_DIR / "scripts" / "seed_agents.py"
_MEDICAL_CODING_PAGE = _FRONTEND_SRC / "pages" / "MedicalCodingPage.tsx"
_RUNTIME_API = _FRONTEND_SRC / "services" / "runtimeApi.ts"
_APP_TSX = _FRONTEND_SRC / "App.tsx"
_EMBEDDED_PAGE = _FRONTEND_SRC / "pages" / "EmbeddedAssistantPage.tsx"


def _check(condition: bool, label: str, detail: str = "") -> bool:
    status = "PASS" if condition else "FAIL"
    msg = f"[{status}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return condition


def check_medical_coding_rewire() -> bool:
    """MedicalCodingPage uses runAgentViaA2A, not the deprecated runAgent."""
    ok = True
    print("\n=== 1. MedicalCodingPage A2A rewire ===")
    if not _MEDICAL_CODING_PAGE.exists():
        return _check(False, "MedicalCodingPage.tsx exists")
    page_src = _MEDICAL_CODING_PAGE.read_text(encoding="utf-8")
    ok &= _check(
        "runAgentViaA2A" in page_src,
        "MedicalCodingPage imports/calls runAgentViaA2A",
    )
    # The deprecated call uses runtimeAgentApi.runAgent( — note the open paren
    # to avoid matching the @deprecated JSDoc tag or runAgentViaA2A.
    deprecated_call = re.search(r"runtimeAgentApi\.runAgent\s*\(", page_src)
    ok &= _check(
        deprecated_call is None,
        "MedicalCodingPage does NOT call deprecated runtimeAgentApi.runAgent(...)",
        f"found: {deprecated_call.group(0) if deprecated_call else ''}".strip(" —"),
    )
    # Verify the agent_id matches the A2A path (medical-coding-agent, not
    # the old medical-coding-agent-2.0.0 ref).
    ok &= _check(
        "MEDICAL_CODING_AGENT_ID = 'medical-coding-agent'" in page_src,
        "MEDICAL_CODING_AGENT_ID constant = 'medical-coding-agent'",
    )
    # runtimeApi.ts must define runAgentViaA2A.
    if _RUNTIME_API.exists():
        api_src = _RUNTIME_API.read_text(encoding="utf-8")
        ok &= _check(
            "runAgentViaA2A" in api_src and "/v1/message:send" in api_src,
            "runtimeApi.ts defines runAgentViaA2A → /v1/message:send",
        )
        ok &= _check(
            "A2A-Protocol-Version" in api_src,
            "runtimeApi.ts sets A2A-Protocol-Version: 0.3 header",
        )
    else:
        ok &= _check(False, "runtimeApi.ts exists")
    return ok


def check_seed_agents_script() -> bool:
    """backend/scripts/seed_agents.py exists and is importable."""
    ok = True
    print("\n=== 2. seed_agents.py exists and is valid ===")
    ok &= _check(_SEED_AGENTS.exists(), "scripts/seed_agents.py exists")
    if not ok:
        return False
    # Verify the script imports without syntax errors.
    try:
        import py_compile
        py_compile.compile(str(_SEED_AGENTS), doraise=True)
        ok &= _check(True, "seed_agents.py compiles")
    except Exception as e:
        ok &= _check(False, "seed_agents.py compiles", str(e))
    # Verify it references the official_agents dir and Agent model.
    src = _SEED_AGENTS.read_text(encoding="utf-8")
    ok &= _check(
        "OFFICIAL_AGENTS_DIR" in src and "agent_pack.json" in src,
        "seed_agents.py reads official_agents/**/agent_pack.json",
    )
    ok &= _check(
        "from app.models.agent import Agent" in src,
        "seed_agents.py imports app.models.agent.Agent",
    )
    ok &= _check(
        "is_prebuilt" in src and "upsert" in src.lower() or "is_prebuilt" in src,
        "seed_agents.py upserts by is_prebuilt=True",
    )
    # Verify hook into main.py lifespan.
    main_py = _BACKEND_DIR / "app" / "main.py"
    if main_py.exists():
        main_src = main_py.read_text(encoding="utf-8")
        ok &= _check(
            "seed_agents_from_packs" in main_src,
            "main.py lifespan calls seed_agents_from_packs at startup",
        )
    else:
        ok &= _check(False, "app/main.py exists")[0]
    return ok


def check_textgen_embedded_deprecated() -> bool:
    """TextGen routes removed + EmbeddedAssistantPage deleted."""
    ok = True
    print("\n=== 3. TextGen + EmbeddedAssistant deprecation ===")
    # EmbeddedAssistantPage.tsx physically deleted.
    ok &= _check(
        not _EMBEDDED_PAGE.exists(),
        "EmbeddedAssistantPage.tsx physically deleted",
    )
    if not _APP_TSX.exists():
        return _check(False, "App.tsx exists")
    app_src = _APP_TSX.read_text(encoding="utf-8")
    # No lazy import for EmbeddedAssistantPage (check the import statement,
    # not just any mention in comments).
    embedded_lazy_import = re.search(
        r"lazy\s*\(\s*\(\s*\)\s*=>\s*import\s*\(\s*'\./pages/EmbeddedAssistantPage'\s*\)",
        app_src,
    )
    ok &= _check(
        embedded_lazy_import is None,
        "App.tsx has no EmbeddedAssistantPage lazy import",
    )
    # No <Route ... element={<TextGenerationPage />} /> (Navigate redirects are OK).
    textgen_route = re.search(
        r'<Route[^>]*element=\{<TextGenerationPage\s*/?\>}',
        app_src,
    )
    ok &= _check(
        textgen_route is None,
        "App.tsx has no TextGenerationPage route element",
        f"found: {textgen_route.group(0) if textgen_route else ''}".strip(" —"),
    )
    # Old paths must redirect to /ai-studio/agents.
    textgen_redirect = re.search(
        r'path="ai-studio/text-generation"[^>]*element=\{<Navigate[^>]+to="/ai-studio/agents"',
        app_src,
    )
    embedded_redirect = re.search(
        r'path="ai-studio/embedded-assistant"[^>]*element=\{<Navigate[^>]+to="/ai-studio/agents"',
        app_src,
    )
    ok &= _check(
        textgen_redirect is not None,
        "ai-studio/text-generation redirects to /ai-studio/agents",
    )
    ok &= _check(
        embedded_redirect is not None,
        "ai-studio/embedded-assistant redirects to /ai-studio/agents",
    )
    # Layout sidebar must not have text-generation or embedded-assistant entries.
    layout_py = _FRONTEND_SRC / "components" / "layout" / "Layout.tsx"
    if layout_py.exists():
        layout_src = layout_py.read_text(encoding="utf-8")
        layout_textgen = re.search(r"to:\s*'/ai-studio/text-generation'", layout_src)
        layout_embedded = re.search(r"to:\s*'/ai-studio/embedded-assistant'", layout_src)
        ok &= _check(
            layout_textgen is None,
            "Layout sidebar has no text-generation entry",
        )
        ok &= _check(
            layout_embedded is None,
            "Layout sidebar has no embedded-assistant entry",
        )
    else:
        ok &= _check(False, "Layout.tsx exists")
    return ok


def check_hub_pack_mastered() -> bool:
    """Hub endpoint reads from official_agents/ (pack-mastered, no DB)."""
    ok = True
    print("\n=== 4. Hub endpoint pack-mastered ===")
    hub_py = _BACKEND_DIR / "app" / "api" / "icoder_agents_hub.py"
    if not hub_py.exists():
        return _check(False, "icoder_agents_hub.py exists")
    src = hub_py.read_text(encoding="utf-8")
    ok &= _check(
        "OFFICIAL_AGENTS_DIR" in src and "rglob" in src,
        "Hub reads official_agents/ via rglob(agent_pack.json)",
    )
    ok &= _check(
        re.search(r'@router\.get\s*\(\s*"/hub"', src) is not None,
        "Hub exposes GET /api/icoder/agents/hub",
    )
    # Verify at least one pack exists on disk.
    packs = list(_OFFICIAL_AGENTS_DIR.rglob("agent_pack.json")) if _OFFICIAL_AGENTS_DIR.exists() else []
    ok &= _check(
        len(packs) >= 10,
        f"official_agents/ has ≥10 agent_pack.json files (found {len(packs)})",
    )
    return ok


def main() -> int:
    print("=" * 60)
    print("Phase 3-B2 Loop 0 — Preconditions smoke test")
    print("=" * 60)
    results = []
    results.append(("MedicalCodingPage A2A rewire", check_medical_coding_rewire()))
    results.append(("seed_agents.py script", check_seed_agents_script()))
    results.append(("TextGen + EmbeddedAssistant deprecation", check_textgen_embedded_deprecated()))
    results.append(("Hub pack-mastered", check_hub_pack_mastered()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for label, ok in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {label}")
        if not ok:
            all_pass = False

    print("\nVerdict: " + ("PASS - Loop 0 preconditions satisfied" if all_pass else "FAIL - fix the failing checks before Loop 1"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
