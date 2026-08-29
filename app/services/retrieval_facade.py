"""统一检索门面（Retrieval Facade）。

Part B（2026-08-28-interview-retrieval-upgrade-partB.md，S1）：
将「query rewrite → hybrid/faiss → rerank → parent expansion → dedup」这条
被 Spec A 消融验证过的管线封装为唯一入口，让问答（rag_service）与面试
（interview_service）共用同一条已验证的检索链路，管线下复用、管线上做策略差异。

设计约束（对应 Spec §5.1 / Spec A 决策）：
- 开关状态以 Spec A 消融结论为准（默认 qr_on + rr_on + hybrid + parent，可配 enable_*）。
- 任一环节失败必须优雅降级（DR-001），不抛出阻塞调用方（调用方按需对空结果降级）。
- 本 facade 自身不读写缓存（DR-004）；若调用方想用缓存，需在 facade 之外按业务语义处理，
  且 key 只允许用「不变量」（如原始问题），绝不允许混入用户回答等可变量。
- 保持与 rag_service 原有检索行为等价（top_k、dedup、parent 语义一致），SSE 事件结构不变（DR-005）。
"""

import json
from dataclasses import dataclass, field

from app.config import settings
from app.storage.faiss_store import FaissStore
from app.services.embedding import EmbeddingService
from app.services.retrieval_service import HybridRetriever
from app.utils.logger import get_logger

logger = get_logger(__name__)

# RRF 融合常数与混合检索的默认候选集规模（与现状链路一致，见 Spec A 基线）
_HYBRID_TOP_K = 20


@dataclass
class SourceInfo:
    """检索来源引用（文档名 + chunk 定位），用于溯源呈现。"""

    file: str
    chunk_index: int
    score: float


@dataclass
class FacadeResult:
    """facade 统一返回：检索到的候选块 + 结构化来源。"""

    chunks: list = field(default_factory=list)      # list[SearchResult]，父扩展+去重后的最终候选
    sources: list = field(default_factory=list)     # list[SourceInfo]

    @property
    def is_empty(self) -> bool:
        return not self.chunks

    def to_text(self) -> str:
        """把候选块拼成供 LLM 使用的上下文文本（与 rag_service 现行为等价）。"""
        if not self.chunks:
            return ""
        return "\n---\n".join([c.content for c in self.chunks])


class RetrievalFacade:
    """统一检索门面：封装完整检索管线，问答与面试共用。"""

    def __init__(
        self,
        faiss_store: FaissStore,
        embedding: EmbeddingService,
        query_rewriter=None,     # QueryRewriteService | None
        hybrid_retriever=None,   # HybridRetriever | None
        reranker=None,           # RerankService | None
    ):
        self._faiss = faiss_store
        self._embedding = embedding
        self._query_rewriter = query_rewriter
        self._hybrid = hybrid_retriever
        self._reranker = reranker
        self.top_k = settings.top_k

    async def rewrite(self, query: str) -> str:
        """查询改写（可关）；返回改写后的检索词。"""
        if self._query_rewriter and getattr(self._query_rewriter, "enabled", False):
            try:
                return await self._query_rewriter.rewrite(query)
            except Exception as e:
                logger.warning(f"Query rewrite failed, use original query: {e}")
        return query

    async def _retrieve_raw(self, retrieval_query: str, top_k: int) -> list:
        """混合检索（可回退 FAISS-only）。覆盖更广的候选集，供后续重排。"""
        if self._hybrid and getattr(self._hybrid, "enabled", False):
            return await self._hybrid.retrieve(retrieval_query, top_k=top_k)
        # 降级：recondense 到稠密腿
        query_vector = await self._embedding.encode([retrieval_query])
        if query_vector.size == 0:
            return []
        return await self._faiss.asearch(query_vector[0], top_k)

    async def _rerank(self, retrieval_query: str, raw_results: list, top_k: int) -> list:
        """重排（可关）；关闭时截断 top_k。"""
        if self._reranker and getattr(self._reranker, "enabled", False):
            docs = [r.content for r in raw_results]
            reranked = await self._reranker.rerank(retrieval_query, docs, top_k=top_k)
            content_to_result = {r.content: r for r in raw_results}
            final = []
            for rr in reranked:
                if rr.content in content_to_result:
                    final.append(content_to_result[rr.content])
            return final
        return raw_results[:top_k]

    def _apply_parent_expansion(self, results: list) -> list:
        """parent 上下文扩展（可关）。与 rag_service 原语义一致（无真实 parent 映射时零回归）。"""
        if not settings.enable_parent_expansion:
            return results
        chunks_by_id = {
            r.chunk_id: {"chunk_id": r.chunk_id, "content": r.content, "parent_id": None}
            for r in results
        }
        return HybridRetriever.expand_with_parents(
            results, chunks_by_id, top_k=len(results) or self.top_k
        )

    @staticmethod
    def _deduplicate_results(results: list) -> list:
        seen = set()
        out = []
        for r in results:
            if r.content not in seen:
                seen.add(r.content)
                out.append(r)
        return out

    async def retrieve(self, query: str, top_k: int | None = None) -> FacadeResult:
        """统一检索入口：qr → hybrid → rerank → parent → dedup。

        任一环节失败即降级返回空（或回退），不抛出——调用方按需对空结果处理。
        """
        top_k = top_k or self.top_k
        try:
            retrieval_query = await self.rewrite(query)
            raw = await self._retrieve_raw(retrieval_query, _HYBRID_TOP_K)
            reranked = await self._rerank(retrieval_query, raw, top_k=top_k)
            expanded = self._apply_parent_expansion(reranked)
            final = self._deduplicate_results(expanded)
            sources = [
                SourceInfo(file=r.source_file, chunk_index=r.chunk_index, score=r.score)
                for r in final
            ]
            return FacadeResult(chunks=final, sources=sources)
        except Exception as e:
            logger.exception(f"RetrievalFacade.retrieve failed: {e}")
            return FacadeResult()