# tests/services/test_interview_evaluation_reason.py
# 面试评价「评分原因 + 参考答案」：新字段透传、报告校正、缺失容错
import asyncio
import json

import pytest

from app.services.interview_service import InterviewService
from app.storage.interview_store import InterviewStore


class FakeLLM:
    """按调用顺序返回预置响应的假 LLM。"""

    def __init__(self, responses):
        self.responses = list(responses)

    async def chat(self, prompt, system=None):
        if self.responses:
            return self.responses.pop(0)
        return ""


@pytest.fixture()
def store(tmp_path):
    s = InterviewStore(db_path=str(tmp_path / "interviews-test.db"))
    yield s
    s = None


QUESTION = "请解释 ConcurrentHashMap 的原理"
REASON = "答对：锁分段思路正确。遗漏：未提到 size 统计与并发更新细节。"
REFERENCE = "1. 分段/桶锁 2. CAS 3. size 统计 4. 与 Hashtable 区别"


def _make_answered_session(store, username="alice"):
    """造一场已作答 1 题、评价携带新字段的面试。"""
    sid = store.create_session("Java后端", username=username)["id"]
    q = store.add_question(sid, 1, QUESTION, topic="并发", category="Java")
    ev = {
        "score": 7,
        "comment": "要点基本覆盖，深度不足",
        "score_reason": REASON,
        "reference_answer": REFERENCE,
        "tags": ["并发"],
        "next_difficulty": "medium",
        "should_end": False,
    }
    store.update_answer(q["id"], "回答内容", ev, 7)
    return sid, q["id"]


def test_answer_returns_new_fields(store):
    """LLM 返回完整新字段时，answer 原样透传给前端。"""
    ev = {
        "score": 8,
        "comment": "不错",
        "score_reason": REASON,
        "reference_answer": REFERENCE,
        "tags": ["Java"],
        "next_difficulty": "medium",
        "should_end": False,
    }
    llm = FakeLLM([json.dumps(ev, ensure_ascii=False)])
    svc = InterviewService(store=store, llm=llm)
    _, qid = _make_answered_session(store)

    result = asyncio.run(svc.answer(qid, "新回答", generate_next=False))
    out = result["evaluation"]
    assert out["score_reason"] == REASON
    assert out["reference_answer"] == REFERENCE
    assert result["next_question"] is None  # generate_next=False 不生成下一题


def test_answer_missing_new_fields_falls_back_to_empty(store):
    """LLM 返回缺新字段的 JSON 时，answer 补空值而非报错。"""
    llm = FakeLLM([
        '{"score": 6, "comment": "中规中矩", "tags": ["Java"], "next_difficulty": "medium", "should_end": false}'
    ])
    svc = InterviewService(store=store, llm=llm)
    _, qid = _make_answered_session(store)

    result = asyncio.run(svc.answer(qid, "新回答", generate_next=False))
    ev = result["evaluation"]
    assert ev["score"] == 6
    assert ev["score_reason"] == ""
    assert ev["reference_answer"] == ""


def test_answer_parse_failure_fallback(store):
    """LLM 输出无法解析时，使用内置 fallback（含空的新字段）。"""
    llm = FakeLLM(["完全不是 JSON 的乱码"])
    svc = InterviewService(store=store, llm=llm)
    _, qid = _make_answered_session(store)

    result = asyncio.run(svc.answer(qid, "新回答", generate_next=False))
    ev = result["evaluation"]
    assert "score_reason" in ev
    assert "reference_answer" in ev
    assert ev["score_reason"] == ""


def test_report_breakdown_full_question_and_fields(store):
    """报告 score_breakdown 用本地数据校正：完整题目 + 真实评分原因/参考答案。

    模拟 LLM 生成的报告截断题目且缺新字段，后端应以本地真实数据覆盖。
    """
    llm_report = json.dumps({
        "score_breakdown": [
            {"round": 1, "question": "题目概要（被截断）", "score": 7, "tags": ["并发"]}
        ],
        "total_score": 7.0,
        "knowledge_analysis": {"strengths": ["并发"], "weaknesses": ["深度"]},
        "improvement_suggestions": ["加深学习"],
        "level": "中级",
    }, ensure_ascii=False)
    llm = FakeLLM([llm_report])
    svc = InterviewService(store=store, llm=llm)
    sid, _ = _make_answered_session(store)

    report = asyncio.run(svc._generate_report(sid))
    item = report["score_breakdown"][0]
    assert item["question"] == QUESTION  # 完整题目，未被截断
    assert item["score_reason"] == REASON
    assert item["reference_answer"] == REFERENCE
    assert item["score"] == 7


def test_report_fallback_contains_new_fields(store):
    """报告生成失败走 fallback 时，score_breakdown 仍携带完整题目与新字段。"""
    llm = FakeLLM(["not json at all"])
    svc = InterviewService(store=store, llm=llm)
    sid, _ = _make_answered_session(store)

    report = asyncio.run(svc._generate_report(sid))
    item = report["score_breakdown"][0]
    assert item["question"] == QUESTION
    assert item["score_reason"] == REASON
    assert item["reference_answer"] == REFERENCE
