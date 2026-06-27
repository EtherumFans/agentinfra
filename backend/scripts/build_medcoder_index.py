"""build_medcoder_index.py — Build the FAISS index for ICD-10-CN retrieval.

Loads the iCoDerA catalog, embeds every code (name + synonyms) with BGE-M3,
and writes:

  <out>/faiss.index    — FAISS IndexFlatIP over 37,897 × 1024 float32
  <out>/metadata.pkl   — list[dict] aligned with the index, one row per code

The embedding text for a code concatenates the canonical Chinese name,
English name, and up to 3 Chinese synonyms / 2 English synonyms — exactly
the information a retrieval system should match on.

Usage:
    python scripts/build_medcoder_index.py \\
        --asset-dir E:/iCoDerA/DataAsset \\
        --out data/medcoder

If the BGE-M3 model isn't cached, it is downloaded (~2.3 GB) into
``data/medcoder/models/`` and reused on subsequent runs.

The script is intentionally side-effect-free on the iCoDerA asset directory
(read-only).
"""
from __future__ import annotations

import argparse
import logging
import os
import pickle
import sys
import time
from pathlib import Path

# Make backend root importable when run as ``python scripts/build_medcoder_index.py``.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("build_medcoder_index")

# Phase A A1 (2026-06-25): embed in chunks so a single failed chunk doesn't
# lose the entire 1+ hour build, and so progress is observable. 1024 codes
# × 1024 dim × 4 bytes ≈ 4 MB per chunk — comfortable on CPU.
EMBED_CHUNK = 1024


def _build_text_for_embedding(entry) -> str:
    """Concatenate code, name_cn, name_en, top synonyms into a single embedding string."""
    parts: list[str] = [entry.name_cn]
    if entry.name_en:
        parts.append(entry.name_en)
    for s in list(entry.synonyms_cn)[:3]:
        if s and s not in parts:
            parts.append(s)
    for s in list(entry.synonyms_en)[:2]:
        if s and s not in parts:
            parts.append(s)
    # Prefix with the code so embedding retains lexical signal.
    return f"{entry.code} " + " | ".join(parts)


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
        help="Output directory for faiss.index + metadata.pkl",
    )
    parser.add_argument(
        "--model-dir",
        default="data/medcoder/models",
        help="Where the BGE-M3 model is cached.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="If > 0, only embed the first N codes (for smoke tests).",
    )
    # E1.9 (2026-06-27): pin BGE-M3 dtype at index-build time. fp16 halves
    # peak memory (3-4 GB → 1.5-2 GB) so the build completes on dev box
    # (16 GB RAM) without OOM. Default ``None`` → resolved inside main()
    # from MEDCODER_BGE_DTYPE env var so monkeypatch.delenv after import
    # still takes effect (argparse default is evaluated at module load).
    parser.add_argument(
        "--bge-dtype",
        default=None,
        choices=("float32", "float16", "bfloat16"),
        help="BGE-M3 torch_dtype for the model load. Default: MEDCODER_BGE_DTYPE env (float16).",
    )
    args = parser.parse_args(argv)

    t0 = time.time()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Load catalog.
    from app.services.icd10cn_loader import ICD10CNLoader  # noqa: E402

    loader = ICD10CNLoader(asset_dir=args.asset_dir)
    stats = loader.load()
    entries = loader.all_codes()
    if args.limit and args.limit > 0:
        entries = entries[: args.limit]
    logger.info("Loaded %d codes (limit=%s) from %s", len(entries), args.limit, args.asset_dir)

    # 2. Build embedding texts.
    texts = [_build_text_for_embedding(e) for e in entries]
    logger.info("Sample embedding text: %r", texts[0] if texts else "")

    # 3. Load embedder + embed.
    from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (  # noqa: E402
        BGEEmbedder,
    )

    embedder = BGEEmbedder(
        model_dir=args.model_dir,
        torch_dtype=(args.bge_dtype or os.environ.get("MEDCODER_BGE_DTYPE", "float16")),
    )
    logger.info("Loading BGE-M3 (lazy). This may take 30-180s on first run...")
    embedder.ensure_loaded()
    logger.info("BGE-M3 loaded (dim=%d). Embedding %d codes in chunks of %d...",
                embedder.dim, len(texts), EMBED_CHUNK)
    t_emb = time.time()
    # Embed in chunks of EMBED_CHUNK codes (default 1024) so that progress is
    # observable in the log and so that a single failed chunk doesn't lose
    # the entire 1+ hour investment. ~150 MB total (38k × 1024 float32) but
    # chunking bounds peak memory and surfaces errors fast.
    import numpy as np  # noqa: E402
    chunks: list[np.ndarray] = []
    for start in range(0, len(texts), EMBED_CHUNK):
        end = min(start + EMBED_CHUNK, len(texts))
        logger.info("  embedding chunk [%d:%d] ...", start, end)
        chunk_arr = embedder.embed_numpy(texts[start:end])
        chunks.append(chunk_arr)
        elapsed = time.time() - t_emb
        rate = (end / elapsed) if elapsed > 0 else 0
        logger.info("  ... done (%.1fs, ~%.1f codes/s)", elapsed, rate)
    arr = np.concatenate(chunks, axis=0).astype("float32")
    logger.info("Embedding done in %.1fs; arr.shape=%s", time.time() - t_emb, arr.shape)

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

    assert arr.shape == (len(entries), embedder.dim), f"shape mismatch: {arr.shape}"
    # Vectors are already L2-normalized; inner product = cosine.
    index = faiss.IndexFlatIP(embedder.dim)
    # Add in chunks to bound peak memory; for 38k × 1024 float32 the whole
    # array is ~150 MB, well within budget, but chunked add is safer if a
    # caller later switches to a larger embedding set.
    chunk = 4096
    for start in range(0, arr.shape[0], chunk):
        end = min(start + chunk, arr.shape[0])
        index.add(arr[start:end])
        logger.info("FAISS add chunk [%d:%d] (ntotal=%d)", start, end, index.ntotal)
    logger.info("FAISS index built: ntotal=%d dim=%d", index.ntotal, embedder.dim)

    # 5. Persist index + metadata.
    faiss_path = out_dir / "faiss.index"
    meta_path = out_dir / "metadata.pkl"
    faiss.write_index(index, str(faiss_path))
    meta = [
        {
            "code": e.code,
            "name_cn": e.name_cn,
            "name_en": e.name_en,
            "chapter_no": e.chapter_no,
            "chapter_name": e.chapter_name,
            "chapter_range": e.chapter_range,
            "category_code": e.category_code,
            "clinical_category": e.clinical_category,
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
