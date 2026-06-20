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

# M3-0 hospital pilot gate: the API hard-503s when ICODER_CREDENTIAL_LLM is
# unset, unless ICODER_ALLOW_DEGRADED_NO_KEY=1. Tests run without a real
# DeepSeek key, so opt in globally to the degraded-echo path by default.
# Individual tests that want to exercise the 503 path use monkeypatch.delenv
# to override.
os.environ.setdefault("ICODER_ALLOW_DEGRADED_NO_KEY", "1")

# M3-0 RBAC gate: /api/icoder/coding-review/* requires a valid JWT.
# Tests can opt in to bypass auth with ICODER_DISABLE_AUTH_FOR_TESTS=1 —
# the session-scoped fixture below sets a mock admin user on the
# ``get_current_user`` dependency override, so the 904 existing tests
# that don't send a token still pass. RBAC-specific tests run with the
# bypass OFF to exercise the 401/403 paths.
os.environ.setdefault("ICODER_DISABLE_AUTH_FOR_TESTS", "1")


def _make_mock_user(role: str = "admin"):
    """Build a User-like object satisfying the dependencies."""
    from app.models.user import User, UserRole

    class _MockUser:
        def __init__(self, role_value: str):
            from datetime import datetime
            # Identity kept stable as "testuser" so existing auth_client-based
            # tests (which expect username=testuser) keep passing. The role
            # is parameterizable for RBAC-specific tests.
            self.id = "u-test-bypass"
            self.username = "testuser"
            self.email = "testuser@example.com"
            self.full_name = "Test User (bypass)"
            self.role = UserRole(role_value)
            self.department = "测试科"
            self.organization_id = "org_default1"
            self.is_active = True
            self.is_verified = True
            self.token_version = 0
            self.created_at = datetime(2026, 1, 1)
            self.updated_at = datetime(2026, 1, 1)

        # Match the SQLAlchemy declarative User interface enough to be
        # usable as an injected dependency.
        @property
        def role_value(self):
            return self.role.value

    return _MockUser(role)


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


@pytest_asyncio.fixture(autouse=True)
async def _install_auth_bypass():
    """Install a get_current_user override when ICODER_DISABLE_AUTH_FOR_TESTS=1.

    This keeps the 904 existing tests green (they don't send Authorization
    headers) while letting RBAC-specific tests opt out by setting the env
    var to "0" or unsetting it via monkeypatch.
    """
    from app.middleware.auth import get_current_user

    if os.environ.get("ICODER_DISABLE_AUTH_FOR_TESTS") == "1":
        # Default to admin so /human-review RBAC gate passes for non-RBAC tests.
        app.dependency_overrides[get_current_user] = lambda: _make_mock_user("admin")
    try:
        yield
    finally:
        if "get_current_user" in app.dependency_overrides:
            del app.dependency_overrides[get_current_user]
