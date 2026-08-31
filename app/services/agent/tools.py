"""确定性工具层（impl-spec v2 附录 F）。

对应关系（spec → 本模块）：
- 附录 F Tool 契约   → :class:`Tool`（name/description/input_schema/output_schema/handler/timeout_sec/error_policy）
- 附录 F ToolRegistry → :class:`ToolRegistry`（幂等 register / get / list / has / execute）
- 附录 F 内置工具表  → `make_*_tool` 工厂 + :func:`build_default_tools`（六个本地工具）
- 附录 G 降级矩阵    → 异常层级（见下），上层（orchestrator，W1 Day 4）据此执行 degrade/abort

设计约束（W1 Day 3）：
- 严格复用存量能力：RetrievalFacade（kb_retrieve）、TopicTracker（pick_next_topic）、
  ProfileStore（get_profile/update_profile）；不重复实现 RAG/TopicTracker/LLM。
- **Tool 不修改 AgentState、不负责状态转移、不调用 orchestrator**；只做 I/O + 规则计算。
- 校验复用 structured_output.validate_against_schema（jsonschema，单一校验实现）。
- 异常层级（上层捕获进降级矩阵）：
  - `ToolError` 基类
  - `ToolNotFoundError` / `ToolInputError` / `ToolOutputError` / `ToolTimeoutError` / `ToolExecutionError`
  - `ToolAbortError`：error_policy="abort" 的运行时失败（信号：触发 G7 逃生舱）
- error_policy：`degrade`（跳过并 trace 打标）/ `abort`（触发 G7），在 execute 中行为化。
"""

from __future__ import annotations

import asyncio
import copy
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from app.services.agent.profile_store import ProfileStore
from app.services.agent.state_machine import difficulty_delta
from app.services.agent.structured_output import validate_against_schema

# ---------------------------------------------------------------- 异常层级

class ToolError(Exception):
    """工具层错误基类：上层（orchestrator）捕获后进入降级矩阵。"""


class ToolNotFoundError(ToolError):
    """工具未注册。"""


class ToolInputError(ToolError):
    """输入不满足 input_schema（调用方错误）。"""


class ToolOutputError(ToolError):
    """handler 输出不满足 output_schema。"""


class ToolTimeoutError(ToolError):
    """执行超时（degrade 语义）。"""


class ToolExecutionError(ToolError):
    """handler 执行失败（degrade 语义）。"""


class ToolAbortError(ToolError):
    """error_policy="abort" 的运行时失败：信号 = 触发 G7 逃生舱。"""


# ---------------------------------------------------------------- Tool 契约

@dataclass(frozen=True)
class Tool:
    """附录 F Tool 契约。handler 为 async (**kwargs) -> dict（输出须满足 output_schema）。"""

    name: str
    description: str
    input_schema: dict
    output_schema: dict
    handler: Callable[..., Awaitable[dict]]
    timeout_sec: float = 5.0
    error_policy: str = "degrade"  # "degrade" | "abort"


# ---------------------------------------------------------------- 注册表

class ToolRegistry:
    """附录 F ToolRegistry：幂等注册 / 查询 / 带契约校验与超时的执行。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册（同名覆盖 = 幂等：重复注册同一工具不报错、不产生重复项）。"""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        try:
            return self._tools[name]
        except KeyError:
            raise ToolNotFoundError(f"tool not registered: {name}") from None

    def has(self, name: str) -> bool:
        return name in self._tools

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    async def execute(self, name: str, **kwargs: Any) -> dict:
        """执行工具：input 校验 → 超时执行 → output 校验。

        失败按 error_policy 行为化：
        - 运行时失败（handler 异常/超时）+ policy="abort" → `ToolAbortError`（信号 G7）
        - 运行时失败 + policy="degrade" → `ToolTimeoutError` / `ToolExecutionError`（信号：跳过+打标）
        - input/output schema 失败 → `ToolInputError` / `ToolOutputError`（恒为调用方/实现错误）
        """
        tool = self.get(name)

        input_errors = validate_against_schema(kwargs, tool.input_schema)
        if input_errors:
            raise ToolInputError(f"tool {name} input schema: {'; '.join(input_errors)}")

        try:
            output = await asyncio.wait_for(tool.handler(**kwargs), timeout=tool.timeout_sec)
        except TimeoutError:
            self._raise_failure(
                tool, ToolTimeoutError,
                f"tool {name} timed out after {tool.timeout_sec}s",
            )
        except ToolError:
            raise
        except Exception as e:  # noqa: BLE001 —— 统一包装进降级矩阵可捕获的层级
            self._raise_failure(tool, ToolExecutionError, f"tool {name} failed: {e}", cause=e)

        output_errors = validate_against_schema(output, tool.output_schema)
        if output_errors:
            raise ToolOutputError(f"tool {name} output schema: {'; '.join(output_errors)}")

        return output

    @staticmethod
    def _raise_failure(tool: Tool, exc_cls: type[ToolError], message: str, cause: Optional[BaseException] = None) -> None:
        """按 error_policy 行为化失败：abort → ToolAbortError（触发 G7 信号）。"""
        if tool.error_policy == "abort":
            raise ToolAbortError(message) from cause
        raise exc_cls(message) from cause


# ---------------------------------------------------------------- 内置工具（附录 F 工具表）

def _s(name: str, description: str, input_schema: dict, output_schema: dict,
       handler: Callable[..., Awaitable[dict]], timeout_sec: float, error_policy: str = "degrade") -> Tool:
    return Tool(
        name=name, description=description,
        input_schema=input_schema, output_schema=output_schema,
        handler=handler, timeout_sec=timeout_sec, error_policy=error_policy,
    )


def make_kb_retrieve_tool(facade: Any, timeout_sec: float = 10.0) -> Tool:
    """kb_retrieve：包 RetrievalFacade.retrieve（存量 RAG 管线，不重复实现）。"""

    async def handler(query: str, top_k: int = 5) -> dict:
        result = await facade.retrieve(query, top_k=top_k)
        chunks = [
            {"content": c.content, "file": c.source_file, "chunk_index": c.chunk_index, "score": c.score}
            for c in result.chunks
        ]
        sources = [
            {"file": s.file, "chunk_index": s.chunk_index, "score": s.score}
            for s in result.sources
        ]
        return {"chunks": chunks, "sources": sources}

    return _s(
        "kb_retrieve",
        "从知识库检索与问题相关的资料块与来源（RetrievalFacade：qr→hybrid→rerank→parent→dedup）。",
        {
            "type": "object",
            "required": ["query"],
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "top_k": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["chunks", "sources"],
            "properties": {
                "chunks": {"type": "array", "items": {
                    "type": "object",
                    "required": ["content", "file", "chunk_index", "score"],
                    "properties": {
                        "content": {"type": "string"},
                        "file": {"type": "string"},
                        "chunk_index": {"type": "integer"},
                        "score": {"type": "number"},
                    },
                }},
                "sources": {"type": "array", "items": {
                    "type": "object",
                    "required": ["file", "chunk_index", "score"],
                    "properties": {
                        "file": {"type": "string"},
                        "chunk_index": {"type": "integer"},
                        "score": {"type": "number"},
                    },
                }},
            },
            "additionalProperties": False,
        },
        handler, timeout_sec,
    )


def make_get_profile_tool(profile_store: ProfileStore, timeout_sec: float = 2.0) -> Tool:
    """get_profile：读取候选人画像（无记录返回空画像）。"""

    async def handler(user_id: str) -> dict:
        return profile_store.get(user_id)

    return _s(
        "get_profile",
        "读取候选人画像（薄弱点/等级/历史正确率/历史），Redis 不可用或新用户返回空画像。",
        {
            "type": "object",
            "required": ["user_id"],
            "properties": {"user_id": {"type": "string", "minLength": 1}},
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["weak_points", "level", "accuracy", "history"],
            "properties": {
                "weak_points": {"type": "array", "items": {"type": "string"}},
                "level": {"type": ["string", "null"]},
                "accuracy": {"type": ["number", "null"]},
                "history": {"type": "array", "items": {"type": "object"}},
            },
            "additionalProperties": False,
        },
        handler, timeout_sec,
    )


def make_update_profile_tool(profile_store: ProfileStore, timeout_sec: float = 2.0) -> Tool:
    """update_profile：画像增量更新（会话末批量写，G8 处调用）。"""

    async def handler(user_id: str, patch: dict) -> dict:
        profile_store.update(user_id, patch)
        return {"ok": True}

    return _s(
        "update_profile",
        "按 patch 增量更新候选人画像（深合并，不整体覆盖）。",
        {
            "type": "object",
            "required": ["user_id", "patch"],
            "properties": {
                "user_id": {"type": "string", "minLength": 1},
                "patch": {"type": "object"},
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
            "additionalProperties": False,
        },
        handler, timeout_sec,
    )


_MOCK_RESUME = {
    "projects": [
        {"name": "企业知识库问答系统", "technologies": ["RAG", "Rerank", "Redis", "FAISS"]},
        {"name": "电商订单中心", "technologies": ["Spring Boot", "MySQL", "Kafka"]},
    ],
    "technologies": ["RAG", "Rerank", "Redis", "FAISS", "Spring Boot", "MySQL", "Kafka"],
}


def make_mock_resume_tool(timeout_sec: float = 1.0) -> Tool:
    """mock_resume：非 RAG 外部工具（mock 简历库，确定性返回；W2 经 MCP 暴露）。"""

    async def handler(user_id: str) -> dict:
        return copy.deepcopy(_MOCK_RESUME)

    return _s(
        "mock_resume",
        "读取候选人的 mock 简历（项目与技术栈）。演示用确定性外部工具，W2 将经 MCP 暴露。",
        {
            "type": "object",
            "required": ["user_id"],
            "properties": {"user_id": {"type": "string"}},
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["projects", "technologies"],
            "properties": {
                "projects": {"type": "array", "items": {
                    "type": "object",
                    "required": ["name", "technologies"],
                    "properties": {
                        "name": {"type": "string"},
                        "technologies": {"type": "array", "items": {"type": "string"}},
                    },
                }},
                "technologies": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        },
        handler, timeout_sec,
    )


def make_pick_next_topic_tool(topic_tracker: Any, timeout_sec: float = 2.0) -> Tool:
    """pick_next_topic：确定性选下一主题（包 TopicTracker.get_next_suggestion，不重复实现）。

    注（与 spec F 工具表的对应）：输入采用 {session_id, position} 直接复用 TopicTracker
    （covered 由 InterviewStore 推导），输出追加 reason（来自 TopicTracker）。
    """

    async def handler(session_id: str, position: str) -> dict:
        suggestion = topic_tracker.get_next_suggestion(session_id, position)
        return {
            "topic": suggestion.get("topic"),
            "category": suggestion.get("category"),
            "reason": suggestion.get("reason", ""),
        }

    return _s(
        "pick_next_topic",
        "基于知识树覆盖率确定性推荐下一出题方向（TopicTracker）。",
        {
            "type": "object",
            "required": ["session_id", "position"],
            "properties": {
                "session_id": {"type": "string", "minLength": 1},
                "position": {"type": "string", "minLength": 1},
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["topic", "category"],
            "properties": {
                "topic": {"type": ["string", "null"]},
                "category": {"type": ["string", "null"]},
                "reason": {"type": "string"},
            },
            "additionalProperties": False,
        },
        handler, timeout_sec,
    )


def _rule_score_from_hit_ratio(hit_ratio: float) -> int:
    """G4-F 规则评分（spec 附录 B）：round(5 + 5 × hit_ratio)，hit_ratio 截断到 [0,1]。"""
    return round(5 + 5 * max(0.0, min(1.0, hit_ratio)))


def make_eval_rules_tool(timeout_sec: float = 1.0) -> Tool:
    """eval_rules：规则校验 + 参数汇算（G5 的载体，确定性纯函数）。

    - score 给定 → 直接用于难度决策；score 缺省但有 hit_ratio → 按 G4-F 规则汇算出分；
    - score 与 hit_ratio 均缺 → ToolInputError（调用方错误）。
    """

    async def handler(
        reask_allowed: bool,
        round: int,
        max_rounds: int,
        score: Optional[float] = None,
        hit_ratio: Optional[float] = None,
        user_ended: bool = False,
    ) -> dict:
        if score is None and hit_ratio is None:
            raise ToolInputError("eval_rules: 需要 score 或 hit_ratio 至少一个")
        effective = float(score) if score is not None else float(_rule_score_from_hit_ratio(hit_ratio))
        decision = difficulty_delta(effective, reask_allowed, round, max_rounds, user_ended)
        return {
            "action": decision["action"],
            "delta": decision["delta"],
            "weak_point": decision["weak_point"],
            "score": effective,
        }

    return _s(
        "eval_rules",
        "规则校验与参数汇算：评估分（或 hit_ratio 汇算分）→ 难度调整决策 {action, delta, weak_point}。",
        {
            "type": "object",
            "required": ["reask_allowed", "round", "max_rounds"],
            "properties": {
                "score": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
                "hit_ratio": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                "reask_allowed": {"type": "boolean"},
                "round": {"type": "integer", "minimum": 0},
                "max_rounds": {"type": "integer", "minimum": 1},
                "user_ended": {"type": "boolean"},
            },
            "additionalProperties": False,
        },
        {
            "type": "object",
            "required": ["action", "delta", "weak_point", "score"],
            "properties": {
                "action": {"type": "string", "enum": ["next", "reask", "end"]},
                "delta": {"type": "integer"},
                "weak_point": {"type": "boolean"},
                "score": {"type": "number"},
            },
            "additionalProperties": False,
        },
        handler, timeout_sec,
    )


def build_default_tools(
    facade: Any,
    topic_tracker: Any,
    profile_store: ProfileStore,
) -> dict[str, Tool]:
    """装配六个本地工具（显式 DI：RetrievalFacade / TopicTracker / ProfileStore）。"""
    tools = [
        make_kb_retrieve_tool(facade),
        make_get_profile_tool(profile_store),
        make_update_profile_tool(profile_store),
        make_mock_resume_tool(),
        make_pick_next_topic_tool(topic_tracker),
        make_eval_rules_tool(),
    ]
    return {t.name: t for t in tools}
