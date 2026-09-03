"""A1B-AE.2 — Canonical Agent/Expert/Pack catalog builder.

Scans the filesystem (no DB access, no hardcoded counts) and emits 5
machine-rebuildable catalogs under ``backend/agent_catalog/``:

  - ``pack_catalog.json``    — every ``backend/official_agents/*`` dir,
                               classified (RUNNABLE_PACK / METADATA_ONLY_PACK
                               / LEGACY_CODE_ORPHAN) with dual-name pairing.
  - ``agent_catalog.json``   — one entry per logical Agent (canonical name
                               chosen between legacy ``_``-form and Pack
                               ``-``-form; expert linkage; seed.py linkage).
  - ``expert_catalog.json``  — one entry per Expert (Corti 9-key public
                               registry + iCoDer internal Python experts +
                               Pack-declared experts).
  - ``aliases.json``         — alias resolution map
                               (e.g. ``code_validation`` -> ``code-validation``).
  - ``migrations.json``      — explicit migration steps to reconcile
                               legacy dual-named Packs to canonical names.

The script is the ONLY source of truth for A1B-AE.2 catalog counts.
Re-running it MUST produce byte-identical output when the filesystem
hasn't changed (deterministic: sorted lists, no timestamps).

Charter A1B-AE.0 §7 — clean-room: this script reads iCoDer filesystem
only. No Corti-internal assets used.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_AGENTS_DIR = REPO_ROOT / "backend" / "official_agents"
INTERNAL_EXPERTS_DIR = REPO_ROOT / "backend" / "app" / "agents" / "experts"
SEED_FILE = REPO_ROOT / "backend" / "app" / "seed.py"
CATALOG_OUT = REPO_ROOT / "backend" / "agent_catalog"

# Corti public 9-key Expert registry (A1B-AE.1 §3.2 — clean-room)
CORTI_PUBLIC_EXPERT_KEYS = (
    "memory-expert",
    "coding-expert",
    "medical-calculator-expert",
    "drugbank-expert",
    "posos-expert",
    "pubmed-expert",
    "clinical-trials-expert",
    "web-search-expert",
    "interviewing-expert",
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PackEntry:
    dir_name: str
    classification: str  # RUNNABLE_PACK | METADATA_ONLY_PACK | LEGACY_CODE_ORPHAN | EMPTY
    has_agent_pack: bool
    has_init_py: bool
    has_agent_py: bool
    py_file_count: int
    agent_ref: str | None
    manifest_name: str | None
    manifest_category: str | None
    manifest_maturity: str | None
    agent_type: str | None
    declared_experts: list[str] = field(default_factory=list)
    legacy_version_claim: str | None = None  # from __init__.py docstring
    dual_name_pair: str | None = None  # paired dir name if dual-named


@dataclass
class AgentCatalogEntry:
    canonical_name: str  # the chosen survivor between dual names
    canonical_agent_ref: str | None
    sources: list[str]  # which sources mention this agent
    pack_dir: str | None
    seed_key: str | None
    expert_ids: list[str]
    classification: str
    dual_name_migration: str | None  # e.g. "code_validation -> code-validation"


@dataclass
class ExpertCatalogEntry:
    key: str
    origin: str  # CORTI_PUBLIC | ICODER_INTERNAL | PACK_DECLARED
    source_file: str | None
    pack_dir: str | None
    corti_alignment: str  # ALIGNED | PARTIAL | ICODER_ONLY | UNKNOWN
    notes: str


@dataclass
class AliasEntry:
    alias: str
    canonical: str
    reason: str


@dataclass
class MigrationStep:
    legacy: str
    canonical: str
    action: str
    rationale: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


_LEGACY_VERSION_RE = re.compile(r"@(\d+\.\d+\.\d+)")


def _extract_legacy_version_claim(init_path: Path) -> str | None:
    """Pull a ``@x.y.z`` version claim from a Pack's ``__init__.py``
    module docstring (top-of-file). Returns None if not found."""
    try:
        src = init_path.read_text(encoding="utf-8")
    except Exception:
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    if (tree.body and isinstance(tree.body[0], ast.Expr)
            and isinstance(tree.body[0].value, ast.Constant)
            and isinstance(tree.body[0].value.value, str)):
        doc = tree.body[0].value.value
        m = _LEGACY_VERSION_RE.search(doc)
        if m:
            return m.group(1)
    # Fallback: regex the whole file
    m = _LEGACY_VERSION_RE.search(src)
    return m.group(1) if m else None


def _classify(pack_dir: Path) -> tuple[str, int]:
    """Classify a Pack directory based on what's inside."""
    has_init = (pack_dir / "__init__.py").exists()
    has_pack = (pack_dir / "agent_pack.json").exists()
    py_files = sorted(pack_dir.glob("*.py"))
    if has_init and has_pack:
        return "RUNNABLE_PACK", len(py_files)
    if has_pack and not has_init:
        return "METADATA_ONLY_PACK", len(py_files)
    if has_init and not has_pack:
        return "LEGACY_CODE_ORPHAN", len(py_files)
    return "EMPTY", len(py_files)


def _seed_prebuilt_keys() -> dict[str, dict[str, str]]:
    """Parse ``seed.py`` PREBUILT_AGENTS list without executing it.

    Returns ``{key: {name, desc, category, expert_name}}``.
    """
    try:
        src = SEED_FILE.read_text(encoding="utf-8")
    except Exception:
        return {}
    # Locate the PREBUILT_AGENTS = [ ... ] block
    m = re.search(
        r"PREBUILT_AGENTS\s*=\s*\[(?P<body>.*?)^\s*\]",
        src,
        re.DOTALL | re.MULTILINE,
    )
    if not m:
        return {}
    body = m.group("body")
    # Each row looks like: {"key": "...", "name": "...", ...}
    out: dict[str, dict[str, str]] = {}
    for row_match in re.finditer(r"\{(?P<inner>.*?)\}", body, re.DOTALL):
        inner = row_match.group("inner")
        kv: dict[str, str] = {}
        for field_match in re.finditer(
            r'"(?P<k>[a-z_]+)"\s*:\s*"(?P<v>[^"]*)"', inner
        ):
            kv[field_match.group("k")] = field_match.group("v")
        if "key" in kv:
            out[kv["key"]] = kv
    return out


# ---------------------------------------------------------------------------
# Main builders
# ---------------------------------------------------------------------------


def build_pack_catalog() -> tuple[list[PackEntry], dict[str, PackEntry]]:
    """Scan ``backend/official_agents/`` and classify every dir."""
    if not OFFICIAL_AGENTS_DIR.exists():
        return [], {}
    entries: list[PackEntry] = []
    by_dirname: dict[str, PackEntry] = {}
    for d in sorted(OFFICIAL_AGENTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        classification, py_count = _classify(d)
        pack_json = _safe_read_json(d / "agent_pack.json")
        manifest = (pack_json or {}).get("manifest") or {}
        declared_experts: list[str] = []
        if pack_json and isinstance(pack_json.get("experts"), list):
            for e in pack_json["experts"]:
                if isinstance(e, dict):
                    ref = e.get("expert_ref") or e.get("id") or e.get("name")
                    if ref:
                        declared_experts.append(str(ref))  # noqa: pyflakes
        entry = PackEntry(
            dir_name=d.name,
            classification=classification,
            has_agent_pack=pack_json is not None,
            has_init_py=(d / "__init__.py").exists(),
            has_agent_py=(d / "agent.py").exists(),
            py_file_count=py_count,
            agent_ref=(pack_json or {}).get("agent_ref"),
            manifest_name=manifest.get("name"),
            manifest_category=manifest.get("category"),
            manifest_maturity=manifest.get("maturity"),
            agent_type=(pack_json or {}).get("agent_type"),
            declared_experts=sorted(set(declared_experts)),  # noqa: pyflakes
            legacy_version_claim=(
                _extract_legacy_version_claim(d / "__init__.py")
                if (d / "__init__.py").exists() else None
            ),
            dual_name_pair=None,
        )
        entries.append(entry)
        by_dirname[d.name] = entry

    # Second pass: detect dual-name pairs (legacy `foo_bar` <-> new `foo-bar`)
    for entry in entries:
        if "_" not in entry.dir_name:
            continue
        candidate_dash = entry.dir_name.replace("_", "-")
        if candidate_dash in by_dirname and candidate_dash != entry.dir_name:
            entry.dual_name_pair = candidate_dash
            partner = by_dirname[candidate_dash]
            partner.dual_name_pair = entry.dir_name
    return entries, by_dirname


def build_agent_catalog(
    pack_entries: list[PackEntry],
    seed_keys: dict[str, dict[str, str]],
) -> list[AgentCatalogEntry]:
    """Collapse dual-named Packs + seed.py rows into one Agent per
    canonical name. Canonical name = the dash-form (Pack form)."""
    # Index by canonical candidate name (dash-form)
    by_canonical: dict[str, AgentCatalogEntry] = {}

    def _canon_for(dir_name: str) -> str:
        return dir_name.replace("_", "-")

    # First: Walk Pack entries
    for pe in pack_entries:
        if pe.classification == "EMPTY":
            continue
        canonical = _canon_for(pe.dir_name)
        sources: list[str] = []
        if pe.has_agent_pack:
            sources.append(f"official_agents/{pe.dir_name}/agent_pack.json")
        if pe.has_init_py:
            sources.append(f"official_agents/{pe.dir_name}/__init__.py")
        migration = None
        if (
            pe.dual_name_pair
            and pe.dir_name == canonical  # the dash-form canonical
            and "_" in pe.dual_name_pair
        ):
            migration = f"{pe.dual_name_pair} -> {canonical}"

        entry = by_canonical.get(canonical)
        if entry is None:
            entry = AgentCatalogEntry(
                canonical_name=canonical,
                canonical_agent_ref=pe.agent_ref,
                sources=sources,
                pack_dir=pe.dir_name,
                seed_key=None,
                expert_ids=list(pe.declared_experts),
                classification=pe.classification,
                dual_name_migration=migration,
            )
            by_canonical[canonical] = entry
        else:
            entry.sources.extend(sources)
            entry.sources = sorted(set(entry.sources))
            if pe.agent_ref and not entry.canonical_agent_ref:
                entry.canonical_agent_ref = pe.agent_ref
            if pe.declared_experts:
                entry.expert_ids.extend(pe.declared_experts)
                entry.expert_ids = sorted(set(entry.expert_ids))
            if pe.dual_name_pair and "_" in pe.dir_name:
                # legacy half of a dual-name pair
                if not entry.dual_name_migration:
                    entry.dual_name_migration = f"{pe.dir_name} -> {canonical}"
                entry.pack_dir = canonical  # survivor is the dash-form

    # Second: Walk seed.py PREBUILT_AGENTS keys
    for key, meta in seed_keys.items():
        entry = by_canonical.get(key)
        if entry is None:
            entry = AgentCatalogEntry(
                canonical_name=key,
                canonical_agent_ref=None,
                sources=["backend/app/seed.py#PREBUILT_AGENTS"],
                pack_dir=None,
                seed_key=key,
                expert_ids=[],
                classification="SEED_ONLY_NO_PACK",
                dual_name_migration=None,
            )
            by_canonical[key] = entry
        else:
            entry.seed_key = key
            entry.sources.append("backend/app/seed.py#PREBUILT_AGENTS")
            entry.sources = sorted(set(entry.sources))
            if meta.get("expert_name") and meta["expert_name"] not in entry.expert_ids:
                entry.expert_ids.append(meta["expert_name"])

    return sorted(by_canonical.values(), key=lambda a: a.canonical_name)


def build_expert_catalog(
    pack_entries: list[PackEntry],
) -> list[ExpertCatalogEntry]:
    """Combine Corti public 9-key + iCoDer internal Python experts +
    Pack-declared experts into one canonical Expert catalog."""
    out: dict[str, ExpertCatalogEntry] = {}

    # 1. Corti public 9-key (clean-room)
    for key in CORTI_PUBLIC_EXPERT_KEYS:
        out[key] = ExpertCatalogEntry(
            key=key,
            origin="CORTI_PUBLIC",
            source_file=None,
            pack_dir=None,
            corti_alignment="CORTI_REFERENCE",
            notes="Corti public docs §3.2 (A1B-AE.1). Implementation target mapped in §3.2.",
        )

    # 2. iCoDer internal Python experts
    if INTERNAL_EXPERTS_DIR.exists():
        for f in sorted(INTERNAL_EXPERTS_DIR.glob("*.py")):
            if f.name == "__init__.py":
                continue
            stem = f.stem  # e.g. "audit_expert"
            # Convert "audit_expert" -> "audit-expert" key
            key = stem.replace("_", "-")
            out.setdefault(
                key,
                ExpertCatalogEntry(
                    key=key,
                    origin="ICODER_INTERNAL",
                    source_file=str(f.relative_to(REPO_ROOT)).replace("\\", "/"),
                    pack_dir=None,
                    corti_alignment="ICODER_ONLY",
                    notes="Internal Python expert; no Corti-public counterpart enumerated.",
                ),
            )

    # 3. Pack-declared experts (from agent_pack.json `experts[]`)
    for pe in pack_entries:
        if not pe.has_agent_pack:
            continue
        for ref in pe.declared_experts:
            # Normalise: take last segment of foo/bar@x.y.z -> foo-bar
            norm = ref.split("/")[-1].split("@")[0]
            key = norm.replace("_", "-")
            existing = out.get(key)
            if existing is None:
                out[key] = ExpertCatalogEntry(
                    key=key,
                    origin="PACK_DECLARED",
                    source_file=None,
                    pack_dir=pe.dir_name,
                    corti_alignment="UNKNOWN",
                    notes=f"Declared in official_agents/{pe.dir_name}/agent_pack.json",
                )
            else:
                # Mark that this Pack also declares it
                if not existing.pack_dir:
                    existing.pack_dir = pe.dir_name
                else:
                    existing.notes += (
                        f"; also declared in {pe.dir_name}"
                    )

    # Compute Corti alignment for iCoDer internal + Pack-declared experts
    corti_keys_set = set(CORTI_PUBLIC_EXPERT_KEYS)
    for key, entry in out.items():
        if entry.origin == "CORTI_PUBLIC":
            continue
        # Heuristic alignment: stem matches a Corti key
        base_key = key.removesuffix("-expert")
        aligned = any(
            base_key == ck.removesuffix("-expert") for ck in corti_keys_set
        )
        if aligned:
            entry.corti_alignment = "ALIGNED"
        elif key in corti_keys_set:
            entry.corti_alignment = "ALIGNED"

    return sorted(out.values(), key=lambda e: e.key)


def build_aliases(
    pack_entries: list[PackEntry],
) -> list[AliasEntry]:
    """Build alias resolution map. For every dual-named pair, the
    underscore-form aliases to the dash-form (dash-form is canonical
    per §9 — matches Corti public convention)."""
    out: list[AliasEntry] = []
    seen: set[str] = set()
    for pe in pack_entries:
        if not pe.dual_name_pair or pe.classification == "EMPTY":
            continue
        if "_" in pe.dir_name:
            alias = pe.dir_name
            canonical = pe.dual_name_pair
        else:
            # dash-form entry: skip (we record underscore -> dash only)
            continue
        if alias in seen:
            continue
        seen.add(alias)
        out.append(AliasEntry(
            alias=alias,
            canonical=canonical,
            reason="LEGACY_DUAL_NAME: legacy code dir used underscores; canonical Pack name uses dashes (Corti public convention).",
        ))
    return sorted(out, key=lambda a: a.alias)


def build_migrations(
    aliases: list[AliasEntry],
    pack_entries: list[PackEntry],
) -> list[MigrationStep]:
    """Explicit migration steps for §9.4 version-shadowing defect class."""
    by_dirname = {pe.dir_name: pe for pe in pack_entries}
    out: list[MigrationStep] = []
    for a in aliases:
        legacy = by_dirname.get(a.alias)
        canonical = by_dirname.get(a.canonical)
        legacy_ver = legacy.legacy_version_claim if legacy else None
        canonical_ver = (
            (canonical.agent_ref or "").split("@")[-1]
            if canonical and canonical.agent_ref else None
        )
        rationale = (
            f"Legacy {a.alias} __init__.py claims @{legacy_ver}; "
            f"canonical {a.canonical}/agent_pack.json claims @{canonical_ver}. "
            "Resolve in A1B-AE.4 (alias resolver) and A1B-AE.9 (deprecate legacy)."
        )
        out.append(MigrationStep(
            legacy=a.alias,
            canonical=a.canonical,
            action="RENAME_LEGACY_DIR_OR_DELETE_AFTER_ALIAS_RESOLVER_LANDED",
            rationale=rationale,
        ))
    return out


# ---------------------------------------------------------------------------
# Serialise
# ---------------------------------------------------------------------------


def _to_jsonable(obj: Any) -> Any:
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_jsonable(getattr(obj, k)) for k in asdict(obj).keys()}
    if isinstance(obj, list):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_jsonable(v) for k, v in obj.items()}
    return obj


def write_catalog(name: str, payload: Any) -> None:
    CATALOG_OUT.mkdir(parents=True, exist_ok=True)
    out_path = CATALOG_OUT / name
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(_to_jsonable(payload), fh, indent=2, ensure_ascii=False, sort_keys=False)
        fh.write("\n")
    print(f"  wrote {out_path.relative_to(REPO_ROOT)}")


def main() -> int:
    if not OFFICIAL_AGENTS_DIR.exists():
        print(f"ERROR: {OFFICIAL_AGENTS_DIR} not found", file=sys.stderr)
        return 2
    pack_entries, _ = build_pack_catalog()
    seed_keys = _seed_prebuilt_keys()
    agent_entries = build_agent_catalog(pack_entries, seed_keys)
    expert_entries = build_expert_catalog(pack_entries)
    aliases = build_aliases(pack_entries)
    migrations = build_migrations(aliases, pack_entries)

    # ---- summary header (machine-rebuildable counts only; no magic numbers) ----
    pack_total = len(pack_entries)
    pack_runnable = sum(1 for p in pack_entries if p.classification == "RUNNABLE_PACK")
    pack_meta_only = sum(1 for p in pack_entries if p.classification == "METADATA_ONLY_PACK")
    pack_legacy_orphan = sum(1 for p in pack_entries if p.classification == "LEGACY_CODE_ORPHAN")
    pack_empty = sum(1 for p in pack_entries if p.classification == "EMPTY")
    dual_named_pairs = len(aliases)
    agent_total = len(agent_entries)
    expert_total = len(expert_entries)
    expert_corti = sum(1 for e in expert_entries if e.origin == "CORTI_PUBLIC")
    expert_internal = sum(1 for e in expert_entries if e.origin == "ICODER_INTERNAL")
    expert_pack = sum(1 for e in expert_entries if e.origin == "PACK_DECLARED")
    seed_total = len(seed_keys)

    summary = {
        "charter": "A1B-AE.2",
        "generated_by": "scripts/a1b_ae_2_build_catalogs.py",
        "clean_room_attested": True,
        "counts": {
            "pack_total": pack_total,
            "pack_runnable": pack_runnable,
            "pack_metadata_only": pack_meta_only,
            "pack_legacy_orphan": pack_legacy_orphan,
            "pack_empty": pack_empty,
            "dual_named_pairs": dual_named_pairs,
            "agent_total_canonical": agent_total,
            "expert_total": expert_total,
            "expert_corti_public_9key": expert_corti,
            "expert_icoder_internal": expert_internal,
            "expert_pack_declared": expert_pack,
            "seed_prebuilt_agents": seed_total,
        },
        "classification_legend": {
            "RUNNABLE_PACK": "dir has both __init__.py (Python code) and agent_pack.json",
            "METADATA_ONLY_PACK": "dir has only agent_pack.json; no runnable Python",
            "LEGACY_CODE_ORPHAN": "dir has only __init__.py; missing Pack manifest",
            "EMPTY": "dir is empty (no __init__.py, no agent_pack.json)",
        },
        "expert_origin_legend": {
            "CORTI_PUBLIC": "clean-room copy of Corti public 9-key registry (A1B-AE.1 §3.2)",
            "ICODER_INTERNAL": "Python module under backend/app/agents/experts/",
            "PACK_DECLARED": "referenced inside an agent_pack.json `experts[]` list",
        },
        "canonical_name_rule": "For dual-named pairs, the dash-form is canonical (matches Corti public convention and Pack metadata). Legacy underscore-form is aliased.",
    }

    print(f"A1B-AE.2 catalog builder — "
          f"{pack_total} Packs ({pack_runnable} runnable / {pack_meta_only} metadata-only / {pack_legacy_orphan} legacy-orphan), "
          f"{dual_named_pairs} dual-name pairs, "
          f"{agent_total} canonical Agents, "
          f"{expert_total} Experts "
          f"({expert_corti} Corti-public + {expert_internal} iCoDer-internal + {expert_pack} pack-declared), "
          f"{seed_total} seed.py PREBUILT_AGENTS rows")

    write_catalog("pack_catalog.json", {
        "_summary": summary,
        "entries": pack_entries,
    })
    write_catalog("agent_catalog.json", {
        "_summary": summary,
        "entries": agent_entries,
    })
    write_catalog("expert_catalog.json", {
        "_summary": summary,
        "entries": expert_entries,
    })
    write_catalog("aliases.json", {
        "_summary": summary,
        "entries": aliases,
    })
    write_catalog("migrations.json", {
        "_summary": summary,
        "entries": migrations,
    })

    # Also drop a tiny build-info file as the regeneration receipt
    write_catalog("BUILD_INFO.json", {
        "charter": "A1B-AE.2",
        "script": "scripts/a1b_ae_2_build_catalogs.py",
        "summary_counts": summary["counts"],
        "canonical_name_rule": summary["canonical_name_rule"],
        "clean_room_attested": True,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
