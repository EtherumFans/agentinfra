"""download_bge_m3.py — Download BAAI/bge-m3 model weights via the hf-mirror.com endpoint.

The default huggingface_hub library download path fails from this network
(SSL EOF + HEAD-call issues against the mirror). We use ``requests`` directly,
which works reliably to ``https://hf-mirror.com``.

Files we need (per BGE-M3 repo, sufficient for sentence-transformers):

  config.json                          ~1 KB
  config_sentence_transformers.json    ~0.1 KB
  modules.json                         ~0.3 KB
  sentence_bert_config.json            ~0.05 KB
  sentencepiece.bpe.model              ~4.7 MB
  special_tokens_map.json              ~0.2 KB
  tokenizer.json                       ~17 MB
  tokenizer_config.json                ~0.3 KB
  1_Pooling/config.json                ~0.05 KB
  pytorch_model.bin                    ~2271 MB  (the heavy one)

Total ≈ 2.3 GB. Files are placed in ``data/medcoder/models/models--BAAI--bge-m3/``
following the standard HF cache layout so sentence-transformers picks them up.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("download_bge_m3")

# Mirror that works from this network (huggingface.co upstream is blocked / flaky).
ENDPOINT = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com").rstrip("/")
REPO_ID = "BAAI/bge-m3"
REVISION = "main"

# All files needed by sentence-transformers to instantiate the model.
REQUIRED_FILES = [
    "config.json",
    "config_sentence_transformers.json",
    "modules.json",
    "sentence_bert_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "1_Pooling/config.json",
    "pytorch_model.bin",
]


def _resolve_revision(repo_id: str, revision: str) -> str:
    """Resolve the latest commit SHA for ``revision`` (branch name)."""
    if len(revision) == 40 and all(c in "0123456789abcdef" for c in revision):
        return revision
    url = f"{ENDPOINT}/api/models/{repo_id}"
    r = requests.get(url, timeout=20)
    r.raise_for_status()
    data = r.json()
    sha = data.get("sha")
    if not sha:
        raise RuntimeError(f"No sha in {url} response: {data}")
    return sha


def _download_one(
    repo_id: str, revision: str, filename: str, dest: Path,
    max_attempts: int = 5,
) -> None:
    """Stream one file from the mirror to ``dest`` with resume on disconnect.

    The mirror returns a 302 redirect to a Xet-CAS storage URL; ``requests``
    follows it automatically. The connection is occasionally reset (10054)
    mid-stream — we retry with exponential backoff and resume from the
    last successfully-written byte via HTTP ``Range:``.
    """
    url = f"{ENDPOINT}/{repo_id}/resolve/{revision}/{filename}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".partial")
    if dest.exists() and dest.stat().st_size > 0:
        logger.info("✓ %s (already present, %d MB)", filename, dest.stat().st_size // (1024 * 1024))
        return

    last_size = tmp.stat().st_size if tmp.exists() else 0
    attempt = 0
    t0 = time.time()
    while attempt < max_attempts:
        attempt += 1
        headers = {}
        mode = "ab" if last_size > 0 else "wb"
        if last_size > 0:
            headers["Range"] = f"bytes={last_size}-"
        try:
            with requests.get(
                url, stream=True, timeout=(20, 120),
                allow_redirects=True, headers=headers,
            ) as r:
                if r.status_code not in (200, 206):
                    r.raise_for_status()
                total = int(r.headers.get("Content-Length", 0)) + last_size
                written = last_size
                with open(tmp, mode) as f:
                    for chunk in r.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)
                            if total and written // (50 * 1024 * 1024) != (written - len(chunk)) // (50 * 1024 * 1024):
                                pct = written * 100 // total
                                mb = written / (1024 * 1024)
                                logger.info("  … %s: %.0f MB (%d%%) [attempt %d]", filename, mb, pct, attempt)
            # success
            tmp.rename(dest)
            elapsed = time.time() - t0
            mb = dest.stat().st_size / (1024 * 1024)
            speed = mb / elapsed if elapsed else 0
            logger.info("✓ %s (%.1f MB in %.1fs, %.1f MB/s)", filename, mb, elapsed, speed)
            return
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_size = tmp.stat().st_size if tmp.exists() else 0
            logger.warning(
                "  ! %s: connection issue (resumable at %d MB): %s — retry %d/%d",
                filename, last_size // (1024 * 1024), str(e)[:100], attempt, max_attempts,
            )
            time.sleep(min(2 ** attempt, 30))
            continue
    raise RuntimeError(f"Failed to download {filename} after {max_attempts} attempts")


def _populate_cache_dir(
    repo_id: str, revision: str, cache_root: Path, snapshot_dir: Path,
) -> None:
    """Place files in the HF cache layout sentence-transformers expects.

    Layout::

        <cache_root>/models--<owner>--<name>/
            refs/<revision>          -> <revision_sha>
            snapshots/<revision_sha>/<files>
            blobs/<sha256>           -> hardlink to snapshot file
    """
    # refs/<revision> -> sha
    refs_dir = cache_root / "refs"
    refs_dir.mkdir(parents=True, exist_ok=True)
    (refs_dir / revision).write_text(revision, encoding="utf-8")
    # snapshots/<sha>/...
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    for f in REQUIRED_FILES:
        dest = snapshot_dir / f
        if not dest.exists() or dest.stat().st_size == 0:
            _download_one(repo_id, revision, f, dest)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/medcoder/models",
                        help="Local model cache root (data/medcoder/models).")
    parser.add_argument("--repo-id", default=REPO_ID)
    parser.add_argument("--revision", default=REVISION)
    args = parser.parse_args(argv)

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    cache_dir = out_root / f"models--{args.repo_id.replace('/', '--')}"
    logger.info("Mirror: %s", ENDPOINT)
    logger.info("Repo:   %s@%s", args.repo_id, args.revision)
    logger.info("Cache:  %s", cache_dir)

    # Resolve the revision SHA once so the file layout is reproducible.
    sha = _resolve_revision(args.repo_id, args.revision)
    logger.info("Resolved %s -> %s", args.revision, sha)
    snapshot_dir = cache_dir / "snapshots" / sha
    _populate_cache_dir(args.repo_id, sha, cache_dir, snapshot_dir)

    # Verify the cache layout is what sentence-transformers expects.
    has_pytorch = (snapshot_dir / "pytorch_model.bin").exists()
    has_config = (snapshot_dir / "config.json").exists()
    logger.info("Cache layout:")
    logger.info("  %s -> %s", cache_dir / "refs" / args.revision, sha)
    logger.info("  %s (%d files)", snapshot_dir, len(list(snapshot_dir.rglob("*"))))
    logger.info("  pytorch_model.bin present: %s", has_pytorch)
    logger.info("  config.json present: %s", has_config)
    if not has_pytorch or not has_config:
        logger.error("Cache incomplete — both pytorch_model.bin and config.json required.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())