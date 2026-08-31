"""W1 Day 4：AgentService 与 legacy contract 兼容性测试（OPEN-1/F9 冻结）。

覆盖：
- 完整 public surface：start/answer/end/get_report/get_detail/history/stats/today
- store / topic_tracker 属性（coverage API 兼容）
- stats 委托 legacy 且传 exclude_sources=("followup",)（F9）
- coverage 过滤 followup（F9：AgentTopicTracker 默认过滤 + TopicTracker 参数）
- 会话隔离（AuthorizationError 语义）
"""

from types import SimpleNamespace

import pytest

from app.exceptions import AuthorizationError
from app.services.agent.agent_service import AgentService, AgentTopicTracker
from app.services.agent.state_machine import EscapeHatch, EscapeHatchConfig
from app.services.topic_tracker import TopicTracker
from tests.services.agent._helpers import build_stack

REAL_TREE_DIR = "data/knowledge_trees"


class FakeLegacyReadonly:
    """legacy 只读面 mock：stats/today 记录调用参数。"""

    def __init__(self):
        self.stats_calls = []

    def stats(self, username=None, exclude_sources=None):
        self.stats_calls.append((username, exclude_sources))
        return {"categories": [], "total_questions": 0}

    async def today(self, username=None, position=None):
        return {"question": "今日复习题", "topic": "", "category": "", "difficulty": "medium"}


async def _start(s):
    return await s["svc"].start("Java后端", username="u1")


# ---------------------------------------------------------------- 9. legacy contract 兼容

@pytest.mark.asyncio
async def test_agent_service_legacy_contract(env_dir):
    s = build_stack(env_dir, max_rounds=1)
    fake_legacy = FakeLegacyReadonly()
    s["svc"]._legacy_readonly = fake_legacy  # 注入只读委托

    # start（legacy 形状）
    res = await _start(s)
    assert set(res) == {"session_id", "question"}
    assert {"id", "content", "round", "difficulty", "source", "knowledge_tags", "topic", "category"} <= set(res["question"])
    sid = res["session_id"]

    # get_report：完成前 None，完成后 dict
    assert await s["svc"].get_report(sid, username="u1") is None
    ans = await s["svc"].answer(res["question"]["id"], "回答内容足够长避免追问：" + "c" * 300, username="u1")
    assert ans["is_complete"] is True
    report = await s["svc"].get_report(sid, username="u1")
    assert report and report["total_score"] is not None

    # end 形状
    end_res = await s["svc"].end(sid, username="u1")
    assert end_res["session_id"] == sid and end_res["report"]

    # get_detail / history
    detail = s["svc"].get_detail(sid, username="u1")
    assert detail["session"]["id"] == sid and detail["questions"]
    hist = s["svc"].history(username="u1")
    assert any(h["id"] == sid for h in hist)

    # stats / today 委托 legacy
    st = s["svc"].stats(username="u1")
    assert st == {"categories": [], "total_questions": 0}
    assert fake_legacy.stats_calls[-1] == ("u1", ("followup",))  # F9：exclude followup
    td = await s["svc"].today(username="u1")
    assert td["question"] == "今日复习题"

    # store / topic_tracker 属性（coverage API 兼容）
    assert s["svc"].store.owns_session(sid, "u1") is True
    assert hasattr(s["svc"], "topic_tracker")
    cov = s["svc"].topic_tracker.get_coverage(sid, "Java后端")
    assert isinstance(cov, dict)


@pytest.mark.asyncio
async def test_authorization_enforced(env_dir):
    s = build_stack(env_dir, max_rounds=1)
    res = await _start(s)  # username="u1"
    with pytest.raises(AuthorizationError):
        await s["svc"].answer(res["question"]["id"], "回答内容足够长避免追问：" + "a" * 300, username="other")


# ---------------------------------------------------------------- F9：coverage 过滤 followup

def test_agent_topic_tracker_filters_followup(env_dir):
    from app.storage.interview_store import InterviewStore

    store = InterviewStore(db_path=str(env_dir / "coverage.db"))
    base = TopicTracker(interview_store=store, tree_dir=REAL_TREE_DIR)
    agent_tracker = AgentTopicTracker(interview_store=store, tree_dir=REAL_TREE_DIR)

    sid = store.create_session("Java后端", username="u1")["id"]
    store.add_question(sid, 1, "主问题", difficulty="medium", source="llm", topic="JVM", category="JVM")
    # followup 行 topic 与主问题不同：未过滤时计入 2 个 topic，过滤后仅主问题
    store.add_question(sid, 1, "追问", difficulty="medium", source="followup", topic="Redis", category="Redis")

    cov_base = base.get_coverage(sid, "Java后端")
    cov_agent = agent_tracker.get_coverage(sid, "Java后端")
    assert cov_base["total_covered"] == 2  # 未过滤：主+追问都计入
    assert cov_agent["total_covered"] == 1  # 过滤：仅主问题


def test_topic_tracker_get_coverage_exclude_sources_param(env_dir):
    from app.storage.interview_store import InterviewStore

    store = InterviewStore(db_path=str(env_dir / "cov2.db"))
    tracker = TopicTracker(interview_store=store, tree_dir=REAL_TREE_DIR)
    sid = store.create_session("Java后端", username="u1")["id"]
    store.add_question(sid, 1, "主", source="llm", topic="JVM", category="JVM")
    store.add_question(sid, 1, "追", source="followup", topic="Redis", category="Redis")
    assert tracker.get_coverage(sid, "Java后端")["total_covered"] == 2
    assert tracker.get_coverage(sid, "Java后端", exclude_sources=("followup",))["total_covered"] == 1


# ---------------------------------------------------------------- build_agent_service 装配

def test_build_agent_service_wires_full_stack(env_dir):
    from app.services.agent.agent_service import build_agent_service
    from app.services.agent.tools import ToolRegistry
    from app.storage.interview_store import InterviewStore

    store = InterviewStore(db_path=str(env_dir / "factory.db"))

    class FakeLLM:
        async def chat(self, prompt, system=None):
            return '{"question": "q?", "difficulty": "medium", "knowledge_tags": ["t"]}'

    tracker = TopicTracker(interview_store=store, tree_dir=str(env_dir))
    svc = build_agent_service(
        store=store, llm=FakeLLM(), facade=None, topic_tracker=tracker,
        trace_dir=str(env_dir / "traces"),
        escape_config=EscapeHatchConfig(max_rounds=1),
    )
    assert isinstance(svc, AgentService)
    assert isinstance(svc.orchestrator.tools, ToolRegistry)
    assert svc.topic_tracker is not None
    assert svc.store is store
