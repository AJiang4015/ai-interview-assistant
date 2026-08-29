import json
import re
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)

GEN_PROMPT = """你正在为 RAG 检索评测集做「同义扩展」：基于一条人工金标准问题，生成同一知识点的不同问法。
要求：
1. 模拟真实用户或面试官的口语化问法（如「你说说线程池呗」「你们线上是怎么搞的」），不得照抄原问题；
2. 只围绕原问题涉及的知识点改写问法，不得引入原问题之外的新知识点；
3. 新问法与原问题语义等价，答案与出处与原问题完全相同。

原问题：{question}
问题类型标签：{question_type}（a=跨文档推理 b=易混概念辨析 c=口语化面试问法 d=边界反直觉）

请生成 {variants} 个不同问法，只以 JSON 输出：{{"questions": ["问法1", "问法2", ...]}}
"""


def _normalize_question(q: str) -> str:
    """去除空白与标点并统一小写，用于问法去重与「防照抄」判定。"""
    return re.sub(r"[\s\W_]+", "", q, flags=re.UNICODE).lower()


class TestSetGenerator:
    """评测集生成器。

    扩展策略（Spec A：禁止 chunk 反推）：以已有「手写核心集」为种子，
    让 LLM 对种子问题做同义改写（口语化/面试官问法变体），期望答案与
    来源直接继承种子样本。chunk 文本不参与问题生成，避免「自问自答」
    导致的检索指标虚高。

    构造参数 chunks 为历史兼容保留，当前实现忽略该参数。
    """

    def __init__(self, llm, testset_path: str = "data/eval_testset.json",
                 chunks: list | None = None, evaluate_every: int = 1,
                 variants_per_seed: int = 3):
        self.llm = llm
        self.testset_path = Path(testset_path)
        self.chunks = chunks or []
        self.evaluate_every = evaluate_every
        self.variants_per_seed = variants_per_seed

    def _parse_json(self, text: str) -> dict | None:
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

    def load(self):
        if not self.testset_path.exists():
            return []
        with open(self.testset_path, encoding="utf-8") as f:
            return json.load(f)

    def clear(self):
        if self.testset_path.exists():
            self.testset_path.unlink()

    async def generate(self, limit: int | None = None):
        """基于手写核心集生成 LLM 扩展集（同义问法变体）。

        - 种子 = 测试集中 origin 非 "llm_extension" 的手写样本；
        - 每个种子生成 variants_per_seed 个变体问法，答案/来源/类型继承种子；
        - 归一化后与已有问法相同（含照抄种子）的一律丢弃；
        - limit=0 时直接返回，可用于 dry-run（不触发任何 LLM 调用）。
        """
        existing = self.load()
        seeds = [e for e in existing if e.get("origin", "handwritten") != "llm_extension"]
        seen = {_normalize_question(e["question"]) for e in existing}
        created = 0
        for seed in seeds:
            if limit is not None and created >= limit:
                break
            try:
                text = await self.llm.chat(GEN_PROMPT.format(
                    question=seed["question"],
                    question_type=seed.get("question_type", ""),
                    variants=self.variants_per_seed,
                ))
                parsed = self._parse_json(text) or {}
                raw = parsed.get("questions", [])
                questions = [q.strip() for q in raw if isinstance(q, str) and q.strip()]
            except Exception as e:
                logger.warning(f"Testset variant gen failed for seed '{seed['question'][:20]}...': {e}")
                questions = []
            for q in questions:
                if limit is not None and created >= limit:
                    break
                nq = _normalize_question(q)
                if not nq or nq in seen:
                    continue
                existing.append({
                    "question": q,
                    "expected_answer": seed["expected_answer"],
                    "expected_source": seed["expected_source"],
                    "source_file": seed["source_file"],
                    "question_type": seed.get("question_type", ""),
                    "origin": "llm_extension",
                })
                seen.add(nq)
                created += 1
        with open(self.testset_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
        return {"total": len(existing), "created": created}
