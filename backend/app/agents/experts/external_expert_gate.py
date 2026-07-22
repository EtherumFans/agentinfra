"""External-Expert Gate — central policy check for external-touching Experts.

Five Corti §3.2 Experts reach outside iCoDer's trust boundary:

  pubmed / clinical-trials / drugbank / posos / web-search

Each of these needs a licence / egress / region check before any live
call is dispatched. A1B-AE.7 centralizes that check here so individual
Experts stay thin.

The gate is hermetic in A1B-AE.7 — no live call is ever made. The
return value tells the caller what *would* be allowed and why, so
runtime callers can surface a clear "deferred" notice instead of a
silent 200 with empty data.

Authority:
- Charter §6 — egress policy (region routing + Provider credentials)
- A1B-AE.1 §3.2 — 5 external Experts are CORTI_REFERENCE / CORTI_ADAPTED
- Charter Amendment 1 §7 — provenance discipline (no silent fallback)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


GATED_EXPERTS = frozenset(
    {
        "pubmed",
        "clinical-trials",
        "drugbank",
        "posos",
        "web-search",
    }
)

GATE_REASON_LICENCE_REQUIRED = "LICENCE_REQUIRED"
GATE_REASON_EGRESS_DISABLED = "EGRESS_DISABLED"
GATE_REASON_REGION_BLOCKED = "REGION_BLOCKED"
GATE_REASON_PROVIDER_OPT_IN_MISSING = "PROVIDER_OPT_IN_MISSING"
GATE_REASON_OK = "OK"

GATE_REASON_VALUES = frozenset(
    {
        GATE_REASON_OK,
        GATE_REASON_LICENCE_REQUIRED,
        GATE_REASON_EGRESS_DISABLED,
        GATE_REASON_REGION_BLOCKED,
        GATE_REASON_PROVIDER_OPT_IN_MISSING,
    }
)


@dataclass
class GateDecision:
    """The gate's ruling on a single Expert invocation.

    ``permitted=True`` means a live call *would* be allowed under the
    supplied context (the caller still MUST consult the Expert's own
    live_*_performed flag — the gate does not perform the call).

    ``permitted=False`` means the caller MUST treat the Expert as
    offline-empty regardless of what the stub returns.
    """

    expert_key: str
    permitted: bool
    reason: str
    notes: str = ""


def evaluate(
    expert_key: str,
    *,
    licence_tokens: Iterable[str] | None = None,
    region: str | None = None,
    egress_enabled: bool = False,
    provider_opt_in: bool = False,
    tenant_opt_in: bool = False,
) -> GateDecision:
    """Evaluate whether a live call to ``expert_key`` would be allowed.

    Resolution rules (first failure wins):

    1. ``expert_key`` not in GATED_EXPERTS → ``permitted=True, reason=OK``
       (gate only polices the 5 external Experts).

    2. Licence-required Experts (drugbank, posos) with no
       ``licence_tokens`` → ``permitted=False, reason=LICENCE_REQUIRED``.

    3. Any external Expert with ``egress_enabled=False`` →
       ``permitted=False, reason=EGRESS_DISABLED`` (Charter §6 default).

    4. Region check: if ``region`` is set and is not in the allowed
       egress regions (``CN``, ``EU``, ``US``) →
       ``permitted=False, reason=REGION_BLOCKED``.

    5. ``web-search`` specifically requires both provider_opt_in and
       tenant_opt_in unless its policy is explicitly ENABLED_FOR_TENANT.
       Missing opt-in → ``permitted=False,
       reason=PROVIDER_OPT_IN_MISSING``.

    6. Otherwise → ``permitted=True, reason=OK``.
    """
    if expert_key not in GATED_EXPERTS:
        return GateDecision(
            expert_key=expert_key,
            permitted=True,
            reason=GATE_REASON_OK,
            notes="expert not in GATED_EXPERTS; gate does not apply",
        )

    tokens = list(licence_tokens or [])

    if expert_key in {"drugbank", "posos"} and not tokens:
        return GateDecision(
            expert_key=expert_key,
            permitted=False,
            reason=GATE_REASON_LICENCE_REQUIRED,
            notes=(
                f"{expert_key} requires a commercial licence token; "
                "supply via licence_tokens. No LLM fallback."
            ),
        )

    if not egress_enabled:
        return GateDecision(
            expert_key=expert_key,
            permitted=False,
            reason=GATE_REASON_EGRESS_DISABLED,
            notes=(
                "egress_enabled=False (Charter §6 default). Set "
                "egress_enabled=True plus a region to permit a live call."
            ),
        )

    if region is not None and region.upper() not in {"CN", "EU", "US"}:
        return GateDecision(
            expert_key=expert_key,
            permitted=False,
            reason=GATE_REASON_REGION_BLOCKED,
            notes=f"region {region!r} not in CN/EU/US egress allowlist",
        )

    if expert_key == "web-search" and not (provider_opt_in and tenant_opt_in):
        return GateDecision(
            expert_key=expert_key,
            permitted=False,
            reason=GATE_REASON_PROVIDER_OPT_IN_MISSING,
            notes=(
                "web-search requires both provider_opt_in and tenant_opt_in "
                "(dual opt-in) before any live call."
            ),
        )

    return GateDecision(
        expert_key=expert_key,
        permitted=True,
        reason=GATE_REASON_OK,
        notes=(
            "live call would be allowed; caller MUST still consult the "
            "Expert's own live_*_performed flag."
        ),
    )


def is_gated(expert_key: str) -> bool:
    return expert_key in GATED_EXPERTS


__all__ = [
    "GATED_EXPERTS",
    "GATE_REASON_LICENCE_REQUIRED",
    "GATE_REASON_EGRESS_DISABLED",
    "GATE_REASON_REGION_BLOCKED",
    "GATE_REASON_PROVIDER_OPT_IN_MISSING",
    "GATE_REASON_OK",
    "GATE_REASON_VALUES",
    "GateDecision",
    "evaluate",
    "is_gated",
]
