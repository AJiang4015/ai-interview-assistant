"""Part B 统一检索门面（RetrievalFacade）的单元测试。

覆盖：管线编排（qr→hybrid→rerank）、降级语义（依赖缺失/异常时不抛）、
来源结构、以及 src 行为等价的关键约束（DR-001 / DR-005 一线）。
"""

import asyncio

from app.config import settings
from app.services.retrieval_facade import RetrievalFacade, SourceInfo, FacadeResult
from app.services.retrieval_service import RetrievalResult


def _res(chunk_id, content, source="a.md", idx=0, score=0.5):
    return RetrievalResult(
        chunk_id=chunk_id, source_file=source, chunk_index=idx,
        content=content, score=score,
    )


class _FakeFaiss:
    async def asearch(self, vec, top_k):
        return [_res(0, "f0", idx=0), _res(1, "f1", idx=1)]


class _FakeEmbed:
    async def encode(self, texts):
        import numpy as np
        return np.ones((len(texts), 8))


class _FakeHybrid:
    enabled = True

    async def retrieve(self, query, top_k):
        return [_res(0, "h0", idx=0), _res(1, "h1", idx=1), _res(2, "h2", idx=2)]


class _FakeRerank:
    enabled = True

    async def rerank(self, query, docs, top_k):
        # 反转顺序，验证重排被采用
        out = []
        for content in reversed(docs):
            out.append(_res(hash(content) % 1000, content, idx=docs.index(content)))
        return out[:top_k]


class _FakeQR:
    enabled = True

    def __init__(self):
        self.queries = []

    async def rewrite(self, q):
        self.queries.append(q)
        return f"rewritten:{q}"


def _facade(hybrid=None, rr=None, qr=None):
    return RetrievalFacade(
        faiss_store=_FakeFaiss(), embedding=_FakeEmbed(),
        query_rewriter=qr, hybrid_retriever=hybrid, reranker=rr,
    )


def test_retrieve_runs_qr_hybrid_rerank_in_order():
    qr = _FakeQR()
    f = _facade(hybrid=_FakeHybrid(), rr=_FakeRerank(), qr=qr)
    result = asyncio.run(f.retrieve("q"))
    assert qr.queries == ["q"]  # 查询改写拿到原始问题
    assert result.sources  # 有来源
    # 重排反转顺序：h2 应排最前（原始顺序 h0,h1,h2 → 重排 h2,h1,h0 → top_k 全收）
    contents = [c.content for c in result.chunks]
    assert contents[0] == "h2"


def test_retrieve_no_hybrid_falls_back_to_faiss():
    f = _facade()  # 无 hybrid、无 rr、无 qr → 走稠密 + 截断
    result = asyncio.run(f.retrieve("q"))
    assert len(result.chunks) <= settings.top_k


def test_retrieve_all_off_returns_topk():
    f = _facade()
    result = asyncio.run(f.retrieve("q", top_k=2))
    assert len(result.chunks) == 2


def test_rewrite_degrades_on_exception():
    class Boom:
        enabled = True

        async def rewrite(self, q):
            raise RuntimeError("boom")

    f = _facade(hybrid=_FakeHybrid(), qr=Boom())
    result = asyncio.run(f.retrieve("q"))
    assert result.sources  # 未抛异常，降级后用原文继续

    query = asyncio.run(f.rewrite("q"))
    assert query == "q"


def test_retrieve_never_raises_on_pipeline_failure():
    class BoomHybrid:
        enabled = True

        async def retrieve(self, q, top_k):
            raise RuntimeError("retrieve boom")

    f = _facade(hybrid=BoomHybrid())
    result = asyncio.run(f.retrieve("q"))
    assert result.is_empty  # 失败 → 空结果，不回抛（DR-001）


def test_facade_result_to_text_and_sources():
    fc = FacadeResult(chunks=[_res(1, "alpha", idx=3, score=0.9)], sources=[SourceInfo(file="a.md", chunk_index=3, score=0.9)])
    assert fc.to_text() == "alpha"
    assert fc.sources[0].file == "a.md"
    assert fc.sources[0].chunk_index == 3
    assert FacadeResult().is_empty is True