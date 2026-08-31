"""Day 4 测试辅助：mock LLM + 完整 agent 栈装配（外部依赖全部 mock / 工作区临时存储）。"""

from types import SimpleNamespace

from app.services.agent.agent_service import AgentService, AgentTopicTracker
from app.services.agent.orchestrator import AgentOrchestrator
from app.services.agent.profile_store import SessionProfileStore
from app.services.agent.state_machine import EscapeHatch, EscapeHatchConfig, StateMachine
from app.services.agent.tools import ToolRegistry, build_default_tools
from app.services.topic_tracker import TopicTracker
from app.storage.interview_store import InterviewStore

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


def make_llm(*, question=None, followup=None, evaluation=None, summary=None):
    """按 prompt 内容分派 mock 输出（question/followup/evaluation/summary 四类）。

    出题按轮次变化（"第 N 题"），避免跨轮相同题目触发 g1 去重门禁。
    """

    async def llm(prompt, system=None):
        if '"followup_question"' in prompt:
            return followup if followup is not None else DEFAULT_FOLLOWUP
        if '"score_reason"' in prompt:
            return evaluation if evaluation is not None else DEFAULT_EVAL
        if '"score_breakdown"' in prompt:
            return summary if summary is not None else DEFAULT_SUMMARY
        if question is not None:
            return question
        import re

        m = re.search(r"当前第 (\d+) 题", prompt)
        n = m.group(1) if m else "1"
        return DEFAULT_QUESTION.replace(
            '"question": "什么是 JVM 内存模型？"',
            f'"question": "第{n}题：什么是 JVM 内存模型？"',
        )

    return llm


class _Facade:
    """mock RetrievalFacade：默认返回空检索；ok=False 时抛异常（测 degrade）。"""

    def __init__(self, ok=True):
        self._ok = ok

    async def retrieve(self, query, top_k=5):
        if not self._ok:
            raise RuntimeError("facade down")
        return SimpleNamespace(chunks=[], sources=[])


def build_stack(
    env_dir,
    *,
    max_rounds=2,
    followup_enabled=True,
    max_followup_depth=1,
    facade_ok=True,
    question=None,
    followup=None,
    evaluation=None,
    summary=None,
    escape=None,
    tree_dir=None,
):
    """装配完整 agent 栈：InterviewStore(工作区临时库) + TopicTracker + SessionProfileStore
    + 六工具注册表 + StateMachine + EscapeHatch + AgentOrchestrator + AgentService。
    """
    db = str(env_dir / "interviews.db")
    store = InterviewStore(db_path=db)
    tracker = TopicTracker(interview_store=store, tree_dir=tree_dir or str(env_dir))
    profile = SessionProfileStore()
    facade = _Facade(ok=facade_ok)
    tools = build_default_tools(facade=facade, topic_tracker=tracker, profile_store=profile)
    reg = ToolRegistry()
    for t in tools.values():
        reg.register(t)
    hatch = escape or EscapeHatch(EscapeHatchConfig(max_rounds=max_rounds))
    machine = StateMachine()
    llm = make_llm(question=question, followup=followup, evaluation=evaluation, summary=summary)
    orch = AgentOrchestrator(
        machine=machine, tools=reg, store=store, llm_call=llm, escape_hatch=hatch,
        trace_dir=str(env_dir / "traces"), profile_store=profile,
        followup_enabled=followup_enabled, max_followup_depth=max_followup_depth,
    )
    agent_tracker = AgentTopicTracker(interview_store=store, tree_dir=tree_dir or str(env_dir))
    svc = AgentService(orchestrator=orch, store=store, topic_tracker=agent_tracker)
    return {
        "svc": svc,
        "store": store,
        "orch": orch,
        "tracker": agent_tracker,
        "env": env_dir,
    }
