"""Agent 编排器（impl-spec v2 附录 D orchestrator；A3 转移 / A6 answer 契约 / C 逃生舱 / G 降级矩阵）。

职责边界（用户 W1 Day 4 特别要求）：
- 本模块**只负责编排**：接收/产生 AgentEvent → StateMachine 判合法转移 → 调用 Role Node
  （roles + structured_output 组装）→ 调用 ToolRegistry → 连接 fallback（G1-F/G4-F/G8）
  → 写 trace → 检查 EscapeHatch。
- **不吸收** StateMachine / Role / Tool / fallback 的内部实现（全部经 import 复用）。
- 节点执行（prompt 构建 + generate_structured）为薄组合层，业务定义仍在 roles / structured_output。

与 spec 的对应：
- A3：每次机器转移经 `_step()`（非法转移 → ValueError，`illegal_transition` 语义）
- A6：answer 契约映射（追问=next_question 且 source='followup'；generate_next=False 同题重评）
- F1：followup 行独立 question_id、source='followup'、topic/category 留空
- C：节点执行后检查逃生舱，触发 → FORCE_END → SUMMARIZING（trace escape 事件）
- G：工具失败（ToolError）→ degrade 跳过并 trace 打标；ToolAbortError → 逃生舱
- E6/F8：报告与统计过滤 followup（deterministic_summary 内部过滤）
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.services.agent.fallback import (
    deterministic_summary,
    fallback_question,
    generate_summary,
    rule_score,
)
from app.services.agent.profile_store import ProfileStore
from app.services.agent.roles import (
    EVALUATOR_SYSTEM,
    FOLLOWUPER_SYSTEM,
    QUESTIONER_SYSTEM,
    Evaluation,
    FollowUp,
    Question,
    build_evaluation_prompt,
    build_followup_prompt,
    build_question_prompt,
)
from app.services.agent.state_machine import (
    AgentEvent,
    AgentState,
    EscapeHatch,
    EscapeHatchContext,
    GateContext,
    StateMachine,
    StepResult,
)
from app.services.agent.structured_output import StructuredResult, generate_structured
from app.services.agent.tools import ToolAbortError, ToolError, ToolRegistry
from app.services.agent.trace import ToolCallTrace, TraceRecorder, TraceRecord
from app.storage.interview_store import InterviewStore

_PROMPT_VERSION = "roles.v1"
# G9 模糊作答启发式阈值（与 state_machine g9_followup_trigger 一致，spec 附录 B G9）
_FOLLOWUP_AMBIGUITY_CHARS = 200
_DIFFICULTY_ORDER = ("easy", "medium", "hard")


def _shift_difficulty(difficulty: str, delta: int) -> str:
    """难度平移（delta 截断到 easy/hard 边界，spec 附录 B G5）。"""
    try:
        idx = _DIFFICULTY_ORDER.index(difficulty)
    except ValueError:
        return "medium"
    idx = max(0, min(len(_DIFFICULTY_ORDER) - 1, idx + delta))
    return _DIFFICULTY_ORDER[idx]


@dataclass
class SessionContext:
    """单会话运行态（A1：AWAITING_ANSWER 为持久化点；Day 4 为进程内 registry，
    生产化（Redis 持久化）列入 W2/W3，见 OPEN 记录）。"""

    session_id: str
    user_id: str
    position: str
    state: AgentState = AgentState.INIT
    round: int = 0
    current_difficulty: str = "medium"
    current_topic: str = ""
    current_tags: list[str] = field(default_factory=list)
    asked_set: set[str] = field(default_factory=set)
    followup_budget: int = 0
    consecutive_failures: int = 0
    total_fallbacks: int = 0
    total_transitions: int = 0
    reask_counts: dict[str, int] = field(default_factory=dict)
    user_ended: bool = False
    main_question_id: str = ""
    personalized_context: str = ""


class AgentOrchestrator:
    """编排器：事件 → 状态机 → 节点 → 工具 → fallback → trace → 逃生舱。"""

    def __init__(
        self,
        *,
        machine: StateMachine,
        tools: ToolRegistry,
        store: InterviewStore,
        llm_call: Callable[..., Awaitable[str]],
        escape_hatch: EscapeHatch,
        trace_dir: str | Path = "data/traces",
        trace_retention: int = 200,
        profile_store: Optional[ProfileStore] = None,
        model_name: str = "unknown",
        followup_enabled: bool = True,
        max_followup_depth: int = 1,
        max_answer_chars: int = 2000,
    ):
        self._machine = machine
        self._tools = tools
        self._store = store
        self._llm_call = llm_call
        self._escape = escape_hatch
        self._trace_dir = str(trace_dir)
        self._trace_retention = trace_retention
        self._profile_store = profile_store
        self._model_name = model_name
        self._followup_enabled = followup_enabled
        self._max_followup_depth = max_followup_depth
        self._max_answer_chars = max_answer_chars
        self._sessions: dict[str, SessionContext] = {}
        self._recorders: dict[str, TraceRecorder] = {}

    @property
    def tools(self) -> ToolRegistry:
        return self._tools

    # ---------------------------------------------------------------- 对外操作

    def get_state(self, session_id: str) -> Optional[AgentState]:
        ctx = self._sessions.get(session_id)
        return ctx.state if ctx else None

    async def start(self, position: str, username: str = "", personalized_context: str = "") -> dict:
        """INIT → QUESTIONING →（出题节点）→ AWAITING_ANSWER。返回 {session_id, question}。"""
        session = self._store.create_session(position, username=username)
        sid = session["id"]
        ctx = SessionContext(
            session_id=sid, user_id=username, position=position,
            state=AgentState.INIT, round=1,
            followup_budget=self._max_followup_depth,
            personalized_context=personalized_context,
        )
        self._sessions[sid] = ctx
        self._recorders[sid] = TraceRecorder(sid, self._trace_dir, self._trace_retention)

        self._step(ctx, AgentState.INIT, AgentEvent.START, position=position)

        qdict = await self._ask_question(ctx)
        row = self._store.add_question(
            sid, ctx.round, qdict["content"], qdict["difficulty"], qdict["source"],
            topic=qdict.get("topic", ""), category=qdict.get("category", ""),
        )
        qdict["id"] = row["id"]
        qdict["round"] = ctx.round
        ctx.main_question_id = row["id"]
        ctx.current_tags = list(qdict["knowledge_tags"])

        event = AgentEvent.QUESTION_FALLBACK if qdict.get("fallback") else AgentEvent.QUESTION_READY
        self._step(
            ctx, AgentState.QUESTIONING, event,
            output=self._question_gate_output(qdict), asked_set=frozenset(ctx.asked_set),
        )
        ctx.asked_set.add(hash(qdict["content"]))
        return {"session_id": sid, "question": qdict}

    async def submit_answer(
        self, question_id: str, answer: str, generate_next: bool = True, user_id: str = "",
    ) -> dict:
        """A6 answer 契约：主答/追问答/同题重评。返回 legacy 形状 {evaluation, is_complete, ...}。"""
        qrow = self._store.get_question(question_id)
        if qrow is None:
            raise ValueError(f"question not found: {question_id}")
        session_id = qrow["session_id"]
        ctx = self._sessions.get(session_id)
        if ctx is None:
            raise ValueError("session state not available (in-process registry; restart recovery not supported)")

        # OPEN-4 同题重评：不推进状态
        if not generate_next:
            ev = await self._evaluate(ctx, qrow, answer)
            self._store.update_answer(question_id, answer, ev, float(ev["score"]))
            return {"evaluation": ev, "is_complete": False, "next_question": None, "session_id": session_id}

        if ctx.state is not AgentState.AWAITING_ANSWER:
            raise ValueError(f"illegal transition: submit_answer in state {ctx.state.value}")

        # G9：短答 + 预算 → 先尝试生成追问（失败则预算置 0 直接评估，G1-f 兜底）
        triggered = (
            self._followup_enabled
            and ctx.followup_budget > 0
            and len(answer) < _FOLLOWUP_AMBIGUITY_CHARS
        )
        if triggered:
            fu = await self._ask_followup(ctx, qrow, answer)
            if fu is not None:
                self._step(
                    ctx, AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
                    answer_len=len(answer), followup_enabled=True,
                    followup_budget=ctx.followup_budget, max_answer_chars=self._max_answer_chars,
                )  # → FOLLOWUP
                # A6：主答评估
                main_ev = await self._evaluate(ctx, qrow, answer)
                self._store.update_answer(question_id, answer, main_ev, float(main_ev["score"]))
                # 追问行持久化（F1：独立 question_id / source='followup' / topic 留空）
                fu_row = self._store.add_question(
                    session_id, ctx.round, fu["content"], fu["difficulty"],
                    "followup", topic="", category="",
                )
                ctx.followup_budget -= 1
                fu["id"] = fu_row["id"]
                fu["round"] = ctx.round
                self._step(
                    ctx, AgentState.FOLLOWUP, AgentEvent.FOLLOWUP_READY,
                    output={"followup_question": fu["content"]},
                )  # → AWAITING_ANSWER
                return {"evaluation": main_ev, "is_complete": False, "next_question": fu, "session_id": session_id}
            ctx.followup_budget = 0  # 追问失败 → 放弃追问，直接评估（G1-f）

        self._step(
            ctx, AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
            answer_len=len(answer), followup_enabled=self._followup_enabled,
            followup_budget=ctx.followup_budget, max_answer_chars=self._max_answer_chars,
        )  # → EVALUATING（¬G9）

        # 评估（追问回答 → 合并最终评估并更新主答行，A6）
        if qrow["source"] == "followup":
            main_row = self._find_main_row(session_id, qrow)
            ev = await self._evaluate_exchange(ctx, main_row, qrow, answer)
            self._store.update_answer(question_id, answer, ev, float(ev["score"]))
            if main_row:
                self._store.update_answer(main_row["id"], main_row.get("answer") or "", ev, float(ev["score"]))
        else:
            ev = await self._evaluate(ctx, qrow, answer)
            self._store.update_answer(question_id, answer, ev, float(ev["score"]))
        score = float(ev["score"])

        # 逃生舱检查（节点执行后；触发 → FORCE_END → SUMMARIZING）
        reason = self._escape_reason(ctx)
        if reason:
            return await self._force_end(session_id, ctx, reason, evaluation=ev)

        ev_event = AgentEvent.EVALUATION_FALLBACK if ev.get("fallback") == "eval_rule" else AgentEvent.EVALUATION_DONE
        self._step(ctx, AgentState.EVALUATING, ev_event, output=ev)

        topic = qrow.get("topic") or ctx.current_topic
        reask_allowed = ctx.reask_counts.get(topic, 0) < self._escape.config.max_reask_per_topic
        st = self._step(
            ctx, AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
            score=score, round=ctx.round, max_rounds=self._escape.config.max_rounds,
            reask_allowed=reask_allowed, user_ended=ctx.user_ended,
        )
        payload = st.guard_payload or {}

        if st.next_state is AgentState.SUMMARIZING:
            report = await self._summarize(session_id, ctx)
            return {"evaluation": ev, "is_complete": True, "report": report, "session_id": session_id}

        # → QUESTIONING：下一题
        delta = payload.get("delta", 0)
        ctx.current_difficulty = _shift_difficulty(qrow.get("difficulty") or ctx.current_difficulty, delta)
        if payload.get("action") == "reask":
            ctx.reask_counts[topic] = ctx.reask_counts.get(topic, 0) + 1
            ctx.current_topic = topic
        else:
            ctx.current_topic = ""
        ctx.round += 1
        ctx.followup_budget = self._max_followup_depth
        ctx.current_tags = []

        next_q = await self._ask_question(ctx)
        row = self._store.add_question(
            session_id, ctx.round, next_q["content"], next_q["difficulty"], next_q["source"],
            topic=next_q.get("topic", ""), category=next_q.get("category", ""),
        )
        ctx.main_question_id = row["id"]
        ctx.current_tags = list(next_q["knowledge_tags"])
        event = AgentEvent.QUESTION_FALLBACK if next_q.get("fallback") else AgentEvent.QUESTION_READY
        self._step(
            ctx, AgentState.QUESTIONING, event,
            output=self._question_gate_output(next_q), asked_set=frozenset(ctx.asked_set),
        )
        ctx.asked_set.add(hash(next_q["content"]))
        next_q["id"] = row["id"]
        next_q["round"] = ctx.round

        reason2 = self._escape_reason(ctx)
        if reason2:
            return await self._force_end(session_id, ctx, reason2, evaluation=ev)

        return {"evaluation": ev, "is_complete": False, "next_question": next_q, "session_id": session_id}

    async def end(self, session_id: str, user_id: str = "") -> dict:
        """END_REQUESTED → SUMMARIZING → 报告 → END。返回 {session_id, report}。"""
        ctx = self._sessions.get(session_id)
        if ctx is None:
            session = self._store.get_session(session_id)
            if session is None:
                raise ValueError(f"session not found: {session_id}")
            # 进程内状态缺失（如重启）：从 store 重建最小上下文
            ctx = SessionContext(
                session_id=session_id, user_id=user_id, position=session["position"],
                state=AgentState.AWAITING_ANSWER,
                round=sum(1 for q in self._store.get_questions(session_id) if q.get("source") != "followup"),
            )
            self._sessions[session_id] = ctx
            self._recorders[session_id] = TraceRecorder(session_id, self._trace_dir, self._trace_retention)

        if ctx.state is AgentState.END:
            session = self._store.get_session(session_id) or {}
            report = session.get("report") or deterministic_summary(session, self._store.get_questions(session_id))
            return {"session_id": session_id, "report": report}

        ctx.user_ended = True
        self._step(ctx, ctx.state, AgentEvent.END_REQUESTED)
        report = await self._summarize(session_id, ctx)
        return {"session_id": session_id, "report": report}

    # ---------------------------------------------------------------- 状态机与逃生舱

    @staticmethod
    def _question_gate_output(qdict: dict) -> dict:
        """把 API 响应形状（content）适配为 Role 输出形状（question），供 g1 门禁校验。"""
        return {
            "question": qdict["content"],
            "difficulty": qdict["difficulty"],
            "knowledge_tags": qdict.get("knowledge_tags", []),
        }

    def _step(self, ctx: SessionContext, state: AgentState, event: AgentEvent, **gate_kwargs: Any) -> StepResult:
        """机器转移（非法/守卫拒绝 → ValueError）；转移计数 + trace transition。"""
        gate_ctx = GateContext(state=state, event=event, **gate_kwargs)
        st = self._machine.step(state, event, gate_ctx)
        if not st.allowed:
            raise ValueError(f"agent transition rejected: {state.value}/{event.value}: {st.reason}")
        ctx.state = st.next_state
        ctx.total_transitions += 1
        self._record(ctx, event="transition", state=st.next_state.value)
        return st

    def _escape_reason(self, ctx: SessionContext) -> Optional[str]:
        return self._escape.check(EscapeHatchContext(
            round=ctx.round,
            total_transitions=ctx.total_transitions,
            consecutive_failures=ctx.consecutive_failures,
            total_fallbacks=ctx.total_fallbacks,
            over_budget=False,
        ))

    async def _force_end(self, session_id: str, ctx: SessionContext, reason: str, evaluation: Optional[dict] = None) -> dict:
        """逃生舱：FORCE_END → SUMMARIZING → 报告。"""
        self._record(ctx, event="escape", fallback_used=reason)
        self._step(ctx, ctx.state, AgentEvent.FORCE_END, force_end=True)
        report = await self._summarize(session_id, ctx)
        return {"evaluation": evaluation, "is_complete": True, "report": report, "session_id": session_id}

    async def _summarize(self, session_id: str, ctx: SessionContext) -> dict:
        session = self._store.get_session(session_id) or {"position": ctx.position, "id": session_id}
        questions = self._store.get_questions(session_id)
        report = await generate_summary(session, questions, llm_call=self._llm_call)
        self._store.complete_session(session_id, report)
        answered = sum(1 for q in questions if q.get("source") != "followup" and q.get("answer"))
        self._step(ctx, AgentState.SUMMARIZING, AgentEvent.SUMMARIZE_DONE,
                   answered_rounds=answered, summary_ready=True)
        self._record(ctx, event="session_end", state=AgentState.END.value)
        rec = self._recorders.pop(session_id, None)
        if rec:
            rec.close()
        return report

    # ---------------------------------------------------------------- 节点执行（薄组合层）

    async def _run_role_node(
        self,
        ctx: SessionContext,
        *,
        node: str,
        role: str,
        system: str,
        prompt: str,
        model_cls: type,
        started: float,
        fallback_label: str,
    ) -> StructuredResult:
        """角色节点执行（薄组合）：generate_structured + trace node_started/node_finished。

        LLM 调用/网络异常（spec G 矩阵「LLM 调用失败」）→ 包装为 fallback 结果，
        由各节点按既有 fallback 逻辑走确定性兜底（G1-F / G1-f / G4-F）。
        """
        self._record(ctx, event="node_started", node=node, role=role)
        try:
            result = await generate_structured(
                self._llm_call, prompt, model_cls.model_json_schema(), model_cls, system=system,
            )
        except Exception as e:  # noqa: BLE001 —— LLM 失败 → 降级矩阵：节点确定性兜底
            result = StructuredResult(ok=False, attempts=1, errors=[f"llm_call failed: {e}"], fallback=True)
        self._record(
            ctx, event="node_finished", node=node, role=role,
            input_summary=prompt[:300],
            raw_output=json.dumps(result.data, ensure_ascii=False) if result.data else None,
            validated=result.ok, retries=result.retries,
            fallback_used=fallback_label if result.fallback else None,
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        return result

    async def _ask_question(self, ctx: SessionContext) -> dict:
        """QUESTIONING 节点：kb/profile/topic 注入 → 结构化出题（含 G1-F 兜底）。"""
        started = time.monotonic()
        kb_text = ""
        kb_sources: list[dict] = []
        kb = await self._run_tool(ctx, "kb_retrieve", query=f"{ctx.position} 技术面试题 {ctx.current_difficulty}", top_k=5)
        if kb:
            kb_text = "\n---\n".join(c["content"] for c in kb["chunks"])
            kb_sources = kb["sources"]

        profile = await self._run_tool(ctx, "get_profile", user_id=ctx.user_id) or {}
        profile_summary = ""
        if profile.get("weak_points"):
            profile_summary = "薄弱点：" + "、".join(profile["weak_points"][:5])

        suggestion: dict = {}
        if not ctx.current_topic:
            suggestion = await self._run_tool(ctx, "pick_next_topic", session_id=ctx.session_id, position=ctx.position) or {}
        suggested_topic = ctx.current_topic or suggestion.get("topic") or ""
        suggested_text = f"{suggestion.get('category', '')} - {suggested_topic}" if suggested_topic else ""
        if ctx.personalized_context:
            kb_text = (kb_text + "\n" + ctx.personalized_context).strip()

        prompt = build_question_prompt(
            ctx.position, ctx.round, ctx.current_difficulty,
            knowledge_context=kb_text, coverage_summary="",
            profile_summary=profile_summary, suggested_topic=suggested_text,
        )
        result = await self._run_role_node(
            ctx, node="questioner", role="出题人", system=QUESTIONER_SYSTEM,
            prompt=prompt, model_cls=Question, started=started,
            fallback_label="question_fallback",
        )
        if result.fallback:
            ctx.consecutive_failures += 1
            ctx.total_fallbacks += 1
            self._record(ctx, event="fallback", node="questioner", fallback_used="question_fallback")
            fq = fallback_question(suggestion or {"category": None, "topic": None}, ctx.current_difficulty)
            return {
                "id": None, "content": fq["question"], "round": ctx.round,
                "difficulty": fq["difficulty"], "source": fq["source"],
                "knowledge_tags": fq["knowledge_tags"], "topic": fq["topic"],
                "category": fq["category"], "sources": [], "fallback": True,
            }
        ctx.consecutive_failures = 0
        q = result.model
        return {
            "id": None, "content": q.question, "round": ctx.round,
            "difficulty": q.difficulty, "source": "kb" if kb_text else "llm",
            "knowledge_tags": q.knowledge_tags, "topic": q.topic,
            "category": q.category, "sources": kb_sources, "fallback": False,
        }

    async def _ask_followup(self, ctx: SessionContext, question_row: dict, answer: str) -> Optional[dict]:
        """FOLLOWUP 节点：失败返回 None（G1-f：放弃追问转评估）。"""
        started = time.monotonic()
        prompt = build_followup_prompt(question_row["question"], answer)
        result = await self._run_role_node(
            ctx, node="followuper", role="追问者", system=FOLLOWUPER_SYSTEM,
            prompt=prompt, model_cls=FollowUp, started=started,
            fallback_label="followup_skipped",
        )
        if result.fallback:
            ctx.consecutive_failures += 1
            ctx.total_fallbacks += 1
            self._record(ctx, event="fallback", node="followuper", fallback_used="followup_skipped")
            return None
        ctx.consecutive_failures = 0
        return {
            "id": None, "content": result.model.followup_question,
            "difficulty": question_row.get("difficulty") or "medium",
            "source": "followup", "knowledge_tags": [], "topic": "", "category": "",
            "sources": [], "fallback": False,
        }

    async def _evaluate(self, ctx: SessionContext, question_row: dict, answer: str) -> dict:
        """EVALUATING 节点：检索参考 → 结构化评估（含 G4-F 规则评分兜底）。"""
        started = time.monotonic()
        kb_text = ""
        kb_sources: list[dict] = []
        kb = await self._run_tool(ctx, "kb_retrieve", query=(question_row["question"] + " " + answer)[:500], top_k=5)
        if kb:
            kb_text = "\n---\n".join(c["content"] for c in kb["chunks"])
            kb_sources = kb["sources"]

        prompt = build_evaluation_prompt(
            question_row["question"], answer,
            knowledge_context=kb_text,
            reference_hint="、".join(ctx.current_tags),
        )
        result = await self._run_role_node(
            ctx, node="evaluator", role="评估官", system=EVALUATOR_SYSTEM,
            prompt=prompt, model_cls=Evaluation, started=started,
            fallback_label="eval_rule",
        )
        if result.fallback:
            ctx.consecutive_failures += 1
            ctx.total_fallbacks += 1
            self._record(ctx, event="fallback", node="evaluator", fallback_used="eval_rule")
            ev = rule_score(question_row["question"], answer, ctx.current_tags)
            ev["sources"] = kb_sources
            return ev
        ctx.consecutive_failures = 0
        return {
            "score": result.model.score, "comment": result.model.comment,
            "score_reason": result.model.score_reason, "reference_answer": result.model.reference_answer,
            "tags": result.model.tags,
            "next_difficulty": _shift_difficulty(ctx.current_difficulty, 1),
            "should_end": False, "sources": kb_sources,
        }

    async def _evaluate_exchange(self, ctx: SessionContext, main_row: dict, followup_row: dict, followup_answer: str) -> dict:
        """追问链合并最终评估（A6）：主答 + 追问 Q&A 一起评估。"""
        combined_question = main_row["question"]
        combined_answer = f"主答：{main_row.get('answer') or ''}\n追问：{followup_row['question']}\n追问回答：{followup_answer}"
        return await self._evaluate(ctx, {"question": combined_question, "difficulty": followup_row.get("difficulty") or "medium"}, combined_answer)

    async def _run_tool(self, ctx: SessionContext, name: str, **kwargs: Any) -> Optional[dict]:
        """工具调用 + trace tool_call；ToolError → degrade 跳过（返回 None）；ToolAbortError → 上抛（触发逃生舱）。"""
        started = time.monotonic()
        args_summary = json.dumps(kwargs, ensure_ascii=False)[:200]
        try:
            out = await self._tools.execute(name, **kwargs)
        except ToolAbortError:
            self._record(
                ctx, event="tool_call", node=name,
                tool_calls=[ToolCallTrace(tool=name, args_summary=args_summary,
                                          latency_ms=int((time.monotonic() - started) * 1000), ok=False)],
                fallback_used="tool_abort",
            )
            raise
        except ToolError as e:
            self._record(
                ctx, event="tool_call", node=name,
                tool_calls=[ToolCallTrace(tool=name, args_summary=args_summary,
                                          latency_ms=int((time.monotonic() - started) * 1000), ok=False)],
                fallback_used=f"tool_degrade:{name}",
            )
            return None  # degrade：跳过该工具，节点降级继续
        self._record(
            ctx, event="tool_call", node=name,
            tool_calls=[ToolCallTrace(tool=name, args_summary=args_summary,
                                      latency_ms=int((time.monotonic() - started) * 1000), ok=True)],
        )
        return out

    def _find_main_row(self, session_id: str, followup_row: dict) -> Optional[dict]:
        """按 round 找与追问同轮的主问题行。"""
        for q in self._store.get_questions(session_id):
            if q.get("source") != "followup" and q.get("round") == followup_row.get("round"):
                return q
        return None

    # ---------------------------------------------------------------- trace

    def _record(
        self, ctx: SessionContext, *, event: str, state: Optional[str] = None,
        node: Optional[str] = None, role: Optional[str] = None, model: Optional[str] = None,
        prompt_version: Optional[str] = None, input_summary: Optional[str] = None,
        raw_output: Optional[str] = None, validated: Optional[bool] = None,
        retries: int = 0, tool_calls: Optional[list[ToolCallTrace]] = None,
        fallback_used: Optional[str] = None, latency_ms: Optional[int] = None,
    ) -> None:
        rec = self._recorders.get(ctx.session_id)
        if rec is None:
            return
        rec.record(TraceRecord(
            session_id=ctx.session_id,
            ts=datetime.now(timezone.utc).isoformat(),
            event=event, state=state or ctx.state.value,
            node=node, role=role, model=model or self._model_name,
            prompt_version=prompt_version, input_summary=input_summary,
            raw_output=raw_output, validated=validated, retries=retries,
            tool_calls=tool_calls, fallback_used=fallback_used, latency_ms=latency_ms,
        ))
