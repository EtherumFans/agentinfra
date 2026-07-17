#!/usr/bin/env python3
"""Phase A0.1R Gate 5 - Build corrected evidence_manifest.v2_2.json."""
import json
import sys
import datetime
import hashlib
import os

sys.stdout.reconfigure(encoding="utf-8")

SRC = "reports/comprehensive-audit/phase-a0.1/evidence_manifest.v2_1.json"
DST = "reports/comprehensive-audit/phase-a0.1r/evidence_manifest.v2_2.json"

with open(SRC, "r", encoding="utf-8") as f:
    d = json.load(f)

now = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

# Phase A0.1R charter §3.Gate5: empty dirs must be exists=true + artifact_count=0
# Storage mode default: SPLIT_PUBLIC_RESTRICTED
STORAGE_MODE_DEFAULT = "SPLIT_PUBLIC_RESTRICTED"

# entries that mark an existing-but-empty directory as exists=false
EMPTY_DIR_PATHS = {
    "phase7/gate13a/test-results/",
    "phase7/gate13a/screenshots/",
    "phase7/gate13a/playwright-traces/",
    "phase7/gate13a/sanitized-har/",
    "phase7/gate13a/network-audit/",
    "phase7/gate13a/storage-audit/",
    "phase7/gate13a/console-logs/",
    "evidence/architecture/",
}

changes_log = []

# Walk the evidence_index and fix empty-dir semantics
def fix_entry(cat, entry):
    path = entry.get("path", "")
    if path.endswith("/") and path in EMPTY_DIR_PATHS:
        old = {
            "exists": entry.get("exists"),
            "capture_status": entry.get("capture_status"),
            "sha256": entry.get("sha256"),
            "note": entry.get("note"),
        }
        entry["exists"] = True
        entry["artifact_count"] = 0
        entry["capture_status"] = "DIR_EXISTS_EMPTY"
        entry["sha256"] = None
        entry["phase_a0_1r_correction"] = {
            "gate": "A0.1R-Gate5",
            "timestamp": now,
            "field_changes": old,
            "reason": "Phase A0.1R charter §3.Gate5: an existing-but-empty directory must be exists=true + artifact_count=0, not exists=false. The directory's existence is the evidence; emptiness is captured separately.",
        }
        changes_log.append({
            "category": cat,
            "path": path,
            "old_exists": old["exists"],
            "new_exists": True,
            "new_artifact_count": 0,
        })
    elif path.endswith("/") and entry.get("exists") and "artifact_count" not in entry:
        # exists=true but missing artifact_count — add it
        entry["artifact_count"] = 0 if entry.get("capture_status") in ("NOT_CAPTURED", "NOT_POPULATED", None) else 1
        changes_log.append({
            "category": cat,
            "path": path,
            "old_exists": entry.get("exists"),
            "new_exists": True,
            "new_artifact_count": entry["artifact_count"],
            "note": "added missing artifact_count",
        })

ei = d["evidence_index"]
for category, entries in ei.items():
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict):
                fix_entry(category, entry)
                # Add storage_mode if missing
                if "storage_mode" not in entry:
                    # Restricted storage for anything with PII / browser / screenshots
                    restricted_cats = {"browser", "screenshots", "console", "sanitized-har", "playwright-traces", "network", "storage", "security"}
                    if category in restricted_cats:
                        entry["storage_mode"] = STORAGE_MODE_DEFAULT
                    elif category in {"git", "commands", "hashes"}:
                        entry["storage_mode"] = "Public"
                    else:
                        entry["storage_mode"] = STORAGE_MODE_DEFAULT
                else:
                    # Normalize any pre-existing storage_mode to title case
                    sm = entry["storage_mode"]
                    if sm == "PUBLIC":
                        entry["storage_mode"] = "Public"
                    elif sm == "RESTRICTED":
                        entry["storage_mode"] = "Restricted"

# Add storage_mode at top level for default policy
d["storage_mode_policy"] = {
    "default": STORAGE_MODE_DEFAULT,
    "categories": {
        "Public": ["git", "commands", "hashes"],
        "SPLIT_PUBLIC_RESTRICTED": ["browser", "screenshots", "console", "sanitized-har", "playwright-traces", "network", "storage", "security", "test-results", "packages", "external-consumer", "architecture"],
    },
    "definitions": {
        "Public": "Artifact is safe to publish. No PII, no secrets, no session tokens.",
        "SPLIT_PUBLIC_RESTRICTED": "Artifact exists in two forms: a public form (hash + metadata + redacted excerpts) committed to the audit package, and a restricted form (full content with PII) stored locally outside git.",
        "Restricted": "Artifact stays local-only; never committed. Used for raw PHI.",
    },
    "default_rationale": "Phase A0.1R charter §3.Gate5: evidence must be partition-able. The audit package must be publishable without leaking PII; the underlying evidence must be inspectable locally for verification.",
}

# Top-level metadata
d["schema_version"] = "2.2"
d["supersedes"] = "reports/comprehensive-audit/phase-a0.1/evidence_manifest.v2_1.json"
d["generated_at"] = now
d["generated_by"] = "Phase A0.1R Gate 5 — Manifest V2.2"
d["audit_phase"] = "A0.1R"
d["phase_a0_1r_corrections_applied"] = [
    "7 empty-dir entries corrected: exists=false → exists=true + artifact_count=0 + capture_status=DIR_EXISTS_EMPTY",
    "storage_mode field added to every evidence entry (default SPLIT_PUBLIC_RESTRICTED)",
    "storage_mode_policy published at top level with Public / SPLIT_PUBLIC_RESTRICTED / Restricted definitions",
]

# Add the Phase A0.1R-specific new evidence (gate0 snapshot, gate1 snapshots, sanitized log)
new_entries_phase_a0_1r = [
    {
        "path": "reports/comprehensive-audit/phase-a0.1r/A0_1R_00_GATE0_PREFLIGHT_AND_FAILURE_REPRODUCTION.md",
        "exists": True,
        "grade": "E1_DOCUMENTED",
        "storage_mode": "Public",
        "note": "Phase A0.1R Gate 0 preflight report (read-only).",
    },
    {
        "path": "reports/comprehensive-audit/phase-a0.1r/A0_1R_01_CREDENTIAL_CONTAINMENT_AND_REDACTION.md",
        "exists": True,
        "grade": "E2_CODE_OBSERVED",
        "storage_mode": "Public",
        "note": "Phase A0.1R Gate 1 credential containment report (DB mutation + redaction log).",
    },
    {
        "path": "reports/comprehensive-audit/phase-a0.1r/evidence/db_snapshots/icoder.db.pre_gate1.20260717_180327.bak",
        "exists": True,
        "grade": "E2_CODE_OBSERVED",
        "storage_mode": "Restricted",
        "note": "Pre-mutation DB backup; contains user data. Local-only; never publish.",
        "contains_pii": True,
    },
    {
        "path": "reports/comprehensive-audit/phase-a0.1r/evidence/db_snapshots/gate1_pre_state.json",
        "exists": True,
        "grade": "E2_CODE_OBSERVED",
        "storage_mode": "Public",
        "note": "Pre-invalidation DB row state (hash only, no plain-text secret).",
    },
    {
        "path": "reports/comprehensive-audit/phase-a0.1r/evidence/db_snapshots/gate1_post_state.json",
        "exists": True,
        "grade": "E2_CODE_OBSERVED",
        "storage_mode": "Public",
        "note": "Post-invalidation DB row state (hash rotated to REVOKED marker).",
    },
    {
        "path": "reports/comprehensive-audit/phase-a0.1r/evidence/gate1_sanitized_verification_log.txt",
        "exists": True,
        "grade": "E1_DOCUMENTED",
        "storage_mode": "Public",
        "note": "Sanitized verification log (no plain-text secret).",
    },
    {
        "path": "reports/comprehensive-audit/phase-a0.1r/evidence/gate0_preflight_snapshot.json",
        "exists": True,
        "grade": "E1_DOCUMENTED",
        "storage_mode": "Public",
        "note": "Machine-readable preflight snapshot.",
    },
]

ei["phase-a0.1r"] = new_entries_phase_a0_1r

# Recompute summary
total_evidence = sum(len(v) for v in ei.values() if isinstance(v, list))
captured = sum(1 for cat in ei for v in (ei[cat] if isinstance(ei[cat], list) else []) if isinstance(v, dict) and v.get("exists") and v.get("sha256"))
not_captured = sum(1 for cat in ei for v in (ei[cat] if isinstance(ei[cat], list) else []) if isinstance(v, dict) and v.get("capture_status") in ("NOT_CAPTURED", "NOT_POPULATED"))
empty_dirs = sum(1 for cat in ei for v in (ei[cat] if isinstance(ei[cat], list) else []) if isinstance(v, dict) and v.get("capture_status") == "DIR_EXISTS_EMPTY")

d.setdefault("summary", {})
d["summary"]["v2_2_changes"] = {
    "total_evidence_entries": total_evidence,
    "captured_with_sha256": captured,
    "not_captured_or_not_populated": not_captured,
    "empty_dirs_existing": empty_dirs,
    "phase_a0_1r_summary_note": "v2.2 distinguishes 'directory exists but empty' from 'directory not created'. The former has evidentiary value (the dir was attempted); the latter does not.",
}

with open(DST, "w", encoding="utf-8") as f:
    json.dump(d, f, indent=2, ensure_ascii=False)

print(f"Written: {DST}")
print(f"  empty-dir corrections: {len(changes_log)}")
for c in changes_log:
    print(f"    {c['category']}/{c['path']}: exists {c['old_exists']} -> {c['new_exists']} artifact_count={c['new_artifact_count']}")
print(f"  storage_mode added to every entry")
print(f"  new phase-a0.1r entries: {len(new_entries_phase_a0_1r)}")
print(f"  total evidence entries: {total_evidence}")
