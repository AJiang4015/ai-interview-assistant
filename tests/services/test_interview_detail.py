# tests/services/test_interview_detail.py
# 面试详情读取：get_detail 逐题返回、纯读取无副作用、越权 403
import asyncio

import pytest

from app.exceptions import AuthorizationError
from app.services.interview_service import InterviewService
from app.storage.interview_store import InterviewStore


@pytest.fixture()
def store(tmp_path):
    s = InterviewStore(db_path=str(tmp_path / "interviews-test.db"))
    yield s
    s = None


def _make_session(store, username, position, n_answered, completed=True):
    """造一场面试：题目数 = n_answered+1（末题为未作答的"当前题"）。"""
    s = store.create_session(position, username=username)
    questions = []
    for i in range(1, n_answered + 2):
        q = store.add_question(s["id"], i, f"题目{i}", topic="并发", category="Java")
        questions.append(q)
    for i, q in enumerate(questions[:n_answered], start=1):
        ev = {"score": i, "comment": f"评价{i}", "tags": ["t1"], "next_difficulty": "medium"}
        store.update_answer(q["id"], f"回答{i}", ev, float(i))
    if completed:
        store.complete_session(s["id"], {"total_score": 999, "level": "优秀"})
    return s["id"]


def test_get_detail_returns_session_and_questions(store):
    sid = _make_session(store, "alice", "Java后端", n_answered=2, completed=True)
    svc = InterviewService(store=store, llm=None)

    detail = svc.get_detail(sid, "alice")
    assert detail is not None
    assert detail["session"]["position"] == "Java后端"
    assert detail["session"]["status"] == "completed"
    assert detail["session"]["total_score"] == 3.0  # 1 + 2

    qs = detail["questions"]
    assert len(qs) == 3
    first = qs[0]
    assert first["question"] == "题目1"
    assert first["answer"] == "回答1"
    assert first["evaluation"]["comment"] == "评价1"
    assert first["evaluation"]["tags"] == ["t1"]
    # 未作答题：answer 为空、evaluation 为空
    last = qs[2]
    assert last["answer"] == ""
    assert last["evaluation"] is None


def test_get_detail_read_only_in_progress(store):
    sid = _make_session(store, "alice", "Java后端", n_answered=1, completed=False)
    svc = InterviewService(store=store, llm=None)

    before = store.get_session(sid)
    detail = svc.get_detail(sid, "alice")
    assert detail["session"]["status"] == "in_progress"
    after = store.get_session(sid)
    # 纯读取：状态不变、不生成报告、无任何写入
    assert after["status"] == "in_progress"
    assert after["report"] is None
    assert after == before


def test_get_detail_authorization(store):
    sid = _make_session(store, "alice", "Java后端", n_answered=1)
    svc = InterviewService(store=store, llm=None)

    # 越权：他人场次禁止访问
    with pytest.raises(AuthorizationError):
        svc.get_detail(sid, "bob")
    # 不存在：返回 None
    assert svc.get_detail("missing", "alice") is None
    # 空归属存量数据：任何登录用户都判定无权访问
    with store._get_conn() as conn:
        conn.execute(
            """INSERT INTO interview_sessions (id, position, status, username)
               VALUES ('legacy_x', 'Java后端', 'in_progress', '')"""
        )
    with pytest.raises(AuthorizationError):
        svc.get_detail("legacy_x", "alice")


def test_get_report_no_side_effect(store):
    # 未完成会话：报告不存在时返回 None，且不得自动生成/落库
    sid = _make_session(store, "alice", "Java后端", n_answered=2, completed=False)
    svc = InterviewService(store=store, llm=None)

    result = asyncio.run(svc.get_report(sid, "alice"))
    assert result is None
    after = store.get_session(sid)
    assert after["report"] is None
    assert after["status"] == "in_progress"

    # 已完成会话且已有报告：原样返回，不改写
    s2 = _make_session(store, "bob", "Go后端", n_answered=1, completed=True)
    r = asyncio.run(svc.get_report(s2, "bob"))
    assert r is not None
    assert r["total_score"] == 999