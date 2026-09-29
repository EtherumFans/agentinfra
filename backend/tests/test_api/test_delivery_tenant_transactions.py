import os
import pytest
from sqlalchemy import text
from app.services.database_tenancy import bind_tenant_to_transaction

@pytest.mark.asyncio
async def test_verified_tenant_survives_commit_but_not_new_session():
    from app.database import AsyncSessionLocal, engine
    if engine.dialect.name!='postgresql':pytest.skip('Requires PostgreSQL transaction-local settings')
    async with AsyncSessionLocal() as db:
        await bind_tenant_to_transaction(db,'delivery_t1')
        await db.commit()
        assert (await db.execute(text("SELECT current_setting('icoder.current_organization_id',true)"))).scalar_one()=='delivery_t1'
        await bind_tenant_to_transaction(db,'delivery_t2')
        await db.rollback()
        assert (await db.execute(text("SELECT current_setting('icoder.current_organization_id',true)"))).scalar_one()=='delivery_t2'
    async with AsyncSessionLocal() as fresh:
        assert not (await fresh.execute(text("SELECT current_setting('icoder.current_organization_id',true)"))).scalar_one()
        assert (await fresh.execute(text('SELECT COUNT(*) FROM agent_releases'))).scalar_one()==0
