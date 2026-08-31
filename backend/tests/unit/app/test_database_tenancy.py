from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.database_tenancy import (
    TENANT_SETTING,
    bind_tenant_to_transaction,
)


class _Session:
    def __init__(self, dialect: str) -> None:
        self._bind = SimpleNamespace(dialect=SimpleNamespace(name=dialect))
        self.execute = AsyncMock()

    def get_bind(self):
        return self._bind


@pytest.mark.asyncio
async def test_postgresql_tenant_context_is_transaction_local() -> None:
    session = _Session("postgresql")

    await bind_tenant_to_transaction(session, "org_alpha-1")

    session.execute.assert_awaited_once()
    statement, params = session.execute.await_args.args
    assert "set_config" in str(statement)
    assert params == {
        "setting_name": TENANT_SETTING,
        "tenant_id": "org_alpha-1",
    }
    assert "true" in str(statement).lower()


@pytest.mark.asyncio
async def test_sqlite_local_mode_does_not_install_session_state() -> None:
    session = _Session("sqlite")

    await bind_tenant_to_transaction(session, "org_local")

    session.execute.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["", "  ", "org/a", "org.alpha", "x" * 65])
async def test_invalid_organization_id_fails_closed(value: str) -> None:
    session = _Session("postgresql")

    with pytest.raises(ValueError, match="organization_id"):
        await bind_tenant_to_transaction(session, value)

    session.execute.assert_not_awaited()
