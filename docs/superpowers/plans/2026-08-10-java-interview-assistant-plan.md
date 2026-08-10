# Java 程序员智能面试助手 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a RAG-based backend service that answers Java/backend technical questions by检索本地知识库并结合 LLM 生成回答。

**Architecture:** 4-layer architecture (API / Services / Storage / Infra). Pure native Python implementation without LangChain. FAISS for vector storage, SiliconFlow for Embedding, Bailian for LLM.

**Tech Stack:** Python 3.10+, FastAPI, FAISS, httpx, Pydantic v2, tenacity

## Global Constraints

- Python 3.10+ required
- All向量需 L2 归一化以配合 FAISS IndexFlatIP
- API Key 必须通过环境变量获取，不硬编码
- 异步优先：所有 I/O 操作使用 asyncio
- 错误处理：自定义异常映射到 HTTP 状态码
- 代码风格：无多余注释，遵循 PEP 8

---

## File Structure Map

| File | Responsibility |
|------|---------------|
| `requirements.txt` | 项目依赖 |
| `.env.example` | 环境变量模板（不含密钥） |
| `.gitignore` | Git 忽略规则 |
| `app/__init__.py` | 应用包初始化 |
| `app/config.py` | Pydantic BaseSettings 配置管理 |
| `app/main.py` | FastAPI 入口 + lifespan + 异常处理 |
| `app/api/__init__.py` | API 包初始化 |
| `app/api/schemas.py` | 请求/响应 Pydantic 模型 |
| `app/api/routes.py` | 路由注册与端点实现 |
| `app/services/__init__.py` | 服务包初始化 |
| `app/services/embedding.py` | 硅基 Embedding API 客户端 |
| `app/services/llm_client.py` | 百炼 LLM API 客户端 |
| `app/services/rag_service.py` | RAG 核心编排（检索+生成） |
| `app/services/index_service.py` | 索引构建服务 |
| `app/storage/__init__.py` | 存储包初始化 |
| `app/storage/faiss_store.py` | FAISS 向量索引封装 |
| `app/storage/doc_store.py` | 文档元数据 JSON 存储 |
| `app/utils/__init__.py` | 工具包初始化 |
| `app/utils/text_splitter.py` | Markdown 分块器 |
| `app/utils/logger.py` | 日志配置 |

---

### Task 1: 项目初始化与配置

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/utils/__init__.py`
- Create: `app/utils/logger.py`
- Create: `data/knowledge_base/.gitkeep`
- Create: `data/faiss_index/.gitkeep`

**Interfaces:**
- Consumes: 无
- Produces: `Settings` 类（`app.config`），`get_logger()` 函数（`app.utils.logger`）

- [ ] **Step 1: 创建 requirements.txt**

```
fastapi==0.115.0
uvicorn==0.32.0
pydantic==2.9.0
pydantic-settings==2.5.0
faiss-cpu==1.8.0
numpy==1.26.0
httpx==0.27.0
python-dotenv==1.0.0
tenacity==9.0.0
```

- [ ] **Step 2: 创建 .env.example**

```
# 百炼平台 API 配置
BAILIAN_API_KEY=your_bailian_api_key_here
BAILIAN_MODEL=qwen3.7-max-2026-05-20

# 硅基平台 API 配置
SILICONFLOW_API_KEY=your_siliconflow_api_key_here
SILICONFLOW_MODEL=Qwen/Qwen3-Embedding-4B

# 系统配置
KNOWLEDGE_BASE_DIR=data/knowledge_base
INDEX_PATH=data/faiss_index
TOP_K=5
CHUNK_SIZE=1000
CHUNK_OVERLAP=200
LLM_TEMPERATURE=0.7
REQUEST_TIMEOUT=30
```

- [ ] **Step 3: 创建 .gitignore**

```
# Python
__pycache__/
*.pyc
*.pyo
.env
.venv/
venv/

# IDE
.idea/
.vscode/

# Data
data/faiss_index/*.index
data/faiss_index/*.json
!data/faiss_index/.gitkeep
!data/knowledge_base/.gitkeep

# OS
Thumbs.db
.DS_Store
```

- [ ] **Step 4: 创建目录结构和 __init__.py 文件**

```bash
mkdir -p app/api app/services app/storage app/utils data/knowledge_base data/faiss_index
# 在每个目录下创建空的 __init__.py
```

- [ ] **Step 5: 创建 app/config.py**

```python
from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    bailian_api_key: str
    bailian_model: str = "qwen3.7-max-2026-05-20"
    siliconflow_api_key: str
    siliconflow_model: str = "Qwen/Qwen3-Embedding-4B"
    knowledge_base_dir: str = "data/knowledge_base"
    index_path: str = "data/faiss_index"
    top_k: int = 5
    chunk_size: int = 1000
    chunk_overlap: int = 200
    llm_temperature: float = 0.7
    request_timeout: int = 30

    model_config = {"env_file": ".env", "extra": "ignore"}

    @property
    def kb_path(self) -> Path:
        return PROJECT_ROOT / self.knowledge_base_dir

    @property
    def idx_path(self) -> Path:
        return PROJECT_ROOT / self.index_path


settings = Settings()
```

- [ ] **Step 6: 创建 app/utils/logger.py**

```python
import logging
import sys


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
```

- [ ] **Step 7: 安装依赖并验证配置加载**

```bash
pip install -r requirements.txt
python -c "from app.config import settings; print('Config OK:', settings.bailian_model)"
```

Expected: `Config OK: qwen3.7-max-2026-05-20`（无 .env 文件时会因缺少必填字段报错，属预期行为）

- [ ] **Step 8: Commit**

```bash
git add requirements.txt .env.example .gitignore app/ data/
git commit -m "feat: 项目初始化 - 依赖、配置、日志"
```

---

### Task 2: 异常定义与 Pydantic Schema

**Files:**
- Create: `app/api/schemas.py`
- Create: `app/exceptions.py`

**Interfaces:**
- Consumes: 无
- Produces: `QueryRequest`, `QueryResponse`, `SourceInfo`, `BuildIndexRequest`, `BuildIndexResponse`, `IndexStatusResponse`, `HealthResponse`；异常类 `IndexNotFoundError`, `EmbeddingAPIError`, `LLMAPIError`, `IndexBuildError`

- [ ] **Step 1: 创建 app/exceptions.py**

```python
class RAGSystemError(Exception):
    """系统基础异常"""


class IndexNotFoundError(RAGSystemError):
    """索引不存在"""


class EmbeddingAPIError(RAGSystemError):
    """Embedding API 调用失败"""


class LLMAPIError(RAGSystemError):
    """LLM API 调用失败"""


class IndexBuildError(RAGSystemError):
    """索引构建失败"""
```

- [ ] **Step 2: 创建 app/api/schemas.py**

```python
from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)


class SourceInfo(BaseModel):
    file: str
    chunk_index: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceInfo]
    retrieved_chunks: list[str]


class BuildIndexRequest(BaseModel):
    rebuild: bool = False


class BuildIndexResponse(BaseModel):
    status: str
    total_chunks: int
    files_processed: int


class IndexStatusResponse(BaseModel):
    index_exists: bool
    total_chunks: int
    last_build_time: str | None
    knowledge_base_files: list[str]


class HealthResponse(BaseModel):
    status: str
    faiss_index: str
    embedding_service: str
    llm_service: str
```

- [ ] **Step 3: 验证 Schema 正确**

```bash
python -c "
from app.api.schemas import QueryRequest, QueryResponse
from app.exceptions import IndexNotFoundError

req = QueryRequest(question='test')
print('QueryRequest OK:', req.question)

try:
    QueryRequest(question='')
except Exception as e:
    print('Validation OK:', type(e).__name__)

print('Exception OK:', IndexNotFoundError.__bases__)
"
```

Expected:
```
QueryRequest OK: test
Validation OK: ValidationError
Exception OK: (<class 'app.exceptions.RAGSystemError'>,)
```

- [ ] **Step 4: Commit**

```bash
git add app/api/schemas.py app/exceptions.py
git commit -m "feat: 添加 Pydantic Schema 和自定义异常"
```

---

### Task 3: FAISS 向量索引封装

**Files:**
- Create: `app/storage/faiss_store.py`

**Interfaces:**
- Consumes: 无
- Produces: `FaissStore` 类，方法 `add_vectors(vectors, metadata)`, `search(query_vector, top_k) -> list[SearchResult]`, `save(path)`, `load(path)`, `reset()`；`SearchResult` 数据类

- [ ] **Step 1: 创建 app/storage/faiss_store.py**

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

import faiss
import numpy as np


@dataclass
class SearchResult:
    chunk_id: int
    source_file: str
    chunk_index: int
    content: str
    score: float


class FaissStore:
    def __init__(self, dimension: int = 1024):
        self.dimension = dimension
        self.index = faiss.IndexFlatIP(dimension)
        self._metadata: list[dict] = []
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return self.index.ntotal

    def add_vectors(self, vectors: np.ndarray, metadata: list[dict]) -> None:
        if vectors.ndim == 1:
            vectors = vectors.reshape(1, -1)
        faiss.normalize_L2(vectors)
        start_id = len(self._metadata)
        for i, meta in enumerate(metadata):
            meta_copy = meta.copy()
            meta_copy["_id"] = start_id + i
            self._metadata.append(meta_copy)
        self.index.add(vectors)

    def search(self, query_vector: np.ndarray, top_k: int = 5) -> list[SearchResult]:
        if self.index.ntotal == 0:
            return []
        qv = query_vector.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(qv)
        k = min(top_k, self.index.ntotal)
        scores, ids = self.index.search(qv, k)
        results = []
        for score, idx in zip(scores[0], ids[0]):
            if idx < 0:
                continue
            meta = self._metadata[idx]
            results.append(SearchResult(
                chunk_id=meta["_id"],
                source_file=meta["source_file"],
                chunk_index=meta["chunk_index"],
                content=meta["content"],
                score=float(score)
            ))
        return results

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(path / "index.faiss"))
        import json
        with open(path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(self._metadata, f, ensure_ascii=False, indent=2)

    def load(self, path: str | Path) -> None:
        path = Path(path)
        index_file = path / "index.faiss"
        if not index_file.exists():
            return
        self.index = faiss.read_index(str(index_file))
        import json
        meta_file = path / "metadata.json"
        if meta_file.exists():
            with open(meta_file, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)

    def reset(self) -> None:
        self.index = faiss.IndexFlatIP(self.dimension)
        self._metadata = []

    def is_loaded(self) -> bool:
        return self.index.ntotal > 0
```

- [ ] **Step 2: 验证 FAISS 存储功能**

```bash
python -c "
import numpy as np
from app.storage.faiss_store import FaissStore

store = FaissStore(dimension=1024)
print('Initial size:', store.size)

vectors = np.random.randn(3, 1024).astype(np.float32)
metadata = [
    {'source_file': 'test.md', 'chunk_index': 0, 'content': 'Hello world'},
    {'source_file': 'test.md', 'chunk_index': 1, 'content': 'Foo bar'},
    {'source_file': 'test2.md', 'chunk_index': 0, 'content': 'Baz qux'}
]
store.add_vectors(vectors, metadata)
print('After add size:', store.size)

results = store.search(vectors[0], top_k=2)
print('Search results:', len(results), results[0].content if results else 'empty')

store.save('data/faiss_index')
print('Saved OK')

store2 = FaissStore(dimension=1024)
store2.load('data/faiss_index')
print('Loaded size:', store2.size)

store.reset()
print('After reset size:', store.size)
"
```

Expected: 输出显示正确的 size 变化和搜索结果。

- [ ] **Step 3: Commit**

```bash
git add app/storage/faiss_store.py
git commit -m "feat: FAISS 向量索引封装"
```

---

### Task 4: 文档元数据存储

**Files:**
- Create: `app/storage/doc_store.py`

**Interfaces:**
- Consumes: 无
- Produces: `DocStore` 类，方法 `save(chunks)`, `load() -> dict | None`, `get_file_list() -> list[str]`, `get_status() -> dict`

- [ ] **Step 1: 创建 app/storage/doc_store.py**

```python
import json
from datetime import datetime
from pathlib import Path


class DocStore:
    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._meta_file = self.base_path / "doc_metadata.json"

    def save(self, chunks: list[dict]) -> None:
        data = {
            "chunks": [
                {
                    "id": i,
                    "source_file": c["source_file"],
                    "chunk_index": c["chunk_index"],
                    "content": c["content"]
                }
                for i, c in enumerate(chunks)
            ],
            "last_build_time": datetime.now().isoformat(),
            "total_chunks": len(chunks)
        }
        with open(self._meta_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self) -> dict | None:
        if not self._meta_file.exists():
            return None
        with open(self._meta_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_file_list(self) -> list[str]:
        data = self.load()
        if not data:
            return []
        files = sorted(set(c["source_file"] for c in data["chunks"]))
        return files

    def get_status(self) -> dict:
        data = self.load()
        if not data:
            return {
                "index_exists": False,
                "total_chunks": 0,
                "last_build_time": None,
                "knowledge_base_files": []
            }
        return {
            "index_exists": True,
            "total_chunks": data["total_chunks"],
            "last_build_time": data["last_build_time"],
            "knowledge_base_files": self.get_file_list()
        }
```

- [ ] **Step 2: 验证文档存储功能**

```bash
python -c "
from app.storage.doc_store import DocStore

store = DocStore('data/faiss_index')

chunks = [
    {'source_file': 'java.md', 'chunk_index': 0, 'content': 'Hashmap is a map...'},
    {'source_file': 'java.md', 'chunk_index': 1, 'content': 'ArrayList is a list...'},
    {'source_file': 'spring.md', 'chunk_index': 0, 'content': 'Spring Boot is...'}
]
store.save(chunks)
print('Saved OK')

status = store.get_status()
print('Status:', status)

files = store.get_file_list()
print('Files:', files)
"
```

Expected: 正确的 status 和 files 列表。

- [ ] **Step 3: Commit**

```bash
git add app/storage/doc_store.py
git commit -m "feat: 文档元数据 JSON 存储"
```

---

### Task 5: Markdown 分块器

**Files:**
- Create: `app/utils/text_splitter.py`

**Interfaces:**
- Consumes: 无
- Produces: `MarkdownSplitter` 类，方法 `split_text(text, source_file) -> list[dict]`, `split_files(file_paths) -> list[dict]`

- [ ] **Step 1: 创建 app/utils/text_splitter.py**

```python
import re
from pathlib import Path


class MarkdownSplitter:
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def split_file(self, file_path: str | Path) -> list[dict]:
        file_path = Path(file_path)
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return self.split_text(text, source_file=file_path.name)

    def split_text(self, text: str, source_file: str) -> list[dict]:
        sections = self._split_by_headers(text)
        chunks = []
        chunk_index = 0
        for section_title, section_content in sections:
            blocks = self._split_into_blocks(section_title, section_content)
            for block in blocks:
                chunks.append({
                    "content": block,
                    "source_file": source_file,
                    "chunk_index": chunk_index
                })
                chunk_index += 1
        return chunks

    def _split_by_headers(self, text: str) -> list[tuple[str, str]]:
        pattern = r'^(#{1,3})\s+(.+)$'
        lines = text.split("\n")
        sections = []
        current_title = "Preamble"
        current_lines = []
        for line in lines:
            m = re.match(pattern, line)
            if m:
                if current_lines:
                    sections.append((current_title, "\n".join(current_lines)))
                current_title = m.group(2).strip()
                current_lines = []
            else:
                current_lines.append(line)
        if current_lines:
            sections.append((current_title, "\n".join(current_lines)))
        return sections

    def _split_into_blocks(self, title: str, content: str) -> list[str]:
        header = f"## {title}\n\n"
        full_text = header + content.strip()
        blocks = []
        if len(full_text) <= self.chunk_size:
            blocks.append(full_text)
            return blocks

        paragraphs = re.split(r'\n\s*\n', full_text)
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 <= self.chunk_size:
                current = current + "\n\n" + para if current else para
            else:
                if current:
                    blocks.append(current)
                if len(para) > self.chunk_size:
                    for i in range(0, len(para), self.chunk_size - self.chunk_overlap):
                        blocks.append(para[i:i + self.chunk_size])
                else:
                    current = para
        if current:
            blocks.append(current)
        return blocks

    def scan_md_files(self, directory: str | Path) -> list[Path]:
        directory = Path(directory)
        if not directory.exists():
            return []
        return sorted(directory.glob("*.md"))
```

- [ ] **Step 2: 创建测试用 md 文件并验证分块**

创建临时测试文件：

```bash
mkdir -p data/knowledge_base
```

创建 `data/knowledge_base/test_java.md`：

```markdown
# Java 集合框架

## HashMap
HashMap 是基于哈希表的 Map 接口实现，允许 null 键和 null 值。
线程不安全，初始容量 16，加载因子 0.75。
扩容时容量翻倍，使用头插法（JDK 1.7+ 改为尾插法）。

## ConcurrentHashMap
ConcurrentHashMap 是线程安全的 Map 实现。
JDK 1.7 及之前使用分段锁，JDK 1.8 改为 CAS + synchronized。
不允许 null 键和 null 值。

# Spring 框架

## Spring Boot
Spring Boot 是简化 Spring 应用开发的框架。
提供自动配置、内嵌服务器、起步依赖等特性。
```

- [ ] **Step 3: 验证分块功能**

```bash
python -c "
from app.utils.text_splitter import MarkdownSplitter

splitter = MarkdownSplitter(chunk_size=500, chunk_overlap=50)
chunks = splitter.split_file('data/knowledge_base/test_java.md')
print(f'Total chunks: {len(chunks)}')
for i, c in enumerate(chunks):
    print(f'  Chunk {i}: [{c[\"source_file\"]}#{c[\"chunk_index\"]}] len={len(c[\"content\"])}')
    print(f'    Preview: {c[\"content\"][:80]}...')
"
```

Expected: 至少产出 3 个 chunks，每个包含标题和内容。

- [ ] **Step 4: Commit**

```bash
git add app/utils/text_splitter.py data/knowledge_base/test_java.md
git commit -m "feat: Markdown 分块器实现"
```

---

### Task 6: Embedding 服务客户端

**Files:**
- Create: `app/services/embedding.py`

**Interfaces:**
- Consumes: `settings` from `app.config`
- Produces: `EmbeddingService` 类，方法 `encode(texts: list[str]) -> np.ndarray`（批量编码，L2 归一化）

- [ ] **Step 1: 创建 app/services/embedding.py**

```python
import numpy as np
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

SILICONFLOW_API = "https://api.siliconflow.cn/v1/embeddings"
BATCH_SIZE = 32


class EmbeddingService:
    def __init__(self):
        self.api_key = settings.siliconflow_api_key
        self.model = settings.siliconflow_model
        self.timeout = settings.request_timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def encode(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.array([]).reshape(0, 1024)

        all_vectors = []
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            for i in range(0, len(texts), BATCH_SIZE):
                batch = texts[i:i + BATCH_SIZE]
                vectors = await self._encode_batch(client, batch)
                all_vectors.append(vectors)

        result = np.vstack(all_vectors)
        if result.size > 0:
            norms = np.linalg.norm(result, axis=1, keepdims=True)
            norms[norms == 0] = 1
            result = result / norms
        return result

    async def _encode_batch(self, client: httpx.AsyncClient, texts: list[str]) -> np.ndarray:
        payload = {
            "model": self.model,
            "input": texts,
            "encoding_format": "float"
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        response = await client.post(SILICONFLOW_API, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        vectors = [item["embedding"] for item in data["data"]]
        return np.array(vectors, dtype=np.float32)
```

- [ ] **Step 2: 验证 Embedding 服务（需要真实 API Key）**

```bash
# 如果有 API Key，可在 .env 中配置后运行：
python -c "
import asyncio
from app.services.embedding import EmbeddingService

async def test():
    svc = EmbeddingService()
    vectors = await svc.encode(['Hello World', 'Test embedding'])
    print('Shape:', vectors.shape)
    print('Norm:', np.linalg.norm(vectors[0]))

asyncio.run(test())
"
```

如果没有 API Key，跳过此步骤，在集成测试时验证。

- [ ] **Step 3: Commit**

```bash
git add app/services/embedding.py
git commit -m "feat: 硅基 Embedding 服务客户端"
```

---

### Task 7: LLM 客户端

**Files:**
- Create: `app/services/llm_client.py`

**Interfaces:**
- Consumes: `settings` from `app.config`
- Produces: `LLMClient` 类，方法 `chat(prompt: str, system: str | None = None) -> str`

- [ ] **Step 1: 创建 app/services/llm_client.py**

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

BAILIAN_API = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


class LLMClient:
    def __init__(self):
        self.api_key = settings.bailian_api_key
        self.model = settings.bailian_model
        self.temperature = settings.llm_temperature
        self.timeout = settings.request_timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
    async def chat(self, prompt: str, system: str | None = None) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(BAILIAN_API, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
```

- [ ] **Step 2: 验证 LLM 客户端（需要真实 API Key）**

```bash
python -c "
import asyncio
from app.services.llm_client import LLMClient

async def test():
    client = LLMClient()
    resp = await client.chat('你好，请自我介绍')
    print('Response:', resp[:100])

asyncio.run(test())
"
```

- [ ] **Step 3: Commit**

```bash
git add app/services/llm_client.py
git commit -m "feat: 百炼 LLM 客户端实现"
```

---

### Task 8: 索引构建服务

**Files:**
- Create: `app/services/index_service.py`

**Interfaces:**
- Consumes: `EmbeddingService`（Task 6）, `FaissStore`（Task 3）, `DocStore`（Task 4）, `MarkdownSplitter`（Task 5）, `settings`（Task 1）
- Produces: `IndexService` 类，方法 `build_index(rebuild: bool = False) -> BuildResponse`, `get_status() -> IndexStatusResponse`

- [ ] **Step 1: 创建 app/services/index_service.py**

```python
from app.config import settings
from app.api.schemas import BuildIndexResponse, IndexStatusResponse
from app.services.embedding import EmbeddingService
from app.storage.faiss_store import FaissStore
from app.storage.doc_store import DocStore
from app.utils.text_splitter import MarkdownSplitter
from app.utils.logger import get_logger

logger = get_logger(__name__)


class IndexService:
    def __init__(self, faiss_store: FaissStore, doc_store: DocStore, embedding: EmbeddingService):
        self.faiss = faiss_store
        self.doc_store = doc_store
        self.embedding = embedding
        self.splitter = MarkdownSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap
        )

    async def build_index(self, rebuild: bool = False) -> BuildIndexResponse:
        md_files = self.splitter.scan_md_files(settings.kb_path)
        if not md_files:
            logger.warning("No .md files found in knowledge base directory")
            return BuildIndexResponse(
                status="warning",
                total_chunks=0,
                files_processed=0
            )

        logger.info(f"Found {len(md_files)} md files, processing...")
        chunks = []
        for f in md_files:
            file_chunks = self.splitter.split_file(f)
            chunks.extend(file_chunks)
        logger.info(f"Split into {len(chunks)} chunks")

        contents = [c["content"] for c in chunks]
        vectors = await self.embedding.encode(contents)
        logger.info(f"Embedded {len(vectors)} vectors")

        if rebuild:
            self.faiss.reset()

        self.faiss.add_vectors(vectors, chunks)
        self.faiss.save(settings.idx_path)
        self.doc_store.save(chunks)

        logger.info(f"Index built: {len(chunks)} chunks from {len(md_files)} files")
        return BuildIndexResponse(
            status="success",
            total_chunks=len(chunks),
            files_processed=len(md_files)
        )

    def get_status(self) -> IndexStatusResponse:
        doc_status = self.doc_store.get_status()
        faiss_loaded = self.faiss.is_loaded() if self.faiss else False
        return IndexStatusResponse(
            index_exists=doc_status["index_exists"] and faiss_loaded,
            total_chunks=doc_status["total_chunks"],
            last_build_time=doc_status["last_build_time"],
            knowledge_base_files=doc_status["knowledge_base_files"]
        )
```

- [ ] **Step 2: Commit**

```bash
git add app/services/index_service.py
git commit -m "feat: 索引构建服务实现"
```

---

### Task 9: RAG 服务编排

**Files:**
- Create: `app/services/rag_service.py`

**Interfaces:**
- Consumes: `EmbeddingService`（Task 6）, `FaissStore`（Task 3）, `LLMClient`（Task 7）, `settings`（Task 1）
- Produces: `RAGService` 类，方法 `query(question: str) -> QueryResponse`

- [ ] **Step 1: 创建 app/services/rag_service.py**

```python
from app.config import settings
from app.api.schemas import QueryResponse, SourceInfo
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient
from app.storage.faiss_store import FaissStore
from app.exceptions import IndexNotFoundError
from app.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = (
    "你是一个专业的 Java/后端技术面试官助手。"
    "请严格基于提供的参考资料回答问题。"
    "如果参考资料中没有相关内容，请明确说明。"
    "回答要准确、简洁、结构清晰。"
)


class RAGService:
    def __init__(self, faiss_store: FaissStore, embedding: EmbeddingService, llm: LLMClient):
        self.faiss = faiss_store
        self.embedding = embedding
        self.llm = llm
        self.top_k = settings.top_k

    async def query(self, question: str) -> QueryResponse:
        if not self.faiss.is_loaded():
            raise IndexNotFoundError("索引未构建，请先调用 /api/index/build")

        logger.info(f"Processing query: {question[:50]}...")

        query_vector = await self.embedding.encode([question])
        if query_vector.size == 0:
            raise ValueError("Failed to encode question")

        results = self.faiss.search(query_vector[0], self.top_k)
        if not results:
            logger.warning("No relevant chunks found")
            return QueryResponse(
                answer="抱歉，我在知识库中没有找到相关内容。请尝试重新构建索引或添加更多相关文档。",
                sources=[],
                retrieved_chunks=[]
            )

        context = "\n---\n".join([r.content for r in results])
        prompt = f"参考资料：\n{context}\n\n问题：{question}"

        answer = await self.llm.chat(prompt, SYSTEM_PROMPT)

        sources = [
            SourceInfo(
                file=r.source_file,
                chunk_index=r.chunk_index,
                score=r.score
            )
            for r in results
        ]

        return QueryResponse(
            answer=answer,
            sources=sources,
            retrieved_chunks=[r.content for r in results]
        )
```

- [ ] **Step 2: Commit**

```bash
git add app/services/rag_service.py
git commit -m "feat: RAG 服务编排实现"
```

---

### Task 10: API 路由与主入口

**Files:**
- Create: `app/api/routes.py`
- Create: `app/main.py`

**Interfaces:**
- Consumes: `RAGService`（Task 9）, `IndexService`（Task 8）, schemas（Task 2）, exceptions（Task 2）
- Produces: 完整的 FastAPI 应用，4 个 API 端点 + 异常处理 + lifespan

- [ ] **Step 1: 创建 app/api/routes.py**

```python
from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    QueryRequest, QueryResponse,
    BuildIndexRequest, BuildIndexResponse,
    IndexStatusResponse, HealthResponse
)
from app.exceptions import (
    IndexNotFoundError, EmbeddingAPIError,
    LLMAPIError, IndexBuildError
)
from app.services.rag_service import RAGService
from app.services.index_service import IndexService
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api")


def _get_rag() -> RAGService:
    from app.main import rag_service
    if rag_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return rag_service


def _get_indexer() -> IndexService:
    from app.main import index_service
    if index_service is None:
        raise HTTPException(status_code=503, detail="Service not initialized")
    return index_service


@router.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    rag = _get_rag()
    try:
        return await rag.query(request.question)
    except IndexNotFoundError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except (EmbeddingAPIError, LLMAPIError) as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.exception(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/index/build", response_model=BuildIndexResponse)
async def build_index(request: BuildIndexRequest):
    indexer = _get_indexer()
    try:
        return await indexer.build_index(rebuild=request.rebuild)
    except IndexBuildError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.exception(f"Index build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/index/status", response_model=IndexStatusResponse)
async def index_status():
    indexer = _get_indexer()
    return indexer.get_status()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    from app.main import faiss_store, embedding_service, llm_client
    return HealthResponse(
        status="ok",
        faiss_index="loaded" if faiss_store and faiss_store.is_loaded() else "empty",
        embedding_service="available" if embedding_service else "unavailable",
        llm_service="available" if llm_client else "unavailable"
    )
```

- [ ] **Step 2: 创建 app/main.py**

```python
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.routes import router
from app.services.embedding import EmbeddingService
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService
from app.services.index_service import IndexService
from app.storage.faiss_store import FaissStore
from app.storage.doc_store import DocStore
from app.utils.logger import get_logger

logger = get_logger(__name__)

faiss_store: FaissStore | None = None
doc_store: DocStore | None = None
embedding_service: EmbeddingService | None = None
llm_client: LLMClient | None = None
rag_service: RAGService | None = None
index_service: IndexService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global faiss_store, doc_store, embedding_service, llm_client, rag_service, index_service

    logger.info("Initializing services...")

    faiss_store = FaissStore(dimension=1024)
    doc_store = DocStore(settings.idx_path)
    embedding_service = EmbeddingService()
    llm_client = LLMClient()

    index_service = IndexService(faiss_store, doc_store, embedding_service)
    rag_service = RAGService(faiss_store, embedding_service, llm_client)

    idx_path = Path(settings.idx_path)
    if (idx_path / "index.faiss").exists():
        faiss_store.load(settings.idx_path)
        logger.info(f"Loaded existing index with {faiss_store.size} vectors")
    else:
        logger.info("No existing index found, index is empty")

    logger.info("Services initialized successfully")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="Java 程序员智能面试助手",
    description="基于 RAG + LLM 的 Java/后端技术问答系统",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router("/api", router=router)
```

- [ ] **Step 3: 验证应用启动**

```bash
python -c "
from app.main import app
print('FastAPI app created:', app.title)
print('Routes:', [r.path for r in app.routes])
"
```

Expected: 输出标题和路由列表。

- [ ] **Step 4: Commit**

```bash
git add app/api/routes.py app/main.py
git commit -m "feat: API 路由与主入口实现"
```

---

### Task 11: 启动与集成验证

**Files:**
- Create: `data/knowledge_base/` (用户自行放置 md 文件)

**Interfaces:**
- Consumes: 所有前序任务的成果
- Produces: 可运行的完整服务

- [ ] **Step 1: 启动服务**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Expected: 控制台输出 `Uvicorn running on http://0.0.0.0:8000`

- [ ] **Step 2: 验证健康检查接口**

```bash
curl http://localhost:8000/api/health
```

Expected:
```json
{
  "status": "ok",
  "faiss_index": "empty",
  "embedding_service": "available",
  "llm_service": "available"
}
```

- [ ] **Step 3: 验证索引状态接口**

```bash
curl http://localhost:8000/api/index/status
```

Expected: 返回 `index_exists: false`（因为还没有构建索引）

- [ ] **Step 4: 构建索引**

将真实的 Java/后端 md 文件放入 `data/knowledge_base/` 后：

```bash
curl -X POST http://localhost:8000/api/index/build \
  -H "Content-Type: application/json" \
  -d '{"rebuild": true}'
```

Expected:
```json
{
  "status": "success",
  "total_chunks": N,
  "files_processed": M
}
```

- [ ] **Step 5: 问答接口测试**

```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "HashMap 和 ConcurrentHashMap 的区别是什么？"}'
```

Expected: 返回包含 `answer`、`sources`、`retrieved_chunks` 的 JSON 响应。

- [ ] **Step 6: 验证 Swagger 文档**

打开浏览器访问 `http://localhost:8000/docs`，确认 4 个端点都已注册且可测试。

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "feat: 完整 RAG 系统实现，集成验证通过"
```

---

## Self-Review Checklist

**1. Spec Coverage:**
- ✅ 单轮问答（Task 9, 10）
- ✅ 预留多轮扩展（`messages` 参数可扩展）
- ✅ 知识库 md 文件（Task 5, 8）
- ✅ FAISS 向量数据库（Task 3）
- ✅ 百炼平台 LLM（Task 7）
- ✅ 硅基平台 Embedding（Task 6）
- ✅ API 触发索引构建（Task 10, `/api/index/build`）
- ✅ 4 个 API 端点（Task 10）
- ✅ 引用来源返回（Task 9, `sources` 字段）
- ✅ 配置管理（Task 1）
- ✅ 错误处理（Task 2, 10）

**2. Placeholder Scan:**
- 无 TBD、TODO、占位符

**3. Type Consistency:**
- `SearchResult` → `SearchResult` (一致)
- `QueryRequest/Response` → 在 `schemas.py` 和 `routes.py` 中一致
- `BuildIndexRequest/Response` → 一致
- 所有方法签名与文档一致
