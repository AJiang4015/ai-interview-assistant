import json
from typing import Optional

import redis
from redis.asyncio import Redis

from app.utils.logger import get_logger

logger = get_logger(__name__)


class SessionStore:
    """Redis-based conversation session storage.

    Stores conversation history as JSON with configurable TTL.
    Supports multi-turn dialogues with session management.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        ttl_seconds: int = 3600,
        max_history_turns: int = 20,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
        self.ttl_seconds = ttl_seconds
        self.max_history_turns = max_history_turns
        self._client: Optional[Redis] = None

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self._client = redis.asyncio.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password,
                decode_responses=True,
            )
            await self._client.ping()
            logger.info(f"Connected to Redis at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._client = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    @property
    def client(self):
        return self._client

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    def _session_key(self, session_id: str) -> str:
        """Generate Redis key for a session."""
        return f"session:{session_id}"

    def _messages_key(self, session_id: str) -> str:
        """Generate Redis key for session messages."""
        return f"session:{session_id}:messages"

    async def create_session(self, session_id: str) -> dict:
        """Create a new session."""
        if not self._client:
            raise ConnectionError("Redis not connected")

        session_data = {
            "session_id": session_id,
            "created_at": self._now(),
            "updated_at": self._now(),
            "turn_count": 0,
        }

        key = self._session_key(session_id)
        await self._client.set(key, json.dumps(session_data), ex=self.ttl_seconds)
        logger.info(f"Session created: {session_id}")
        return session_data

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get session metadata."""
        if not self._client:
            return None

        key = self._session_key(session_id)
        data = await self._client.get(key)
        if data:
            return json.loads(data)
        return None

    async def session_exists(self, session_id: str) -> bool:
        """Check if session exists."""
        if not self._client:
            return False

        key = self._session_key(session_id)
        return await self._client.exists(key) > 0

    async def add_message(
        self, session_id: str, role: str, content: str, metadata: Optional[dict] = None
    ) -> None:
        """Add a message to the session history."""
        if not self._client:
            raise ConnectionError("Redis not connected")

        if not await self.session_exists(session_id):
            await self.create_session(session_id)

        message = {
            "role": role,
            "content": content,
            "timestamp": self._now(),
        }
        if metadata:
            message["metadata"] = metadata

        msg_key = self._messages_key(session_id)
        await self._client.rpush(msg_key, json.dumps(message, ensure_ascii=False))

        # Trim history if exceeds max turns (keep last N*2 messages)
        max_messages = self.max_history_turns * 2
        msg_count = await self._client.llen(msg_key)
        if msg_count > max_messages:
            await self._client.ltrim(msg_key, msg_count - max_messages, -1)

        # Update session metadata
        session_key = self._session_key(session_id)
        session_data = json.loads(await self._client.get(session_key))
        session_data["turn_count"] += 1
        session_data["updated_at"] = self._now()
        await self._client.set(
            session_key, json.dumps(session_data), ex=self.ttl_seconds
        )

        # Refresh TTL on messages key too
        await self._client.expire(msg_key, self.ttl_seconds)

    async def get_history(self, session_id: str) -> list[dict]:
        """Get full conversation history."""
        if not self._client:
            return []

        msg_key = self._messages_key(session_id)
        raw_messages = await self._client.lrange(msg_key, 0, -1)
        return [json.loads(msg) for msg in raw_messages]

    async def get_recent_messages(
        self, session_id: str, turns: int = 5
    ) -> list[dict]:
        """Get recent N turns of conversation history."""
        if not self._client:
            return []

        msg_key = self._messages_key(session_id)
        # turns * 2 because each turn has user + assistant message
        count = turns * 2
        raw_messages = await self._client.lrange(msg_key, -count, -1)
        return [json.loads(msg) for msg in raw_messages]

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        if not self._client:
            return False

        keys = [self._session_key(session_id), self._messages_key(session_id)]
        deleted = await self._client.delete(*keys)
        logger.info(f"Session deleted: {session_id}, keys removed: {deleted}")
        return deleted > 0

    async def clear_all_sessions(self) -> int:
        """Clear all sessions (use with caution)."""
        if not self._client:
            return 0

        # Find and delete all session keys
        cursor = 0
        total_deleted = 0
        while True:
            cursor, keys = await self._client.scan(
                cursor=cursor, match="session:*", count=100
            )
            if keys:
                deleted = await self._client.delete(*keys)
                total_deleted += deleted
            if cursor == 0:
                break

        logger.info(f"Cleared {total_deleted} session keys")
        return total_deleted

    async def get_session_count(self) -> int:
        """Get total number of active sessions."""
        if not self._client:
            return 0

        cursor = 0
        count = 0
        while True:
            cursor, keys = await self._client.scan(
                cursor=cursor, match="session:*", count=100
            )
            # Filter out message keys (session:{id}:messages)
            session_keys = [k for k in keys if k.count(":") == 1]
            count += len(session_keys)
            if cursor == 0:
                break
        return count

    async def list_sessions(self) -> list[dict]:
        """List all active sessions with metadata."""
        if not self._client:
            return []

        cursor = 0
        session_keys = []
        while True:
            cursor, keys = await self._client.scan(
                cursor=cursor, match="session:*", count=100
            )
            for key in keys:
                if key.count(":") == 1:
                    session_keys.append(key)
            if cursor == 0:
                break

        sessions = []
        for key in session_keys:
            data = await self._client.get(key)
            if data:
                try:
                    session = json.loads(data)
                    session_id = session["session_id"]
                    title = await self._get_session_title(session_id)
                    session["title"] = title
                    sessions.append(session)
                except (json.JSONDecodeError, KeyError):
                    continue

        sessions.sort(key=lambda s: s.get("updated_at", ""), reverse=True)
        return sessions

    async def _get_session_title(self, session_id: str) -> str:
        """Generate a title for the session from the first user message."""
        msg_key = self._messages_key(session_id)
        raw_messages = await self._client.lrange(msg_key, 0, 0)
        if raw_messages:
            try:
                first_msg = json.loads(raw_messages[0])
                if first_msg.get("role") == "user":
                    content = first_msg.get("content", "")
                    return content[:30] + "..." if len(content) > 30 else content
            except (json.JSONDecodeError, KeyError):
                pass
        return f"会话 {session_id[:8]}"

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()
