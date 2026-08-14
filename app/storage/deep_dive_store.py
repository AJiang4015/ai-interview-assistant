# app/storage/deep_dive_store.py
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)


class DeepDiveStore:
    """SQLite storage for project deep-dive sessions."""

    def __init__(self, db_path: str = "data/interviews.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS deep_dive_sessions (
                    id           TEXT PRIMARY KEY,
                    project_name TEXT NOT NULL,
                    tech_point   TEXT NOT NULL,
                    description  TEXT DEFAULT '',
                    status       TEXT NOT NULL DEFAULT 'in_progress',
                    summary      TEXT DEFAULT '',
                    start_round  INTEGER DEFAULT 0,
                    created_at   TEXT
                );
                CREATE TABLE IF NOT EXISTS deep_dive_questions (
                    id         TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    round      INTEGER NOT NULL,
                    question   TEXT NOT NULL,
                    answer     TEXT DEFAULT '',
                    score      REAL DEFAULT 0,
                    judgment   TEXT DEFAULT '{}',
                    created_at TEXT,
                    FOREIGN KEY (session_id) REFERENCES deep_dive_sessions(id)
                );
                CREATE INDEX IF NOT EXISTS idx_ddq_session ON deep_dive_questions(session_id);
            """)

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def create_session(self, project_name: str, tech_point: str, description: str = "") -> dict:
        sid = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO deep_dive_sessions (id, project_name, tech_point, description, status, created_at)
                   VALUES (?, ?, ?, ?, 'in_progress', ?)""",
                (sid, project_name, tech_point, description, self._now()),
            )
        return {"id": sid, "project_name": project_name, "tech_point": tech_point,
                "description": description, "status": "in_progress"}

    def add_question(self, session_id: str, round_num: int, question: str) -> dict:
        qid = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO deep_dive_questions (id, session_id, round, question, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (qid, session_id, round_num, question, self._now()),
            )
            conn.execute("UPDATE deep_dive_sessions SET start_round = ? WHERE id = ?",
                         (round_num, session_id))
        return {"id": qid, "session_id": session_id, "round": round_num, "question": question}

    def update_answer(self, question_id: str, answer: str, score: float, judgment: dict):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE deep_dive_questions SET answer = ?, score = ?, judgment = ? WHERE id = ?",
                (answer, score, json.dumps(judgment, ensure_ascii=False), question_id),
            )

    def get_session(self, session_id: str) -> dict | None:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM deep_dive_sessions WHERE id = ?",
                               (session_id,)).fetchone()
            return dict(row) if row else None

    def get_questions(self, session_id: str) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM deep_dive_questions WHERE session_id = ? ORDER BY round ASC",
                (session_id,)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["judgment"] = json.loads(d.get("judgment") or "{}")
                out.append(d)
            return out

    def complete_session(self, session_id: str, summary_text: str):
        with self._get_conn() as conn:
            conn.execute(
                "UPDATE deep_dive_sessions SET status = 'completed', summary = ? WHERE id = ?",
                (summary_text, session_id),
            )

    def list_sessions(self, limit: int = 50) -> list[dict]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM deep_dive_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,)).fetchall()
            return [dict(r) for r in rows]