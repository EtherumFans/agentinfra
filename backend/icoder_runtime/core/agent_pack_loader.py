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

import json
import logging
from pathlib import Path
from typing import Any, Iterable

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

    _classify(normalized)
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
        p.validation_errors.append("system_prompt is required and must be a non-empty string")
        return
    p.system_prompt = sp


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
        p.production_ready = True
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
        p.production_ready = True
        p.experimental = False
        p.enabled_by_default = True
        return

    if p.agent_type == "community":
        # community packs need real code to be executable
        if p.code:
            p.status = PackStatus.EXECUTABLE
            p.production_ready = True
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

    if _has_real_experts(p) or p.tools:
        p.status = PackStatus.EXECUTABLE
        p.production_ready = True
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


# ── Aggregations over many packs ──


def summary_counts(packs: Iterable[NormalizedPack]) -> dict[str, int]:
    """Aggregate status / production_ready counts for API + doctor."""
    packs = list(packs)
    by_status: dict[str, int] = {s.value: 0 for s in PackStatus}
    by_type: dict[str, int] = {}
    by_format: dict[str, int] = {}
    production_ready = 0
    experimental = 0
    metadata_only = 0
    invalid = 0
    for p in packs:
        by_status[p.status.value] += 1
        by_type[p.agent_type] = by_type.get(p.agent_type, 0) + 1
        by_format[p.format_version] = by_format.get(p.format_version, 0) + 1
        if p.production_ready:
            production_ready += 1
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