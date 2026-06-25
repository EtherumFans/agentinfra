"""build_medcoder_icd9cm3_index.py — Build the FAISS index for ICD-9-CM-3 retrieval.

Loads the iCoDerA catalog, embeds every code (name + synonyms) with BGE-M3,
and writes:

  <out>/faiss_icd9cm3.index    — FAISS IndexFlatIP over 13,617 × 1024 float32
  <out>/metadata_icd9cm3.pkl   — list[dict] aligned with the index, one row per code

This mirrors ``build_medcoder_index.py`` (which builds the ICD-10-CN index)
so the two indices can be loaded side-by-side for procedure code retrieval.

Usage:
    python scripts/build_medcoder_icd9cm3_index.py \\
        --asset-dir E:/iCoDerA/DataAsset \\
        --out data/medcoder

If the BGE-M3 model isn't cached, it is downloaded (~2.3 GB) into
``data/medcoder/models/`` and reused on subsequent runs.

The script is intentionally side-effect-free on the iCoDerA asset directory
(read-only).

M2.5 — added in response to the index-recovery project. The ICD-9-CM-3
index is **new** — it was never built before. M2.5 adds it to close the
procedure-side retrieval gap.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import sys
import time
from pathlib import Path

# Make backend root importable when run as ``python scripts/build_medcoder_icd9cm3_index.py``.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("build_medcoder_icd9cm3_index")


def _build_text_for_embedding(entry: dict) -> str:
    """Concatenate code, name_cn, name_en, top synonyms into a single embedding string."""
    parts: list[str] = [entry.get("name_cn", "")]
    if entry.get("name_en"):
        parts.append(entry["name_en"])
    for s in list(entry.get("synonyms_cn") or [])[:3]:
        if s and s not in parts:
            parts.append(s)
    for s in list(entry.get("synonyms_en") or [])[:2]:
        if s and s not in parts:
            parts.append(s)
    # Prefix with the code so embedding retains lexical signal.
    code = entry.get("code", "")
    return f"{code} " + " | ".join(p for p in parts if p)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--asset-dir",
        default=os.environ.get("ICODER_DATA_ASSET_DIR", r"E:\iCoDerA\DataAsset"),
        help="Path to the iCoDerA DataAsset directory (read-only).",
    )
    parser.add_argument(
        "--out",
        default="data/medcoder",
        help="Output directory for faiss_icd9cm3.index + metadata_icd9cm3.pkl",
    )
    parser.add_argument(
        "--model-dir",
        default="data/medcoder/models",
        help="Where the BGE-M3 model is cached (shared with ICD-10 build).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="If > 0, only embed the first N codes (for smoke tests).",
    )
    args = parser.parse_args(argv)

    t0 = time.time()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load catalog (UTF-8 — Windows defaults to GBK).
    catalog_path = Path(args.asset_dir) / "icd9cm3_code_catalog.json"
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    entries: list[dict] = catalog.get("codes", [])
    if args.limit and args.limit > 0:
        entries = entries[: args.limit]
    logger.info("Loaded %d codes (limit=%s) from %s", len(entries), args.limit, catalog_path)

    if not entries:
        logger.error("No codes loaded from %s — abort.", catalog_path)
        return 1

    # 2. Build embedding texts.
    texts = [_build_text_for_embedding(e) for e in entries]
    logger.info("Sample embedding text: %r", texts[0])

    # 3. Load embedder + embed.
    from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (  # noqa: E402
        BGEEmbedder,
    )

    embedder = BGEEmbedder(model_dir=args.model_dir)
    logger.info("Loading BGE-M3 (lazy). This may take 30-180s on first run...")
    embedder.ensure_loaded()
    logger.info("BGE-M3 loaded (dim=%d). Embedding %d codes...", embedder.dim, len(texts))
    t_emb = time.time()
    vectors = embedder.embed(texts)
    logger.info("Embedding done in %.1fs", time.time() - t_emb)

    # 4. Build FAISS index.
    try:
        import faiss  # type: ignore
        import numpy as np  # type: ignore
    except ImportError as e:
        logger.error(
            "faiss-cpu / numpy not installed: %s. Run `pip install faiss-cpu numpy`.",
            e,
        )
        return 1

    arr = np.asarray(vectors, dtype="float32")
    assert arr.shape == (len(entries), embedder.dim), f"shape mismatch: {arr.shape}"
    # Vectors are already L2-normalized; inner product = cosine.
    index = faiss.IndexFlatIP(embedder.dim)
    index.add(arr)
    logger.info("FAISS index built: ntotal=%d dim=%d", index.ntotal, embedder.dim)

    # 5. Persist index + metadata.
    faiss_path = out_dir / "faiss_icd9cm3.index"
    meta_path = out_dir / "metadata_icd9cm3.pkl"
    faiss.write_index(index, str(faiss_path))
    meta = [
        {
            "code": e.get("code", ""),
            "name_cn": e.get("name_cn", ""),
            "name_en": e.get("name_en", ""),
            "category": e.get("category", ""),
            "chapter_no": e.get("chapter_no", ""),
            "chapter_name": e.get("chapter_name", ""),
            "chapter_range": e.get("chapter_range", ""),
            "is_extended": e.get("is_extended", False),
            "insurance_code": e.get("insurance_code", ""),
            "is_insurance_gray": e.get("is_insurance_gray", False),
        }
        for e in entries
    ]
    with open(meta_path, "wb") as f:
        pickle.dump(meta, f, protocol=pickle.HIGHEST_PROTOCOL)

    size_mb = faiss_path.stat().st_size / 1024 / 1024
    meta_mb = meta_path.stat().st_size / 1024 / 1024
    logger.info(
        "Wrote %s (%.1f MB) and %s (%.1f MB). Total time: %.1fs",
        faiss_path, size_mb, meta_path, meta_mb, time.time() - t0,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
