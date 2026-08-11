import json
from typing import Optional

import redis
from redis.asyncio import Redis

from app.utils.logger import get_logger

logger = get_logger(__name__)


class UserStore:
    """Redis-based user storage for authentication.

    Stores user accounts with hashed passwords and metadata.
    Uses Redis Hash and String data structures.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
    ):
        self.host = host
        self.port = port
        self.db = db
        self.password = password
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
            logger.info(f"UserStore connected to Redis at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to connect UserStore to Redis: {e}")
            self._client = None

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("UserStore Redis connection closed")

    @property
    def is_connected(self) -> bool:
        return self._client is not None

    def _user_key(self, username: str) -> str:
        """Generate Redis key for a user."""
        return f"user:{username}"

    def _username_index_key(self) -> str:
        """Generate Redis key for username→user_id index."""
        return "user:index:usernames"

    async def create_user(
        self, username: str, password_hash: str, display_name: str | None = None
    ) -> dict:
        """Create a new user."""
        if not self._client:
            raise ConnectionError("Redis not connected")

        key = self._user_key(username)
        if await self._client.exists(key):
            raise ValueError(f"User '{username}' already exists")

        user_data = {
            "username": username,
            "password_hash": password_hash,
            "display_name": display_name or username,
            "created_at": self._now(),
        }

        await self._client.set(key, json.dumps(user_data, ensure_ascii=False))
        # Add to username index
        await self._client.sadd(self._username_index_key(), username)

        logger.info(f"User created: {username}")
        return self._sanitize_user(user_data)

    async def get_user(self, username: str) -> Optional[dict]:
        """Get user by username (without password hash)."""
        if not self._client:
            return None

        key = self._user_key(username)
        data = await self._client.get(key)
        if not data:
            return None

        user_data = json.loads(data)
        return self._sanitize_user(user_data)

    async def get_user_with_password(self, username: str) -> Optional[dict]:
        """Get user by username including password hash (for auth)."""
        if not self._client:
            return None

        key = self._user_key(username)
        data = await self._client.get(key)
        if not data:
            return None

        return json.loads(data)

    async def user_exists(self, username: str) -> bool:
        """Check if user exists."""
        if not self._client:
            return False

        key = self._user_key(username)
        return await self._client.exists(key) > 0

    async def list_users(self) -> list[dict]:
        """List all users (without password hashes)."""
        if not self._client:
            return []

        index_key = self._username_index_key()
        usernames = await self._client.smembers(index_key)

        users = []
        for username in usernames:
            user = await self.get_user(username)
            if user:
                users.append(user)

        return sorted(users, key=lambda u: u.get("created_at", ""))

    async def delete_user(self, username: str) -> bool:
        """Delete a user."""
        if not self._client:
            return False

        key = self._user_key(username)
        deleted = await self._client.delete(key)

        index_key = self._username_index_key()
        await self._client.srem(index_key, username)

        logger.info(f"User deleted: {username}")
        return deleted > 0

    def _sanitize_user(self, user_data: dict) -> dict:
        """Remove sensitive fields from user data."""
        return {
            "username": user_data["username"],
            "display_name": user_data.get("display_name", user_data["username"]),
            "created_at": user_data.get("created_at", ""),
        }

    @staticmethod
    def _now() -> str:
        from datetime import datetime, timezone

        return datetime.now(timezone.utc).isoformat()