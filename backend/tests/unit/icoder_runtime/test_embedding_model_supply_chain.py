from __future__ import annotations

import sys
from types import SimpleNamespace

from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
    BGEEmbedder,
    MODEL_REVISION,
)


def test_embedder_forwards_pinned_revision_and_offline_policy(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, object] = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name_or_path, **kwargs):
            captured["model_name_or_path"] = model_name_or_path
            captured.update(kwargs)

        def get_sentence_embedding_dimension(self):
            return 1024

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )
    monkeypatch.setenv("MEDCODER_BGE_LOCAL_FILES_ONLY", "1")
    monkeypatch.delenv("MEDCODER_BGE_REVISION", raising=False)

    embedder = BGEEmbedder(
        model_dir=str(tmp_path / "model-cache"),
        torch_dtype="float32",
    )
    embedder._load()

    assert captured["model_name_or_path"] == "BAAI/bge-m3"
    assert captured["revision"] == MODEL_REVISION
    assert captured["local_files_only"] is True
    assert captured["cache_folder"] == str(tmp_path / "model-cache")


def test_explicit_revision_override_is_supported(monkeypatch, tmp_path) -> None:
    captured: dict[str, object] = {}

    class FakeSentenceTransformer:
        def __init__(self, model_name_or_path, **kwargs):
            captured.update(kwargs)

        def get_sentence_embedding_dimension(self):
            return 1024

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeSentenceTransformer),
    )

    embedder = BGEEmbedder(
        model_revision="test-revision",
        model_dir=str(tmp_path / "model-cache"),
        torch_dtype="float32",
    )
    embedder._load()

    assert captured["revision"] == "test-revision"
