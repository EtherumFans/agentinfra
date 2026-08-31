"""Native-free MedCodER worker fixture served by a real Uvicorn process."""
from __future__ import annotations

import os
import sys

from ml_worker.retrieval_app import create_app


if any(
    name == package or name.startswith(f"{package}.")
    for package in ("torch", "faiss", "sentence_transformers", "pyarrow")
    for name in sys.modules
):
    raise RuntimeError("native ML module imported into contract fixture")


class _FixtureRetriever:
    def __init__(self, code: str, name: str, chapter: str) -> None:
        self.code = code
        self.name = name
        self.chapter = chapter

    def ensure_loaded(self) -> None:
        return None

    def retrieve_sync(
        self,
        query: str,
        top_k: int | None = None,
        expand_synonyms: bool = True,
    ) -> list[dict]:
        del query, expand_synonyms
        return [{
            "code": self.code,
            "name": self.name,
            "score": 0.97,
            "chapter": self.chapter,
        }][:(top_k or 1)]


app = create_app(
    diagnosis_retriever=_FixtureRetriever("I50.900", "心力衰竭", "循环系统"),
    procedure_retriever=_FixtureRetriever("51.2300", "腹腔镜胆囊切除术", "消化系统手术"),
    service_token=os.environ.get("MEDCODER_RETRIEVER_TOKEN", ""),
    warmup=True,
    index_version="contract-fixture-2026-08",
)
