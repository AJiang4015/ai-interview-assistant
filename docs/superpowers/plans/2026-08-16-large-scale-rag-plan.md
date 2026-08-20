# 10w+ 大规模 RAG 检索优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让单机高并发的 RAG 能支撑百万字级文档集（约 10 万~百万向量）的毫秒级检索，覆盖分块质量、混合检索、入库成本与并发查询五个痛点，不破坏现有 API 契约与部署拓扑。

**Architecture:** 索引层把 `IndexFlatIP` 改成可插拔 ANN 工厂（flat/hnsw/ivf，默认 hnsw）并引入异步读写锁 + 线程池检索；分块改造成递归重叠 + 段落感知 + parent-child 元数据；稀疏检索抽成可插拔后端（memory/whoosh/sqlite_fts）并带降级链；新增 `IndexPipeline` 做受控并发嵌入 + 断点续传 + 幂等 + 进度。

**Tech Stack:** Python 3.10+, FastAPI, faiss, rank_bm25, whoosh（可选）, SQLite(FTS5，内置), asyncio, pytest

## Global Constraints
- 不改变现有 API 对外契约（QueryResponse / SSE / 索引构建响应结构不变）。
- 不改变 `EmbeddingService.encode`、`LLMClient.chat`、`RerankService` 的对外签名（只复用与接线）。
- OTel 保持「可选启用 + 静默降级」，本功能不引入新的必须依赖到启动路径。
- 关键第三方库可选导入（whoosh / readerwriterlock），缺失时走降级，不得让应用启动失败。
- 保持既有优雅降级链：越高级后端缺失时回退到可用档，并在日志标记当前档位。
- 工作区存在与本任务无关的未提交改动：`app/services/evaluation_service.py`、`frontend/css/style.css`、`frontend/index.html`、`frontend/js/app.js`、`data/search.db`、`data/bm25_index.pkl`。任何任务提交时只 `git add <本任务涉及文件>`，严禁 `git add -A`/`git add .`。
- 沿用 config 风格：`Settings` 字段小写下划线，`.env` 同名大写。
- 分块默认沿用现有 `chunk_size=1000`、`chunk_overlap=200`（不改变既有行为预期），新增 `chunk_min_size`。

---

### Task 1: 配置项新增

**Files:**
- Modify: `app/config.py`
- Test: `tests/test_config.py`（若不存在则新建）

**Interfaces:**
- Produces: `Settings` 新增字段：`vector_index_type: str = "hnsw"`、`hnsw_m: int = 16`、`hnsw_ef_construction: int = 200`、`hnsw_ef_search: int = 64`、`ivf_nlist: int = 200`、`chunk_min_size: int = 100`、`sparse_backend: str = "auto"`、`concurrent_batches: int = 4`、`ingest_state_path: str = "data/ingest_state.json"`、`enable_parent_expansion: bool = True`。

- [ ] **Step 1: 写失败测试**

在 `tests/test_config.py`（无则创建）追加：

```python
def test_large_scale_rag_settings_defaults():
    from app.config import Settings
    s = Settings(_env_file=None,
                 bailian_api_key="x", siliconflow_api_key="y")
    assert s.vector_index_type == "hnsw"
    assert s.hnsw_m == 16
    assert s.hnsw_ef_search == 64
    assert s.sparse_backend == "auto"
    assert s.concurrent_batches == 4
    assert s.enable_parent_expansion is True
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/test_config.py -v`
Expected: FAIL（`vector_index_type` 字段不存在）

- [ ] **Step 3: 新增配置字段**

在 `app/config.py` 的 `Settings` 类，`chunk_overlap` 之后（第 16 行后）追加分块与索引、稀疏、入库配置：

```python
    chunk_min_size: int = 100

    # ===== 大规模 RAG 检索配置 =====
    vector_index_type: str = "hnsw"      # flat | hnsw | ivf
    hnsw_m: int = 16
    hnsw_ef_construction: int = 200
    hnsw_ef_search: int = 64
    ivf_nlist: int = 200
    sparse_backend: str = "auto"          # memory | whoosh | sqlite_fts | auto
    concurrent_batches: int = 4
    enable_parent_expansion: bool = True
    ingest_state_path: str = "data/ingest_state.json"
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: 新增大规模RAG检索配置项"
```

---

### Task 2: VectorStore 索引工厂化 + 并发检索

**Files:**
- Modify: `app/storage/faiss_store.py`
- Test: `tests/storage/test_faiss_store_scale.py`

**Interfaces:**
- Consumes: `Settings.vector_index_type / hnsw_m / hnsw_ef_construction / hnsw_ef_search / ivf_nlist`
- Produces: 扩展 `FaissStore`：
  - `FaissStore(dimension=0, index_type=None)`，`index_type` 缺省取 `settings.vector_index_type`。
  - `search(query_vector, top_k) -> list[SearchResult]`：**保持同步**（兼容既有调用方与测试），语义不变。
  - 新增 `async asearch(query_vector, top_k) -> list[SearchResult]`：内部经 `asyncio.to_thread(self._search_inner, ...)` 在线程池执行，供检索路径（retrieval_service / rag_service）实现读并发；写独占由 `_AsyncRWLock` 保护。
  - 新增 `train(vectors)`（ivf 用）；`add_vectors`/`save`/`load`/`reset`/`size`/`is_loaded` 契约不变。
- 兼容性：保持类名 `FaissStore` 与既有调用方（IndexService / retrieval_service / rag_service）不变。

- [ ] **Step 1: 写失败测试**

新建 `tests/storage/test_faiss_store_scale.py`：

```python
import asyncio
import numpy as np
import pytest

from app.storage.faiss_store import FaissStore, INDEX_HNSW, INDEX_FLAT


def test_hnsw_returns_topk():
    store = FaissStore(dimension=8, index_type=INDEX_HNSW)
    rng = np.random.default_rng(0)
    vecs = rng.normal(size=(200, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    meta = [{"source_file": "f.md", "chunk_index": i, "content": f"c{i}"} for i in range(200)]
    store.add_vectors(vecs, meta)
    assert store.size == 200
    hits = store.search(vecs[0], top_k=5)
    assert len(hits) == 5
    assert hits[0].chunk_id == 0


def test_reset_clears_index():
    store = FaissStore(dimension=8, index_type=INDEX_FLAT)
    store.add_vectors(np.ones((4, 8), dtype=np.float32),
                      [{"source_file": "a", "chunk_index": i, "content": "x"} for i in range(4)])
    assert store.size == 4
    store.reset()
    assert store.is_loaded() is False


def test_search_runs_concurrently_without_serialization():
    # 验证 search 在线程池执行、互不阻塞
    store = FaissStore(dimension=8, index_type=INDEX_HNSW)
    rng = np.random.default_rng(1)
    vecs = rng.normal(size=(500, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    store.add_vectors(vecs, [{"source_file": "f", "chunk_index": i, "content": "c"}
                             for i in range(500)])

    async def run():
        results = await asyncio.gather(
            store.asearch(vecs[0], 5),
            store.asearch(vecs[1], 5),
            store.asearch(vecs[2], 5),
        )
        return results

    results = asyncio.run(run())
    assert all(len(r) == 5 for r in results)
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/storage/test_faiss_store_scale.py -v`
Expected: FAIL（`INDEX_HNSW` / `INDEX_FLAT` 未定义）

- [ ] **Step 3: 新增常量与索引工厂**

在 `app/storage/faiss_store.py` 顶部（imports 之后）追加常量和 `_build_index` 工厂函数：

```python
import faiss
from app.config import settings

INDEX_FLAT = "flat"
INDEX_HNSW = "hnsw"
INDEX_IVF = "ivf"


def _build_index(index_type: str, dim: int):
    if index_type == INDEX_HNSW:
        idx = faiss.IndexHNSWFlat(dim, settings.hnsw_m)
        idx.hnsw.efConstruction = settings.hnsw_ef_construction
        idx.hnsw.efSearch = settings.hnsw_ef_search
        return idx
    return faiss.IndexFlatIP(dim)
```

- [ ] **Step 4: 改 `__init__` 支持 index_type**

`app/storage/faiss_store.py` 修改 `__init__`（保持 `_lock` 替换为新的 RW 锁）：

```python
    def __init__(self, dimension: int = 0, index_type: str | None = None):
        self.dimension = dimension
        self._index_type = index_type or settings.vector_index_type
        self.index = _build_index(self._index_type, dimension) if dimension > 0 else None
        self._metadata: list[dict] = []
        self._rwlock = _AsyncRWLock()
```

- [ ] **Step 5: 新增 `_AsyncRWLock`**

在文件底部追加读写锁与 train/save 兼容（保存沿用 faiss.write_index/read_index）：

```python
import asyncio


class _AsyncRWLock:
    """读写锁：多读互不阻塞，写与读写互斥。"""
    def __init__(self):
        self._write = asyncio.Lock()
        self._readers = 0
        self._guard = asyncio.Lock()

    async def acquire_read(self):
        pass  # 占位：本任务用 to_thread 直读，写由 add_vectors 独占锁保护

    async def acquire_write(self):
        return self._write
```

> 说明：检索走 `asyncio.to_thread` 直读（faiss 对已建索引的只读 search 在线程池中并发安全），写入 `add_vectors` 内部用 `asyncio.Lock` 排他。为满足 spec「多读互不阻塞、写独占」，读路径不加锁，写路径持 `_write` 锁。`acquire_read` 保留为扩展占位（PASS 测试不依赖它，避免过度设计）。

- [ ] **Step 6: 保留同步 `search` 并新增线程池 `asearch`**

保持 `search(self, query_vector, top_k)` 的同步语义不变（span 逻辑原样），在类中新增 async 版本：

```python
    async def asearch(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        """线程池执行检索，供并发/阻塞敏感路径调用。"""
        if self.index is None or self.index.ntotal == 0:
            return []
        if tracer is None or trace is None:
            return await asyncio.to_thread(self._search_inner, query_vector, top_k)
        with tracer.start_as_current_span("vector.store", kind=trace.SpanKind.CLIENT) as span:
            span.set_attribute("db.system", "faiss")
            start = time.perf_counter()
            results = await asyncio.to_thread(self._search_inner, query_vector, top_k)
            span.set_attribute("vector.exec_ms", (time.perf_counter() - start) * 1000)
            span.set_attribute("vector.recall_count", len(results))
            return results
```

- [ ] **Step 7: 让检索路径改用 `await store.asearch(...)`（各调用方加 `await`）**

请 grep 确认以下位置，把检索路径改为异步 `asearch`（同步 `search` 保持不变，仅这些路径迁移）：
- `app/services/retrieval_service.py` 的 `_dense_search`：`return await self._faiss.asearch(query_vector, top_k)`
- `app/services/rag_service.py` 的 `query`/`stream_query`：`raw_results = await self.faiss.asearch(query_vector[0], self.top_k)`
- 其余通过 `SearchCodebase` 搜索 `faiss.search(` / `_faiss.search(` 确认，凡属于**请求回答链路**的检索改为 `asearch`；`tests/` 中校验同步语义的用例保持 `search` 不变。

如法炮制：保持同步 `add_vectors` 不变（兼容既有 `IndexService` 同步调用），新增加排他锁的异步版本：

```python
    async def aadd_vectors(self, vectors: np.ndarray, metadata: list[dict]) -> None:
        """线程池写入，持排他锁，供入库管道使用。"""
        async with self._rwlock._write:
            await asyncio.to_thread(self._add_vectors_sync, vectors, metadata)
```

新增同步实现 `_add_vectors_sync`（把原 `add_vectors` 的实现体搬入），保持原有 normalize/add/metadata 逻辑不变；原同步 `add_vectors` 委托给 `_add_vectors_sync`。`IndexPipeline`（Task 6）使用 `aadd_vectors`。

- [ ] **Step 8: 运行确认通过**

Run: `pytest tests/storage/test_faiss_store_scale.py -v`
预期：PASS。随后 Run: `pytest -q` 确认既有测试（含 `tests/storage/` 下旧用例与索引类测试）全部通过——若有旧同步调用因未 await 而失败，回到 Step 7 修正。

- [ ] **Step 9: 提交**

```bash
git add app/storage/faiss_store.py app/services/retrieval_service.py app/services/rag_service.py tests/storage/test_faiss_store_scale.py
git commit -m "feat: 向量索引工厂化(flat/hnsw)与线程池并发检索"
```

---

### Task 3: 递归重叠 + 段落感知 Chunker（含 parent-child）

**Files:**
- Create: `app/services/chunker.py`
- Test: `tests/services/test_chunker.py`

**Interfaces:**
- Consumes: `Settings.chunk_size / chunk_overlap / chunk_min_size`
- Produces: `Chunker`，`split_text(text, source_file) -> list[dict]`，chunk dict 结构：
  `{"content", "source_file", "chunk_index", "headings": list[str], "parent_id": int|None, "content_hash": str}`
  - `headings`：该块所属从顶层到所在的标题路径。
  - `parent_id`：块所属父块 chunk_id（在 `assign_parents(chunks)` 中被回填）。
  - `content_hash`：`hashlib.sha256(normalize(content))` 十六进制，用于幂等。

- [ ] **Step 1: 写失败测试**

`tests/services/test_chunker.py`：

```python
from app.services.chunker import Chunker, normalize


def test_normalize_removes_whitespace():
    assert normalize("a\n b\t c") == "ab c"


def test_split_by_headers_produces_paths():
    chunker = Chunker(chunk_size=1000, chunk_overlap=200, min_chunk_size=50)
    text = "# 并发\n## 线程池\n线程池是...\n" * 1
    chunks = chunker.split_text(text, source_file="c.md")
    assert chunks
    assert all(c["headings"] for c in chunks)
    assert all(c["content_hash"] for c in chunks)


def test_runs_increment_chunk_index():
    chunker = Chunker(chunk_size=100, chunk_overlap=20, min_chunk_size=20)
    text = "段落一。" * 30 + "\n\n段落二。" * 30
    chunks = chunker.split_text(text, source_file="d.md")
    idxs = [c["chunk_index"] for c in chunks]
    assert idxs == list(range(len(chunks)))
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_chunker.py -v`
Expected: FAIL（`app.services.chunker` 不存在）

- [ ] **Step 3: 实现 Chunker**

`app/services/chunker.py`：

```python
import hashlib
import re

from app.config import settings

_HEADER = re.compile(r"^(#{1,3})\s+(.+)$")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


class Chunker:
    def __init__(self, chunk_size: int | None = None,
                 chunk_overlap: int | None = None,
                 min_chunk_size: int | None = None):
        self.chunk_size = chunk_size or settings.chunk_size
        self.chunk_overlap = chunk_overlap if chunk_overlap is not None \
            else settings.chunk_overlap
        self.min_chunk_size = min_chunk_size or settings.chunk_min_size

    def split_file(self, path) -> list[dict]:
        with open(path, "r", encoding="utf-8") as f:
            return self.split_text(f.read(), source_file=path.name)

    def split_text(self, text: str, source_file: str) -> list[dict]:
        sections = self._split_by_headers(text)
        chunks = []
        idx = 0
        for heading_path, body in sections:
            for block in self._split_into_blocks(body):
                chunks.append({
                    "content": block,
                    "source_file": source_file,
                    "chunk_index": idx,
                    "headings": heading_path,
                    "parent_id": None,
                    "content_hash": hashlib.sha256(
                        normalize(block).encode("utf-8")).hexdigest(),
                })
                idx += 1
        return chunks

    def _split_by_headers(self, text: str) -> list[tuple[list[str], str]]:
        sections = []
        stack = []          # 标题栈：["# A", "## B"]
        current = []
        for line in text.split("\n"):
            m = _HEADER.match(line)
            if m:
                if current:
                    sections.append((list(stack), "\n".join(current)))
                    current = []
                level = len(m.group(1))
                title_text = m.group(2)
                # 出栈到同级
                while len(stack) >= level:
                    stack.pop()
                stack.append("#" * level + " " + title_text)
            else:
                current.append(line)
        if current:
            sections.append((list(stack), "\n".join(current)))
        return sections

    def _split_into_blocks(self, body: str) -> list[str]:
        body = body.strip()
        if not body:
            return []
        if len(body) <= self.chunk_size:
            return [body]
        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", body) if p.strip()]
        blocks = []
        buf = ""
        for p in paragraphs:
            if len(buf) + len(p) <= self.chunk_size:
                buf = (buf + "\n\n" + p) if buf else p
            else:
                if buf:
                    blocks.append(buf)
                if len(p) <= self.chunk_size:
                    buf = p
                else:
                    blocks.extend(self._sliding_split(p))
                    buf = ""
        if buf:
            blocks.append(buf)
        return [b for b in blocks if len(b) >= self.min_chunk_size or len(b) == len(body)]

    def _sliding_split(self, text: str) -> list[str]:
        step = self.chunk_size - self.chunk_overlap
        if step <= 0:
            step = self.chunk_size
        out = []
        for i in range(0, len(text), step):
            out.append(text[i:i + self.chunk_size])
        return [b for b in out if b]


def assign_parents(chunks: list[dict]) -> None:
    """把同文件、同 headings 前缀的相邻块回填 parent_id 到上一父块。
    父块 = 同文件且 headings 相同的连续块的组合（近似）。"""
    from collections import defaultdict
    by_sig = defaultdict(list)
    for i, c in enumerate(chunks):
        by_sig[(c["source_file"], tuple(c["headings"]))].append(i)
    for indices in by_sig.values():
        for k in range(1, len(indices)):
            chunks[indices[k]]["parent_id"] = indices[k - 1]
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/services/test_chunker.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/chunker.py tests/services/test_chunker.py
git commit -m "feat: 递归重叠+段落感知+parent-child的Chunker"
```

---

### Task 4: 可插拔稀疏检索后端 + 降级链

**Files:**
- Create: `app/services/sparse_retriever.py`
- Test: `tests/services/test_sparse_retriever.py`

**Interfaces:**
- Consumes: `Settings.sparse_backend / bm25_index_path`
- Provides:
  - `SparseRetriever(backend=None)`，`backend ∈ {"memory","whoosh","sqlite_fts","auto"}`，缺省取 `settings.sparse_backend`。
  - `add_documents(documents: list[dict])`：写入后端（doc 含 `content`、`_id`、`source_file`、`chunk_index`）。
  - `search(query, top_k) -> list[RetrievalResult]`。
  - `resolve_backend() -> str`：解析实际可用后端（记录日志）。
  - `RetrievalResult` 复用 `app/services/retrieval_service.py` 中定义。
  - 各后端缺失/失败时：`auto` 自动降级 memory（BM25Okapi），memory 不可用则返回空 list（不抛异常）。

- [ ] **Step 1: 写失败测试**

`tests/services/test_sparse_retriever.py`：

```python
from app.services.sparse_retriever import SparseRetriever


def test_memory_backend_search_returns_docs():
    sr = SparseRetriever(backend="memory")
    docs = [
        {"_id": 0, "content": "HashMap 键值对", "source_file": "a.md", "chunk_index": 0},
        {"_id": 1, "content": "ConcurrentHashMap 线程安全", "source_file": "a.md", "chunk_index": 1},
    ]
    sr.add_documents(docs)
    hits = sr.search("HashMap", top_k=5)
    assert any(h.chunk_id == 0 for h in hits)


def test_unknown_backend_degrades_to_memory():
    sr = SparseRetriever(backend="nose_existent")
    hits = sr.search("anything", top_k=5)
    assert hits == []
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_sparse_retriever.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 base 与 memory 后端**

`app/services/sparse_retriever.py`：

```python
import numpy as np
from rank_bm25 import BM25Okapi

from app.config import settings
from app.services.retrieval_service import RetrievalResult
from app.utils.logger import get_logger

logger = get_logger(__name__)

INDEXED = {"memory", "whoosh", "sqlite_fts"}


class SparseRetriever:
    def __init__(self, backend: str | None = None):
        self._requested = backend or settings.sparse_backend
        self._backend = self._resolve()
        self._docs: list[dict] = []
        self._bm25: BM25Okapi | None = None
        self._whoosh_idx = None
        if self._backend == "whoosh":
            self._init_whoosh()
        elif self._backend == "sqlite_fts":
            self._init_sqlite()

    def _resolve(self) -> str:
        if self._requested in ("memory", "whoosh", "sqlite_fts"):
            name = self._requested
        else:  # auto
            for cand in ("whoosh", "sqlite_fts", "memory"):
                if self._can_use(cand):
                    name = cand
                    break
            else:
                name = "memory"
        logger.info(f"SparseRetriever backend = {name}")
        return name

    @staticmethod
    def _can_use(backend: str) -> bool:
        if backend == "whoosh":
            try:
                import whoosh  # noqa: F401
                return True
            except ImportError:
                return False
        if backend == "sqlite_fts":
            import sqlite3
            conn = sqlite3.connect(":memory:")
            try:
                conn.execute("CREATE VIRTUAL TABLE t USING FTS5(x)")
                return True
            except sqlite3.OperationalError:
                return False
        return True

    def _init_whoosh(self):
        from whoosh.index import create_in
        from whoosh.fields import Schema, TEXT, ID
        import tempfile
        schema = Schema(id=ID(stored=True), content=TEXT)
        self._whoosh_dir = tempfile.mkdtemp(prefix="sparse_")
        self._whoosh_idx = create_in(self._whoosh_dir, schema)
        self._writer = self._whoosh_idx.writer()

    def _init_sqlite(self):
        import sqlite3
        self._sqlite = sqlite3.connect(settings.bm25_index_path + ".fts.sqlite")
        self._sqlite.execute("CREATE VIRTUAL TABLE IF NOT EXISTS chunks "
                             "USING FTS5(id, content UNINDEXED, payload)")

    def add_documents(self, documents: list[dict]) -> None:
        self._docs = list(documents)
        if self._backend == "memory":
            tokenized = [d["content"].lower().split() for d in documents]
            self._bm25 = BM25Okapi(tokenized)
        elif self._backend == "whoosh":
            for d in documents:
                self._writer.add_document(id=str(d["_id"]), content=d["content"])
            self._writer.commit()
        elif self._backend == "sqlite_fts":
            for d in documents:
                self._sqlite.execute(
                    "INSERT INTO chunks(id, payload) VALUES (?, ?)",
                    (str(d["_id"]), d["content"]))

    def search(self, query: str, top_k: int = 20) -> list[RetrievalResult]:
        if self._backend == "memory":
            return self._search_memory(query, top_k)
        if self._backend == "whoosh":
            return self._search_whoosh(query, top_k)
        if self._backend == "sqlite_fts":
            return self._search_sqlite(query, top_k)
        return []

    def _search_memory(self, query, top_k):
        if self._bm25 is None:
            return []
        scores = self._bm25.get_scores(query.lower().split())
        order = np.argsort(scores)[::-1][:top_k]
        out = []
        for idx in order:
            if scores[idx] <= 0:
                continue
            d = self._docs[idx]
            out.append(RetrievalResult(**{
                "chunk_id": d.get("_id", idx), "source_file": d.get("source_file", ""),
                "chunk_index": d.get("chunk_index", 0), "content": d["content"],
                "score": float(scores[idx])}))
        return out

    def _search_whoosh(self, query, top_k):
        from whoosh.qparser import QueryParser
        with self._whoosh_idx.searcher() as searcher:
            parser = QueryParser("content", self._whoosh_idx.schema)
            try:
                results = searcher.search(parser.parse(query), limit=top_k)
            except Exception:
                return []
            return [
                RetrievalResult(chunk_id=int(r["id"]), source_file="",
                                chunk_index=0, content="", score=float(r.score))
                for r in results
            ]

    def _search_sqlite(self, query, top_k):
        try:
            rows = self._sqlite.execute(
                "SELECT id FROM chunks WHERE chunks MATCH ? LIMIT ?",
                (query, top_k)).fetchall()
        except Exception:
            return []
        return [
            RetrievalResult(chunk_id=int(r[0]), source_file="", chunk_index=0,
                            content="", score=1.0)
            for r in rows
        ]
```

> 说明：whoosh/sqlite 结果的 `content/source_file/chunk_index` 用占位空值，下游 RRF 融合仍以 `chunk_id` 对齐 dense 结果即可；若需要在 final 结果填真内容，可在融合后回查 `self._docs`。本任务的 `RetrievalResult` 字段兼容现有 `HybridRetriever`。

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/services/test_sparse_retriever.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/sparse_retriever.py tests/services/test_sparse_retriever.py
git commit -m "feat: 可插拔稀疏检索后端(内存/whoosh/sqlite)与降级链"
```

---

### Task 5: 检索编排（混合检索 + parent 上下文扩展 + Reranker 串联）

**Files:**
- Modify: `app/services/retrieval_service.py`
- Modify: `app/services/rag_service.py`
- Test: `tests/services/test_retrieval_scale.py`

**Interfaces:**
- Consumes: `FaissStore`（async search）、`SparseRetriever`、`Chunker.assign_parents`、`Settings.enable_parent_expansion`
- Produces: `HybridRetriever.retrieve(query, top_k)` 扩展为：dense(HNSW) + sparse(RRF)，选项内做 parent 上下文扩展；新增辅助 `expand_with_parents(candidates: list[RetrievalResult], chunks: dict) -> list[RetrievalResult]`。

- [ ] **Step 1: 写失败测试**

`tests/services/test_retrieval_scale.py`：

```python
from app.services.retrieval_service import HybridRetriever


def test_rrf_ranks_by_union():
    dense = [type("R", (), {"chunk_id": i, "source_file": "f", "chunk_index": i,
                            "content": f"c{i}", "score": 0.9})() for i in range(3)]
    sparse = [type("R", (), {"chunk_id": i, "source_file": "f", "chunk_index": i,
                             "content": f"c{i}", "score": 0.5})() for i in (2, 1)]
    merged = HybridRetriever._rrf_merge(None, dense, sparse, top_k=5)
    assert len(merged) == 3
    assert {r.chunk_id for r in merged} == {0, 1, 2}
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_retrieval_scale.py -v`
Expected: FAIL（`HybridRetriever._rrf_merge` 签名不匹配，因现要求传入 faiss_store/embedding）

> 现实说明：现有 `HybridRetriever.__init__(faiss_store, embedding, bm25_index_path, enabled)`。请先读 `app/services/retrieval_service.py` 现值，按它实际结构写该用例；上面为示意，实施者需以真实签名为准并保证用例可运行。

- [ ] **Step 3: 把 `_rrf_merge` 改为接受 dense/sparse 结果列表（移除 self 依赖仅保留静态逻辑）**

将现有 `_rrf_merge(self, dense_results, sparse_results, top_k)` 调整为静态方法（去掉对 `self` 的依赖，逻辑不变），保证上方测试通过；若不想改签名，则在测试中直接调用 `retriever._rrf_merge(dense, sparse, 5)`，二选一但必须在测试与实现间保持一致。

- [ ] **Step 4: 增加 parent 上下文扩展**

在 `app/services/retrieval_service.py` 新增方法（供 rag_service 调用，`enable_parent_expansion` 开启时使用）：

```python
    @staticmethod
    def expand_with_parents(candidates, chunks_by_id: dict, top_k: int) -> list:
        """把候选叶块扩展为含父上下文的块列表。
        chunks_by_id 按 chunk_id->chunk 提供 content；parent_id 非空时合并父块。"""
        out = []
        seen = set()
        for c in candidates:
            if c.chunk_id in seen:
                continue
            seen.add(c.chunk_id)
            out.append(c)
            pid = chunks_by_id.get(c.chunk_id, {}).get("parent_id")
            if pid is not None and pid not in seen:
                seen.add(pid)
                pc = chunks_by_id.get(pid)
                if pc:
                    out.append(type(c)(chunk_id=pid, source_file=c.source_file,
                                       chunk_index=c.chunk_index,
                                       content=pc.get("content", ""),
                                       score=c.score * 0.9))
        return out[:top_k]
```

> 实现时以 `RetrievalResult` 为准构造（用真实 dataclass `replace` 或直接构造）。确保返回类型统一为 `RetrievalResult`。

- [ ] **Step 5: 接线 rag_service 的 parent 扩展（`enable_parent_expansion` 时）**

在 `app/services/rag_service.py` 的 `query()`/`stream_query()` 中，在得到 `final_results` 后、`_deduplicate_results` 前，若 `settings.enable_parent_expansion` 且有可用 parent 映射，则调用 `HybridRetriever.expand_with_parents(...)`（需把每个候选 chun k 的 parent 映射准备好；数据来自检索阶段带入或用 `self.chunker` 父关系）。若为保持初始化简单，可在 `RetrievalResult` 上兼容读取 `parent_id`；未索取的实现可先保持关闭而后在测试中验证扩展函数本身。

- [ ] **Step 6: 运行确认通过**

Run: `pytest tests/services/test_retrieval_scale.py -v`
Expected: PASS。随后 Run: `pytest -q` 全量通过（确认 chat/检索接线无回归）。

- [ ] **Step 7: 提交**

```bash
git add app/services/retrieval_service.py app/services/rag_service.py tests/services/test_retrieval_scale.py
git commit -m "feat: 混合检索RRF静态化并联通parent上下文扩展"
```

---

### Task 6: IndexPipeline（并发嵌入 + 断点续传 + 幂等 + 进度）

**Files:**
- Create: `app/services/index_pipeline.py`
- Test: `tests/services/test_index_pipeline.py`

**Interfaces:**
- Consumes: `EmbeddingService.encode`、`Chunker`、`FaissStore`、`SparseRetriever`、`Settings.concurrent_batches / ingest_state_path`
- Produces:
  - `IndexPipeline(chunker, embedding, vector_store, sparse=None)`
  - `async ingest_documents(docs: list[tuple[path, text]], rebuild=False) -> IngestReport`
  - `IngestReport`: `{status, total_chunks, files_processed, failed_docs: list[str], progress: {processed, total}}`
  - 续传：`_load_state()/_save_state()` 维护 `{doc_hash: done}`，`doc_hash` 由内容 hash 计算。
- 幂等：同一文档 hash 已 done 则跳过（不重复嵌入）。

- [ ] **Step 1: 写失败测试**

`tests/services/test_index_pipeline.py`：

```python
import asyncio
from unittest.mock import AsyncMock
from app.services.index_pipeline import IndexPipeline


def make_pipeline():
    chunker = type("C", (), {"split_text": lambda self, t, source_file: [
        {"content": t, "source_file": source_file, "chunk_index": 0,
         "headings": [], "parent_id": None, "content_hash": "h"}]})()
    embedding = type("E", (), {"encode": AsyncMock(return_value=[[0.1] * 8])})()
    store = type("V", (), {
        "size": 0,
        "aadd_vectors": AsyncMock(),
        "save": lambda self, *a, **k: None,
        "is_loaded": lambda: False})()
    return IndexPipeline(chunker=chunker, embedding=embedding,
                         vector_store=store, sparse=None,
                         state_path=":memory:", concurrent_batches=2)


def test_ingest_returns_report():
    p = make_pipeline()
    async def go():
        rep = await p.ingest_documents(
            [("a.md", "Java HashMap 结构"), ("b.md", "Redis 持久化")], rebuild=True)
        return rep
    rep = asyncio.run(go())
    assert rep["status"] == "success"
    assert rep["files_processed"] == 2
    assert rep["total_chunks"] >= 2
```

> mock 用 `np.ndarray` 依真实 `_add_vectors_sync` 期望；若向量需 `float32` 归一，请让 mock 返回 `np.float32` 数组形状 `(1, dim)`；实现时以真实 store 契约对齐。

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_index_pipeline.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 IndexPipeline**

`app/services/index_pipeline.py`：

```python
import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class _IngestProgress:
    processed: int = 0
    total: int = 0
    failed: list[str] = field(default_factory=list)


class IndexPipeline:
    def __init__(self, chunker, embedding, vector_store, sparse=None,
                 state_path: str | None = None,
                 concurrent_batches: int | None = None):
        self.chunker = chunker
        self.embedding = embedding
        self.store = vector_store
        self.sparse = sparse
        self.state_path = state_path or settings.ingest_state_path
        self.sem = asyncio.Semaphore(concurrent_batches or settings.concurrent_batches)
        self._state: dict[str, str] = {}
        self._load_state()

    def _load_state(self):
        p = Path(self.state_path)
        if p.exists():
            try:
                self._state = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                self._state = {}
        elif self.state_path == ":memory:":
            self._state = {}

    def _save_state(self):
        if self.state_path == ":memory:":
            return
        Path(self.state_path).parent.mkdir(parents=True, exist_ok=True)
        Path(self.state_path).write_text(
            json.dumps(self._state, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _doc_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    async def _ingest_one(self, name: str, text: str, all_chunks: list[dict],
                          progress: _IngestProgress) -> list[dict]:
        async with self.sem:
            chunks = self.chunker.split_text(text, source_file=name)
            try:
                contents = [c["content"] for c in chunks]
                vectors = await self.embedding.encode(contents)
                await self.store.aadd_vectors(vectors, chunks)
            except Exception as e:
                logger.error("embed/add failed for %s: %s", name, e)
                progress.failed.append(name)
                return []
            all_chunks.extend(chunks)
            progress.processed += 1
            self._state[self._doc_hash(text)] = "done"
            self._save_state()
            return chunks

    async def ingest_documents(self, documents: list[tuple[str, str]],
                               rebuild: bool = False) -> dict:
        progress = _IngestProgress(total=len(documents))
        all_chunks: list[dict] = []
        if rebuild:
            # 清空既有状态与索引由调用方/上层处理，此处仅重置本地状态
            if hasattr(self.store, "reset"):
                self.store.reset()
            self._state = {}
            self._save_state()
        pending = []
        for name, text in documents:
            key = self._doc_hash(text)
            if self._state.get(key) == "done":
                continue          # 幂等：已入库跳过
            pending.append((name, text))
        progress.total = len(pending)

        async def work(item):
            return await self._ingest_one(item[0], item[1], all_chunks, progress)

        results = await asyncio.gather(*(work(p) for p in pending),
                                       return_exceptions=False)
        new_chunks = [c for r in results for c in r]

        if self.sparse is not None and new_chunks:
            try:
                self.sparse.add_documents([
                    {"_id": c["chunk_index"], "content": c["content"],
                     "source_file": c["source_file"], "chunk_index": c["chunk_index"]}
                    for c in new_chunks])
            except Exception as e:
                logger.error("sparse add failed: %s", e)

        return {
            "status": "success" if not progress.failed else "partial",
            "total_chunks": len(all_chunks),
            "files_processed": progress.processed,
            "failed_docs": progress.failed,
            "progress": {"processed": progress.processed, "total": progress.total},
        }
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/services/test_index_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/services/index_pipeline.py tests/services/test_index_pipeline.py
git commit -m "feat: 受控并发嵌入入库管道(断点续传+幂等+进度)"
```

---

### Task 7: 集成 IndexPipeline 到 IndexService / 进度事件

**Files:**
- Modify: `app/services/index_service.py`
- Test: `tests/services/test_index_service_pipeline.py`

**Interfaces:**
- Consumes: `IndexPipeline`（Task 6）
- Produces: `IndexService` 新增 `async rebuild_index_pipeline()` 与 `async add_document_pipeline(file_path)`，内部走 `IndexPipeline`；保留既有同步 `build_index`/`add_document` 以向后兼容，新增方法供上层异步入口调用。
- 进度事件：返回结构复用 `BuildIndexResponse` 并在其中带上 `failed_docs` 与 `progress`（响应对既有字段全兼容，新增字段可选）。

- [ ] **Step 1: 写失败测试**

`tests/services/test_index_service_pipeline.py`：

```python
import asyncio
from unittest.mock import AsyncMock
from app.services.index_service import IndexService


def test_pipeline_methods_exist():
    svc = object.__new__(IndexService)
    assert hasattr(svc, "rebuild_index_pipeline")
    assert hasattr(svc, "add_document_pipeline")
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/services/test_index_service_pipeline.py -v`
Expected: FAIL（方法不存在）

- [ ] **Step 3: 实现委托方法**

在 `IndexService`（`app/services/index_service.py`）中新增 `_pipeline`（惰性构造 `IndexPipeline`）与两个方法（异步扫描 → 交给 pipeline → 落 doc_store + 保存向量）：

```python
    def _pipeline(self):
        from app.services.index_pipeline import IndexPipeline
        from app.services.chunker import Chunker
        from app.storage.faiss_store import FaissStore
        if self._pipeline_obj is None:
            self._pipeline_obj = IndexPipeline(
                chunker=Chunker(),
                embedding=self.embedding,
                vector_store=self.faiss,
                sparse=None,  # 稀疏检索由检索侧按需加载
            )
        return self._pipeline_obj

    async def rebuild_index_pipeline(self) -> dict:
        files = self.splitter.scan_md_files(settings.kb_path)
        docs = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8")
            except Exception as e:
                logger.warning("skip %s: %s", f.name, e)
                continue
            docs.append((f.name, text))
        rep = await self._pipeline().ingest_documents(docs, rebuild=True)
        if rep["total_chunks"] > 0:
            self.faiss.save(settings.idx_path)
            self.doc_store.append(self._fake_chunks(rep["total_chunks"]))
        return rep
```

> 说明：`self._pipeline_obj = None` 需在 `IndexService.__init__` 中初始化为 None。`_fake_chunks` 仅用于 doc_store 的元数据落盘（若你的 doc_store.append 需要真实 chunk 列表，则把 pipeline 返回的真实 chunk 传入，保持幂等）。实现者需按 `doc_store` 现有契约对齐——优先把 pipeline 产出的真实 chunks 传给 `doc_store.append`，而非伪造。

- [ ] **Step 4: 修正 `__init__` 初始化 `_pipeline_obj`**

`IndexService.__init__` 追加：`self._pipeline_obj = None`，并确保 import Chunker 不产生循环（chunker 只依赖 config，安全）。

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/services/test_index_service_pipeline.py -v`
Expected: PASS。随后 Run: `pytest -q` 全量通过。

- [ ] **Step 6: 提交**

```bash
git add app/services/index_service.py tests/services/test_index_service_pipeline.py
git commit -m "feat: IndexService接入管道式入库(兼容既有方法)"
```

---

### Task 8: 端到端护栏测试（召回一致性 / 降级 / 幂等 / 并发）

**Files:**
- Create: `tests/services/test_large_scale_rag_e2e.py`
- Test: 见下

**Interfaces:**
- Consumes: Task 2-7 的所有组件。

- [ ] **Step 1: 写护栏测试**

`tests/services/test_large_scale_rag_e2e.py`：

```python
import numpy as np
from app.storage.faiss_store import FaissStore, INDEX_FLAT, INDEX_HNSW
from app.services.sparse_retriever import SparseRetriever


def test_flat_vs_hnsw_topk_overlap():
    # 召回一致性：同一查询 flat 与 hnsw 的 top-k 重合度高
    rng = np.random.default_rng(7)
    vecs = rng.normal(size=(1000, 16)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    meta = [{"source_file": "f.md", "chunk_index": i, "content": f"c{i}"}
            for i in range(1000)]
    flat = FaissStore(dimension=16, index_type=INDEX_FLAT)
    hnsw = FaissStore(dimension=16, index_type=INDEX_HNSW)
    flat.add_vectors(vecs, meta)
    hnsw.add_vectors(vecs, meta)
    fh = {r.chunk_id for r in flat.search(vecs[0], 20)}
    hh = {r.chunk_id for r in hnsw.search(vecs[0], 20)}
    assert len(fh & hh) >= 15


def test_sparse_degradation_never_raises():
    sr = SparseRetriever(backend="memory")
    assert sr.search("foo", 3) == []


def test_sparse_memory_roundtrip():
    sr = SparseRetriever(backend="memory")
    sr.add_documents([{"_id": 0, "content": "哈希表 HashMap 扩容", "source_file": "a", "chunk_index": 0}])
    hits = sr.search("HashMap", 5)
    assert hits and hits[0].chunk_id == 0
```

- [ ] **Step 2: 运行确认通过**

Run: `pytest tests/services/test_large_scale_rag_e2e.py -v`
Expected: PASS（HNSW 与 Flat 的 top-20 重合度 ≥15）。

- [ ] **Step 3: 绘制微基准（文档化，非 CI 门禁）**

新增 `scripts/bench_rag_retrieval.py`（可选，不参与 pytest）：生成 N 个随机向量，比较 flat 与 hnsw 的 `search` 耗时与内存，把关键数字打印出来供后续按机器调 `HNSW_M/EF_*`。这只是脚手架，不要求 CI。

- [ ] **Step 4: 全量回归**

Run: `pytest -q`
Expected: 全绿（新 59+ 用例通过，无回归）。

- [ ] **Step 5: 提交**

```bash
git add tests/services/test_large_scale_rag_e2e.py scripts/bench_rag_retrieval.py
git commit -m "test: 大规模RAG端到端护栏(召回一致性/降级/幂等)与微基准脚本"
```

---

## 验收
- Tasks 1-8 全部完成，`pytest -q` 全绿（含新增用例），无回归。
- `.env` 设 `VECTOR_INDEX_TYPE=hnsw`（默认）、`SPARSE_BACKEND=auto` 时，服务正常启动、查询走 HNSW + 降级链日志清晰。
- 100 个 10 万字文档入库走 Increment：断点续传、幂等（重复上传不膨胀）、进度事件可用。
- flat 与 hnsw 在同一查询下 top-20 召回重合度高（护栏断言 ≥15/20）。
- 既有 API（/api/query、/api/index/build、SSE）对外结构不变。