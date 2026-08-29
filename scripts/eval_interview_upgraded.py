"""面试检索升级后复试（Part B S3）。

用升级后的统一 RetrievalFacade（hybrid + rerank + parent，Part A 决策配置）对
同一面试评测子集 data/eval_interview_subset.json 跑一遍，产出 recall@3 / MRR /
命中文档，对照 S2 升级前基线（raw FAISS top-3：recall@3=0.588, mrr=0.559）。

目标：验证「升级后不劣于升级前」（Spec B §6）。输出 JSON 报告到 docs/evaluation/。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.environ.setdefault("PYTHONUNBUFFERED", "1")

from app.config import settings
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient
from app.services.query_rewrite import QueryRewriteService
from app.services.rerank_service import RerankService
from app.services.retrieval_facade import RetrievalFacade
from app.services.retrieval_service import HybridRetriever
from app.services.sparse_retriever import SparseRetriever
from app.storage.faiss_store import FaissStore

SUBSET_PATH = Path("data/eval_interview_subset.json")
REPORT_DIR = Path("docs/evaluation")
TOP_K = 5  # facade 检索 top_k（出题/评价均用 5，与 S3 实现一致）


def _load_subset():
    if not SUBSET_PATH.exists():
        raise SystemExit(f"面试评测子集不存在: {SUBSET_PATH}")
    return json.loads(SUBSET_PATH.read_text(encoding="utf-8"))


async def _build_facade() -> RetrievalFacade:
    """复刻 app/main.py 的装配：embedding + llm + sparse + hybrid + rerank + qr → facade。"""
    faiss_store = FaissStore()
    faiss_store.load(settings.idx_path)
    if not faiss_store.is_loaded():
        raise SystemExit(f"FAISS 索引未加载: {settings.idx_path}")

    embedding_service = EmbeddingService()
    llm_client = LLMClient()

    sparse_retriever = SparseRetriever(backend=settings.sparse_backend)
    _meta = faiss_store.get_all_metadata()
    if _meta:
        sparse_retriever.add_documents([
            {"_id": m.get("_id", i), "content": m.get("content", ""),
             "source_file": m.get("source_file", ""), "chunk_index": m.get("chunk_index", 0)}
            for i, m in enumerate(_meta)
        ])

    hybrid = HybridRetriever(
        faiss_store=faiss_store, embedding=embedding_service,
        bm25_index_path=settings.bm25_index_path,
        enabled=settings.enable_hybrid_search, sparse=sparse_retriever,
    )
    hybrid.load_bm25()

    qr = QueryRewriteService(llm=llm_client, enabled=settings.enable_query_rewrite)
    rr = RerankService(api_key=settings.siliconflow_api_key,
                       model_name=settings.rerank_model,
                       enabled=settings.enable_rerank)

    return RetrievalFacade(
        faiss_store=faiss_store, embedding=embedding_service,
        query_rewriter=qr, hybrid_retriever=hybrid, reranker=rr,
    )


async def main(limit: int):
    subset = _load_subset()
    if limit:
        subset = subset[:limit]
    facade = await _build_facade()

    rows = []
    for item in subset:
        query = item["query"]
        expected_raw = item["expected_source"]
        expected = expected_raw if isinstance(expected_raw, list) else [expected_raw]
        sample_type = item.get("sample_type", "出题形态")

        result = await facade.retrieve(query, top_k=TOP_K)
        hits = [s.file for s in result.sources]
        hit = len([e for e in expected if e in set(hits)]) >= 1

        mrr = 0.0
        for rank, src in enumerate(hits, start=1):
            if src in expected:
                mrr = 1.0 / rank
                break

        rows.append({
            "query": query[:80], "sample_type": sample_type,
            "expected_source": expected, "top_k_hits": hits,
            "hit": hit, "mrr": mrr,
        })

    overall = {
        "n": len(rows),
        "recall@3": round(sum(1 for r in rows if r["hit"]) / len(rows), 4) if rows else 0,
        "mrr": round(sum(r["mrr"] for r in rows) / len(rows), 4) if rows else 0,
    }
    by_type = {}
    for st in ("出题形态", "评价形态"):
        rs = [r for r in rows if r["sample_type"] == st]
        if rs:
            by_type[st] = {
                "n": len(rs),
                "recall@3": round(sum(1 for r in rs if r["hit"]) / len(rs), 4),
                "mrr": round(sum(r["mrr"] for r in rs) / len(rs), 4),
            }

    report = {
        "purpose": "Part B S3 面试检索升级后复试（统一 facade hybrid+rerank）",
        "config": {"backend": "retrieval_facade", "top_k": TOP_K,
                   "qr_enabled": settings.enable_query_rewrite,
                   "rerank_enabled": settings.enable_rerank},
        "baseline_ref": {"recall@3": 0.588, "mrr": 0.559,
                         "note": "S2 升级前 raw FAISS top-3"},
        "overall": overall, "by_sample_type": by_type, "rows": rows,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "eval_interview_upgraded_facade_top5.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[报告已写] {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    asyncio.run(main(args.limit))