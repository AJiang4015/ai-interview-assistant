# app/services/evaluation_service.py
import json
import re
import asyncio
import time
from pathlib import Path

from app.services.eval_metrics import hit_rate, recall_at_k, mrr
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


class EvaluationService:
    def __init__(self, llm, embedding, faiss, hybrid_retriever, reranker,
                 testset_path: str = "data/eval_testset.json", top_k: int = 5):
        self.llm = llm
        self.embedding = embedding
        self.faiss = faiss
        self.hybrid = hybrid_retriever
        self.reranker = reranker
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
        try:
            result = await self.run(configs)
            self._jobs[job_id] = {"status": "done", "result": result, "error": None}
        except Exception as e:
            self._jobs[job_id] = {"status": "error", "result": None, "error": str(e)}

    async def _retrieve(self, query: str, use_hybrid: bool, use_rerank: bool) -> list[dict]:
        """按配置检索，返回按相关性排序的 chunk 列表：[{content, source_file}]。"""
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

    async def run(self, configs: list[dict] | None = None) -> dict:
        testset = self._load_testset()
        if not testset:
            return {"error": "测试集为空，请先生成测试集"}
        default_cfgs = [
            {"name": "hybrid_rerank", "use_hybrid": True, "use_rerank": True},
            {"name": "dense_only", "use_hybrid": False, "use_rerank": False},
            {"name": "no_rerank", "use_hybrid": True, "use_rerank": False},
        ]
        configs = configs or default_cfgs
        report = {
            "timestamp": time.strftime("%Y%m%d_%H%M%S"),
            "configs": [],
            "total_questions": len(testset),
        }
        for cfg in configs:
            retrieval_metrics = []
            gen_f = gen_r = gen_c = 0.0
            gen_n = 0
            for item in testset:
                chunks = await self._retrieve(item["question"], cfg["use_hybrid"], cfg["use_rerank"])
                ranked = [c["source_file"] for c in chunks]
                expected = {item["expected_source"]}
                retrieval_metrics.append({
                    "hit": hit_rate(ranked, expected, self.top_k),
                    "recall": recall_at_k(ranked, expected, self.top_k),
                    "mrr": mrr(ranked, expected, self.top_k),
                })
                context = self._context_text(chunks)
                answer = await self._generate_answer(item["question"], context)
                gen_f += await self._judge(FAITHFULNESS_PROMPT.format(context=context, answer=answer))
                gen_r += await self._judge(ANSWER_RELEVANCE_PROMPT.format(question=item["question"], answer=answer))
                gen_c += await self._judge(CONTEXT_RELEVANCE_PROMPT.format(question=item["question"], context=context))
                gen_n += 1
            report["configs"].append({
                "name": cfg["name"],
                "retrieval": _aggregate_retrieval(retrieval_metrics),
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