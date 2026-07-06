"""
Convert the existing Corti deep-crawler output (api-contracts-v2.json)
to HAR 1.2 format so the existing tools (analyze_corti_har.py,
extract_route_graph.py, redact_har.py) can consume it.

The deep-crawler output has the shape:
{
  "captured_at": "...",
  "total_requests": N,
  "total_clicks": ...,
  "requests": [
    {
      "id": 0,
      "ts": "ISO 8601",
      "method": "GET",
      "url": "...",
      "resource_type": "document|xhr|...",
      "req_body": null | str,
      "resp_status": 200,
      "resp_headers": {...},
      "resp_body": "..." | null
    },
    ...
  ]
}

Output HAR 1.2 shape (per spec at http://www.softwareishard.com/blog/har-12-spec/):
{
  "log": {
    "version": "1.2",
    "creator": {"name": "...", "version": "..."},
    "entries": [
      {
        "startedDateTime": "ISO 8601",
        "time": 0,
        "request": {
          "method": "GET",
          "url": "...",
          "httpVersion": "HTTP/1.1",
          "cookies": [],
          "headers": [],
          "queryString": [],
          "headersSize": -1,
          "bodySize": -1
        },
        "response": {
          "status": 200,
          "statusText": "",
          "httpVersion": "HTTP/1.1",
          "cookies": [],
          "headers": [...],
          "content": {"size": 0, "mimeType": "...", "text": "..."},
          "redirectURL": "",
          "headersSize": -1,
          "bodySize": -1
        },
        "cache": {},
        "timings": { "send": 0, "wait": 0, "receive": 0 },
        "_resourceType": "xhr"
      }
    ]
  }
}

Usage:
    python tools/corti_reverse/har_analyzer/convert_crawl_to_har.py \\
        --input docs/corti-reverse-engineered/api-contracts-v2.json \\
        --output artifacts/corti_reverse/hars/corti-deep-crawl-v2.har
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def guess_mime(resource_type: str, resp_headers: dict) -> str:
    """Pick a plausible mimeType based on resource_type and Content-Type header."""
    ct = (resp_headers.get("content-type") or "").lower()
    if ct:
        return ct.split(";")[0].strip()
    rt = (resource_type or "").lower()
    return {
        "document": "text/html",
        "xhr": "application/json",
        "fetch": "application/json",
        "script": "application/javascript",
        "stylesheet": "text/css",
        "image": "image/png",
        "font": "font/woff2",
        "websocket": "application/json",
        "manifest": "application/manifest+json",
        "other": "application/octet-stream",
    }.get(rt, "application/octet-stream")


def headers_dict_to_har(headers: dict) -> list[dict]:
    """Convert a {name: value} dict to HAR headers list of {name, value}."""
    if not isinstance(headers, dict):
        return []
    return [{"name": str(k), "value": str(v)} for k, v in headers.items()]


def convert(crawl_path: Path) -> dict:
    raw = json.loads(crawl_path.read_text(encoding="utf-8"))
    requests = raw.get("requests", []) if isinstance(raw, dict) else []
    entries: list[dict] = []
    for r in requests:
        method = (r.get("method") or "GET").upper()
        url = r.get("url") or ""
        ts = r.get("ts") or ""
        resource_type = r.get("resource_type") or "other"
        req_body = r.get("req_body")
        resp_status = r.get("resp_status") or 0
        resp_headers = r.get("resp_headers") or {}
        resp_body = r.get("resp_body")

        # Request headers — the deep crawler doesn't capture them; leave empty.
        req_headers_har: list[dict] = []
        # Synthesize a Content-Type header for POST bodies.
        if req_body:
            req_headers_har.append({"name": "Content-Type", "value": "application/json"})

        # Response headers — convert dict to list.
        resp_headers_har = headers_dict_to_har(resp_headers)

        # Request postData.
        post_data = None
        if req_body:
            post_data = {
                "mimeType": "application/json",
                "text": req_body if isinstance(req_body, str) else json.dumps(req_body),
            }

        # Response content.
        mime = guess_mime(resource_type, resp_headers)
        content = {
            "size": len(resp_body.encode("utf-8")) if isinstance(resp_body, str) else 0,
            "mimeType": mime,
        }
        if isinstance(resp_body, str) and resp_body:
            content["text"] = resp_body

        entry = {
            "startedDateTime": ts,
            "time": 0,  # not captured by deep crawler
            "request": {
                "method": method,
                "url": url,
                "httpVersion": "HTTP/1.1",
                "cookies": [],
                "headers": req_headers_har,
                "queryString": [],
                "headersSize": -1,
                "bodySize": len(req_body.encode("utf-8")) if isinstance(req_body, str) else 0,
                "postData": post_data,
            },
            "response": {
                "status": resp_status,
                "statusText": "",
                "httpVersion": "HTTP/1.1",
                "cookies": [],
                "headers": resp_headers_har,
                "content": content,
                "redirectURL": resp_headers.get("location", "") if isinstance(resp_headers, dict) else "",
                "headersSize": -1,
                "bodySize": content["size"],
            },
            "cache": {},
            "timings": {"send": 0, "wait": 0, "receive": 0},
            "_resourceType": resource_type,
            "connection": "",
            "pageref": "page_1",
        }
        entries.append(entry)

    return {
        "log": {
            "version": "1.2",
            "creator": {
                "name": "icoder-deep-crawler-to-har",
                "version": "1.0",
                "_source": str(crawl_path),
                "_captured_at": raw.get("captured_at") if isinstance(raw, dict) else "",
                "_total_requests": raw.get("total_requests") if isinstance(raw, dict) else len(entries),
            },
            "pages": [
                {
                    "startedDateTime": entries[0]["startedDateTime"] if entries else "",
                    "id": "page_1",
                    "title": "Corti deep crawl v2",
                    "pageTimings": {"onContentLoad": -1, "onLoad": -1},
                }
            ],
            "entries": entries,
        }
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Path to api-contracts-v2.json")
    p.add_argument("--output", required=True, help="Path to write HAR file")
    args = p.parse_args()

    in_path = Path(args.input)
    if not in_path.exists():
        print(f"Input not found: {in_path}", file=sys.stderr)
        return 2

    har = convert(in_path)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(har, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote HAR: {out_path}")
    print(f"  Entries: {len(har['log']['entries'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
