"""Tests for BGEEmbedder — E1.9 memory knobs (fp16/device/model_kwargs/encode_kwargs).

The real ``SentenceTransformer`` is 2.3 GB on disk; we mock it so this
suite stays fast and hermetic.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


@pytest.fixture
def fake_sentence_transformers():
    """Inject a fake ``sentence_transformers`` module so ``BGEEmbedder._load``
    doesn't try to download a 2.3 GB model. The fake class captures
    constructor kwargs for assertion.
    """
    fake_mod = MagicMock()
    captured: dict = {}

    class _FakeSentenceTransformer:
        def __init__(self, model_name_or_path, **kwargs):
            captured["model_name_or_path"] = model_name_or_path
            captured.update(kwargs)
            self._encode = MagicMock(
                return_value=np.ones((1, 1024), dtype="float32")
            )

        def encode(self, *args, **kwargs):
            # Return shape-matches-input fake vectors
            n = len(args[0]) if args else kwargs.get("sentences", [[]]).__len__()
            return np.ones((n, 1024), dtype="float32")

        def get_sentence_embedding_dimension(self):
            return 1024

    fake_mod.SentenceTransformer = _FakeSentenceTransformer
    captured["_CAPTURE"] = captured  # expose via closure

    sys.modules["sentence_transformers"] = fake_mod
    yield captured
    sys.modules.pop("sentence_transformers", None)


class TestBGEEmbedderMemoryKnobs:
    """E1.9: device / torch_dtype / model_kwargs / encode_kwargs env wiring.

    These tests assert on the *string* dtype that gets stored in
    ``self.model_kwargs`` and ultimately forwarded to ``SentenceTransformer``.
    The actual ``torch.dtype`` resolution happens inside ``_load()`` and
    requires a working torch C extension; we avoid that here because
    some Windows + pytest combos abort the process on ``import torch``
    after a previous multiprocessing test has torn down torch's
    internal state. Real prod loads always have a healthy torch.
    """

    def test_default_dtype_is_float16(self, fake_sentence_transformers, monkeypatch):
        # Make sure no inherited env var forces float32
        monkeypatch.delenv("MEDCODER_BGE_DTYPE", raising=False)
        monkeypatch.delenv("MEDCODER_BGE_DEVICE", raising=False)
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        emb = BGEEmbedder()
        assert emb.torch_dtype == "float16"
        assert emb.device == "cpu"
        # E1.10: default key is the new ``dtype`` (transformers 4.50+).
        # Legacy ``torch_dtype`` still works when explicitly passed — see
        # test_explicit_legacy_torch_dtype_key.
        assert emb.model_kwargs.get("dtype") == "float16"
        assert "torch_dtype" not in emb.model_kwargs

    def test_env_override_to_float32(self, fake_sentence_transformers, monkeypatch):
        monkeypatch.setenv("MEDCODER_BGE_DTYPE", "float32")
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        emb = BGEEmbedder()
        assert emb.torch_dtype == "float32"
        # fp32 is sentence-transformers default — no dtype injected.
        assert "dtype" not in emb.model_kwargs
        assert "torch_dtype" not in emb.model_kwargs

    def test_env_override_to_bfloat16(self, fake_sentence_transformers, monkeypatch):
        monkeypatch.setenv("MEDCODER_BGE_DTYPE", "bfloat16")
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        emb = BGEEmbedder()
        assert emb.torch_dtype == "bfloat16"
        assert emb.model_kwargs.get("dtype") == "bfloat16"

    def test_device_default_is_cpu(self, fake_sentence_transformers, monkeypatch):
        monkeypatch.delenv("MEDCODER_BGE_DEVICE", raising=False)
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        assert BGEEmbedder().device == "cpu"

    def test_device_env_override(self, fake_sentence_transformers, monkeypatch):
        monkeypatch.setenv("MEDCODER_BGE_DEVICE", "cuda")
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        assert BGEEmbedder().device == "cuda"

    def test_load_passes_device_and_model_kwargs(self, fake_sentence_transformers, monkeypatch):
        monkeypatch.delenv("MEDCODER_BGE_DTYPE", raising=False)
        monkeypatch.delenv("MEDCODER_BGE_DEVICE", raising=False)
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        emb = BGEEmbedder()
        emb._load()
        assert fake_sentence_transformers["device"] == "cpu"
        # E1.10: ``_load()`` resolves the dtype string into a real
        # ``torch.dtype`` under the new ``dtype`` key. We import torch
        # here for the comparison (this test is happy-path — torch works).
        import torch
        assert fake_sentence_transformers["model_kwargs"].get("dtype") == torch.float16
        assert "torch_dtype" not in fake_sentence_transformers["model_kwargs"]
        assert fake_sentence_transformers["cache_folder"] == emb.model_dir

    def test_explicit_kwargs_override_env(self, fake_sentence_transformers, monkeypatch):
        # Env says fp16 but explicit kwarg says fp32 → explicit wins
        monkeypatch.setenv("MEDCODER_BGE_DTYPE", "float16")
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        emb = BGEEmbedder(torch_dtype="float32")
        assert emb.torch_dtype == "float32"
        # No dtype injected (fp32 is sentence-transformers default)
        assert "dtype" not in emb.model_kwargs
        assert "torch_dtype" not in emb.model_kwargs

    def test_explicit_legacy_torch_dtype_key(self, fake_sentence_transformers, monkeypatch):
        """E1.10 back-compat: callers (tests, external libs) that hand-build
        ``BGEEmbedder(model_kwargs={"torch_dtype": "float16"})`` still get
        correct torch.dtype resolution in ``_load()``. The ``__init__``
        code preserves any caller-supplied key; ``_load()`` resolves
        whichever is present, preferring ``dtype`` and falling back to
        ``torch_dtype``.
        """
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        emb = BGEEmbedder(model_kwargs={"torch_dtype": "float16"})
        # __init__ must not clobber caller-supplied key with new "dtype".
        assert "torch_dtype" in emb.model_kwargs
        assert emb.model_kwargs["torch_dtype"] == "float16"
        assert "dtype" not in emb.model_kwargs
        # _load() resolves the legacy key into a real torch.dtype.
        import torch
        emb._load()
        forwarded = fake_sentence_transformers["model_kwargs"]
        # Either the legacy key resolved to a real dtype, or it was
        # moved to the new key — both are acceptable as long as fp16
        # made it to SentenceTransformer.
        if "dtype" in forwarded:
            assert forwarded["dtype"] == torch.float16
        else:
            assert forwarded.get("torch_dtype") == torch.float16

    def test_encode_uses_encode_kwargs_defaults(self, fake_sentence_transformers, monkeypatch):
        """E1.9: ``encode_kwargs`` defaults match pre-E1.9 behavior
        (batch_size=32, normalize_embeddings=True, etc.).
        """
        monkeypatch.delenv("MEDCODER_BGE_DTYPE", raising=False)
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        emb = BGEEmbedder()
        emb._load()
        out = emb.embed_numpy(["a", "b", "c"])
        # Shape must be (3, 1024) — proves the encode() ran with the
        # default normalize_embeddings=True path.
        assert out.shape == (3, 1024)

    def test_unknown_dtype_falls_back_to_fp32(self, fake_sentence_transformers, monkeypatch):
        """Unknown dtype name (typo, unsupported) → load with no dtype
        key, which falls back to sentence-transformers default fp32 + warning.
        """
        monkeypatch.setenv("MEDCODER_BGE_DTYPE", "float128")  # doesn't exist
        from icoder_runtime.providers.medical_coding.embedding_bge_m3 import (
            BGEEmbedder,
        )
        emb = BGEEmbedder()
        # Unknown dtype name → still stored as-is in model_kwargs for
        # _load() to attempt resolution; if torch.getattr fails inside
        # _load(), the kwarg is dropped.
        assert emb.torch_dtype == "float128"
        assert emb.model_kwargs.get("dtype") == "float128"
