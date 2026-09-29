import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_release_migration_preserves_populated_history_on_downgrade(tmp_path, monkeypatch):
    path=Path(__file__).resolve().parents[3]/'alembic/versions/078_agent_releases.py'
    spec=importlib.util.spec_from_file_location('migration_078',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=sa.create_engine('sqlite:///'+str(tmp_path/'release.db'))
    with engine.begin() as db:
        db.execute(sa.text('CREATE TABLE agents (id VARCHAR(128), organization_id VARCHAR(12), UNIQUE(organization_id,id))'))
        monkeypatch.setattr(migration,'op',Operations(MigrationContext.configure(db)))
        migration.upgrade()
        assert 'agent_releases' in sa.inspect(db).get_table_names()
        db.execute(sa.text("INSERT INTO agent_releases VALUES ('release','org','agent','1.0.0','{}','{}','user','2026-09-08')"))
        with pytest.raises(RuntimeError,match='Cannot discard published releases'):
            migration.downgrade()
        assert db.execute(sa.text('SELECT count(*) FROM agent_releases')).scalar_one()==1
    engine.dispose()
