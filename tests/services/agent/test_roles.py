"""W1 Day 2：roles 单元测试（impl-spec v2 附录 E3）。

覆盖：
- 三角色输出模型 Schema（enum/minItems/minLength/范围/必填）
- strict + extra=forbid 行为（禁止类型强转与多余字段）
- 角色注册表与 system prompt
- prompt 构建器包含 schema 指令
- **防漂移一致性**：jsonschema 与 pydantic 对同一实例的接受/拒绝判定完全一致
  （单一事实来源 = Pydantic 模型，schema 由 model_json_schema() 生成）
"""

import pytest
from pydantic import BaseModel, ValidationError

from app.services.agent.roles import (
    EVALUATOR_ROLE,
    FOLLOWUPER_ROLE,
    QUESTIONER_ROLE,
    ROLES,
    Evaluation,
    FollowUp,
    Question,
    build_evaluation_prompt,
    build_followup_prompt,
    build_question_prompt,
)
from app.services.agent.structured_output import validate_against_schema


def test_question_schema_keywords():
    s = Question.model_json_schema()
    assert s["properties"]["difficulty"]["enum"] == ["easy", "medium", "hard"]
    assert s["properties"]["knowledge_tags"]["type"] == "array"
    assert s["properties"]["knowledge_tags"]["minItems"] == 1
    assert s["properties"]["question"]["minLength"] == 1
    assert "question" in s["required"]
    assert "difficulty" in s["required"]


def test_evaluation_schema_bounds():
    s = Evaluation.model_json_schema()
    p = s["properties"]["score"]
    assert p["type"] == "integer"
    assert p["minimum"] == 1
    assert p["maximum"] == 10
    assert s["properties"]["tags"]["minItems"] == 1


def test_followup_schema_enum():
    s = FollowUp.model_json_schema()
    assert s["properties"]["intent"]["enum"] == ["clarify", "probe", "boundary"]


def test_strict_mode_rejects_coercion_and_extra():
    with pytest.raises(ValidationError):
        # 多余字段（extra=forbid）
        Question.model_validate({
            "question": "q", "difficulty": "medium", "knowledge_tags": ["JVM"], "score": 1,
        })
    with pytest.raises(ValidationError):
        # 字符串 "7" 不得强转为 int（strict=True）
        Evaluation.model_validate({
            "score": "7", "comment": "c", "score_reason": "r", "tags": ["JVM"],
        })


def test_roles_registry():
    assert set(ROLES) == {"questioner", "followuper", "evaluator"}
    for r in ROLES.values():
        assert r.system_prompt.strip()
        assert issubclass(r.output_model, BaseModel)
    assert QUESTIONER_ROLE.label == "出题人"
    assert FOLLOWUPER_ROLE.label == "追问者"
    assert EVALUATOR_ROLE.label == "评估官"


def test_prompt_builders_include_schema_instruction():
    p = build_question_prompt("Java后端", 1, "medium")
    assert '"difficulty"' in p and '"knowledge_tags"' in p and '"question"' in p
    f = build_followup_prompt("为什么用 B+ 树？", "因为查询快")
    assert '"followup_question"' in f and '"intent"' in f
    e = build_evaluation_prompt("什么是事务？", "ACID", knowledge_context="参考资料...")
    assert '"score"' in e and '"score_reason"' in e and "参考资料" in e


@pytest.mark.parametrize(
    "model_cls, instance, expected",
    [
        # Question：合法 / 可选字段缺省 / 缺必填 / enum 错误 / 类型错误 / 多余字段
        (Question, {"question": "q", "difficulty": "medium",
                    "knowledge_tags": ["JVM"], "topic": "JVM", "category": "JVM"}, True),
        (Question, {"question": "q", "difficulty": "medium", "knowledge_tags": ["JVM"]}, True),
        (Question, {"difficulty": "medium", "knowledge_tags": ["JVM"]}, False),
        (Question, {"question": "q", "difficulty": "insane", "knowledge_tags": ["JVM"]}, False),
        (Question, {"question": "q", "difficulty": "medium", "knowledge_tags": "JVM"}, False),
        (Question, {"question": "q", "difficulty": "medium",
                    "knowledge_tags": ["JVM"], "extra": 1}, False),
        # Evaluation：合法 / 分数越界 / 空 comment
        (Evaluation, {"score": 7, "comment": "c", "score_reason": "r",
                      "reference_answer": "ref", "tags": ["JVM"]}, True),
        (Evaluation, {"score": 0, "comment": "c", "score_reason": "r", "tags": ["JVM"]}, False),
        (Evaluation, {"score": 7, "comment": "", "score_reason": "r", "tags": ["JVM"]}, False),
        # FollowUp：合法 / intent enum 错误
        (FollowUp, {"followup_question": "为什么？", "intent": "probe"}, True),
        (FollowUp, {"followup_question": "为什么？", "intent": "other"}, False),
    ],
)
def test_jsonschema_and_pydantic_agree(model_cls, instance, expected):
    """防漂移一致性：jsonschema 与 pydantic（strict）对同一实例判定必须一致。"""
    schema = model_cls.model_json_schema()
    js_ok = not validate_against_schema(instance, schema)
    try:
        model_cls.model_validate(instance)
        py_ok = True
    except ValidationError:
        py_ok = False
    assert js_ok == py_ok == expected
