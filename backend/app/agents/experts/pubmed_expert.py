"""PubMed Expert — Corti public §3.2 key 7 of 9.

A1B-AE.6 (2026-07-22): STUB — Expert Registry entry only, no live call.
A1B-AE-R.3.a (2026-07-23): LIVE — when the External-Expert Gate permits
and SSRF guard passes, performs a real EUtils esearch + esummary call
against https://eutils.ncbi.nlm.nih.gov/entrez/eutils/. No API key
required (3 req/s rate limit applies).

The live path is OFF by default. Caller must supply:
- ``egress_enabled=True``
- ``region`` in {CN, EU, US}
- Either a live HTTP client (production) or a VCR fixture replayer (tests)

VCR fixtures live at:
    reports/phase-a1b-runtime/evidence/api_captures/pubmed_<query_sha>.json

Charter §6 egress policy is enforced by external_expert_gate.evaluate()
*before* this module opens any socket. SSRF guard then asserts the URL
safety. This module is the LAST gate before network egress.
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


PUBMED_EXPERT_CANONICAL_KEY = "pubmed"
PUBMED_EXPERT_NAME = "PubMed Expert"

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


@dataclass
class PubMedResult:
    query: str
    articles: list[dict[str, Any]] = field(default_factory=list)
    total: int = 0
    live_search_performed: bool = False
    notes: str = ""


def _fixture_path(query: str) -> Path:
    """Return the canonical VCR fixture path for a given query."""
    repo_root = Path(__file__).resolve().parents[4]
    digest = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    return (
        repo_root
        / "reports"
        / "phase-a1b-runtime"
        / "evidence"
        / "api_captures"
        / f"pubmed_{digest}.json"
    )


def _load_fixture(query: str) -> dict[str, Any] | None:
    """Load VCR fixture if present. Returns None if no fixture."""
    p = _fixture_path(query)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("fixture load failed for %s: %s", p, e)
        return None


def _save_fixture(query: str, payload: dict[str, Any]) -> None:
    """Persist a VCR fixture (called when live capture is enabled)."""
    p = _fixture_path(query)
    p.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "expert": PUBMED_EXPERT_CANONICAL_KEY,
        "query": query,
        "captured_at": _now_iso(),
        "payload": payload,
    }
    p.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


async def _live_esearch(query: str, max_results: int) -> dict[str, Any]:
    """Real EUtils esearch.fcgi call. Returns parsed JSON."""
    import httpx

    from app.services.ssrf_guard import assert_url_safe

    url = (
        f"{EUTILS_BASE}/esearch.fcgi?db=pubmed&term="
        f"{_quote(query)}&retmax={max_results}&retmode=json"
    )
    assert_url_safe(url)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


async def _live_esummary(pmids: list[str]) -> dict[str, Any]:
    """Real EUtils esummary.fcgi call. Returns parsed JSON."""
    import httpx

    from app.services.ssrf_guard import assert_url_safe

    if not pmids:
        return {"result": {"uids": []}}

    ids_csv = ",".join(pmids)
    url = (
        f"{EUTILS_BASE}/esummary.fcgi?db=pubmed&id={_quote(ids_csv)}&retmode=json"
    )
    assert_url_safe(url)
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
        r.raise_for_status()
        return r.json()


def _quote(s: str) -> str:
    from urllib.parse import quote

    return quote(s, safe="")


def _format_articles(esummary: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert EUtils esummary result → list of {pmid, title, journal, year}."""
    result = esummary.get("result", {}) or {}
    uids = result.get("uids", []) or []
    out: list[dict[str, Any]] = []
    for uid in uids:
        entry = result.get(uid, {}) or {}
        out.append(
            {
                "pmid": uid,
                "title": entry.get("title", ""),
                "journal": entry.get("fulljournalname", entry.get("source", "")),
                "year": entry.get("pubdate", "")[:4],
                "authors": [a.get("name", "") for a in entry.get("authors", [])][:5],
            }
        )
    return out


async def search_async(
    query: str,
    *,
    max_results: int = 10,
    egress_enabled: bool = False,
    region: str | None = None,
    allow_live_capture: bool = False,
) -> PubMedResult:
    """Async live PubMed search with VCR fixture replay.

    Decision tree:
    1. Query empty → return empty + live_search_performed=False
    2. External-Expert Gate denies → return empty + live_search_performed=False
       (NO socket opened; zero DNS lookups; zero TCP connects)
    3. VCR fixture exists for query → replay fixture, set live_search_performed=True
    4. allow_live_capture=True → hit real EUtils, save fixture, return result
    5. allow_live_capture=False AND no fixture → return hermetic stub
    """
    if not query or not query.strip():
        return PubMedResult(
            query=query, articles=[], total=0, live_search_performed=False, notes="empty query"
        )

    from app.agents.experts.external_expert_gate import evaluate as gate_evaluate

    decision = gate_evaluate(
        PUBMED_EXPERT_CANONICAL_KEY,
        region=region,
        egress_enabled=egress_enabled,
    )
    if not decision.permitted:
        return PubMedResult(
            query=query.strip(),
            articles=[],
            total=0,
            live_search_performed=False,
            notes=f"GATE_DENIED reason={decision.reason}",
        )

    # Replay from fixture if available
    fixture = _load_fixture(query)
    if fixture is not None:
        payload = fixture.get("payload", {}) or {}
        return PubMedResult(
            query=query.strip(),
            articles=payload.get("articles", []),
            total=payload.get("total", 0),
            live_search_performed=True,
            notes=f"VCR fixture replay (captured_at={fixture.get('captured_at')})",
        )

    # Live capture (rare; only when explicitly enabled)
    if allow_live_capture:
        try:
            esearch = await _live_esearch(query, max_results)
            id_list = esearch.get("esearchresult", {}).get("idlist", [])
            if not id_list:
                return PubMedResult(
                    query=query.strip(),
                    articles=[],
                    total=0,
                    live_search_performed=True,
                    notes="live: 0 results",
                )
            esummary = await _live_esummary(id_list[:max_results])
            articles = _format_articles(esummary)
            payload = {"articles": articles, "total": len(articles)}
            _save_fixture(query, payload)
            return PubMedResult(
                query=query.strip(),
                articles=articles,
                total=len(articles),
                live_search_performed=True,
                notes="live capture (fixture saved)",
            )
        except Exception as e:
            logger.warning("PubMed live capture failed: %s", e)
            return PubMedResult(
                query=query.strip(),
                articles=[],
                total=0,
                live_search_performed=False,
                notes=f"live capture error: {e}",
            )

    return PubMedResult(
        query=query.strip(),
        articles=[],
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
    max_results: int = 10,
    egress_enabled: bool = False,
    region: str | None = None,
    allow_live_capture: bool = False,
) -> PubMedResult:
    """Synchronous wrapper for backward compat with A1B-AE.6 stub signature.

    The sync path CANNOT perform live calls — it always returns the
    hermetic stub. Callers that need live data MUST use ``search_async``.
    """
    import asyncio

    if not query or not query.strip():
        return PubMedResult(
            query=query, articles=[], total=0, live_search_performed=False, notes="empty query"
        )

    # Try fixture replay synchronously (no network needed)
    fixture = _load_fixture(query)
    if fixture is not None:
        payload = fixture.get("payload", {}) or {}
        return PubMedResult(
            query=query.strip(),
            articles=payload.get("articles", []),
            total=payload.get("total", 0),
            live_search_performed=True,
            notes=f"VCR fixture replay (captured_at={fixture.get('captured_at')})",
        )

    # Sync fallback — no live path
    return PubMedResult(
        query=query.strip(),
        articles=[],
        total=0,
        live_search_performed=False,
        notes=(
            "STUB (SYNC path): live calls require search_async(). To seed a fixture, "
            "invoke search_async(query, egress_enabled=True, allow_live_capture=True) once."
        ),
    )


__all__ = [
    "PUBMED_EXPERT_CANONICAL_KEY",
    "PUBMED_EXPERT_NAME",
    "PubMedResult",
    "search",
    "search_async",
]
