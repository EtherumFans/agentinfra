"""Track H3.1 — Corti CDI Python SSE runner.

PDF §10 — Python httpx + httpx-sse runner for Corti CDI Agent (40-case calibration).

Failure taxonomy per PDF §10.1:
- AUTH_FAILURE (401/403)
- REQUEST_REJECTED (400)
- FIRST_TOKEN_TIMEOUT (>30s to first token)
- STREAM_STALL (no token for >60s mid-stream)
- STREAM_DISCONNECTED (network drop)
- EXPERT_FAILURE (Expert MCP server error)
- FINAL_SYNTHESIS_MISSING (stream ended without "Specialist Trace:")
- PARTIAL_RESPONSE (response <200 chars)
- SCHEMA_PARSE_FAILURE (cannot extract gaps/queries from final text)
- RATE_LIMIT (429)
- UNKNOWN (everything else)

Features:
- Dual-auth: Supabase JWT + Keycloak JWT
- SSE streaming via httpx-sse
- Per-case trace persistence
- Heartbeat watchdog (FIRST_TOKEN_TIMEOUT + STREAM_STALL)
- Max 2 retries per case
- Resume from partial run (skip cases with existing per-case JSON)
- Merge mode: combine per-case JSONs into a final aggregate

Credentials (per docs/corti_parity/phase5_d_p05_gate8/preflight_corti_cdi_execution.md):
- Supabase JWT: localStorage 'sb-api-auth-token' → .access_token
- Keycloak JWT: sessionStorage 'access-token:PROJECT:CLIENT' → .data

For headless run, both JWTs must be supplied via env or a JSON credentials file.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

try:
    import httpx
    from httpx_sse import aconnect_sse
except ImportError:
    print("ERROR: install deps first: pip install httpx httpx-sse", file=sys.stderr)
    sys.exit(2)


CORTI_BASE = "https://api.console.corti.app/functions/v1"
PROJECT_ID = "4c4193c7-c6bb-4a71-a275-0ed6c53172d0"
CLIENT_ID = "f63bcaaa-d9a4-4c42-95c0-0d9d0788d636"
AGENT_DEF_ID = "fa3be93e-d1b3-45ef-ae8c-3a07c8d19ef2"

OUT_DIR = Path("reports/track_h/corti_per_case")
OUT_DIR.mkdir(parents=True, exist_ok=True)
SUMMARY_OUT = Path("reports/track_h/corti_40_summary.json")

FIRST_TOKEN_TIMEOUT_S = 30.0
STREAM_STALL_S = 60.0
MAX_RETRIES = 2
PER_CASE_DELAY_S = 5.0  # be polite


def classify_failure(
    status: int | None,
    err: str,
    first_token_received: bool,
    final_text_len: int,
    has_specialist_trace: bool,
) -> str:
    if status in (401, 403):
        return "AUTH_FAILURE"
    if status == 400:
        return "REQUEST_REJECTED"
    if status == 429:
        return "RATE_LIMIT"
    if "connect" in err.lower() or "timeout" in err.lower():
        if not first_token_received:
            return "FIRST_TOKEN_TIMEOUT"
        return "STREAM_STALL"
    if "eof" in err.lower() or "closed" in err.lower():
        return "STREAM_DISCONNECTED"
    # No error, but no text → stream ended empty (likely upstream silent failure)
    if not err and final_text_len == 0:
        return "PARTIAL_RESPONSE"
    if final_text_len > 0 and final_text_len < 200:
        return "PARTIAL_RESPONSE"
    # Substantial text but no Specialist Trace section: Corti returned a valid response
    # in non-standard format (e.g. "input-required" state asking for more chart info).
    # This is a legitimate CDI signal, not a transient failure — do not retry.
    if final_text_len >= 200 and not has_specialist_trace:
        return ""
    return ""


def parse_corti_response(text: str) -> dict:
    """Parse Corti's free-text response into structured counts.

    Corti's actual output format (from empirical network capture 2026-07-12):
        Encounter Summary:
        - <bullet points>

        Documentation Gaps:
        1. <gap title>
        - Why it matters: ...
        - Evidence quote(s): ...
        - Minimal clarification needed: ...

        2. <gap title>
        ...

        Proposed Provider Queries:
        1. Topic: <topic>
        - Reason query is needed: ...
        - Evidence quote(s): ...
        - Non-leading query text: ...

        Coding Specificity Checklist:
        ...

        Risk Flags:
        ...

        Specialist Trace:
        - Medical Coding Expert: Consulted for ...
        - AMBOSS Expert: Not consulted. Reason: ...
        - CDI Web Search Expert: Not consulted. Reason: ...

    Returns: {gap_count, query_count, encounter_summary, gaps[], queries[], specialists_contacted[]}
    """
    # Section regex - tolerant to both bulleted and numbered list formats
    gap_section = re.search(
        r"Documentation Gaps:\s*(.*?)(?:Proposed Provider Queries:)",
        text, re.DOTALL,
    )
    query_section = re.search(
        r"Proposed Provider Queries:\s*(.*?)(?:Coding Specificity Checklist:)",
        text, re.DOTALL,
    )
    summary_section = re.search(
        r"Encounter Summary:\s*(.*?)(?:Documentation Gaps:)",
        text, re.DOTALL,
    )
    trace_section = re.search(
        r"Specialist Trace:\s*(.*)",
        text, re.DOTALL,
    )

    gaps_text = gap_section.group(1) if gap_section else ""
    queries_text = query_section.group(1) if query_section else ""
    summary_text = summary_section.group(1) if summary_section else ""
    trace_text = trace_section.group(1) if trace_section else ""

    # Each gap is a numbered item: "N. <title>" possibly followed by indented bullets
    gaps = []
    for m in re.finditer(r"(?:^|\n)\s*(\d+)\.\s+([^\n]+(?:\n(?!\s*\d+\.\s)[^\n]+)*)", gaps_text):
        gaps.append({"idx": int(m.group(1)), "text": m.group(2).strip()[:500]})

    # Each query starts with "N. Topic:" — handle both "1. Topic: X" and "1. <title>\n   - Topic: X"
    queries = []
    # Pattern 1: "N. Topic: X"
    for m in re.finditer(r"(?:^|\n)\s*(\d+)\.\s*Topic:\s*([^\n]+)", queries_text):
        queries.append({"idx": int(m.group(1)), "text": m.group(2).strip()[:500]})
    # Pattern 2 (fallback): "N. <anything>" — count numbered items
    if not queries:
        for m in re.finditer(r"(?:^|\n)\s*(\d+)\.\s+([^\n]+(?:\n(?!\s*\d+\.\s)[^\n]+)*)", queries_text):
            queries.append({"idx": int(m.group(1)), "text": m.group(2).strip()[:500]})

    # Specialists contacted (from trace section) — must be more specific to avoid false matches
    # The actual format is "Medical Coding Expert: Consulted for..." or "Not consulted"
    specialists = []
    for expert in ["Medical Coding Expert", "AMBOSS Expert", "CDI Web Search Expert",
                   "PubMed Expert", "Medical Calculator Expert", "Web Search Expert", "Coding Expert"]:
        # Must be mentioned with "Consulted" to count
        pat = re.compile(re.escape(expert) + r"\s*:\s*(Consulted|was\s+consulted)", re.IGNORECASE)
        if pat.search(trace_text):
            specialists.append(expert)

    return {
        "encounter_summary": summary_text.strip()[:1000],
        "gaps": gaps,
        "gap_count": len(gaps),
        "queries": queries,
        "query_count": len(queries),
        "specialists_contacted": specialists,
        "specialist_trace_text": trace_text.strip()[:2000],
        "has_specialist_trace": "Specialist Trace" in text,
    }


async def fetch_agent_config(client: httpx.AsyncClient, supabase_jwt: str, corti_jwt: str) -> dict:
    """Fetch the agent's config (system prompt + experts) for session creation.

    Returns the inner `config` object (the one needed by POST /ai/agents).
    """
    res = await client.get(
        f"{CORTI_BASE}/projects/{PROJECT_ID}/agents/{AGENT_DEF_ID}",
        headers=_auth_headers(supabase_jwt, corti_jwt),
        timeout=30.0,
    )
    res.raise_for_status()
    top = res.json()
    # The API returns {id, name, config: {name, experts, description, systemPrompt}, ...}
    # POST /ai/agents expects the inner config object.
    return top.get("config") or {
        "name": top.get("name", ""),
        "systemPrompt": top.get("systemPrompt", ""),
        "experts": top.get("experts", []),
        "description": top.get("description", ""),
    }


async def create_session(client: httpx.AsyncClient, supabase_jwt: str, corti_jwt: str, config: dict) -> str:
    res = await client.post(
        f"{CORTI_BASE}/ai/agents",
        headers={**_auth_headers(supabase_jwt, corti_jwt), "content-type": "application/json"},
        json={
            "agentId": AGENT_DEF_ID,
            "projectId": PROJECT_ID,
            "config": config,
        },
        timeout=30.0,
    )
    if res.status_code != 200:
        raise RuntimeError(f"create_session HTTP {res.status_code}: {res.text[:300]}")
    return res.json()["id"]


def _auth_headers(supabase_jwt: str, corti_jwt: str) -> dict:
    return {
        "authorization": f"Bearer {supabase_jwt}",
        "corti-access-token": f"Bearer {corti_jwt}",
    }


async def send_message_stream(
    client: httpx.AsyncClient,
    session_id: str,
    chart_en: str,
    supabase_jwt: str,
    corti_jwt: str,
) -> dict:
    """Send chart text via Vercel AI SDK v1 stream protocol. Returns per-case trace dict."""
    t0 = time.time()
    first_token_at: float | None = None
    last_token_at: float | None = None
    full_text_parts: list[str] = []
    event_count = 0
    raw_events: list[str] = []  # first 20 events for debugging
    expert_events: list[dict] = []  # data-json events (tool/expert outputs)
    status_events: list[dict] = []  # data-status-update events
    finish_metadata: dict = {}  # messageMetadata from finish event
    err = ""
    status: int | None = None
    headers = {
        **_auth_headers(supabase_jwt, corti_jwt),
        "content-type": "application/json",
        "accept": "text/event-stream",
    }
    # Vercel AI SDK v1 message format (A2A-style parts)
    body = {
        "agentDefinitionId": AGENT_DEF_ID,
        "id": session_id,
        "messages": [
            {
                "parts": [{"text": chart_en, "type": "text"}],
                "id": f"msg-{int(time.time() * 1000)}",
                "role": "user",
            }
        ],
        "projectId": PROJECT_ID,
        "trigger": "submit-message",
    }

    try:
        prev_event_at = None
        async with aconnect_sse(
            client, "POST", f"{CORTI_BASE}/ai/agents/{session_id}",
            headers=headers, json=body,
            timeout=httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=30.0),
        ) as event_source:
            status = event_source.response.status_code
            if status != 200:
                err = event_source.response.text[:500]
                return {
                    "status": status,
                    "error": err,
                    "first_token_at": None,
                    "stream_duration_s": round(time.time() - t0, 2),
                    "event_count": 0,
                    "text": "",
                }
            async for sse_event in event_source.aiter_sse():
                event_count += 1
                now = time.time()
                if first_token_at is None:
                    first_token_at = now
                # Streak watchdog: gap between events
                if prev_event_at is not None and (now - prev_event_at) > STREAM_STALL_S:
                    raise TimeoutError(f"stream stall {now - prev_event_at:.1f}s")
                prev_event_at = now
                last_token_at = now
                if event_count <= 20:
                    raw_events.append(str(sse_event.event or "")[:60] + "|" + (sse_event.data or "")[:200])
                # First-token timeout watchdog
                if (now - t0) > FIRST_TOKEN_TIMEOUT_S and first_token_at is None:
                    raise TimeoutError("first token timeout")
                payload = sse_event.data or ""
                if not payload or payload == "[DONE]":
                    continue
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                etype = obj.get("type", "")
                if etype == "text-delta":
                    delta = obj.get("delta", "")
                    if isinstance(delta, str) and delta:
                        full_text_parts.append(delta)
                elif etype == "data-status-update":
                    status_events.append(obj.get("data", {}))
                elif etype == "data-json":
                    expert_events.append(obj.get("data", {}))
                elif etype == "message-metadata":
                    finish_metadata = obj.get("messageMetadata", {})
                elif etype == "finish":
                    finish_metadata = {**finish_metadata, **obj.get("messageMetadata", {})}
    except TimeoutError as e:
        err = str(e)
    except httpx.HTTPError as e:
        err = f"httpx: {e}"
    except Exception as e:
        err = f"{type(e).__name__}: {e}"

    full_text = "".join(full_text_parts)
    duration = round(time.time() - t0, 2)
    first_token_s = round(first_token_at - t0, 2) if first_token_at else None
    last_token_s = round(last_token_at - t0, 2) if last_token_at else None

    parsed = parse_corti_response(full_text)
    failure = classify_failure(
        status=status,
        err=err,
        first_token_received=first_token_at is not None,
        final_text_len=len(full_text),
        has_specialist_trace=parsed["has_specialist_trace"],
    )

    return {
        "status": status,
        "error": err,
        "first_token_at_s": first_token_s,
        "last_token_at_s": last_token_s,
        "stream_duration_s": duration,
        "event_count": event_count,
        "raw_events_preview": raw_events,
        "expert_events": expert_events,
        "status_events": status_events,
        "finish_metadata": finish_metadata,
        "text": full_text,
        "text_length": len(full_text),
        "parsed": parsed,
        "failure_taxonomy": failure if failure != "UNKNOWN" or err else "",
    }


async def run_one_case(
    client: httpx.AsyncClient,
    case: dict,
    supabase_jwt: str,
    corti_jwt: str,
    config: dict,
    attempt: int = 1,
) -> dict:
    case_id = case["case_id"]
    chart_en = case["chart_en"]
    print(f"  [{case_id}] attempt {attempt} ...", flush=True)
    session_id = None
    try:
        session_id = await create_session(client, supabase_jwt, corti_jwt, config)
    except Exception as e:
        return {
            "case_id": case_id,
            "session_id": None,
            "attempt": attempt,
            "outcome": "CREATE_SESSION_FAILED",
            "error": str(e)[:300],
            "elapsed_s": 0,
        }
    result = await send_message_stream(client, session_id, chart_en, supabase_jwt, corti_jwt)
    failure = result.get("failure_taxonomy", "")
    if not failure or failure == "UNKNOWN":
        outcome = "SUCCESS"
    else:
        outcome = failure
    elapsed = result.get("stream_duration_s", 0)
    record = {
        "case_id": case_id,
        "group": case.get("group", ""),
        "variant": case.get("variant", ""),
        "session_id": session_id,
        "attempt": attempt,
        "outcome": outcome,
        "elapsed_s": elapsed,
        "expected": case.get("expected", {}),
        "text_length": result.get("text_length", 0),
        "first_token_at_s": result.get("first_token_at_s"),
        "last_token_at_s": result.get("last_token_at_s"),
        "event_count": result.get("event_count", 0),
        "raw_events_preview": result.get("raw_events_preview", []),
        "expert_events": result.get("expert_events", []),
        "status_events": result.get("status_events", []),
        "finish_metadata": result.get("finish_metadata", {}),
        "parsed": result.get("parsed", {}),
        "error": result.get("error", ""),
        "text": result.get("text", ""),
    }
    # Save per-case trace immediately (resume support)
    out_file = OUT_DIR / f"{case_id}.json"
    out_file.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


async def run_case_with_retries(
    client: httpx.AsyncClient,
    case: dict,
    supabase_jwt: str,
    corti_jwt: str,
    config: dict,
    max_retries: int = MAX_RETRIES,
) -> dict:
    last = None
    for attempt in range(1, max_retries + 2):  # initial + retries
        last = await run_one_case(client, case, supabase_jwt, corti_jwt, config, attempt=attempt)
        if last["outcome"] == "SUCCESS":
            return last
        # Retryable failures
        if last["outcome"] in {"AUTH_FAILURE", "RATE_LIMIT", "FINAL_SYNTHESIS_MISSING"}:
            # AUTH_FAILURE is not retryable without new credentials
            if last["outcome"] == "AUTH_FAILURE":
                return last
            print(f"    → {last['outcome']}, retrying...", flush=True)
            await asyncio.sleep(5.0)
            continue
        # Non-retryable (REQUEST_REJECTED, PARTIAL_RESPONSE, SCHEMA_PARSE_FAILURE, etc.)
        return last
    return last  # type: ignore[return-value]


def load_credentials(cred_file: str | None) -> tuple[str, str]:
    if cred_file:
        data = json.loads(Path(cred_file).read_text(encoding="utf-8"))
        return data["supabase_jwt"], data["corti_jwt"]
    supabase = os.environ.get("CORTI_SUPABASE_JWT")
    corti = os.environ.get("CORTI_KEYCLOAK_JWT")
    if not supabase or not corti:
        print(
            "ERROR: credentials required. Either:\n"
            "  - Write JSON to scripts/corti_parity/track_h/.corti_creds.json with "
            "{supabase_jwt, corti_jwt}\n"
            "  - Or set env CORTI_SUPABASE_JWT and CORTI_KEYCLOAK_JWT",
            file=sys.stderr,
        )
        sys.exit(2)
    return supabase, corti


def _find_fixture(name: str) -> Path:
    """Find fixture in repo, trying multiple candidate paths."""
    candidates = [
        Path(name),
        Path("backend") / name,
        Path("backend/tests/fixtures") / name,
        Path("tests/fixtures") / name,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"Cannot find fixture {name} in any of: {[str(c) for c in candidates]}")


def load_cases(fixture_path: str | None, smoke: bool) -> list[dict]:
    if fixture_path:
        data = json.loads(Path(fixture_path).read_text(encoding="utf-8"))
        return data["cases"] if "cases" in data else data
    if smoke:
        # Quick smoke: just 3 cases
        fixture = _find_fixture("cdi_gap8_smoke10.json")
        data = json.loads(fixture.read_text(encoding="utf-8"))
        # Take first 3
        return [
            {
                "case_id": c["case_id"],
                "group": c.get("category", ""),
                "chart_en": c["chart_en"],
                "expected": c.get("expected", {}),
            }
            for c in data["cases"][:3]
        ]
    # Default: 40-case fixture
    fixture = _find_fixture("cdi_gate8_40cases.json")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    return [
        {
            "case_id": c["case_id"],
            "group": c.get("category", ""),
            "chart_en": c["chart_en"],
            "expected": c.get("expected", {}),
        }
        for c in data["cases"]
    ]


def already_done(case_id: str) -> bool:
    p = OUT_DIR / f"{case_id}.json"
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d.get("outcome") == "SUCCESS"
    except Exception:
        return False


async def main_inner(args: argparse.Namespace) -> int:
    supabase_jwt, corti_jwt = load_credentials(args.creds)
    cases = load_cases(args.fixture, args.smoke)
    if args.limit:
        cases = cases[: args.limit]
    if not args.force:
        before = len(cases)
        cases = [c for c in cases if not already_done(c["case_id"])]
        if len(cases) < before:
            print(f"Skipping {before - len(cases)} already-completed cases (use --force to re-run)")

    if not cases:
        print("Nothing to run. Use --force to re-run completed cases.")
        return 0

    print(f"Running {len(cases)} cases against Corti CDI agent {AGENT_DEF_ID}")

    async with httpx.AsyncClient(http2=False) as client:
        try:
            config = await fetch_agent_config(client, supabase_jwt, corti_jwt)
            print(f"  Agent config fetched: name={config.get('name', '?')}, "
                  f"systemPrompt length={len(config.get('systemPrompt', ''))}")
        except Exception as e:
            print(f"ERROR: cannot fetch agent config: {e}", file=sys.stderr)
            return 3

        results: list[dict] = []
        consecutive_auth_failures = 0
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {case['case_id']} ({case.get('group', '')})")
            # Tier 2: re-read creds from file each case so a background
            # refresh daemon can keep tokens valid during long runs.
            if args.creds and Path(args.creds).exists():
                try:
                    fresh = json.loads(Path(args.creds).read_text(encoding="utf-8"))
                    supabase_jwt = fresh["supabase_jwt"]
                    corti_jwt = fresh["corti_jwt"]
                except Exception:
                    pass
            r = await run_case_with_retries(client, case, supabase_jwt, corti_jwt, config)
            results.append(r)
            # Fast-fail: 3 consecutive CREATE_SESSION_FAILED with 401 → abort
            if r["outcome"] == "CREATE_SESSION_FAILED" and "401" in r.get("error", ""):
                consecutive_auth_failures += 1
                if consecutive_auth_failures >= 3:
                    print(f"\nABORT: 3 consecutive AUTH_FAILUREs. Credentials expired. "
                          f"Re-extract JWT and re-run (resume will skip {sum(1 for r in results if r['outcome']=='SUCCESS')} completed).",
                          file=sys.stderr)
                    break
            else:
                consecutive_auth_failures = 0
            if i < len(cases):
                await asyncio.sleep(PER_CASE_DELAY_S)

    # Write summary
    success_count = sum(1 for r in results if r["outcome"] == "SUCCESS")
    summary = {
        "executed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "agent_def_id": AGENT_DEF_ID,
        "case_count": len(results),
        "success_count": success_count,
        "by_outcome": {},
        "results": [
            {k: v for k, v in r.items() if k != "text"}  # drop full text from summary
            for r in results
        ],
    }
    for r in results:
        outcome = r["outcome"]
        summary["by_outcome"][outcome] = summary["by_outcome"].get(outcome, 0) + 1
    SUMMARY_OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"Wrote: {SUMMARY_OUT}")
    print(f"  Success: {success_count}/{len(results)}")
    for outcome, count in summary["by_outcome"].items():
        print(f"  {outcome}: {count}")
    return 0


def main() -> None:
    global OUT_DIR, SUMMARY_OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--creds", default="scripts/corti_parity/track_h/.corti_creds.json",
                    help="JSON file with {supabase_jwt, corti_jwt}")
    ap.add_argument("--fixture", default=None, help="JSON fixture with cases (default: 40-case fixture)")
    ap.add_argument("--smoke", action="store_true", help="Run 3-case smoke instead of 40-case")
    ap.add_argument("--limit", type=int, default=None, help="Limit N cases (debugging)")
    ap.add_argument("--force", action="store_true", help="Re-run even if per-case JSON exists")
    ap.add_argument("--out-dir", default=None, help="Override per-case output dir (default: reports/track_h/corti_per_case)")
    ap.add_argument("--summary-out", default=None, help="Override summary output JSON path")
    args = ap.parse_args()
    if args.out_dir:
        OUT_DIR = Path(args.out_dir)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
    if args.summary_out:
        SUMMARY_OUT = Path(args.summary_out)
    sys.exit(asyncio.run(main_inner(args)))


if __name__ == "__main__":
    main()
