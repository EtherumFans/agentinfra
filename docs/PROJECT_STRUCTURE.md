# Project structure

This document is the canonical ownership map for the repository. New files should go to the narrowest matching directory; generated runtime output must not be placed at the repository root.

## Product and integration code

| Path | Purpose | Source of truth |
|---|---|---|
| `backend/` | FastAPI service, runtime, Agent packs, migrations and backend tests | Yes |
| `frontend/` | React/TypeScript application and browser tests | Yes |
| `packages/` | JavaScript, Python, .NET and web integration SDKs | Yes |
| `web-components/` | Legacy/top-level embedded component compatibility surface | Transitional |
| `examples/` | Maintained integration examples and partner reference applications | Yes |
| `phase7-external-consumer/` | External-consumer compatibility harness | Test fixture |
| `deploy/` | Hosted deployment definitions | Yes |
| `postman/` | API collections | Yes |

## Tests and governed assets

| Path | Purpose | Rule |
|---|---|---|
| `tests/` | Repository-level release, audit and cross-component tests | Commit source/fixtures only |
| `fixtures/` | Cross-component deterministic fixtures | No secrets or live PHI |
| `backend/tests/` | Backend unit, integration, regression and E2E tests | Keep beside backend |
| `backend/data/` | Versioned dictionaries and governed model metadata | Large rebuildable binaries stay ignored |
| `golden_captures/` | Minimal canonical golden response set | Do not store ad-hoc runs |

## Documentation and evidence

| Path | Purpose | Rule |
|---|---|---|
| `docs/` | Product, architecture, operations and phase summaries | Human-readable source of truth |
| `docs-site/` | Documentation site implementation | Generated site output ignored |
| `reports/development-baseline/` | Current baseline manifest and freeze report | One dated baseline per freeze |
| `reports/comprehensive-audit/` | Canonical audit packages | Immutable historical record |
| `reports/release-candidate/` | Release-candidate evidence | Must bind to a commit/hash |
| `reports/<capability>/` | Compact, named capability evidence | No anonymous temp output |
| `outputs/` | Historical tracked capture packages | Legacy; no new output here |
| `archive/` | Superseded implementation retained for reference | Not part of current runtime |

## Tooling

| Path | Purpose |
|---|---|
| `.github/workflows/` | CI and release gates |
| `scripts/release/` | Reproducible release/baseline commands |
| `scripts/audit/` | Audit builders and semantic validators |
| `scripts/` | Maintained operational/development scripts |
| `tools/` | Supporting developer utilities |
| `scripts_rv7/` | Legacy single-purpose audit helper; migrate into `scripts/audit/` when touched |

## Local state — never a release source

The following may exist locally but are not part of a trustworthy source baseline:

- `.claude/`, `.gstack/`, `.icoder/`;
- root `data/` databases and local MedCodER cache;
- `node_modules/`, `dist/`, Playwright output and browser profiles;
- `.env` variants other than committed `.example` templates;
- root screenshots, XML, logs and temporary node-id lists.

`.icoder/` and root `data/` can contain recoverable user/runtime state. Do not delete them through generic cleanup; inspect, migrate or back them up explicitly.

## Placement rules

1. Repository root contains only entry documentation, configuration and top-level modules.
2. Tests belong to their owning component unless they validate the repository/release as a whole.
3. Every generated report has a stable producer script and a dated/versioned output directory.
4. Intermediate runs go to an ignored temporary directory, not `reports/`.
5. A final report should reference the smallest evidence set needed to reproduce its claim.
6. Build artifacts are generated in CI and attached to a release; they are not committed with source.
7. Secrets, tokens, signed URLs and raw PHI are forbidden everywhere in the repository.
