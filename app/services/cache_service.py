import hashlib
import json
from typing import Optional

from app.storage.session_store import SessionStore
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ResponseCache:
    """基于 Redis 的响应缓存，避免相同查询重复生成。"""

    def __init__(
        self,
        session_store: SessionStore | None,
        ttl: int = 3600,
        prefix: str = "cache:rag:",
    ):
        self._store = session_store
        self._ttl = ttl
        self._prefix = prefix

    @property
    def available(self) -> bool:
        return self._store is not None and self._store.is_connected

    def make_key(self, question: str, _session_id: str = "", _msg_count: int = 0) -> str:
        # DR-004 / P001：缓存 key 只基于原始问题原文。
        # session_id / msg_count 等可变维度一律不参与，使相同问题可跨会话、跨轮次命中。
        h = hashlib.md5(question.encode("utf-8")).hexdigest()
        return f"{self._prefix}{h}"

    async def get(self, key: str) -> Optional[dict]:
        if not self.available:
            return None
        try:
            client = self._store.client
            if client is None:
                return None
            data = await client.get(key)
            if data:
                logger.info(f"Cache hit: {key[:40]}...")
                return json.loads(data)
            return None
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None

    async def set(self, key: str, answer: str, sources: list) -> None:
        if not self.available:
            return
        try:
            client = self._store.client
            if client is None:
                return
            payload = json.dumps(
                {"answer": answer, "sources": sources}, ensure_ascii=False
            )
            await client.setex(key, self._ttl, payload)
            logger.info(f"Cache set: {key[:40]}... (TTL={self._ttl}s)")
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")