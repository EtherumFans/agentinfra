import importlib.util
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

@pytest.mark.parametrize('filename,table', [('079_run_execution_identity.py','run_history'),('080_agent_evaluations.py','agent_evaluations')])
def test_migration_preserves_evidence_on_downgrade(tmp_path,filename,table):
    path=Path(__file__).resolve().parents[3]/'alembic/versions'/filename
    spec=importlib.util.spec_from_file_location('delivery_migration',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    engine=sa.create_engine('sqlite:///'+str(tmp_path/'migration.db'))
    with engine.begin() as c:
        c.execute(sa.text('CREATE TABLE run_history (id TEXT PRIMARY KEY)'))
        c.execute(sa.text('CREATE TABLE agents (id TEXT, organization_id TEXT, UNIQUE(organization_id,id))'))
        m.op=Operations(MigrationContext.configure(c));m.upgrade()
        if table=='run_history':c.execute(sa.text("INSERT INTO run_history(id,executed_agent_version) VALUES ('r','1.0.0')"))
        else:c.execute(sa.text("INSERT INTO agent_evaluations(id,organization_id,agent_id,report,created_by,created_at) VALUES ('e','o','a','{}','u','2026-09-08')"))
        with pytest.raises(RuntimeError):m.downgrade()
        assert c.execute(sa.text(f'SELECT COUNT(*) FROM {table}')).scalar_one()==1
