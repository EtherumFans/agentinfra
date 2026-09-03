"""Compose independently validated local and external Agent evidence.

The two scoped bundles are useful for bounded reruns, but neither may inflate
the strict 26-Agent gate alone.  This composer revalidates both source bundles,
requires disjoint scopes whose union equals the current visible Pack snapshot,
and binds their hashes into one strict semantic evidence artifact.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from scripts.corti_parity.agent_hub_live_evidence import (  # noqa: E402
    canonical_sha256,
    sha256_file,
)
from scripts.corti_parity.build_agent_hub_external_semantic_evidence_bundle import (  # noqa: E402
    validate_external_bundle_file,
)
from scripts.corti_parity.build_agent_hub_local_semantic_evidence_bundle import (  # noqa: E402
    validate_local_bundle_file,
)
from scripts.corti_parity.build_agent_hub_semantic_evidence_bundle import (  # noqa: E402
    DEFAULT_AGENTS_DIR,
    _freshness_errors,
    _read_json,
    _snapshot_from_agents_dir,
    verify_bundle_digest,
)


EXPECTED_AGENT_COUNT = 26
COMPOSITE_QUALITY_SCOPE = (
    "fresh_composed_26_agent_http_semantic_safety_stability_not_clinical_accuracy"
)
DEFAULT_OUT_DIR = REPO_ROOT / "reports" / "agent_hub" / "composite_semantic_evidence"


def build_composite_bundle(
    *,
    local_bundle_path: Path,
    external_bundle_path: Path,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    max_age_hours: float = 24.0,
    now: datetime | None = None,
    matrix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if max_age_hours <= 0:
        raise ValueError("max_age_hours must be positive")
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    agents_dir = agents_dir.resolve()
    local_bundle_path = local_bundle_path.resolve()
    external_bundle_path = external_bundle_path.resolve()
    full_snapshot = _snapshot_from_agents_dir(agents_dir)
    errors: list[str] = []

    local_validation = validate_local_bundle_file(
        local_bundle_path,
        agents_dir=agents_dir,
        max_age_hours=max_age_hours,
        now=current,
        matrix=matrix,
    )
    external_validation = validate_external_bundle_file(
        external_bundle_path,
        agents_dir=agents_dir,
        max_age_hours=max_age_hours,
        now=current,
        matrix=matrix,
    )
    if not local_validation.get("valid"):
        errors.extend(
            f"local:{item}" for item in local_validation.get("errors") or []
        )
    if not external_validation.get("valid"):
        errors.extend(
            f"external:{item}" for item in external_validation.get("errors") or []
        )

    local_ids = set(local_validation.get("verified_agent_ids") or [])
    external_ids = set(external_validation.get("verified_agent_ids") or [])
    current_ids = set(full_snapshot)
    if local_ids & external_ids:
        errors.append("scope: local and external verified Agent sets overlap")
    if local_ids | external_ids != current_ids:
        errors.append("scope: scoped bundle union does not equal the 26 visible Agents")
    if len(current_ids) != EXPECTED_AGENT_COUNT:
        errors.append("scope: current visible Agent count is not 26")

    source_paths = {
        "local": local_bundle_path,
        "external": external_bundle_path,
    }
    common_source_root = Path(
        os.path.commonpath([str(path.parent) for path in source_paths.values()])
    )
    source_bundles: dict[str, dict[str, Any]] = {}
    for label, path in source_paths.items():
        try:
            source_bundles[label] = _read_json(path)
        except ValueError as exc:
            errors.append(f"{label}:{exc}")
            source_bundles[label] = {}

    errors = sorted(set(errors))
    verified_ids = current_ids if not errors else set()
    agent_results = [
        {
            "agent_id": agent_id,
            "scope": "local" if agent_id in local_ids else "external",
            "source_bundle_sha256": str(
                (
                    source_bundles["local"]
                    if agent_id in local_ids
                    else source_bundles["external"]
                ).get("bundle_sha256")
                or ""
            ),
            "semantic_live_e2e_verified": agent_id in verified_ids,
        }
        for agent_id in sorted(current_ids)
    ]
    bundle: dict[str, Any] = {
        "schema_version": "icoder.agent-hub-composite-semantic-evidence-bundle/v1",
        "generated_at": current.isoformat(),
        "quality_scope": COMPOSITE_QUALITY_SCOPE,
        "max_age_hours": max_age_hours,
        "valid": not errors and len(verified_ids) == EXPECTED_AGENT_COUNT,
        "errors": errors,
        "summary": {
            "visible_agents": len(current_ids),
            "local_semantic_e2e_verified": len(local_ids) if not errors else 0,
            "external_semantic_live_e2e_verified": (
                len(external_ids) if not errors else 0
            ),
            "semantic_live_e2e_verified": len(verified_ids),
            "semantic_live_e2e_pending": sorted(current_ids - verified_ids),
        },
        "sources": {
            label: {
                "path": str(path),
                "relative_path": str(path.relative_to(common_source_root)),
                "sha256": sha256_file(path) if path.is_file() else "",
                "schema_version": source_bundles[label].get("schema_version"),
                "bundle_sha256": source_bundles[label].get("bundle_sha256"),
                "generated_at": source_bundles[label].get("generated_at"),
            }
            for label, path in source_paths.items()
        },
        "agent_snapshot": full_snapshot,
        "agent_results": agent_results,
        "limitations": [
            "This artifact composes independently revalidated 24-Agent local and 2-Agent real-model evidence; neither source bundle can satisfy the 26-Agent gate alone.",
            "All cases remain Pack-owned synthetic development cases, not an independent clinical gold-standard evaluation.",
            "The bundle does not prove Corti product/model equivalence, hospital acceptance, regulatory approval, or production readiness.",
        ],
    }
    digest_payload = copy.deepcopy(bundle)
    bundle["bundle_sha256"] = canonical_sha256(digest_payload)
    return bundle


def _resolve_source_path(
    *,
    bundle_path: Path,
    source: dict[str, Any],
) -> Path:
    path = Path(str(source.get("path") or ""))
    if path.is_file():
        return path.resolve()
    relative = Path(str(source.get("relative_path") or ""))
    candidate = bundle_path.resolve().parent.parent / relative
    return candidate.resolve()


def validate_composite_bundle_file(
    bundle_path: Path,
    *,
    agents_dir: Path = DEFAULT_AGENTS_DIR,
    max_age_hours: float = 24.0,
    now: datetime | None = None,
    matrix: dict[str, Any] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        supplied = _read_json(bundle_path.resolve())
    except ValueError as exc:
        return {"valid": False, "errors": [str(exc)], "verified_agent_ids": []}
    if supplied.get("schema_version") != (
        "icoder.agent-hub-composite-semantic-evidence-bundle/v1"
    ):
        errors.append("bundle: unsupported schema_version")
    if supplied.get("quality_scope") != COMPOSITE_QUALITY_SCOPE:
        errors.append("bundle: composite quality scope is missing")
    if not verify_bundle_digest(supplied):
        errors.append("bundle: canonical digest mismatch")
    if supplied.get("valid") is not True:
        errors.append("bundle: source validation did not pass")

    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    errors.extend(
        _freshness_errors(
            supplied,
            label="bundle",
            now=current,
            max_age=timedelta(hours=max_age_hours),
        )
    )
    sources = supplied.get("sources")
    sources = sources if isinstance(sources, dict) else {}
    local_source = sources.get("local")
    local_source = local_source if isinstance(local_source, dict) else {}
    external_source = sources.get("external")
    external_source = external_source if isinstance(external_source, dict) else {}
    local_path = _resolve_source_path(
        bundle_path=bundle_path,
        source=local_source,
    )
    external_path = _resolve_source_path(
        bundle_path=bundle_path,
        source=external_source,
    )
    for label, path, source in (
        ("local", local_path, local_source),
        ("external", external_path, external_source),
    ):
        if not path.is_file():
            errors.append(f"{label}: source bundle is missing")
        elif str(source.get("sha256") or "") != sha256_file(path):
            errors.append(f"{label}: source bundle digest mismatch")

    rebuilt = build_composite_bundle(
        local_bundle_path=local_path,
        external_bundle_path=external_path,
        agents_dir=agents_dir.resolve(),
        max_age_hours=max_age_hours,
        now=current,
        matrix=matrix,
    )
    if not rebuilt.get("valid"):
        errors.extend(str(item) for item in rebuilt.get("errors") or [])
    if supplied.get("agent_snapshot") != rebuilt.get("agent_snapshot"):
        errors.append("bundle: current 26-Agent snapshot mismatch")
    if supplied.get("agent_results") != rebuilt.get("agent_results"):
        errors.append("bundle: composite Agent verification rows do not match sources")
    if {
        label: str((sources.get(label) or {}).get("sha256") or "")
        for label in ("local", "external")
    } != {
        label: str((rebuilt.get("sources", {}).get(label) or {}).get("sha256") or "")
        for label in ("local", "external")
    }:
        errors.append("bundle: source artifact digest mismatch")
    verified = sorted(
        str(item["agent_id"])
        for item in rebuilt.get("agent_results", [])
        if item.get("semantic_live_e2e_verified") is True
    )
    if len(verified) != EXPECTED_AGENT_COUNT:
        errors.append("bundle: all 26 visible Agents must be verified")
    return {
        "valid": not errors,
        "errors": sorted(set(errors)),
        "verified_agent_ids": verified if not errors else [],
        "bundle_sha256": str(supplied.get("bundle_sha256") or ""),
    }


def write_bundle(out_dir: Path, bundle: dict[str, Any]) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "agent_hub_composite_semantic_evidence_bundle.json"
    md_path = out_dir / "agent_hub_composite_semantic_evidence_bundle.md"
    json_path.write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = bundle["summary"]
    lines = [
        "# Agent Hub composite semantic evidence bundle",
        "",
        f"Generated: `{bundle['generated_at']}`",
        "",
        f"Validation: **{'PASS' if bundle['valid'] else 'FAIL'}**",
        "",
        f"Strict synthetic live semantic evidence: **{summary['semantic_live_e2e_verified']}/{summary['visible_agents']}**",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in bundle["limitations"])
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local-bundle", type=Path, required=True)
    parser.add_argument("--external-bundle", type=Path, required=True)
    parser.add_argument("--agents-dir", type=Path, default=DEFAULT_AGENTS_DIR)
    parser.add_argument("--max-age-hours", type=float, default=24.0)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    bundle = build_composite_bundle(
        local_bundle_path=args.local_bundle,
        external_bundle_path=args.external_bundle,
        agents_dir=args.agents_dir,
        max_age_hours=args.max_age_hours,
    )
    paths = write_bundle(args.out_dir, bundle)
    print(json.dumps(bundle["summary"], ensure_ascii=False))
    print(paths[0])
    print(paths[1])
    return 0 if bundle["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
