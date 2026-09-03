"""Resolve active membership before installing PostgreSQL tenant authority.

Revision ID: 073
Revises: 072
Create Date: 2026-09-02
"""

from alembic import op


revision = "073"
down_revision = "072"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        """
        CREATE FUNCTION icoder_user_has_active_membership(
          p_user_id text, p_organization_id text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
          previous_tenant text;
          membership_exists boolean;
        BEGIN
          previous_tenant := current_setting('icoder.current_organization_id', true);
          PERFORM set_config('icoder.current_organization_id', p_organization_id, true);
          SELECT EXISTS (
            SELECT 1
            FROM public.organization_members m
            JOIN public.organizations o ON o.id = m.organization_id
            WHERE m.user_id = p_user_id
              AND m.organization_id = p_organization_id
              AND o.is_active IS TRUE
          ) INTO membership_exists;
          PERFORM set_config(
            'icoder.current_organization_id', coalesce(previous_tenant, ''), true
          );
          RETURN membership_exists;
        EXCEPTION WHEN OTHERS THEN
          PERFORM set_config(
            'icoder.current_organization_id', coalesce(previous_tenant, ''), true
          );
          RAISE;
        END
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION icoder_oauth_credential_is_active(
          p_token_hash text, p_client_id text, p_organization_id text, p_owner_id text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
          previous_tenant text;
          credential_exists boolean;
        BEGIN
          previous_tenant := current_setting('icoder.current_organization_id', true);
          PERFORM set_config('icoder.current_organization_id', p_organization_id, true);
          SELECT EXISTS (
            SELECT 1
            FROM public.oauth_tokens t
            JOIN public.oauth_clients c
              ON c.organization_id = t.organization_id AND c.client_id = t.client_id
            JOIN public.organizations o ON o.id = c.organization_id
            JOIN public.users u ON u.id = c.owner_id
            JOIN public.organization_members m
              ON m.organization_id = c.organization_id AND m.user_id = c.owner_id
            WHERE t.token_hash = p_token_hash
              AND t.client_id = p_client_id
              AND t.organization_id = p_organization_id
              AND t.is_revoked IS FALSE
              AND t.expires_at > clock_timestamp()
              AND c.owner_id = p_owner_id
              AND c.is_active IS TRUE
              AND o.is_active IS TRUE
              AND u.is_active IS TRUE
          ) INTO credential_exists;
          PERFORM set_config(
            'icoder.current_organization_id', coalesce(previous_tenant, ''), true
          );
          RETURN credential_exists;
        EXCEPTION WHEN OTHERS THEN
          PERFORM set_config(
            'icoder.current_organization_id', coalesce(previous_tenant, ''), true
          );
          RAISE;
        END
        $$
        """
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(
        "DROP FUNCTION IF EXISTS icoder_oauth_credential_is_active(text, text, text, text)"
    )
    op.execute("DROP FUNCTION IF EXISTS icoder_user_has_active_membership(text, text)")
