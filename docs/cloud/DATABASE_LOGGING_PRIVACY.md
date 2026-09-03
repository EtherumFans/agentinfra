# Database logging privacy

Clinical notes, identifiers, prompts and Connector payloads are stored as bound
SQL parameters. They must never be emitted to application, container or cloud
collector logs.

## Defaults

- `DEBUG` does not control SQLAlchemy logging.
- `ICODER_DATABASE_SQL_ECHO=false` is the default in code, local Compose and
  the cloud environment template.
- The application engine always sets `hide_parameters=true`, including when an
  operator raises the `sqlalchemy.engine` logger level independently.
- Cloud mode refuses to boot when `ICODER_DATABASE_SQL_ECHO=true`.

## Local statement-only diagnosis

An operator may temporarily inspect SQL statement shapes in an isolated local
database:

```powershell
$env:ICODER_DATABASE_SQL_ECHO="true"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

The output may contain table names and SQL structure, but bound values are
replaced by SQLAlchemy's parameter-hidden marker. Do not interpolate clinical
content into raw SQL text. Clear the process-local switch after diagnosis:

```powershell
Remove-Item Env:ICODER_DATABASE_SQL_ECHO -ErrorAction SilentlyContinue
```

This switch is not a production troubleshooting mechanism. Cloud diagnosis
must use aggregate metrics, safe Run/Trace metadata and approved audit views.
