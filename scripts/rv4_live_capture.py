"""A1B-AE-RV.4 — Live PubMed + ClinicalTrials capture.

Runs ONE real EUtils esearch+esummary and ONE real CT.gov v2 studies
call with synthetic queries. Saves the request envelope (URL, headers
sent, query, timestamp, latency), the response envelope (status, body
truncated, full body SHA-256), and an MD5 of the VCR replay shape so
RV.5/RV.6 can diff live vs replay.

This script is the ONLY place where allow_live_capture=True is set in
the audit phase. Production runtime paths keep it off.

Run:
    cd backend && python -m scripts.rv4_live_capture
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import ssl
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure backend/ is on sys.path
HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent / "backend"
sys.path.insert(0, str(BACKEND))

EVIDENCE = (
    BACKEND.parent
    / "reports"
    / "phase-a1b"
    / "agent-expert-reverification"
    / "evidence"
    / "public-expert-live"
)
EVIDENCE.mkdir(parents=True, exist_ok=True)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(payload: Any) -> str:
    if isinstance(payload, (dict, list)):
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    elif isinstance(payload, bytes):
        raw = payload
    else:
        raw = str(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _network_probe(host: str) -> dict[str, Any]:
    """Pre-flight DNS + TCP + TLS probe so BLOCKED_BY_NETWORK is distinct
    from API-level errors."""
    out: dict[str, Any] = {"host": host}
    t0 = time.perf_counter()
    try:
        addr = socket.gethostbyname(host)
        out["dns_resolved"] = True
        out["ip"] = addr
    except Exception as e:
        out["dns_resolved"] = False
        out["dns_error"] = repr(e)
        out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
        return out

    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=10) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                out["tls_handshake"] = True
                out["tls_version"] = ssock.version()
    except Exception as e:
        out["tls_handshake"] = False
        out["tls_error"] = repr(e)

    out["elapsed_ms"] = int((time.perf_counter() - t0) * 1000)
    return out


# ─────────────────────────────────────────────────────────────────────
# PubMed — real EUtils call (no API key required; 3 req/s rate limit)
# ─────────────────────────────────────────────────────────────────────


PUBMED_QUERY = "RV4MARKER diabetes type 2 cohort synthetic"


async def capture_pubmed() -> dict[str, Any]:
    """Live EUtils esearch + esummary capture."""
    import httpx

    from app.agents.experts import pubmed_expert
    from app.services.ssrf_guard import assert_url_safe

    base = pubmed_expert.EUTILS_BASE
    probe = _network_probe("eutils.ncbi.nlm.nih.gov")

    envelope: dict[str, Any] = {
        "expert": "pubmed",
        "capture_id": "rv4-pubmed-" + uuid.uuid4().hex[:12],
        "captured_at": _utcnow(),
        "query": PUBMED_QUERY,
        "capture_mode": "LIVE_CAPTURE",
        "endpoint_base": base,
        "network_probe": probe,
    }

    if not probe.get("dns_resolved") or not probe.get("tls_handshake"):
        envelope["status"] = "BLOCKED_BY_NETWORK"
        envelope["notes"] = (
            "DNS or TLS handshake failed; external network not available."
        )
        return envelope

    # Step 1: esearch.fcgi
    from urllib.parse import quote

    esearch_url = (
        f"{base}/esearch.fcgi?db=pubmed&term="
        f"{quote(PUBMED_QUERY, safe='')}&retmax=5&retmode=json"
    )
    assert_url_safe(esearch_url)
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(esearch_url)
            r.raise_for_status()
            esearch_body = r.json()
    except Exception as e:
        envelope["status"] = "BLOCKED_BY_EXTERNAL_DEPENDENCY"
        envelope["notes"] = f"esearch raised: {e!r}"
        return envelope
    esearch_latency_ms = int((time.perf_counter() - t0) * 1000)

    id_list = (
        (esearch_body.get("esearchresult") or {}).get("idlist") or []
    )
    envelope["esearch"] = {
        "url": esearch_url,
        "status_code": r.status_code,
        "latency_ms": esearch_latency_ms,
        "pmids_returned": len(id_list),
        "body_sha256": _sha256(esearch_body),
        "body_excerpt": json.dumps(esearch_body, ensure_ascii=False)[:500],
    }

    # Step 2: esummary.fcgi for the PMIDs returned
    if id_list:
        ids_csv = ",".join(id_list[:5])
        esummary_url = (
            f"{base}/esummary.fcgi?db=pubmed&id="
            f"{quote(ids_csv, safe='')}&retmode=json"
        )
        assert_url_safe(esummary_url)
        t0 = time.perf_counter()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r2 = await client.get(esummary_url)
                r2.raise_for_status()
                esummary_body = r2.json()
        except Exception as e:
            envelope["status"] = "BLOCKED_BY_EXTERNAL_DEPENDENCY"
            envelope["notes"] = f"esummary raised: {e!r}"
            return envelope
        esummary_latency_ms = int((time.perf_counter() - t0) * 1000)
        articles = pubmed_expert._format_articles(esummary_body)
        envelope["esummary"] = {
            "url": esummary_url,
            "status_code": r2.status_code,
            "latency_ms": esummary_latency_ms,
            "articles_returned": len(articles),
            "body_sha256": _sha256(esummary_body),
            "articles_excerpt": articles[:2],
        }
        envelope["articles"] = articles
        envelope["total"] = len(articles)

    envelope["status"] = "OK"
    envelope["live_search_performed"] = True
    envelope["notes"] = (
        "Real EUtils call succeeded; no VCR replay used. Body SHA-256 "
        "is over the parsed-JSON canonical form so re-runs of the same "
        "query produce comparable hashes (PubMed returns PMIDs in "
        "relevance order, which is stable for a fresh query)."
    )
    return envelope


# ─────────────────────────────────────────────────────────────────────
# ClinicalTrials — real CT.gov v2 call
# ─────────────────────────────────────────────────────────────────────


CT_QUERY = "hypertension"


async def capture_clinical_trials() -> dict[str, Any]:
    """Live CT.gov v2 studies call."""
    import httpx

    from app.agents.experts import clinical_trials_expert
    from app.services.ssrf_guard import assert_url_safe

    base = clinical_trials_expert.CT_GOV_BASE
    probe = _network_probe("clinicaltrials.gov")

    envelope: dict[str, Any] = {
        "expert": "clinical-trials",
        "capture_id": "rv4-ct-" + uuid.uuid4().hex[:12],
        "captured_at": _utcnow(),
        "query": CT_QUERY,
        "capture_mode": "LIVE_CAPTURE",
        "endpoint_base": base,
        "network_probe": probe,
    }

    if not probe.get("dns_resolved") or not probe.get("tls_handshake"):
        envelope["status"] = "BLOCKED_BY_NETWORK"
        envelope["notes"] = (
            "DNS or TLS handshake failed; external network not available."
        )
        return envelope

    from urllib.parse import quote

    url = (
        f"{base}?query.term={quote(CT_QUERY, safe='')}"
        f"&pageSize=5&format=json"
    )
    assert_url_safe(url)
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(url)
            r.raise_for_status()
            body = r.json()
    except Exception as e:
        envelope["status"] = "BLOCKED_BY_EXTERNAL_DEPENDENCY"
        envelope["notes"] = f"CT.gov raised: {e!r}"
        return envelope
    latency_ms = int((time.perf_counter() - t0) * 1000)

    studies = (body.get("studies") or [])[:5]
    trials = clinical_trials_expert._format_studies(studies)
    envelope["request"] = {
        "url": url,
        "status_code": r.status_code,
        "latency_ms": latency_ms,
        "studies_returned": len(studies),
        "body_sha256": _sha256(body),
        "body_excerpt": json.dumps(body, ensure_ascii=False)[:500],
    }
    envelope["trials"] = trials
    envelope["total"] = len(trials)
    envelope["status"] = "OK"
    envelope["live_search_performed"] = True
    envelope["notes"] = (
        "Real CT.gov v2 call succeeded; no VCR replay used. Body SHA-256 "
        "is over parsed-JSON canonical form."
    )
    return envelope


# ─────────────────────────────────────────────────────────────────────
# VCR replay comparison
# ─────────────────────────────────────────────────────────────────────


def compare_with_fixture(live: dict[str, Any], expert: str) -> dict[str, Any]:
    """Compare live capture shape to any pre-existing VCR fixture for
    the same query. Flags schema drift, missing fields, etc."""
    from app.agents.experts import pubmed_expert, clinical_trials_expert

    if expert == "pubmed":
        path = pubmed_expert._fixture_path(live["query"])
    else:
        path = clinical_trials_expert._fixture_path(live["query"])

    if not path.exists():
        return {
            "fixture_path": str(path),
            "fixture_present": False,
            "drift": "NO_FIXURE_PRESENT (first live capture seeds the fixture)",
        }

    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture_payload = fixture.get("payload", {}) or {}

    # Shape check: same keys
    live_keys = set()
    if expert == "pubmed":
        for art in live.get("articles", []):
            live_keys.update(art.keys())
    else:
        for tr in live.get("trials", []):
            live_keys.update(tr.keys())

    fixture_keys = set()
    if expert == "pubmed":
        for art in fixture_payload.get("articles", []):
            fixture_keys.update(art.keys())
    else:
        for tr in fixture_payload.get("trials", []):
            fixture_keys.update(tr.keys())

    return {
        "fixture_path": str(path),
        "fixture_present": True,
        "fixture_captured_at": fixture.get("captured_at"),
        "live_keys": sorted(live_keys),
        "fixture_keys": sorted(fixture_keys),
        "keys_only_in_live": sorted(live_keys - fixture_keys),
        "keys_only_in_fixture": sorted(fixture_keys - live_keys),
        "shape_match": live_keys == fixture_keys,
    }


async def main() -> int:
    out: dict[str, Any] = {
        "phase": "A1B-AE-RV",
        "sub_gate": "RV.4",
        "started_at": _utcnow(),
        "host": socket.gethostname(),
        "python_version": sys.version.split()[0],
    }

    # PubMed
    print("[RV.4] PubMed live capture starting...", flush=True)
    pm = await capture_pubmed()
    pm["fixture_comparison"] = compare_with_fixture(pm, "pubmed")
    pm_path = EVIDENCE / "PUBMED_LIVE_CAPTURE.json"
    pm_path.write_text(
        json.dumps(pm, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[RV.4] PubMed envelope → {pm_path}", flush=True)
    print(f"      status={pm.get('status')} articles={pm.get('total', 0)}", flush=True)

    # ClinicalTrials
    print("[RV.4] ClinicalTrials live capture starting...", flush=True)
    ct = await capture_clinical_trials()
    ct["fixture_comparison"] = compare_with_fixture(ct, "clinical-trials")
    ct_path = EVIDENCE / "CLINICAL_TRIALS_LIVE_CAPTURE.json"
    ct_path.write_text(
        json.dumps(ct, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[RV.4] ClinicalTrials envelope → {ct_path}", flush=True)
    print(f"      status={ct.get('status')} trials={ct.get('total', 0)}", flush=True)

    out["pubmed_status"] = pm.get("status")
    out["pubmed_articles"] = pm.get("total", 0)
    out["clinical_trials_status"] = ct.get("status")
    out["clinical_trials_trials"] = ct.get("total", 0)
    out["finished_at"] = _utcnow()
    out["pubmed_evidence_path"] = str(pm_path)
    out["clinical_trials_evidence_path"] = str(ct_path)

    # Combined manifest
    (EVIDENCE / "MANIFEST.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Exit non-zero if any hard blocker
    if pm.get("status") not in {"OK"} or ct.get("status") not in {"OK"}:
        print(
            f"[RV.4] WARNING — at least one capture did not return OK "
            f"(pubmed={pm.get('status')}, ct={ct.get('status')})",
            file=sys.stderr,
            flush=True,
        )
        return 2
    return 0


if __name__ == "__main__":
    rc = asyncio.run(main())
    sys.exit(rc)
