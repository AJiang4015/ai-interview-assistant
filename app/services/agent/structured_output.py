"""结构化输出：JSON 提取 → jsonschema 校验 → 错误回填重试（impl-spec v2 §4.1 / 附录 E3）。

职责边界（防 schema 漂移，W1 Day 2 决策）：
- 本模块只负责「LLM 文本 → 结构化数据」的提取与**对外契约校验**（jsonschema）；
- Schema 一律来自 roles 内 Pydantic 模型的 `model_json_schema()`（单一事实来源），
  本模块不接受手工编写的第二套 schema；Pydantic 负责内部类型模型与 Schema 生成。
- 校验失败把错误信息**回填 prompt** 重试；总尝试上限 `max_attempts=3`
  （第 1 次为初始尝试，第 2/3 次为重试；`attempts` 记录总尝试次数，
  `retries = attempts - 1` 供 trace.retries 写入；与 EscapeHatchConfig.max_structured_retries=3 对齐）。
- 重试耗尽返回 `fallback=True` 明确信号，由上层（门禁 G1-F / G4-F）执行确定性兜底。
- **本模块不修改 AgentState、不调用 LLM**（LLM 由调用方以 `llm_call` 注入，便于 mock/单测）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

import jsonschema
from pydantic import BaseModel, ValidationError

MAX_ATTEMPTS_DEFAULT = 3
_MAX_FEEDBACK_ERRORS = 5


# ---------------------------------------------------------------- JSON 提取

def _extract_balanced(text: str, start: int) -> Optional[str]:
    """从 start（'{' 下标）起按花括号配平截取子串，支持嵌套（如题目含 {堆}）。"""
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def extract_json(text: str) -> Optional[dict]:
    """三段式提取：```json 围栏 → 全文 → 首个配平花括号块。返回 dict 或 None。"""
    candidates: list[str] = []

    # 1) 围栏块（含 ```json 与裸 ```）
    for m in re.finditer(r"```(?:json)?\s*(?P<body>.*?)```", text, re.DOTALL):
        body = m.group("body").strip()
        if body.startswith("{"):
            candidates.append(body)

    # 2) 全文
    stripped = text.strip()
    if stripped.startswith("{"):
        candidates.append(stripped)

    # 3) 首个 '{' 起的配平块（容错：输出前有叙述文本）
    start = text.find("{")
    if start != -1:
        balanced = _extract_balanced(text, start)
        if balanced:
            candidates.append(balanced)

    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


# ---------------------------------------------------------------- Schema 校验

def validate_against_schema(instance: dict, schema: dict) -> list[str]:
    """jsonschema 校验（对外契约），返回错误消息列表（空 = 通过）。

    校验器按 schema 声明的 draft 自动选择（pydantic 2 默认 draft 2020-12）。
    错误最多返回 `_MAX_FEEDBACK_ERRORS` 条，供 prompt 回填。
    """
    validator_cls = jsonschema.validators.validator_for(schema)
    errors = sorted(
        validator_cls(schema).iter_errors(instance),
        key=lambda e: list(e.absolute_path),
    )
    return [
        f"{e.json_path or '$'}: {e.message}"
        for e in errors[:_MAX_FEEDBACK_ERRORS]
    ]


def build_feedback_prompt(original_prompt: str, errors: list[str], attempt: int) -> str:
    """把校验错误回填进 prompt（spec §4.1：校验失败时把错误信息拼回 prompt 重试）。"""
    parts = [original_prompt.rstrip()]
    parts.append("\n\n【上一次输出校验失败，请修正后重新输出】")
    parts.append(f"校验错误（第 {attempt} 次尝试，仅需修正以下问题）：")
    parts.extend(f"- {err}" for err in errors[:_MAX_FEEDBACK_ERRORS])
    parts.append("请仅输出符合给定 JSON Schema 的 JSON，不要包含其他内容。")
    return "\n".join(parts)


# ---------------------------------------------------------------- 主流程

@dataclass
class StructuredResult:
    """结构化输出结果。fallback=True 表示重试耗尽，需要上层确定性兜底。"""

    ok: bool
    data: Optional[dict] = None
    model: Optional[Any] = None  # Pydantic 类型实例（ok 时）
    attempts: int = 0
    errors: list[str] = field(default_factory=list)
    fallback: bool = False

    @property
    def retries(self) -> int:
        """重试次数 = 尝试次数 - 1（写 trace.retries 用）。"""
        return max(0, self.attempts - 1)


async def generate_structured(
    llm_call: Callable[..., Awaitable[str]],
    prompt: str,
    schema: dict,
    model_cls: type[BaseModel],
    max_attempts: int = MAX_ATTEMPTS_DEFAULT,
    system: Optional[str] = None,
) -> StructuredResult:
    """一次结构化生成：提取 → 校验 → 回填重试（≤max_attempts 次总尝试）。

    Args:
        llm_call: `async (prompt, system=None) -> str`，由调用方注入（mock 或真实 LLM）。
        prompt: 初始 user prompt（由 roles 构建，含 schema 指令）。
        schema: 对外契约 JSON Schema（必须来自 model_cls.model_json_schema()）。
        model_cls: Pydantic 模型（成功时用于 typed 解析）。
        max_attempts: 总尝试次数上限（默认 3）。
        system: 可选 system prompt（角色）。

    Returns:
        StructuredResult：ok=False 且 fallback=True 表示重试耗尽，上层走确定性兜底。
    """
    current_prompt = prompt
    errors: list[str] = []

    for attempt in range(1, max_attempts + 1):
        text = await llm_call(current_prompt, system)

        data = extract_json(text)
        if data is None:
            errors = [f"第 {attempt} 次输出无法提取 JSON（无合法对象）"]
            current_prompt = build_feedback_prompt(prompt, errors, attempt)
            continue

        errors = validate_against_schema(data, schema)
        if errors:
            current_prompt = build_feedback_prompt(prompt, errors, attempt)
            continue

        try:
            obj = model_cls.model_validate(data)
        except ValidationError as e:
            # 防御分支：schema 由 model 生成且双方均 strict，理论不应触发；
            # 触发则视为校验失败进入回填重试。
            errors = [f"pydantic 解析失败（防漂移设计下不应发生）: {e}"]
            current_prompt = build_feedback_prompt(prompt, errors, attempt)
            continue

        return StructuredResult(ok=True, data=data, model=obj, attempts=attempt)

    return StructuredResult(
        ok=False, attempts=max_attempts, errors=errors, fallback=True
    )
