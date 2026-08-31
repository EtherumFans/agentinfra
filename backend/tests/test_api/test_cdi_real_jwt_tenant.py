"""Regression coverage for CDI tenant resolution through a real user JWT."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from app.models.cdi_case import CDICaseModel


@pytest.mark.asyncio
async def test_real_jwt_org_claim_scopes_cdi_persistence(
    client,
    needs_auth,
    monkeypatch,
) -> None:
    """CDI must use the validated JWT organization, not a User-only attribute."""

    monkeypatch.setenv("ICODER_CDI_FORCE_STUB_FOR_TESTS", "1")
    suffix = uuid.uuid4().hex[:10]
    register = await client.post(
        "/api/auth/register",
        json={
            "username": f"cdi-jwt-{suffix}",
            "email": f"cdi-jwt-{suffix}@example.com",
            "password": "CdiJwt!2026",
            "full_name": "CDI JWT Tenant Test",
            # Public registration is intentionally least-privilege. CDI only
            # requires an authenticated organization member for this flow.
            "role": "coder",
            "organization_name": f"CDI JWT Org {suffix}",
        },
    )
    assert register.status_code == 201, register.text
    auth = register.json()
    org_id = auth["current_org_id"]
    assert org_id

    case_id = f"CASE-JWT-{suffix}"
    run = await client.post(
        "/api/v1/cdi/runs",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
        json={
            "case_id": case_id,
            "chart_excerpt": "入院记录：肺炎，严重程度未明确。",
        },
    )
    assert run.status_code == 200, run.text

    from app import database as database_module

    async with database_module.async_session_factory() as session:
        persisted_org_id = (
            await session.execute(
                select(CDICaseModel.organization_id).where(CDICaseModel.id == case_id)
            )
        ).scalar_one()
    assert persisted_org_id == org_id

    read_back = await client.get(
        f"/api/v1/cdi/runs/{case_id}",
        headers={"Authorization": f"Bearer {auth['access_token']}"},
    )
    assert read_back.status_code == 200, read_back.text
    assert read_back.json()["case_id"] == case_id
