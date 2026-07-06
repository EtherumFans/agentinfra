#!/usr/bin/env python3
"""Parse llms.txt (markdown index) to extract complete docs structure + sample content.

llms.txt is a Mintlify convention: complete URL + description index for AI ingestion.
Plus fetches raw markdown from .md URLs.
"""
import json
import re
import sys
import io
import urllib.request
from pathlib import Path
from datetime import datetime, timezone

if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

OUTPUT_DIR = Path("docs/corti-reverse-engineered/docs-site")


def fetch(url: str, timeout: int = 15) -> str | None:
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")
    except Exception as e:
        return None


def parse_llms(llms_text: str) -> list[dict]:
    """Parse llms.txt markdown into [(url, title, description)] entries."""
    entries = []
    # Pattern: - [Title](url): description
    for m in re.finditer(r'\[([^\]]+)\]\((https?://docs\.corti\.ai/[^)]+)\)(?::\s*([^\n]+))?', llms_text):
        title = m.group(1).strip()
        url = m.group(2).strip()
        desc = (m.group(3) or "").strip()
        # Clean URL (remove trailing )
        url = url.rstrip(').').rstrip(')').rstrip('.')
        # Skip malformed URLs (have ): in them)
        if '):' in m.group(2) or url.endswith('.md)'):
            url = url.rstrip(')')
        entries.append({"title": title, "url": url, "description": desc})
    return entries


def fetch_markdown(url: str) -> str | None:
    """Fetch raw markdown from Mintlify URL.

    Mintlify serves markdown at <url>.md (append .md if not present).
    """
    if not url.endswith('.md'):
        md_url = url + '.md'
    else:
        md_url = url
    return fetch(md_url, timeout=10)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/4] Loading llms.txt...")
    llms = fetch("https://docs.corti.ai/llms.txt")
    if not llms:
        print("  FAIL: cannot fetch llms.txt")
        return
    (OUTPUT_DIR / "llms.txt").write_text(llms, encoding="utf-8")
    print(f"  saved ({len(llms)} bytes)")

    print("\n[2/4] Parsing index...")
    entries = parse_llms(llms)
    print(f"  parsed {len(entries)} doc entries")

    # Dedupe
    seen = set()
    unique = []
    for e in entries:
        if e['url'] not in seen:
            seen.add(e['url'])
            unique.append(e)
    entries = unique
    print(f"  unique: {len(entries)}")

    # Group by category from URL prefix
    by_category = {}
    for e in entries:
        # Extract first path segment
        path = e['url'].replace('https://docs.corti.ai/', '')
        parts = path.split('/')
        cat = parts[0] if parts else 'other'
        by_category.setdefault(cat, []).append(e)

    print(f"\n[3/4] Categories ({len(by_category)}):")
    for cat in sorted(by_category):
        items = by_category[cat]
        print(f"  {cat:25s} {len(items)} pages")

    # Priority pages — get full markdown content
    priority_urls = [
        # Product positioning
        "https://docs.corti.ai/about/introduction",
        "https://docs.corti.ai/about/compliance",
        "https://docs.corti.ai/about/admin-api",
        "https://docs.corti.ai/about/roadmap",
        # Agentic framework — the KEY architecture
        "https://docs.corti.ai/agentic/overview",
        "https://docs.corti.ai/agentic/architecture",
        "https://docs.corti.ai/agentic/beginners-guide",
        "https://docs.corti.ai/agentic/core-concepts",
        "https://docs.corti.ai/agentic/orchestrator",
        "https://docs.corti.ai/agentic/experts",
        "https://docs.corti.ai/agentic/experts/overview",
        "https://docs.corti.ai/agentic/experts/medical-coding",
        "https://docs.corti.ai/agentic/context-memory",
        "https://docs.corti.ai/agentic/a2a-protocol",
        "https://docs.corti.ai/agentic/quickstart",
        "https://docs.corti.ai/agentic/sdks-integrations",
        "https://docs.corti.ai/agentic/faq",
        # Studio tools
        "https://docs.corti.ai/coding/overview",
        "https://docs.corti.ai/stt/overview",
        "https://docs.corti.ai/textgen/overview",
        "https://docs.corti.ai/assistant/welcome",
        # Authentication / SDK
        "https://docs.corti.ai/authentication/overview",
        "https://docs.corti.ai/sdk/overview",
        # API reference key endpoints
        "https://docs.corti.ai/api-reference/codes/predict-codes",
        "https://docs.corti.ai/api-reference/guided-documents/get-document",
        "https://docs.corti.ai/api-reference/guided-sections/get-section-version",
        "https://docs.corti.ai/api-reference/admin/auth/authenticate-user-and-get-access-token",
        "https://docs.corti.ai/api-reference/console/auth",
    ]

    print(f"\n[4/4] Fetching markdown for {len(priority_urls)} priority pages...")
    detailed = {}
    for url in priority_urls:
        md = fetch_markdown(url)
        if md is None or len(md) < 50:
            print(f"  [SKIP] {url}")
            continue
        # Strip .md from URL for storage
        clean_url = url.replace('.md', '')
        slug = clean_url.replace('https://docs.corti.ai/', '').strip('/').replace('/', '_') or 'root'
        detailed[slug] = {
            "url": clean_url,
            "markdown": md,
            "title": md.split('\n')[0].lstrip('# ').strip() if md.startswith('#') else "",
        }
        print(f"  [OK] {url} → {len(md)} bytes")

    # Save everything
    out = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "index_entries": entries,
        "by_category": {cat: len(items) for cat, items in by_category.items()},
        "detailed_pages": detailed,
    }
    out_file = OUTPUT_DIR / "docs-content.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n[saved] {out_file}")
    print(f"  {len(entries)} index entries")
    print(f"  {len(detailed)} detailed markdown pages")


if __name__ == "__main__":
    main()