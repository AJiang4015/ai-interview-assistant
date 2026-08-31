"""W1 Day 4：fallback 单元测试（spec G1-F / G4-F / G8 确定性兜底）。"""

import pytest

from app.services.agent.fallback import (
    deterministic_summary,
    fallback_question,
    generate_summary,
    rule_score,
)


def test_fallback_question_with_topic():
    q = fallback_question({"category": "JVM", "topic": "类加载", "reason": "薄弱"}, "easy")
    assert "类加载" in q["question"]
    assert q["difficulty"] == "easy"
    assert q["knowledge_tags"] == ["类加载"]
    assert q["source"] == "llm"
    assert q["fallback"] is True


def test_fallback_question_without_topic():
    q = fallback_question({"category": None, "topic": None, "reason": "知识树未加载"}, "medium")
    assert q["question"]
    assert q["topic"] == ""
    assert q["fallback"] is True


def test_rule_score_short_answer_scores_2():
    ev = rule_score("什么是事务？", "嗯", ["事务"])
    assert ev["score"] == 2
    assert ev["fallback"] == "eval_rule"
    assert ev["score_reason"]


def test_rule_score_hit_ratio():
    ev = rule_score("什么是 JVM？", "JVM 是 Java 虚拟机，负责加载字节码并解释执行。" * 2, ["JVM", "类加载"])
    # 命中 1/2 → round(5 + 5*0.5) = 8
    assert ev["score"] == 8


def test_rule_score_zero_hit():
    ev = rule_score("什么是 JVM？", "不太确定，可能是缓存相关。" * 2, ["JVM"])
    assert ev["score"] == 5  # 命中 0/1


def _questions():
    return [
        {
            "round": 1, "question": "q1", "answer": "a1", "score": 7.0,
            "topic": "JVM", "category": "JVM", "source": "llm",
            "evaluation": {"tags": ["JVM"], "comment": "c", "score_reason": "r", "reference_answer": "ref"},
        },
        {  # followup：不得计入统计
            "round": 1, "question": "fq", "answer": "fa", "score": 7.0,
            "topic": "", "category": "", "source": "followup",
            "evaluation": {"tags": ["JVM"]},
        },
        {
            "round": 2, "question": "q2", "answer": "a2", "score": 3.0,
            "topic": "Redis", "category": "Redis", "source": "llm",
            "evaluation": {"tags": ["Redis"], "comment": "c", "score_reason": "r", "reference_answer": "ref"},
        },
    ]


def test_deterministic_summary_filters_followup_and_legacy_shape():
    session = {"position": "Java后端", "id": "s1"}
    r = deterministic_summary(session, _questions())
    # 主问题 (7+3)/2 = 5.0，followup 不计入
    assert r["total_score"] == 5.0
    assert len(r["score_breakdown"]) == 2
    assert r["level"] in ("初级", "中级", "高级")
    assert isinstance(r["knowledge_analysis"], dict)
    assert isinstance(r["improvement_suggestions"], list)
    assert r["topic_analysis"]  # Redis 弱 (3) → weak
    assert r["recommended_study"]


def test_deterministic_summary_empty():
    r = deterministic_summary({"position": "Java后端", "id": "s1"}, [])
    assert r["total_score"] == 0
    assert r["level"] == "未知"
    assert r["improvement_suggestions"]


@pytest.mark.asyncio
async def test_generate_summary_llm_ok_merges_local():
    session = {"position": "Java后端", "id": "s1"}
    questions = [_questions()[0]]

    async def llm(prompt, system=None):
        return '{"level": "高级", "knowledge_analysis": {"strengths": ["JVM"], "weaknesses": []}, "improvement_suggestions": ["x"]}'

    r = await generate_summary(session, questions, llm_call=llm)
    assert r["total_score"] == 7.0  # 本地校正覆盖 LLM
    assert r["level"] == "高级"
    assert len(r["score_breakdown"]) == 1
    assert r["topic_analysis"] is not None


@pytest.mark.asyncio
async def test_generate_summary_llm_fails_falls_back_to_deterministic():
    session = {"position": "Java后端", "id": "s1"}
    questions = [_questions()[0]]

    async def llm(prompt, system=None):
        return "not json at all"

    r = await generate_summary(session, questions, llm_call=llm)
    assert r["total_score"] == 7.0
    assert r["score_breakdown"] and r["topic_analysis"]
