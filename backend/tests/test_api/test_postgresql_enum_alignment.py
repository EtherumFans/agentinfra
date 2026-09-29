"""Check the deployed enum contract, including historically mismatched labels."""
import pytest
from sqlalchemy import Enum, text

@pytest.mark.asyncio
async def test_native_enum_labels_match_orm():
    from app.database import engine, Base
    from app import models
    if engine.dialect.name!='postgresql':pytest.skip('PostgreSQL enum contract')
    checked=set()
    async with engine.connect() as conn:
        for table in Base.metadata.tables.values():
            for col in table.c:
                if isinstance(col.type,Enum) and col.type.native_enum and col.type.name not in checked:
                    labels=set((await conn.execute(text('SELECT e.enumlabel FROM pg_enum e JOIN pg_type t ON t.oid=e.enumtypid JOIN pg_namespace n ON n.oid=t.typnamespace WHERE n.nspname=current_schema() AND t.typname=:name'),{'name':col.type.name})).scalars())
                    if labels:
                        assert set(col.type.enums).issubset(labels),col.type.name
                        checked.add(col.type.name)
    assert {'templatecategory','templatelanguage','templatescope','userrole','orgrole','ticketstatus','customerregion'}.issubset(checked)
