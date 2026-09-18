#!/usr/bin/env python3
"""Fail a commit when staged changes introduce obvious secrets.

Lightweight pre-commit guard. Conservative by design: flags JWT-shaped strings
and high-signal token/secret/key assignments with literal (quoted) values, and
skips documentation/example fixtures expected to describe fields without
carrying real values.

Usage:
  python scripts/audit/guard_secrets.py             # scan staged files
  python scripts/audit/guard_secrets.py --paths <f> [<f> ...]
  python scripts/audit/guard_secrets.py --all       # audit all tracked files
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

JWT = re.compile(
    rb"eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
)
SECRET_ASSIGNMENT = re.compile(
    rb"(?i)\b(access[_-]?token|refresh[_-]?token|client[_-]?secret"
    rb"|api[_-]?key|private[_-]?key|secret[_-]?key|password)"
    rb"\s*[:=]\s*[\"'][A-Za-z0-9_\-+/=.]{20,}[\"']"
)
PLACEHOLDER = re.compile(
    rb"(example|placeholder|changeme|dummy|your[_-]|xxxx|\.\.\.|<[^>]+>"
    rb"|\$\{|%s\b|ENV\[)", re.IGNORECASE
)
EXEMPT_SUFFIXES = {".md", ".rst", ".txt", ".csv", ".example"}
EXEMPT_DIRS = {"tests", "fixtures", "examples", "reports", "docs"}


def git(*args: str) -> list[str]:
    out = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    return out.stdout.splitlines()


def staged_paths() -> list[str]:
    return [
        p for p in git("diff", "--cached", "--name-only", "--diff-filter=ACM")
        if p
    ]


def tracked_paths() -> list[str]:
    return [p for p in git("ls-files") if p]


def is_exempt(path: str) -> bool:
    p = Path(path)
    if p.suffix.lower() in EXEMPT_SUFFIXES:
        return True
    parts = set(p.parts[:-1])
    return bool(parts & EXEMPT_DIRS)


def scan(paths: list[str]) -> list[str]:
    hits: list[str] = []
    for path in paths:
        if is_exempt(path):
            continue
        p = ROOT / path
        if not p.is_file():
            continue
        try:
            with open(p, "rb") as fh:
                head = fh.read(4096)
                if b"\x00" in head:
                    continue
                data = head + fh.read()
        except OSError:
            continue
        for lineno, raw in enumerate(data.splitlines(), 1):
            for pat in (JWT, SECRET_ASSIGNMENT):
                m = pat.search(raw)
                if m and not PLACEHOLDER.search(raw):
                    hits.append(f"{path}:{lineno}: {pat.pattern[:24]}")
                    break
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paths", nargs="*")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    if args.paths:
        paths = args.paths
    elif args.all:
        paths = tracked_paths()
    else:
        paths = staged_paths()

    hits = scan(paths)
    if hits:
        print("secret-scan: potential secrets found; commit blocked")
        for h in hits[:50]:
            print(f"  {h}")
        print("If this is a false positive, review the line and add an "
              "allowlist entry; do not commit real tokens.")
        return 1
    print(f"secret-scan: clean ({len(paths)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
