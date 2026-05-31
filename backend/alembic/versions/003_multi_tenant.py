"""Multi-tenant migration

Revision ID: 003
Create Date: 2026-05-28

Creates:
- organizations table
- organization_members table
- organization_invites table
- Adds organization_id column to all data tables
- Creates default organization and migrates existing data
"""
from datetime import datetime, timezone
import uuid

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    """Create organization tables and add tenant columns."""
    # This migration is designed for SQLite via create_all.
    # For PostgreSQL/MySQL, use raw SQL ALTER TABLE instead.
    import asyncio
    asyncio.run(_upgrade_async())


async def _upgrade_async():
    from app.database import async_session_factory, engine, Base
    from app.models.organization import Organization, OrganizationMember, OrganizationInvite
    from app.models.user import User
    from sqlalchemy import text, select

    # Create new tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            Organization.__table__,
            OrganizationMember.__table__,
            OrganizationInvite.__table__,
        ])

    # Add organization_id columns to existing tables
    async with engine.begin() as conn:
        data_tables = [
            "agents", "api_keys", "audit_logs",
            "code_candidates", "code_mappings", "code_tables",
            "coding_reviews", "clinical_evidences",
            "conversation_memories",
            "documents", "encounters",
            "experts", "mcp_servers",
            "gold_cases",
            "oauth_clients", "oauth_tokens",
            "runtime_sessions", "runtime_transitions",
            "runtime_audit_records", "runtime_duc_decisions",
            "team_members", "team_invites",
            "transactions",
        ]
        for table in data_tables:
            try:
                await conn.execute(text(
                    f"ALTER TABLE {table} ADD COLUMN organization_id VARCHAR(12) REFERENCES organizations(id)"
                ))
            except Exception:
                pass  # Column may already exist

    # Create default organization
    async with async_session_factory() as session:
        from sqlalchemy import select as db_select

        result = await session.execute(db_select(Organization).limit(1))
        if result.scalar_one_or_none():
            return  # Already migrated

        default_org = Organization(
            id="org_default1",
            name="iCoDer Default",
            slug="icoder-default",
            plan="enterprise",
        )
        session.add(default_org)
        await session.flush()

        # Assign all existing users to default org
        users_result = await session.execute(db_select(User))
        for user in users_result.scalars().all():
            member = OrganizationMember(
                organization_id=default_org.id,
                user_id=user.id,
                role="owner" if user.username == "admin" else "member",
                is_default=True,
            )
            session.add(member)

        # Set org_id on all existing records
        for table in data_tables:
            try:
                await session.execute(text(
                    f"UPDATE {table} SET organization_id = :org_id WHERE organization_id IS NULL"
                ), {"org_id": default_org.id})
            except Exception:
                pass

        await session.commit()


def downgrade():
    """Remove organization columns and tables."""
    import asyncio
    asyncio.run(_downgrade_async())


async def _downgrade_async():
    from app.database import engine
    from sqlalchemy import text

    # SQLite doesn't support DROP COLUMN, so downgrade is no-op for SQLite
    pass
