"""Registration tokens must refer to committed identity and tenant ownership."""
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from starlette.requests import Request

from app.api import auth
from app.database import Base
from app.models.organization import OrganizationMember
from app.models.user import User
from app.schemas.user import UserCreate


@pytest_asyncio.fixture
async def registration_db(tmp_path):
    # Independent connections matter: shared in-memory SQLite hides the race.
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'register.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    yield sessions
    await engine.dispose()


def _request():
    return Request({"type": "http", "headers": [], "client": ("127.0.0.1", 1234)})


def _data():
    return UserCreate(
        username="commit-boundary", email="commit-boundary@example.com",
        password="Test-only-password-aA123!", full_name="Commit Boundary",
        organization_name="Commit Boundary Org",
    )


@pytest.mark.asyncio
async def test_registration_is_visible_before_dependency_cleanup(registration_db):
    async with registration_db() as request_db:
        response = await auth.register(_data(), _request(), request_db)
        # No get_db finalizer or caller-side commit has run yet.
        async with registration_db() as next_request_db:
            user = await next_request_db.get(User, response.user.id)
            assert user is not None
            member = (await next_request_db.execute(select(OrganizationMember).where(
                OrganizationMember.user_id == user.id,
                OrganizationMember.organization_id == response.current_org_id,
            ))).scalar_one()
            assert member.role.value == "owner"
        assert response.access_token and response.refresh_token


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_never_mints_tokens(registration_db, monkeypatch):
    access, refresh = Mock(), Mock()
    monkeypatch.setattr(auth, "create_access_token", access)
    monkeypatch.setattr(auth, "create_refresh_token", refresh)
    async with registration_db() as request_db:
        monkeypatch.setattr(request_db, "commit", AsyncMock(side_effect=RuntimeError("sensitive database details")))
        with pytest.raises(HTTPException) as caught:
            await auth.register(_data(), _request(), request_db)
        assert caught.value.status_code == 503
        assert "sensitive" not in caught.value.detail
        access.assert_not_called()
        refresh.assert_not_called()
        async with registration_db() as observer:
            assert (await observer.execute(select(User))).scalars().all() == []
