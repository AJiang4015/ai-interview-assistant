"""面试检索升级前基线统计（Part B S2）。

用【旧链路】行为（interview_service._retrieve_context 复刻：raw FAISS 稠密检索，top-3）
对面试评测子集 data/eval_interview_subset.json 跑一遍，统计：
  - recall@3、MRR（with expected_source 单源）
  - 命中 / 未命中文档明细
  - 分形态（出题 / 评价）维度

目的：固化「升级前基线」，供 S3 迁移 RetrievalFacade 后对照，验证不劣于升级前（Spec B §6）。

本脚本是【一次性基线工具】，复刻旧链路，不依赖务实入口；输出 JSON 报告到 docs/evaluation/ 并打印人工抽查摘要。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.environ.setdefault("PYTHONUNBUFFERED", "1")

from app.config import settings
from app.services.embedding import EmbeddingService
from app.storage.faiss_store import FaissStore

SUBSET_PATH = Path("data/eval_interview_subset.json")
REPORT_DIR = Path("docs/evaluation")
TOP_K = 3  # 与旧链路 _retrieve_context 的 top-3 一致


def _load_subset():
    if not SUBSET_PATH.exists():
        raise SystemExit(f"面试评测子集不存在: {SUBSET_PATH}")
    return json.loads(SUBSET_PATH.read_text(encoding="utf-8"))


def _match_found(hits: list[str], expected: list[str]) -> tuple[bool, list]:
    """单源匹配：expected_source 列表（本子集单源必现）。返回 (hit, 命中的期望文档数/名)。"""
    hitset = set(hits)
    matched = [e for e in expected if e in hitset]
    return (len(matched) >= 1, matched)


async def main(limit: int):
    subset = _load_subset()
    if limit:
        subset = subset[:limit]

    faiss_store = FaissStore()
    faiss_store.load(settings.idx_path)
    if not faiss_store.is_loaded():
        raise SystemExit(f"FAISS 索引未加载: {settings.idx_path}")
    embedding = EmbeddingService()

    rows = []
    for item in subset:
        query = item["query"]
        expected_raw = item["expected_source"]
        expected = expected_raw if isinstance(expected_raw, list) else [expected_raw]
        sample_type = item.get("sample_type", "出题形态")

        vec = await embedding.encode([query])
        results = await faiss_store.asearch(vec[0], TOP_K)
        hits = [r.source_file for r in results]
        hit, matched = _match_found(hits, expected)

        # MRR：期望主文档首次出现的名次倒数；未命中记 0
        mrr = 0.0
        for rank, src in enumerate(hits, start=1):
            if src in expected:
                mrr = 1.0 / rank
                break

        rows.append({
            "query": query[:80],
            "sample_type": sample_type,
            "expected_source": expected,
            "top_k_hits": hits,
            "matched": matched,
            "hit": hit,
            "mrr": mrr,
        })

    overall = {
        "n": len(rows),
        "hit_rate": round(sum(r["hit"] for r in rows) / len(rows), 4) if rows else 0,
        "recall@3": round(sum(1 for r in rows if r["hit"]) / len(rows), 4) if rows else 0,
        "mrr": round(sum(r["mrr"] for r in rows) / len(rows), 4) if rows else 0,
    }

    # 分维度
    by_type: dict[str, dict] = {}
    for st in ("出题形态", "评价形态"):
        rs = [r for r in rows if r["sample_type"] == st]
        if rs:
            by_type[st] = {
                "n": len(rs),
                "recall@3": round(sum(1 for r in rs if r["hit"]) / len(rs), 4),
                "mrr": round(sum(r["mrr"] for r in rs) / len(rs), 4),
            }

    report = {
        "purpose": "Part B S2 面试检索升级前基线（旧链路 raw FAISS top-3）",
        "config": {"backend": "raw_faiss_dense", "top_k": TOP_K, "model": settings.siliconflow_model},
        "overall": overall,
        "by_sample_type": by_type,
        "rows": rows,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "eval_interview_baseline_rawfaiss_top3.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n[报告已写] {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全部）")
    args = ap.parse_args()
    asyncio.run(main(args.limit))