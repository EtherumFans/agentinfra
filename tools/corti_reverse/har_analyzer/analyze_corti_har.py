"""
Tool #4 — Corti HAR analyzer.

Parses a HAR (HTTP Archive) file, extracts API endpoints, headers,
bodies, auth mechanism, SSE/WS evidence, file uploads, latency
distribution, and produces a Markdown report + JSON summary.

Usage:
    python tools/corti_reverse/har_analyzer/analyze_corti_har.py \\
        --input artifacts/corti_reverse/hars/<name>.redacted.har \\
        --output-report artifacts/corti_reverse/hars/<name>.report.md \\
        --output-json artifacts/corti_reverse/hars/<name>.report.json

Run after `redact_har.py` to ensure no sensitive data leaks into
the report.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable


# Domains considered "first-party" for Corti (extend as discovered).
CORTI_FIRST_PARTY_PATTERNS = [
    re.compile(r"^https?://[^/]*corti\.ai", re.I),
    re.compile(r"^https?://[^/]*corti\.com", re.I),
    re.compile(r"^https?://[^/]*corti\.app", re.I),
]


def is_first_party(url: str) -> bool:
    return any(p.match(url) for p in CORTI_FIRST_PARTY_PATTERNS)


def path_template(path: str) -> str:
    """Collapse likely-id segments to :id for route grouping.

    Heuristic: any segment that looks like a UUID, integer ID, or
    long alphanumeric hash is replaced with `:id`.
    """
    uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    int_re = re.compile(r"^\d+$")
    hash_re = re.compile(r"^[a-zA-Z0-9_-]{20,}$")
    parts = path.split("/")
    templated = []
    for seg in parts:
        if uuid_re.match(seg) or int_re.match(seg) or hash_re.match(seg):
            templated.append(":id")
        else:
            templated.append(seg)
    return "/".join(templated)


def categorize_headers(headers: Iterable[dict]) -> dict[str, list[str]]:
    """Bucket headers into auth / content-type / custom / other."""
    auth, content, custom, other = [], [], [], []
    for h in headers:
        name = (h.get("name") or "").lower()
        if name in ("authorization", "cookie", "set-cookie", "x-csrf-token", "x-auth-token"):
            auth.append(name)
        elif name in ("content-type", "accept", "content-length", "content-encoding"):
            content.append(name)
        elif name.startswith("x-") or name.startswith("corti-"):
            custom.append(name)
        else:
            other.append(name)
    return {"auth": sorted(set(auth)), "content": sorted(set(content)),
            "custom": sorted(set(custom)), "other": sorted(set(other))}


def infer_auth(entries: list[dict]) -> dict:
    """Detect Bearer / cookie / region / tenant / workspace evidence."""
    bearer = False
    cookies = False
    region = None
    tenant = None
    workspace = None
    for e in entries:
        req = e.get("request", {})
        url = req.get("url", "")
        for h in req.get("headers", []):
            n = (h.get("name") or "").lower()
            v = h.get("value") or ""
            if n == "authorization" and v.lower().startswith("bearer"):
                bearer = True
            if n == "cookie":
                cookies = True
            if n in ("x-region", "x-corti-region"):
                region = region or v
            if n in ("x-tenant", "x-corti-tenant", "x-tenant-id"):
                tenant = tenant or v
            if n in ("x-workspace", "x-corti-workspace", "x-workspace-id"):
                workspace = workspace or v
        # Path-based region/tenant
        m = re.search(r"/(eu|us|cn|asia|emea)(/|$)", url, re.I)
        if m and not region:
            region = m.group(1).lower()
    return {"bearer_token": bearer, "cookie_auth": cookies,
            "region_header": region, "tenant_header": tenant,
            "workspace_header": workspace}


def detect_streaming(entries: list[dict]) -> dict:
    """Detect SSE / WebSocket / long-polling evidence."""
    sse = ws = long_poll = False
    for e in entries:
        resp = e.get("response", {})
        mime = (resp.get("content") or {}).get("mimeType", "")
        url = (e.get("request") or {}).get("url", "")
        if "text/event-stream" in mime:
            sse = True
        if e.get("_resourceType") == "websocket" or "ws" in url:
            ws = True
        # Long-polling: response status 200 + duration > 20s
        t = e.get("time", 0)
        if t and t > 20000:
            long_poll = True
    return {"sse": sse, "websocket": ws, "long_polling": long_poll}


def detect_file_upload(entries: list[dict]) -> list[dict]:
    """Find multipart/form-data POST bodies."""
    uploads = []
    for e in entries:
        req = e.get("request") or {}
        post = req.get("postData") or {}
        mime = post.get("mimeType", "")
        if "multipart/form-data" in mime:
            uploads.append({
                "url": req.get("url"),
                "method": req.get("method"),
                "params": [p.get("name") for p in post.get("params", [])],
            })
    return uploads


def summarize_body(body: Any, max_len: int = 200) -> dict:
    """Infer JSON shape from a body string."""
    if not body:
        return {"empty": True}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return {"text_preview": body[:max_len]}
    if isinstance(body, dict):
        keys = list(body.keys())[:20]
        types = {k: type(body[k]).__name__ for k in keys
                 if not isinstance(body[k], (dict, list))}
        nested = {k: "object" for k in keys if isinstance(body[k], dict)}
        arrays = {k: f"array[{len(body[k])}]" for k in keys if isinstance(body[k], list)}
        return {"object_keys": keys, "leaf_types": types,
                "nested_objects": nested, "arrays": arrays}
    if isinstance(body, list):
        return {"array_length": len(body),
                "first_item_keys": list(body[0].keys())[:20] if body and isinstance(body[0], dict) else None}
    return {"type": type(body).__name__}


def latency_distribution(entries: list[dict]) -> dict:
    """Compute latency stats by route template."""
    by_route: dict[str, list[float]] = defaultdict(list)
    for e in entries:
        req = e.get("request") or {}
        url = req.get("url", "")
        if not is_first_party(url):
            continue
        # Strip query
        path = url.split("/", 3)[-1] if "://" in url else url
        path = "/" + path.split("?", 1)[0]
        templ = path_template(path)
        t = e.get("time", 0) or 0
        by_route[req.get("method", "?") + " " + templ].append(t)
    out = {}
    for route, times in by_route.items():
        if not times:
            continue
        times_sorted = sorted(times)
        n = len(times_sorted)
        out[route] = {
            "count": n,
            "min_ms": times_sorted[0],
            "max_ms": times_sorted[-1],
            "median_ms": times_sorted[n // 2],
            "p95_ms": times_sorted[min(n - 1, int(n * 0.95))],
        }
    return out


def analyze(har_path: Path) -> dict:
    raw = json.loads(har_path.read_text(encoding="utf-8"))
    entries = raw.get("log", {}).get("entries", [])
    if not entries:
        return {"error": "no entries in HAR"}

    # Endpoints
    endpoints: dict[str, dict] = {}
    for e in entries:
        req = e.get("request") or {}
        url = req.get("url", "")
        if not is_first_party(url):
            continue
        method = req.get("method", "?")
        path = url.split("://", 1)[-1].split("/", 3)[-1] if "://" in url else url
        path = "/" + path.split("?", 1)[0]
        templ = path_template(path)
        key = f"{method} {templ}"
        if key not in endpoints:
            endpoints[key] = {"methods": [method], "path_template": templ,
                              "statuses": [], "request_headers": [],
                              "response_headers": [], "request_body": None,
                              "response_body": None}
        resp = e.get("response") or {}
        endpoints[key]["statuses"].append(resp.get("status", 0))
        endpoints[key]["request_headers"].extend(req.get("headers", []))
        endpoints[key]["response_headers"].extend(resp.get("headers", []))
        # Capture first non-empty body sample
        if endpoints[key]["request_body"] is None and req.get("postData"):
            endpoints[key]["request_body"] = summarize_body(req["postData"].get("text"))
        if endpoints[key]["response_body"] is None and resp.get("content"):
            endpoints[key]["response_body"] = summarize_body(
                resp["content"].get("text"))

    # Aggregate
    summary = {
        "total_entries": len(entries),
        "first_party_entries": sum(1 for e in entries if is_first_party((e.get("request") or {}).get("url", ""))),
        "endpoints": {k: {**v,
                          "request_header_categories": categorize_headers(v["request_headers"]),
                          "response_header_categories": categorize_headers(v["response_headers"]),
                          "request_headers": None, "response_headers": None}
                      for k, v in endpoints.items()},
        "auth_mechanism": infer_auth(entries),
        "streaming": detect_streaming(entries),
        "file_uploads": detect_file_upload(entries),
        "latency_by_route": latency_distribution(entries),
    }
    return summary


def to_markdown(report: dict) -> str:
    if "error" in report:
        return f"**Error**: {report['error']}\n"
    lines = ["# Corti HAR Analysis Report\n",
             f"- Total entries: {report['total_entries']}",
             f"- First-party entries: {report['first_party_entries']}",
             f"- Unique endpoints: {len(report['endpoints'])}",
             ""]
    lines.append("## Auth Mechanism\n")
    for k, v in report["auth_mechanism"].items():
        lines.append(f"- **{k}**: {v}")
    lines.append("\n## Streaming Evidence\n")
    for k, v in report["streaming"].items():
        lines.append(f"- **{k}**: {v}")
    lines.append(f"\n## File Uploads ({len(report['file_uploads'])})\n")
    for u in report["file_uploads"][:10]:
        lines.append(f"- `{u['method']} {u['url']}` params={u['params']}")
    lines.append("\n## Endpoints\n")
    for route, info in sorted(report["endpoints"].items()):
        statuses = Counter(info["statuses"]).most_common()
        lines.append(f"### `{route}`")
        lines.append(f"- Statuses: {dict(statuses)}")
        lines.append(f"- Request headers: {info['request_header_categories']}")
        if info.get("request_body"):
            lines.append(f"- Request body: `{info['request_body']}`")
        if info.get("response_body"):
            lines.append(f"- Response body: `{info['response_body']}`")
        lines.append("")
    lines.append("\n## Latency by Route (ms)\n")
    lines.append("| Route | Count | Min | Median | P95 | Max |")
    lines.append("|---|---|---|---|---|---|")
    for route, stats in sorted(report["latency_by_route"].items(),
                               key=lambda x: -x[1]["count"]):
        lines.append(f"| {route} | {stats['count']} | {stats['min_ms']:.0f} | "
                     f"{stats['median_ms']:.0f} | {stats['p95_ms']:.0f} | {stats['max_ms']:.0f} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Path to HAR file")
    p.add_argument("--output-report", help="Path to write Markdown report")
    p.add_argument("--output-json", help="Path to write JSON summary")
    p.add_argument("--check-sse", action="store_true",
                   help="Print SSE chunk count (verbose)")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 2

    report = analyze(in_path)
    md = to_markdown(report)

    if args.output_report:
        Path(args.output_report).write_text(md, encoding="utf-8")
        print(f"Wrote report: {args.output_report}")
    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8")
        print(f"Wrote JSON: {args.output_json}")
    if not args.output_report and not args.output_json:
        print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
