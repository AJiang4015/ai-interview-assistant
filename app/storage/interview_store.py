"""SQLite-based interview session storage.

Stores interview sessions, questions, and evaluations.
Independent from the existing session store (Redis) and search store (SQLite).
"""

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.utils.logger import get_logger

logger = get_logger(__name__)


class InterviewStore:
    """SQLite storage for interview data."""

    def __init__(self, db_path: str = "data/interviews.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        logger.info(f"InterviewStore initialized at {self.db_path}")

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS interview_sessions (
                    id             TEXT PRIMARY KEY,
                    position       TEXT NOT NULL,
                    status         TEXT NOT NULL DEFAULT 'in_progress',
                    total_rounds   INTEGER DEFAULT 0,
                    total_score    REAL DEFAULT 0,
                    started_at     TEXT,
                    completed_at   TEXT,
                    report         TEXT
                );

                CREATE TABLE IF NOT EXISTS interview_questions (
                    id             TEXT PRIMARY KEY,
                    session_id     TEXT NOT NULL,
                    round          INTEGER NOT NULL,
                    question       TEXT NOT NULL,
                    answer         TEXT DEFAULT '',
                    evaluation     TEXT,
                    score          REAL DEFAULT 0,
                    difficulty     TEXT DEFAULT 'medium',
                    source         TEXT DEFAULT 'kb',
                    created_at     TEXT,
                    FOREIGN KEY (session_id) REFERENCES interview_sessions(id)
                );

                CREATE INDEX IF NOT EXISTS idx_iq_session ON interview_questions(session_id);
            """)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_session(self, position: str) -> dict:
        """Create a new interview session."""
        session_id = str(uuid.uuid4())
        now = self._now()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO interview_sessions (id, position, status, started_at)
                   VALUES (?, ?, 'in_progress', ?)""",
                (session_id, position, now),
            )
        logger.info(f"Interview session created: {session_id} for {position}")
        return {"id": session_id, "position": position, "status": "in_progress", "started_at": now}

    def add_question(self, session_id: str, round_num: int, question: str, difficulty: str = "medium", source: str = "kb") -> dict:
        """Add a question to the interview."""
        qid = str(uuid.uuid4())
        now = self._now()
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO interview_questions (id, session_id, round, question, difficulty, source, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (qid, session_id, round_num, question, difficulty, source, now),
            )
            conn.execute(
                "UPDATE interview_sessions SET total_rounds = ? WHERE id = ?",
                (round_num, session_id),
            )
        return {"id": qid, "session_id": session_id, "round": round_num, "question": question, "difficulty": difficulty}

    def update_answer(self, question_id: str, answer: str, evaluation: dict, score: float):
        """Update a question with user's answer and evaluation."""
        evaluation_json = json.dumps(evaluation, ensure_ascii=False)
        with self._get_conn() as conn:
            conn.execute(
                """UPDATE interview_questions SET answer = ?, evaluation = ?, score = ?
                   WHERE id = ?""",
                (answer, evaluation_json, score, question_id),
            )
            # Update session total score
            row = conn.execute(
                "SELECT session_id FROM interview_questions WHERE id = ?",
                (question_id,),
            ).fetchone()
            if row:
                total = conn.execute(
                    "SELECT SUM(score) FROM interview_questions WHERE session_id = ?",
                    (row["session_id"],),
                ).fetchone()[0]
                conn.execute(
                    "UPDATE interview_sessions SET total_score = ? WHERE id = ?",
                    (total or 0, row["session_id"]),
                )

    def complete_session(self, session_id: str, report: dict):
        """Mark session as completed with report."""
        now = self._now()
        report_json = json.dumps(report, ensure_ascii=False)
        with self._get_conn() as conn:
            conn.execute(
                """UPDATE interview_sessions SET status = 'completed', completed_at = ?, report = ?
                   WHERE id = ?""",
                (now, report_json, session_id),
            )
        logger.info(f"Interview session completed: {session_id}")

    def get_session(self, session_id: str) -> Optional[dict]:
        """Get interview session metadata."""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM interview_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if row:
                data = dict(row)
                if data.get("report"):
                    data["report"] = json.loads(data["report"])
                return data
        return None

    def get_questions(self, session_id: str) -> list[dict]:
        """Get all questions for a session, ordered by round."""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM interview_questions WHERE session_id = ? ORDER BY round ASC",
                (session_id,),
            ).fetchall()
            results = []
            for row in rows:
                d = dict(row)
                if d.get("evaluation"):
                    d["evaluation"] = json.loads(d["evaluation"])
                results.append(d)
            return results

    def get_current_question(self, session_id: str) -> Optional[dict]:
        """Get the latest unanswered question for a session."""
        with self._get_conn() as conn:
            row = conn.execute(
                """SELECT * FROM interview_questions
                   WHERE session_id = ? AND answer = ''
                   ORDER BY round DESC LIMIT 1""",
                (session_id,),
            ).fetchone()
            if row:
                d = dict(row)
                if d.get("evaluation"):
                    d["evaluation"] = json.loads(d["evaluation"])
                return d
        return None

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """List recent interview sessions."""
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT id, position, status, total_rounds, total_score, started_at, completed_at
                   FROM interview_sessions ORDER BY started_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and its questions."""
        with self._get_conn() as conn:
            conn.execute("DELETE FROM interview_questions WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM interview_sessions WHERE id = ?", (session_id,))
        return True

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()