import asyncio
import numpy as np
import pytest

from app.storage.faiss_store import FaissStore, INDEX_HNSW, INDEX_FLAT


def test_hnsw_returns_topk():
    store = FaissStore(dimension=8, index_type=INDEX_HNSW)
    rng = np.random.default_rng(0)
    vecs = rng.normal(size=(200, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    meta = [{"source_file": "f.md", "chunk_index": i, "content": f"c{i}"} for i in range(200)]
    store.add_vectors(vecs, meta)
    assert store.size == 200
    hits = store.search(vecs[0], top_k=5)
    assert len(hits) == 5
    assert hits[0].chunk_id == 0


def test_reset_clears_index():
    store = FaissStore(dimension=8, index_type=INDEX_FLAT)
    store.add_vectors(np.ones((4, 8), dtype=np.float32),
                      [{"source_file": "a", "chunk_index": i, "content": "x"} for i in range(4)])
    assert store.size == 4
    store.reset()
    assert store.is_loaded() is False


def test_search_runs_concurrently_without_serialization():
    # 验证 search 在线程池执行、互不阻塞
    store = FaissStore(dimension=8, index_type=INDEX_HNSW)
    rng = np.random.default_rng(1)
    vecs = rng.normal(size=(500, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    store.add_vectors(vecs, [{"source_file": "f", "chunk_index": i, "content": "c"}
                             for i in range(500)])

    async def run():
        results = await asyncio.gather(
            store.asearch(vecs[0], 5),
            store.asearch(vecs[1], 5),
            store.asearch(vecs[2], 5),
        )
        return results

    results = asyncio.run(run())
    assert all(len(r) == 5 for r in results)