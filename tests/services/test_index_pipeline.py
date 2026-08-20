import asyncio
from unittest.mock import AsyncMock
from app.services.index_pipeline import IndexPipeline


def make_pipeline():
    chunker = type("C", (), {"split_text": lambda self, t, source_file: [
        {"content": t, "source_file": source_file, "chunk_index": 0,
         "headings": [], "parent_id": None, "content_hash": "h"}]})()
    embedding = type("E", (), {"encode": AsyncMock(return_value=[[0.1] * 8])})()
    store = type("V", (), {
        "size": 0,
        "aadd_vectors": AsyncMock(),
        "save": lambda self, *a, **k: None,
        "is_loaded": lambda: False})()
    return IndexPipeline(chunker=chunker, embedding=embedding,
                         vector_store=store, sparse=None,
                         state_path=":memory:", concurrent_batches=2)


def test_ingest_returns_report():
    p = make_pipeline()
    async def go():
        rep = await p.ingest_documents(
            [("a.md", "Java HashMap 结构"), ("b.md", "Redis 持久化")], rebuild=True)
        return rep
    rep = asyncio.run(go())
    assert rep["status"] == "success"
    assert rep["files_processed"] == 2
    assert rep["total_chunks"] >= 2
    assert rep["failed_docs"] == []
    assert rep["progress"]["processed"] == 2
    assert rep["progress"]["total"] == 2


def test_ingest_idempotent_skips_done_doc():
    """同一文本已入库(done)后再次 ingest 应幂等跳过。"""
    class C:
        def split_text(self, t, source_file):
            return [{"content": t, "source_file": source_file, "chunk_index": 0,
                     "headings": [], "parent_id": None, "content_hash": "h"}]
    embedding = type("E", (), {"encode": AsyncMock(return_value=[[0.1] * 8])})()
    store = type("V", (), {
        "size": 0,
        "aadd_vectors": AsyncMock(),
        "save": lambda self, *a, **k: None,
        "is_loaded": lambda: False})()
    p = IndexPipeline(chunker=C(), embedding=embedding,
                      vector_store=store, sparse=None,
                      state_path=":memory:", concurrent_batches=2)

    async def go():
        first = await p.ingest_documents([("a.md", "相同内容")], rebuild=False)
        second = await p.ingest_documents([("a.md", "相同内容")], rebuild=False)
        return first, second

    first, second = asyncio.run(go())
    assert first["files_processed"] == 1
    assert second["files_processed"] == 0, "已 done 的文档第二次应被幂等跳过"
    assert second["total_chunks"] == 0
    assert second["progress"]["total"] == 0