"""Agent 角色定义（impl-spec v2 附录 E3）。

职责划分（防 schema 漂移，W1 Day 2 决策，对应 spec E3「Schema 定义放在 roles.py」）：
- **内部类型模型（Pydantic）= 单一事实来源**：Question / FollowUp / Evaluation。
- **对外 Schema（JSON Schema）= 由内部模型 `model_json_schema()` 生成**，绝不手工维护第二套。
- 校验职责：structured_output 用 jsonschema 对 LLM 输出做「对外契约校验 + 错误回填」；
  Pydantic 负责「内部类型模型 + Schema 生成」。二者通过 `strict=True` + `extra="forbid"`
  保证对同一实例的接受/拒绝判定完全一致（有防漂移单测 test_roles.py）。
- 输出 Schema 在 prompt 中以 `model_json_schema()` 文本形式作为接口契约下发（JSON Schema 即契约，JD1-11）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------- 输出模型（内部类型模型）

class Question(BaseModel):
    """出题人输出（附录 E3 出题人 Schema）。"""

    model_config = ConfigDict(strict=True, extra="forbid")

    question: str = Field(..., min_length=1, description="题目内容")
    difficulty: Literal["easy", "medium", "hard"] = Field(..., description="难度")
    knowledge_tags: list[str] = Field(..., min_length=1, description="知识点标签")
    topic: str = Field(default="", description="知识树 topic")
    category: str = Field(default="", description="知识树 category")


class FollowUp(BaseModel):
    """追问者输出（附录 E3 追问者 Schema）。"""

    model_config = ConfigDict(strict=True, extra="forbid")

    followup_question: str = Field(..., min_length=1, description="追问内容")
    intent: Literal["clarify", "probe", "boundary"] = Field(..., description="追问意图")


class Evaluation(BaseModel):
    """评估官输出（附录 E3 评估官 Schema）。"""

    model_config = ConfigDict(strict=True, extra="forbid")

    score: int = Field(..., ge=1, le=10, description="1-10 整数评分")
    comment: str = Field(..., min_length=1, description="一句话评价摘要")
    score_reason: str = Field(..., min_length=1, description="评分原因")
    reference_answer: str = Field(default="", description="参考答案要点")
    tags: list[str] = Field(..., min_length=1, description="涉及知识点")


# ---------------------------------------------------------------- System prompt（按阶段注入）

QUESTIONER_SYSTEM = """你是一位专业的 Java/后端技术面试官，负责出题。
职责：
1. 根据岗位方向、轮次与目标难度，出一道高质量技术面试题（覆盖技术知识点、项目经验或系统设计）。
2. 结合注入的领域知识（知识库检索块）与候选人画像（薄弱点/历史表现）出题。
3. 只输出符合给定 JSON Schema 的 JSON，不要输出任何其他内容。"""

FOLLOWUPER_SYSTEM = """你是一位追问的面试官，基于本题与面试者的回答提出一个追问。
追问意图：
- clarify：澄清含糊表述
- probe：深挖底层原理
- boundary：考察方案边界与扩展性
要求：追问必须基于面试者上一回答，不能自问自答；只输出符合给定 JSON Schema 的 JSON。"""

EVALUATOR_SYSTEM = """你是一位公正的评估官，评价面试者的回答。
评分标准：
- 9-10：回答准确完整，深度超出预期
- 7-8：回答正确，覆盖主要知识点，略有不足
- 5-6：回答基本正确，但不够深入或遗漏关键点
- 3-4：回答有明显错误或遗漏
- 1-2：回答完全不对或避而不答
要求：只输出符合给定 JSON Schema 的 JSON，不要输出任何其他内容。"""


# ---------------------------------------------------------------- 输入上下文构建（按阶段注入）

def _schema_instruction(model_cls: type[BaseModel]) -> str:
    """把模型生成的 JSON Schema 作为接口契约文本下发到 prompt。"""
    schema = model_cls.model_json_schema()
    return (
        "\n请严格按以下 JSON Schema 输出（不要包含其他内容）：\n"
        + json.dumps(schema, ensure_ascii=False, indent=2)
    )


def build_question_prompt(
    position: str,
    round_num: int,
    difficulty: str,
    knowledge_context: str = "",
    coverage_summary: str = "",
    profile_summary: str = "",
    suggested_topic: str = "",
) -> str:
    """出题人输入上下文（附录 E3：KG/RAG 检索块 + 画像 + 难度历史）。"""
    parts = [f"岗位方向：{position}", f"当前第 {round_num} 题", f"目标难度：{difficulty}"]
    if knowledge_context:
        parts.append(f"\n【知识库参考】\n{knowledge_context}")
    if coverage_summary:
        parts.append(f"\n【覆盖情况】\n{coverage_summary}")
    if profile_summary:
        parts.append(f"\n【候选人画像】\n{profile_summary}")
    if suggested_topic:
        parts.append(f"\n【建议出题方向】\n{suggested_topic}")
    return "\n".join(parts) + _schema_instruction(Question)


def build_followup_prompt(
    question: str,
    answer: str,
    evaluation_summary: str = "",
) -> str:
    """追问者输入上下文（附录 E3：本题 + 用户回答 + 评估要点）。"""
    parts = [f"本题：{question}", f"\n面试者的回答：\n{answer}"]
    if evaluation_summary:
        parts.append(f"\n【评估要点】\n{evaluation_summary}")
    return "\n".join(parts) + _schema_instruction(FollowUp)


def build_evaluation_prompt(
    question: str,
    answer: str,
    knowledge_context: str = "",
    reference_hint: str = "",
) -> str:
    """评估官输入上下文（附录 E3：题目 + 回答 + 参考要点）。"""
    parts = [f"题目：{question}", f"\n面试者的回答：\n{answer}"]
    if knowledge_context:
        parts.append(f"\n【参考资料】\n{knowledge_context}")
    if reference_hint:
        parts.append(f"\n【期望考察知识点】\n{reference_hint}")
    return "\n".join(parts) + _schema_instruction(Evaluation)


# ---------------------------------------------------------------- 角色注册表

@dataclass(frozen=True)
class Role:
    """角色定义：name / 中文 label / system prompt / 输出模型（schema 事实来源）。"""

    name: str
    label: str
    system_prompt: str
    output_model: type[BaseModel]


QUESTIONER_ROLE = Role("questioner", "出题人", QUESTIONER_SYSTEM, Question)
FOLLOWUPER_ROLE = Role("followuper", "追问者", FOLLOWUPER_SYSTEM, FollowUp)
EVALUATOR_ROLE = Role("evaluator", "评估官", EVALUATOR_SYSTEM, Evaluation)

ROLES: dict[str, Role] = {
    r.name: r for r in (QUESTIONER_ROLE, FOLLOWUPER_ROLE, EVALUATOR_ROLE)
}
