import numpy as np
from app.storage.faiss_store import FaissStore, INDEX_FLAT, INDEX_HNSW
from app.services.sparse_retriever import SparseRetriever


def test_flat_vs_hnsw_topk_overlap():
    # 召回一致性：同一查询 flat 与 hnsw 的 top-k 重合度高
    rng = np.random.default_rng(7)
    vecs = rng.normal(size=(1000, 16)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    meta = [{"source_file": "f.md", "chunk_index": i, "content": f"c{i}"}
            for i in range(1000)]
    flat = FaissStore(dimension=16, index_type=INDEX_FLAT)
    hnsw = FaissStore(dimension=16, index_type=INDEX_HNSW)
    flat.add_vectors(vecs, meta)
    hnsw.add_vectors(vecs, meta)
    fh = {r.chunk_id for r in flat.search(vecs[0], 20)}
    hh = {r.chunk_id for r in hnsw.search(vecs[0], 20)}
    assert len(fh & hh) >= 15


def test_sparse_degradation_never_raises():
    sr = SparseRetriever(backend="memory")
    assert sr.search("foo", 3) == []


def test_sparse_memory_roundtrip():
    sr = SparseRetriever(backend="memory")
    # 含英文独立 token "HashMap" 的文档需要命中；再添加若干不含该词的干扰文档，
    # 使该词 idf>0。BM25 对 df 过大（df>=N/2 时 idf<=0）的词得分为非正，
    # 会被内存后端过滤掉，故需保证 "HashMap" 仅出现在少数文档中。
    sr.add_documents([
        {"_id": 0, "content": "哈希表 HashMap 扩容", "source_file": "a", "chunk_index": 0},
        {"_id": 1, "content": "今天天气不错 适合散步", "source_file": "b", "chunk_index": 1},
        {"_id": 2, "content": "量子计算 又是一门新学问", "source_file": "c", "chunk_index": 2},
    ])
    hits = sr.search("HashMap", 5)
    assert hits and hits[0].chunk_id == 0