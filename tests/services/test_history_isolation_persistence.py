"""问答历史用户隔离 + 长期持久化（短期/长期记忆）回归测试。

覆盖：
- SearchStore 表迁移（username/updated_at 幂等补列）与存量 legacy 行不可见
- SearchStore 按用户列出/搜索/归属/按用户清空
- RAGService resolve_session：新建绑定 / Redis miss→SQLite 恢复回填 / 越权拒绝
- RAGService get_session_history 越权返回 None
- RAGService list_sessions 合并 Redis 活跃会话与 SQLite 长期会话
"""

import asyncio
import sqlite3

import pytest

from app.services.rag_service import RAGService
from app.storage.search_store import SearchStore


# ---------------------- FakeSessionStore ----------------------
# 仅实现判活/建会话/归属/增删/列举所需接口，避免依赖真实 Redis。
class FakeSessionStore:
    def __init__(self):
        self.is_connected = True
        self.sessions: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}

    async def create_session(self, session_id, username=None):
        self.sessions[session_id] = {"session_id": session_id, "username": username}

    async def is_session_owned(self, session_id, username):
        if session_id not in self.sessions:
            return None
        return self.sessions[session_id].get("username") == username

    async def add_message(self, session_id, role, content, metadata=None):
        if session_id not in self.sessions:
            await self.create_session(session_id)
        self.messages.setdefault(session_id, []).append(
            {"role": role, "content": content, "timestamp": "", "metadata": metadata or {}}
        )

    async def get_history(self, session_id):
        return self.messages.get(session_id, [])

    async def get_session(self, session_id):
        return self.sessions.get(session_id)

    async def delete_session(self, session_id):
        self.sessions.pop(session_id, None)
        self.messages.pop(session_id, None)
        return True

    async def list_sessions(self, username):
        return [s for s in self.sessions.values() if s.get("username") == username]

    async def clear_user_sessions(self, username):
        ids = [sid for sid, s in self.sessions.items() if s.get("username") == username]
        for sid in ids:
            self.sessions.pop(sid, None)
            self.messages.pop(sid, None)
        return len(ids)


def make_rag(store_path, fake_session):
    search = SearchStore(store_path)
    return RAGService(
        faiss_store=None,
        embedding=None,
        llm=None,
        session_store=fake_session,
        search_store=search,
    ), search


def run(coro):
    return asyncio.run(coro)


# ---------------------- SearchStore ----------------------

def test_legacy_schema_migration_adds_columns(tmp_path):
    """存量库（无 username/updated_at）初始化时幂等补列，legacy 行不可见。"""
    db = tmp_path / "legacy.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE sessions (session_id TEXT PRIMARY KEY, title TEXT, created_at TEXT);
            CREATE TABLE messages (id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL, role TEXT NOT NULL, content TEXT NOT NULL,
                created_at TEXT);
            """
        )
        conn.execute(
            "INSERT INTO sessions (session_id, title, created_at) VALUES (?, ?, ?)",
            ("legacy-session", "旧会话", "2020-01-01"),
        )

    store = SearchStore(str(db))
    # 列已补上
    cols = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(sessions)")}
    assert {"username", "updated_at"} <= cols
    # legacy 行归属为空，不出现在任何用户列表
    assert store.list_user_sessions("alice") == []
    # legacy 消息在搜索中不可见（无论归属谁）
    store.index_session("s2", username="alice")
    store.index_message("s2", "user", "如何实现LRU")
    assert store.search("LRU", username="alice") != []
    assert store.search("LRU", username="bob") == []


def test_search_store_user_isolation_and_clear(tmp_path):
    store = SearchStore(str(tmp_path / "s.db"))
    for user, sid, text in [
        ("alice", "a1", "Java掩码问题"),
        ("alice", "a2", "Redis并发"),
        ("bob", "b1", "JVM调优"),
    ]:
        store.index_session(sid, title=text, username=user)
        store.index_message(sid, "user", text)

    # 归属
    assert store.get_session_owner("a1") == "alice"
    assert store.get_session_owner("b1") == "bob"
    assert store.get_session_owner("nope") is None

    # 按用户列出
    alice_ids = {r["session_id"] for r in store.list_user_sessions("alice")}
    assert alice_ids == {"a1", "a2"}
    assert {r["session_id"] for r in store.list_user_sessions("bob")} == {"b1"}

    # 搜索隔离（LIKE 降级路径，用短关键词）
    assert {r["session_id"] for r in store.search("掩码", username="alice")} == {"a1"}
    assert store.search("掩码", username="bob") == []

    # 消息有序可恢复
    msgs = store.get_messages("a1")
    assert [m["role"] for m in msgs] == ["user"]
    assert msgs[0]["content"] == "Java掩码问题"

    # 按用户清空只影响该用户
    assert store.delete_user_sessions("alice") == 2
    assert store.list_user_sessions("alice") == []
    assert {r["session_id"] for r in store.list_user_sessions("bob")} == {"b1"}


# ---------------------- RAGService resolve / restore ----------------------

def test_resolve_new_session_binds_user(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.rag_service.settings.enable_history_persistence", True)
    fake = FakeSessionStore()
    rag, _ = make_rag(tmp_path / "r.db", fake)

    sid = run(rag.resolve_session(None, "alice"))
    assert sid
    assert fake.sessions[sid]["username"] == "alice"


def test_resolve_from_sqlite_restores_after_redis_expiry(tmp_path, monkeypatch):
    """Redis 中会话已过期（无记录），SQLite 有归属数据 → 恢复回填 Redis。"""
    monkeypatch.setattr("app.services.rag_service.settings.enable_history_persistence", True)
    fake = FakeSessionStore()
    rag, search = make_rag(tmp_path / "r.db", fake)

    search.index_session("sx", title="问题", username="alice")
    search.index_message("sx", "user", "第一问")
    search.index_message("sx", "assistant", "第一答")

    sid = run(rag.resolve_session("sx", "alice"))
    assert sid == "sx"
    # 已回填到 Redis(fake)，短期记忆可继续
    assert fake.sessions["sx"]["username"] == "alice"
    roles = [m["role"] for m in fake.messages["sx"]]
    assert roles == ["user", "assistant"]


def test_resolve_rejects_other_users_persisted_session(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.rag_service.settings.enable_history_persistence", True)
    fake = FakeSessionStore()
    rag, search = make_rag(tmp_path / "r.db", fake)
    search.index_session("sx", username="bob")

    assert run(rag.resolve_session("sx", "alice")) is None


def test_get_session_history_unauthorized_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.rag_service.settings.enable_history_persistence", True)
    fake = FakeSessionStore()
    rag, _ = make_rag(tmp_path / "r.db", fake)
    # Redis 中只有 bob 的会话
    run(fake.create_session("bob-session", "bob"))

    history = run(rag.get_session_history("bob-session", "alice"))
    assert history is None


def test_get_session_history_authorized_reads_redis(tmp_path, monkeypatch):
    fake = FakeSessionStore()
    rag, _ = make_rag(tmp_path / "r.db", fake)
    run(fake.create_session("mine", "alice"))
    run(fake.add_message("mine", "user", "你好"))

    history = run(rag.get_session_history("mine", "alice"))
    assert history is not None
    assert history[0]["content"] == "你好"


def test_list_sessions_merges_redis_and_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.rag_service.settings.enable_history_persistence", True)
    fake = FakeSessionStore()
    rag, search = make_rag(tmp_path / "r.db", fake)

    # Redis 活跃会话（alice）
    run(fake.create_session("active", "alice"))
    fake.messages.setdefault("active", [])
    # SQLite 长期会话（alice）
    search.index_session("persisted1", title="历史会话", username="alice")

    result = run(rag.list_sessions("alice"))
    ids = {s["session_id"] for s in result["sessions"]}
    assert ids == {"active", "persisted1"}
    assert result["total_sessions"] == 2
    # bob 看不到 alice 的任何会话
    assert run(rag.list_sessions("bob"))["total_sessions"] == 0