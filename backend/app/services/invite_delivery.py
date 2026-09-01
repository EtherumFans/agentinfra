"""Encrypted organization-invitation outbox and webhook delivery."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.organization import (
    Organization,
    OrganizationInvite,
    OrganizationInviteDelivery,
)
from app.services.phi_encryption import (
    decrypt_phi,
    encrypt_phi,
    is_encrypted_value,
    is_encryption_enabled,
)
from app.services.system_audit import tenant_owned_system_audit
from app.services.database_tenancy import bind_tenant_to_transaction


class InviteDeliveryConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeliveryClaim:
    delivery_id: str
    lock_id: str
    organization_id: str | None = None


@dataclass(frozen=True)
class DeliveryResult:
    succeeded: bool
    retryable: bool
    status_code: int | None
    error_code: str | None = None
    provider_message_id: str | None = None


def invite_delivery_mode() -> str:
    return str(settings.ICODER_INVITE_DELIVERY_MODE or "manual").strip().casefold()


def allowed_email_domains() -> frozenset[str]:
    return frozenset(
        str(domain).strip().casefold().rstrip(".")
        for domain in settings.ICODER_INVITE_ALLOWED_EMAIL_DOMAINS
        if str(domain).strip()
    )


def recipient_domain_allowed(email: str) -> bool:
    domain = email.rsplit("@", 1)[-1].strip().casefold().rstrip(".")
    allowed = allowed_email_domains()
    return not allowed or domain in allowed


def validate_webhook_configuration() -> None:
    if invite_delivery_mode() != "webhook":
        raise InviteDeliveryConfigurationError("invitation delivery mode is not webhook")
    if not is_encryption_enabled():
        raise InviteDeliveryConfigurationError("invitation webhook outbox requires at-rest encryption")
    parsed = urlparse(str(settings.ICODER_INVITE_WEBHOOK_URL or ""))
    allowed_schemes = {"https"}
    if settings.ICODER_DEPLOYMENT_MODE == "local":
        allowed_schemes.add("http")
    if (
        parsed.scheme not in allowed_schemes
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise InviteDeliveryConfigurationError("invalid invitation webhook URL")
    token = str(settings.ICODER_INVITE_WEBHOOK_BEARER_TOKEN or "").strip()
    if not 32 <= len(token) <= 512:
        raise InviteDeliveryConfigurationError("invalid invitation webhook bearer token")
    domains = allowed_email_domains()
    if not domains or any(
        not re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
            r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
            domain,
        )
        for domain in domains
    ):
        raise InviteDeliveryConfigurationError("invitation email-domain allowlist is empty")
    if not 1 <= int(settings.ICODER_INVITE_MAX_ATTEMPTS) <= 20:
        raise InviteDeliveryConfigurationError("invalid invitation delivery max attempts")
    if not 1 <= int(settings.ICODER_INVITE_RETRY_BASE_SECONDS) <= 3600:
        raise InviteDeliveryConfigurationError("invalid invitation retry base")
    if not 10 <= int(settings.ICODER_INVITE_CLAIM_TIMEOUT_SECONDS) <= 3600:
        raise InviteDeliveryConfigurationError("invalid invitation claim timeout")
    if not 0.1 <= float(settings.ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS) <= 60.0:
        raise InviteDeliveryConfigurationError("invalid invitation webhook timeout")


def build_invite_payload(
    *,
    invite: OrganizationInvite,
    organization: Organization,
    raw_token: str,
) -> dict:
    # CORS_ORIGINS is the configured browser application origin; the hosted
    # URL is the API endpoint and must not receive a fragment-only credential.
    base_url = str((settings.CORS_ORIGINS or ["http://localhost:5173"])[0]).rstrip("/")
    return {
        "schema_version": "icoder.organization-invite-delivery/v1",
        "invite_id": invite.id,
        "organization_id": organization.id,
        "organization_name": organization.name,
        "recipient_email": invite.email,
        "role": invite.role.value,
        "expires_at": invite.expires_at.isoformat(),
        # Fragment avoids sending the credential to the frontend web server.
        "accept_url": f"{base_url}/accept-invite#token={raw_token}",
    }


async def enqueue_invite_delivery(
    db: AsyncSession,
    *,
    invite: OrganizationInvite,
    organization: Organization,
    raw_token: str,
) -> OrganizationInviteDelivery:
    validate_webhook_configuration()
    payload = build_invite_payload(invite=invite, organization=organization, raw_token=raw_token)
    encrypted = encrypt_phi(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    if not encrypted or not is_encrypted_value(encrypted):
        raise InviteDeliveryConfigurationError("invitation payload encryption failed closed")
    row = OrganizationInviteDelivery(
        organization_id=invite.organization_id,
        invite_id=invite.id,
        encrypted_payload=encrypted,
        status="queued",
        attempts=0,
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(row)
    await db.flush()
    return row


async def cancel_invite_delivery(
    db: AsyncSession,
    *,
    invite_id: str,
    status: str = "cancelled",
) -> None:
    row = (
        await db.execute(
            select(OrganizationInviteDelivery).where(
                OrganizationInviteDelivery.invite_id == invite_id
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return
    if row.status != "delivered":
        row.status = status
    row.encrypted_payload = ""
    row.lock_id = None
    row.locked_at = None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


async def claim_due_deliveries(
    db: AsyncSession,
    *,
    limit: int = 20,
) -> list[DeliveryClaim]:
    validate_webhook_configuration()
    limit = max(1, min(int(limit), 100))
    now = datetime.now(timezone.utc)
    stale_before = now - timedelta(seconds=int(settings.ICODER_INVITE_CLAIM_TIMEOUT_SECONDS))
    due = or_(
        (
            OrganizationInviteDelivery.status.in_(["queued", "retry"])
            & (OrganizationInviteDelivery.next_attempt_at <= now)
        ),
        (
            (OrganizationInviteDelivery.status == "processing")
            & (OrganizationInviteDelivery.locked_at <= stale_before)
        ),
    )
    claims: list[DeliveryClaim] = []
    if db.get_bind().dialect.name == "postgresql":
        tenant_ids: list[str | None] = list(
            (await db.execute(select(Organization.id))).scalars().all()
        )
    else:
        tenant_ids = [None]

    for organization_id in tenant_ids:
        if organization_id:
            await bind_tenant_to_transaction(db, organization_id)
        candidate_ids = (
            await db.execute(
                select(OrganizationInviteDelivery.id)
                .where(due)
                .order_by(
                    OrganizationInviteDelivery.next_attempt_at,
                    OrganizationInviteDelivery.created_at,
                )
                .limit(limit * 3)
            )
        ).scalars().all()
        for delivery_id in candidate_ids:
            lock_id = secrets.token_hex(16)
            claimed = await db.execute(
                update(OrganizationInviteDelivery)
                .where(OrganizationInviteDelivery.id == delivery_id, due)
                .values(status="processing", locked_at=now, lock_id=lock_id)
            )
            if claimed.rowcount == 1:
                claims.append(
                    DeliveryClaim(
                        delivery_id=delivery_id,
                        lock_id=lock_id,
                        organization_id=organization_id,
                    )
                )
                if len(claims) >= limit:
                    break
        await db.commit()
        if len(claims) >= limit:
            break
    return claims


class WebhookInviteProvider:
    async def deliver(self, payload: dict, *, delivery_id: str) -> DeliveryResult:
        validate_webhook_configuration()
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
        timestamp = str(int(time.time()))
        credential = settings.ICODER_INVITE_WEBHOOK_BEARER_TOKEN.strip()
        signature = hmac.new(
            credential.encode("utf-8"),
            timestamp.encode("ascii") + b"." + body,
            hashlib.sha256,
        ).hexdigest()
        headers = {
            "Authorization": f"Bearer {credential}",
            "Content-Type": "application/json",
            "Idempotency-Key": f"invite-delivery-{delivery_id}",
            "X-iCoDer-Timestamp": timestamp,
            "X-iCoDer-Signature": f"sha256={signature}",
        }
        try:
            async with httpx.AsyncClient(
                timeout=float(settings.ICODER_INVITE_WEBHOOK_TIMEOUT_SECONDS),
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    settings.ICODER_INVITE_WEBHOOK_URL,
                    content=body,
                    headers=headers,
                )
        except (httpx.TimeoutException, httpx.NetworkError):
            return DeliveryResult(False, True, None, "network_error")

        message_id = response.headers.get("X-Message-ID")
        if 200 <= response.status_code < 300:
            return DeliveryResult(True, False, response.status_code, provider_message_id=message_id)
        if response.status_code in {408, 425, 429} or response.status_code >= 500:
            return DeliveryResult(False, True, response.status_code, f"http_{response.status_code}")
        return DeliveryResult(False, False, response.status_code, f"http_{response.status_code}")


def _retry_delay_seconds(delivery_id: str, attempts: int) -> int:
    base = int(settings.ICODER_INVITE_RETRY_BASE_SECONDS)
    exponential = min(3600, base * (2 ** max(0, attempts - 1)))
    fraction = int(hashlib.sha256(f"{delivery_id}:{attempts}".encode()).hexdigest()[:4], 16) / 65535
    return max(1, int(exponential * (1.0 + 0.25 * fraction)))


async def process_delivery_claim(
    db: AsyncSession,
    claim: DeliveryClaim,
    *,
    provider: WebhookInviteProvider | None = None,
) -> str:
    if claim.organization_id:
        await bind_tenant_to_transaction(db, claim.organization_id)
    row = (
        await db.execute(
            select(OrganizationInviteDelivery).where(
                OrganizationInviteDelivery.id == claim.delivery_id,
                OrganizationInviteDelivery.status == "processing",
                OrganizationInviteDelivery.lock_id == claim.lock_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return "claim_lost"
    invite = (
        await db.execute(select(OrganizationInvite).where(OrganizationInvite.id == row.invite_id))
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if invite is None or invite.status != "pending" or _as_utc(invite.expires_at) <= now:
        if invite is not None and invite.status == "pending":
            invite.status = "expired"
        row.status = "cancelled"
        row.encrypted_payload = ""
        row.lock_id = None
        row.locked_at = None
        await db.commit()
        return "cancelled"

    try:
        plaintext = decrypt_phi(row.encrypted_payload)
        payload = json.loads(plaintext or "")
        if payload.get("schema_version") != "icoder.organization-invite-delivery/v1":
            raise ValueError("unsupported payload")
    except Exception:
        row.status = "dead_letter"
        row.attempts += 1
        row.last_error_code = "payload_decrypt_failed"
        row.lock_id = None
        row.locked_at = None
        await tenant_owned_system_audit(
            db,
            organization_id=row.organization_id,
            action="org.invite.delivery_dead_letter",
            resource_type="organization_invite_delivery",
            resource_id=row.id,
            details={"attempts": row.attempts, "error_code": row.last_error_code},
        )
        await db.commit()
        return "dead_letter"

    result = await (provider or WebhookInviteProvider()).deliver(payload, delivery_id=row.id)
    row.attempts += 1
    row.lock_id = None
    row.locked_at = None
    if result.succeeded:
        row.status = "delivered"
        row.delivered_at = now
        row.last_error_code = None
        row.encrypted_payload = ""
        if result.provider_message_id:
            row.provider_message_id_hash = hashlib.sha256(
                result.provider_message_id.encode("utf-8")
            ).hexdigest()
        await tenant_owned_system_audit(
            db,
            organization_id=row.organization_id,
            action="org.invite.delivery_succeeded",
            resource_type="organization_invite_delivery",
            resource_id=row.id,
            details={"attempts": row.attempts, "status_code": result.status_code},
        )
        outcome = "delivered"
    elif result.retryable and row.attempts < int(settings.ICODER_INVITE_MAX_ATTEMPTS):
        delay = _retry_delay_seconds(row.id, row.attempts)
        row.status = "retry"
        row.next_attempt_at = now + timedelta(seconds=delay)
        row.last_error_code = result.error_code or "retryable_failure"
        await tenant_owned_system_audit(
            db,
            organization_id=row.organization_id,
            action="org.invite.delivery_retry_scheduled",
            resource_type="organization_invite_delivery",
            resource_id=row.id,
            details={
                "attempts": row.attempts,
                "status_code": result.status_code,
                "error_code": row.last_error_code,
                "retry_delay_seconds": delay,
            },
        )
        outcome = "retry"
    else:
        row.status = "dead_letter"
        row.last_error_code = result.error_code or "permanent_failure"
        await tenant_owned_system_audit(
            db,
            organization_id=row.organization_id,
            action="org.invite.delivery_dead_letter",
            resource_type="organization_invite_delivery",
            resource_id=row.id,
            details={
                "attempts": row.attempts,
                "status_code": result.status_code,
                "error_code": row.last_error_code,
            },
        )
        outcome = "dead_letter"
    await db.commit()
    return outcome


async def requeue_dead_letter(db: AsyncSession, *, invite_id: str) -> OrganizationInviteDelivery | None:
    row = (
        await db.execute(
            select(OrganizationInviteDelivery).where(
                OrganizationInviteDelivery.invite_id == invite_id,
                OrganizationInviteDelivery.status == "dead_letter",
            )
        )
    ).scalar_one_or_none()
    if row is None or not row.encrypted_payload:
        return None
    row.status = "queued"
    row.attempts = 0
    row.next_attempt_at = datetime.now(timezone.utc)
    row.last_error_code = None
    row.lock_id = None
    row.locked_at = None
    await db.flush()
    return row


__all__ = [
    "DeliveryClaim",
    "DeliveryResult",
    "InviteDeliveryConfigurationError",
    "WebhookInviteProvider",
    "allowed_email_domains",
    "cancel_invite_delivery",
    "claim_due_deliveries",
    "enqueue_invite_delivery",
    "invite_delivery_mode",
    "process_delivery_claim",
    "recipient_domain_allowed",
    "requeue_dead_letter",
    "validate_webhook_configuration",
]
