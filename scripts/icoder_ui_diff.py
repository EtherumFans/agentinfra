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
import os
import re
import subprocess
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

SCHEMA_VERSION_SUPPORTED = {1, 2}

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
    if spec.get("schema_version") not in SCHEMA_VERSION_SUPPORTED:
        raise CheckError(
            f"unsupported schema_version: {spec.get('schema_version')} "
            f"(this tool supports {sorted(SCHEMA_VERSION_SUPPORTED)})"
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


def _run_check(check: dict[str, Any], repo_root: Path, feature: str = "unknown", spec_version: int = 2) -> tuple[bool, list[str]]:
    """Dispatch a check to its registered runners."""
    static = check.get("static")
    runtime = check.get("runtime")
    if not static and not runtime:
        return False, ["check has neither 'static' nor 'runtime'"]

    # Inject feature/version for the runtime runner to use.
    check_with_ctx = {**check, "_feature": feature, "_spec_version": spec_version}

    failures: list[str] = []
    if static:
        ok, static_failures = _run_static_check(check, repo_root)
        failures.extend(static_failures)
    if runtime:
        # Non-empty runtime: dispatch to the runtime runner. schema_version 2+
        # is required (v1 specs treat this as a future-cycle error so the gap
        # is visible).
        if spec_version < 2:
            failures.append(
                "runtime check requires schema_version >= 2 "
                "(this spec is v{0}); bump the spec to add runtime checks".format(spec_version)
            )
        elif runtime.get("_deferred"):
            # A check can ship a static gate now and a runtime gate later.
            # Mark the runtime as deferred (NOT a failure) so the cycle can
            # close on the static side and the gap stays visible in the report.
            deferred_reason = runtime["_deferred"]
            print(f"       {Fore.YELLOW}[deferred-runtime]{Style.RESET_ALL} {deferred_reason}")
        else:
            ok, runtime_failures = _run_runtime_check(check_with_ctx, repo_root)
            failures.extend(runtime_failures)

    return (len(failures) == 0), failures


# ===========================================================================
# Runtime runner — Playwright (cycle 20+)
# ===========================================================================

# Step actions supported in cycle 20. Keep this list flat; if a future check
# needs more verbs, add them here and extend _STEP_DSL below.
SUPPORTED_STEP_ACTIONS = {"goto", "wait_for", "fill", "click", "expect_text", "expect_count"}

# Generated spec dir — gitignored so generated .spec.ts files don't pollute
# the repo. Picked up by the existing 'e2e' project's testMatch pattern
# (playwright.config.ts: testMatch /.*\\.spec\\.ts/).
GENERATED_SPEC_DIR = REPO_ROOT / "frontend" / "tests" / "e2e" / "_runtime"

# Marker used to find the generated test by title in the JSON reporter.
# Cycle-20+ should keep this stable so reporters can match tests across runs.
# Must be regex-safe — passed to playwright --grep which is a regex match.
RUNTIME_TEST_TITLE_PREFIX = "ui_diff_runtime::"


def _step_to_ts(step: dict[str, Any], indent: str = "    ") -> str:
    """Translate a single runtime.steps[] entry to a Playwright TS expression.

    Returns the expression body (without the leading ``await`` or trailing
    semicolon). The caller wraps it in ``await`` + ``;``.
    """
    action = step.get("action")
    if action not in SUPPORTED_STEP_ACTIONS:
        raise CheckError(f"unsupported runtime step action: {action!r}")

    sel = step.get("selector")
    if action not in ("goto",) and not sel:
        raise CheckError(f"runtime step {action!r} requires 'selector'")

    if action == "goto":
        url = step["url"]
        return f"await page.goto(baseURL + {json.dumps(url)})"
    if action == "wait_for":
        timeout = step.get("timeout_ms", 10000)
        state = step.get("state", "visible")
        return (
            f"await page.waitForSelector({json.dumps(sel)}, "
            f"{{ state: {json.dumps(state)}, timeout: {timeout} }})"
        )
    if action == "fill":
        val = step["value"]
        return f"await page.fill({json.dumps(sel)}, {json.dumps(val)})"
    if action == "click":
        return f"await page.click({json.dumps(sel)})"
    if action == "expect_text":
        loc = f"page.locator({json.dumps(sel)})"
        if "contains" in step:
            needle = step["contains"]
            return f"await expect({loc}).toContainText({json.dumps(needle)})"
        if "equals" in step:
            needle = step["equals"]
            return f"await expect({loc}).toHaveText({json.dumps(needle)})"
        raise CheckError("expect_text requires 'contains' or 'equals'")
    if action == "expect_count":
        loc = f"page.locator({json.dumps(sel)})"
        if "min" in step:
            n = int(step["min"])
            # Use expect.poll-style approach via a helper to keep generated code clean.
            return f"expect((await {loc}.count()) >= {n}).toBeTruthy()"
        if "max" in step:
            n = int(step["max"])
            return f"expect((await {loc}.count()) <= {n}).toBeTruthy()"
        if "equals" in step:
            n = int(step["equals"])
            return f"await expect({loc}).toHaveCount({n})"
        raise CheckError("expect_count requires 'min', 'max', or 'equals'")

    # Unreachable.
    raise CheckError(f"unhandled action: {action}")


def _generate_spec(check: dict[str, Any], feature: str) -> str:
    """Build the .spec.ts file body for a runtime check.

    Returns the file contents as a string. Caller writes to disk.
    """
    runtime = check["runtime"]
    cid = check["id"]
    test_name = runtime.get("test_name", cid)
    steps = runtime.get("steps", [])
    if not steps:
        raise CheckError(f"runtime check {cid!r} has empty steps[]")

    lines: list[str] = []
    lines.append("/**")
    lines.append(f" * AUTO-GENERATED by scripts/icoder_ui_diff.py")
    lines.append(f" * feature: {feature}")
    lines.append(f" * check:   {cid}")
    lines.append(f" * source:  corti_ui_contracts/{feature}.json")
    lines.append(" * DO NOT EDIT — will be overwritten on next toolchain run.")
    lines.append(" */")
    lines.append("import { test, expect } from '@playwright/test';")
    lines.append("")
    lines.append(f"test.describe('{RUNTIME_TEST_TITLE_PREFIX}{cid}', () => {{")
    lines.append(f"  test.use({{ storageState: 'tests/e2e/.auth.json' }});")
    lines.append("")
    # Optional per-test timeout (ms). Default = playwright.config.ts (60s).
    # Some checks (e.g. waiting for a real LLM call to finish) need more.
    test_timeout_ms = runtime.get("test_timeout_ms")
    if test_timeout_ms:
        lines.append(f"  test.setTimeout({int(test_timeout_ms)});")
    lines.append(f"  test({json.dumps(test_name)}, async ({{ page }}, testInfo) => {{")
    lines.append(f"    const baseURL = testInfo.project.use.baseURL || 'http://localhost:3000';")
    lines.append("")
    for i, step in enumerate(steps):
        try:
            expr = _step_to_ts(step)
        except CheckError as e:
            raise CheckError(f"step[{i}] in check {cid!r}: {e}")
        lines.append(f"    // step[{i}]: {step.get('action')}")
        lines.append(f"    {expr};")
        lines.append("")
    lines.append("  });")
    lines.append("});")
    lines.append("")
    return "\n".join(lines)


def _run_runtime_check(check: dict[str, Any], repo_root: Path) -> tuple[bool, list[str]]:
    """Execute a Playwright runtime check by generating a spec and shelling
    ``npx playwright test``. Returns (passed, list_of_failure_lines).

    Prerequisites (out of scope to auto-start in cycle 20):
      * Backend on :8000 (uvicorn)
      * Vite dev server on :3000 (``npm run dev``)
      * ``frontend/tests/e2e/.auth.json`` exists (run ``npx playwright test
        --project=setup`` once)
    """
    runtime = check.get("runtime") or {}
    if runtime.get("kind") != "playwright":
        return False, [f"unsupported runtime.kind: {runtime.get('kind')!r} (only 'playwright' is supported)"]

    feature = check.get("_feature", "unknown")
    cid = check["id"]
    failures: list[str] = []

    # 1. Generate the spec file
    GENERATED_SPEC_DIR.mkdir(parents=True, exist_ok=True)
    spec_file = GENERATED_SPEC_DIR / f"_generated.{cid}.spec.ts"
    try:
        spec_body = _generate_spec(check, feature)
        spec_file.write_text(spec_body, encoding="utf-8")
    except CheckError as e:
        return False, [f"spec generation failed: {e}"]

    # 2. Run Playwright with the JSON reporter so we can map failures back
    #    to test titles (the cycle-19 'print → eyeball' pattern doesn't scale).
    frontend_dir = repo_root / "frontend"
    if not (frontend_dir / "node_modules").exists():
        failures.append(
            "frontend/node_modules missing — run `npm install` in frontend/ first"
        )
        return False, failures

    # On Windows, subprocess.run(['npx', ...]) fails with WinError 2 because
    # npx is a .cmd shim that needs shell=True. We side-step the issue by
    # invoking the local node_modules/.bin/playwright binary directly — same
    # behavior, no shell, no PATH dance.
    #
    # We pin `--project=e2e` to skip the auth.setup.ts project: rate-limited
    # /api/auth/login would 429 after a few rapid cycles, but the storageState
    # file (tests/e2e/.auth.json) is still valid — the e2e project reuses it.
    if sys.platform == "win32":
        playwright_bin = frontend_dir / "node_modules" / ".bin" / "playwright.cmd"
        # Use as_posix() — on Windows, str(WindowsPath) emits backslashes which
        # the .cmd shim mangles. Forward slashes work for every Playwright flag.
        cmd = [
            str(playwright_bin),
            "test",
            "--reporter=json",
            "--project=e2e",
            "--grep", f"{RUNTIME_TEST_TITLE_PREFIX}{cid}",
            spec_file.relative_to(frontend_dir).as_posix(),
        ]
        shell = False
    else:
        cmd = [
            "npx", "playwright", "test",
            "--reporter=json",
            "--project=e2e",
            "--grep", f"{RUNTIME_TEST_TITLE_PREFIX}{cid}",
            spec_file.relative_to(frontend_dir).as_posix(),
        ]
        shell = False

    print(f"       {Fore.CYAN}$ {' '.join(cmd)}{Style.RESET_ALL}")

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(frontend_dir),
            capture_output=True,
            text=True,
            timeout=180,
            env=os.environ.copy(),
            shell=shell,
        )
    except subprocess.TimeoutExpired:
        failures.append("playwright run timed out after 180s")
        return False, failures
    except FileNotFoundError as e:
        failures.append(f"playwright not runnable: {e}")
        return False, failures
    finally:
        # Best-effort cleanup — even on error, don't leave generated specs lying around.
        try:
            spec_file.unlink(missing_ok=True)
        except Exception:
            pass

    # 3. Parse JSON reporter. Playwright writes ONE JSON object on stdout when
    #    --reporter=json is set — but it's pretty-printed across multiple lines,
    #    not one-object-per-line as the docs imply. json.loads the whole thing.
    stdout = (proc.stdout or "").strip()
    if not stdout:
        tail = "\n".join((proc.stderr or "").splitlines()[-15:])
        failures.append(
            f"playwright produced empty stdout (exit={proc.returncode})\n{tail}"
        )
        return False, failures

    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as e:
        # Save raw output for debugging
        debug_path = repo_root / "frontend" / "tests" / "e2e" / "_runtime" / f"_last_report_{cid}.json"
        try:
            debug_path.parent.mkdir(parents=True, exist_ok=True)
            debug_path.write_text(stdout, encoding="utf-8")
            debug_hint = f"\nraw stdout saved to {debug_path.relative_to(repo_root)}"
        except Exception:
            debug_hint = ""
        failures.append(f"JSON reporter parse error: {e}{debug_hint}")
        return False, failures

    stats = report.get("stats", {}) or {}
    expected = stats.get("expected", 0)
    unexpected = stats.get("unexpected", 0)
    skipped = stats.get("skipped", 0)
    failed_count = unexpected

    # expected + skipped counts as "passed" (skipped tests are intentional)
    if expected >= 1 and failed_count == 0:
        return True, []

    # Walk the suites tree to find the first error message. Playwright's JSON
    # reporter uses `specs` as a LIST of spec dicts (each with `tests`), and
    # `suites` as a LIST of child suite dicts. Be defensive — production JSON
    # has these as lists, but types are not formally guaranteed.
    err_msgs: list[str] = []
    def _walk(node: dict[str, Any]) -> None:
        for s in (node.get("specs") or []):
            if not isinstance(s, dict):
                continue
            for t in (s.get("tests") or []):
                for r in (t.get("results") or []):
                    err = r.get("error") or {}
                    msg = err.get("message") or ""
                    if msg:
                        err_msgs.extend(msg.splitlines())
        for child in (node.get("suites") or []):
            if isinstance(child, dict):
                _walk(child)
    for suite in (report.get("suites") or []):
        if isinstance(suite, dict):
            _walk(suite)

    if expected == 0 and failed_count == 0:
        # Playwright exited 1 but no tests were collected — likely grep miss or
        # spec file missing. Show stderr for diagnostics.
        tail = "\n".join((proc.stderr or "").splitlines()[-20:])
        failures.append(f"no tests collected (grep miss?). stderr:\n{tail}")
        return False, failures

    if not err_msgs:
        err_msgs = [f"playwright exit={proc.returncode}, expected={expected}, failed={failed_count}"]
    failures.extend(err_msgs[:5])
    return False, failures


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

    spec_version = int(spec.get("schema_version", 1))
    print(f"{Fore.CYAN}[ui-diff] feature={feature}  checks={len(checks)}  schema_version={spec_version}")

    results: list[tuple[dict[str, Any], bool, list[str]]] = []
    for check in checks:
        ok, failures = _run_check(check, REPO_ROOT, feature=feature, spec_version=spec_version)
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
