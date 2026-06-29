"""Templates API tests — Corti parity for /templates (Beta) page.

Covers:
* list with pagination + search + category + language filter
* built-in templates seeded for the test user's org
* create custom → 201 + returns id
* get existing → 200
* delete custom → 204
* delete built-in → 403 TEMPLATE_BUILTIN_PROTECTED
"""
from __future__ import annotations

import sys
import os
from urllib.parse import quote

import pytest
import pytest_asyncio

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


def _enc(t: str) -> str:
    return quote(t, safe="")


pytestmark = pytest.mark.asyncio


# Test user has organization_id = "org_default1" (hardcoded in conftest._make_mock_user).
# The seed_builtin_templates() iterates Organization objects — and the test session
# only seeds via the dev `seed()` flow which creates a NEW org. So we insert the
# built-ins directly with the test user's org_id to mirror what main.py does at
# runtime (it calls seed_builtin_templates() after the dev seed creates the org).
TEST_ORG_ID = "org_default1"


@pytest_asyncio.fixture
async def seeded_templates():
    """Insert the built-in templates directly for the test user's org,
    skipping the seed_builtin_templates() org iteration (test org is hardcoded)."""
    from app.database import async_session_factory
    from app.models.template import (
        Template, TemplateCategory, TemplateLanguage, TemplateScope,
    )
    from sqlalchemy import select as _select

    async with async_session_factory() as session:
        existing = (await session.execute(
            _select(Template).where(
                Template.organization_id == TEST_ORG_ID,
                Template.is_builtin == True,  # noqa: E712
            ).limit(1)
        )).scalar_one_or_none()
        if existing:
            return True
        for tpl in [
            ("出院小结", "inpatient", "标准出院小结"),
            ("入院记录", "inpatient", "完整入院记录"),
            ("日常病程记录", "inpatient", "SOAP格式"),
            ("术前讨论记录", "surgery", "术前讨论"),
            ("手术记录", "surgery", "手术经过"),
            ("转诊信", "outpatient", "转诊至其他科室"),
            ("门诊就诊记录", "outpatient", "通用门诊就诊"),
            ("急诊记录", "emergency", "急诊就诊记录"),
            ("会诊记录", "consultation", "科间会诊"),
        ]:
            session.add(Template(
                organization_id=TEST_ORG_ID,
                name=tpl[0],
                description=tpl[2],
                content="",
                category=TemplateCategory(tpl[1]),
                language=TemplateLanguage.ZH_CN,
                scope=TemplateScope.ALL_CUSTOMERS,
                is_builtin=True,
            ))
        await session.commit()
    return True


class TestListTemplates:
    async def test_list_after_seed_returns_builtins(self, auth_client, seeded_templates):
        r = await auth_client.get("/api/templates")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 9
        assert all(t["is_builtin"] for t in body["templates"])

    async def test_list_search_filters_by_name(self, auth_client, seeded_templates):
        r = await auth_client.get("/api/templates", params={"search": "出院"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] >= 1
        names = [t["name"] for t in body["templates"]]
        assert "出院小结" in names

    async def test_list_category_filter(self, auth_client, seeded_templates):
        r = await auth_client.get("/api/templates", params={"category": "surgery"})
        assert r.status_code == 200, r.text
        body = r.json()
        for t in body["templates"]:
            assert t["category"] == "surgery"

    async def test_list_language_filter(self, auth_client, seeded_templates):
        r = await auth_client.get("/api/templates", params={"language": "zh-CN"})
        assert r.status_code == 200, r.text
        body = r.json()
        for t in body["templates"]:
            assert t["language"] == "zh-CN"


class TestCreateTemplate:
    async def test_create_custom_returns_201(self, auth_client):
        r = await auth_client.post(
            "/api/templates",
            json={
                "name": "My Custom Template",
                "description": "Used for testing",
                "content": "请生成以下内容：",
                "category": "custom",
                "language": "zh-CN",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["name"] == "My Custom Template"
        assert body["is_builtin"] is False
        assert body["id"]

    async def test_create_default_category_is_custom(self, auth_client):
        r = await auth_client.post(
            "/api/templates",
            json={"name": "Bare Minimum"},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["category"] == "custom"
        assert body["language"] == "zh-CN"


class TestGetTemplate:
    async def test_get_returns_200(self, auth_client):
        create = await auth_client.post(
            "/api/templates",
            json={"name": "Get Test", "content": "x"},
        )
        assert create.status_code == 201, create.text
        tid = create.json()["id"]
        r = await auth_client.get(f"/api/templates/{_enc(tid)}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == tid
        assert body["name"] == "Get Test"

    async def test_get_unknown_returns_404(self, auth_client):
        r = await auth_client.get("/api/templates/does-not-exist")
        assert r.status_code == 404, r.text
        body = r.json()
        assert body["detail"]["error_code"] == "TEMPLATE_NOT_FOUND"


class TestDeleteTemplate:
    async def test_delete_custom_returns_204(self, auth_client):
        create = await auth_client.post(
            "/api/templates",
            json={"name": "Delete Me", "content": ""},
        )
        assert create.status_code == 201, create.text
        tid = create.json()["id"]
        r = await auth_client.delete(f"/api/templates/{_enc(tid)}")
        assert r.status_code == 204, r.text

    async def test_delete_builtin_returns_403(self, auth_client, seeded_templates):
        # grab any built-in from the seeded list
        r = await auth_client.get("/api/templates", params={"page_size": 1})
        assert r.status_code == 200, r.text
        first = r.json()["templates"][0]
        assert first["is_builtin"] is True
        d = await auth_client.delete(f"/api/templates/{_enc(first['id'])}")
        assert d.status_code == 403, d.text
        body = d.json()
        assert body["detail"]["error_code"] == "TEMPLATE_BUILTIN_PROTECTED"

    async def test_delete_unknown_returns_404(self, auth_client):
        r = await auth_client.delete("/api/templates/never-existed")
        assert r.status_code == 404, r.text