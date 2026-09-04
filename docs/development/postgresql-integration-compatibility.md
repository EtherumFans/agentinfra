# PostgreSQL integration compatibility

The integration workflow keeps the complete historical suite on its isolated
SQLite database while promoting database-sensitive contracts to PostgreSQL in
reviewable waves. Tests in the PostgreSQL matrix carry the
`postgresql_compat` marker.

## Promotion criteria

A promoted test must:

- run against the Alembic-built PostgreSQL schema rather than ORM `create_all`;
- use a session-scoped asyncio loop when sharing the session-scoped asyncpg
  engine;
- provision and clean up its own tenant-scoped data;
- avoid SQLite-only SQL and implicit coercions;
- remain green in the full SQLite integration suite.

## Current waves

| Wave | Coverage | Test modules |
| --- | --- | --- |
| Foundational | role provisioning, Alembic schema, cross-process trace persistence | dedicated PostgreSQL contract tests |
| Wave 1 | 13 A2A context/task/artifact, observability, feedback, retention, and tenant-isolation contracts | `test_agentic_context_resources.py`, `test_agentic_observability_feedback.py` |
| Wave 2 | 37 Connector CRUD, execution-policy, transport, audit, and graph-runtime contracts | `test_agent_connectors.py`, `test_connector_executor.py`, `test_connector_graph_runtime.py` |

## Next candidates

Context repository unit-integration modules are the next database-heavy
candidates. They remain intentionally SQLite-specific until their in-memory
engine fixtures are parameterized.
