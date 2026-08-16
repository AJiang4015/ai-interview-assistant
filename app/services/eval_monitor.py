"""幻觉评估：抽样式 Faithfulness 打分，低于阈值触发告警。"""
import json
import random
import re

from app.config import settings


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


class EvalMonitor:
    """抽样式幻觉评估。sample_rate 默认取 settings.sample_eval_rate。"""

    def __init__(self, llm, sample_rate: float | None = None, threshold: float | None = None):
        self.llm = llm
        self.sample_rate = sample_rate if sample_rate is not None else settings.sample_eval_rate
        self.threshold = threshold if threshold is not None else settings.faithfulness_threshold

    async def maybe_eval(self, query: str, context: str, answer: str,
                         session_id: str | None = None) -> float | None:
        """按采样率决定是否评估。返回 Faithfulness 分数；未采样返回 None。"""
        if random.random() > self.sample_rate:
            return None
        prompt = "判断回答是否忠于给定的检索上下文（无幻觉）。\n上下文：\n{context}\n\n回答：\n{answer}\n请只以 JSON 输出：{{\"score\": <0.0-1.0>}}".format(
            context=context, answer=answer)
        try:
            text = await self.llm.chat(prompt)
        except Exception:
            return None
        score = self._evaluate_score(text)
        return score

    def _evaluate_score(self, llm_text: str) -> bool:
        """提取 score 并判断是否低于阈值。返回 True 表示命中幻觉预埋。"""
        data = _parse_json(llm_text)
        if data is None:
            return False
        score = max(0.0, min(1.0, float(data.get("score", 0))))
        return score < self.threshold