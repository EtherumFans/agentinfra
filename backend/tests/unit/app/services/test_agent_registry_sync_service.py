"""Registry Pack -> DB prebuilt projection consistency tests."""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.database import Base
from app.models.agent import Agent
from app.services.agent_registry_sync_service import AgentRegistrySyncService
from icoder_runtime.core.registry import RuntimeAgentRegistry


def _pack() -> dict:
    return {
        "format_version": "1.2",
        "agent_type": "certified",
        "agent_ref": "icoder/test-projection-agent@1.2.3",
        "manifest": {
            "name": "Test Projection Agent",
            "version": "1.2.3",
            "description": "Pack-mastered prebuilt projection",
            "category": "quality",
            "icon": "ShieldCheck",
            "use_case": "coding_quality",
            "maturity": "runnable",
            "human_review": "required",
            "production_ready": False,
            "hidden_from_hub": False,
        },
        "system_prompt": "Return a governed structured result.",
        "experts": [{"expert_id": "quality-gate"}],
        "permissions": {"network": False},
        "requirements": {"min_runtime_version": "1.0.0"},
        "llm_capabilities": {"required": False},
        "output_contract": {
            "schema_ref": "icoder/TestProjection/v1",
            "required_fields": ["status"],
        },
        "non_goals": ["no autonomous writeback"],
        "a2a": {"endpoint": "/v1/message:send"},
        "code": {"entrypoint": "test_projection:run"},
        "integrity": {"algorithm": "sha256", "digest": "test-only"},
    }


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all,
            tables=[Agent.__table__],
        )
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def registry(tmp_path):
    result = RuntimeAgentRegistry(storage_dir=tmp_path / "registry")
    result.install(_pack(), publisher_name="iCoDer")
    return result


@pytest.mark.asyncio
async def test_repair_creates_complete_prebuilt_projection(db_session, registry):
    service = AgentRegistrySyncService(registry=registry)

    before = await service.check_consistency(db_session)
    assert before.total_registry == 1
    assert [item.type for item in before.inconsistencies] == ["missing_in_db"]

    repaired = await service.repair_from_registry(db_session)
    assert repaired["total_repaired"] == 1
    assert repaired["total_failed"] == 0

    row = (await db_session.execute(select(Agent))).scalar_one()
    assert row.organization_id is None
    assert row.is_prebuilt is True
    assert row.is_published is True
    assert row.status == "published"
    assert row.canonical_key == "test-projection-agent"
    assert row.version == "1.2.3"
    assert row.expert_ids == ["quality-gate"]
    assert row.config["agent_ref"] == "icoder/test-projection-agent@1.2.3"
    assert row.config["registry_agent_id"] == "test-projection-agent-1.2.3"
    assert row.config["registry_projection_managed"] is True
    assert row.config["runtime_binding"]["code"]["entrypoint"] == (
        "test_projection:run"
    )

    after = await service.check_consistency(db_session)
    assert after.consistent is True
    assert after.inconsistencies == []
    repeated = await service.repair_from_registry(db_session)
    assert repeated["total_repaired"] == 0
    assert repeated["total_failed"] == 0


def test_broad_seed_projection_is_explicitly_not_registry_managed():
    from scripts.seed_agents import _build_fields

    fields = _build_fields(_pack())
    assert fields["config"]["registry_projection_managed"] is False


@pytest.mark.asyncio
async def test_custom_clone_is_excluded_from_registry_consistency(db_session, registry):
    service = AgentRegistrySyncService(registry=registry)
    await service.repair_from_registry(db_session)
    db_session.add(Agent(
        organization_id="org-test",
        name="Tenant Custom Clone",
        is_prebuilt=False,
        status="published",
        config={
            "source_agent_ref": "icoder/test-projection-agent@1.2.3",
            "cloned_from_prebuilt": True,
        },
    ))
    await db_session.commit()

    report = await service.check_consistency(db_session)
    assert report.consistent is True
    assert report.total_db == 1


@pytest.mark.asyncio
async def test_unmanaged_seed_projection_is_not_a_registry_orphan(db_session, tmp_path):
    registry = RuntimeAgentRegistry(storage_dir=tmp_path / "empty-registry")
    db_session.add(Agent(
        name="Hidden Metadata Pack",
        is_prebuilt=True,
        is_published=True,
        status="published",
        config={
            "agent_ref": "icoder/hidden-metadata@1.0.0",
            "registry_projection_managed": False,
            "hidden_from_hub": True,
        },
    ))
    await db_session.commit()

    report = await AgentRegistrySyncService(registry=registry).check_consistency(
        db_session
    )
    assert report.consistent is True
    assert report.total_registry == 0
    assert report.total_db == 0


@pytest.mark.asyncio
async def test_legacy_incomplete_row_is_upgraded_in_place(db_session, registry):
    record = registry.list_all()[0]
    db_session.add(Agent(
        id=record.agent_id,
        name=record.name,
        description=record.description,
        category=record.category,
        icon=record.icon,
        system_prompt=record.system_prompt,
        expert_ids=record.expert_ids,
        status="published",
        is_prebuilt=False,
        is_published=False,
        config=None,
    ))
    await db_session.commit()

    service = AgentRegistrySyncService(registry=registry)
    result = await service.repair_from_registry(db_session)
    assert result["total_repaired"] == 1

    rows = (await db_session.execute(select(Agent))).scalars().all()
    assert len(rows) == 1
    assert rows[0].id == record.agent_id
    assert rows[0].is_prebuilt is True
    assert rows[0].config["agent_ref"] == "icoder/test-projection-agent@1.2.3"


@pytest.mark.asyncio
async def test_pack_field_drift_is_reported_and_repaired(db_session, registry):
    service = AgentRegistrySyncService(registry=registry)
    await service.repair_from_registry(db_session)
    row = (await db_session.execute(select(Agent))).scalar_one()
    row.description = "stale metadata"
    row.version = "0.0.1"
    row.config = {**row.config, "production_ready": True}
    await db_session.commit()

    report = await service.check_consistency(db_session)
    assert report.consistent is False
    assert len(report.inconsistencies) == 1
    mismatch = report.inconsistencies[0]
    assert mismatch.type == "field_mismatch"
    assert "description" in mismatch.detail
    assert "version" in mismatch.detail
    assert "config" in mismatch.detail

    repaired = await service.repair_from_registry(db_session)
    assert repaired["total_repaired"] == 1
    await db_session.refresh(row)
    assert row.description == "Pack-mastered prebuilt projection"
    assert row.version == "1.2.3"
    assert row.config["production_ready"] is False
    assert (await service.check_consistency(db_session)).consistent is True


@pytest.mark.asyncio
async def test_pack_expert_slug_is_preserved_without_truncation(db_session, registry):
    pack = _pack()
    expert_id = "triage-questionnaire-path-reviewer"
    pack["experts"] = [{"expert_id": expert_id}]
    registry.install(pack, publisher_name="iCoDer")
    service = AgentRegistrySyncService(registry=registry)
    assert Agent.__table__.c.default_expert_id.type.length == 128
    assert (await service.repair_from_registry(db_session))["total_failed"] == 0
    db_session.expunge_all()
    row = (await db_session.execute(select(Agent))).scalar_one()
    assert row.default_expert_id == expert_id
    assert service.last_state.total_in_db == service.last_state.total_in_registry == 1


@pytest.mark.asyncio
async def test_failed_pack_savepoint_does_not_poison_other_repairs(
    db_session, registry, monkeypatch,
):
    import app.services.agent_registry_sync_service as module

    second = _pack()
    second["agent_ref"] = "icoder/second-projection@1.0.0"
    second["manifest"]["name"] = "Second Projection"
    registry.install(second, publisher_name="iCoDer")
    original = module._registry_record_db_fields

    def fields(record):
        values = original(record)
        if values["canonical_key"] == "test-projection-agent":
            values["name"] = None  # actual NOT NULL flush failure
        return values

    monkeypatch.setattr(module, "_registry_record_db_fields", fields)
    service = AgentRegistrySyncService(registry=registry)
    result = await service.repair_from_registry(db_session)
    assert result["total_failed"] == result["total_repaired"] == 1
    assert service.last_state.last_status == "failed"
    assert service.last_state.last_error == "IntegrityError"
    db_session.expunge_all()
    rows = (await db_session.execute(select(Agent))).scalars().all()
    assert [row.canonical_key for row in rows] == ["second-projection"]
    monkeypatch.setattr(module, "_registry_record_db_fields", original)
    assert (await service.repair_from_registry(db_session))["total_repaired"] == 1
    assert service.last_state.last_status == "success"


@pytest.mark.asyncio
async def test_commit_failure_does_not_claim_repairs(db_session, registry, monkeypatch):
    async def fail_commit():
        raise RuntimeError("private SQL parameters must not be published")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    service = AgentRegistrySyncService(registry=registry)
    result = await service.repair_from_registry(db_session)
    assert result["total_repaired"] == 0
    assert result["total_failed"] == 1
    assert service.last_state.last_status == "failed"
    assert service.last_state.last_error == "RuntimeError"
    assert (await db_session.execute(select(Agent))).scalars().all() == []
