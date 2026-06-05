# Pytest configuration for iCoDer
import os
import pytest_asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.database import init_db, Base, engine
from app.config import settings

# Test DB: use ICODER_DATABASE_URL if set (PostgreSQL in CI), else SQLite with WAL mode
_test_db_url = os.environ.get("ICODER_DATABASE_URL", "")
if not _test_db_url:
    _test_db_url = "sqlite+aiosqlite:///./data/test.db"
settings.DATABASE_URL = _test_db_url
settings.DEBUG = False


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset login rate limiter between tests to avoid state leakage."""
    from app.api.auth import login_limiter
    login_limiter._attempts.clear()
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    """Initialize database once for the test session."""
    await init_db()
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_client():
    """Client pre-authenticated with a test user (auto-registered with org)."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Login or register testuser (with auto-created org)
        response = await ac.post("/api/auth/login", json={
            "username": "testuser",
            "password": "testpass123",
        })
        if response.status_code != 200:
            response = await ac.post("/api/auth/register", json={
                "username": "testuser",
                "email": "test@example.com",
                "password": "testpass123",
                "full_name": "Test User",
                "role": "admin",
                "department": "测试科",
            })
        if response.status_code in (200, 201):
            data = response.json()
            token = data.get("access_token", "")
            if token:
                ac.headers["Authorization"] = f"Bearer {token}"
        yield ac
