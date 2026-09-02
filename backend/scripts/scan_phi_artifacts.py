"""Fail-closed plaintext-canary scanner for backups and copied WAL artifacts.

Sentinels are supplied in a JSON file containing an array of strings.  The
scanner searches UTF-8, UTF-16LE and UTF-16BE representations without printing
the sentinel itself.  Use plain pg_dump output (or pg_restore it to plain SQL)
and copied raw WAL/pg_waldump output; opaque compressed archives must first be
expanded into a controlled temporary directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


CHUNK_SIZE = 1024 * 1024


def _files(paths: Iterable[Path]) -> list[Path]:
    result: set[Path] = set()
    for path in paths:
        resolved = path.resolve(strict=True)
        if resolved.is_file():
            result.add(resolved)
        elif resolved.is_dir():
            result.update(item.resolve() for item in resolved.rglob("*") if item.is_file())
        else:
            raise RuntimeError(f"unsupported artifact path: {path}")
    return sorted(result)


def _needles(sentinel_file: Path) -> list[tuple[str, bytes]]:
    raw = json.loads(sentinel_file.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not raw or not all(isinstance(v, str) and v for v in raw):
        raise RuntimeError("sentinel file must contain a non-empty JSON string array")
    needles: list[tuple[str, bytes]] = []
    for value in raw:
        sentinel_id = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        for encoding in ("utf-8", "utf-16le", "utf-16be"):
            encoded = value.encode(encoding)
            if len(encoded) < 6:
                raise RuntimeError("each encoded sentinel must be at least 6 bytes")
            needles.append((f"{sentinel_id}:{encoding}", encoded))
    return needles


def scan(paths: list[Path], sentinel_file: Path) -> dict:
    artifacts = _files(paths)
    needles = _needles(sentinel_file)
    overlap = max(len(value) for _name, value in needles) - 1
    findings: list[dict] = []
    summaries: list[dict] = []
    total_bytes = 0
    for artifact in artifacts:
        digest = hashlib.sha256()
        size = 0
        tail = b""
        seen: set[tuple[str, int]] = set()
        with artifact.open("rb") as handle:
            while chunk := handle.read(CHUNK_SIZE):
                digest.update(chunk)
                window = tail + chunk
                window_start = size - len(tail)
                for sentinel_id, needle in needles:
                    start = 0
                    while True:
                        found = window.find(needle, start)
                        if found < 0:
                            break
                        absolute = window_start + found
                        marker = (sentinel_id, absolute)
                        if marker not in seen:
                            seen.add(marker)
                            findings.append({
                                "artifact": str(artifact),
                                "offset": absolute,
                                "sentinel_id": sentinel_id,
                            })
                        start = found + 1
                size += len(chunk)
                tail = window[-overlap:] if overlap else b""
        total_bytes += size
        summaries.append({
            "artifact": str(artifact), "bytes": size, "sha256": digest.hexdigest(),
        })
    return {
        "schema_version": "icoder.phi-artifact-scan/v1",
        "status": "failed_plaintext_found" if findings else "passed",
        "artifacts": summaries,
        "artifact_count": len(artifacts),
        "bytes_scanned": total_bytes,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--sentinel-file", required=True, type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = scan(args.paths, args.sentinel_file.resolve(strict=True))
    rendered = json.dumps(report, ensure_ascii=False, sort_keys=True)
    if args.report:
        args.report.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 2 if report["finding_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

