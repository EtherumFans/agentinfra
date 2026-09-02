from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta

import psycopg
import pytest


MIGRATION_URL = os.getenv("P1_POSTGRES_MIGRATION_DATABASE_URL", "")
APP_URL = os.getenv("P1_POSTGRES_APP_DATABASE_URL", "")


def _sync_url(value: str) -> str:
    return value.replace("postgresql+asyncpg://", "postgresql://").replace(
        "postgresql+psycopg://", "postgresql://"
    )


@pytest.mark.skipif(not MIGRATION_URL or not APP_URL, reason="requires PostgreSQL role URLs")
def test_membership_bootstrap_is_minimum_disclosure_and_precedes_rls_binding() -> None:
    suffix = secrets.token_hex(4)
    user_id = f"u{suffix}"[:12]
    org_id = f"o{suffix}"[:12]
    migration = psycopg.connect(_sync_url(MIGRATION_URL), autocommit=True)
    app = psycopg.connect(_sync_url(APP_URL), autocommit=False)
    try:
        migration.execute(
            """INSERT INTO users
               (id, username, email, hashed_password, full_name, role,
                department, is_active, is_verified, token_version)
               VALUES (%s, %s, %s, 'not-a-real-hash', 'P1 test', 'CODER', '', true, true, 0)""",
            (user_id, f"p1-{suffix}", f"p1-{suffix}@example.invalid"),
        )
        migration.execute(
            """INSERT INTO organizations
               (id, name, slug, plan, settings, is_active)
               VALUES (%s, %s, %s, 'free', '{}'::json, true)""",
            (org_id, f"P1 {suffix}", f"p1-{suffix}"),
        )
        migration.execute(
            "SELECT set_config('icoder.current_organization_id', %s, false)", (org_id,),
        )
        migration.execute(
            """INSERT INTO organization_members
               (id, organization_id, user_id, role, is_default)
               VALUES (%s, %s, %s, 'member', true)""",
            (f"m{suffix}"[:12], org_id, user_id),
        )

        assert app.execute(
            "SELECT icoder_user_has_active_membership(%s, %s)", (user_id, org_id),
        ).fetchone() == (True,)
        assert app.execute(
            "SELECT icoder_user_has_active_membership(%s, %s)", ("forged-user", org_id),
        ).fetchone() == (False,)
        client_id = f"client-{suffix}"
        token_hash = secrets.token_hex(32)
        migration.execute(
            """INSERT INTO oauth_clients
               (id, organization_id, name, client_id, client_secret_hash, description,
                scopes, is_active, owner_id, token_expires_seconds,
                allowed_agent_ids, allowed_purposes)
               VALUES (%s, %s, 'P1 test', %s, 'hash', '', 'api:read', true, %s, 300,
                       '[]'::json, '[]'::json)""",
            (f"c{suffix}"[:12], org_id, client_id, user_id),
        )
        migration.execute(
            """INSERT INTO oauth_tokens
               (id, organization_id, client_id, token_hash, scopes, expires_at, is_revoked)
               VALUES (%s, %s, %s, %s, 'api:read', %s, false)""",
            (f"t{suffix}"[:12], org_id, client_id, token_hash, datetime.now(UTC) + timedelta(minutes=5)),
        )
        assert app.execute(
            "SELECT icoder_oauth_credential_is_active(%s, %s, %s, %s)",
            (token_hash, client_id, org_id, user_id),
        ).fetchone() == (True,)
        assert app.execute(
            "SELECT icoder_oauth_credential_is_active(%s, %s, %s, %s)",
            (token_hash, client_id, "forged-org", user_id),
        ).fetchone() == (False,)
        # The bootstrap result is a boolean; it does not expose the protected row
        # and it does not install a transaction tenant setting as a side effect.
        assert app.execute(
            "SELECT current_setting('icoder.current_organization_id', true)"
        ).fetchone()[0] in (None, "")
        assert app.execute("SELECT count(*) FROM organization_members").fetchone() == (0,)
        app.rollback()

        migration.execute(
            "UPDATE organizations SET is_active=false WHERE id=%s", (org_id,),
        )
        assert app.execute(
            "SELECT icoder_user_has_active_membership(%s, %s)", (user_id, org_id),
        ).fetchone() == (False,)
    finally:
        app.rollback()
        app.close()
        migration.execute(
            "SELECT set_config('icoder.current_organization_id', %s, false)", (org_id,),
        )
        migration.execute("DELETE FROM oauth_tokens WHERE organization_id=%s", (org_id,))
        migration.execute("DELETE FROM oauth_clients WHERE organization_id=%s", (org_id,))
        migration.execute("DELETE FROM organization_members WHERE organization_id=%s", (org_id,))
        migration.execute("DELETE FROM organizations WHERE id=%s", (org_id,))
        migration.execute("DELETE FROM users WHERE id=%s", (user_id,))
        migration.close()
