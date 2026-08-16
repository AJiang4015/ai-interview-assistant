import asyncio
from unittest.mock import AsyncMock, MagicMock

import numpy as np

from app.services.rag_service import RAGService
from app.storage.faiss_store import SearchResult


def _make_service(results):
    faiss = MagicMock()
    faiss.is_loaded.return_value = True
    faiss.search.return_value = results

    embedding = MagicMock()
    embedding.encode = AsyncMock(return_value=np.zeros((1, 4)))

    llm = MagicMock()
    llm.chat = AsyncMock(return_value="answer")

    return RAGService(
        faiss_store=faiss,
        embedding=embedding,
        llm=llm,
        session_store=None,
        search_store=None,
        query_rewriter=None,
        hybrid_retriever=None,
        reranker=None,
        cache_service=None,
    )


def test_query_empty_result_records_vector_empty(monkeypatch):
    recorded = []

    def spy(empty):
        recorded.append(empty)

    monkeypatch.setattr("app.services.monitor.record_vector_query", spy)
    service = _make_service(results=[])
    asyncio.run(service.query("hi"))
    assert recorded == [True]


def test_query_nonempty_result_records_vector_ok(monkeypatch):
    recorded = []
    result = SearchResult(
        chunk_id=0, source_file="a.md", chunk_index=0,
        content="context", score=0.9,
    )

    def spy(empty):
        recorded.append(empty)

    monkeypatch.setattr("app.services.monitor.record_vector_query", spy)
    service = _make_service(results=[result])
    resp = asyncio.run(service.query("hi"))
    assert resp.answer == "answer"
    assert recorded == [False]