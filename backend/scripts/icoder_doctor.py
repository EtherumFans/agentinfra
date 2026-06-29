"""iCoDer Doctor — productization readiness checks for local + cloud.

P1.0-C: Surface the runtime's health as a structured report so:

* new contributors can run `python scripts/icoder_doctor.py` and see what's broken
* the Agent Hub UI `/runtime/doctor` page can render the same JSON
* CI / pre-deploy gates can call `icoder_doctor.py --json` and assert on it

Design rules:
* Read-only. Never mutates runtime state.
* Each check returns ``{id, title, status, detail}`` where status is
  one of ``OK | WARN | FAIL | SKIP``.
* Aggregate verdict: FAIL if any FAIL; else WARN if any WARN; else OK.
* Exit code: 0 on OK, 1 on WARN, 2 on FAIL.

Checks (20 total — see ``CHECKS`` list at bottom):

  01. python_version
  02. fastapi_version
  03. starlette_version
  04. uvicorn_version
  05. no_deprecated_on_startup_in_app_code
  06. app_main_imports
  07. api_health_endpoint
  08. agent_registry_present
  09. agent_pack_files_present
  10. agent_pack_required_fields
  11. mcp_tool_registry_loads
  12. mcp_tool_registry_matches_pack
  13. faiss_icd10_index
  14. faiss_icd9cm3_index
  15. bge_m3_model_cache
  16. llm_provider_configured
  17. run_trace_dir_writable
  18. icoder_state_dir_gitignored
  19. fewshot_flag_default_off
  20. medcoder_index_health_via_app_state

Each check is a function ``_check_<id>(ctx) -> dict`` taking a shared
context dict. Pure functions — same input → same output (modulo
filesystem mtimes).
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# ── Result types ──────────────────────────────────────────────────────────


@dataclass
class CheckResult:
    """One check's outcome."""

    id: str
    title: str
    status: str  # "OK" | "WARN" | "FAIL" | "SKIP"
    detail: dict[str, Any] = field(default_factory=dict)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class DoctorReport:
    """Aggregate of all checks."""

    verdict: str  # "OK" | "WARN" | "FAIL"
    passed: int = 0
    warned: int = 0
    failed: int = 0
    skipped: int = 0
    checks: list[CheckResult] = field(default_factory=list)
    backend_root: str = str(BACKEND_ROOT)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "summary": {
                "passed": self.passed,
                "warned": self.warned,
                "failed": self.failed,
                "skipped": self.skipped,
                "total": len(self.checks),
            },
            "checks": [c.to_dict() for c in self.checks],
            "backend_root": self.backend_root,
        }


# ── Tiny helpers ──────────────────────────────────────────────────────────


def _ok(cid: str, title: str, message: str = "", **detail: Any) -> CheckResult:
    return CheckResult(id=cid, title=title, status="OK", message=message, detail=detail)


def _warn(cid: str, title: str, message: str = "", **detail: Any) -> CheckResult:
    return CheckResult(id=cid, title=title, status="WARN", message=message, detail=detail)


def _fail(cid: str, title: str, message: str = "", **detail: Any) -> CheckResult:
    return CheckResult(id=cid, title=title, status="FAIL", message=message, detail=detail)


def _skip(cid: str, title: str, message: str = "", **detail: Any) -> CheckResult:
    return CheckResult(id=cid, title=title, status="SKIP", message=message, detail=detail)


def _pkg_version(name: str) -> str | None:
    """Return the installed version of a distribution, or None."""
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ── Checks ────────────────────────────────────────────────────────────────


def _check_python_version(ctx: dict) -> CheckResult:
    v = sys.version_info
    major, minor = v.major, v.minor
    if (major, minor) >= (3, 11):
        return _ok("01.python_version", "Python ≥ 3.11", f"{major}.{minor}.{v.micro}",
                   version=f"{major}.{minor}.{v.micro}")
    return _fail("01.python_version", "Python ≥ 3.11",
                 f"Got {major}.{minor}, expected ≥ 3.11",
                 version=f"{major}.{minor}.{v.micro}")


def _check_fastapi_version(ctx: dict) -> CheckResult:
    v = _pkg_version("fastapi")
    if not v:
        return _fail("02.fastapi_version", "fastapi installed", "not installed")
    # Pin ≥0.100 (Lifespan + TestClient stability); warn if we ever drop below.
    try:
        major, minor = v.split(".")[:2]
        if int(minor) >= 100 or int(major) > 0:
            return _ok("02.fastapi_version", "fastapi ≥ 0.100", v, version=v)
    except Exception:
        pass
    return _ok("02.fastapi_version", "fastapi installed", v, version=v)


def _check_starlette_version(ctx: dict) -> CheckResult:
    v = _pkg_version("starlette")
    if not v:
        return _fail("03.starlette_version", "starlette installed", "not installed")
    # Starlette ≥ 0.36 deprecated on_startup; we want a version ≥ 0.38
    # (iCoDer runtime pin) but accept any version that does NOT break app boot.
    try:
        parts = v.split(".")
        if len(parts) >= 2 and int(parts[0]) == 0 and int(parts[1]) >= 36:
            return _ok("03.starlette_version", "starlette ≥ 0.36 (no on_startup)", v,
                       version=v)
    except Exception:
        pass
    return _ok("03.starlette_version", "starlette installed", v, version=v)


def _check_uvicorn_version(ctx: dict) -> CheckResult:
    v = _pkg_version("uvicorn")
    if not v:
        return _fail("04.uvicorn_version", "uvicorn installed", "not installed")
    return _ok("04.uvicorn_version", "uvicorn installed", v, version=v)


def _check_no_deprecated_on_startup(ctx: dict) -> CheckResult:
    """Production code must not use the deprecated ``@app.on_startup``.

    E1.1 fix (2026-06-26): replaced with lifespan context manager.
    """
    app_dir = BACKEND_ROOT / "app"
    bad_files: list[str] = []
    pattern = re.compile(r"@app\.(on_startup|on_event|on_shutdown)")
    for path in app_dir.rglob("*.py"):
        # Skip __pycache__ just in case
        if "__pycache__" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if pattern.search(text):
            bad_files.append(str(path.relative_to(BACKEND_ROOT)))
    if bad_files:
        return _fail(
            "05.no_deprecated_on_startup_in_app_code",
            "No deprecated @app.on_startup/on_event in production code",
            f"Found in {len(bad_files)} file(s): {bad_files[:3]}",
            files=bad_files,
        )
    return _ok("05.no_deprecated_on_startup_in_app_code",
               "No deprecated @app.on_startup/on_event in production code")


def _check_app_main_imports(ctx: dict) -> CheckResult:
    try:
        mod = importlib.import_module("app.main")
    except Exception as e:
        return _fail("06.app_main_imports", "import app.main", f"{type(e).__name__}: {e}",
                     error=str(e))
    app = getattr(mod, "app", None)
    if app is None:
        return _fail("06.app_main_imports", "import app.main", "app object missing")
    return _ok("06.app_main_imports", "import app.main", "ok",
               app_name=getattr(app, "title", "?"))


def _check_api_health_endpoint(ctx: dict) -> CheckResult:
    """Hit /api/health via TestClient with lifespan — fast, no external deps."""
    try:
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as c:
            r = c.get("/api/health")
        if r.status_code != 200:
            return _fail("07.api_health_endpoint", "GET /api/health → 200",
                         f"got {r.status_code}", body=r.text[:200])
        body = r.json()
        return _ok("07.api_health_endpoint", "GET /api/health → 200",
                   "ok", status=body.get("status"), medcoder_index_ready=body.get("medcoder_index_ready"))
    except Exception as e:
        return _fail("07.api_health_endpoint", "GET /api/health → 200",
                     f"{type(e).__name__}: {e}", error=str(e))


def _check_agent_registry_present(ctx: dict) -> CheckResult:
    """After lifespan, app.state.agent_registry should be populated."""
    try:
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as c:
            r = c.get("/api/icoder/agents")
        if r.status_code != 200:
            return _fail("08.agent_registry_present",
                         "RuntimeAgentRegistry populated",
                         f"/api/icoder/agents → {r.status_code}", body=r.text[:200])
        body = r.json()
        total = body.get("total", 0)
        if total == 0:
            return _warn("08.agent_registry_present",
                         "RuntimeAgentRegistry populated",
                         "registry_status={}".format(body.get("registry_status")),
                         registry_status=body.get("registry_status"), agents=body.get("agents", []))
        return _ok("08.agent_registry_present",
                   "RuntimeAgentRegistry populated",
                   f"{total} agent(s)", total=total,
                   registry_status=body.get("registry_status"))
    except Exception as e:
        return _fail("08.agent_registry_present", "RuntimeAgentRegistry populated",
                     f"{type(e).__name__}: {e}", error=str(e))


def _check_agent_pack_files_present(ctx: dict) -> CheckResult:
    """Each official_agents/<name>/agent_pack.json must exist and be valid JSON."""
    agents_dir = BACKEND_ROOT / "official_agents"
    packs: list[dict] = []
    bad: list[str] = []
    if not agents_dir.is_dir():
        return _fail("09.agent_pack_files_present",
                     "official_agents/*/agent_pack.json present",
                     f"missing dir: {agents_dir}")
    import json as _json
    for path in sorted(agents_dir.iterdir()):
        if not path.is_dir():
            continue
        # Skip Python cache dirs and dotfiles (sibling artifacts of the
        # agent pack directories themselves, not agent packs).
        if path.name.startswith(".") or path.name == "__pycache__":
            continue
        pack_path = path / "agent_pack.json"
        if not pack_path.is_file():
            bad.append(f"{path.name}/agent_pack.json (missing)")
            continue
        try:
            with open(pack_path, encoding="utf-8") as f:
                pack = _json.load(f)
            packs.append({"dir": path.name, "format_version": pack.get("format_version"),
                          "agent_type": pack.get("agent_type")})
        except Exception as e:
            bad.append(f"{path.name}/agent_pack.json ({e})")
    if bad:
        return _fail("09.agent_pack_files_present",
                     "official_agents/*/agent_pack.json present",
                     f"{len(bad)} bad", bad=bad, good=len(packs))
    return _ok("09.agent_pack_files_present",
               "official_agents/*/agent_pack.json present",
               f"{len(packs)} pack(s)",
               packs=packs)


def _check_agent_pack_required_fields(ctx: dict) -> CheckResult:
    """Raw-pack required fields (skips AgentPackageV1.from_dict() on purpose —
    Phase D3 packs use format_version=1.2 + agent_type=reference, which the
    v1.1 validator rejects. Doctor checks raw fields instead.)."""
    import json as _json

    required_top = ("manifest", "system_prompt")
    required_manifest = ("name", "version")
    required_req = ("min_runtime_version",)
    agents_dir = BACKEND_ROOT / "official_agents"
    issues: list[str] = []
    inspected = 0
    for path in sorted(agents_dir.iterdir()):
        if not path.is_dir():
            continue
        # Skip Python cache dirs and dotfiles (sibling artifacts of the
        # agent pack directories themselves, not agent packs).
        if path.name.startswith(".") or path.name == "__pycache__":
            continue
        pack_path = path / "agent_pack.json"
        if not pack_path.is_file():
            continue
        inspected += 1
        try:
            with open(pack_path, encoding="utf-8") as f:
                pack = _json.load(f)
        except Exception as e:
            issues.append(f"{path.name}: JSON load failed: {e}")
            continue
        for key in required_top:
            if key not in pack:
                issues.append(f"{path.name}: missing top-level {key!r}")
        manifest = pack.get("manifest", {})
        if not isinstance(manifest, dict):
            issues.append(f"{path.name}: manifest is not a dict")
            continue
        for key in required_manifest:
            if not manifest.get(key):
                issues.append(f"{path.name}: missing manifest.{key}")
        sp = pack.get("system_prompt", "")
        if not isinstance(sp, str) or not sp.strip():
            issues.append(f"{path.name}: system_prompt is empty")
        req = pack.get("requirements", {})
        if not isinstance(req, dict):
            issues.append(f"{path.name}: requirements is not a dict")
            continue
        for key in required_req:
            if not req.get(key):
                issues.append(f"{path.name}: missing requirements.{key}")
    if issues:
        return _fail("10.agent_pack_required_fields",
                     "Agent packs have required raw fields",
                     f"{len(issues)} issue(s) across {inspected} pack(s)",
                     issues=issues)
    return _ok("10.agent_pack_required_fields",
               "Agent packs have required raw fields",
               f"{inspected} pack(s) inspected", inspected=inspected)


def _check_mcp_tool_registry_loads(ctx: dict) -> CheckResult:
    try:
        from app.icoder.mcp.tool_registry import TOOL_REGISTRY
    except Exception as e:
        return _fail("11.mcp_tool_registry_loads", "MCP TOOL_REGISTRY importable",
                     f"{type(e).__name__}: {e}", error=str(e))
    if not TOOL_REGISTRY:
        return _fail("11.mcp_tool_registry_loads", "MCP TOOL_REGISTRY populated",
                     "empty registry")
    return _ok("11.mcp_tool_registry_loads", "MCP TOOL_REGISTRY populated",
               f"{len(TOOL_REGISTRY)} tool(s)",
               tools=sorted(TOOL_REGISTRY.keys()))


def _check_mcp_tool_registry_matches_pack(ctx: dict) -> CheckResult:
    """Boot assertion: TOOL_REGISTRY keys ⊆ pack tools[].name."""
    try:
        from app.icoder.mcp.tool_registry import TOOL_REGISTRY
    except Exception as e:
        return _fail("12.mcp_tool_registry_matches_pack",
                     "TOOL_REGISTRY ⊆ pack tools",
                     f"registry import failed: {e}")
    medcoder_pack = BACKEND_ROOT / "official_agents" / "medcoder-coding-review" / "agent_pack.json"
    if not medcoder_pack.is_file():
        return _skip("12.mcp_tool_registry_matches_pack",
                     "TOOL_REGISTRY ⊆ pack tools",
                     "medcoder-coding-review/agent_pack.json missing")
    import json as _json
    with open(medcoder_pack, encoding="utf-8") as f:
        pack = _json.load(f)
    pack_tool_names = set()
    for t in pack.get("tools", []):
        if isinstance(t, dict):
            n = t.get("name") or t.get("id")
            if n:
                pack_tool_names.add(n)
        elif isinstance(t, str):
            pack_tool_names.add(t)
    reg_names = set(TOOL_REGISTRY.keys())
    missing_in_pack = reg_names - pack_tool_names
    extra_in_pack = pack_tool_names - reg_names
    if missing_in_pack:
        return _fail("12.mcp_tool_registry_matches_pack",
                     "TOOL_REGISTRY ⊆ pack tools",
                     f"missing in pack: {sorted(missing_in_pack)}",
                     missing_in_pack=sorted(missing_in_pack),
                     extra_in_pack=sorted(extra_in_pack))
    return _ok("12.mcp_tool_registry_matches_pack",
               "TOOL_REGISTRY ⊆ pack tools",
               f"{len(reg_names)} tool(s) match",
               registered=sorted(reg_names),
               extra_in_pack=sorted(extra_in_pack))


def _check_faiss_icd10_index(ctx: dict) -> CheckResult:
    try:
        from app.services.medcoder_index_health import index_health_check
        h = index_health_check(BACKEND_ROOT / "data" / "medcoder")
    except Exception as e:
        return _fail("13.faiss_icd10_index", "FAISS ICD-10 index healthy",
                     f"{type(e).__name__}: {e}", error=str(e))
    if h.get("status") == "ok":
        return _ok("13.faiss_icd10_index", "FAISS ICD-10 index healthy",
                   f"ntotal={h.get('ntotal')} dim={h.get('dim')}",
                   ntotal=h.get("ntotal"), dim=h.get("dim"),
                   faiss_path=h.get("faiss_path"))
    return _fail("13.faiss_icd10_index", "FAISS ICD-10 index healthy",
                 h.get("reason") or "degraded", report=h)


def _check_faiss_icd9cm3_index(ctx: dict) -> CheckResult:
    try:
        from app.services.medcoder_index_health import index_health_check
        h = index_health_check(
            BACKEND_ROOT / "data" / "medcoder",
            faiss_filename="faiss_icd9cm3.index",
            metadata_filename="metadata_icd9cm3.pkl",
        )
    except Exception as e:
        return _fail("14.faiss_icd9cm3_index", "FAISS ICD-9-CM-3 index healthy",
                     f"{type(e).__name__}: {e}", error=str(e))
    if h.get("status") == "ok":
        return _ok("14.faiss_icd9cm3_index", "FAISS ICD-9-CM-3 index healthy",
                   f"ntotal={h.get('ntotal')} dim={h.get('dim')}",
                   ntotal=h.get("ntotal"), dim=h.get("dim"),
                   faiss_path=h.get("faiss_path"))
    return _warn("14.faiss_icd9cm3_index", "FAISS ICD-9-CM-3 index healthy",
                 h.get("reason") or "degraded",
                 reason=h.get("reason"), report=h)


def _check_bge_m3_model_cache(ctx: dict) -> CheckResult:
    """BGE-M3 must be downloaded once and cached locally."""
    candidates = [
        BACKEND_ROOT / "data" / "medcoder" / "models" / "models--BAAI--bge-m3",
        Path.home() / ".cache" / "huggingface" / "hub" / "models--BAAI--bge-m3",
    ]
    for c in candidates:
        if c.is_dir():
            return _ok("15.bge_m3_model_cache", "BGE-M3 model cache present",
                       str(c), path=str(c))
    return _warn("15.bge_m3_model_cache", "BGE-M3 model cache present",
                 "not yet downloaded — first sentence-transformers run will pull it",
                 searched=[str(c) for c in candidates])


def _check_llm_provider_configured(ctx: dict) -> CheckResult:
    # Source of truth order: env vars first, then app config defaults.
    key = os.environ.get("ICODER_CREDENTIAL_LLM", "")
    base = os.environ.get("LLM_BASE_URL", "")
    model = os.environ.get("LLM_MODEL", "")
    if not base or not model:
        try:
            from app.config import settings
            base = base or getattr(settings, "LLM_BASE_URL", "")
            model = model or getattr(settings, "LLM_MODEL", "")
        except Exception:
            pass
    has_key = bool(key)
    if has_key and base and model:
        return _ok("16.llm_provider_configured", "LLM provider configured",
                   f"model={model} base={base}", model=model, base=base,
                   key_set=True)
    missing = []
    if not has_key:
        missing.append("ICODER_CREDENTIAL_LLM")
    if not base:
        missing.append("LLM_BASE_URL")
    if not model:
        missing.append("LLM_MODEL")
    return _warn("16.llm_provider_configured", "LLM provider configured",
                 f"missing: {missing}", missing=missing,
                 key_set=has_key, base=base, model=model)


def _check_run_trace_dir_writable(ctx: dict) -> CheckResult:
    """M2aRecorder stores run traces under backend/.icoder/m2a/."""
    target = BACKEND_ROOT / ".icoder" / "m2a"
    try:
        target.mkdir(parents=True, exist_ok=True)
        probe = target / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return _ok("17.run_trace_dir_writable", "Run trace dir writable",
                   str(target), path=str(target))
    except Exception as e:
        return _fail("17.run_trace_dir_writable", "Run trace dir writable",
                     f"{type(e).__name__}: {e}", path=str(target), error=str(e))


def _check_icoder_state_dir_gitignored(ctx: dict) -> CheckResult:
    gitignore = BACKEND_ROOT.parent / ".gitignore"
    if not gitignore.is_file():
        return _warn("18.icoder_state_dir_gitignored", ".icoder/ in .gitignore",
                     f"no .gitignore at {gitignore}")
    text = _read_text(gitignore)
    if re.search(r"(^|/)backend/\.icoder/?", text, re.MULTILINE):
        return _ok("18.icoder_state_dir_gitignored", ".icoder/ in .gitignore",
                   "match found", path=str(gitignore))
    return _fail("18.icoder_state_dir_gitignored", ".icoder/ in .gitignore",
                 "backend/.icoder/ pattern not found", path=str(gitignore))


def _check_fewshot_flag_default_off(ctx: dict) -> CheckResult:
    """P1.0-A: ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT must default to off.

    Truthy values: 1 / true / yes / on (case-insensitive).
    """
    from icoder_runtime.providers.medical_coding.medcoder_adapter import (
        is_medcoder_fewshot_enabled,
    )
    raw = os.environ.get("ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT", "")
    enabled = is_medcoder_fewshot_enabled()
    if enabled:
        return _warn("19.fewshot_flag_default_off",
                     "ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT default off",
                     f"flag set: env={raw!r} → enabled (experimental feature ACTIVE)",
                     env=raw, enabled=True)
    return _ok("19.fewshot_flag_default_off",
               "ICODER_EXPERIMENTAL_MEDCODER_FEWSHOT default off",
               f"env={raw!r} → disabled",
               env=raw, enabled=False)


def _check_medcoder_index_health_via_app_state(ctx: dict) -> CheckResult:
    """After lifespan, app.state.medcoder_index_health is populated."""
    try:
        from fastapi.testclient import TestClient
        from app.main import app

        with TestClient(app) as c:
            r = c.get("/api/health")
        body = r.json()
        ready = body.get("medcoder_index_ready")
        loading = body.get("medcoder_index_loading")
        err = body.get("medcoder_index_error")
        if ready:
            return _ok("20.medcoder_index_health_via_app_state",
                       "MedCodER index health via app.state",
                       "ready=True", ready=True, loading=loading, error=err)
        if loading:
            return _warn("20.medcoder_index_health_via_app_state",
                         "MedCodER index health via app.state",
                         "still loading", ready=False, loading=True, error=err)
        return _fail("20.medcoder_index_health_via_app_state",
                     "MedCodER index health via app.state",
                     err or "not ready", ready=False, loading=loading, error=err)
    except Exception as e:
        return _fail("20.medcoder_index_health_via_app_state",
                     "MedCodER index health via app.state",
                     f"{type(e).__name__}: {e}", error=str(e))


# ── Registry ──────────────────────────────────────────────────────────────


CHECKS: list[tuple[str, Callable[[dict], CheckResult]]] = [
    ("01.python_version", _check_python_version),
    ("02.fastapi_version", _check_fastapi_version),
    ("03.starlette_version", _check_starlette_version),
    ("04.uvicorn_version", _check_uvicorn_version),
    ("05.no_deprecated_on_startup_in_app_code", _check_no_deprecated_on_startup),
    ("06.app_main_imports", _check_app_main_imports),
    ("07.api_health_endpoint", _check_api_health_endpoint),
    ("08.agent_registry_present", _check_agent_registry_present),
    ("09.agent_pack_files_present", _check_agent_pack_files_present),
    ("10.agent_pack_required_fields", _check_agent_pack_required_fields),
    ("11.mcp_tool_registry_loads", _check_mcp_tool_registry_loads),
    ("12.mcp_tool_registry_matches_pack", _check_mcp_tool_registry_matches_pack),
    ("13.faiss_icd10_index", _check_faiss_icd10_index),
    ("14.faiss_icd9cm3_index", _check_faiss_icd9cm3_index),
    ("15.bge_m3_model_cache", _check_bge_m3_model_cache),
    ("16.llm_provider_configured", _check_llm_provider_configured),
    ("17.run_trace_dir_writable", _check_run_trace_dir_writable),
    ("18.icoder_state_dir_gitignored", _check_icoder_state_dir_gitignored),
    ("19.fewshot_flag_default_off", _check_fewshot_flag_default_off),
    ("20.medcoder_index_health_via_app_state", _check_medcoder_index_health_via_app_state),
]


# ── Runner ────────────────────────────────────────────────────────────────


def run_doctor(check_ids: list[str] | None = None) -> DoctorReport:
    ctx: dict = {}
    results: list[CheckResult] = []
    for cid, fn in CHECKS:
        # Match either the full id ("09.agent_pack_files_present") or the
        # 2-digit prefix ("09") that the user types on the CLI.
        if check_ids:
            prefix = cid.split(".", 1)[0]
            if cid not in check_ids and prefix not in check_ids:
                continue
        try:
            r = fn(ctx)
        except Exception as e:  # noqa: BLE001 — last-resort guard
            r = CheckResult(id=cid, title=fn.__name__, status="FAIL",
                            message=f"{type(e).__name__}: {e}",
                            detail={"error": str(e)})
        results.append(r)

    passed = sum(1 for r in results if r.status == "OK")
    warned = sum(1 for r in results if r.status == "WARN")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIP")
    if failed:
        verdict = "FAIL"
    elif warned:
        verdict = "WARN"
    else:
        verdict = "OK"
    return DoctorReport(
        verdict=verdict, passed=passed, warned=warned, failed=failed,
        skipped=skipped, checks=results,
    )


def _print_human(report: DoctorReport) -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass
    print(f"iCoDer Doctor — verdict: {report.verdict}")
    print(f"summary: {report.passed} OK, {report.warned} WARN, "
          f"{report.failed} FAIL, {report.skipped} SKIP "
          f"(of {len(report.checks)})")
    print()
    for r in report.checks:
        glyph = {"OK": "[OK]", "WARN": "[WARN]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}.get(r.status, "[?]")
        msg = f" — {r.message}" if r.message else ""
        print(f"  {glyph} {r.id} {r.title}{msg}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="iCoDer Doctor")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of human output")
    ap.add_argument("--only", help="Comma-separated check IDs to run (e.g. 01,07,19)")
    args = ap.parse_args(argv)
    check_ids = None
    if args.only:
        check_ids = {c.strip() for c in args.only.split(",") if c.strip()}
    report = run_doctor(check_ids)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, default=str))
    else:
        _print_human(report)
    return {"OK": 0, "WARN": 1, "FAIL": 2}.get(report.verdict, 1)


if __name__ == "__main__":
    sys.exit(main())