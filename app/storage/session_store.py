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

    def _user_sessions_key(self, username: str) -> str:
        """Per-user session registration set（用于按用户 O(1) 列举与归属过滤）。"""
        return f"user_sessions:{username}"

    async def create_session(self, session_id: str, username: str | None = None) -> dict:
        """Create a new session, optionally bound to a username."""
        if not self._client:
            raise ConnectionError("Redis not connected")

        session_data = {
            "session_id": session_id,
            "username": username,
            "created_at": self._now(),
            "updated_at": self._now(),
            "turn_count": 0,
        }

        key = self._session_key(session_id)
        await self._client.set(key, json.dumps(session_data), ex=self.ttl_seconds)
        if username:
            await self._client.sadd(self._user_sessions_key(username), session_id)
        logger.info(f"Session created: {session_id} (user: {username})")
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

    async def is_session_owned(self, session_id: str, username: str) -> bool | None:
        """校验会话是否属于指定用户。

        返回：True=本人；False=归属他人或旧无归属会话；None=Redis 中会话不存在（可能需从 SQLite 恢复）。
        """
        if not self._client:
            return None
        session = await self.get_session(session_id)
        if not session:
            return None
        return session.get("username") == username

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

        # 记录归属用于同步注销 per-user 集合成员
        owner = None
        data = await self._client.get(self._session_key(session_id))
        if data:
            try:
                owner = json.loads(data).get("username")
            except json.JSONDecodeError:
                pass

        keys = [self._session_key(session_id), self._messages_key(session_id)]
        deleted = await self._client.delete(*keys)
        if owner:
            await self._client.srem(self._user_sessions_key(owner), session_id)
        logger.info(f"Session deleted: {session_id}, keys removed: {deleted}")
        return deleted > 0

    async def clear_user_sessions(self, username: str) -> int:
        """Clear all sessions belonging to a single user."""
        if not self._client:
            return 0

        member_key = self._user_sessions_key(username)
        session_ids = await self._client.smembers(member_key)
        count = 0
        for sid in session_ids:
            keys = [self._session_key(sid), self._messages_key(sid)]
            await self._client.delete(*keys)
            count += 1
        await self._client.delete(member_key)
        logger.info(f"Cleared {count} session keys for user {username}")
        return count

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

    async def list_sessions(self, username: str) -> list[dict]:
        """List all active sessions belonging to the given user.

        通过 per-user 集合索引（`user_sessions:{username}`）O(1) 列举，
        并对归属做二次校验（过滤旧无归属会话，避免借助成员关系泄露）。
        """
        if not self._client:
            return []

        member_key = self._user_sessions_key(username)
        session_ids = await self._client.smembers(member_key)

        sessions = []
        for sid in session_ids:
            data = await self._client.get(self._session_key(sid))
            if data:
                try:
                    session = json.loads(data)
                    if session.get("username") != username:
                        continue
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
