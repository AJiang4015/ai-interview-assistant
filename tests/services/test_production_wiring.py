"""Task 10 生产接线回归测试。

覆盖：
a) HybridRetriever 注入 sparse 时 _sparse_search 走 sparse 而非内部 BM25；
b) IndexService.build_index/add_document 内部用 aadd_vectors（带读/写锁），而非裸 add_vectors；
c) build_index 返回的 BuildIndexResponse 序列化后不含 chunks 键。
"""
import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from app.config import settings
from app.services.index_service import IndexService
from app.services.retrieval_service import HybridRetriever, RetrievalResult


# ---------- (a) HybridRetriever 稀疏腿接线 ----------

def test_sparse_search_uses_injected_sparse():
    class FakeSparse:
        def __init__(self, results):
            self._results = results
            self.calls = 0
        def search(self, query, top_k):
            self.calls += 1
            return self._results
        _docs = []

    fake = FakeSparse([
        RetrievalResult(chunk_id=3, source_file="f.md", chunk_index=3,
                        content="sparse hit", score=8.0),
    ])
    retriever = HybridRetriever(faiss_store=object(), embedding=None,
                                enabled=True, sparse=fake)
    out = retriever._sparse_search("java hashmap", 20)
    assert fake.calls == 1
    assert out == fake._results


def test_sparse_search_falls_back_to_bm25_when_no_sparse(tmp_path):
    bm25_path = tmp_path / "bm25.pkl"
    retriever = HybridRetriever(faiss_store=object(), embedding=None,
                                enabled=True, sparse=None,
                                bm25_index_path=str(bm25_path))
    # 无 sparse 时回退到 BM25：在若干文档上检索应命中 vocabulary 里的词
    retriever.save_bm25([
        {"_id": 0, "content": "hashmap resize linked list bucket collision", "source_file": "a.md", "chunk_index": 0},
        {"_id": 1, "content": "concurrenthashmap synchronized node locking", "source_file": "a.md", "chunk_index": 1},
        {"_id": 2, "content": "totally unrelated unrelated filler text", "source_file": "a.md", "chunk_index": 2},
    ])
    # query 词 "hashmap" 只出现在 id=0，应命中
    out = retriever._sparse_search("hashmap bucket", 5)
    assert isinstance(out, list)
    assert {r.chunk_id for r in out} == {0}


# ---------- (b) + (c) IndexService 生产写路径 ----------

def _make_index_service_with_faiss(sparse=None, hybrid=None):
    faiss = type("F", (), {
        "aadd_vectors": AsyncMock(),
        "add_vectors": Mock(),
        "save": Mock(),
        "reset": Mock(),
        "is_loaded": Mock(return_value=False),
        "get_all_metadata": Mock(return_value=[]),
    })()
    doc_store = type("D", (), {
        "save": Mock(),
        "append": Mock(),
        "get_status": Mock(return_value={
            "index_exists": False, "total_chunks": 0,
            "last_build_time": None, "knowledge_base_files": [],
        }),
    })()
    embedding = type("E", (), {"encode": AsyncMock(return_value=[[0.1] * 8])})()
    return IndexService(faiss_store=faiss, doc_store=doc_store,
                        embedding=embedding, hybrid_retriever=hybrid,
                        sparse=sparse), faiss, doc_store


def _long_text():
    return ("# 数据结构\n"
            "Java HashMap 基于数组加链表（以及红黑树）实现，默认负载因子 0.75，"
            "tableSizeFor 保证容量为 2 的幂，插入与查找平均 O(1)。" * 8)


def test_build_index_uses_aadd_vectors_and_returns_no_chunks(monkeypatch):
    svc, faiss, _ = _make_index_service_with_faiss()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "kb.md"
        p.write_text(_long_text(), encoding="utf-8")
        svc.splitter.scan_md_files = lambda _: [p]
        monkeypatch.setattr(settings, "ingest_state_path", str(Path(d) / "state.json"))

        resp = asyncio.run(svc.build_index(rebuild=True))

    assert faiss.aadd_vectors.called
    assert not faiss.add_vectors.called
    assert resp.total_chunks >= 1
    # 序列化后不得包含 chunks 字段
    payload = resp.model_dump()
    assert "chunks" not in payload


def test_add_document_uses_aadd_vectors_and_no_chunks(monkeypatch):
    svc, faiss, doc_store = _make_index_service_with_faiss()
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "up.md"
        p.write_text(_long_text(), encoding="utf-8")
        monkeypatch.setattr(settings, "ingest_state_path", str(Path(d) / "state.json"))

        resp = asyncio.run(svc.add_document(p))

    assert faiss.aadd_vectors.called
    assert not faiss.add_vectors.called
    assert doc_store.append.called
    assert resp.total_chunks >= 1
    assert "chunks" not in resp.model_dump()


def test_build_index_feeds_sparse_when_provided(monkeypatch):
    sparse = type("S", (), {"add_documents": Mock()})()
    svc, faiss, _ = _make_index_service_with_faiss(sparse=sparse)
    # 让 get_all_metadata 返回带全局 _id 的元数据，验证喂给 sparse 用真实 id
    faiss.get_all_metadata.return_value = [
        {"_id": 0, "content": "c0", "source_file": "a.md", "chunk_index": 0},
        {"_id": 1, "content": "c1", "source_file": "a.md", "chunk_index": 1},
    ]
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sb.md"
        p.write_text(_long_text(), encoding="utf-8")
        svc.splitter.scan_md_files = lambda _: [p]
        monkeypatch.setattr(settings, "ingest_state_path", str(Path(d) / "state.json"))

        asyncio.run(svc.build_index(rebuild=True))

    assert sparse.add_documents.called
    fed = sparse.add_documents.call_args.args[0]
    assert fed, "sparse 应收到基于 faiss 元数据的文档"