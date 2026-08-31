"""确定性兜底动作（impl-spec v2 附录 D fallback.py；附录 B G1-F / G4-F；附录 G G8）。

对应关系（spec → 本模块）：
- G1-F 出题兜底      → :func:`fallback_question`（重试耗尽后的确定性模板题）
- G4-F 评估兜底      → :func:`rule_score`（短答记 2 分；否则 round(5+5×命中率)）
- G8 报告兜底        → :func:`deterministic_summary`（确定性摘要，legacy report 形状兼容）
- SUMMARIZING 报告   → :func:`generate_summary`（LLM 尝试 + 本地校正；失败 → deterministic）

约束：
- 本模块为确定性代码，不调用 LLM（generate_summary 的 llm_call 由调用方注入，失败即兜底）。
- 统计一律过滤 `source='followup'`（F7/F8/F9 冻结：追问不污染主问题统计）。
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable, Optional

from app.services.agent.structured_output import extract_json


# ---------------------------------------------------------------- G1-F 出题兜底

def fallback_question(suggestion: dict, difficulty: str) -> dict:
    """G1-F：出题结构化输出重试耗尽后的确定性模板题（优先使用知识树建议）。"""
    topic = suggestion.get("topic") or ""
    category = suggestion.get("category") or ""
    if topic:
        question_text = f"请系统性地介绍「{topic}」相关的基础概念、核心原理与常见实现。"
    else:
        question_text = "请介绍 Java 后端开发中最熟悉的一个知识点，并说明其核心原理。"
    return {
        "question": question_text,
        "difficulty": difficulty if difficulty in ("easy", "medium", "hard") else "medium",
        "knowledge_tags": [topic] if topic else ["通用"],
        "topic": topic,
        "category": category,
        "source": "llm",
        "fallback": True,
    }


# ---------------------------------------------------------------- G4-F 评估兜底

def rule_score(question: str, answer: str, expected_tags: list[str]) -> dict:
    """G4-F：评估结构化输出重试耗尽后的确定性规则评分（spec 附录 B G4-F）。

    - answer < 20 字符 → score=2（答不上来）
    - 否则 hit_ratio = 命中期望知识点数 / 期望总数，score = round(5 + 5 × hit_ratio)
    """
    text = (answer or "").strip()
    total = max(len(expected_tags), 1)
    if len(text) < 20:
        hit = 0
        score = 2
    else:
        hit = sum(1 for t in expected_tags if t and t.lower() in text.lower())
        score = round(5 + 5 * (hit / total))
    return {
        "score": score,
        "comment": "规则兜底评分（评估节点重试耗尽）",
        "score_reason": f"命中期望知识点 {hit}/{total}",
        "reference_answer": "",
        "tags": list(expected_tags),
        "fallback": "eval_rule",
    }


# ---------------------------------------------------------------- G8 报告兜底

def deterministic_summary(session: dict, questions: list[dict]) -> dict:
    """G8：确定性摘要（legacy 报告形状兼容；过滤 source='followup'）。

    字段对齐 legacy report：total_score / score_breakdown / knowledge_analysis /
    improvement_suggestions / level / topic_analysis / recommended_study。
    """
    main_qs = [
        q for q in questions
        if q.get("source") != "followup" and q.get("answer")
    ]
    if not main_qs:
        return {
            "total_score": 0, "level": "未知", "score_breakdown": [],
            "knowledge_analysis": {"strengths": [], "weaknesses": []},
            "improvement_suggestions": ["无足够数据"],
            "topic_analysis": [], "recommended_study": [],
        }

    avg = round(sum(q.get("score") or 0 for q in main_qs) / len(main_qs), 1)

    breakdown = []
    for q in sorted(main_qs, key=lambda x: x["round"]):
        ev = q.get("evaluation") or {}
        breakdown.append({
            "round": q["round"], "question": q["question"], "score": q.get("score") or 0,
            "tags": ev.get("tags", []), "comment": ev.get("comment", ""),
            "score_reason": ev.get("score_reason", ""), "reference_answer": ev.get("reference_answer", ""),
            "topic": q.get("topic", "") or "", "category": q.get("category", "") or "",
        })

    category_scores: dict[str, list[float]] = {}
    for q in main_qs:
        cat = q.get("category") or "其他"
        category_scores.setdefault(cat, []).append(q.get("score") or 0)
    topic_analysis = []
    for cat, scores in category_scores.items():
        c_avg = round(sum(scores) / len(scores), 1)
        status = "strong" if c_avg >= 7 else ("moderate" if c_avg >= 5 else "weak")
        topic_analysis.append({
            "category": cat, "topics_covered": len(scores), "avg_score": c_avg, "status": status,
        })
    topic_analysis.sort(key=lambda c: (c["avg_score"], -c["topics_covered"]))

    strengths = [
        t for q in main_qs if (q.get("score") or 0) >= 7
        for t in (q.get("evaluation") or {}).get("tags", [])
    ]
    weaknesses = [
        t for q in main_qs if (q.get("score") or 0) < 5
        for t in (q.get("evaluation") or {}).get("tags", [])
    ]
    recommended = []
    for ta in topic_analysis:
        if ta["status"] == "weak":
            recommended.append({
                "category": ta["category"], "priority": "high",
                "reason": f"得分偏低（{ta['avg_score']}分），建议重点复习",
            })
        elif ta["status"] == "moderate":
            recommended.append({
                "category": ta["category"], "priority": "medium",
                "reason": f"基础尚可（{ta['avg_score']}分），建议补充深度",
            })

    level = "高级" if avg >= 8 else ("中级" if avg >= 6 else "初级")

    return {
        "total_score": avg,
        "level": level,
        "score_breakdown": breakdown,
        "knowledge_analysis": {
            "strengths": list(dict.fromkeys(strengths)),
            "weaknesses": list(dict.fromkeys(weaknesses)),
        },
        "improvement_suggestions": [r["reason"] for r in recommended] or ["整体表现一般，建议按薄弱方向系统复习"],
        "topic_analysis": topic_analysis,
        "recommended_study": recommended,
    }


REPORT_PROMPT = """请根据以下面试记录生成面试报告。

岗位：{position}
总题数：{total_rounds}
总分：{total_score}

各题详情：
{questions_detail}

请按以下 JSON 格式输出（不要包含其他内容）：
{{
    "score_breakdown": [
        {{"round": 1, "question": "完整题目", "score": 7, "tags": ["知识点1"], "comment": "一句话摘要", "score_reason": "评分原因", "reference_answer": "参考答案"}}
    ],
    "total_score": <1-10 的浮点数>,
    "knowledge_analysis": {{"strengths": ["掌握较好的知识点"], "weaknesses": ["薄弱知识点"]}},
    "improvement_suggestions": ["具体改进建议1", "具体改进建议2"],
    "level": "初级/中级/高级"
}}

等级标准：8 分以上高级；6-7.9 中级；6 分以下初级。"""


async def generate_summary(
    session: dict,
    questions: list[dict],
    llm_call: Optional[Callable[..., Awaitable[str]]] = None,
) -> dict:
    """SUMMARIZING 报告生成（OPEN-6 冻结）：LLM 尝试 + 本地校正；任何失败 → 确定性摘要。

    - 确定性部分（total_score / topic_analysis / recommended_study / score_breakdown 兜底）
      一律由 :func:`deterministic_summary` 提供并覆盖 LLM 输出，防止 LLM 失真。
    - LLM 负责 level / knowledge_analysis / improvement_suggestions 等自然语言部分。
    """
    deterministic = deterministic_summary(session, questions)
    if llm_call is None:
        return deterministic

    main_qs = [q for q in questions if q.get("source") != "followup" and q.get("answer")]
    if not main_qs:
        return deterministic

    details = [
        {
            "round": q["round"], "question": q["question"], "score": q.get("score") or 0,
            "comment": (q.get("evaluation") or {}).get("comment", ""),
            "tags": (q.get("evaluation") or {}).get("tags", []),
        }
        for q in main_qs
    ]
    prompt = REPORT_PROMPT.format(
        position=session.get("position", ""),
        total_rounds=len(main_qs),
        total_score=deterministic["total_score"],
        questions_detail=json.dumps(details, ensure_ascii=False),
    )
    try:
        text = await llm_call(prompt)
        parsed = extract_json(text)
    except Exception:
        return deterministic
    if not isinstance(parsed, dict):
        return deterministic

    # 本地校正（对齐 legacy _generate_report 的本地覆盖策略）
    parsed["total_score"] = deterministic["total_score"]
    parsed["topic_analysis"] = deterministic["topic_analysis"]
    parsed["recommended_study"] = deterministic["recommended_study"]
    parsed.setdefault("score_breakdown", deterministic["score_breakdown"])
    parsed.setdefault("knowledge_analysis", deterministic["knowledge_analysis"])
    parsed.setdefault("improvement_suggestions", deterministic["improvement_suggestions"])
    parsed.setdefault("level", deterministic["level"])
    return parsed
