"""Compute SHA-256 manifest for A1B-AE.1 Corti evidence files."""
import hashlib
import json
import os

evidence_root = "reports/phase-a1b/evidence/corti_observation"
manifest = {
    "charter": "A1B-AE.1",
    "captured_at": "2026-07-22T05:20:00Z",
    "evidence_root": evidence_root,
    "algorithm": "sha256",
    "files": [],
}
total = 0
for dirpath, dirs, files in sorted(os.walk(evidence_root)):
    for f in sorted(files):
        full = os.path.join(dirpath, f)
        rel = full.replace(os.sep, "/")
        with open(full, "rb") as fh:
            h = hashlib.sha256(fh.read()).hexdigest()
        size = os.path.getsize(full)
        manifest["files"].append({"path": rel, "sha256": h, "size": size})
        total += size
manifest["total_files"] = len(manifest["files"])
manifest["total_bytes"] = total
out_path = os.path.join(evidence_root, "sha256_manifest.json")
with open(out_path, "w", encoding="utf-8") as out:
    json.dump(manifest, out, indent=2, ensure_ascii=False)
print(f"wrote {out_path} with {manifest['total_files']} files, {total} bytes")
