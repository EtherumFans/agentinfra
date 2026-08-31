#!/usr/bin/env python3
"""Build and verify a reproducible snapshot of the current development tree.

This tool intentionally supports a dirty working tree.  It does not stage,
commit, tag, delete, or publish anything.  The resulting manifest makes every
visible change explicit and content-addressed so that the tree can be reviewed
and split into safe commits later.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "icoder/development-baseline/v1"
ROOT = Path(__file__).resolve().parents[2]

SOURCE_PREFIXES = (
    ".github/workflows/",
    "backend/alembic/",
    "backend/app/",
    "backend/compliance_services/",
    "backend/icoder_runtime/",
    "backend/official_agents/",
    "frontend/src/",
    "packages/",
    "scripts/",
    "web-components/",
)
TEST_MARKERS = ("/tests/", "/test_", ".test.", ".spec.")
DOC_PREFIXES = ("docs/", "reports/", "postman/")
GENERATED_PREFIXES = ("artifacts/", "outputs/", "screenshots/", "golden_captures/")
GENERATED_SUFFIXES = (".log", ".xml", ".png", ".jpg", ".jpeg", ".tgz", ".whl")
LOCAL_UNSAFE_NAMES = (".env", ".env.local", ".env.cloud")


class BaselineError(RuntimeError):
    pass


def git(root: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if check and result.returncode:
        raise BaselineError(result.stderr.strip() or "git command failed")
    return result.stdout


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def changed_paths(root: Path) -> dict[str, str]:
    """Return path -> compact state without depending on localized Git text."""
    states: dict[str, str] = {}
    for line in git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines():
        if len(line) < 4:
            continue
        state, raw = line[:2], line[3:]
        # Porcelain may quote unusual paths. All current repository paths are
        # ordinary UTF-8 paths; retain quotes only if Git emitted them rather
        # than guessing an unsafe unescape.
        path = raw.split(" -> ")[-1].replace("\\", "/")
        states[path] = state
    return states


def classify(path: str) -> str:
    lowered = path.lower()
    name = Path(lowered).name
    if name in LOCAL_UNSAFE_NAMES or name.startswith(".env.") and not name.endswith(".example"):
        return "unsafe_local"
    if any(marker in f"/{lowered}" for marker in TEST_MARKERS):
        return "tests"
    if lowered.startswith(DOC_PREFIXES):
        return "documentation_evidence"
    if lowered.startswith(GENERATED_PREFIXES) or lowered.endswith(GENERATED_SUFFIXES):
        return "generated_binary_or_evidence"
    if lowered.startswith(SOURCE_PREFIXES) or lowered in {
        ".env.cloud.example",
        ".gitattributes",
        ".gitignore",
        "docker-compose.local-dev.yml",
        "docker-compose.medcoder.yml",
        "readme.md",
        "version",
    }:
        return "product_source"
    return "needs_review"


def build(root: Path, output: Path) -> dict[str, Any]:
    states = changed_paths(root)
    output_rel = output.resolve().relative_to(root.resolve()).as_posix()
    states.pop(output_rel, None)
    entries: list[dict[str, Any]] = []
    for rel, state in sorted(states.items()):
        path = root / rel
        entry: dict[str, Any] = {
            "path": rel,
            "git_state": state,
            "bucket": classify(rel),
        }
        if path.is_file():
            entry.update(size_bytes=path.stat().st_size, sha256=sha256(path))
        elif not path.exists():
            entry["deleted"] = True
        else:
            entry["non_file"] = True
        entries.append(entry)

    buckets = Counter(item["bucket"] for item in entries)
    states_count = Counter(item["git_state"] for item in entries)
    return {
        "schema_version": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repository": {
            "head": git(root, "rev-parse", "HEAD").strip(),
            "branch": git(root, "branch", "--show-current").strip(),
            "tree_state": "dirty" if entries else "clean",
        },
        "policy": {
            "purpose": "content-address the current development tree before safe commit splitting",
            "mutates_git": False,
            "publication_performed": False,
            "output_excluded_from_snapshot": output_rel,
            "immutable_baseline_requires_clean_commit": True,
        },
        "summary": {
            "changed_paths": len(entries),
            "by_bucket": dict(sorted(buckets.items())),
            "by_git_state": dict(sorted(states_count.items())),
        },
        "entries": entries,
    }


def comparable(manifest: dict[str, Any]) -> dict[str, Any]:
    value = json.loads(json.dumps(manifest))
    value.pop("generated_at", None)
    # The manifest records the commit from which it was generated, but
    # committing the manifest necessarily advances HEAD.  Comparing that
    # field would make a sealed manifest fail forever by self-reference.
    # Tree state and every non-output changed path remain strict.
    value.get("repository", {}).pop("head", None)
    return value


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify", type=Path, help="Fail if the current tree differs from this manifest")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    try:
        current = build(root, output)
        if args.verify:
            verify_path = args.verify if args.verify.is_absolute() else root / args.verify
            expected = json.loads(verify_path.read_text(encoding="utf-8"))
            if comparable(current) != comparable(expected):
                print("DEVELOPMENT_BASELINE_DRIFTED", file=sys.stderr)
                return 1
            print(f"DEVELOPMENT_BASELINE_VERIFIED paths={current['summary']['changed_paths']}")
            return 0
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (BaselineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"DEVELOPMENT_BASELINE_INVALID: {exc}", file=sys.stderr)
        return 2
    print(
        "DEVELOPMENT_BASELINE_WRITTEN "
        f"paths={current['summary']['changed_paths']} output={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
