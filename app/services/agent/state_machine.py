"""确定性编排状态机（impl-spec v2 附录 A / B / C）。

对应关系（spec → 本模块）：
- 附录 A1 AgentState      → :class:`AgentState`
- 附录 A2 AgentEvent      → :class:`AgentEvent`（行 14「（内部）」→ `AgentEvent.SUMMARIZE_DONE`）
- 附录 A3 转移表          → :data:`TRANSITIONS`（14 行：行 12 展开 4 来源、行 13 展开全部非终态、行 14 内部事件）
- 附录 A6 answer 契约映射 → 由 orchestrator（W1 Day 4）消费 guard_payload，本模块只保证转移合法性
- 附录 B 门禁 G0..G9      → 门禁名对照：
    G0→g0_start, G1→g1_question, G1-F→g1_fallback, G1-f→g1_followup,
    G2→g2_answer, G4→g4_eval, G4-F→g4_fallback, G5→g5_next/g5_reask/g5_end,
    G6→g6_end, G7→g7_escape, G8→g8_summary, G9→g9_followup_trigger
- 附录 C 全局逃生舱      → :class:`EscapeHatch` / :class:`EscapeHatchConfig` / :class:`EscapeHatchContext`

设计约束：
- 纯函数式引擎：不持有会话数据、不调用 LLM、不导入 settings（运行时配置经
  `EscapeHatchConfig.from_settings()` 注入），保证单测可脱离 .env 运行。
- 非法转移一律返回 `StepResult(allowed=False, reason="illegal_transition")`，不抛异常。
- 守卫按表序求值；同事件多行由守卫互斥保证确定性（附录 A3 注）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional, Sequence

# ---------------------------------------------------------------- 状态与事件

_DIFFICULTY_VALUES = ("easy", "medium", "hard")
# G2 回答长度上限（默认，运行期由 settings.agent_max_answer_chars 覆盖）
_DEFAULT_MAX_ANSWER_CHARS = 2000
# G9 模糊作答启发式阈值（spec 附录 B G9：answer 长度 < 200 触发追问）
_FOLLOWUP_AMBIGUITY_CHARS = 200


class AgentState(Enum):
    """spec 附录 A1 状态集合。"""

    INIT = "init"
    QUESTIONING = "questioning"
    AWAITING_ANSWER = "awaiting_answer"
    FOLLOWUP = "followup"
    EVALUATING = "evaluating"
    DIFFICULTY_ADJ = "difficulty_adj"
    SUMMARIZING = "summarizing"
    END = "end"


class AgentEvent(Enum):
    """spec 附录 A2 事件集合。"""

    START = "start"
    QUESTION_READY = "question_ready"
    QUESTION_FALLBACK = "question_fallback"
    ANSWER_SUBMITTED = "answer_submitted"
    FOLLOWUP_READY = "followup_ready"
    EVALUATION_DONE = "evaluation_done"
    EVALUATION_FALLBACK = "evaluation_fallback"
    DIFFICULTY_ADJUSTED = "difficulty_adjusted"
    END_REQUESTED = "end_requested"
    FORCE_END = "force_end"
    # 内部事件：spec 附录 A3 行 14「（内部）」——SUMMARIZING 完成后进入 END
    SUMMARIZE_DONE = "_summarize_done"


# ---------------------------------------------------------------- 门禁

@dataclass
class GuardResult:
    """门禁求值结果。"""

    passes: bool
    reason: str = ""
    payload: Optional[dict] = None


GateFn = Callable[["GateContext"], GuardResult]


@dataclass
class GateContext:
    """门禁求值上下文：仅承载门禁所需的确定性事实，不含业务会话对象。

    - output：候选节点输出（G1/G1-F/G1-f/G4/G4-F 校验用）
    - 其余字段对应各门禁所需事实（position/answer_len/score/round 等）
    """

    state: AgentState
    event: AgentEvent
    output: Optional[dict] = None
    # G0
    position: Optional[str] = None
    session_active: bool = False
    # G2 / G9
    answer_len: int = 0
    max_answer_chars: int = _DEFAULT_MAX_ANSWER_CHARS
    followup_enabled: bool = True
    followup_budget: int = 0
    # G1 去重
    asked_set: Optional[frozenset] = None
    # G4 / G5
    score: Optional[float] = None
    round: int = 0
    max_rounds: int = 15
    reask_allowed: bool = False
    reask_count: int = 0
    max_reask: int = 1
    user_ended: bool = False
    # G7 / G8
    force_end: bool = False
    summary_ready: bool = False
    answered_rounds: int = 0


# --- 门禁实现（spec 附录 B）---

def g0_start(ctx: GateContext) -> GuardResult:
    """G0 START_GATE：position 非空且会话未在活动态。"""
    if not (ctx.position and ctx.position.strip()):
        return GuardResult(False, "position_empty")
    if ctx.session_active:
        return GuardResult(False, "session_active")
    return GuardResult(True)


def g1_question(ctx: GateContext) -> GuardResult:
    """G1 QUESTION_GATE：Question Schema 确定性部分（非空/enum/去重）。

    完整 jsonschema 校验由 structured_output（W1 Day 2）在节点输出侧完成，
    此处只做门禁需要的确定性判定。
    """
    out = ctx.output or {}
    q = out.get("question")
    if not (isinstance(q, str) and q.strip()):
        return GuardResult(False, "question_empty")
    if out.get("difficulty") not in _DIFFICULTY_VALUES:
        return GuardResult(False, "difficulty_invalid")
    tags = out.get("knowledge_tags")
    if not (isinstance(tags, list) and tags):
        return GuardResult(False, "knowledge_tags_empty")
    if ctx.asked_set is not None and hash(q) in ctx.asked_set:
        return GuardResult(False, "question_duplicate")
    return GuardResult(True)


def g1_fallback(ctx: GateContext) -> GuardResult:
    """G1-F QUESTION_FALLBACK：出题重试耗尽后的确定性兜底题。"""
    out = ctx.output or {}
    q = out.get("question")
    if isinstance(q, str) and q.strip():
        return GuardResult(True)
    return GuardResult(False, "fallback_question_empty")


def g1_followup(ctx: GateContext) -> GuardResult:
    """G1-f FOLLOWUP_QUESTION_GATE：追问输出非空。"""
    out = ctx.output or {}
    q = out.get("followup_question")
    if isinstance(q, str) and q.strip():
        return GuardResult(True)
    return GuardResult(False, "followup_question_empty")


def g2_answer(ctx: GateContext) -> GuardResult:
    """G2 ANSWER_GATE：回答非空且不超长。"""
    if ctx.answer_len <= 0:
        return GuardResult(False, "answer_empty")
    if ctx.answer_len > ctx.max_answer_chars:
        return GuardResult(False, "answer_too_long")
    return GuardResult(True)


def g9_followup_trigger(ctx: GateContext) -> GuardResult:
    """G9 FOLLOWUP_TRIGGER_GATE：开启 && 预算>0 && 短答（模糊作答启发式）。"""
    if not ctx.followup_enabled:
        return GuardResult(False, "followup_disabled")
    if ctx.followup_budget <= 0:
        return GuardResult(False, "followup_budget_exhausted")
    if ctx.answer_len >= _FOLLOWUP_AMBIGUITY_CHARS:
        return GuardResult(False, "answer_not_ambiguous")
    return GuardResult(True)


def g4_eval(ctx: GateContext) -> GuardResult:
    """G4 EVAL_GATE：Evaluation Schema 确定性部分（score int 1-10/字段非空）。"""
    out = ctx.output or {}
    score = out.get("score")
    if not isinstance(score, int) or not (1 <= score <= 10):
        return GuardResult(False, "score_invalid")
    if not (isinstance(out.get("comment"), str) and out["comment"].strip()):
        return GuardResult(False, "comment_empty")
    if not (isinstance(out.get("score_reason"), str) and out["score_reason"].strip()):
        return GuardResult(False, "score_reason_empty")
    tags = out.get("tags")
    if not (isinstance(tags, list) and tags):
        return GuardResult(False, "tags_empty")
    return GuardResult(True)


def g4_fallback(ctx: GateContext) -> GuardResult:
    """G4-F EVAL_FALLBACK：兜底规则分（int 1-10）放行。"""
    score = (ctx.output or {}).get("score")
    if isinstance(score, int) and 1 <= score <= 10:
        return GuardResult(True)
    return GuardResult(False, "fallback_score_invalid")


def _difficulty_decision(ctx: GateContext) -> dict:
    """G5 难度调整表求值（spec 附录 B G5）。返回 {action, delta, weak_point}。"""
    return difficulty_delta(
        ctx.score, ctx.reask_allowed, ctx.round, ctx.max_rounds, ctx.user_ended
    )


def g5_next(ctx: GateContext) -> GuardResult:
    """G5-N：action==next（下一知识点）。"""
    d = _difficulty_decision(ctx)
    if d["action"] == "next":
        return GuardResult(True, payload=d)
    return GuardResult(False, "action_is_next")


def g5_reask(ctx: GateContext) -> GuardResult:
    """G5-R：action==reask（同知识点降难度重问）。"""
    d = _difficulty_decision(ctx)
    if d["action"] == "reask":
        return GuardResult(True, payload=d)
    return GuardResult(False, "action_is_reask")


def g5_end(ctx: GateContext) -> GuardResult:
    """G5-E：action==end（轮数耗尽/用户结束）。"""
    d = _difficulty_decision(ctx)
    if d["action"] == "end":
        return GuardResult(True, payload=d)
    return GuardResult(False, "action_is_end")


def g6_end(ctx: GateContext) -> GuardResult:
    """G6 END_GATE：END_REQUESTED 由转移表限定来源状态，此处放行。"""
    return GuardResult(True)


def g7_escape(ctx: GateContext) -> GuardResult:
    """G7 ESCAPE_GATE：FORCE_END 必须由逃生舱触发（ctx.force_end=True）。"""
    if ctx.force_end:
        return GuardResult(True)
    return GuardResult(False, "force_end_not_triggered")


def g8_summary(ctx: GateContext) -> GuardResult:
    """G8 SUMMARY_GATE：已答 >=1 轮，或由 G6/G7 进入（summary_ready）。"""
    if ctx.answered_rounds >= 1 or ctx.summary_ready:
        return GuardResult(True)
    return GuardResult(False, "no_data_to_summarize")


DEFAULT_GATES: dict[str, GateFn] = {
    "g0_start": g0_start,
    "g1_question": g1_question,
    "g1_fallback": g1_fallback,
    "g1_followup": g1_followup,
    "g2_answer": g2_answer,
    "g9_followup_trigger": g9_followup_trigger,
    "g4_eval": g4_eval,
    "g4_fallback": g4_fallback,
    "g5_next": g5_next,
    "g5_reask": g5_reask,
    "g5_end": g5_end,
    "g6_end": g6_end,
    "g7_escape": g7_escape,
    "g8_summary": g8_summary,
}


def difficulty_delta(
    score: Optional[float],
    reask_allowed: bool,
    round_num: int,
    max_rounds: int,
    user_ended: bool,
) -> dict:
    """spec 附录 B G5 难度调整表（确定性，纯函数）。

    返回 {"action": "next"|"reask"|"end", "delta": int, "weak_point": bool}
    - end 优先（轮数耗尽或用户结束，无论分数）
    - score None（防御分支）→ end，避免无分情况下卡死
    """
    if user_ended or round_num >= max_rounds or score is None:
        return {"action": "end", "delta": 0, "weak_point": False}
    if score >= 8:
        return {"action": "next", "delta": 1, "weak_point": False}
    if score >= 5:
        return {"action": "next", "delta": 0, "weak_point": False}
    if reask_allowed:
        return {"action": "reask", "delta": -1, "weak_point": False}
    return {"action": "next", "delta": 0, "weak_point": True}


# ---------------------------------------------------------------- 转移表

@dataclass(frozen=True)
class Transition:
    """spec 附录 A3 转移表一行。guards 为 AND 语义，按表序求值。"""

    from_state: AgentState
    event: AgentEvent
    guards: tuple[str, ...]
    to_state: AgentState
    action: Optional[str] = None


def _end_requested_rows():
    """行 12：END_REQUESTED，来源 = 4 个可中断状态。"""
    return tuple(
        Transition(s, AgentEvent.END_REQUESTED, ("g6_end",), AgentState.SUMMARIZING,
                   action="partial_summary")
        for s in (AgentState.QUESTIONING, AgentState.AWAITING_ANSWER,
                  AgentState.FOLLOWUP, AgentState.EVALUATING)
    )


def _force_end_rows():
    """行 13：FORCE_END，来源 = 任意非终态（除 END 外全部，含 SUMMARIZING 幂等）。"""
    return tuple(
        Transition(s, AgentEvent.FORCE_END, ("g7_escape",), AgentState.SUMMARIZING,
                   action="escape_summarize")
        for s in AgentState
        if s is not AgentState.END
    )


TRANSITIONS: tuple[Transition, ...] = (
    # 行 1
    Transition(AgentState.INIT, AgentEvent.START, ("g0_start",),
               AgentState.QUESTIONING, action="build_context"),
    # 行 2 / 行 3
    Transition(AgentState.QUESTIONING, AgentEvent.QUESTION_READY, ("g1_question",),
               AgentState.AWAITING_ANSWER, action="persist_question"),
    Transition(AgentState.QUESTIONING, AgentEvent.QUESTION_FALLBACK, ("g1_fallback",),
               AgentState.AWAITING_ANSWER, action="persist_fallback_question"),
    # 行 4 / 行 5（互斥：G9 命中→FOLLOWUP，否则→EVALUATING）
    Transition(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
               ("g2_answer", "g9_followup_trigger"),
               AgentState.FOLLOWUP, action="store_answer"),
    Transition(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
               ("g2_answer",),
               AgentState.EVALUATING, action="store_answer"),
    # 行 6
    Transition(AgentState.FOLLOWUP, AgentEvent.FOLLOWUP_READY, ("g1_followup",),
               AgentState.AWAITING_ANSWER, action="deliver_followup"),
    # 行 7 / 行 8
    Transition(AgentState.EVALUATING, AgentEvent.EVALUATION_DONE, ("g4_eval",),
               AgentState.DIFFICULTY_ADJ, action="update_profile_stats"),
    Transition(AgentState.EVALUATING, AgentEvent.EVALUATION_FALLBACK, ("g4_fallback",),
               AgentState.DIFFICULTY_ADJ, action="rule_score"),
    # 行 9 / 行 10 / 行 11（互斥：G5 决策 action 唯一）
    Transition(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED, ("g5_next",),
               AgentState.QUESTIONING, action="next_topic"),
    Transition(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED, ("g5_reask",),
               AgentState.QUESTIONING, action="reask_same_topic"),
    Transition(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED, ("g5_end",),
               AgentState.SUMMARIZING, action="summarize"),
    # 行 12 / 行 13 / 行 14
    *_end_requested_rows(),
    *_force_end_rows(),
    Transition(AgentState.SUMMARIZING, AgentEvent.SUMMARIZE_DONE, ("g8_summary",),
               AgentState.END, action="finalize"),
)


# ---------------------------------------------------------------- 状态机

@dataclass
class StepResult:
    """step() 求值结果。allowed=False 时 reason 区分非法转移与守卫拒绝。"""

    allowed: bool
    next_state: Optional[AgentState] = None
    reason: str = ""
    guard_payload: Optional[dict] = None
    transition: Optional[Transition] = None


class StateMachine:
    """确定性状态机：事件 → 表序匹配转移 → AND 守卫求值 → 转移。

    - 非法转移（当前状态无该事件行）→ `StepResult(allowed=False, reason="illegal_transition")`
    - 守卫拒绝 → `StepResult(allowed=False, reason="guard_denied:<首个失败门禁名>")`
    - 门禁可注入覆盖（测试/编排层扩展用）
    """

    def __init__(
        self,
        transitions: Sequence[Transition] = TRANSITIONS,
        gates: Optional[dict[str, GateFn]] = None,
    ):
        self._transitions = tuple(transitions)
        merged = dict(DEFAULT_GATES)
        if gates:
            merged.update(gates)
        self._gates = merged

    def transitions_for(self, state: AgentState, event: AgentEvent) -> list[Transition]:
        """按表序返回 state+event 的候选转移行。"""
        return [t for t in self._transitions if t.from_state is state and t.event is event]

    def allowed_events(self, state: AgentState) -> list[AgentEvent]:
        """当前状态下合法的事件集合（终态为空）。"""
        seen: list[AgentEvent] = []
        for t in self._transitions:
            if t.from_state is state and t.event not in seen:
                seen.append(t.event)
        return seen

    def step(self, state: AgentState, event: AgentEvent, ctx: GateContext) -> StepResult:
        """求值一次转移。ctx.state/ctx.event 应与参数一致（由调用方构造）。"""
        candidates = self.transitions_for(state, event)
        if not candidates:
            return StepResult(allowed=False, reason="illegal_transition")

        failed_guard: Optional[str] = None
        for t in candidates:  # 表序求值（附录 A3：守卫按表序；同事件多行互斥）
            results = [self._gates[g](ctx) for g in t.guards]
            if all(r.passes for r in results):
                payload: dict = {}
                for r in results:
                    if r.payload:
                        payload.update(r.payload)
                return StepResult(
                    allowed=True, next_state=t.to_state,
                    reason="ok", guard_payload=payload or None, transition=t,
                )
            if failed_guard is None:
                for g, r in zip(t.guards, results):
                    if not r.passes:
                        failed_guard = g
                        break
        return StepResult(allowed=False, reason=f"guard_denied:{failed_guard}")


# ---------------------------------------------------------------- 附录 C 全局逃生舱

@dataclass(frozen=True)
class EscapeHatchConfig:
    """逃生舱上限（spec 附录 C；默认值即 spec 值，运行期由 settings 覆盖）。"""

    max_rounds: int = 15
    max_structured_retries: int = 3
    max_consecutive_failures: int = 3
    max_total_fallbacks: int = 5
    node_timeout_sec: int = 60
    max_transitions: int = 200
    max_reask_per_topic: int = 1

    @classmethod
    def from_settings(cls) -> "EscapeHatchConfig":
        """从 app.config.settings 构造（仅运行期调用，保持本模块无 settings 依赖）。"""
        from app.config import settings

        return cls(
            max_rounds=settings.agent_max_rounds,
            max_structured_retries=settings.agent_max_structured_retries,
            max_consecutive_failures=settings.agent_max_consecutive_failures,
            max_total_fallbacks=settings.agent_max_total_fallbacks,
            node_timeout_sec=settings.agent_node_timeout_sec,
            max_transitions=settings.agent_max_transitions,
            max_reask_per_topic=settings.agent_max_reask_per_topic,
        )


@dataclass
class EscapeHatchContext:
    """逃生舱判定所需计数器（由 orchestrator 维护，W1 Day 4 接线）。"""

    round: int = 0
    total_transitions: int = 0
    consecutive_failures: int = 0
    total_fallbacks: int = 0
    over_budget: bool = False


class EscapeHatch:
    """附录 C 逃生舱：check() 返回首个触发原因（str）或 None；不抛异常。

    触发原因（对应 trace `escape_reason`）：
    - budget_exceeded
    - transition_count_exceeded
    - consecutive_failures_exceeded
    - fallbacks_exceeded
    """

    def __init__(self, config: Optional[EscapeHatchConfig] = None):
        self._config = config or EscapeHatchConfig()

    @property
    def config(self) -> EscapeHatchConfig:
        return self._config

    def check(self, ctx: EscapeHatchContext) -> Optional[str]:
        if ctx.over_budget:
            return "budget_exceeded"
        if ctx.total_transitions >= self._config.max_transitions:
            return "transition_count_exceeded"
        if ctx.consecutive_failures >= self._config.max_consecutive_failures:
            return "consecutive_failures_exceeded"
        if ctx.total_fallbacks >= self._config.max_total_fallbacks:
            return "fallbacks_exceeded"
        return None
