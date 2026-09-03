"""Safety and deterministic Chinese fallback tests for persistent memory."""

from types import SimpleNamespace

from app.services import memory_expert


def test_known_unsafe_runtime_does_not_import_or_load_model(monkeypatch):
    monkeypatch.setattr(memory_expert, "_embedding_model", None)
    monkeypatch.setattr(memory_expert, "_embedding_runtime_reason", "not_assessed")
    monkeypatch.setattr(
        memory_expert,
        "assess_sentence_transformer_runtime_safety",
        lambda: SimpleNamespace(
            safe=False,
            reason="known_unsafe_windows_native_stack:test",
            torch_version="2.11.0",
            sentence_transformers_version="3.2.1",
        ),
    )

    assert memory_expert._get_embedding_model() is None
    assert memory_expert._embedding_model is False
    assert "known_unsafe_windows_native_stack" in memory_expert._embedding_runtime_reason


def test_chinese_bigram_fallback_recalls_unsegmented_clinical_text():
    score = memory_expert.lexical_similarity(
        "糖尿病控制",
        "患者2型糖尿病控制欠佳，近期空腹血糖升高",
    )

    assert score >= 0.75
    assert memory_expert.lexical_similarity("糖尿病", "左侧桡骨远端骨折") == 0


def test_cosine_similarity_rejects_dimension_mismatch():
    assert memory_expert._cosine_similarity([1.0, 0.0], [1.0]) == 0.0
