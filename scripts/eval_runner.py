"""检索评测 CLI 薄封装（Spec A 基线/门禁/消融入口）。

用法：
    python scripts/eval_runner.py                          # 完整基线：全部 120 条、默认配置、默认 top_k
    python scripts/eval_runner.py --limit 5                # 小规模冒烟：只跑前 5 条（验证链路 + 控成本）
    python scripts/eval_runner.py --limit 5 --top-k 5      # 冒烟并指定检索 top_k
    make eval-dry-run                                      # dry-run：仅统计校验测试集，零外部调用

约束：本脚本复用 app/services/evaluation_service.py 与 app/services/eval_testset.py，
不重复实现任何评测逻辑（薄封装）。报告按项目约定（PROCESS.md §1.2）同时落盘
docs/evaluation/ 与 evaluation_service 默认的 data/eval_reports/。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

# 允许以 `python scripts/eval_runner.py` 直接运行：把项目根加入 sys.path 以导入 app 包
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
os.environ.setdefault("PYTHONUNBUFFERED", "1")

TESTSET_PATH = Path("data/eval_testset.json")
REPORT_LINK_DIR = Path("docs/evaluation")

REQUIRED_FIELDS = {"question", "expected_answer", "expected_source", "source_file", "question_type"}

# 内置检索配置：基线主配置 + 消融 4 组合（Spec A §4.3，hybrid 恒开）
BUILTIN_CONFIGS = {
    "hybrid_rerank": {"name": "hybrid_rerank", "use_hybrid": True, "use_rerank": True,
                      "use_query_rewrite": False},
    "dense_only": {"name": "dense_only", "use_hybrid": False, "use_rerank": False,
                   "use_query_rewrite": False},
    "no_rerank": {"name": "no_rerank", "use_hybrid": True, "use_rerank": False,
                  "use_query_rewrite": False},
    # 消融：query_rewrite × rerank 四组合（hybrid 恒开）
    "qr_on_rr_on": {"name": "qr_on_rr_on", "use_hybrid": True, "use_rerank": True,
                    "use_query_rewrite": True},
    "qr_off_rr_on": {"name": "qr_off_rr_on", "use_hybrid": True, "use_rerank": True,
                     "use_query_rewrite": False},
    "qr_on_rr_off": {"name": "qr_on_rr_off", "use_hybrid": True, "use_rerank": False,
                     "use_query_rewrite": True},
    "qr_off_rr_off": {"name": "qr_off_rr_off", "use_hybrid": True, "use_rerank": False,
                      "use_query_rewrite": False},
}


def _load_testset() -> list[dict]:
    if not TESTSET_PATH.exists():
        raise SystemExit(f"测试集不存在: {TESTSET_PATH}")
    return json.loads(TESTSET_PATH.read_text(encoding="utf-8"))


def _write_subset(testset: list[dict]) -> Path:
    """将评测子集写到临时文件，返回其路径（薄封装：只做子集编排，不改评估逻辑）。"""
    tmp = TESTSET_PATH.with_name(f"_eval_subset_{Path(__file__).name}.json")
    tmp.write_text(json.dumps(testset, ensure_ascii=False, indent=2), encoding="utf-8")
    return tmp


def _filter_by_origin(items: list[dict], origin: str | None) -> list[dict]:
    """按 origin 筛选样本（薄封装，不改评估逻辑）：
    - handwritten：仅手写核心集（origin 缺省或非 llm_extension，Spec A 金标准）
    - llm_extension：仅 LLM 扩展集
    - all / None：全部
    """
    if origin in (None, "all"):
        return items
    if origin == "handwritten":
        return [e for e in items if e.get("origin", "handwritten") != "llm_extension"]
    if origin == "llm_extension":
        return [e for e in items if e.get("origin") == "llm_extension"]
    raise SystemExit(f"未知 origin: {origin}（可选 handwritten / llm_extension / all）")


def _persist_to_docs(result: dict, prefix: str = "baseline") -> Path:
    import time
    import uuid
    REPORT_LINK_DIR.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = REPORT_LINK_DIR / f"eval_{prefix}_{ts}_{uuid.uuid4().hex[:6]}.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _dry_run(limit: int | None, top_k: int | None, origin: str | None = None) -> None:
    """仅做统计校验，绝不初始化检索环境，也不调用任何外部 API。"""
    items = _filter_by_origin(_load_testset(), origin)
    bad = [i for i, e in enumerate(items) if not REQUIRED_FIELDS.issubset(e.keys())]
    dist = Counter(e.get("question_type") for e in items)
    multi = sum(1 for e in items if isinstance(e.get("expected_source"), list))
    subset_n = min(limit, len(items)) if limit is not None else len(items)
    print(f"[dry-run] 测试集: {TESTSET_PATH}（origin={origin or 'all'}）")
    print(f"[dry-run] 总条数      = {len(items)}（本次将评测 {subset_n} 条）")
    print(f"[dry-run] 四维度分布  = {dict(sorted(dist.items()))}")
    print(f"[dry-run] 多源(跨文档) = {multi}")
    print(f"[dry-run] 字段完整(缺失索引) = {bad if bad else '无'}")
    print(f"[dry-run] 检索 top_k  = {top_k if top_k is not None else '(取 settings.top_k)'}")
    print("[dry-run] 已跳过检索管线初始化与 LLM/Embedding/Rerank 调用。")
    print("[dry-run] OK —— 测试集可供基线运行使用。")


def _run(limit: int | None, top_k: int | None, configs: list[dict] | None,
         origin: str | None = None) -> None:
    """真实基线运行：复用 evaluation_service.run。"""
    from app.services.evaluation_service import EvaluationService
    from app.services.embedding import EmbeddingService
    from app.storage.faiss_store import FaissStore
    from app.services.llm_client import LLMClient
    from app.services.sparse_retriever import SparseRetriever
    from app.services.retrieval_service import HybridRetriever
    from app.services.rerank_service import RerankService
    from app.services.query_rewrite import QueryRewriteService
    from app.config import settings

    items = _filter_by_origin(_load_testset(), origin)
    if limit is not None:
        items = items[: limit]
    subset_path = _write_subset(items)

    llm = LLMClient()
    embedding = EmbeddingService()
    faiss = FaissStore()
    idx = Path(settings.idx_path)
    if (idx / "index.faiss").exists():
        faiss.load(settings.idx_path)
    else:
        subset_path.unlink(missing_ok=True)
        raise SystemExit("未找到 FAISS 索引，请先构建（curl -X POST http://localhost:8000/api/index/build）")

    sparse = SparseRetriever(backend=settings.sparse_backend)
    if faiss.is_loaded():
        meta = faiss.get_all_metadata()
        if meta:
            sparse.add_documents([
                {"_id": m.get("_id", i), "content": m.get("content", ""),
                 "source_file": m.get("source_file", ""), "chunk_index": m.get("chunk_index", 0)}
                for i, m in enumerate(meta)
            ])

    hybrid = HybridRetriever(
        faiss_store=faiss, embedding=embedding,
        bm25_index_path=settings.bm25_index_path,
        enabled=settings.enable_hybrid_search, sparse=sparse)
    hybrid.load_bm25()

    rerank = RerankService(api_key=settings.siliconflow_api_key,
                           model_name=settings.rerank_model,
                           enabled=settings.enable_rerank)
    query_rewriter = QueryRewriteService(llm=llm, enabled=settings.enable_query_rewrite)

    svc = EvaluationService(llm=llm, embedding=embedding, faiss=faiss,
                            hybrid_retriever=hybrid, reranker=rerank,
                            query_rewriter=query_rewriter,
                            testset_path=str(subset_path),
                            top_k=top_k if top_k is not None else settings.top_k)
    result = asyncio.run(svc.run(configs))

    subset_path.unlink(missing_ok=True)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    cfg_name = configs[0]["name"] if configs else "all"
    report_name = _persist_to_docs(result, prefix=f"ablation_{cfg_name}")
    print(f"\n[report] 已落盘 docs/evaluation/ -> {report_name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="检索评测 CLI")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅统计校验测试集，不初始化检索环境、不调用外部 API")
    ap.add_argument("--limit", type=int, default=None,
                    help="评测样本条数上限（取测试集前 N 条）；省略则用全部。用于小规模冒烟 / 控成本")
    ap.add_argument("--top-k", type=int, default=None,
                    help="检索 top_k（默认取 settings.top_k）")
    ap.add_argument("--config", type=str, default=None,
                    choices=sorted(BUILTIN_CONFIGS),
                    help="内置检索配置名（hybrid_rerank / dense_only / no_rerank / qr_on_rr_on / qr_off_rr_on / qr_on_rr_off / qr_off_rr_off）；省略则跑全部 3 个")
    ap.add_argument("--configs", type=str, default=None,
                    help='可选的 JSON 配置列表，如 \'[{"name":"x","use_hybrid":true,"use_rerank":true,"use_query_rewrite":true}]\'')
    ap.add_argument("--origin", type=str, default=None,
                    choices=["handwritten", "llm_extension", "all"],
                    help="样本来源筛选：handwritten=仅手写核心集；llm_extension=仅扩展集；all=全部（默认）")
    args = ap.parse_args()

    if args.config:
        configs = [BUILTIN_CONFIGS[args.config]]
    else:
        configs = json.loads(args.configs) if args.configs else None
    if args.dry_run:
        _dry_run(args.limit, args.top_k, args.origin)
    else:
        _run(args.limit, args.top_k, configs, args.origin)


if __name__ == "__main__":
    main()