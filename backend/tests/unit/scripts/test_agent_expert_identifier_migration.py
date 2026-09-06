from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa


def test_populated_expert_identifier_upgrade_and_lossless_downgrade():
    path = Path(__file__).resolve().parents[3] / "alembic/versions/076_agent_default_expert_identifier.py"
    spec = importlib.util.spec_from_file_location("migration_076", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(sa.text("CREATE TABLE agents (id VARCHAR(128) PRIMARY KEY, default_expert_id VARCHAR(12) NOT NULL)"))
        connection.execute(sa.text("INSERT INTO agents VALUES ('existing', 'quality-gate')"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {c["name"]: c for c in sa.inspect(connection).get_columns("agents")}
        assert columns["default_expert_id"]["type"].length == 128
        assert connection.execute(sa.text("SELECT default_expert_id FROM agents")).scalar_one() == "quality-gate"
        expert = "triage-questionnaire-path-reviewer"
        connection.execute(sa.text("UPDATE agents SET default_expert_id=:expert"), {"expert": expert})
        with pytest.raises(RuntimeError, match="cannot downgrade 076"):
            migration.downgrade()
        assert connection.execute(sa.text("SELECT default_expert_id FROM agents")).scalar_one() == expert
        connection.execute(sa.text("UPDATE agents SET default_expert_id='quality-gate'"))
        migration.downgrade()
        columns = {c["name"]: c for c in sa.inspect(connection).get_columns("agents")}
        assert columns["default_expert_id"]["type"].length == 12
    engine.dispose()
