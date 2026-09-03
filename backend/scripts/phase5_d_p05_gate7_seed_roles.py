"""Phase 5 Track D P0.5 Gate 7 — 4-role user seeder.

Creates (or refreshes) four dev users — one per CDI role — so the browser
walkthrough can log in as each role and verify role-gated UI + transitions.

    g7admin      ADMIN         → cdi_role = admin
    g7qc         QC            → cdi_role = cdi_specialist
    g7clinician  CLINICIAN     → cdi_role = clinician
    g7insurance  INSURANCE     → cdi_role = auditor

All four users share password: Gate7!2026

Usage:
    python scripts/phase5_d_p05_gate7_seed_roles.py

Idempotent: re-running updates existing rows in place. Dev DB only —
do NOT run against production.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys

# Ensure repo root + backend/ are importable when run as `python scripts/...`
sys.path.insert(0, ".")

# Windows console defaults to GBK; force UTF-8 so Chinese chars print cleanly.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, io.UnsupportedOperation):
        pass

from app.database import async_session_factory, init_db
from app.models.cdi_case import (  # noqa: F401  (forces import for create_all)
    CDICaseModel,
    DocumentationGapModel,
    ProviderQueryModel,
)
from app.models.organization import Organization, OrganizationMember
from app.models.user import User, UserRole
from app.middleware.auth import hash_password

PASSWORD = "Gate7!2026"
ORG_SLUG = "g7org"

# (username, email, full_name, UserRole, cdi_role_description)
_SEED = [
    ("g7admin", "g7admin@example.com", "Gate 7 Admin", UserRole.ADMIN, "管理员"),
    ("g7qc", "g7qc@example.com", "Gate 7 CDI Specialist", UserRole.QC, "CDI 专员"),
    ("g7clinician", "g7clinician@example.com", "Gate 7 Clinician", UserRole.CLINICIAN, "临床医生"),
    ("g7insurance", "g7insurance@example.com", "Gate 7 Auditor", UserRole.INSURANCE, "审计员"),
]


async def _seed(dry_run: bool = False) -> int:
    await init_db()
    async with async_session_factory() as s:
        # 1. Ensure org exists
        from sqlalchemy import select

        org = (await s.execute(select(Organization).where(Organization.slug == ORG_SLUG))).scalars().first()
        if org is None:
            org = Organization(
                id="org-g7-seed",
                name="Gate 7 Walkthrough Org",
                slug=ORG_SLUG,
                plan="free",
                settings={},
                is_active=True,
            )
            s.add(org)
            await s.flush()
        org_id = org.id

        # 2. Upsert each user
        for username, email, full_name, role_enum, _desc in _SEED:
            existing = (
                await s.execute(select(User).where(User.username == username))
            ).scalars().first()
            if existing is None:
                u = User(
                    id=f"u-g7-{username}",
                    username=username,
                    email=email,
                    hashed_password=hash_password(PASSWORD),
                    full_name=full_name,
                    role=role_enum,
                    department="CDI Gate 7 走查",
                    is_active=True,
                    is_verified=True,
                    token_version=0,
                )
                s.add(u)
            else:
                existing.hashed_password = hash_password(PASSWORD)
                existing.role = role_enum
                existing.is_active = True
                existing.is_verified = True

            # Ensure org membership
            member = (
                await s.execute(
                    select(OrganizationMember).where(
                        OrganizationMember.organization_id == org_id,
                        OrganizationMember.user_id == f"u-g7-{username}",
                    )
                )
            ).scalars().first()
            if member is None:
                s.add(OrganizationMember(
                    organization_id=org_id,
                    user_id=f"u-g7-{username}",
                    role="admin" if role_enum == UserRole.ADMIN else "member",
                    is_default=True,
                ))

        if dry_run:
            print("[dry-run] would commit 4 users + 1 org + 4 memberships")
            return 0

        await s.commit()

    # Report (ASCII-only for cross-locale terminal safety)
    from app.services.cdi_roles_notifications import platform_role_to_cdi_role

    print("=" * 60)
    print("Phase 5 Track D P0.5 Gate 7 - 4-role seed COMPLETE")
    print("=" * 60)
    print(f"Org slug: {ORG_SLUG}  (id: org-g7-seed)")
    print(f"Shared password: {PASSWORD}")
    print()
    print("Users (platform role -> CDI role):")
    for username, _email, _full, role_enum, _desc in _SEED:
        cdi_role = platform_role_to_cdi_role(role_enum.value)
        print(f"  - {username:<14} {role_enum.value:<12} -> {cdi_role}")
    print()
    print("Next: log in via the frontend with any of these users.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed 4 CDI roles for Gate 7 walkthrough")
    parser.add_argument("--dry-run", action="store_true", help="Print plan and exit without writing")
    args = parser.parse_args()
    return asyncio.run(_seed(dry_run=args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
