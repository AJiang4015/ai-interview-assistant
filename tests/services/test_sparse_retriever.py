from app.services.sparse_retriever import SparseRetriever


def test_memory_backend_search_returns_docs():
    sr = SparseRetriever(backend="memory")
    docs = [
        {"_id": 0, "content": "HashMap 键值对", "source_file": "a.md", "chunk_index": 0},
        {"_id": 1, "content": "ConcurrentHashMap 线程安全", "source_file": "a.md", "chunk_index": 1},
        {"_id": 2, "content": "Redis 缓存淘汰策略 LRU LFU", "source_file": "b.md", "chunk_index": 0},
    ]
    sr.add_documents(docs)
    hits = sr.search("HashMap", top_k=5)
    assert any(h.chunk_id == 0 for h in hits)


def test_unknown_backend_degrades_to_memory():
    sr = SparseRetriever(backend="nose_existent")
    hits = sr.search("anything", top_k=5)
    assert hits == []