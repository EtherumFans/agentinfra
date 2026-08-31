"""Agent Pack Loader (P1.1) — unified loader for v1.1 and v1.2 packs.

The loader always returns a :class:`NormalizedPack`. Validation errors are
recorded on the pack (``validation_errors``) and the pack's ``status`` is
set to one of:

* :attr:`PackStatus.EXECUTABLE` — fully wired, can be dispatched
* :attr:`PackStatus.METADATA_ONLY` — on disk but lacks executors (e.g.
  ``expert-stub`` v1.2 packs awaiting Phase D implementation)
* :attr:`PackStatus.INVALID` — validation failed; surfaced but never
  dispatched by the runtime

This is the single point of truth for "is this pack loadable?" for both
Agent Hub discovery and the runtime registry. Both consumers should
call :func:`load_pack` (or :func:`load_packs_from_dir`) and never reach
into ``pack_data`` directly.

The pre-existing :class:`AgentPackageV1` validator is preserved
unchanged for legacy callers; it remains the gate for ``v1.1`` packs.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Iterable

from icoder_runtime.backends.output_contract_validation import (
    SUPPORTED_FIELD_TYPES,
    declared_field_schemas,
    declared_optional_fields,
    declared_field_types,
    validate_declared_field_schemas,
    validate_cross_agent_relations_definition,
    validate_evidence_bindings_definition,
    validate_field_relations_definition,
    validate_field_schema_definition,
    validate_required_field_types,
)

from .agent_pack_schema import (
    LEGAL_AGENT_TYPES,
    SUPPORTED_FORMAT_VERSIONS,
    NormalizedExpert,
    NormalizedPack,
    NormalizedTool,
    PackStatus,
)

logger = logging.getLogger(__name__)


# ── Public entry points ──


def load_pack(
    pack: dict[str, Any],
    *,
    source_path: str | None = None,
) -> NormalizedPack:
    """Normalize any agent pack dict (v1.1 or v1.2) into a NormalizedPack.

    Never raises on validation errors — sets ``status=INVALID`` and records
    the errors. Raises only on truly malformed input (non-dict).
    """
    if not isinstance(pack, dict):
        raise TypeError(f"agent pack must be a dict, got {type(pack).__name__}")

    normalized = NormalizedPack(
        raw=pack,
        source_path=source_path,
        agent_ref=str(pack.get("agent_ref", "")),
        format_version=str(pack.get("format_version", "")),
        agent_type=str(pack.get("agent_type", "")),
        name="",
        version="",
    )

    _populate_manifest(normalized)
    _populate_identity(normalized)
    _populate_system_prompt(normalized)
    _populate_experts(normalized)
    _populate_tools(normalized)
    _populate_runtime_metadata(normalized)
    _populate_v12_extensions(normalized)
    _populate_v13_extensions(normalized)

    _classify(normalized)
    _assess_launch_candidate(normalized)
    return normalized


def load_packs_from_dir(
    agents_dir: str | Path,
) -> list[NormalizedPack]:
    """Discover + load every ``<dir>/<name>/agent_pack.json`` under *agents_dir*.

    Skips ``__pycache__`` and hidden directories. Records a load error on
    any file that fails to parse rather than raising.
    """
    base = Path(agents_dir)
    packs: list[NormalizedPack] = []
    if not base.exists() or not base.is_dir():
        return packs

    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name == "__pycache__":
            continue
        pack_file = child / "agent_pack.json"
        if not pack_file.exists():
            continue
        try:
            raw = json.loads(pack_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(f"[agent_pack_loader] failed to parse {pack_file}: {e}")
            errored = NormalizedPack(
                raw={},
                source_path=str(pack_file),
                agent_ref=child.name,
                format_version="",
                agent_type="",
                name=child.name,
                version="",
            )
            errored.validation_errors.append(f"Failed to parse JSON: {e}")
            errored.status = PackStatus.INVALID
            packs.append(errored)
            continue
        normalized = load_pack(raw, source_path=str(pack_file))
        packs.append(normalized)
    return packs


def discover_v1_files(
    agents_dir: str | Path,
) -> dict[str, list[Path]]:
    """Return ``{pack_name: [pack_file_path, ...]}`` for downstream tests."""
    base = Path(agents_dir)
    out: dict[str, list[Path]] = {}
    if not base.exists() or not base.is_dir():
        return out
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        if child.name.startswith(".") or child.name == "__pycache__":
            continue
        pf = child / "agent_pack.json"
        if pf.exists():
            out.setdefault(child.name, []).append(pf)
    return out


# ── Population helpers ──


def _populate_manifest(p: NormalizedPack) -> None:
    manifest = p.raw.get("manifest") or {}
    if not isinstance(manifest, dict):
        p.validation_errors.append("manifest must be a dict")
        manifest = {}
    p.name = str(manifest.get("name", ""))
    p.version = str(manifest.get("version", ""))
    p.description = str(manifest.get("description", ""))
    p.category = str(manifest.get("category", "general"))
    p.icon = str(manifest.get("icon", "Bot"))
    tags = manifest.get("tags") or []
    if isinstance(tags, list):
        p.tags = [str(t) for t in tags]

    if not p.name:
        p.validation_errors.append("manifest.name is required")
    if not p.version:
        p.validation_errors.append("manifest.version is required")


def _populate_identity(p: NormalizedPack) -> None:
    if p.format_version not in SUPPORTED_FORMAT_VERSIONS:
        p.validation_errors.append(
            f"Unsupported format_version: {p.format_version!r}. "
            f"Expected one of {SUPPORTED_FORMAT_VERSIONS}."
        )
    if p.agent_type not in LEGAL_AGENT_TYPES:
        p.validation_errors.append(
            f"agent_type {p.agent_type!r} is not one of {LEGAL_AGENT_TYPES}"
        )

    # agent_ref fallback: derive from manifest if missing
    if not p.agent_ref:
        if p.name and p.version:
            slug = _slugify(p.name)
            p.agent_ref = f"icoder/{slug}@{p.version}"
            p.validation_warnings.append(
                f"agent_ref missing — derived from manifest: {p.agent_ref!r}"
            )
        else:
            p.validation_errors.append("agent_ref is required when manifest.name/version missing")


def _populate_system_prompt(p: NormalizedPack) -> None:
    sp = p.raw.get("system_prompt", "")
    if not sp or not isinstance(sp, str):
        # Phase A1D.5 — metadata-only packs are explicit catalog stubs
        # (manifest.maturity == "metadata-only"). They exist for marketplace
        # presence / future road-map signaling, not for execution. Skip
        # the runnability requirement so the loader can mark them
        # METADATA_ONLY in _classify instead of INVALID.
        if _is_metadata_only_maturity(p):
            p.validation_warnings.append(
                "system_prompt empty — allowed for manifest.maturity=metadata-only "
                "(pack is METADATA_ONLY, not runnable)"
            )
            p.system_prompt = ""
            return
        p.validation_errors.append("system_prompt is required and must be a non-empty string")
        return
    p.system_prompt = sp


def _is_metadata_only_maturity(p: NormalizedPack) -> bool:
    """Phase A1D.5 — True when the pack explicitly declares itself a stub.

    A metadata-only pack is an intentional catalog placeholder: it ships
    a manifest and (optionally) experts/tools skeleton, but no
    runnable system_prompt. The loader classifies these as
    METADATA_ONLY (visible in registry, not enabled) instead of INVALID.

    Detection (either is sufficient):
      - ``manifest.maturity == "metadata-only"``
      - ``"metadata-only" in manifest.tags``
    """
    manifest = p.raw.get("manifest") or {}
    if not isinstance(manifest, dict):
        return False
    if manifest.get("maturity") == "metadata-only":
        return True
    tags = manifest.get("tags") or []
    if isinstance(tags, list) and "metadata-only" in tags:
        return True
    return False


def _populate_experts(p: NormalizedPack) -> None:
    raw_experts = p.raw.get("experts") or []
    if not isinstance(raw_experts, list):
        p.validation_errors.append("experts must be a list")
        return
    for i, e in enumerate(raw_experts):
        if not isinstance(e, dict):
            p.validation_errors.append(f"experts[{i}]: must be a dict")
            continue
        exp = NormalizedExpert(
            raw=e,
            id=str(e.get("id") or e.get("expert_id", "")),
            name=str(e.get("name", "")),
            role=str(e.get("role", "")),
            description=str(e.get("description", "")),
            system_prompt=str(e.get("system_prompt", "")),
            tools=[str(t) for t in (e.get("tools") or []) if isinstance(t, str)],
            model=str(e.get("model", "")),
            non_goals=[str(x) for x in (e.get("non_goals") or []) if isinstance(x, str)],
            output_contract=e.get("output_contract") if isinstance(e.get("output_contract"), dict) else None,
            timeout_ms=int(e["timeout_ms"]) if isinstance(e.get("timeout_ms"), (int, float)) else None,
        )
        if not exp.id:
            p.validation_errors.append(f"experts[{i}]: id is required")
        if not exp.name:
            p.validation_errors.append(f"experts[{i}]: name is required")
        p.experts.append(exp)


def _populate_tools(p: NormalizedPack) -> None:
    raw_tools = p.raw.get("tools") or []
    if not isinstance(raw_tools, list):
        p.validation_errors.append("tools must be a list")
        return
    for i, t in enumerate(raw_tools):
        tool = _normalize_tool(i, t, p)
        p.tools.append(tool)


def _normalize_tool(index: int, t: Any, p: NormalizedPack) -> NormalizedTool:
    """Return a NormalizedTool for one raw entry; collect issues on *p*."""
    if isinstance(t, str):
        # Legacy: just an ID with no shape.
        if not t:
            p.validation_errors.append(f"tools[{index}]: empty string id")
        return NormalizedTool(
            raw={"id": t},
            id=t,
            name=t,
            kind="legacy",
        )

    if not isinstance(t, dict):
        p.validation_errors.append(f"tools[{index}]: must be dict or str")
        return NormalizedTool(raw={"_bad": True}, id=f"_bad_{index}", name=f"_bad_{index}", kind="invalid")

    # v1.1 has tier/executor_file; v1.2 has type/ref/stage.
    has_v11 = "tier" in t or "executor_file" in t
    has_v12 = "ref" in t or "type" in t

    name = str(t.get("name") or t.get("id") or "")
    if not name:
        p.validation_errors.append(f"tools[{index}]: name (or id) is required")

    kind = "v1_1" if has_v11 and not has_v12 else "v1_2"
    if has_v12:
        type_str = str(t.get("type", "")).lower()
        if type_str == "guard":
            kind = "v1_2_guard"
        elif type_str == "mcp":
            kind = "v1_2_mcp"
        elif type_str in ("function", "builtin"):
            kind = "v1_2_function"

    return NormalizedTool(
        raw=t,
        id=name,
        name=name,
        kind=kind,
        ref=str(t.get("ref", "")) or None,
        stage=str(t.get("stage", "")) or None,
        tier=int(t["tier"]) if isinstance(t.get("tier"), (int, float)) else None,
        executor_file=str(t.get("executor_file", "")) or None,
        description=str(t.get("description", "")),
        input_schema=t.get("input_schema") if isinstance(t.get("input_schema"), dict) else None,
        output_schema=t.get("output_schema") if isinstance(t.get("output_schema"), dict) else None,
    )


def _populate_runtime_metadata(p: NormalizedPack) -> None:
    for src_field, dst_field in (
        ("model", "model"),
        ("pipeline", "pipeline"),
        ("permissions", "permissions"),
        ("requirements", "requirements"),
        ("llm_capabilities", "llm_capabilities"),
        ("integrity", "integrity"),
    ):
        value = p.raw.get(src_field, {})
        if isinstance(value, dict):
            setattr(p, dst_field, value)
        elif value in (None, ""):
            setattr(p, dst_field, {})
        else:
            p.validation_warnings.append(f"{src_field}: expected dict, got {type(value).__name__}")

    # Code files (only legal in community or expert-stub v1.2 packs)
    code = p.raw.get("code") or {}
    if isinstance(code, dict):
        p.code = {k: str(v) for k, v in code.items()}
    elif code:
        p.validation_warnings.append("code: expected dict, got other")

    if p.agent_type == "certified" and p.code:
        p.validation_errors.append("certified agents cannot contain code/")

    if not p.requirements.get("min_runtime_version"):
        p.validation_errors.append("requirements.min_runtime_version is required")


def _populate_v12_extensions(p: NormalizedPack) -> None:
    non_goals = p.raw.get("non_goals") or []
    if isinstance(non_goals, list):
        p.non_goals = [str(x) for x in non_goals]
    elif non_goals:
        p.validation_warnings.append("non_goals: expected list")

    oc = p.raw.get("output_contract") or {}
    if isinstance(oc, dict):
        p.output_contract = oc

    phi = p.raw.get("phi_redaction")
    if isinstance(phi, str) and phi in ("required", "optional", "blocked"):
        p.phi_redaction = phi

    for flag in ("context_required", "recorder_required", "metrics_required"):
        v = p.raw.get(flag)
        if isinstance(v, bool):
            setattr(p, flag, v)

    hrw = p.raw.get("human_review_required_when") or []
    if isinstance(hrw, list):
        p.human_review_required_when = [str(x) for x in hrw]

    a2a = p.raw.get("a2a") or {}
    if isinstance(a2a, dict):
        p.a2a = a2a

    _populate_backend_provider(p)


def _populate_backend_provider(p: NormalizedPack) -> None:
    """Phase 4-A: extract ``backend_provider`` + ``backend_config``.

    Accepts both top-level and ``agent``-nested placement so pack
    authors can write either:

      ``{"backend_provider": "icoder.rule-engine.v1", ...}`` (top-level)
      ``{"agent": {"backend_provider": "icoder.rule-engine.v1", ...}, ...}``

    If neither is present, ``backend_provider`` stays empty and the
    runtime falls back to ``DEFAULT_FALLBACK_PROVIDER_ID`` (preserves
    backward compat with the 16 existing official agent packs).
    """
    raw = p.raw or {}
    if not isinstance(raw, dict):
        return

    # Top-level
    bp = raw.get("backend_provider")
    if isinstance(bp, str) and bp:
        p.backend_provider = bp
    elif bp is not None and not isinstance(bp, str):
        p.validation_warnings.append(
            f"backend_provider: expected string, got {type(bp).__name__}"
        )

    bc = raw.get("backend_config")
    if isinstance(bc, dict):
        p.backend_config = bc
    elif bc is not None and not isinstance(bc, dict):
        p.validation_warnings.append(
            f"backend_config: expected dict, got {type(bc).__name__}"
        )

    # Nested under ``agent`` (alternative placement)
    agent_node = raw.get("agent")
    if isinstance(agent_node, dict):
        if not p.backend_provider:
            nested_bp = agent_node.get("backend_provider")
            if isinstance(nested_bp, str) and nested_bp:
                p.backend_provider = nested_bp
            elif nested_bp is not None and not isinstance(nested_bp, str):
                p.validation_warnings.append(
                    "agent.backend_provider: expected string, "
                    f"got {type(nested_bp).__name__}"
                )
        if not p.backend_config:
            nested_bc = agent_node.get("backend_config")
            if isinstance(nested_bc, dict):
                p.backend_config = nested_bc
            elif nested_bc is not None and not isinstance(nested_bc, dict):
                p.validation_warnings.append(
                    "agent.backend_config: expected dict, "
                    f"got {type(nested_bc).__name__}"
                )

    # Validate tool-scope config if present (mandatory ⊆ scope, forbidden ∩ scope = ∅).
    if p.backend_config:
        tools_cfg = p.backend_config.get("tools")
        if isinstance(tools_cfg, dict):
            scope = tools_cfg.get("scope")
            mandatory = tools_cfg.get("mandatory")
            conditional_mandatory = tools_cfg.get("conditional_mandatory")
            forbidden = tools_cfg.get("forbidden")
            if scope is not None and not isinstance(scope, list):
                p.validation_errors.append(
                    "backend_config.tools.scope: expected list"
                )
            if mandatory is not None and not isinstance(mandatory, list):
                p.validation_errors.append(
                    "backend_config.tools.mandatory: expected list"
                )
            if forbidden is not None and not isinstance(forbidden, list):
                p.validation_errors.append(
                    "backend_config.tools.forbidden: expected list"
                )
            if conditional_mandatory is not None and not isinstance(
                conditional_mandatory, list
            ):
                p.validation_errors.append(
                    "backend_config.tools.conditional_mandatory: expected list"
                )
            if isinstance(scope, list) and isinstance(conditional_mandatory, list):
                conditional_tools = {
                    str(tool)
                    for policy in conditional_mandatory
                    if isinstance(policy, dict)
                    for tool in (policy.get("tools") or [])
                }
                if not conditional_tools.issubset(set(scope)):
                    p.validation_errors.append(
                        "backend_config.tools: conditional mandatory tools must be subset of scope"
                    )
            if (
                isinstance(scope, list)
                and isinstance(mandatory, list)
                and not set(mandatory).issubset(set(scope))
            ):
                p.validation_errors.append(
                    "backend_config.tools: mandatory must be subset of scope"
                )
            if (
                isinstance(scope, list)
                and isinstance(forbidden, list)
                and set(forbidden).intersection(set(scope))
            ):
                p.validation_errors.append(
                    "backend_config.tools: forbidden must not intersect scope"
                )


def _populate_v13_extensions(p: NormalizedPack) -> None:
    """Phase 4-F (2026-07-09): extract prebuilt-agent spec fields.

    Reads ``default_runtime_mode``, ``available_runtime_modes``,
    ``example_inputs``, ``example_outputs``, ``built_by`` from the raw
    pack (top-level or ``agent``-nested). These fields drive the Agents
    list card badges + the Agent Detail Settings panel + the "Try" demo
    button. Empty defaults are fine — legacy v1.1/v1.2 packs that
    haven't been upgraded simply show blank fields in the UI.
    """
    raw = p.raw or {}
    if not isinstance(raw, dict):
        return

    # Top-level extraction
    drm = raw.get("default_runtime_mode")
    if isinstance(drm, str) and drm:
        p.default_runtime_mode = drm
    elif drm is not None and not isinstance(drm, str):
        p.validation_warnings.append(
            f"default_runtime_mode: expected string, got {type(drm).__name__}"
        )

    arm = raw.get("available_runtime_modes")
    if isinstance(arm, list):
        p.available_runtime_modes = [str(x) for x in arm if isinstance(x, str)]
    elif arm is not None and not isinstance(arm, list):
        p.validation_warnings.append(
            f"available_runtime_modes: expected list, got {type(arm).__name__}"
        )

    ei = raw.get("example_inputs")
    if isinstance(ei, list):
        p.example_inputs = [x for x in ei if isinstance(x, dict)]
    elif ei is not None and not isinstance(ei, list):
        p.validation_warnings.append(
            f"example_inputs: expected list, got {type(ei).__name__}"
        )

    eo = raw.get("example_outputs")
    if isinstance(eo, list):
        p.example_outputs = [x for x in eo if isinstance(x, dict)]
    elif eo is not None and not isinstance(eo, list):
        p.validation_warnings.append(
            f"example_outputs: expected list, got {type(eo).__name__}"
        )

    bb = raw.get("built_by")
    if isinstance(bb, str) and bb:
        p.built_by = bb
    elif bb is not None and not isinstance(bb, str):
        p.validation_warnings.append(
            f"built_by: expected string, got {type(bb).__name__}"
        )

    # Nested under ``agent`` (alternative placement) — only fill if not
    # already set at top level, matching _populate_backend_provider's
    # precedence rule.
    agent_node = raw.get("agent")
    if isinstance(agent_node, dict):
        if not p.default_runtime_mode:
            nested_drm = agent_node.get("default_runtime_mode")
            if isinstance(nested_drm, str) and nested_drm:
                p.default_runtime_mode = nested_drm
        if not p.available_runtime_modes:
            nested_arm = agent_node.get("available_runtime_modes")
            if isinstance(nested_arm, list):
                p.available_runtime_modes = [
                    str(x) for x in nested_arm if isinstance(x, str)
                ]
        if not p.example_inputs:
            nested_ei = agent_node.get("example_inputs")
            if isinstance(nested_ei, list):
                p.example_inputs = [x for x in nested_ei if isinstance(x, dict)]
        if not p.example_outputs:
            nested_eo = agent_node.get("example_outputs")
            if isinstance(nested_eo, list):
                p.example_outputs = [x for x in nested_eo if isinstance(x, dict)]
        if not p.built_by:
            nested_bb = agent_node.get("built_by")
            if isinstance(nested_bb, str) and nested_bb:
                p.built_by = nested_bb


# ── Classification ──


def _classify(p: NormalizedPack) -> None:
    """Decide status / production_ready / experimental / enabled_by_default.

    Rules (per P1.1 spec — "no fake data" + "no experimental marked
    production-ready"):

    * INVALID  — any validation_error is present
    * METADATA_ONLY — no validation errors but the pack is not wired for
      execution: ``expert-stub`` agent_type with no real experts wired,
      or no experts and no code, or empty system_prompt
    * EXECUTABLE — full validation passes AND the pack has either real
      experts OR executable code
    """
    # Phase A1D.5 — explicit metadata-only maturity short-circuits to
    # METADATA_ONLY status. These packs exist for catalog presence /
    # road-map signaling; they ship a manifest but intentionally ship
    # no runnable system_prompt or wired experts. They are visible in
    # the registry (so users can see what's coming) but never enabled.
    # Must run BEFORE the validation_errors check so stubs that ship
    # v1.0-style vestigial fields (e.g. inline code dict, canonical_key
    # experts) are not penalized for schema drift in their stub state.
    if _is_metadata_only_maturity(p):
        p.status = PackStatus.METADATA_ONLY
        p.production_ready = False
        p.enabled_by_default = False
        p.experimental = False
        return

    if p.validation_errors:
        p.status = PackStatus.INVALID
        p.production_ready = False
        p.enabled_by_default = False
        return

    # v1.2 expert-stub: needs at least one expert with non-empty system_prompt
    # or model, AND tools/executors wired. Most Phase D2 stubs ship with
    # just an experts[] skeleton — those are METADATA_ONLY until the impl lands.
    if p.agent_type == "expert-stub":
        if _has_real_experts(p):
            p.status = PackStatus.EXECUTABLE
            p.production_ready = False   # expert-stubs are not production-ready by definition
        else:
            p.status = PackStatus.METADATA_ONLY
            p.production_ready = False
        p.experimental = False
        p.enabled_by_default = True
        return

    if p.agent_type == "reference":
        # canonical reference impl — executable (MedCodER family) but
        # explicitly NOT production_ready (per spec: no experimental /
        # metadata-only marked production-ready, and reference is the
        # "real Python impl" marker that bypasses hybrid_adapter).
        p.status = PackStatus.EXECUTABLE
        p.production_ready = _production_ready_from_manifest(p, inferred=True)
        p.experimental = False
        p.enabled_by_default = True
        return

    if p.agent_type == "internal_engine":
        # Phase 3-A: internal engine backing a Corti-style product Agent.
        # Same execution semantics as reference (real Python impl, real
        # experts/tools), but flagged as internal-only — not user-facing.
        # The Medical Coding Agent (icoder/medical-coding-agent@2.0.0)
        # is the user-facing product; medcoder-coding-review is its engine.
        p.status = PackStatus.EXECUTABLE
        p.production_ready = _production_ready_from_manifest(p, inferred=True)
        p.experimental = False
        p.enabled_by_default = True
        return

    if p.agent_type == "community":
        # community packs need real code to be executable
        if p.code:
            p.status = PackStatus.EXECUTABLE
            p.production_ready = _production_ready_from_manifest(p, inferred=True)
        else:
            p.status = PackStatus.METADATA_ONLY
            p.production_ready = False
        p.experimental = False
        p.enabled_by_default = (not p.code)  # community code packs default-disabled (tier 2)
        return

    # certified
    if p.code:
        p.status = PackStatus.INVALID
        p.validation_errors.append("certified agents cannot contain code/")
        p.production_ready = False
        p.enabled_by_default = False
        return

    if _has_real_experts(p) or p.tools or _has_non_prompt_backend(p):
        p.status = PackStatus.EXECUTABLE
        p.production_ready = _production_ready_from_manifest(p, inferred=True)
    else:
        # Pure-prompt certified: still executable but production-ready False
        # (per P1.1 honest-classification rule)
        p.status = PackStatus.EXECUTABLE
        p.production_ready = False
        p.validation_warnings.append(
            "certified pack has no experts/tools — pure-prompt template, production_ready=False"
        )
    p.experimental = False
    p.enabled_by_default = True


def _has_real_experts(p: NormalizedPack) -> bool:
    """A real expert is one with an id, a name, and either a system_prompt
    or a non-empty tools list."""
    return any(
        e.id and e.name and (e.system_prompt or e.tools or e.model)
        for e in p.experts
    )


def _has_non_prompt_backend(p: NormalizedPack) -> bool:
    """Recognize an explicit runtime that is more than prompt execution."""
    return bool(p.backend_provider) and p.backend_provider not in {
        "icoder.pure-llm.v1",
        "icoder.llm-with-tools.v1",
    }


def _production_ready_from_manifest(p: NormalizedPack, *, inferred: bool) -> bool:
    """Honor explicit governance state over loader shape inference.

    Executable wiring cannot overrule ``manifest.production_ready=false``.
    Legacy packs that omit the field retain historical inferred behavior.
    """
    manifest = p.raw.get("manifest") or {}
    declared = manifest.get("production_ready") if isinstance(manifest, dict) else None
    return declared if isinstance(declared, bool) else inferred


def _assess_launch_candidate(p: NormalizedPack) -> None:
    """Assess the development-verifiable gate for an external release cycle.

    ``launch_candidate_ready`` is intentionally narrower than production
    readiness.  It proves that the pack is executable, auditable, bounded and
    testable from repository evidence.  Hospital integration, independent
    clinical validation, security/privacy review and deployment approval stay
    explicit external gates even when this assessment passes.
    """
    blockers: list[str] = []
    manifest = p.raw.get("manifest") or {}
    maturity = str(manifest.get("maturity", "")) if isinstance(manifest, dict) else ""
    tags = set(p.tags)

    if p.status != PackStatus.EXECUTABLE:
        blockers.append(f"pack_status={p.status.value}; executable required")
    if maturity in {"metadata-only", "stub", "deprecated"} or tags.intersection(
        {"metadata-only", "stub", "deprecated"}
    ):
        blockers.append("placeholder/deprecated maturity or tag must be removed")
    if not p.system_prompt.strip():
        blockers.append("system_prompt is required")
    if not (p.backend_provider or p.a2a.get("endpoint")):
        blockers.append("explicit backend_provider or a2a.endpoint is required")
    if p.backend_provider == "icoder.pure-llm.v1" and p.tools:
        blockers.append("pure_llm backend cannot declare runtime tools")

    schema_ref = p.output_contract.get("schema_ref")
    required_fields = p.output_contract.get("required_fields")
    raw_optional_fields = p.output_contract.get("optional_fields", [])
    optional_fields = declared_optional_fields(p.output_contract)
    if not isinstance(schema_ref, str) or not schema_ref.strip():
        blockers.append("output_contract.schema_ref is required")
    if not isinstance(required_fields, list) or not required_fields:
        blockers.append("output_contract.required_fields must be non-empty")
    if not isinstance(raw_optional_fields, list):
        blockers.append("output_contract.optional_fields must be an array when present")
    elif (
        len(optional_fields) != len(raw_optional_fields)
        or len(set(optional_fields)) != len(optional_fields)
        or any(not field.strip() for field in optional_fields)
    ):
        blockers.append("output_contract.optional_fields must contain unique non-empty strings")
    if isinstance(required_fields, list) and set(required_fields).intersection(optional_fields):
        blockers.append("output_contract.required_fields and optional_fields must be disjoint")
    declared_fields = [
        field for field in (required_fields if isinstance(required_fields, list) else [])
        if isinstance(field, str)
    ] + optional_fields
    field_types = declared_field_types(p.output_contract)
    if not isinstance(p.output_contract.get("field_types"), dict):
        blockers.append("output_contract.field_types must be an object")
    elif declared_fields:
        missing_type_declarations = [
            field for field in declared_fields if field not in field_types
        ]
        unsupported_type_declarations = [
            field for field in declared_fields
            if field_types.get(field) not in SUPPORTED_FIELD_TYPES
        ]
        if missing_type_declarations:
            blockers.append(
                "output_contract.field_types must cover every required field: "
                + ", ".join(missing_type_declarations)
            )
        if unsupported_type_declarations:
            blockers.append(
                "output_contract.field_types contains unsupported types for: "
                + ", ".join(unsupported_type_declarations)
            )
        stale_type_declarations = sorted(set(field_types) - set(declared_fields))
        if stale_type_declarations:
            blockers.append(
                "output_contract.field_types contains undeclared fields: "
                + ", ".join(stale_type_declarations)
            )
        raw_field_schemas = p.output_contract.get("field_schemas")
        field_schemas = declared_field_schemas(p.output_contract)
        if declared_fields and not isinstance(raw_field_schemas, dict):
            blockers.append("output_contract.field_schemas must be an object")
        elif isinstance(raw_field_schemas, dict):
            missing_field_schemas = sorted(set(declared_fields) - set(field_schemas))
            stale_field_schemas = sorted(set(field_schemas) - set(declared_fields))
            if missing_field_schemas:
                blockers.append(
                    "output_contract.field_schemas must cover every declared field: "
                    + ", ".join(missing_field_schemas)
                )
            if stale_field_schemas:
                blockers.append(
                    "output_contract.field_schemas contains undeclared fields: "
                    + ", ".join(stale_field_schemas)
                )
            for field in declared_fields:
                schema = field_schemas.get(field)
                if schema is None:
                    continue
                blockers.extend(
                    validate_field_schema_definition(
                        schema,
                        path=f"output_contract.field_schemas.{field}",
                        expected_root_type=field_types.get(field),
                    )
                )
        blockers.extend(validate_field_relations_definition(p.output_contract))
        blockers.extend(validate_evidence_bindings_definition(p.output_contract))
        blockers.extend(validate_cross_agent_relations_definition(p.output_contract))

    # Every first-party clinical pack processes potentially identifiable chart
    # content.  Candidate packs must declare the same fail-closed guardrails,
    # independent of whether a particular demo input is synthetic.
    if p.phi_redaction != "required":
        blockers.append("phi_redaction=required is required")
    if not p.recorder_required:
        blockers.append("recorder_required=true is required")
    if not p.metrics_required:
        blockers.append("metrics_required=true is required")
    if not p.permissions.get("production_writeback_blocked", False):
        blockers.append("permissions.production_writeback_blocked=true is required")

    human_review = str(manifest.get("human_review", "")) if isinstance(manifest, dict) else ""
    if human_review != "required" and not p.human_review_required_when:
        blockers.append("human review policy or explicit review triggers are required")
    if not p.example_inputs:
        blockers.append("at least one example_input is required for smoke/E2E tests")
    if not p.example_outputs:
        blockers.append("at least one contract-complete example_output is required")
    elif isinstance(required_fields, list) and required_fields:
        contract_complete = any(
            all(field in example for field in required_fields)
            for example in p.example_outputs
            if isinstance(example, dict)
        )
        if not contract_complete:
            blockers.append(
                "an example_output containing every output_contract.required_field is required"
            )
        elif field_types:
            type_complete = any(
                all(field in example for field in required_fields)
                and not validate_required_field_types(example, p.output_contract)
                and not validate_declared_field_schemas(example, p.output_contract)
                and not (set(example) - set(declared_fields))
                for example in p.example_outputs
                if isinstance(example, dict)
            )
            if not type_complete:
                blockers.append(
                    "a contract-complete example_output with valid declared field types is required"
                )
            missing_optional_examples = [
                field for field in optional_fields
                if not any(field in example for example in p.example_outputs)
            ]
            if missing_optional_examples:
                blockers.append(
                    "every optional output field requires at least one typed example: "
                    + ", ".join(missing_optional_examples)
                )

    # Integrity is optional in the pack format, but a pack that declares it
    # must provide a real canonical SHA-256. Placeholders and stale hashes
    # cannot qualify as release candidates.
    if p.integrity:
        declared_sha = str(p.integrity.get("sha256") or "").lower()
        if len(declared_sha) != 64 or any(c not in "0123456789abcdef" for c in declared_sha):
            blockers.append("integrity.sha256 must be a 64-character lowercase hex digest")
        elif declared_sha != _canonical_pack_sha256(p.raw):
            blockers.append("integrity.sha256 does not match canonical pack content")

    p.launch_candidate_blockers = blockers
    p.launch_candidate_ready = not blockers
    p.external_release_gates = [
        "independent_clinical_quality_validation",
        "hospital_workflow_and_interoperability_validation",
        "security_privacy_and_compliance_review",
        "production_infrastructure_and_operations_approval",
    ]


def _canonical_pack_sha256(pack: dict[str, Any]) -> str:
    """Match the v1 pack integrity algorithm for every normalized version."""
    # ``_pack_mtime_iso`` is injected by the Hub at read time solely for card
    # presentation.  It is not authored pack content and must not invalidate a
    # pack whose canonical digest was verified directly from disk.
    excluded = {
        "integrity",
        "downloads",
        "published_at",
        "loaded_at",
        "_pack_mtime_iso",
    }
    clean = {key: value for key, value in pack.items() if key not in excluded}
    raw = json.dumps(clean, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ── Aggregations over many packs ──


def summary_counts(packs: Iterable[NormalizedPack]) -> dict[str, int]:
    """Aggregate status / production_ready counts for API + doctor."""
    packs = list(packs)
    by_status: dict[str, int] = {s.value: 0 for s in PackStatus}
    by_type: dict[str, int] = {}
    by_format: dict[str, int] = {}
    production_ready = 0
    launch_candidate_ready = 0
    experimental = 0
    metadata_only = 0
    invalid = 0
    for p in packs:
        by_status[p.status.value] += 1
        by_type[p.agent_type] = by_type.get(p.agent_type, 0) + 1
        by_format[p.format_version] = by_format.get(p.format_version, 0) + 1
        if p.production_ready:
            production_ready += 1
        if p.launch_candidate_ready:
            launch_candidate_ready += 1
        if p.experimental:
            experimental += 1
        if p.status == PackStatus.METADATA_ONLY:
            metadata_only += 1
        if p.status == PackStatus.INVALID:
            invalid += 1
    return {
        "total": len(packs),
        "executable": by_status[PackStatus.EXECUTABLE.value],
        "metadata_only": metadata_only,
        "invalid": invalid,
        "production_ready": production_ready,
        "launch_candidate_ready": launch_candidate_ready,
        "experimental": experimental,
        "by_type": by_type,
        "by_format": by_format,
    }


def why_not_executable(p: NormalizedPack) -> list[str]:
    """Human-readable list of reasons a pack is not in EXECUTABLE state.

    Used by the Agent Hub ``WhyNotExecutable`` panel.
    """
    reasons: list[str] = []
    if p.status == PackStatus.EXECUTABLE:
        return reasons

    if p.status == PackStatus.INVALID:
        reasons.append(f"INVALID — {len(p.validation_errors)} validation error(s):")
        reasons.extend(f"  • {e}" for e in p.validation_errors)
        return reasons

    if p.status == PackStatus.METADATA_ONLY:
        if p.agent_type == "expert-stub":
            reasons.append(
                "expert-stub pack: skeleton with no executable expert wired yet. "
                "Likely waiting for Phase D implementation."
            )
        elif p.agent_type == "community" and not p.code:
            reasons.append("community pack with no code/ — no executor to dispatch.")
        elif not p.experts and not p.tools:
            reasons.append("no experts[] and no tools[] — nothing to dispatch.")
        else:
            reasons.append("METADATA_ONLY — see validation_warnings above.")
        if p.validation_warnings:
            reasons.append("warnings:")
            reasons.extend(f"  • {w}" for w in p.validation_warnings)
    return reasons


# ── Convenience: compat shim ──


def normalized_from_record(
    rec_pack_data: dict[str, Any],
    *,
    source_path: str | None = None,
) -> NormalizedPack:
    """Build a NormalizedPack from a stored ``InstalledAgentRecord.pack_data``.

    Mirrors :func:`load_pack` but tolerates the legacy DB-shaped envelope.
    Always returns a NormalizedPack with at least agent_ref, format_version,
    agent_type, and name derived from available fields.
    """
    return load_pack(rec_pack_data, source_path=source_path)


# ── slug helper ──


def _slugify(name: str) -> str:
    """Best-effort slug for agent_ref derivation. Mirrors registry.install()."""
    import re
    s = re.sub(r"[^a-zA-Z0-9\-]+", "-", name).strip("-").lower()
    return s or "agent"
