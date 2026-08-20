import asyncio
import threading
import time

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
    # 验证 search 在线程池执行、互不阻塞：三条 asearch 应运行在不同线程
    store = FaissStore(dimension=8, index_type=INDEX_HNSW)
    rng = np.random.default_rng(1)
    vecs = rng.normal(size=(500, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    store.add_vectors(vecs, [{"source_file": "f", "chunk_index": i, "content": "c"}
                             for i in range(500)])

    threads = set()
    original_search_inner = store._search_inner

    def wrapped(*args, **kwargs):
        threads.add(threading.current_thread().name)
        # 短暂占住当前 worker，确保三条 asearch 同时在线程池中，取不同线程
        time.sleep(0.05)
        return original_search_inner(*args, **kwargs)

    store._search_inner = wrapped

    async def run():
        results = await asyncio.gather(
            store.asearch(vecs[0], 5),
            store.asearch(vecs[1], 5),
            store.asearch(vecs[2], 5),
        )
        return results

    results = asyncio.run(run())
    assert all(len(r) == 5 for r in results)
    # 3 条 asearch 必须跑在不同线程，证明确实走线程池并发而非串行
    assert len(threads) == 3, f"expected 3 threads, got {len(threads)}: {threads}"


def test_auto_ensure_index_uses_hnsw():
    # I-1: 空构造/自动建索引时应走 factory，按 index_type 建出 HNSW 索引
    store = FaissStore(dimension=0, index_type=INDEX_HNSW)
    rng = np.random.default_rng(3)
    vecs = rng.normal(size=(64, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    meta = [{"source_file": "f", "chunk_index": i, "content": "c"} for i in range(64)]
    store.add_vectors(vecs, meta)
    assert store.index.__class__.__name__ == "IndexHNSWFlat"
    assert store.size == 64

    # 异步路径也应建出 HNSW
    async def run():
        async_store = FaissStore(dimension=8, index_type=INDEX_HNSW)
        await async_store.aadd_vectors(
            vecs, [{"source_file": "f", "chunk_index": i, "content": "c"} for i in range(64)]
        )
        return async_store

    async_store = asyncio.run(run())
    assert async_store.index.__class__.__name__ == "IndexHNSWFlat"


def test_rwlock_read_write_contexts():
    # I-2: 读写锁可作为上下文管理器正常进入/退出，读可多读者共享、写独占
    store = FaissStore(dimension=8, index_type=INDEX_FLAT)
    store.add_vectors(np.ones((4, 8), dtype=np.float32),
                      [{"source_file": "a", "chunk_index": i, "content": "x"} for i in range(4)])

    async def run():
        async with store._rwlock.read():
            async with store._rwlock.read():  # 多读者共享，第二个读者不被阻塞
                pass
        async with store._rwlock.write():
            pass
        return True

    assert asyncio.run(run()) is True