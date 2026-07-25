"""Clinical Trials Expert — Corti public §3.2 key 8 of 9.

A1B-AE.6 (2026-07-22): STUB — Expert Registry entry only, no live call.
A1B-AE-R.3.a (2026-07-23): LIVE — when the External-Expert Gate permits
and SSRF guard passes, performs a real CT.gov v2 API call against
https://clinicaltrials.gov/api/v2/studies. No API key required.

Live path is OFF by default. See pubmed_expert.py docstring for the
decision tree (gate → fixture → live_capture → stub).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


CLINICAL_TRIALS_EXPERT_CANONICAL_KEY = "clinical-trials"
CLINICAL_TRIALS_EXPERT_NAME = "Clinical Trials Expert"

CT_GOV_BASE = "https://clinicaltrials.gov/api/v2/studies"


@dataclass
class ClinicalTrialsResult:
    query: str
    trials: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    live_search_performed: bool = False
    notes: str = ""


def _fixture_path(query: str) -> Path:
    repo_root = Path(__file__).resolve().parents[4]
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return (
        repo_root
        / "reports"
        / "phase-a1b-runtime"
        / "evidence"
        / "api_captures"
        / f"clinical_trials_{digest}.json"
    )


def _load_fixture(query: str) -> dict[str, Any] | None:
    p = _fixture_path(query)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("fixture load failed for %s: %s", p, e)
        return None


def _save_fixture(query: str, payload: dict[str, Any]) -> None:
    p = _fixture_path(query)
    p.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "expert": CLINICAL_TRIALS_EXPERT_CANONICAL_KEY,
        "query": query,
        "captured_at": _now_iso(),
        "payload": payload,
    }
    p.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _quote(s: str) -> str:
    from urllib.parse import quote

    return quote(s, safe="")


def _format_studies(studies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert CT.gov v2 study objects → list of {nct_id, title, status, phase}."""
    out: list[dict[str, Any]] = []
    for s in studies:
        protocol = (s.get("protocolSection") or {}) if isinstance(s, dict) else {}
        id_mod = protocol.get("identificationModule", {}) or {}
        status_mod = protocol.get("statusModule", {}) or {}
        design_mod = protocol.get("designModule", {}) or {}
        out.append(
            {
                "nct_id": id_mod.get("nctId", ""),
                "title": id_mod.get("briefTitle", ""),
                "status": status_mod.get("overallStatus", ""),
                "phase": ", ".join(design_mod.get("phases", []) or []),
            }
        )
    return out


async def _live_ctgov(
    query: str, max_results: int
) -> dict[str, Any]:
    """Real CT.gov v2 studies query."""
    import httpx

    from app.services.ssrf_guard import assert_url_safe

    url = (
        f"{CT_GOV_BASE}?query.term={_quote(query)}"
        f"&countTotal=true&pageSize={max_results}"
    )
    assert_url_safe(url)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def search_async(
    query: str,
    *,
    max_results: int = 10,
    egress_enabled: bool = False,
    region: str | None = None,
    allow_live_capture: bool = False,
) -> ClinicalTrialsResult:
    """Async live clinicaltrials.gov search with VCR fixture replay."""
    if not query or not query.strip():
        return ClinicalTrialsResult(
            query=query, trials=[], total=0, live_search_performed=False, notes="empty query"
        )

    from app.agents.experts.external_expert_gate import evaluate as gate_evaluate

    decision = gate_evaluate(
        CLINICAL_TRIALS_EXPERT_CANONICAL_KEY,
        region=region,
        egress_enabled=egress_enabled,
    )
    if not decision.permitted:
        return ClinicalTrialsResult(
            query=query.strip(),
            trials=[],
            total=0,
            live_search_performed=False,
            notes=f"GATE_DENIED reason={decision.reason}",
        )

    fixture = _load_fixture(query)
    if fixture is not None:
        payload = fixture.get("payload", {}) or {}
        return ClinicalTrialsResult(
            query=query.strip(),
            trials=payload.get("trials", []),
            total=payload.get("total", 0),
            live_search_performed=True,
            notes=f"VCR fixture replay (captured_at={fixture.get('captured_at')})",
        )

    if allow_live_capture:
        try:
            data = await _live_ctgov(query, max_results)
            studies = data.get("studies", []) or []
            trials = _format_studies(studies)
            total = int(data.get("totalCount", len(trials)))
            payload = {"trials": trials, "total": total}
            _save_fixture(query, payload)
            return ClinicalTrialsResult(
                query=query.strip(),
                trials=trials,
                total=total,
                live_search_performed=True,
                notes="live capture (fixture saved)",
            )
        except Exception as e:
            logger.warning("ClinicalTrials live capture failed: %s", e)
            return ClinicalTrialsResult(
                query=query.strip(),
                trials=[],
                total=0,
                live_search_performed=False,
                notes=f"live capture error: {e}",
            )

    return ClinicalTrialsResult(
        query=query.strip(),
        trials=[],
        total=0,
        live_search_performed=False,
        notes=(
            "STUB (no fixture, no live_capture flag): gate permitted but "
            "neither a VCR fixture nor allow_live_capture=True was supplied. "
            "Run once with allow_live_capture=True to seed the fixture."
        ),
    )


def search(
    query: str,
    *,
    condition: str | None = None,
    location: str | None = None,
    max_results: int = 10,
    egress_enabled: bool = False,
    region: str | None = None,
    allow_live_capture: bool = False,
) -> ClinicalTrialsResult:
    """Synchronous wrapper (backward compat). Sync path cannot do live calls."""
    if not query or not query.strip():
        return ClinicalTrialsResult(
            query=query, trials=[], total=0, live_search_performed=False, notes="empty query"
        )

    fixture = _load_fixture(query)
    if fixture is not None:
        payload = fixture.get("payload", {}) or {}
        return ClinicalTrialsResult(
            query=query.strip(),
            trials=payload.get("trials", []),
            total=payload.get("total", 0),
            live_search_performed=True,
            notes=f"VCR fixture replay (captured_at={fixture.get('captured_at')})",
        )

    return ClinicalTrialsResult(
        query=query.strip(),
        trials=[],
        total=0,
        live_search_performed=False,
        notes="STUB (SYNC path): live calls require search_async().",
    )


__all__ = [
    "CLINICAL_TRIALS_EXPERT_CANONICAL_KEY",
    "CLINICAL_TRIALS_EXPERT_NAME",
    "ClinicalTrialsResult",
    "search",
    "search_async",
]
