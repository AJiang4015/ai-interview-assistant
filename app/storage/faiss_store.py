from __future__ import annotations

import asyncio
import contextlib
import time
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np

from app.observability import tracer, trace
from app.config import settings


INDEX_FLAT = "flat"
INDEX_HNSW = "hnsw"
INDEX_IVF = "ivf"


def _build_index(index_type: str, dim: int):
    if index_type == INDEX_HNSW:
        idx = faiss.IndexHNSWFlat(dim, settings.hnsw_m)
        idx.hnsw.efConstruction = settings.hnsw_ef_construction
        idx.hnsw.efSearch = settings.hnsw_ef_search
        return idx
    return faiss.IndexFlatIP(dim)


@dataclass
class SearchResult:
    chunk_id: int
    source_file: str
    chunk_index: int
    content: str
    score: float


class FaissStore:
    def __init__(self, dimension: int = 0, index_type: str | None = None):
        self.dimension = dimension
        self._index_type = index_type or settings.vector_index_type
        self.index = _build_index(self._index_type, dimension) if dimension > 0 else None
        self._metadata: list[dict] = []
        self._rwlock = _AsyncRWLock()

    @property
    def size(self) -> int:
        return self.index.ntotal if self.index else 0

    def _ensure_index(self, dim: int) -> None:
        if self.index is None or self.dimension != dim:
            self.dimension = dim
            self.index = _build_index(self._index_type, dim)

    def add_vectors(self, vectors: np.ndarray, metadata: list[dict]) -> None:
        self._add_vectors_sync(vectors, metadata)

    def _add_vectors_sync(self, vectors: np.ndarray, metadata: list[dict]) -> None:
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        dim = vectors.shape[1]
        self._ensure_index(dim)
        faiss.normalize_L2(vectors)
        start_id = len(self._metadata)
        for i, meta in enumerate(metadata):
            meta_copy = meta.copy()
            meta_copy["_id"] = start_id + i
            self._metadata.append(meta_copy)
        self.index.add(vectors)

    async def aadd_vectors(self, vectors: np.ndarray, metadata: list[dict]) -> None:
        """线程池写入，写独占，供入库管道使用。"""
        async with self._rwlock.write():
            await asyncio.to_thread(self._add_vectors_sync, vectors, metadata)

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        if self.index is None or self.index.ntotal == 0:
            return []
        if tracer is None or trace is None:
            return self._search_inner(query_vector, top_k)
        with tracer.start_as_current_span("vector.store", kind=trace.SpanKind.CLIENT) as span:
            span.set_attribute("db.system", "faiss")
            start = time.perf_counter()
            results = self._search_inner(query_vector, top_k)
            span.set_attribute("vector.exec_ms", (time.perf_counter() - start) * 1000)
            span.set_attribute("vector.recall_count", len(results))
            return results

    async def asearch(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        """线程池执行检索，多读者共享、不被写者打断，供并发/阻塞敏感路径调用。"""
        if self.index is None or self.index.ntotal == 0:
            return []
        if tracer is None or trace is None:
            async with self._rwlock.read():
                return await asyncio.to_thread(self._search_inner, query_vector, top_k)
        with tracer.start_as_current_span("vector.store", kind=trace.SpanKind.CLIENT) as span:
            span.set_attribute("db.system", "faiss")
            start = time.perf_counter()
            async with self._rwlock.read():
                results = await asyncio.to_thread(self._search_inner, query_vector, top_k)
            span.set_attribute("vector.exec_ms", (time.perf_counter() - start) * 1000)
            span.set_attribute("vector.recall_count", len(results))
            return results

    def _search_inner(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        qv = query_vector.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(qv)
        k = min(top_k, self.index.ntotal)
        scores, ids = self.index.search(qv, k)
        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            meta = self._metadata[idx]
            results.append(SearchResult(
                chunk_id=meta["_id"],
                source_file=meta["source_file"],
                chunk_index=meta["chunk_index"],
                content=meta["content"],
                score=float(score)
            ))
        return results

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if self.index and self.index.ntotal > 0:
            faiss.write_index(self.index, str(path / "index.faiss"))
        import json
        with open(path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2)

    def load(self, path: str | Path) -> None:
        path = Path(path)
        index_file = path / "index.faiss"
        if not index_file.exists():
            return
        self.index = faiss.read_index(str(index_file))
        self.dimension = self.index.d
        import json
        meta_file = path / "metadata.json"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)

    def reset(self) -> None:
        self.index = None
        self.dimension = 0
        self._metadata = []

    def get_all_metadata(self) -> list[dict]:
        """返回全部向量元数据，用于同步重建 BM25 索引。"""
        return self._metadata

    def is_loaded(self) -> bool:
        return self.index is not None and self.index.ntotal > 0


class _AsyncRWLock:
    """协程读写锁：多读者共享、写独占（写与读互斥，读者互不阻塞）。"""
    def __init__(self):
        self._write = asyncio.Lock()
        self._readers = 0
        self._guard = asyncio.Lock()

    @contextlib.asynccontextmanager
    async def read(self):
        async with self._guard:
            self._readers += 1
            if self._readers == 1:
                await self._write.acquire()
        try:
            yield
        finally:
            async with self._guard:
                self._readers -= 1
                if self._readers == 0:
                    self._write.release()

    @contextlib.asynccontextmanager
    async def write(self):
        async with self._write:
            yield

    async def acquire_read(self):
        return self.read()

    async def acquire_write(self):
        return self.write()
