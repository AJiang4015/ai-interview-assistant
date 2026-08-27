"""SQLite-based conversation search store.

Stores conversation messages for full-text search across sessions.
Synced alongside Redis session store for persistence beyond TTL.
"""

import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class SearchStore:
    """SQLite search index for cross-session conversation retrieval."""

    def __init__(self, db_path: str = "data/search.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"SearchStore initialized at {self.db_path}")

    def _init_db(self):
        """创建表和索引（如果不存在）"""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id   TEXT PRIMARY KEY,
                    title        TEXT,
                    created_at   TEXT
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id   TEXT NOT NULL,
                    role         TEXT NOT NULL,
                    content      TEXT NOT NULL,
                    created_at   TEXT,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_messages_content ON messages(content);
                CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);

                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                    content,
                    session_id UNINDEXED,
                    role UNINDEXED,
                    content='messages',
                    content_rowid='id',
                    tokenize='trigram'
                );

                CREATE TRIGGER IF NOT EXISTS messages_fts_ai AFTER INSERT ON messages BEGIN
                    INSERT INTO messages_fts(rowid, content, session_id, role)
                    VALUES (new.id, new.content, new.session_id, new.role);
                END;

                CREATE TRIGGER IF NOT EXISTS messages_fts_ad AFTER DELETE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content, session_id, role)
                    VALUES ('delete', old.id, old.content, old.session_id, old.role);
                END;

                CREATE TRIGGER IF NOT EXISTS messages_fts_au AFTER UPDATE ON messages BEGIN
                    INSERT INTO messages_fts(messages_fts, rowid, content, session_id, role)
                    VALUES ('delete', old.id, old.content, old.session_id, old.role);
                    INSERT INTO messages_fts(rowid, content, session_id, role)
                    VALUES (new.id, new.content, new.session_id, new.role);
                END;
            """)

            # 迁移：为存量库补全 user 隔离相关列（幂等）
            session_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(sessions)")
            }
            if "username" not in session_cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN username TEXT")
            if "updated_at" not in session_cols:
                conn.execute("ALTER TABLE sessions ADD COLUMN updated_at TEXT")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username)"
            )

            # 迁移现有数据到 FTS5（如果 FTS5 表为空）
            existing_count = conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
            if existing_count == 0:
                conn.execute("""
                    INSERT INTO messages_fts(rowid, content, session_id, role)
                    SELECT id, content, session_id, role FROM messages
                """)
                logger.info("Migrated existing messages to FTS5 index")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def index_session(
        self, session_id: str, title: Optional[str] = None, username: Optional[str] = None
    ):
        """写入或更新会话元数据。username 提供时用于首建归属与用户隔离过滤。"""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO sessions (session_id, title, created_at, updated_at, username)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(session_id) DO UPDATE SET
                           title = COALESCE(excluded.title, sessions.title),
                           updated_at = excluded.updated_at,
                           username = COALESCE(excluded.username, sessions.username)""",
                    (session_id, title, self._now(), self._now(), username)
                )
        except Exception as e:
            logger.error(f"Failed to index session {session_id}: {e}")

    def index_message(self, session_id: str, role: str, content: str):
        """写入一条消息到搜索索引"""
        try:
            with self._get_conn() as conn:
                conn.execute(
                    """INSERT INTO messages (session_id, role, content, created_at)
                       VALUES (?, ?, ?, ?)""",
                    (session_id, role, content, self._now())
                )
        except Exception as e:
            logger.error(f"Failed to index message for session {session_id}: {e}")

    def delete_session(self, session_id: str):
        """删除会话及其所有消息"""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        except Exception as e:
            logger.error(f"Failed to delete session {session_id} from search index: {e}")

    def clear_all(self):
        """清空所有搜索索引数据（包括 FTS5 表）"""
        try:
            with self._get_conn() as conn:
                conn.execute("DELETE FROM messages")
                conn.execute("DELETE FROM sessions")
                # FTS5 内容表通过触发器自动同步，但为确保完全清空，重建 FTS5 索引
                conn.executescript("""
                    INSERT INTO messages_fts(messages_fts) VALUES('rebuild');
                """)
            logger.info("Search index cleared (including FTS5)")
        except Exception as e:
            logger.error(f"Failed to clear search index: {e}")

    def cleanup_expired(self, active_session_ids: set[str]):
        """清理不在活跃会话列表中的过期数据"""
        try:
            with self._get_conn() as conn:
                # 删除所有不在活跃列表中的会话及其消息
                placeholders = ','.join('?' * len(active_session_ids)) if active_session_ids else 'NULL'
                deleted_sessions = conn.execute(
                    f"DELETE FROM sessions WHERE session_id NOT IN ({placeholders})",
                    list(active_session_ids)
                ).rowcount
                deleted_messages = conn.execute(
                    f"DELETE FROM messages WHERE session_id NOT IN ({placeholders})",
                    list(active_session_ids)
                ).rowcount
                if deleted_sessions > 0 or deleted_messages > 0:
                    # 重建 FTS5 索引
                    conn.executescript("""
                        INSERT INTO messages_fts(messages_fts) VALUES('rebuild');
                    """)
                    logger.info(f"Cleaned up {deleted_sessions} expired sessions and {deleted_messages} messages")
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions: {e}")

    def search(self, keyword: str, username: str, limit: int = 50) -> list[dict]:
        """全文搜索消息，使用 FTS5 trigram 分词器（仅返回指定用户可见的会话）

        注意事项：
        - trigram 分词器对少于 3 字符的查询词返回 0 结果（因为无法形成 trigram）
        - 对短词（< 3 字符）自动降级到 LIKE 搜索
        - FTS5 整体失败时降级到 LIKE 搜索
        - username 过滤：SESSION 无归属（legacy，username 为 NULL/空）或归属他人时不可见
        """
        # 短词降级：trigram 对 1-2 字符的词无效
        stripped = keyword.strip()
        if len(stripped) < 3:
            return self._search_like_fallback(stripped, username, limit)

        try:
            with self._get_conn() as conn:
                # trigram 分词器无需特殊转义，直接使用原关键词
                rows = conn.execute(
                    """SELECT m.session_id, m.role, m.content, m.created_at, s.title
                       FROM messages_fts f
                       JOIN messages m ON f.rowid = m.id
                       JOIN sessions s ON m.session_id = s.session_id
                       WHERE messages_fts MATCH ? AND s.username = ?
                       ORDER BY rank
                       LIMIT ?""",
                    (stripped, username, limit)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"FTS5 search failed for '{keyword}': {e}")
            # 降级：使用 LIKE 搜索
            return self._search_like_fallback(stripped, username, limit)

    @staticmethod
    def _should_use_prefix(keyword: str) -> bool:
        """判断是否对关键词使用前缀通配符

        简单条件：不含空格、不含 FTS5 特殊字符、长度合理
        """
        if not keyword or len(keyword) > 30:
            return False
        # 含 FTS5 特殊字符的短语查询不追加通配符
        # 注意：不包含 * 和 "，因为 * 表示已经是通配查询， " 是短语标记
        fts5_special = set("'()+-<>~^:&|")
        if any(c in keyword for c in fts5_special):
            return False
        return True

    @staticmethod
    def _fts5_escape(keyword: str) -> str:
        """转义 FTS5 查询关键词中的特殊字符"""
        # FTS5 特殊字符: + - * & ~ ( ) < > " 等
        # 简单方案：用双引号包裹整个关键词作为短语查询
        # 如果关键词本身包含引号，需要转义
        escaped = keyword.replace('"', '""')
        return f'"{escaped}"'

    def _search_like_fallback(self, keyword: str, username: str, limit: int = 50) -> list[dict]:
        """LIKE 搜索降级方案（限定用户可见会话）"""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """SELECT m.session_id, m.role, m.content, m.created_at, s.title
                       FROM messages m
                       JOIN sessions s ON m.session_id = s.session_id
                       WHERE m.content LIKE ? AND s.username = ?
                       ORDER BY m.created_at DESC
                       LIMIT ?""",
                    (f"%{keyword}%", username, limit)
                ).fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"LIKE fallback search failed for '{keyword}': {e}")
            return []

    def list_user_sessions(self, username: str, limit: int = 100) -> list[dict]:
        """按用户列出长期持久化会话（供 Redis 过期后恢复侧边栏）。"""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """SELECT session_id, title, created_at, updated_at
                       FROM sessions
                       WHERE username = ?
                       ORDER BY COALESCE(updated_at, created_at) DESC
                       LIMIT ?""",
                    (username, limit)
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to list sessions for {username}: {e}")
            return []

    def get_session_owner(self, session_id: str) -> Optional[str]:
        """返回会话归属用户名；会话不存在返回 None。"""
        try:
            with self._get_conn() as conn:
                row = conn.execute(
                    "SELECT username FROM sessions WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                return row["username"] if row else None
        except Exception as e:
            logger.error(f"Failed to get owner for session {session_id}: {e}")
            return None

    def get_messages(self, session_id: str) -> list[dict]:
        """按 id 顺序取回会话全部消息，用于 Redis 过期后恢复历史。"""
        try:
            with self._get_conn() as conn:
                rows = conn.execute(
                    """SELECT role, content, created_at
                       FROM messages WHERE session_id = ?
                       ORDER BY id""",
                    (session_id,),
                ).fetchall()
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Failed to get messages for session {session_id}: {e}")
            return []

    def delete_user_sessions(self, username: str) -> int:
        """删除指定用户的全部会话及其消息，返回删除的会话数。"""
        try:
            with self._get_conn() as conn:
                ids = [r["session_id"] for r in conn.execute(
                    "SELECT session_id FROM sessions WHERE username = ?", (username,)
                ).fetchall()]
                for sid in ids:
                    conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                deleted = conn.execute(
                    "DELETE FROM sessions WHERE username = ?", (username,)
                ).rowcount
                if ids:
                    conn.executescript("""
                        INSERT INTO messages_fts(messages_fts) VALUES('rebuild');
                    """)
                logger.info(f"Deleted {deleted} sessions for user {username}")
                return deleted
        except Exception as e:
            logger.error(f"Failed to delete sessions for {username}: {e}")
            return 0

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
