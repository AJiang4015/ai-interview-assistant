"""W1 Day 5 冒烟：真实装配接线 + 真实 LLM 客户端 + 异常演练 + trace 校验。

场景：
1. verify_assembly       — interview_mode 分支、AgentService 与 legacy surface 兼容（含 stats/today 委托）
2. scenario_happy_path   — 真实工厂装配 + 可工作模型适配器：完整状态流（含 FOLLOWUP）→ report 落库
3. scenario_schema_retry — schema 校验失败 → 回填重试 → 成功（attempts 计数）
4. scenario_real_client  — 真实 LLMClient（当前 .env 密钥无效，401）：LLM 失败 → retry → 确定性兜底 → 流程仍完成
5. scenario_escape       — 真实 LLMClient + max_consecutive_failures=1：逃生舱 → SUMMARIZING → END
6. verify_trace          — 7 类事件齐全（transition/node_started/node_finished/tool_call/fallback/escape/session_end）

说明：因 BAILIAN_API_KEY 无效（401），真实模型推理不可用；真实客户端路径以失败注入
（真实客户端+真实网络行为）验证降级矩阵；正常出题/追问/评估路径用可工作模型适配器
跑在**真实工厂装配**上（真实 InterviewStore/TopicTracker/settings 配置）。
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.services.agent.agent_service import AgentService, build_agent_service  # noqa: E402
from app.services.agent.orchestrator import AgentOrchestrator  # noqa: E402
from app.services.agent.state_machine import AgentState, EscapeHatchConfig  # noqa: E402
from app.services.interview_service import InterviewService  # noqa: E402
from app.services.llm_client import LLMClient  # noqa: E402
from app.services.topic_tracker import TopicTracker  # noqa: E402
from app.storage.interview_store import InterviewStore  # noqa: E402

WORK = PROJECT_ROOT / "data" / "agent_smoke"
TRACE_DIR = WORK / "traces"
RESULTS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    print(RESULTS[-1])


class _EmptyFacade:
    """kb_retrieve 的空实现（RAG 链路不在本冒烟范围，聚焦 LLM 编排）。"""

    async def retrieve(self, query, top_k=5):
        return SimpleNamespace(chunks=[], sources=[])


DEFAULT_QUESTION = (
    '{"question": "什么是 JVM 内存模型？", "difficulty": "medium", '
    '"knowledge_tags": ["JVM"], "topic": "JVM", "category": "JVM"}'
)
DEFAULT_FOLLOWUP = '{"followup_question": "为什么用分段锁？", "intent": "probe"}'
DEFAULT_EVAL = (
    '{"score": 7, "comment": "覆盖主要要点", "score_reason": "主要知识点覆盖完整", '
    '"reference_answer": "参考", "tags": ["JVM"]}'
)
DEFAULT_SUMMARY = (
    '{"level": "中级", "knowledge_analysis": {"strengths": ["JVM"], "weaknesses": []}, '
    '"improvement_suggestions": ["补强深度"]}'
)


class _ScriptedLLM:
    """可工作模型适配器（模拟模型行为，跑在真实装配上）。"""

    def __init__(self, *, question=None, followup=None, evaluation=None, summary=None,
                 fail_question_times=0, question_note=""):
        self.question = question
        self.followup = followup
        self.evaluation = evaluation
        self.summary = summary
        self.fail_question_times = fail_question_times
        self.question_calls = 0
        self.question_note = question_note

    async def chat(self, prompt, system=None):
        if '"followup_question"' in prompt:
            return self.followup if self.followup is not None else DEFAULT_FOLLOWUP
        if '"score_reason"' in prompt:
            return self.evaluation if self.evaluation is not None else DEFAULT_EVAL
        if '"score_breakdown"' in prompt:
            return self.summary if self.summary is not None else DEFAULT_SUMMARY
        self.question_calls += 1
        if self.question_calls <= self.fail_question_times:
            return "不是 JSON 的输出（注入 schema 失败）"
        m = re.search(r"当前第 (\d+) 题", prompt)
        n = m.group(1) if m else str(self.question_calls)
        return (self.question or DEFAULT_QUESTION).replace(
            '"question": "什么是 JVM 内存模型？"',
            f'"question": "{self.question_note or "第" + n + "题"}：什么是 JVM 内存模型？"',
        )


def _build(store, facade, llm, escape_cfg, trace_dir):
    return build_agent_service(
        store=store, llm=llm, facade=facade, topic_tracker=TopicTracker(interview_store=store),
        trace_dir=str(trace_dir), trace_retention=50,
        escape_config=escape_cfg,
        followup_enabled=settings.agent_followup_enabled,
        max_followup_depth=settings.agent_max_followup_depth,
        max_answer_chars=settings.agent_max_answer_chars,
    )


def _new_store(name: str) -> InterviewStore:
    (WORK / "db").mkdir(parents=True, exist_ok=True)
    return InterviewStore(db_path=str(WORK / "db" / f"{name}.db"))


def _trace_events(session_id: str) -> list[dict]:
    tf = TRACE_DIR / f"{session_id}.jsonl"
    if not tf.exists():
        return []
    return [json.loads(line) for line in tf.read_text(encoding="utf-8").strip().splitlines()]


def verify_assembly() -> None:
    print("\n== 1. 装配验证（interview_mode 分支 + surface 兼容）==")
    check("settings.interview_mode 默认 legacy（存量行为不变）", settings.interview_mode == "legacy",
          f"interview_mode={settings.interview_mode!r}")

    store = _new_store("assembly")
    facade = _EmptyFacade()
    llm = LLMClient()  # 真实客户端（401 密钥，仅用于装配冒烟）
    tracker = TopicTracker(interview_store=store)
    legacy = InterviewService(store, llm, facade=facade, topic_tracker=tracker)
    agent = _build(store, facade, llm, EscapeHatchConfig(max_rounds=3), TRACE_DIR)

    check("agent 是 AgentService 实例", isinstance(agent, AgentService))
    check("legacy 仍是 InterviewService 实例", isinstance(legacy, InterviewService))

    legacy_surface = {m for m in dir(legacy) if not m.startswith("_")}
    for m in ("start", "answer", "end", "get_report", "get_detail", "history", "stats", "today"):
        check(f"agent 兼容方法: {m}", m in legacy_surface and hasattr(agent, m))

    check("agent.store 属性（coverage API）", hasattr(agent, "store"))
    check("agent.topic_tracker 属性（coverage API）", hasattr(agent, "topic_tracker"))
    check("agent.stats 委托 legacy（exclude followup）", agent.stats(username="smoke") == {"categories": [], "total_questions": 0})


async def scenario_happy_path() -> None:
    print("\n== 2. 正常完整状态流（真实工厂装配 + 可工作模型适配器）==")
    store = _new_store("happy")
    llm = _ScriptedLLM()
    svc = _build(store, _EmptyFacade(), llm, EscapeHatchConfig(max_rounds=2), TRACE_DIR)
    res = await svc.start("Java后端", username="smoke")
    sid, qid = res["session_id"], res["question"]["id"]
    check("start → question", bool(qid))

    ans1 = await svc.answer(qid, "短答触发追问", username="smoke")
    nq = ans1["next_question"]
    check("短答 → 追问（next_question.source=followup）", nq is not None and nq["source"] == "followup")

    ans2 = await svc.answer(nq["id"], "追问回答内容略长以避免再次追问", username="smoke")
    check("追问答 → 最终评估 + 下一题", ans2["is_complete"] is False and ans2["next_question"] is not None)

    q2 = ans2["next_question"]
    ans3 = await svc.answer(q2["id"], "第二轮回答内容足够长避免追问：" + "x" * 300, username="smoke")
    check("round2 回答 → 收尾（is_complete）", ans3["is_complete"] is True)

    report = store.get_session(sid)
    check("report 落库（completed + 字段）",
          report is not None and report["status"] == "completed" and (report.get("report") or {}).get("total_score") is not None)
    check("state=END", svc.orchestrator.get_state(sid) is AgentState.END)
    events = _trace_events(sid)
    kinds = {e["event"] for e in events}
    check("happy trace 含 transition/node/tool/session_end",
          {"transition", "node_finished", "tool_call", "session_end"} <= kinds)


async def scenario_schema_retry() -> None:
    print("\n== 3. schema 校验失败 → 回填重试 → 成功 ==")
    store = _new_store("retry")
    llm = _ScriptedLLM(fail_question_times=2)  # 前两次非 JSON，第三次成功
    svc = _build(store, _EmptyFacade(), llm, EscapeHatchConfig(max_rounds=3), TRACE_DIR)
    res = await svc.start("Java后端", username="smoke")
    check("question 经 3 次尝试成功", res["question"]["content"] and llm.question_calls == 3)


async def scenario_real_client() -> None:
    print("\n== 4. 真实 LLMClient（密钥 401）→ 失败重试 → 确定性兜底 → 流程完成 ==")
    store = _new_store("real")
    llm = LLMClient()  # 真实客户端：401 → generate_structured 内 3 次尝试失败 → fallback
    svc = _build(store, _EmptyFacade(), llm, EscapeHatchConfig(max_rounds=1), TRACE_DIR)
    res = await svc.start("Java后端", username="smoke")
    check("出题 LLM 失败 → G1-F 兜底题", bool(res["question"]["content"]))
    ans = await svc.answer(res["question"]["id"], "回答内容足够长避免追问：" + "r" * 300, username="smoke")
    check("评估 LLM 失败 → G4-F 规则分", ans["evaluation"]["score"] == 5)
    check("流程仍完成（is_complete）", ans["is_complete"] is True)
    ev = _trace_events(res["session_id"])
    check("真实链路 trace 含 fallback", any(e["event"] == "fallback" for e in ev))


async def scenario_escape() -> None:
    print("\n== 5. 逃生舱（max_consecutive_failures=1 + LLM 失败）→ SUMMARIZING → END ==")
    store = _new_store("escape")
    llm = LLMClient()
    svc = _build(store, _EmptyFacade(), llm, EscapeHatchConfig(max_rounds=5, max_consecutive_failures=1), TRACE_DIR)
    res = await svc.start("Java后端", username="smoke")
    ans = await svc.answer(res["question"]["id"], "回答内容足够长避免追问：" + "e" * 300, username="smoke")
    check("逃生 → 强制收尾", ans["is_complete"] is True and ans["report"].get("total_score") is not None)
    ev = _trace_events(res["session_id"])
    check("trace 含 escape 事件", any(e["event"] == "escape" for e in ev))


def verify_trace() -> None:
    print("\n== 6. trace 7 类事件齐全（跨全部场景）==")
    all_kinds: set[str] = set()
    total = 0
    for p in TRACE_DIR.glob("*.jsonl"):
        for line in p.read_text(encoding="utf-8").strip().splitlines():
            all_kinds.add(json.loads(line)["event"])
            total += 1
    required = {"transition", "node_started", "node_finished", "tool_call", "fallback", "escape", "session_end"}
    missing = required - all_kinds
    check("trace 7 类事件齐全", not missing, f"missing={sorted(missing)}" if missing else f"total={total} events")


async def main() -> None:
    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    verify_assembly()
    await scenario_happy_path()
    await scenario_schema_retry()
    await scenario_real_client()
    await scenario_escape()
    verify_trace()
    failed = [r for r in RESULTS if r.startswith("[FAIL]")]
    print(f"\n===== W1 Day 5 冒烟结果：{len(RESULTS) - len(failed)}/{len(RESULTS)} PASS =====")
    if failed:
        print("\n".join(failed))
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
