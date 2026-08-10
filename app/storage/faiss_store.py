from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np


@dataclass
class SearchResult:
    chunk_id: int
    source_file: str
    chunk_index: int
    content: str
    score: float


class FaissStore:
    def __init__(self, dimension: int = 1024):
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)
        self._metadata: list[dict] = []
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return self.index.ntotal

    def add_vectors(self, vectors: np.ndarray, metadata: list[dict]) -> None:
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        faiss.normalize_L2(vectors)
        start_id = len(self._metadata)
        for i, meta in enumerate(metadata):
            meta_copy = meta.copy()
            meta_copy["_id"] = start_id + i
            self._metadata.append(meta_copy)
        self.index.add(vectors)

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        if self.index.ntotal == 0:
            return []
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
        import json
        meta_file = path / "metadata.json"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)

    def reset(self) -> None:
        self.index = faiss.IndexFlatIP(self.dimension)
        self._metadata = []

    def is_loaded(self) -> bool:
        return self.index.ntotal > 0