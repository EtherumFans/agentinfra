#!/usr/bin/env python3
"""A1A Gate 0 — Git Object Database Secret Scan.

Scan ALL git objects (loose + packed) for any substring of the compromised
secret that is longer than the 8-char public fingerprint. The 8-char
prefix `862b7cf5` IS public (it appears in audit reports as documentation).
Chars 9+ are NOT public.

Exit 0 if clean. Exit 1 with hit list if any non-public substring is found.
"""
from __future__ import annotations
import subprocess
import sys
import json
import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Substrings to scan. The 8-char prefix is public (audit reports publish it
# as documentation). Chars 9+ are NOT public.
FULL_SECRET = "862b7cf5b001b5b7f285739eee828cf5fb14ea43fc2cdc2b"
NON_PUBLIC_SUBSTRINGS = [
    ("chars_9_16", "b001b5b7"),            # chars 9-16
    ("chars_9_24", "b001b5b7f285739e"),    # chars 9-24
    ("chars_17_24", "f285739e"),           # chars 17-24
    ("chars_25_32", "ee828cf5"),           # chars 25-32
    ("chars_33_40", "fb14ea43"),           # chars 33-40
    ("chars_41_48", "fc2cdc2b"),           # chars 41-48
    ("chars_9_end", "b001b5b7f285739eee828cf5fb14ea43fc2cdc2b"),  # everything after 8-char prefix
    ("full_secret", FULL_SECRET),
]


def get_all_blobs() -> list[str]:
    """Return list of all blob SHA-1s in the object database (loose + packed)."""
    result = subprocess.run(
        ["git", "cat-file", "--batch-all-objects", "--batch-check"],
        cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    blobs = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "blob":
            blobs.append(parts[0])
    return blobs


def read_blob(sha: str) -> bytes:
    result = subprocess.run(
        ["git", "cat-file", "-p", sha],
        cwd=REPO_ROOT, capture_output=True,
    )
    return result.stdout


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Scanning all git objects for compromised secret substrings...")
    blobs = get_all_blobs()
    print(f"Total blob objects in database: {len(blobs)}")

    findings = {label: [] for label, _ in NON_PUBLIC_SUBSTRINGS}
    scanned = 0
    for sha in blobs:
        scanned += 1
        if scanned % 500 == 0:
            print(f"  scanned {scanned}/{len(blobs)}")
        try:
            content = read_blob(sha)
        except Exception as e:
            print(f"  WARNING: could not read blob {sha}: {e}")
            continue
        for label, sub in NON_PUBLIC_SUBSTRINGS:
            if sub.encode() in content:
                findings[label].append(sha)

    print(f"\nScan complete. {scanned} blobs scanned.")
    print("\nFindings:")
    total_hits = 0
    for label, subs in findings.items():
        print(f"  {label:<16}: {len(subs)} hits")
        total_hits += len(subs)
        for sha in subs[:5]:
            print(f"      {sha}")

    # Identify which blobs hit each substring (dedupe)
    all_hit_blobs = set()
    for subs in findings.values():
        all_hit_blobs.update(subs)

    # For each hit blob, find its paths (via git rev-list --objects --all)
    blob_paths = {}
    if all_hit_blobs:
        result = subprocess.run(
            ["git", "rev-list", "--all", "--objects"],
            cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        for line in result.stdout.splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and parts[0] in all_hit_blobs:
                blob_paths.setdefault(parts[0], []).append(parts[1])

    # Write JSON report
    report = {
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "scanner": "scripts/audit/a1a_gate0_scan_git_objects.py",
        "scope": "ALL git objects (loose + packed) reachable via cat-file --batch-all-objects",
        "total_blobs_scanned": scanned,
        "public_fingerprint_8char": "862b7cf5",
        "non_public_substrings_scanned": [
            {"label": label, "substring": sub} for label, sub in NON_PUBLIC_SUBSTRINGS
        ],
        "findings_per_substring": {label: len(subs) for label, subs in findings.items()},
        "all_hit_blob_count": len(all_hit_blobs),
        "hit_blob_details": [
            {
                "blob_sha": sha,
                "matched_labels": [label for label, subs in findings.items() if sha in subs],
                "known_paths": blob_paths.get(sha, []),
            }
            for sha in sorted(all_hit_blobs)
        ],
        "verdict": "CLEAN_NO_NON_PUBLIC_SUBSTRING_FOUND" if not all_hit_blobs
                   else "PARTIAL_BLOCKED_BY_SECRET_PRESENT_IN_GIT_OBJECT_DATABASE",
    }

    out_path = REPO_ROOT / "reports" / "phase-a1a" / "git_object_secret_scan.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport written: {out_path}")
    print(f"\nVERDICT: {report['verdict']}")

    sys.exit(0 if not all_hit_blobs else 1)


if __name__ == "__main__":
    main()
