# RAG 管道质量升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 RAG 管道增加重排序、查询改写、混合检索、响应缓存四个模块，提升检索质量和响应速度。

**Architecture:** 在现有 "Embedding → FAISS → LLM" 管道中插入四个独立服务模块，每个模块通过依赖注入集成到 RAGService 中。所有新模块均支持通过配置开关启用/禁用。

**Tech Stack:** Python 3.10+, sentence-transformers, rank_bm25, Redis（已有）, FAISS（已有）

## Global Constraints

- 不修改任何前端代码
- 不修改 session 管理、search store、faiss_store 等已有存储层
- 所有新模块必须支持通过配置开关启用/禁用
- 服务初始化错误不影响应用启动（降级为禁用对应功能）
- 使用 pip 安装新增依赖

---

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

---

### Task 2: 查询改写服务

**Files:**
- Create: `app/services/query_rewrite.py`

**Interfaces:**
- Consumes: `LLMClient`（`app/services/llm_client.py`）
- Produces: `QueryRewriteService` 类，`rewrite(question: str) -> str` 方法

- [ ] **Step 1: 创建 app/services/query_rewrite.py**

```python
from app.services.llm_client import LLMClient
from app.utils.logger import get_logger

logger = get_logger(__name__)

REWRITE_PROMPT = (
    "你是一个检索助手。请将以下面试问题改写为更完整、更利于检索的表述，"
    "包含相关技术关键词，直接输出改写结果，不要多余内容：\n\n{question}"
)


class QueryRewriteService:
    def __init__(self, llm: LLMClient, enabled: bool = True):
        self._llm = llm
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def rewrite(self, question: str) -> str:
        if not self._enabled:
            return question
        try:
            prompt = REWRITE_PROMPT.format(question=question)
            rewritten = await self._llm.chat(prompt)
            rewritten = rewritten.strip().strip('"\'')
            logger.info(f"Query rewritten: '{question[:30]}...' -> '{rewritten[:50]}...'")
            return rewritten if rewritten else question
        except Exception as e:
            logger.warning(f"Query rewrite failed, using original: {e}")
            return question
```

- [ ] **Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('app/services/query_rewrite.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/query_rewrite.py
git commit -m "feat: add query rewrite service"
```

---

### Task 3: 重排序服务

**Files:**
- Create: `app/services/rerank_service.py`

**Interfaces:**
- Consumes: 无（本地加载模型）
- Produces: `RerankService` 类，`rerank(query, documents, top_k) -> list[RerankResult]`

- [ ] **Step 1: 安装依赖**

Run: `pip install sentence-transformers torch`

- [ ] **Step 2: 创建 app/services/rerank_service.py**

```python
from dataclasses import dataclass
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RerankResult:
    index: int
    score: float
    content: str


class RerankService:
    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3", enabled: bool = True):
        self._model_name = model_name
        self._enabled = enabled
        self._model = None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load_model(self):
        if self._model is not None:
            return
        logger.info(f"Loading reranker model: {self._model_name}")
        from sentence_transformers import CrossEncoder
        self._model = CrossEncoder(self._model_name)
        logger.info(f"Reranker model loaded: {self._model_name}")

    async def rerank(
        self, query: str, documents: list[str], top_k: int = 5
    ) -> list[RerankResult]:
        if not self._enabled or not documents:
            return [
                RerankResult(index=i, score=1.0, content=doc)
                for i, doc in enumerate(documents[:top_k])
            ]

        if self._model is None:
            self.load_model()

        pairs = [[query, doc] for doc in documents]
        scores = self._model.predict(pairs)
        scored = list(enumerate(zip(scores, documents)))
        scored.sort(key=lambda x: x[1][0], reverse=True)

        return [
            RerankResult(index=idx, score=float(score), content=doc)
            for idx, (score, doc) in scored[:top_k]
        ]
```

- [ ] **Step 3: 验证语法**

Run: `python -c "import ast; ast.parse(open('app/services/rerank_service.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add app/services/rerank_service.py
git commit -m "feat: add rerank service with bge-reranker-v2-m3"
```

---

### Task 4: 混合检索服务

**Files:**
- Create: `app/services/retrieval_service.py`

**Interfaces:**
- Consumes: `FaissStore`（`app/storage/faiss_store.py`），`EmbeddingService`（`app/services/embedding.py`）
- Produces: `HybridRetriever` 类，`retrieve(query, top_k) -> list[SearchResult]`

- [ ] **Step 1: 安装依赖**

Run: `pip install rank_bm25`

- [ ] **Step 2: 创建 app/services/retrieval_service.py**

```python
import pickle
from pathlib import Path
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from app.storage.faiss_store import FaissStore, SearchResult
from app.services.embedding import EmbeddingService
from app.utils.logger import get_logger

logger = get_logger(__name__)

RRF_K = 60


@dataclass
class RetrievalResult:
    chunk_id: int
    source_file: str
    chunk_index: int
    content: str
    score: float


class HybridRetriever:
    def __init__(
        self,
        faiss_store: FaissStore,
        embedding: EmbeddingService,
        bm25_index_path: str = "data/bm25_index.pkl",
        enabled: bool = True,
    ):
        self._faiss = faiss_store
        self._embedding = embedding
        self._bm25_path = Path(bm25_index_path)
        self._enabled = enabled
        self._bm25: BM25Okapi | None = None
        self._bm25_docs: list[dict] = []

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def bm25_loaded(self) -> bool:
        return self._bm25 is not None

    def load_bm25(self):
        if self._bm25 is not None:
            return
        if not self._bm25_path.exists():
            logger.warning(f"BM25 index not found at {self._bm25_path}")
            return
        with open(self._bm25_path, "rb") as f:
            data = pickle.load(f)
        self._bm25 = data["bm25"]
        self._bm25_docs = data["documents"]
        logger.info(f"BM25 index loaded: {len(self._bm25_docs)} documents")

    def save_bm25(self, documents: list[dict]):
        tokenized = [self._tokenize(doc["content"]) for doc in documents]
        self._bm25 = BM25Okapi(tokenized)
        self._bm25_docs = documents
        self._bm25_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._bm25_path, "wb") as f:
            pickle.dump({"bm25": self._bm25, "documents": documents}, f)
        logger.info(f"BM25 index saved: {len(documents)} documents to {self._bm25_path}")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().split()

    async def _dense_search(self, query: str, top_k: int) -> list[SearchResult]:
        query_vector = await self._embedding.encode([query])
        if query_vector.size == 0:
            return []
        return self._faiss.search(query_vector[0], top_k)

    def _sparse_search(self, query: str, top_k: int) -> list[RetrievalResult]:
        if self._bm25 is None:
            return []
        tokenized = self._tokenize(query)
        scores = self._bm25.get_scores(tokenized)
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            if scores[idx] <= 0:
                continue
            doc = self._bm25_docs[idx]
            results.append(RetrievalResult(
                chunk_id=doc.get("_id", idx),
                source_file=doc.get("source_file", ""),
                chunk_index=doc.get("chunk_index", 0),
                content=doc["content"],
                score=float(scores[idx]),
            ))
        return results

    def _rrf_merge(
        self, dense_results: list, sparse_results: list, top_k: int
    ) -> list[RetrievalResult]:
        """RRF 融合：给每个文档计算 RRF 分数，取 top_k。"""
        scores: dict[int, float] = {}
        doc_map: dict[int, RetrievalResult] = {}

        for rank, r in enumerate(dense_results):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (RRF_K + rank)
            doc_map[r.chunk_id] = RetrievalResult(
                chunk_id=r.chunk_id, source_file=r.source_file,
                chunk_index=r.chunk_index, content=r.content,
                score=0.0,
            )

        for rank, r in enumerate(sparse_results):
            scores[r.chunk_id] = scores.get(r.chunk_id, 0) + 1.0 / (RRF_K + rank)
            if r.chunk_id not in doc_map:
                doc_map[r.chunk_id] = RetrievalResult(
                    chunk_id=r.chunk_id, source_file=r.source_file,
                    chunk_index=r.chunk_index, content=r.content,
                    score=0.0,
                )

        sorted_ids = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        results = []
        for cid in sorted_ids[:top_k]:
            result = doc_map[cid]
            result.score = scores[cid]
            results.append(result)
        return results

    async def retrieve(self, query: str, top_k: int = 20) -> list[RetrievalResult]:
        if not self._enabled:
            dense = await self._dense_search(query, top_k)
            return [
                RetrievalResult(
                    chunk_id=r.chunk_id, source_file=r.source_file,
                    chunk_index=r.chunk_index, content=r.content,
                    score=r.score,
                )
                for r in dense
            ]

        dense_results = await self._dense_search(query, top_k)
        sparse_results = self._sparse_search(query, top_k)

        if not sparse_results:
            return [
                RetrievalResult(
                    chunk_id=r.chunk_id, source_file=r.source_file,
                    chunk_index=r.chunk_index, content=r.content,
                    score=r.score,
                )
                for r in dense_results
            ]

        return self._rrf_merge(dense_results, sparse_results, top_k)
```

- [ ] **Step 3: 验证语法**

Run: `python -c "import ast; ast.parse(open('app/services/retrieval_service.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 4: Commit**

```bash
git add app/services/retrieval_service.py
git commit -m "feat: add hybrid retrieval service with BM25 + RRF"
```

---

### Task 5: 索引构建集成 BM25

**Files:**
- Modify: `app/services/index_service.py`

**Interfaces:**
- Consumes: `HybridRetriever`（Task 4）的 `save_bm25()` 方法
- Produces: 在索引构建时同步写入 BM25 索引

- [ ] **Step 1: 修改 app/services/index_service.py**

在 `IndexService.__init__` 中增加 `hybrid_retriever` 参数，在 `build_index` 末尾调用 `save_bm25`。

修改 `__init__`：

```python
class IndexService:
    def __init__(
        self,
        faiss_store: FaissStore,
        doc_store: DocStore,
        embedding: EmbeddingService,
        hybrid_retriever=None,
    ):
        self.faiss = faiss_store
        self.doc_store = doc_store
        self.embedding = embedding
        self.hybrid_retriever = hybrid_retriever  # 可选
        self.splitter = MarkdownSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
        )
```

在 `build_index` 方法的 `self.doc_store.save(chunks)` 之后追加：

```python
        # 同步构建 BM25 索引
        if self.hybrid_retriever:
            bm25_docs = []
            for idx, c in enumerate(chunks):
                doc = {**c, "_id": idx}
                bm25_docs.append(doc)
            self.hybrid_retriever.save_bm25(bm25_docs)
```

- [ ] **Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('app/services/index_service.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: Commit**

```bash
git add app/services/index_service.py
git commit -m "feat: integrate BM25 index building into IndexService"
```

---

### Task 6: RAGService 重构集成

**Files:**
- Modify: `app/services/rag_service.py`

**Interfaces:**
- Consumes: `QueryRewriteService`, `HybridRetriever`, `RerankService`, `ResponseCache`
- Produces: 集成后的 `RAGService.query()` 和 `RAGService.stream_query()`

- [ ] **Step 1: 修改 app/services/rag_service.py 的 __init__**

```python
class RAGService:
    def __init__(
        self,
        faiss_store: FaissStore,
        embedding: EmbeddingService,
        llm: LLMClient,
        session_store: SessionStore | None = None,
        search_store: SearchStore | None = None,
        query_rewriter=None,      # QueryRewriteService | None
        hybrid_retriever=None,    # HybridRetriever | None
        reranker=None,            # RerankService | None
        cache_service=None,       # ResponseCache | None
    ):
        self.faiss = faiss_store
        self.embedding = embedding
        self.llm = llm
        self.session_store = session_store
        self.search_store = search_store
        self.query_rewriter = query_rewriter
        self.hybrid_retriever = hybrid_retriever
        self.reranker = reranker
        self.cache = cache_service
        self.top_k = settings.top_k
```

- [ ] **Step 2: 在 stream_query 中集成完整管道**

替换 `stream_query` 方法，集成四个新模块：

```python
    async def stream_query(
        self, question: str, session_id: str | None = None
    ):
        if not self.faiss.is_loaded():
            raise IndexNotFoundError("索引未构建，请先调用 /api/index/build")

        logger.info(f"Processing stream query: {question[:50]}... (session: {session_id})")
        session_id = await self._ensure_session(session_id)
        yield self._sse_event("session", {"session_id": session_id})

        # 1. 查询改写
        retrieval_query = question
        if self.query_rewriter and self.query_rewriter.enabled:
            retrieval_query = await self.query_rewriter.rewrite(question)
            logger.info(f"Rewritten query: '{question[:30]}' -> '{retrieval_query[:50]}'")

        # 2. 检查缓存
        if self.cache and self.cache.available:
            msg_count = await self._get_message_count(session_id)
            cache_key = self.cache.make_key(question, session_id, msg_count)
            cached = await self.cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for session {session_id}")
                yield self._sse_event("retrieval", {
                    "sources": cached["sources"],
                    "chunks": [],
                })
                yield self._sse_event("done", {
                    "answer": cached["answer"],
                    "sources": cached["sources"],
                    "session_id": session_id,
                })
                return

        # 3. 混合检索
        if self.hybrid_retriever and self.hybrid_retriever.enabled:
            raw_results = await self.hybrid_retriever.retrieve(retrieval_query, top_k=20)
        else:
            query_vector = await self.embedding.encode([retrieval_query])
            if query_vector.size == 0:
                yield self._sse_event("error", {"message": "Failed to encode question"})
                return
            raw_results = self.faiss.search(query_vector[0], self.top_k)

        if not raw_results:
            logger.warning("No relevant chunks found")
            yield self._sse_event("retrieval", {"sources": [], "chunks": []})
            yield self._sse_event("done", {
                "answer": "抱歉，我在知识库中没有找到相关内容。请尝试重新构建索引或添加更多相关文档。",
                "sources": [],
                "session_id": session_id,
            })
            return

        # 4. 重排序
        if self.reranker and self.reranker.enabled:
            docs = [r.content for r in raw_results]
            reranked = await self.reranker.rerank(retrieval_query, docs, top_k=self.top_k)
            # 用重排序结果替换原始结果
            final_results = []
            content_to_result = {r.content: r for r in raw_results}
            for rr in reranked:
                if rr.content in content_to_result:
                    orig = content_to_result[rr.content]
                    final_results.append(orig)
        else:
            final_results = raw_results[:self.top_k]

        unique_results = self._deduplicate_results(final_results)

        sources_data = [
            {"file": r.source_file, "chunk_index": r.chunk_index, "score": r.score}
            for r in unique_results
        ]
        yield self._sse_event("retrieval", {
            "sources": sources_data,
            "chunks": [r.content for r in unique_results],
        })

        # 5. LLM 生成
        context = "\n---\n".join([r.content for r in unique_results])
        prompt = await self._build_prompt(session_id, question, context)

        answer_parts = []
        try:
            async for chunk in self.llm.chat_stream(prompt, SYSTEM_PROMPT):
                answer_parts.append(chunk)
                yield self._sse_event("token", {"content": chunk})
        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            yield self._sse_event("error", {"message": str(e)})
            return

        answer = "".join(answer_parts)

        await self._save_to_session(session_id, question, answer, unique_results)

        # 6. 写入缓存
        if self.cache and self.cache.available:
            msg_count = await self._get_message_count(session_id)
            cache_key = self.cache.make_key(question, session_id, msg_count)
            await self.cache.set(cache_key, answer, sources_data)

        yield self._sse_event("done", {
            "answer": answer,
            "sources": sources_data,
            "session_id": session_id,
        })
```

- [ ] **Step 3: 添加 _get_message_count 辅助方法**

```python
    async def _get_message_count(self, session_id: str) -> int:
        """获取会话的消息数量，用于缓存 key 计算。"""
        if not self.session_store or not self.session_store.is_connected:
            return 0
        try:
            history = await self.session_store.get_history(session_id)
            return len(history)
        except Exception:
            return 0
```

- [ ] **Step 4: 同样更新同步 query 方法**

```python
    async def query(
        self, question: str, session_id: str | None = None
    ) -> QueryResponse:
        if not self.faiss.is_loaded():
            raise IndexNotFoundError("索引未构建，请先调用 /api/index/build")
        logger.info(f"Processing query: {question[:50]}... (session: {session_id})")
        session_id = await self._ensure_session(session_id)

        # 1. 查询改写
        retrieval_query = question
        if self.query_rewriter and self.query_rewriter.enabled:
            retrieval_query = await self.query_rewriter.rewrite(question)

        # 2. 混合检索
        if self.hybrid_retriever and self.hybrid_retriever.enabled:
            raw_results = await self.hybrid_retriever.retrieve(retrieval_query, top_k=20)
        else:
            query_vector = await self.embedding.encode([retrieval_query])
            if query_vector.size == 0:
                raise ValueError("Failed to encode question")
            raw_results = self.faiss.search(query_vector[0], self.top_k)

        if not raw_results:
            return QueryResponse(
                answer="抱歉，我在知识库中没有找到相关内容。请尝试重新构建索引或添加更多相关文档。",
                sources=[], retrieved_chunks=[], session_id=session_id,
            )

        # 3. 重排序
        if self.reranker and self.reranker.enabled:
            docs = [r.content for r in raw_results]
            reranked = await self.reranker.rerank(retrieval_query, docs, top_k=self.top_k)
            content_to_result = {r.content: r for r in raw_results}
            final_results = []
            for rr in reranked:
                if rr.content in content_to_result:
                    final_results.append(content_to_result[rr.content])
        else:
            final_results = raw_results[:self.top_k]

        unique_results = self._deduplicate_results(final_results)
        context = "\n---\n".join([r.content for r in unique_results])
        prompt = await self._build_prompt(session_id, question, context)
        answer = await self.llm.chat(prompt, SYSTEM_PROMPT)
        await self._save_to_session(session_id, question, answer, unique_results)

        sources = [
            SourceInfo(file=r.source_file, chunk_index=r.chunk_index, score=r.score)
            for r in unique_results
        ]
        return QueryResponse(
            answer=answer, sources=sources,
            retrieved_chunks=[r.content for r in unique_results],
            session_id=session_id,
        )
```

- [ ] **Step 5: 验证语法**

Run: `python -c "import ast; ast.parse(open('app/services/rag_service.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 6: Commit**

```bash
git add app/services/rag_service.py
git commit -m "refactor: integrate rerank, query rewrite, hybrid search, and cache into RAGService"
```

---

### Task 7: 在 main.py 中注册新服务

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: 修改 app/main.py，注册所有新服务**

在 `lifespan` 函数中，在 `rag_service` 初始化之前插入新服务的初始化：

```python
# 在 lifespan 中，rag_service 初始化之前：

from app.services.query_rewrite import QueryRewriteService
from app.services.rerank_service import RerankService
from app.services.retrieval_service import HybridRetriever
from app.services.cache_service import ResponseCache

# 查询改写
query_rewrite_service = QueryRewriteService(
    llm=llm_client,
    enabled=settings.enable_query_rewrite,
)

# 混合检索 + BM25
hybrid_retriever = HybridRetriever(
    faiss_store=faiss_store,
    embedding=embedding_service,
    bm25_index_path=settings.bm25_index_path,
    enabled=settings.enable_hybrid_search,
)
hybrid_retriever.load_bm25()

# 重排序
rerank_service = RerankService(
    model_name=settings.rerank_model,
    enabled=settings.enable_rerank,
)

# 响应缓存
response_cache = ResponseCache(
    session_store=session_store,
    ttl=settings.cache_ttl,
)
```

修改 `rag_service` 初始化，传入新服务：

```python
rag_service = RAGService(
    faiss_store, embedding_service, llm_client,
    session_store=session_store,
    search_store=search_store,
    query_rewriter=query_rewrite_service,
    hybrid_retriever=hybrid_retriever,
    reranker=rerank_service,
    cache_service=response_cache,
)
```

修改 `index_service` 初始化，传入 hybrid_retriever：

```python
index_service = IndexService(
    faiss_store, doc_store, embedding_service,
    hybrid_retriever=hybrid_retriever,
)
```

在 `global` 声明中增加新服务的变量名，并在函数顶部声明：

```python
global faiss_store, doc_store, embedding_service, llm_client, rag_service
global index_service, session_store, search_store, user_store, auth_service
global query_rewrite_service, hybrid_retriever, rerank_service, response_cache
```

- [ ] **Step 2: 验证语法**

Run: `python -c "import ast; ast.parse(open('app/main.py').read()); print('Syntax OK')"`
Expected: `Syntax OK`

- [ ] **Step 3: 验证完整导入链路**

Run: `python -c "from app.main import app; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 4: 启动服务并验证**

Run: `python -c "from app.main import app; import uvicorn; uvicorn.run(app, host='0.0.0.0', port=8000)"`
Expected: 服务正常启动，日志无报错

- [ ] **Step 5: Commit**

```bash
git add app/main.py
git commit -m "feat: register new RAG pipeline services in main.py"
```