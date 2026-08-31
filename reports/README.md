# Reports directory

`reports/` stores reviewable evidence, not general program output.

## Stable sections

- `development-baseline/` — content-addressed working-tree freezes.
- `release-candidate/` — evidence bound to a release candidate.
- `comprehensive-audit/` — canonical historical audit packages.
- `deployment/`, `security/`, `sdk/`, `agent_hub/` — capability-specific evidence.
- `phase-*`, `track_h/` — historical phase evidence retained for traceability.

## Evidence lifecycle

1. A producer writes intermediate data to an ignored temporary directory.
2. The producer reduces it to a compact aggregate report.
3. The aggregate report records source revision, configuration, limitations and hashes.
4. Only evidence referenced by a final summary is retained in the source baseline.
5. Large raw runs are uploaded as CI/release artifacts or stored in governed object storage.

Do not create `test-temp`, `_debug_*`, anonymous timestamps without a summary, screenshots at repository root, or raw patient/provider payloads here.
