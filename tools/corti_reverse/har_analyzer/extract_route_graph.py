"""
Tool #7 — Route graph extractor.

Builds a route graph from one or more (already-redacted) HAR files.

- Nodes: unique API endpoints (method + path template, with `:id`
  substituted for path params).
- Edges: caller→callee ordering observed in HAR (e.g., page load
  fires `GET /agents` then `GET /agents/{id}/experts`).
- Cluster by domain (corti.ai vs assets.corti.ai vs external).
- Mark A2A / MCP-like routes by pattern match.

Output: Graphviz DOT + Markdown adjacency list.

Usage:
    python tools/corti_reverse/har_analyzer/extract_route_graph.py \\
        --input artifacts/corti_reverse/hars/*.redacted.har \\
        --output-dot artifacts/corti_reverse/route_graph.dot \\
        --output-md docs/reverse_engineering/corti/CORTI_ROUTE_GRAPH.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable


CORTI_FIRST_PARTY = re.compile(r"^https?://[^/]*corti\.(ai|com|app)", re.I)
A2A_PATTERN = re.compile(r"/a2a|/v1/agents/.+/(?:card|run|tasks?|messages?)",
                         re.I)
MCP_PATTERN = re.compile(r"/mcp|/tools/(?:list|call)|/resources/",
                         re.I)


def is_first_party(url: str) -> bool:
    return bool(CORTI_FIRST_PARTY.match(url))


def path_template(path: str) -> str:
    uuid_re = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                         r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
    int_re = re.compile(r"^\d+$")
    hash_re = re.compile(r"^[a-zA-Z0-9_-]{20,}$")
    return "/".join(":id" if (uuid_re.match(s) or int_re.match(s)
                              or hash_re.match(s)) else s
                    for s in path.split("/"))


def domain_of(url: str) -> str:
    m = re.match(r"https?://([^/]+)/?", url)
    return m.group(1).lower() if m else "unknown"


def route_key(method: str, url: str) -> str | None:
    if not is_first_party(url):
        return None
    path = url.split("://", 1)[-1].split("/", 3)[-1] if "://" in url else url
    path = "/" + path.split("?", 1)[0]
    return f"{method} {path_template(path)}"


def is_a2a(route: str) -> bool:
    return bool(A2A_PATTERN.search(route))


def is_mcp(route: str) -> bool:
    return bool(MCP_PATTERN.search(route))


def extract_routes(har_path: Path) -> list[tuple[str, str, str]]:
    """Return list of (timestamp, route, domain) in HAR order."""
    har = json.loads(har_path.read_text(encoding="utf-8"))
    out = []
    for e in har.get("log", {}).get("entries", []):
        req = e.get("request") or {}
        url = req.get("url", "")
        method = req.get("method", "?")
        route = route_key(method, url)
        if not route:
            continue
        ts = e.get("startedDateTime", "")
        out.append((ts, route, domain_of(url)))
    return out


def build_adjacency(per_har_routes: list[list[tuple[str, str, str]]]) -> dict:
    """For each HAR, count transitions A→B where A immediately precedes B."""
    edges: dict[tuple[str, str], int] = defaultdict(int)
    nodes: set[str] = set()
    for routes in per_har_routes:
        # Sort by timestamp
        sorted_routes = sorted(routes, key=lambda x: x[0])
        seen_in_har: set[str] = set()
        prev: str | None = None
        for ts, route, domain in sorted_routes:
            nodes.add(route)
            if prev and prev != route:
                edges[(prev, route)] += 1
            prev = route
    return {"nodes": sorted(nodes), "edges": dict(edges)}


def to_dot(graph: dict) -> str:
    lines = ["digraph corti_routes {", "  rankdir=LR;",
             "  node [shape=box, fontname=\"Helvetica\"];"]
    for n in graph["nodes"]:
        attrs = []
        if is_a2a(n):
            attrs.append("color=blue, style=filled, fillcolor=lightblue")
        elif is_mcp(n):
            attrs.append("color=green, style=filled, fillcolor=lightgreen")
        attr_str = ", ".join(attrs) if attrs else ""
        lines.append(f'  "{n}" [{attr_str}];')
    for (a, b), w in sorted(graph["edges"].items(),
                            key=lambda x: -x[1]):
        lines.append(f'  "{a}" -> "{b}" [label="{w}"];')
    lines.append("}")
    return "\n".join(lines)


def to_markdown(graph: dict, har_files: list[str]) -> str:
    lines = ["# Corti Route Graph\n",
             f"Built from {len(har_files)} HAR file(s).\n",
             f"- Nodes (unique routes): {len(graph['nodes'])}",
             f"- Edges (transitions): {len(graph['edges'])}",
             ""]
    # A2A / MCP routes
    a2a = [n for n in graph["nodes"] if is_a2a(n)]
    mcp = [n for n in graph["nodes"] if is_mcp(n)]
    lines.append("## A2A-like Routes\n")
    for r in a2a:
        lines.append(f"- `{r}`")
    lines.append(f"\n## MCP-like Routes\n")
    for r in mcp:
        lines.append(f"- `{r}`")
    lines.append("\n## Top Transitions (A → B, weighted by occurrence)\n")
    lines.append("| From | To | Count |")
    lines.append("|---|---|---|")
    for (a, b), w in sorted(graph["edges"].items(),
                            key=lambda x: -x[1])[:30]:
        lines.append(f"| `{a}` | `{b}` | {w} |")
    lines.append("\n## All Routes\n")
    for n in sorted(graph["nodes"]):
        lines.append(f"- `{n}`")
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--input", nargs="+", required=True,
                   help="One or more redacted HAR files")
    p.add_argument("--output-dot", help="Output Graphviz DOT path")
    p.add_argument("--output-md", help="Output Markdown path")
    args = p.parse_args()

    if not args.output_dot and not args.output_md:
        print("At least one of --output-dot / --output-md required",
              file=sys.stderr)
        return 2

    per_har: list[list[tuple[str, str, str]]] = []
    for har_path in args.input:
        p = Path(har_path)
        if not p.exists():
            print(f"Skipping (not found): {p}", file=sys.stderr)
            continue
        per_har.append(extract_routes(p))

    graph = build_adjacency(per_har)
    if args.output_dot:
        Path(args.output_dot).write_text(to_dot(graph), encoding="utf-8")
        print(f"Wrote DOT: {args.output_dot}")
    if args.output_md:
        Path(args.output_md).write_text(
            to_markdown(graph, args.input), encoding="utf-8")
        print(f"Wrote MD: {args.output_md}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
