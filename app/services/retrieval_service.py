import pickle
from pathlib import Path
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from app.storage.faiss_store import FaissStore, SearchResult
from app.services.embedding import EmbeddingService
from app.utils.logger import get_logger

logger = get_logger(__name__)

RRF_K = 60


@dataclass
class RetrievalResult:
    chunk_id: int
    source_file: str
    chunk_index: int
    content: str
    score: float


class HybridRetriever:
    def __init__(
        self,
        faiss_store: FaissStore,
        embedding: EmbeddingService,
        bm25_index_path: str = "data/bm25_index.pkl",
        enabled: bool = True,
    ):
        self._faiss = faiss_store
        self._embedding = embedding
        self._bm25_path = Path(bm25_index_path)
        self._enabled = enabled
        self._bm25: BM25Okapi | None = None
        self._bm25_docs: list[dict] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def bm25_loaded(self) -> bool:
        return self._bm25 is not None

    def load_bm25(self):
        if self._bm25 is not None:
            return
        if not self._bm25_path.exists():
            logger.warning(f"BM25 index not found at {self._bm25_path}")
            return
        with open(self._bm25_path, "rb") as f:
            data = pickle.load(f)
        self._bm25 = data["bm25"]
        self._bm25_docs = data["documents"]
        logger.info(f"BM25 index loaded: {len(self._bm25_docs)} documents")

    def save_bm25(self, documents: list[dict]):
        tokenized = [self._tokenize(doc["content"]) for doc in documents]
        self._bm25 = BM25Okapi(tokenized)
        self._bm25_docs = documents
        self._bm25_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._bm25_path, "wb") as f:
            pickle.dump({"bm25": self._bm25, "documents": documents}, f)
        logger.info(f"BM25 index saved: {len(documents)} documents to {self._bm25_path}")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().split()

    async def _dense_search(self, query: str, top_k: int) -> list[SearchResult]:
        query_vector = await self._embedding.encode([query])
        if query_vector.size == 0:
            return []
        return self._faiss.search(query_vector[0], top_k)

    def _sparse_search(self, query: str, top_k: int) -> list[RetrievalResult]:
        if self._bm25 is None:
            return []
        tokenized = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized)
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            doc = self._bm25_docs[idx]
            results.append(RetrievalResult(
                chunk_id=doc.get("_id", idx),
                source_file=doc.get("source_file", ""),
                chunk_index=doc.get("chunk_index", 0),
                content=doc["content"],
                score=float(scores[idx]),
            ))
        return results

    def _rrf_merge(
        self, dense_results: list, sparse_results: list, top_k: int
    ) -> list[RetrievalResult]:
        """RRF 融合：给每个文档计算 RRF 分数，取 top_k。"""
        scores: dict[int, float] = {}
        doc_map: dict[int, RetrievalResult] = {}

        for rank, r in enumerate(dense_results):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (RRF_K + rank)
            doc_map[r.chunk_id] = RetrievalResult(
                chunk_id=r.chunk_id, source_file=r.source_file,
                chunk_index=r.chunk_index, content=r.content,
                score=0.0,
            )

        for rank, r in enumerate(sparse_results):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (RRF_K + rank)
            if r.chunk_id not in doc_map:
                doc_map[r.chunk_id] = RetrievalResult(
                    chunk_id=r.chunk_id, source_file=r.source_file,
                    chunk_index=r.chunk_index, content=r.content,
                    score=0.0,
                )

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        results = []
        for cid in sorted_ids[:top_k]:
            result = doc_map[cid]
            result.score = scores[cid]
            results.append(result)
        return results

    async def retrieve(self, query: str, top_k: int = 20) -> list[RetrievalResult]:
        if not self._enabled:
            dense = await self._dense_search(query, top_k)
            return [
                RetrievalResult(
                    chunk_id=r.chunk_id, source_file=r.source_file,
                    chunk_index=r.chunk_index, content=r.content,
                    score=r.score,
                )
                for r in dense
            ]

        dense_results = await self._dense_search(query, top_k)
        sparse_results = self._sparse_search(query, top_k)

        if not sparse_results:
            return [
                RetrievalResult(
                    chunk_id=r.chunk_id, source_file=r.source_file,
                    chunk_index=r.chunk_index, content=r.content,
                    score=r.score,
                )
                for r in dense_results
            ]

        return self._rrf_merge(dense_results, sparse_results, top_k)