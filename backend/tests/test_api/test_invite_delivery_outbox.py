"""End-to-end security and reliability coverage for invitation delivery."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import threading
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select


def _uid() -> str:
    return uuid.uuid4().hex[:10]


async def _register(client, label: str) -> dict:
    suffix = _uid()
    response = await client.post(
        "/api/auth/register",
        json={
            "username": f"{label}-{suffix}",
            "email": f"{label}-{suffix}@example.com",
            "password": "SecurePass123!",
            "full_name": f"{label} {suffix}",
            "role": "coder",
            "organization_name": f"{label} Org {suffix}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def webhook_settings(monkeypatch):
    from app.config import settings

    key = Fernet.generate_key().decode("ascii")
    bearer = "test-invite-webhook-bearer-token-1234567890"
    monkeypatch.setenv("ICODER_PHI_ENCRYPTION_KEY", key)
    monkeypatch.setattr(settings, "ICODER_DEPLOYMENT_MODE", "local")
    monkeypatch.setattr(settings, "ICODER_INVITE_DELIVERY_MODE", "webhook")
    monkeypatch.setattr(settings, "ICODER_INVITE_WEBHOOK_URL", "http://127.0.0.1:9/invitations")
    monkeypatch.setattr(settings, "ICODER_INVITE_WEBHOOK_BEARER_TOKEN", bearer)
    monkeypatch.setattr(settings, "ICODER_INVITE_ALLOWED_EMAIL_DOMAINS", ["example.com"])
    monkeypatch.setattr(settings, "ICODER_INVITE_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "ICODER_INVITE_RETRY_BASE_SECONDS", 1)
    monkeypatch.setattr(settings, "ICODER_INVITE_CLAIM_TIMEOUT_SECONDS", 10)
    monkeypatch.setattr(settings, "ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS", 2.0)
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://console.test.example.com"])
    return bearer


class _CaptureHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - stdlib callback name
        length = int(self.headers.get("Content-Length", "0"))
        self.server.captured_body = self.rfile.read(length)  # type: ignore[attr-defined]
        self.server.captured_headers = dict(self.headers.items())  # type: ignore[attr-defined]
        self.send_response(202)
        self.send_header("X-Message-ID", "provider-message-test-001")
        self.end_headers()

    def log_message(self, _format, *_args):
        return


@pytest.mark.asyncio
async def test_webhook_invite_is_encrypted_signed_delivered_and_accepted(
    client, needs_auth, webhook_settings, monkeypatch
):
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models.organization import OrganizationInvite, OrganizationInviteDelivery
    from app.services.invite_delivery import claim_due_deliveries, process_delivery_claim
    from app.services.phi_encryption import decrypt_phi, is_encrypted_value

    server = ThreadingHTTPServer(("127.0.0.1", 0), _CaptureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(
        settings,
        "ICODER_INVITE_WEBHOOK_URL",
        f"http://127.0.0.1:{server.server_port}/invitations",
    )
    try:
        owner = await _register(client, "webhook-owner")
        invitee = await _register(client, "webhook-invitee")
        org_id = owner["current_org_id"]
        created = await client.post(
            f"/api/organizations/{org_id}/invites",
            headers=_headers(owner["access_token"]),
            json={"email": invitee["user"]["email"], "role": "member"},
        )
        assert created.status_code == 201, created.text
        assert created.json()["delivery"] == "queued"
        assert "invite_token" not in created.json()
        assert created.headers["cache-control"] == "no-store"
        invite_id = created.json()["invite_id"]

        async with AsyncSessionLocal() as db:
            invite = (
                await db.execute(select(OrganizationInvite).where(OrganizationInvite.id == invite_id))
            ).scalar_one()
            delivery = (
                await db.execute(
                    select(OrganizationInviteDelivery).where(
                        OrganizationInviteDelivery.invite_id == invite_id
                    )
                )
            ).scalar_one()
            assert is_encrypted_value(delivery.encrypted_payload)
            payload = json.loads(decrypt_phi(delivery.encrypted_payload))
            raw_token = payload["accept_url"].split("#token=", 1)[1]
            assert urlparse(payload["accept_url"]).query == ""
            assert payload["accept_url"].startswith("https://console.test.example.com/")
            assert invite.token == hashlib.sha256(raw_token.encode()).hexdigest()
            assert raw_token not in delivery.encrypted_payload

        listed = await client.get(
            f"/api/organizations/{org_id}/invites",
            headers=_headers(owner["access_token"]),
        )
        assert listed.status_code == 200
        assert listed.json()[0]["delivery_status"] == "queued"
        assert raw_token not in listed.text

        async with AsyncSessionLocal() as db:
            claims = await claim_due_deliveries(db, limit=1)
        assert len(claims) == 1
        async with AsyncSessionLocal() as db:
            assert await process_delivery_claim(db, claims[0]) == "delivered"

        body = server.captured_body  # type: ignore[attr-defined]
        captured_headers = {
            key.casefold(): value
            for key, value in server.captured_headers.items()  # type: ignore[attr-defined]
        }
        timestamp = captured_headers["x-icoder-timestamp"]
        expected = hmac.new(
            webhook_settings.encode(),
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        assert captured_headers["authorization"] == f"Bearer {webhook_settings}"
        assert captured_headers["x-icoder-signature"] == f"sha256={expected}"
        assert captured_headers["idempotency-key"].startswith("invite-delivery-")
        assert json.loads(body)["recipient_email"] == invitee["user"]["email"]

        async with AsyncSessionLocal() as db:
            delivery = (
                await db.execute(
                    select(OrganizationInviteDelivery).where(
                        OrganizationInviteDelivery.invite_id == invite_id
                    )
                )
            ).scalar_one()
            assert delivery.status == "delivered"
            assert delivery.encrypted_payload == ""
            assert delivery.provider_message_id_hash == hashlib.sha256(
                b"provider-message-test-001"
            ).hexdigest()

        accepted = await client.post(
            "/api/organizations/invites/accept",
            headers=_headers(invitee["access_token"]),
            json={"token": raw_token},
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["id"] == org_id
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


class _PermanentFailureProvider:
    async def deliver(self, _payload, *, delivery_id: str):
        from app.services.invite_delivery import DeliveryResult

        assert delivery_id
        return DeliveryResult(False, False, 400, "http_400")


class _RetryableFailureProvider:
    async def deliver(self, _payload, *, delivery_id: str):
        from app.services.invite_delivery import DeliveryResult

        assert delivery_id
        return DeliveryResult(False, True, 503, "http_503")


@pytest.mark.asyncio
async def test_dead_letter_can_be_requeued_then_revoked_without_secret_exposure(
    client, needs_auth, webhook_settings
):
    from app.database import AsyncSessionLocal
    from app.models.organization import OrganizationInviteDelivery
    from app.services.invite_delivery import claim_due_deliveries, process_delivery_claim

    owner = await _register(client, "retry-owner")
    invitee = await _register(client, "retry-invitee")
    org_id = owner["current_org_id"]
    owner_headers = _headers(owner["access_token"])
    created = await client.post(
        f"/api/organizations/{org_id}/invites",
        headers=owner_headers,
        json={"email": invitee["user"]["email"], "role": "viewer"},
    )
    assert created.status_code == 201, created.text
    invite_id = created.json()["invite_id"]
    async with AsyncSessionLocal() as db:
        claims = await claim_due_deliveries(db, limit=1)
    assert len(claims) == 1
    async with AsyncSessionLocal() as db:
        outcome = await process_delivery_claim(
            db, claims[0], provider=_PermanentFailureProvider()
        )
    assert outcome == "dead_letter"

    retried = await client.post(
        f"/api/organizations/{org_id}/invites/{invite_id}/retry",
        headers=owner_headers,
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["delivery_status"] == "queued"
    assert "token" not in retried.text

    revoked = await client.delete(
        f"/api/organizations/{org_id}/invites/{invite_id}",
        headers=owner_headers,
    )
    assert revoked.status_code == 204
    async with AsyncSessionLocal() as db:
        delivery = (
            await db.execute(
                select(OrganizationInviteDelivery).where(
                    OrganizationInviteDelivery.invite_id == invite_id
                )
            )
        ).scalar_one()
        assert delivery.status == "cancelled"
        assert delivery.encrypted_payload == ""


@pytest.mark.asyncio
async def test_concurrent_workers_claim_each_delivery_at_most_once(
    client, needs_auth, webhook_settings
):
    from app.database import AsyncSessionLocal
    from app.services.invite_delivery import cancel_invite_delivery, claim_due_deliveries

    owner = await _register(client, "claim-owner")
    invitee = await _register(client, "claim-invitee")
    org_id = owner["current_org_id"]
    created = await client.post(
        f"/api/organizations/{org_id}/invites",
        headers=_headers(owner["access_token"]),
        json={"email": invitee["user"]["email"], "role": "member"},
    )
    assert created.status_code == 201, created.text

    async def worker():
        async with AsyncSessionLocal() as db:
            return await claim_due_deliveries(db, limit=1)

    first, second = await asyncio.gather(worker(), worker())
    all_claims = first + second
    assert len(all_claims) == 1
    assert len({claim.delivery_id for claim in all_claims}) == 1

    async with AsyncSessionLocal() as db:
        await cancel_invite_delivery(db, invite_id=created.json()["invite_id"])
        await db.commit()


@pytest.mark.asyncio
async def test_retry_is_bounded_and_stale_claim_is_recovered(
    client, needs_auth, webhook_settings, monkeypatch
):
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models.organization import OrganizationInviteDelivery
    from app.services.invite_delivery import claim_due_deliveries, process_delivery_claim

    monkeypatch.setattr(settings, "ICODER_INVITE_MAX_ATTEMPTS", 2)
    owner = await _register(client, "bounded-owner")
    invitee = await _register(client, "bounded-invitee")
    created = await client.post(
        f"/api/organizations/{owner['current_org_id']}/invites",
        headers=_headers(owner["access_token"]),
        json={"email": invitee["user"]["email"], "role": "member"},
    )
    assert created.status_code == 201, created.text
    invite_id = created.json()["invite_id"]

    async with AsyncSessionLocal() as db:
        delivery = (
            await db.execute(
                select(OrganizationInviteDelivery).where(
                    OrganizationInviteDelivery.invite_id == invite_id
                )
            )
        ).scalar_one()
        delivery.status = "processing"
        delivery.lock_id = "abandoned-worker"
        delivery.locked_at = datetime.now(timezone.utc) - timedelta(seconds=30)
        await db.commit()

    async with AsyncSessionLocal() as db:
        recovered = await claim_due_deliveries(db, limit=1)
    assert len(recovered) == 1
    assert recovered[0].lock_id != "abandoned-worker"
    async with AsyncSessionLocal() as db:
        assert await process_delivery_claim(
            db, recovered[0], provider=_RetryableFailureProvider()
        ) == "retry"
        delivery = (
            await db.execute(
                select(OrganizationInviteDelivery).where(
                    OrganizationInviteDelivery.invite_id == invite_id
                )
            )
        ).scalar_one()
        assert delivery.attempts == 1
        assert delivery.last_error_code == "http_503"
        assert delivery.encrypted_payload
        delivery.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        await db.commit()

    async with AsyncSessionLocal() as db:
        second_claim = await claim_due_deliveries(db, limit=1)
    assert len(second_claim) == 1
    async with AsyncSessionLocal() as db:
        assert await process_delivery_claim(
            db, second_claim[0], provider=_RetryableFailureProvider()
        ) == "dead_letter"
        delivery = (
            await db.execute(
                select(OrganizationInviteDelivery).where(
                    OrganizationInviteDelivery.invite_id == invite_id
                )
            )
        ).scalar_one()
        assert delivery.attempts == 2
        assert delivery.status == "dead_letter"
        assert delivery.encrypted_payload


@pytest.mark.asyncio
async def test_webhook_mode_rejects_unapproved_recipient_domain(
    client, needs_auth, webhook_settings
):
    owner = await _register(client, "domain-owner")
    response = await client.post(
        f"/api/organizations/{owner['current_org_id']}/invites",
        headers=_headers(owner["access_token"]),
        json={"email": f"user-{_uid()}@unapproved.example.cn", "role": "member"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVITE_EMAIL_DOMAIN_FORBIDDEN"


@pytest.mark.asyncio
async def test_operator_processor_defaults_to_secret_free_dry_run(webhook_settings):
    from scripts.process_invite_outbox import _run

    report = await _run(execute=False, limit=999)
    assert report["mode"] == "dry_run"
    assert report["limit"] == 100
    serialized = json.dumps(report)
    assert "recipient" not in serialized
    assert "token" not in serialized
    assert webhook_settings not in serialized
