# tests/storage/test_deep_dive_store.py
import pytest
from app.storage.deep_dive_store import DeepDiveStore

@pytest.fixture
def store(tmp_path):
    return DeepDiveStore(db_path=str(tmp_path / "dd.db"))

def test_create_and_get_session(store):
    s = store.create_session("RAG知识库", "Rerank", "构建问答系统")
    got = store.get_session(s["id"])
    assert got["project_name"] == "RAG知识库"
    assert got["status"] == "in_progress"

def test_question_round_trip(store):
    s = store.create_session("P", "T", "d")
    q = store.add_question(s["id"], 1, "为什么不直接向量检索?")
    store.update_answer(q["id"], "因为要重排", 6.0, {"ok": True})
    qs = store.get_questions(s["id"])
    assert len(qs) == 1 and qs[0]["answer"] == "因为要重排"

def test_complete_session(store):
    s = store.create_session("P", "T", "d")
    store.complete_session(s["id"], "薄弱点: Rerank原理")
    assert store.get_session(s["id"])["status"] == "completed"

def test_list_sessions(store):
    s1 = store.create_session("P1", "T1", "d")
    s2 = store.create_session("P2", "T2", "d")
    sessions = store.list_sessions()
    assert len(sessions) >= 2