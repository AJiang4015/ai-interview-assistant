### Task 1: 配置项 + 响应缓存服务

**Files:**
- Create: `app/services/cache_service.py`
- Modify: `app/config.py`（新增配置项）

**Interfaces:**
- Consumes: 无
- Produces: `ResponseCache` 类，`make_key()`, `get()`, `set()` 方法

- [ ] **Step 1: 修改 app/config.py，新增配置项**

在 `class Settings` 中追加以下字段：

```python
# RAG pipeline 配置
rerank_top_k: int = 5
rerank_model: str = "BAAI/bge-reranker-v2-m3"
enable_query_rewrite: bool = True
enable_hybrid_search: bool = True
enable_rerank: bool = True
enable_cache: bool = True
bm25_index_path: str = "data/bm25_index.pkl"
cache_ttl: int = 3600
```

- [ ] **Step 2: 创建 app/services/cache_service.py**

```python
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
            raw = await self._store.redis.get(f"cache:{key}")
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
            await self._store.redis.setex(f"cache:{key}", self._ttl, data)
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
```

- [ ] **Step 3: 验证语法**

Run: `python -c "import ast; ast.parse(open('app/services/cache_service.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add app/config.py app/services/cache_service.py
git commit -m "feat: add config and response cache service"
```