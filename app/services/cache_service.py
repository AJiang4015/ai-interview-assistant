import hashlib
import json
from app.storage.session_store import SessionStore
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ResponseCache:
    def __init__(self, session_store: SessionStore | None, ttl: int = 3600):
        self._store = session_store
        self._ttl = ttl

    @property
    def available(self) -> bool:
        return self._store is not None and self._store.is_connected

    def make_key(self, question: str, session_id: str, msg_count: int) -> str:
        raw = f"{question}|{session_id}|{msg_count}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def get(self, key: str) -> dict | None:
        if not self.available:
            return None
        try:
            raw = await self._store.client.get(f"cache:{key}")
            if raw:
                return json.loads(raw)
            return None
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
            return None

    async def set(self, key: str, answer: str, sources: list):
        if not self.available:
            return
        try:
            data = json.dumps({
                "answer": answer,
                "sources": sources,
                "created_at": __import__("datetime").datetime.now().isoformat(),
            })
            await self._store.client.setex(f"cache:{key}", self._ttl, data)
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")