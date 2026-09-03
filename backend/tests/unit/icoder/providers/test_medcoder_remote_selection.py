from __future__ import annotations

import sys

from icoder_runtime.providers.medical_coding.medcoder_strategy import MedCodERStrategy
from icoder_runtime.providers.medical_coding.remote_retriever import (
    RemoteMedCodERRetriever,
)


TOKEN = "test-medcoder-service-token-32-characters"


def _configure_remote(monkeypatch) -> None:
    monkeypatch.setenv("MEDCODER_RETRIEVER_URL", "https://medcoder.internal")
    monkeypatch.setenv("MEDCODER_RETRIEVER_TOKEN", TOKEN)
    monkeypatch.delenv("MEDCODER_RETRIEVER_ALLOW_HTTP", raising=False)


def test_default_diagnosis_retriever_prefers_remote_without_native_imports(
    monkeypatch,
) -> None:
    _configure_remote(monkeypatch)
    native_import_state = {
        name: name in sys.modules for name in ("torch", "faiss")
    }

    retriever = MedCodERStrategy()._create_default_retriever()

    assert isinstance(retriever, RemoteMedCodERRetriever)
    assert retriever.code_system == "ICD-10-CN"
    assert {
        name: name in sys.modules for name in native_import_state
    } == native_import_state


def test_default_procedure_retriever_uses_remote_code_system(monkeypatch) -> None:
    _configure_remote(monkeypatch)

    retriever = MedCodERStrategy()._create_default_procedure_retriever()

    assert isinstance(retriever, RemoteMedCodERRetriever)
    assert retriever.code_system == "ICD-9-CM-3-CN"


def test_invalid_remote_configuration_fails_closed(monkeypatch) -> None:
    _configure_remote(monkeypatch)
    monkeypatch.setenv("MEDCODER_RETRIEVER_TOKEN", "weak")

    assert MedCodERStrategy()._create_default_retriever() is None
