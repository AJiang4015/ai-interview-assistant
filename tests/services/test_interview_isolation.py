# tests/services/test_interview_isolation.py
# 用户复习画像隔离：按用户聚合、越权 403、存量数据归属
import pytest

from app.exceptions import AuthorizationError
from app.services.interview_service import InterviewService
from app.storage.interview_store import InterviewStore


@pytest.fixture()
def store(tmp_path):
    s = InterviewStore(db_path=str(tmp_path / "interviews-test.db"))
    yield s
    s = None


def _make_completed_session(store, username, position, questions):
    """造一场已完成面试：questions=[(category, topic, score, round)]。"""
    s = store.create_session(position, username=username)
    for i, (category, topic, score) in enumerate(questions, start=1):
        q = store.add_question(s["id"], i, f"题目{i}", topic=topic, category=category)
        store.update_answer(q["id"], "回答", {"tags": ["t"]}, score)
    store.complete_session(s["id"], {"total_score": sum(q[2] for q in questions)})
    return s["id"]


def test_stats_scopes_by_user(store):
    # A 有 2 场：Java 薄弱（4分）、其余正常
    _make_completed_session(store, "alice", "Java后端",
                            [("Java", "并发", 4.0), ("Java", "JVM", 6.0)])
    _make_completed_session(store, "alice", "Java后端",
                            [("Redis", "缓存穿透", 5.0)])
    # B 有一场高分，不应混入 A 的画像
    _make_completed_session(store, "bob", "Go后端",
                            [("Go", "channel", 9.0)])

    svc = InterviewService(store=store, llm=None)

    alice_stats = svc.stats(username="alice")
    assert alice_stats["total_questions"] == 3
    cats = {c["category"] for c in alice_stats["categories"]}
    assert cats == {"Java", "Redis"}  # 不含 Go

    bob_stats = svc.stats(username="bob")
    assert "Java" not in {c["category"] for c in bob_stats["categories"]}
    assert bob_stats["total_questions"] == 1

    # history 仅返回本人的场次
    assert {s["position"] for s in svc.history(username="alice")} == {"Java后端"}
    assert {s["position"] for s in svc.history(username="bob")} == {"Go后端"}


def test_legacy_unclaimed_is_forbidden(store):
    # 直接插入未认领（username=''）的旧场次
    with store._get_conn() as conn:
        conn.execute(
            """INSERT INTO interview_sessions (id, position, status, username)
               VALUES ('legacy1', 'Java后端', 'completed', '')"""
        )

    svc = InterviewService(store=store, llm=None)

    # 未认领存量数据：任何登录用户（含空归属判定）都判定无权访问
    assert store.owns_session("legacy1", "alice") is False
    assert store.list_sessions(username="alice") == []  # 不出现在用户画像
    with pytest.raises(AuthorizationError):
        svc._authorize("legacy1", "alice")


def test_legacy_claimed_to_owner(store, monkeypatch):
    monkeypatch.setattr("app.config.settings.legacy_data_owner", "admin")
    # 重新执行建库（含认领迁移）把存量 username='' 归到 admin
    with store._get_conn() as conn:
        conn.execute(
            """INSERT INTO interview_sessions (id, position, status, username)
               VALUES ('l2', 'Java后端', 'completed', '')"""
        )
    store._init_db()

    assert store.owns_session("l2", "admin") is True
    assert store.owns_session("l2", "alice") is False


def test_authorize_rejects_foreign_session(store):
    sid = _make_completed_session(store, "alice", "Java后端",
                                  [("Java", "并发", 7.0)])
    svc = InterviewService(store=store, llm=None)

    assert store.owns_session(sid, "alice") is True
    assert store.owns_session(sid, "bob") is False
    with pytest.raises(AuthorizationError):
        svc._authorize(sid, "bob")
    # 不传 username（内部调用）不校验，保持兼容
    svc._authorize(sid, None)