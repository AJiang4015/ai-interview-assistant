"""W1 Day 2：structured_output 单元测试（impl-spec v2 §4.1 / 附录 E3）。

先于实现编写（TDD）。覆盖：
- JSON 提取：合法 / 围栏（含无语言标记）/ 嵌套花括号 / 非法
- Schema 校验：缺字段 / 类型错误 / enum 错误
- 错误回填 prompt（含校验错误信息）
- 第 1/2/3 次尝试成功（attempts/retries 计数）
- 3 次均失败 → fallback 信号
- 全部使用 mock LLM，无真实调用
"""

import json

import pytest

from app.services.agent.roles import Evaluation, Question
from app.services.agent.structured_output import (
    MAX_ATTEMPTS_DEFAULT,
    StructuredResult,
    build_feedback_prompt,
    extract_json,
    generate_structured,
    validate_against_schema,
)

Q_SCHEMA = Question.model_json_schema()
E_SCHEMA = Evaluation.model_json_schema()

VALID_Q = {
    "question": "请讲一下 JVM 内存模型。",
    "difficulty": "medium",
    "knowledge_tags": ["JVM"],
    "topic": "JVM",
    "category": "JVM",
}


def _make_llm(script):
    """mock LLM：按脚本依次返回文本，并记录每次 prompt。"""
    calls = []

    async def llm(prompt, system=None):
        calls.append({"prompt": prompt, "system": system})
        return script.pop(0)

    return llm, calls


# ---------------------------------------------------------------- JSON 提取

def test_extract_json_plain():
    assert extract_json(json.dumps(VALID_Q, ensure_ascii=False)) == VALID_Q


def test_extract_json_fenced():
    text = "好的，答案如下：\n```json\n" + json.dumps(VALID_Q, ensure_ascii=False) + "\n```"
    assert extract_json(text) == VALID_Q


def test_extract_json_fenced_without_lang():
    text = "```\n" + json.dumps(VALID_Q, ensure_ascii=False) + "\n```"
    assert extract_json(text) == VALID_Q


def test_extract_json_nested_braces():
    q = dict(VALID_Q, question="请讲一下 JVM {堆} 与 {栈} 的区别？")
    assert extract_json(json.dumps(q, ensure_ascii=False)) == q


def test_extract_json_invalid_returns_none():
    assert extract_json("这不是 JSON") is None
    assert extract_json("") is None
    assert extract_json("[1, 2, 3]") is None  # 非 dict


# ---------------------------------------------------------------- Schema 校验

def test_validate_against_schema_ok():
    assert validate_against_schema(VALID_Q, Q_SCHEMA) == []


def test_validate_missing_field():
    errs = validate_against_schema({"difficulty": "medium", "knowledge_tags": ["JVM"]}, Q_SCHEMA)
    assert any("question" in e and "required" in e for e in errs)


def test_validate_type_error():
    errs = validate_against_schema(dict(VALID_Q, knowledge_tags="JVM"), Q_SCHEMA)
    assert any("array" in e for e in errs)


def test_validate_enum_error():
    errs = validate_against_schema(dict(VALID_Q, difficulty="insane"), Q_SCHEMA)
    assert any("one of" in e for e in errs)


# ---------------------------------------------------------------- 错误回填

def test_build_feedback_prompt_includes_errors():
    p = build_feedback_prompt("出题", ["$.difficulty: 'insane' is not one of ['easy','medium','hard']"], 2)
    assert "校验失败" in p
    assert "insane" in p
    assert "重新输出" in p
    assert p.startswith("出题")


# ---------------------------------------------------------------- 重试与 fallback（mock LLM）

@pytest.mark.asyncio
async def test_success_on_first_attempt():
    llm, calls = _make_llm([json.dumps(VALID_Q, ensure_ascii=False)])
    r = await generate_structured(llm, "出题", Q_SCHEMA, Question)
    assert r.ok and not r.fallback
    assert r.attempts == 1 and r.retries == 0
    assert isinstance(r.model, Question)
    assert r.model.question == VALID_Q["question"]
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_success_on_second_attempt_with_feedback():
    bad = '{"difficulty": "medium", "knowledge_tags": ["JVM"]}'  # 缺 question
    llm, calls = _make_llm([bad, json.dumps(VALID_Q, ensure_ascii=False)])
    r = await generate_structured(llm, "出题", Q_SCHEMA, Question)
    assert r.ok and r.attempts == 2 and r.retries == 1
    assert len(calls) == 2
    # 第二次 prompt 必须包含校验错误回填
    assert "校验失败" in calls[1]["prompt"]
    assert "question" in calls[1]["prompt"]


@pytest.mark.asyncio
async def test_success_on_third_attempt():
    bad = '{"question": "q", "difficulty": "insane", "knowledge_tags": ["JVM"]}'
    llm, calls = _make_llm([bad, bad, json.dumps(VALID_Q, ensure_ascii=False)])
    r = await generate_structured(llm, "出题", Q_SCHEMA, Question)
    assert r.ok and r.attempts == 3 and r.retries == 2
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_all_three_attempts_fail_fallback():
    bad = "完全不是 JSON"
    llm, calls = _make_llm([bad, bad, bad])
    r = await generate_structured(llm, "出题", Q_SCHEMA, Question)
    assert not r.ok and r.fallback
    assert r.attempts == MAX_ATTEMPTS_DEFAULT
    assert r.model is None and r.data is None
    assert r.errors  # 有明确错误信息供上层兜底
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_mixed_failures_fallback_signal():
    llm, calls = _make_llm([
        "x",  # 提取失败
        '{"question":"q","difficulty":"bad","knowledge_tags":[]}',  # enum + minItems 失败
        "y",  # 提取失败
    ])
    r = await generate_structured(llm, "出题", Q_SCHEMA, Question)
    assert not r.ok and r.fallback
    assert r.attempts == 3 and len(r.errors) >= 1


@pytest.mark.asyncio
async def test_fallback_on_evaluation_schema():
    # 首输出 score 为字符串（类型错误）→ 回填重试 2 次仍失败 → fallback
    llm, calls = _make_llm([
        '{"score": "7", "comment": "c", "score_reason": "r", "tags": ["t"]}',
        "bad",
        "bad",
    ])
    r = await generate_structured(llm, "评估", E_SCHEMA, Evaluation)
    assert not r.ok and r.fallback and r.attempts == 3


@pytest.mark.asyncio
async def test_retry_count_accuracy():
    """retries = attempts - 1，写入 trace 用。"""
    bad = "no json"
    llm, _ = _make_llm([bad, bad, json.dumps(VALID_Q, ensure_ascii=False)])
    r = await generate_structured(llm, "出题", Q_SCHEMA, Question)
    assert r.attempts == 3 and r.retries == 2
    llm2, _ = _make_llm([json.dumps(VALID_Q, ensure_ascii=False)])
    r2 = await generate_structured(llm2, "出题", Q_SCHEMA, Question)
    assert r2.attempts == 1 and r2.retries == 0
