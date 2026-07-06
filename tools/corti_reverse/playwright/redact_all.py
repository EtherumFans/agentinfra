"""
Batch redaction runner for Phase 3-B1.5 Section C artifacts.

Runs redact_har.py over all HARs in artifacts/corti_reverse/hars/
and over all PNGs in artifacts/corti_reverse/screenshots/, producing
.redacted.har / OCR-masked PNG alongside each input.

Usage:
    python tools/corti_reverse/playwright/redact_all.py
    python tools/corti_reverse/playwright/redact_all.py --skip-images
    python tools/corti_reverse/playwright/redact_all.py --skip-hars
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts" / "corti_reverse"
HARS_DIR = ARTIFACTS / "hars"
SCREENSHOTS_DIR = ARTIFACTS / "screenshots"
REDACT_SCRIPT = Path(__file__).resolve().parents[0].parent / "har_analyzer" / "redact_har.py"


def redact_hars() -> int:
    if not HARS_DIR.exists():
        print(f"HARs dir not found: {HARS_DIR}")
        return 0
    hars = sorted(HARS_DIR.glob("C-*.har"))
    hars = [h for h in hars if ".redacted." not in h.name]
    if not hars:
        print("No C-*.har files to redact.")
        return 0
    print(f"Redacting {len(hars)} HAR file(s)...")
    failures = 0
    for har in hars:
        out = har.with_suffix(".har").parent / f"{har.stem}.redacted.har"
        print(f"  {har.name} -> {out.name}")
        rc = subprocess.call([
            sys.executable, str(REDACT_SCRIPT),
            "--input", str(har),
            "--output", str(out),
        ])
        if rc != 0 and rc != 1:
            # rc=1 means redactions were applied (CI signal); treat as success.
            # Other non-zero codes are real failures.
            print(f"    FAILED (rc={rc})")
            failures += 1
    return failures


def redact_images() -> int:
    if not SCREENSHOTS_DIR.exists():
        print(f"Screenshots dir not found: {SCREENSHOTS_DIR}")
        return 0
    pngs = sorted(SCREENSHOTS_DIR.glob("C-*.png"))
    if not pngs:
        print("No C-*.png files to redact.")
        return 0
    print(f"Redacting {len(pngs)} image file(s)...")
    failures = 0
    for png in pngs:
        # OCR image-mode redaction modifies in place (copies to output then masks).
        print(f"  {png.name}")
        rc = subprocess.call([
            sys.executable, str(REDACT_SCRIPT),
            "--input", str(png),
            "--output", str(png),
            "--image-mode",
        ])
        if rc != 0 and rc != 1:
            print(f"    FAILED (rc={rc})")
            failures += 1
    return failures


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--skip-images", action="store_true")
    p.add_argument("--skip-hars", action="store_true")
    args = p.parse_args()

    total_failures = 0
    if not args.skip_hars:
        total_failures += redact_hars()
    if not args.skip_images:
        total_failures += redact_images()

    if total_failures:
        print(f"\n{total_failures} file(s) failed redaction.")
        return 1
    print("\nAll redactions complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
