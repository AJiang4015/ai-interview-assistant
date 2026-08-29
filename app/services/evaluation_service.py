# app/services/evaluation_service.py
import json
import re
import asyncio
import time
from pathlib import Path

from app.services.eval_metrics import (
    recall_at_k, mrr, parse_expected_sources, multi_source_hit,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

REPORT_DIR = Path("data/eval_reports")

FAITHFULNESS_PROMPT = """判断回答是否忠于给定的检索上下文（无幻觉）。
上下文：
{context}

回答：
{answer}

请只以 JSON 输出：{{"score": <0.0-1.0>}}
"""
ANSWER_RELEVANCE_PROMPT = """判断回答与问题是否相关。
问题：{question}
回答：{answer}
请只以 JSON 输出：{{"score": <0.0-1.0>}}
"""
CONTEXT_RELEVANCE_PROMPT = """判断给定的检索上下文与问题是否相关。
问题：{question}
上下文：
{context}
请只以 JSON 输出：{{"score": <0.0-1.0>}}
"""


def _parse_json(text: str) -> dict | None:
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"(\{.*\})", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    return None


def _aggregate_retrieval(metrics: list[dict]) -> dict:
    n = max(len(metrics), 1)
    return {
        "hit_rate": round(sum(m["hit"] for m in metrics) / n, 4),
        "recall": round(sum(m["recall"] for m in metrics) / n, 4),
        "mrr": round(sum(m["mrr"] for m in metrics) / n, 4),
        "samples": len(metrics),
    }


def _aggregate_breakdown(metrics: list[dict]) -> dict:
    """按 question_type(a/b/c/d) 分维度聚合 recall@3 / recall@5 / mrr（Spec A §4.2）。"""
    total = {"recall@3": 0.0, "recall@5": 0.0, "mrr": 0.0}
    by_dim: dict[str, list[dict]] = {}
    for m in metrics:
        qt = m["question_type"]
        by_dim.setdefault(qt, []).append(m)
        total["recall@3"] += m["recall@3"]
        total["recall@5"] += m["recall@5"]
        total["mrr"] += m["mrr"]
    n = max(len(metrics), 1)
    overall = {k: round(v / n, 4) for k, v in total.items()}
    overall["samples"] = len(metrics)
    dims = {}
    for qt, ms in by_dim.items():
        k2 = len(ms)
        dims[qt] = {
            "samples": k2,
            "recall@3": round(sum(x["recall@3"] for x in ms) / max(k2, 1), 4),
            "recall@5": round(sum(x["recall@5"] for x in ms) / max(k2, 1), 4),
            "mrr": round(sum(x["mrr"] for x in ms) / max(k2, 1), 4),
        }
    return {"overall": overall, "by_dimension": dims}


class EvaluationService:
    def __init__(self, llm, embedding, faiss, hybrid_retriever, reranker,
                 testset_path: str = "data/eval_testset.json", top_k: int = 5,
                 query_rewriter=None):
        self.llm = llm
        self.embedding = embedding
        self.faiss = faiss
        self.hybrid = hybrid_retriever
        self.reranker = reranker
        self.query_rewriter = query_rewriter
        self.testset_path = Path(testset_path)
        self.top_k = top_k
        self._jobs: dict[str, dict] = {}
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

    def create_job(self, configs: list[dict] | None = None) -> str:
        import uuid
        job_id = uuid.uuid4().hex[:12]
        self._jobs[job_id] = {"status": "running", "result": None, "error": None}
        return job_id

    def get_job(self, job_id: str) -> dict | None:
        return self._jobs.get(job_id)

    async def run_async(self, job_id: str, configs: list[dict] | None = None):
        """后台执行评测，结果写入 job。"""
        def _progress(current_config, total_configs, current_item, total_items, stage):
            self._jobs[job_id]["progress"] = {
                "current_config": current_config,
                "total_configs": total_configs,
                "current_item": current_item,
                "total_items": total_items,
                "stage": stage,
            }
        try:
            result = await self.run(configs, progress_cb=_progress)
            self._jobs[job_id] = {"status": "done", "result": result, "error": None}
        except Exception as e:
            self._jobs[job_id] = {"status": "error", "result": None, "error": str(e)}

    async def _retrieve(self, query: str, use_hybrid: bool, use_rerank: bool,
                        use_query_rewrite: bool = False) -> list[dict]:
        """按配置检索，返回按相关性排序的 chunk 列表：[{content, source_file}]。"""
        if use_query_rewrite and self.query_rewriter and self.query_rewriter.enabled:
            try:
                rewritten = await self.query_rewriter.rewrite(query)
                if rewritten and rewritten.strip():
                    query = rewritten.strip()
            except Exception as e:
                logger.warning(f"Eval query rewrite failed, using original: {e}")
        if use_hybrid and self.hybrid and self.hybrid.enabled:
            try:
                results = await self.hybrid.retrieve(query, top_k=20)
            except Exception as e:
                logger.warning(f"Eval hybrid retrieve failed: {e}")
                return []
        else:
            try:
                vec = await self.embedding.encode([query])
            except Exception as e:
                logger.warning(f"Eval embedding failed: {e}")
                return []
            if vec.size == 0:
                return []
            results = self.faiss.search(vec[0], 20)
        if use_rerank and self.reranker and self.reranker.enabled:
            docs = [r.content for r in results]
            reranked = await self.reranker.rerank(query, docs, top_k=self.top_k)
            content_idx = {r.content: r for r in results}
            ordered = [content_idx[rr.content] for rr in reranked if rr.content in content_idx]
        else:
            ordered = list(results)[:self.top_k]
        return [{"content": r.content, "source_file": r.source_file} for r in ordered]

    async def _judge(self, prompt: str) -> float:
        try:
            text = await self.llm.chat(prompt)
            data = _parse_json(text)
            if data is None:
                return 0.0
            return max(0.0, min(1.0, float(data.get("score", 0))))
        except Exception as e:
            logger.warning(f"Judge failed: {e}")
            return 0.0

    async def _generate_answer(self, question: str, context: str) -> str:
        try:
            return await self.llm.chat(f"参考资料：\n{context}\n\n问题：{question}")
        except Exception:
            return ""

    @staticmethod
    def _context_text(chunks: list[dict]) -> str:
        return "\n---\n".join(c["content"] for c in chunks)

    async def run(self, configs: list[dict] | None = None, progress_cb=None) -> dict:
        testset = self._load_testset()
        if not testset:
            return {"error": "测试集为空，请先生成测试集"}
        default_cfgs = [
            {"name": "hybrid_rerank", "use_hybrid": True, "use_rerank": True},
            {"name": "dense_only", "use_hybrid": False, "use_rerank": False},
            {"name": "no_rerank", "use_hybrid": True, "use_rerank": False},
        ]
        configs = configs or default_cfgs
        total_items = len(testset) * len(configs)
        processed = 0
        report = {
            "timestamp": time.strftime("%Y%m%d_%H%M%S"),
            "configs": [],
            "total_questions": len(testset),
        }
        for cfg_index, cfg in enumerate(configs, start=1):
            retrieval_metrics = []
            gen_f = gen_r = gen_c = 0.0
            gen_n = 0
            for item in testset:
                chunks = await self._retrieve(item["question"], cfg["use_hybrid"], cfg["use_rerank"],
                                              cfg.get("use_query_rewrite", False))
                ranked = [c["source_file"] for c in chunks]
                # 多源 recall 语义（Spec A）：
                # - expected_source 为列表（跨文档题）时，主文档（首元素）必须出现在
                #   top-k，且至少一个副文档也出现，hit 才记 1.0；recall 按全部期望
                #   来源的命中比例计算；mrr 以主文档的排名为准。
                # - expected_source 为字符串（单源题）时，三种指标均退化为原有逻辑。
                primary, expected = parse_expected_sources(item["expected_source"])
                retrieval_metrics.append({
                    "hit": multi_source_hit(ranked, item["expected_source"], self.top_k),
                    "recall": recall_at_k(ranked, expected, self.top_k),
                    "recall@3": recall_at_k(ranked, expected, 3),
                    "recall@5": recall_at_k(ranked, expected, 5),
                    "mrr": mrr(ranked, {primary}, self.top_k),
                    "question_type": item.get("question_type", ""),
                })
                context = self._context_text(chunks)
                answer = await self._generate_answer(item["question"], context)
                gen_f += await self._judge(FAITHFULNESS_PROMPT.format(context=context, answer=answer))
                gen_r += await self._judge(ANSWER_RELEVANCE_PROMPT.format(question=item["question"], answer=answer))
                gen_c += await self._judge(CONTEXT_RELEVANCE_PROMPT.format(question=item["question"], context=context))
                gen_n += 1
                processed += 1
                if progress_cb:
                    progress_cb(cfg_index, len(configs), processed, total_items, cfg["name"])
            report["configs"].append({
                "name": cfg["name"],
                "retrieval": _aggregate_retrieval(retrieval_metrics),
                "retrieval_breakdown": _aggregate_breakdown(retrieval_metrics),
                "generation": {
                    "faithfulness": round(gen_f / max(gen_n, 1), 4),
                    "answer_relevance": round(gen_r / max(gen_n, 1), 4),
                    "context_relevance": round(gen_c / max(gen_n, 1), 4),
                },
            })
        self._save_report(report)
        return report

    def _load_testset(self):
        if not self.testset_path.exists():
            return []
        with open(self.testset_path, encoding="utf-8") as f:
            return json.load(f)

    def _save_report(self, report):
        import uuid
        name = f"{report['timestamp']}_{uuid.uuid4().hex[:6]}.json"
        with open(REPORT_DIR / name, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

    def list_reports(self):
        return sorted(p.name for p in REPORT_DIR.glob("*.json"))

    def get_report(self, name):
        path = REPORT_DIR / name
        if not path.exists():
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)