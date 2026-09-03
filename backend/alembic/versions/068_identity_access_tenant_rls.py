"""Enforce PostgreSQL tenant isolation for identity and access state.

Revision ID: 068
Revises: 067
Create Date: 2026-09-01

Tenant-owned identity rows use the standard FORCE RLS policy. ``audit_logs``
is deliberately split: tenant rows use the same policy, while genuine
``MODERN_SYSTEM`` rows remain NULL-owned and are append-only through the
security-definer function created here.
"""

from alembic import op


revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


TENANT_TABLES = (
    "api_keys",
    "oauth_clients",
    "oauth_tokens",
    "organization_invite_deliveries",
    "organization_invites",
    "organization_members",
    "team_invites",
    "team_members",
)
SPLIT_POLICY_TABLES = ("audit_logs",)
POLICY_NAME = "icoder_tenant_isolation"
TENANT_EXPRESSION = (
    "organization_id = NULLIF("
    "current_setting('icoder.current_organization_id', true), '')"
)


def _validate_ownership() -> None:
    bind = op.get_bind()
    invalid: dict[str, int] = {}
    for table in TENANT_TABLES:
        count = bind.exec_driver_sql(
            f'SELECT count(*) FROM "{table}" WHERE organization_id IS NULL'
        ).scalar_one()
        if count:
            invalid[f"{table}:null_tenant"] = int(count)

    checks = {
        "audit_logs:invalid_null_partition": (
            "SELECT count(*) FROM audit_logs WHERE organization_id IS NULL AND ("
            "tenancy_classification IS DISTINCT FROM 'MODERN_SYSTEM' OR "
            "tenancy_attribution_source IS DISTINCT FROM 'security_event' OR "
            "tenancy_attribution_confidence IS DISTINCT FROM 'verified')"
        ),
        "api_keys:owner_not_member": (
            "SELECT count(*) FROM api_keys k LEFT JOIN organization_members m "
            "ON m.organization_id=k.organization_id AND m.user_id=k.owner_id "
            "WHERE m.id IS NULL"
        ),
        "oauth_clients:owner_not_member": (
            "SELECT count(*) FROM oauth_clients c LEFT JOIN organization_members m "
            "ON m.organization_id=c.organization_id AND m.user_id=c.owner_id "
            "WHERE m.id IS NULL"
        ),
        "oauth_tokens:client_scope_mismatch": (
            "SELECT count(*) FROM oauth_tokens t LEFT JOIN oauth_clients c "
            "ON c.organization_id=t.organization_id AND c.client_id=t.client_id "
            "WHERE c.id IS NULL"
        ),
        "organization_invites:inviter_not_member": (
            "SELECT count(*) FROM organization_invites i "
            "LEFT JOIN organization_members m ON m.organization_id=i.organization_id "
            "AND m.user_id=i.invited_by WHERE m.id IS NULL"
        ),
        "organization_invite_deliveries:invite_scope_mismatch": (
            "SELECT count(*) FROM organization_invite_deliveries d "
            "LEFT JOIN organization_invites i ON i.organization_id=d.organization_id "
            "AND i.id=d.invite_id WHERE i.id IS NULL"
        ),
        "team_members:missing_authoritative_membership": (
            "SELECT count(*) FROM team_members t LEFT JOIN organization_members m "
            "ON m.organization_id=t.organization_id AND m.user_id=t.user_id "
            "WHERE m.id IS NULL"
        ),
        "team_invites:inviter_not_member": (
            "SELECT count(*) FROM team_invites i LEFT JOIN organization_members m "
            "ON m.organization_id=i.organization_id AND m.user_id=i.invited_by "
            "WHERE m.id IS NULL"
        ),
    }
    for key, statement in checks.items():
        count = bind.exec_driver_sql(statement).scalar_one()
        if count:
            invalid[key] = int(count)
    if invalid:
        details = ", ".join(
            f"{key}={count}" for key, count in sorted(invalid.items())
        )
        raise RuntimeError(
            "migration 068 requires evidence-backed identity/access tenant "
            "reconciliation: " + details
        )


def _create_bootstrap_functions() -> None:
    # These functions disclose only a tenant identifier or a boolean needed to
    # establish RLS context. They never expose secrets or tenant-owned rows.
    op.execute(
        """
        CREATE FUNCTION icoder_resolve_oauth_client_tenant(p_client_id text)
        RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
          SELECT c.organization_id FROM public.oauth_clients c
          JOIN public.organizations o ON o.id = c.organization_id
          WHERE c.client_id = p_client_id AND c.is_active IS TRUE
            AND o.is_active IS TRUE
          LIMIT 1
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION icoder_resolve_invite_tenant(p_token text)
        RETURNS text LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
          SELECT organization_id FROM public.organization_invites
          WHERE token = p_token LIMIT 1
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION icoder_partner_origin_allowed(p_origin text)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
          SELECT EXISTS (
            SELECT 1 FROM public.oauth_clients c
            JOIN public.organizations o ON o.id = c.organization_id
            WHERE c.is_active IS TRUE AND o.is_active IS TRUE
              AND c.allowed_origins IS NOT NULL
              AND c.allowed_origins::jsonb @> jsonb_build_array(p_origin)
          )
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION icoder_write_system_audit(p_event jsonb)
        RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        BEGIN
          IF coalesce(p_event->>'id', '') = ''
             OR coalesce(p_event->>'action', '') = ''
             OR coalesce(p_event->>'resource_type', '') = '' THEN
            RAISE EXCEPTION 'invalid system audit event';
          END IF;
          IF NOT (
            p_event->>'action' = ANY (ARRAY[
              'agentic.feedback.training_authorization.granted',
              'agentic.feedback.training_authorization.revoked',
              'api_client.authentication_rejected', 'api_client.rotate',
              'auth.register.denied.role_escalation',
              'cdi.run.failed.required_gate_degraded', 'context.clear',
              'idempotency.dedup', 'org.invite.delivery_dead_letter',
              'org.invite.delivery_retry_scheduled',
              'org.invite.delivery_succeeded',
              'platform_admin.organization_updated',
              'platform_admin.user_access_update_denied',
              'platform_admin.user_access_updated', 'retention.purge',
              'run.cancel', 'run.complete', 'run.failed', 'run.timeout',
              'security_admin.access', 'sse.denied.invisible_classification',
              'sse.denied.org_mismatch', 'sse.denied.orphan_run',
              'system.config_change', 'system.migration',
              'system.secret_rotation', 'system.shutdown', 'system.startup',
              'trace.read.denied.invisible_classification',
              'trace.read.denied.org_mismatch', 'trace.read.denied.orphan_run'
            ])
            OR p_event->>'action' LIKE 'security_admin.%'
          ) THEN
            RAISE EXCEPTION 'system audit action is not allowlisted';
          END IF;
          INSERT INTO public.audit_logs (
            id, organization_id, user_id, username, action, resource_type,
            resource_id, details, ip_address, user_agent, status, error_message,
            tenancy_classification, tenancy_attribution_source,
            tenancy_attribution_confidence, tenancy_attribution_migration,
            tenancy_attributed_at, tenancy_original_org_id,
            tenancy_candidate_count, created_at, updated_at
          ) VALUES (
            left(p_event->>'id', 12), NULL, nullif(p_event->>'user_id', ''),
            nullif(p_event->>'username', ''), left(p_event->>'action', 128),
            left(p_event->>'resource_type', 64),
            nullif(left(p_event->>'resource_id', 64), ''), p_event->'details',
            nullif(left(p_event->>'ip_address', 45), ''),
            nullif(left(p_event->>'user_agent', 256), ''),
            coalesce(nullif(left(p_event->>'status', 32), ''), 'success'),
            nullif(p_event->>'error_message', ''), 'MODERN_SYSTEM',
            'security_event', 'verified', '068', clock_timestamp(), NULL, 0,
            clock_timestamp(), clock_timestamp()
          );
        END
        $$
        """
    )


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    _validate_ownership()

    for table in TENANT_TABLES:
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN organization_id SET NOT NULL'
        )

    op.create_unique_constraint(
        "uq_oauth_clients_org_client_id",
        "oauth_clients",
        ["organization_id", "client_id"],
    )
    op.create_foreign_key(
        "fk_oauth_tokens_client_scope",
        "oauth_tokens",
        "oauth_clients",
        ["organization_id", "client_id"],
        ["organization_id", "client_id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "uq_organization_invites_org_id",
        "organization_invites",
        ["organization_id", "id"],
    )
    op.drop_constraint(
        "organization_invite_deliveries_invite_id_fkey",
        "organization_invite_deliveries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_organization_invite_deliveries_invite_scope",
        "organization_invite_deliveries",
        "organization_invites",
        ["organization_id", "invite_id"],
        ["organization_id", "id"],
        ondelete="CASCADE",
    )

    for table in TENANT_TABLES + SPLIT_POLICY_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f'CREATE POLICY "{POLICY_NAME}" ON "{table}" '
            f"USING ({TENANT_EXPRESSION}) WITH CHECK ({TENANT_EXPRESSION})"
        )

    # The migration/table owner is the only identity allowed to traverse the
    # control partition. SECURITY DEFINER bootstrap functions run as that
    # owner; the runtime role cannot use this policy with direct SQL.
    for table in ("oauth_clients", "organization_invites"):
        owner_expression = (
            "current_user = pg_get_userbyid((SELECT relowner FROM pg_class "
            f"WHERE oid = 'public.{table}'::regclass))"
        )
        op.execute(
            f'CREATE POLICY "icoder_control_plane_read" ON "{table}" '
            f"FOR SELECT USING ({owner_expression})"
        )
    audit_owner_expression = (
        "current_user = pg_get_userbyid((SELECT relowner FROM pg_class "
        "WHERE oid = 'public.audit_logs'::regclass))"
    )
    op.execute(
        'CREATE POLICY "icoder_system_audit_insert" ON "audit_logs" '
        f"FOR INSERT WITH CHECK (organization_id IS NULL AND "
        "tenancy_classification = 'MODERN_SYSTEM' AND "
        "tenancy_attribution_source = 'security_event' AND "
        "tenancy_attribution_confidence = 'verified' AND "
        f"{audit_owner_expression})"
    )
    _create_bootstrap_functions()


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    for function, signature in (
        ("icoder_write_system_audit", "jsonb"),
        ("icoder_partner_origin_allowed", "text"),
        ("icoder_resolve_invite_tenant", "text"),
        ("icoder_resolve_oauth_client_tenant", "text"),
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}({signature})")
    op.execute('DROP POLICY IF EXISTS "icoder_system_audit_insert" ON audit_logs')
    for table in ("organization_invites", "oauth_clients"):
        op.execute(
            f'DROP POLICY IF EXISTS "icoder_control_plane_read" ON "{table}"'
        )
    for table in reversed(TENANT_TABLES + SPLIT_POLICY_TABLES):
        op.execute(f'DROP POLICY IF EXISTS "{POLICY_NAME}" ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')

    op.drop_constraint(
        "fk_organization_invite_deliveries_invite_scope",
        "organization_invite_deliveries",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "organization_invite_deliveries_invite_id_fkey",
        "organization_invite_deliveries",
        "organization_invites",
        ["invite_id"],
        ["id"],
    )
    op.drop_constraint(
        "uq_organization_invites_org_id", "organization_invites", type_="unique"
    )
    op.drop_constraint(
        "fk_oauth_tokens_client_scope", "oauth_tokens", type_="foreignkey"
    )
    op.drop_constraint(
        "uq_oauth_clients_org_client_id", "oauth_clients", type_="unique"
    )
    for table in ("api_keys", "oauth_clients", "oauth_tokens", "team_invites", "team_members"):
        op.execute(
            f'ALTER TABLE "{table}" ALTER COLUMN organization_id DROP NOT NULL'
        )
