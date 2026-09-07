from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa


def test_populated_runtime_identifier_upgrade_and_lossless_downgrade():
    path = Path(__file__).resolve().parents[3] / "alembic/versions/077_run_history_runtime_identifier.py"
    spec = importlib.util.spec_from_file_location("migration_077", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE run_history (id VARCHAR(128) PRIMARY KEY, runtime_mode VARCHAR(48) NOT NULL DEFAULT '')"))
        connection.execute(sa.text("INSERT INTO run_history VALUES ('existing', 'corti_like_fast')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {c["name"]: c for c in sa.inspect(connection).get_columns("run_history")}
        assert columns["runtime_mode"]["type"].length == 128
        assert connection.execute(sa.text("SELECT runtime_mode FROM run_history")).scalar_one() == "corti_like_fast"
        runtime = "governed_local_documented_medication_reconciliation"
        assert len(runtime) > 48
        connection.execute(sa.text("UPDATE run_history SET runtime_mode=:runtime"), {"runtime": runtime})
        with pytest.raises(RuntimeError, match="cannot downgrade 077"):
            migration.downgrade()
        assert connection.execute(sa.text("SELECT runtime_mode FROM run_history")).scalar_one() == runtime
        connection.execute(sa.text("UPDATE run_history SET runtime_mode='corti_like_fast'"))
        migration.downgrade()
        columns = {c["name"]: c for c in sa.inspect(connection).get_columns("run_history")}
        assert columns["runtime_mode"]["type"].length == 48
    engine.dispose()


def test_all_pack_runtime_identifiers_fit_audit_schema():
    import json
    from app.models.run_history import RunHistoryModel

    width = RunHistoryModel.__table__.c.runtime_mode.type.length
    directory = Path(__file__).resolve().parents[3] / "official_agents"
    identifiers = []
    for path in directory.glob("*/agent_pack.json"):
        pack = json.loads(path.read_text(encoding="utf-8"))
        identifier = pack.get("default_runtime_mode") or pack.get("backend_provider") or ""
        identifiers.append(identifier)
        assert len(identifier) <= width, (path.parent.name, identifier, width)
    assert max(map(len, identifiers)) > 48


@pytest.mark.parametrize("shadow_populated", [False, True])
def test_interrupted_sqlite_shadow_is_recovered_only_when_empty(shadow_populated):
    path = Path(__file__).resolve().parents[3] / "alembic/versions/077_run_history_runtime_identifier.py"
    spec = importlib.util.spec_from_file_location("migration_077_recovery", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE run_history (id VARCHAR(128) PRIMARY KEY, runtime_mode VARCHAR(48) NOT NULL DEFAULT '')"))
        connection.execute(sa.text("INSERT INTO run_history VALUES ('authoritative', 'corti_like_fast')"))
        connection.execute(sa.text("CREATE TABLE _alembic_tmp_run_history AS SELECT * FROM run_history WHERE 1=0"))
        if shadow_populated:
            connection.execute(sa.text("INSERT INTO _alembic_tmp_run_history VALUES ('preserve-me', 'corti_like_fast')"))
        migration.op = Operations(MigrationContext.configure(connection))
        if shadow_populated:
            with pytest.raises(RuntimeError, match="manual recovery"):
                migration.upgrade()
            assert connection.execute(sa.text("SELECT id FROM _alembic_tmp_run_history")).scalar_one() == "preserve-me"
        else:
            migration.upgrade()
            assert not sa.inspect(connection).has_table("_alembic_tmp_run_history")
        assert connection.execute(sa.text("SELECT id FROM run_history")).scalar_one() == "authoritative"
        columns = {c["name"]: c for c in sa.inspect(connection).get_columns("run_history")}
        assert columns["runtime_mode"]["type"].length == (48 if shadow_populated else 128)
    engine.dispose()
