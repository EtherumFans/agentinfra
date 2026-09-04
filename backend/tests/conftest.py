# Pytest configuration for iCoDer
# FastAPI/Starlette compatibility is pinned in requirements-api.txt;
# test-time router monkey-patching is intentionally not used.

# FastAPI/starlette env patch — fastapi 0.115.0 still passes ``on_startup``
# to starlette 1.3.1's Router, which removed the kwarg. Must run before
# ANY ``FastAPI()`` or ``APIRouter()`` instantiation in the import chain.
import os
from pathlib import Path

# Never let a developer or CI host secret leak into hermetic JWT tests. This
# value is process-local, explicitly non-production, and long enough for
# HS256's RFC 7518 minimum so security warnings remain actionable.
os.environ["ICODER_SECRET_KEY"] = (
    "icoder-pytest-only-not-a-production-secret-2026-08-22-64chars"
)

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

# Keep legacy migration assertions pointed at the same isolated SQLite file as
# the SQLAlchemy test engine.  Without this bridge, an explicit
# ICODER_DATABASE_URL (for example a C: drive database used to avoid a full E:
# disk) still makes those assertions inspect backend/data/test.db instead.
from sqlalchemy.engine import make_url

_parsed_test_db_url = make_url(_test_db_url)
if (
    _parsed_test_db_url.get_backend_name() == "sqlite"
    and _parsed_test_db_url.database
    and _parsed_test_db_url.database != ":memory:"
):
    _sqlite_test_path = Path(_parsed_test_db_url.database)
    if not _sqlite_test_path.is_absolute():
        _sqlite_test_path = (Path.cwd() / _sqlite_test_path).resolve()
    os.environ["ICODER_TEST_DB_PATH"] = str(_sqlite_test_path)
else:
    # SQLite-specific schema checks skip cleanly for PostgreSQL/in-memory runs.
    os.environ["ICODER_TEST_DB_PATH"] = ""

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
            self.id = os.environ.get("ICODER_TEST_USER_ID", "u-test-bypass")
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


def _make_mock_org():
    """Build an Organization-like object satisfying dependencies.

    TD-001 fix: the mock user's organization_id is "org_default1", but
    `get_current_organization` (not overridden previously) reads the JWT
    `org_id` claim, queries the DB, and returns the auto-created org with
    a UUID id — so any test fixture that seeds rows with organization_id
    = "org_default1" is invisible to API routes that filter by
    `current_org.id`. Unify the org context by also overriding
    `get_current_organization` to return a mock org whose id matches the
    mock user's organization_id.
    """
    from datetime import datetime

    class _MockOrg:
        id = "org_default1"
        name = "Test Organization (bypass)"
        slug = "test-org-bypass"
        plan = "free"
        settings = {}
        is_active = True
        created_at = datetime(2026, 1, 1)
        updated_at = datetime(2026, 1, 1)

    return _MockOrg()


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset login rate limiter AND HTTP rate-limit middleware between tests.

    Phase A1A Gate 4R.2: the HTTP middleware at app/middleware/rate_limit.py
    moved its per-IP counter dict off the module global and onto
    app.state.rate_limiter_counts. Without a per-test reset, the sliding
    window accumulates across tests and trips the 30/min limit partway
    through the suite — which was the dominant cause of the 77 pass->fail
    regressions catalogued in Gate 4R.1.
    """
    from app.api.auth import login_limiter
    login_limiter._attempts.clear()
    # Wipe the HTTP rate-limiter counters bound to the session-scoped app.
    if hasattr(app.state, "rate_limiter_counts"):
        app.state.rate_limiter_counts.clear()
    # Force lazy re-init of Redis client on next request (tests don't use
    # Redis, but resetting keeps the fixture hermetic if REDIS_URL is set).
    if hasattr(app.state, "rate_limiter_redis"):
        app.state.rate_limiter_redis = False
    yield


@pytest_asyncio.fixture(scope="session", loop_scope="session", autouse=True)
async def setup_db():
    """Initialize database once for the test session.

    Cycle 25 safety: the original teardown ran ``Base.metadata.drop_all`` on the
    engine imported at module load — but that engine was created with the
    dev DB URL before the ``settings.DATABASE_URL`` override above took effect.
    The net effect was that every pytest session dropped all 34 tables from
    ``data/icoder.db`` on exit. The settings override changes the attribute on
    the Pydantic Settings instance, but ``app.database.engine`` was already
    bound to the dev URL.

    Fix: rebuild the engine after the override so init_db() and the teardown
    both target ``data/test.db``. Tests that hit the FastAPI app via the
    ``client`` fixture also pick up the rebound engine (get_db dependency
    resolves at request time).

    A1B-AE-RV.2 dev DB guard: snapshot mtime+size of ``data/icoder.db``
    before tests start and assert unchanged on teardown. Any test that
    mutates the dev DB during the session fails the session loudly.
    """
    import app.database as _db_module
    from pathlib import Path

    _dev_db = Path("data/icoder.db")
    _dev_db_before = (
        (_dev_db.stat().st_mtime_ns, _dev_db.stat().st_size)
        if _dev_db.exists() else None
    )
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    from sqlalchemy.pool import NullPool

    # Dispose the dev engine and rebuild against the test URL
    await _db_module.engine.dispose()
    test_engine_kwargs = {
        "echo": False,
        "connect_args": (
            {"check_same_thread": False} if "sqlite" in _test_db_url else {}
        ),
    }
    if _parsed_test_db_url.get_backend_name() == "postgresql":
        test_engine_kwargs["poolclass"] = NullPool
    _test_engine = create_async_engine(_test_db_url, **test_engine_kwargs)
    _db_module.engine = _test_engine
    _db_module.AsyncSessionLocal = async_sessionmaker(
        _test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    # TD-001 fix: async_session_factory was bound at module-import time to the
    # OLD AsyncSessionLocal (dev DB). Rebind it so test fixtures that import
    # `from app.database import async_session_factory` write to the test DB,
    # not the dev DB. Without this, seeded_templates inserts into dev DB
    # while the API reads test DB — the rows are invisible.
    _db_module.async_session_factory = _db_module.AsyncSessionLocal

    use_premigrated_schema = (
        os.environ.get("ICODER_TEST_USE_PREMIGRATED_SCHEMA") == "1"
        and _parsed_test_db_url.get_backend_name() == "postgresql"
    )

    # A prior interrupted pytest session cannot run the teardown below and
    # may leave fixed-id fixtures in data/test.db.  Start from a known-empty
    # schema so repeated and interrupted local runs remain deterministic.
    # This engine is already rebound to the dedicated test URL; the dev DB
    # guard below continues to prove data/icoder.db is untouched.
    if not use_premigrated_schema:
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await init_db()
    yield
    # A pre-migrated PostgreSQL service is disposable and the app role must
    # never acquire schema-owner DDL privileges merely for test cleanup.
    if not use_premigrated_schema:
        # Drop tables from the test engine only — dev DB is never touched.
        async with _test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    await _test_engine.dispose()

    # A1B-AE-RV.2 dev DB guard: assert dev DB untouched.
    if _dev_db_before is not None:
        if not _dev_db.exists():
            raise RuntimeError(
                "A1B-AE-RV.2 dev DB guard: data/icoder.db was DELETED during "
                "the test session. Tests must not mutate the dev DB."
            )
        _dev_db_after = (_dev_db.stat().st_mtime_ns, _dev_db.stat().st_size)
        if _dev_db_after != _dev_db_before:
            raise RuntimeError(
                "A1B-AE-RV.2 dev DB guard: data/icoder.db was MODIFIED during "
                f"the test session. Before={_dev_db_before} After={_dev_db_after}. "
                "Tests must use data/test.db (settings.DATABASE_URL override)."
            )


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
                "role": "coder",
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
    """Install get_current_user + get_current_organization overrides when
    ICODER_DISABLE_AUTH_FOR_TESTS=1.

    This keeps the 904 existing tests green (they don't send Authorization
    headers) while letting RBAC-specific tests opt out by setting the env
    var to "0" or unsetting it via monkeypatch.

    TD-001 fix: also override get_current_organization so the mock user's
    organization_id ("org_default1") matches the org returned to routes
    that filter by current_org.id. Previously only get_current_user was
    overridden, so get_current_organization queried the DB via the JWT
    org_id claim and returned an auto-created org with a UUID id,
    breaking any fixture that seeded rows with organization_id =
    "org_default1".
    """
    from app.middleware.auth import (
        get_current_user,
        get_current_organization,
        get_current_user_or_oauth_client,
    )

    if os.environ.get("ICODER_DISABLE_AUTH_FOR_TESTS") == "1":
        # Default to admin so /human-review RBAC gate passes for non-RBAC tests.
        mock_user = _make_mock_user("admin")
        app.dependency_overrides[get_current_user] = lambda: mock_user
        # TD-001: unify org context — return a mock org whose id matches
        # the mock user's organization_id.
        app.dependency_overrides[get_current_organization] = lambda: _make_mock_org()
        # Phase 7 Gate 12 — hybrid auth bypass. Routes using
        # get_current_user_or_oauth_client see the same mock user as
        # get_current_user, with no OAuth client (user path).
        app.dependency_overrides[get_current_user_or_oauth_client] = lambda: (mock_user, None)
    try:
        yield
    finally:
        if "get_current_user" in app.dependency_overrides:
            del app.dependency_overrides[get_current_user]
        if "get_current_organization" in app.dependency_overrides:
            del app.dependency_overrides[get_current_organization]
        if "get_current_user_or_oauth_client" in app.dependency_overrides:
            del app.dependency_overrides[get_current_user_or_oauth_client]


@pytest_asyncio.fixture
async def needs_auth():
    """Opt out of the auth bypass for tests that exercise real 401/403 paths.

    Usage:
        async def test_protected_route_without_token(client, needs_auth):
            response = await client.get("/api/encounters")
            assert response.status_code == 401

    Removes the get_current_user + get_current_organization overrides for
    the duration of the test, then restores them after.
    """
    from app.middleware.auth import (
        get_current_user,
        get_current_organization,
        get_current_user_or_oauth_client,
    )
    saved_user = app.dependency_overrides.get(get_current_user)
    saved_org = app.dependency_overrides.get(get_current_organization)
    saved_hybrid = app.dependency_overrides.get(get_current_user_or_oauth_client)
    if get_current_user in app.dependency_overrides:
        del app.dependency_overrides[get_current_user]
    if get_current_organization in app.dependency_overrides:
        del app.dependency_overrides[get_current_organization]
    if get_current_user_or_oauth_client in app.dependency_overrides:
        del app.dependency_overrides[get_current_user_or_oauth_client]
    try:
        yield
    finally:
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user
        if saved_org is not None:
            app.dependency_overrides[get_current_organization] = saved_org
        if saved_hybrid is not None:
            app.dependency_overrides[get_current_user_or_oauth_client] = saved_hybrid
