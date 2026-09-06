# Agent Hub live gate

The September 7 mainline run `34045208739` exposed four prerequisites hidden
by the former credential skip: external-provider egress remained disabled;
the 0.5-second HTTP replay exhausted the API's 30/minute IP budget; Registry
projection tried to store Pack expert slugs in VARCHAR(12); and the old real
E2E invoked the obsolete `medcoder-coding-review` provider-backed route.

## Boundaries

- Production still denies external LLM egress by default and retains the
  default rate limit. Only the isolated GitHub live job, using synthetic Pack
  examples and an authorized repository credential, enables DeepSeek egress
  and a 600/minute API budget. Authentication and no-key fail-closed remain on.
- A dedicated preflight verifies the credential's presence (not value), data
  policy, PostgreSQL schema/head/cloud-start agreement, and complete Registry
  synchronization before any model call. A listening OpenAPI endpoint alone
  is not sufficient readiness evidence.
- Revision 076 widens `agents.default_expert_id` to 128 without truncation.
  Downgrade refuses populated identifiers longer than 12. Registry writes
  flush inside savepoints; a failed Pack does not poison later writes, and
  any failed/incomplete synchronization remains unready. Error metadata is
  limited to exception classes rather than SQL parameters or Pack prompts.
- The canonical A2A live E2E uses real HTTP, a self-registered tenant principal,
  `medical-coding-agent`, schema-labelled output, result/trace attestations,
  provider identity, and rejection of mock/degraded results. It runs explicitly
  in the live job with `--noconftest`, outside hermetic TestClient fixtures.
  Ordinary backend E2E does not receive the provider credential. The release
  evidence checker requires the dedicated preflight and A2A steps, so moving
  the test cannot turn an omitted live run into a release pass.
- The existing 26 happy cases, 26 adversarial cases, two-round stability,
  reference semantics and evidence bundle remain blocking and unchanged.
  Model-independent governed Agents do not thereby become real-LLM claims.
- Medical Coding A2A commits a tenant-owned RUNNING record before dispatch,
  retains success/failure traces and finalizes the audit before publishing a
  result. Audit persistence failures withhold results. Console/partner/SSE
  orphan-run and cross-tenant denial rules are unchanged; tests must not seed
  an artificial run record to claim successful A2A trace retrieval.
- Revision 077 widens audit `run_history.runtime_mode` from 48 to 128 for
  full governed-provider identifiers. Downgrade refuses truncation. Live
  preflight checks both expert and runtime identifier widths before calls.
- PHI rotation/rewrap explicitly accept revisions 076/077; unknown future schema
  revisions remain rejected. Human review is required in the signed domain
  result, not assumed from an optional duplicate envelope metadata field.
- Public registration commits the user, organization, membership and audit
  before minting tokens. Dependency cleanup after response transmission is
  not a safe commit boundary for the immediate authenticated Agent request.
  Commit failure rolls back and returns 503 without issuing credentials.

## Local verification

- CI/release evidence contracts: 54 passed.
- Configuration/readiness/A2A negative contracts: 10 passed.
- Registry, preflight and populated migration contracts: 20 passed.
- Agent Hub examples/adversarial/stability/semantic/runtime contracts plus
  backend E2E: 68 passed, 2 explicitly skipped without live execution.
- SQLite migration/ORM drift checks passed during the targeted run.
- Disposable PostgreSQL 18.6: clean upgrade to 076, downgrade to 075, upgrade
  to 076; authenticated-mode API startup without external calls synchronized
  27/27 Registry records, including a 34-character expert identifier.
- GitHub PostgreSQL 16 and real-provider outcomes must be checked on the
  resulting commit. Local results are not live semantic or clinical evidence.

No merge, publication, deployment, independent clinical quality approval,
or production database mutation is performed by this change.
