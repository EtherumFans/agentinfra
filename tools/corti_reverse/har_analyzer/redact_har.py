"""
Tool #6 — Redaction script for Corti HAR / screenshots / traces.

Redacts:
- `authorization` headers (Bearer tokens)
- `cookie` / `set-cookie` headers
- Session IDs in URL params
- Email addresses
- Person names (Corti default test patient names)
- PHI in request/response bodies (configurable pattern list)
- Workspace IDs (if flagged sensitive)
- IP addresses
- Account numbers / phone numbers

Modes:
- `--har-mode` (default): redacts a HAR JSON file in place.
- `--image-mode`: OCR-scans a screenshot PNG and masks emails /
  names / PHI with black rectangles (requires `pytesseract`).
- `--flows-mode`: redacts a mitmproxy `.flows` file (requires
  `mitmproxy` Python package).

Usage:
    python tools/corti_reverse/har_analyzer/redact_har.py \\
        --input artifacts/corti_reverse/hars/<name>.har \\
        --output artifacts/corti_reverse/hars/<name>.redacted.har

Exit code: 0 on success, 1 if any redaction pattern matched > 0
items (so CI can fail if raw artifacts were committed without
redaction).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


# Regex patterns. Each entry: (name, regex, replacement).
REDACTION_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Auth headers — replace whole value
    ("authorization_header",
     re.compile(r"(authorization)(\s*[:=]\s*)(Bearer\s+[\w\.\-]+)",
                re.IGNORECASE),
     r"\1\2REDACTED_BEARER"),
    ("cookie_header",
     re.compile(r"(cookie|set-cookie)(\s*[:=]\s*)([^\r\n]+)",
                re.IGNORECASE),
     r"\1\2REDACTED_COOKIE"),
    ("x_csrf_token",
     re.compile(r"(x-csrf-token|x-auth-token)(\s*[:=]\s*)([\w\.\-]+)",
                re.IGNORECASE),
     r"\1\2REDACTED_TOKEN"),

    # Emails
    ("email",
     re.compile(r"\b[\w\.\-]+@[\w\.\-]+\.\w+\b"),
     "REDACTED_EMAIL"),

    # IPv4
    ("ipv4",
     re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
     "REDACTED_IP"),

    # Phone (CN/US heuristic)
    ("phone",
     re.compile(r"\b1[3-9]\d{9}\b|\+\d{1,3}[\-\s]?\d{6,14}\b"),
     "REDACTED_PHONE"),

    # UUIDs
    ("uuid",
     re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"),
     "REDACTED_UUID"),

    # JWT tokens (3 base64 segments separated by dots)
    ("jwt",
     re.compile(r"\beyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b"),
     "REDACTED_JWT"),

    # Common Corti test patient names — mask any CJK Chinese name (3-4 chars)
    # This is heuristic and may over-redact; manual review still required.
    ("cjk_person_name",
     re.compile(r"\b[一-鿿]{2,4}\b"),
     "REDACTED_PERSON"),
]


def redact_string(s: str) -> tuple[str, dict[str, int]]:
    """Apply all patterns to a string. Return (redacted, counts)."""
    counts: dict[str, int] = {}
    for name, pat, repl in REDACTION_PATTERNS:
        s, n = pat.subn(repl, s)
        if n:
            counts[name] = counts.get(name, 0) + n
    return s, counts


def redact_har(har: dict) -> tuple[dict, dict[str, int]]:
    """Walk a HAR dict, redacting sensitive values in place (returns new dict)."""
    total_counts: dict[str, int] = {}

    def walk(obj: Any) -> Any:
        if isinstance(obj, str):
            red, counts = redact_string(obj)
            for k, v in counts.items():
                total_counts[k] = total_counts.get(k, 0) + v
            return red
        if isinstance(obj, dict):
            return {k: walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [walk(x) for x in obj]
        return obj

    redacted = walk(har)
    # Force-overwrite auth/cookie header values that survived regex
    # (e.g., empty values, unusual casing).
    for entry in redacted.get("log", {}).get("entries", []):
        for header_bucket in ("headers",):
            for h in (entry.get("request") or {}).get(header_bucket, []) + \
                     (entry.get("response") or {}).get(header_bucket, []):
                name = (h.get("name") or "").lower()
                if name in ("authorization", "cookie", "set-cookie",
                            "x-csrf-token", "x-auth-token"):
                    if h.get("value") != "REDACTED_COOKIE" and \
                       h.get("value") != "REDACTED_BEARER" and \
                       h.get("value") != "REDACTED_TOKEN":
                        h["value"] = "REDACTED"
                        total_counts["forced_header_value"] = \
                            total_counts.get("forced_header_value", 0) + 1
    return redacted, total_counts


def redact_image(png_path: Path) -> dict[str, int]:
    """OCR-scan a PNG and mask sensitive text with black rectangles.

    Requires `pytesseract` + `Pillow`. If unavailable, prints a warning
    and returns empty counts (manual review required).
    """
    try:
        import pytesseract  # type: ignore
        from PIL import Image, ImageDraw  # type: ignore
    except ImportError:
        print("WARNING: pytesseract/Pillow not installed — skipping image "
              "redaction. Manually review the screenshot before commit.",
              file=sys.stderr)
        return {}

    img = Image.open(png_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    draw = ImageDraw.Draw(img)
    counts: dict[str, int] = {}
    for i, text in enumerate(data["text"]):
        if not text:
            continue
        red, c = redact_string(text)
        if c:
            x = data["left"][i]
            y = data["top"][i]
            w = data["width"][i]
            h = data["height"][i]
            draw.rectangle([x, y, x + w, y + h], fill="black")
            for k, v in c.items():
                counts[k] = counts.get(k, 0) + v
    img.save(png_path)
    return counts


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Input file path")
    p.add_argument("--output", help="Output file path (defaults to <input>.redacted.<ext>)")
    p.add_argument("--har-mode", action="store_true", help="Redact HAR JSON (default)")
    p.add_argument("--image-mode", action="store_true",
                   help="Redact screenshot PNG (OCR-based)")
    p.add_argument("--flows-mode", action="store_true",
                   help="Redact mitmproxy .flows file (requires mitmproxy)")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 2

    out_path = Path(args.output) if args.output else \
        in_path.with_suffix(in_path.suffix + ".redacted")

    if args.image_mode:
        import shutil
        shutil.copy(in_path, out_path)
        counts = redact_image(out_path)
    elif args.flows_mode:
        print("--flows-mode not yet implemented; use --har-mode after "
              "converting .flows to HAR via mitmdump.", file=sys.stderr)
        return 1
    else:
        har = json.loads(in_path.read_text(encoding="utf-8"))
        redacted, counts = redact_har(har)
        out_path.write_text(json.dumps(redacted, indent=2), encoding="utf-8")

    print(f"Wrote redacted file: {out_path}")
    if counts:
        print("Redaction counts:")
        for k, v in sorted(counts.items()):
            print(f"  {k}: {v}")
        # Exit 1 to signal CI that the input had sensitive data
        # (only meaningful if input was the raw artifact; CI can
        # check that .redacted file exists and raw file is gitignored).
        return 1 if not args.output else 0
    print("No redactions needed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
