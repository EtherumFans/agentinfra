#!/usr/bin/env python3
"""iCoDer UI contract diff gate (Phase 2 first cycle).

For each check in ``corti_ui_contracts/{feature}.json``:

  1. Run static TSX analysis (grep-based) on ``static.tsx_path``.
  2. Report per-check pass/fail with the missing/extra evidence.
  3. On full pass, write ``corti_ui_contracts/{feature}.VERIFIED_OK``.
  4. On any fail, write ``UI_DIFF.md`` to ``--cycle-dir`` (or stdout).

This is the static-only first version. Future cycles will populate
``checks[].runtime`` with Playwright assertions (the spec format already
reserves that field; see ``schema_version: 1`` in the spec).

Spec format
-----------
    {
      "feature": "medical-coding",
      "schema_version": 1,
      "checks": [
        {
          "id": "real_time_char_counter",
          "description": "Input area has a live char/credit counter",
          "static": {
            "tsx_path": "frontend/src/pages/MedicalCodingPage.tsx",
            "must_contain":    ["onChange", "input.length", "charCount"],
            "must_not_contain": ["// TODO: no char counter"],
            "imported":        ["EvidenceHighlighter"],
            "jsx_used":        ["<EvidenceHighlighter"]
          },
          "runtime": {}
        }
      ]
    }

The four static lists each behave like a set:

  * ``must_contain``    — each pattern MUST appear somewhere in the file
                          (use this for things that prove the feature exists)
  * ``must_not_contain``— each pattern MUST NOT appear (use this for
                          things that prove the OLD behaviour is gone)
  * ``imported``        — each pattern MUST appear on a line that starts
                          with ``import`` (or ``} from``). Use this to
                          prove a dependency is wired.
  * ``jsx_used``        — each pattern MUST appear with a following
                          character that's NOT an identifier char (i.e. it's
                          used as JSX, not just imported). Use this to
                          defeat the "imported but never rendered" trap.

Usage
-----
    python scripts/icoder_ui_diff.py --feature medical-coding
    python scripts/icoder_ui_diff.py --feature medical-coding --cycle-dir docs/phase_cycles/cycle_19_ui_medical_coding
    python scripts/icoder_ui_diff.py --list                # show all features + check counts
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from colorama import Fore, Style, init as colorama_init

# Force UTF-8 stdout/stderr on Windows (GBK can't encode box chars / emojis)
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

colorama_init()

REPO_ROOT = Path(__file__).resolve().parent.parent
CONTRACTS_DIR = REPO_ROOT / "corti_ui_contracts"
DEFAULT_CYCLE_DIR = REPO_ROOT / "docs" / "phase_cycles"

SCHEMA_VERSION_SUPPORTED = 1

# Regex used to detect an import line for the ``imported`` check.
_IMPORT_LINE_RE = re.compile(r"^\s*(?:import|export\s+type|export\s+\*).*?\b(?P<sym>\w+)\b")
_JSX_USE_RE = re.compile(r"<(?P<sym>[A-Za-z]\w*)(?P<after>\W|$)")


class CheckError(Exception):
    pass


def _load_spec(feature: str, contracts_dir: Path) -> dict[str, Any]:
    spec_path = contracts_dir / f"{feature}.json"
    if not spec_path.exists():
        raise CheckError(f"spec not found: {spec_path}")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    if spec.get("schema_version") != SCHEMA_VERSION_SUPPORTED:
        raise CheckError(
            f"unsupported schema_version: {spec.get('schema_version')} "
            f"(this tool supports {SCHEMA_VERSION_SUPPORTED})"
        )
    return spec


def _run_static_check(check: dict[str, Any], repo_root: Path) -> tuple[bool, list[str]]:
    """Return (passed, list_of_failure_lines)."""
    static = check.get("static") or {}
    rel = static.get("tsx_path")
    if not rel:
        return False, ["static.tsx_path missing"]
    path = (repo_root / rel).resolve()
    if not path.exists():
        return False, [f"file not found: {path}"]
    if path.is_dir():
        return False, [f"tsx_path is a directory, expected file: {path}"]
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    failures: list[str] = []

    for needle in static.get("must_contain", []) or []:
        if needle not in text:
            failures.append(f"must_contain NOT FOUND: {needle!r}")

    for needle in static.get("must_not_contain", []) or []:
        if needle in text:
            # Show first occurrence for context
            for i, line in enumerate(lines, 1):
                if needle in line:
                    failures.append(
                        f"must_not_contain FOUND (forbidden): {needle!r}  "
                        f"at {rel}:{i}: {line.strip()[:80]}"
                    )
                    break

    for needle in static.get("imported", []) or []:
        # Match an import line that contains the symbol as a whole word.
        # We allow import X from '...' / } from '...' / export type X = ...
        # but the simplest portable match is: a line that starts with
        # import (or has } from after import) AND contains the symbol.
        found = False
        for line in lines:
            stripped = line.lstrip()
            if not (stripped.startswith("import ") or stripped.startswith("} from") or "from '" in line or 'from "' in line):
                continue
            if re.search(rf"\b{re.escape(needle)}\b", line):
                found = True
                break
        if not found:
            failures.append(f"imported NOT FOUND: {needle!r}")

    for needle in static.get("jsx_used", []) or []:
        # Accept both "Foo" and "<Foo" in the spec — the leading "<" is just
        # visual clarity that it's a JSX tag. Strip it before matching the
        # captured symbol group.
        symbol = needle.lstrip("<")
        if not symbol:
            failures.append(f"jsx_used pattern is empty after stripping '<': {needle!r}")
            continue
        # Match `<Needle` (JSX use) but NOT `import { Needle }` etc.
        # We require the next char to be a non-identifier char.
        found = False
        for m in _JSX_USE_RE.finditer(text):
            if m.group("sym") == symbol:
                # Filter out false positives: an HTML-like tag in a comment
                # or a string. Cheap heuristic: skip if the line is a
                # comment-only line.
                line_start = text.rfind("\n", 0, m.start()) + 1
                line_end = text.find("\n", m.start())
                if line_end == -1:
                    line_end = len(text)
                line = text[line_start:line_end].strip()
                if line.startswith("//") or line.startswith("*") or line.startswith("/*"):
                    continue
                # Filter out TypeScript generics: `<EvidenceHighlighter<...>>`
                # is unusual in JSX but cheap to detect via the trailing
                # `<` after the symbol. We just take the simpler form and
                # require whitespace or `>` to follow the symbol.
                after = m.group("after")
                if after in (" ", ">", "/", "\n", "\r", "\t"):
                    found = True
                    break
        if not found:
            failures.append(f"jsx_used NOT FOUND: {needle!r}")

    return (len(failures) == 0), failures


def _run_check(check: dict[str, Any], repo_root: Path) -> tuple[bool, list[str]]:
    """Dispatch a check to its registered runners.

    Today: only ``static`` is supported. ``runtime`` is reserved for
    future Playwright assertions (cycle 20+).
    """
    static = check.get("static")
    runtime = check.get("runtime")
    if not static and not runtime:
        return False, ["check has neither 'static' nor 'runtime'"]

    failures: list[str] = []
    if static:
        ok, static_failures = _run_static_check(check, repo_root)
        failures.extend(static_failures)
    if runtime:
        # Reserved for future cycles. Treat as an error so the gap is
        # visible — silent skip would hide the fact that we have
        # runtime-only checks with no runner.
        failures.append("runtime check is reserved for future cycles; no runner implemented yet")

    return (len(failures) == 0), failures


def _print_check(check: dict[str, Any], passed: bool, failures: list[str]) -> None:
    cid = check.get("id", "<no id>")
    desc = check.get("description", "")
    if passed:
        print(f"  {Fore.GREEN}[OK]  {Fore.CYAN}{cid}{Style.RESET_ALL}")
        print(f"       {desc}")
    else:
        print(f"  {Fore.RED}[FAIL]{Fore.CYAN} {cid}{Style.RESET_ALL}")
        print(f"       {desc}")
        for f in failures:
            print(f"         {Fore.RED}- {f}{Style.RESET_ALL}")


def write_verified_ok(feature: str, summary: dict[str, Any], contracts_dir: Path) -> Path:
    path = contracts_dir / f"{feature}.VERIFIED_OK"
    path.write_text(
        json.dumps({**summary, "verified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, indent=2),
        encoding="utf-8",
    )
    return path


def write_cycle_report(feature: str, results: list[tuple[dict[str, Any], bool, list[str]]], cycle_dir: Path) -> Path:
    cycle_dir.mkdir(parents=True, exist_ok=True)
    report = cycle_dir / "UI_DIFF.md"
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    lines = [
        f"# UI contract diff - {feature} - {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}",
        "",
        f"**Result: {passed}/{total} checks pass**",
        "",
    ]
    for check, ok, failures in results:
        status = "OK" if ok else "FAIL"
        lines.append(f"- {status} `{check.get('id', '<no id>')}` — {check.get('description', '')}")
        if not ok:
            for f in failures:
                lines.append(f"  - {f}")
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def list_features(contracts_dir: Path) -> int:
    if not contracts_dir.exists():
        print(f"{Fore.RED}[fail] {contracts_dir} not found")
        return 2
    specs = sorted(contracts_dir.glob("*.json"))
    if not specs:
        print(f"{Fore.YELLOW}[note] no specs in {contracts_dir}")
        return 0
    print(f"{Fore.CYAN}UI feature specs in {contracts_dir.name}/")
    for s in specs:
        try:
            data = json.loads(s.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  {Fore.RED}[bad]  {s.name}: {e}")
            continue
        if s.stem.endswith(".VERIFIED_OK"):
            continue
        n_checks = len(data.get("checks", []))
        marker = f"{Fore.GREEN}VERIFIED{Style.RESET_ALL}" if (s.parent / f"{s.stem}.VERIFIED_OK").exists() else f"{Fore.YELLOW}pending{Style.RESET_ALL}"
        print(f"  {marker}  {s.name}  ({n_checks} checks)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="iCoDer UI contract diff gate (static).")
    parser.add_argument("--feature", help="Feature slug (matches corti_ui_contracts/{feature}.json)")
    parser.add_argument("--contracts-dir", type=Path, default=CONTRACTS_DIR, help="Override specs dir")
    parser.add_argument("--cycle-dir", type=Path, help="Phase cycle archive dir for UI_DIFF.md")
    parser.add_argument("--list", action="store_true", help="List known feature specs and exit")
    args = parser.parse_args()

    if args.list:
        return list_features(args.contracts_dir)

    if not args.feature:
        print(f"{Fore.RED}[fail] --feature is required (or use --list)")
        return 2

    try:
        spec = _load_spec(args.feature, args.contracts_dir)
    except CheckError as e:
        print(f"{Fore.RED}[fail] {e}")
        return 2

    feature = spec.get("feature", args.feature)
    checks = spec.get("checks", [])
    if not checks:
        print(f"{Fore.YELLOW}[note] {feature}: no checks defined; nothing to do")
        return 0

    print(f"{Fore.CYAN}[ui-diff] feature={feature}  checks={len(checks)}  schema_version={spec.get('schema_version')}")

    results: list[tuple[dict[str, Any], bool, list[str]]] = []
    for check in checks:
        ok, failures = _run_check(check, REPO_ROOT)
        _print_check(check, ok, failures)
        results.append((check, ok, failures))

    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{Fore.CYAN}{'=' * 60}")
    print(f"{Fore.CYAN}[summary] {passed}/{total} checks pass for {feature}")

    if passed == total:
        ok_path = write_verified_ok(feature, {"feature": feature, "checks_passed": total}, args.contracts_dir)
        print(f"{Fore.GREEN}[OK] wrote {ok_path.relative_to(REPO_ROOT)}")
        if args.cycle_dir:
            cycle_dir = (REPO_ROOT / args.cycle_dir).resolve()
            cycle_dir.mkdir(parents=True, exist_ok=True)
            report = cycle_dir / "REPORT.md"
            report.write_text(
                f"# UI diff — {feature} — {passed}/{total} pass — {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}\n",
                encoding="utf-8",
            )
            print(f"{Fore.GREEN}[report] {report.relative_to(REPO_ROOT)}")
        return 0
    else:
        cycle_dir = (REPO_ROOT / args.cycle_dir).resolve() if args.cycle_dir else DEFAULT_CYCLE_DIR
        report = write_cycle_report(feature, results, cycle_dir)
        print(f"{Fore.RED}[FAIL] wrote {report.relative_to(REPO_ROOT)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
