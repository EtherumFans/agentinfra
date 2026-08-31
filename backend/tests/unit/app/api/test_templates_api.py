"""Templates API tests — Corti parity for /templates (Beta) page.

Covers:
* list with pagination + search + category + language filter
* built-in templates seeded for the test user's org
* create custom → 201 + returns id
* get existing → 200
* update custom → 200; built-in protected
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
        builtins = [t for t in body["templates"] if t["is_builtin"]]
        assert len(builtins) >= 9
        assert "出院小结" in {t["name"] for t in builtins}

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

    async def test_create_blank_name_is_422(self, auth_client):
        response = await auth_client.post("/api/templates", json={"name": "   "})
        assert response.status_code == 422, response.text


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


class TestUpdateTemplate:
    async def test_update_custom_returns_200(self, auth_client):
        create = await auth_client.post(
            "/api/templates",
            json={"name": "Update Me", "content": "old"},
        )
        assert create.status_code == 201, create.text
        tid = create.json()["id"]
        response = await auth_client.patch(
            f"/api/templates/{_enc(tid)}",
            json={
                "name": "Updated Template",
                "content": "new",
                "language": "en-US",
                "category": "outpatient",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["name"] == "Updated Template"
        assert body["content"] == "new"
        assert body["language"] == "en-US"
        assert body["category"] == "outpatient"

    async def test_update_empty_payload_is_422(self, auth_client):
        create = await auth_client.post("/api/templates", json={"name": "No-op"})
        tid = create.json()["id"]
        response = await auth_client.patch(f"/api/templates/{_enc(tid)}", json={})
        assert response.status_code == 422, response.text

    @pytest.mark.parametrize("payload", [{"name": "   "}, {"content": None}])
    async def test_update_blank_or_null_field_is_422(self, auth_client, payload):
        create = await auth_client.post("/api/templates", json={"name": "Strict update"})
        tid = create.json()["id"]
        response = await auth_client.patch(f"/api/templates/{_enc(tid)}", json=payload)
        assert response.status_code == 422, response.text

    async def test_update_builtin_returns_403(self, auth_client, seeded_templates):
        listed = await auth_client.get("/api/templates", params={"page_size": 1})
        builtin = listed.json()["templates"][0]
        response = await auth_client.patch(
            f"/api/templates/{_enc(builtin['id'])}", json={"name": "Forbidden"}
        )
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["error_code"] == "TEMPLATE_BUILTIN_PROTECTED"

    async def test_update_unknown_returns_404(self, auth_client):
        response = await auth_client.patch(
            "/api/templates/never-existed", json={"name": "Unknown"}
        )
        assert response.status_code == 404, response.text


class TestPublishTemplate:
    async def test_publish_appends_immutable_versions_and_surfaces_latest(self, auth_client):
        created = await auth_client.post(
            "/api/templates",
            json={"name": "Versioned", "content": "first prompt"},
        )
        template_id = created.json()["id"]

        first = await auth_client.post(f"/api/templates/{_enc(template_id)}/publish")
        assert first.status_code == 201, first.text
        assert first.json()["version_number"] == 0
        assert first.json()["generation"]["instructions"]["prompt"] == "first prompt"

        updated = await auth_client.patch(
            f"/api/templates/{_enc(template_id)}", json={"content": "second prompt"}
        )
        assert updated.status_code == 200, updated.text
        second = await auth_client.post(f"/api/templates/{_enc(template_id)}/publish")
        assert second.status_code == 201, second.text
        assert second.json()["version_number"] == 1

        versions = await auth_client.get(f"/api/templates/{_enc(template_id)}/versions")
        assert versions.status_code == 200, versions.text
        assert [row["version_number"] for row in versions.json()] == [1, 0]
        immutable_first = await auth_client.get(
            f"/api/templates/{_enc(template_id)}/versions/{_enc(first.json()['id'])}"
        )
        assert immutable_first.status_code == 200, immutable_first.text
        assert immutable_first.json()["generation"]["instructions"]["prompt"] == "first prompt"

        current = await auth_client.get(f"/api/templates/{_enc(template_id)}")
        assert current.json()["published_version_count"] == 2
        assert current.json()["published_version"]["id"] == second.json()["id"]

    async def test_publish_normalizes_builder_generation(self, auth_client):
        content = '{"instructions":{"prompt":"grounded"},"sections":[{"sectionId":"10000001-aaaa-4c01-8c01-100000000001","heading":"Chief complaint","instructions":{"contentPrompt":"Grounded only"}}]}'
        created = await auth_client.post(
            "/api/templates", json={"name": "Builder draft", "content": content}
        )
        published = await auth_client.post(
            f"/api/templates/{_enc(created.json()['id'])}/publish"
        )
        assert published.status_code == 201, published.text
        generation = published.json()["generation"]
        assert generation["instructions"]["prompt"] == "grounded"
        assert generation["sections"][0]["id"] == "10000001-aaaa-4c01-8c01-100000000001"
        assert generation["sections"][0]["name"] == "Chief complaint"
        assert generation["sections"][0]["languages"] == ["zh-CN"]

    async def test_v2_published_filter_tracks_explicit_publication(self, auth_client):
        created = await auth_client.post(
            "/api/templates", json={"name": "Discovery draft", "content": "safe"}
        )
        template_id = created.json()["id"]
        drafts = (await auth_client.get(
            "/api/v2/tools/templates/?source=user&published=false"
        )).json()
        assert any(row["name"] == "Discovery draft" for row in drafts)
        published_before = (await auth_client.get(
            "/api/v2/tools/templates/?source=user&published=true"
        )).json()
        assert all(row["name"] != "Discovery draft" for row in published_before)

        version = await auth_client.post(f"/api/templates/{_enc(template_id)}/publish")
        assert version.status_code == 201, version.text
        published_after = (await auth_client.get(
            "/api/v2/tools/templates/?source=user&published=true"
        )).json()
        row = next(row for row in published_after if row["name"] == "Discovery draft")
        assert row["publishedVersion"]["id"] == version.json()["id"]
        assert row["publishedVersion"]["versionNumber"] == 0

    async def test_v2_publish_accepts_only_opaque_public_id(self, auth_client):
        created = await auth_client.post(
            "/api/templates", json={"name": "Public publish", "content": "safe"}
        )
        legacy_id = created.json()["id"]
        discovered = (await auth_client.get(
            "/api/v2/tools/templates/?source=user&published=false"
        )).json()
        public_id = next(row["id"] for row in discovered if row["name"] == "Public publish")

        rejected = await auth_client.post(
            f"/api/v2/tools/templates/{_enc(legacy_id)}/publish"
        )
        assert rejected.status_code == 404, rejected.text
        published = await auth_client.post(
            f"/api/v2/tools/templates/{_enc(public_id)}/publish"
        )
        assert published.status_code == 201, published.text
        assert published.json()["versionNumber"] == 0

    async def test_builtin_publish_is_product_managed(self, auth_client, seeded_templates):
        listed = await auth_client.get("/api/templates", params={"page_size": 1})
        builtin = listed.json()["templates"][0]
        response = await auth_client.post(
            f"/api/templates/{_enc(builtin['id'])}/publish"
        )
        assert response.status_code == 403, response.text
        assert response.json()["detail"]["error_code"] == "TEMPLATE_BUILTIN_PROTECTED"

    async def test_version_lookup_fails_closed_across_tenants(self, auth_client):
        from app.database import async_session_factory
        from app.models.template import Template, TemplateVersion
        from app.models.template import TemplateCategory, TemplateLanguage, TemplateScope
        import json

        async with async_session_factory() as db:
            foreign = Template(
                organization_id="foreign_org",
                name="Foreign",
                description="",
                content="secret",
                category=TemplateCategory.CUSTOM,
                language=TemplateLanguage.ZH_CN,
                scope=TemplateScope.ALL_CUSTOMERS,
                is_builtin=False,
            )
            db.add(foreign)
            await db.flush()
            version = TemplateVersion(
                organization_id="foreign_org",
                template_id=foreign.id,
                version_number=0,
                generation_json=json.dumps({"instructions": {"prompt": "secret"}}),
                snapshot_json="{}",
            )
            db.add(version)
            await db.commit()
            foreign_id, version_id = foreign.id, version.id
        response = await auth_client.get(
            f"/api/templates/{_enc(foreign_id)}/versions/{_enc(version_id)}"
        )
        assert response.status_code == 404, response.text

    async def test_deleted_template_versions_are_not_publicly_readable(self, auth_client):
        created = await auth_client.post(
            "/api/templates", json={"name": "Deleted version", "content": "private"}
        )
        template_id = created.json()["id"]
        published = await auth_client.post(f"/api/templates/{_enc(template_id)}/publish")
        version_id = published.json()["id"]
        assert (await auth_client.delete(f"/api/templates/{_enc(template_id)}")).status_code == 204
        response = await auth_client.get(
            f"/api/templates/{_enc(template_id)}/versions/{_enc(version_id)}"
        )
        assert response.status_code == 404, response.text


class TestDeleteTemplate:
    async def test_delete_custom_returns_204(self, auth_client):
        from app.database import async_session_factory
        from app.models.template import Template

        create = await auth_client.post(
            "/api/templates",
            json={"name": "Delete Me", "content": ""},
        )
        assert create.status_code == 201, create.text
        tid = create.json()["id"]
        r = await auth_client.delete(f"/api/templates/{_enc(tid)}")
        assert r.status_code == 204, r.text

        assert (await auth_client.get(f"/api/templates/{_enc(tid)}")).status_code == 404
        listed = await auth_client.get("/api/templates", params={"search": "Delete Me"})
        assert listed.status_code == 200, listed.text
        assert all(item["id"] != tid for item in listed.json()["templates"])

        async with async_session_factory() as db:
            row = await db.get(Template, tid)
            assert row is not None
            assert row.deleted_at is not None

    async def test_deleted_custom_is_absent_from_v2_discovery(self, auth_client):
        created = await auth_client.post(
            "/api/templates", json={"name": "V2 soft delete", "content": "{}"}
        )
        assert created.status_code == 201, created.text
        legacy_id = created.json()["id"]

        before = await auth_client.get("/api/v2/tools/templates/")
        assert before.status_code == 200, before.text
        public_id = next(
            item["id"] for item in before.json() if item["name"] == "V2 soft delete"
        )

        deleted = await auth_client.delete(f"/api/templates/{_enc(legacy_id)}")
        assert deleted.status_code == 204, deleted.text
        after = await auth_client.get("/api/v2/tools/templates/")
        assert after.status_code == 200, after.text
        assert all(item["id"] != public_id for item in after.json())
        assert (
            await auth_client.get(f"/api/v2/tools/templates/{_enc(public_id)}")
        ).status_code == 404

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


class TestTemplateAudit:
    async def test_create_update_delete_emit_audit_events(self, auth_client):
        from app.database import async_session_factory
        from app.models.audit_log import AuditLog
        from sqlalchemy import select

        created = await auth_client.post(
            "/api/templates", json={"name": "Audited template", "content": "initial"}
        )
        assert created.status_code == 201, created.text
        template_id = created.json()["id"]
        updated = await auth_client.patch(
            f"/api/templates/{_enc(template_id)}", json={"content": "updated"}
        )
        assert updated.status_code == 200, updated.text
        deleted = await auth_client.delete(f"/api/templates/{_enc(template_id)}")
        assert deleted.status_code == 204, deleted.text

        async with async_session_factory() as db:
            actions = list((await db.scalars(select(AuditLog.action).where(
                AuditLog.resource_id == template_id
            ))).all())
        assert "template.create" in actions
        assert "template.update" in actions
        assert "template.delete" in actions
