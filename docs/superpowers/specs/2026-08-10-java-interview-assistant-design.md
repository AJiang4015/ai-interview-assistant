# Java 程序员智能面试助手 — 系统设计文档

> 创建日期：2026-08-10
> 状态：待审核

---

## 1. 项目概述

### 1.1 目标
构建一个基于 RAG（检索增强生成）+ LLM 的 Java/后端程序员智能面试助手。用户输入技术问题，系统从内置知识库检索相关内容，LLM 基于检索结果生成回答，返回答案及引用来源。

### 1.2 第一版范围
- 纯后端服务（Python + FastAPI）
- 单轮问答（预留多轮扩展）
- 知识库：用户提供 Markdown 文件
- 向量数据库：FAISS
- LLM：百炼平台 qwen3.7-max-2026-05-20
- Embedding：硅基平台 Qwen/Qwen3-Embedding-4B

### 1.3 非目标（未来版本）
- 前端界面
- 多轮对话/追问
- 面试题生成与评价
- 多模态支持

---

## 2. 技术选型

| 类别 | 技术 | 版本 | 理由 |
|------|------|------|------|
| 语言 | Python | 3.10+ | 用户主力语言 |
| 框架 | FastAPI | 0.115.0 | 异步、自动文档、高性能 |
| 向量库 | FAISS | 1.8.0 | 轻量、高性能、纯本地 |
| LLM | qwen3.7-max | — | 百炼平台，API Key 通过环境变量 |
| Embedding | Qwen3-Embedding-4B | — | 硅基平台，API Key 通过环境变量 |
| HTTP 客户端 | httpx | 0.27.0 | 支持异步、连接池 |

---

## 3. 系统架构

### 3.1 分层架构

```
┌─────────────────────────────────────────────────┐
│                   API 层 (FastAPI)               │
│  路由定义 · 请求校验 · 响应格式 · 错误处理       │
├─────────────────────────────────────────────────┤
│                  服务层 (Services)               │
│  RAG 编排 · 索引构建 · Embedding · LLM 调用     │
├─────────────────────────────────────────────────┤
│                 存储层 (Storage)                 │
│  FAISS 向量索引 · 文档元数据 (JSON)             │
├─────────────────────────────────────────────────┤
│                基础设施层 (Infra)                │
│  配置管理 · 日志 · 外部 API 客户端               │
└─────────────────────────────────────────────────┘
```

### 3.2 查询流程

```
用户提问 → POST /api/query
         → RAG Service
              ├─ 1. Embedding 服务：问题 → 向量
              ├─ 2. FAISS 检索：Top-K 相关文档块
              ├─ 3. 上下文拼接：问题 + 检索文档
              ├─ 4. LLM 生成：百炼 API 调用
              └─ 5. 响应组装：answer + sources + chunks
```

### 3.3 索引构建流程

```
POST /api/index/build
         → Index Service
              ├─ 1. 扫描 knowledge_base_dir 下所有 .md 文件
              ├─ 2. Markdown 分块（按标题层级，chunk_size=1000, overlap=200）
              ├─ 3. 批量 Embedding（硅基 API，分批处理）
              ├─ 4. 写入 FAISS IndexFlatIP
              └─ 5. 持久化索引 + 文档元数据 JSON
```

---

## 4. 项目结构

```
RAGKonwLedge/
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI 应用入口，lifespan 管理
│   ├── config.py                # 配置管理（环境变量 + 默认值 + 校验）
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            # API 路由注册
│   │   └── schemas.py           # Pydantic 请求/响应模型
│   ├── services/
│   │   ├── __init__.py
│   │   ├── rag_service.py       # RAG 核心编排
│   │   ├── index_service.py     # 索引构建服务
│   │   ├── embedding.py         # Embedding 服务客户端（硅基）
│   │   └── llm_client.py        # LLM 服务客户端（百炼）
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── faiss_store.py       # FAISS 向量索引封装
│   │   └── doc_store.py         # 文档元数据存储
│   └── utils/
│       ├── __init__.py
│       ├── text_splitter.py     # Markdown 分块器
│       └── logger.py            # 日志配置
├── data/
│   ├── knowledge_base/          # 用户放置 md 文件的目录
│   └── faiss_index/             # FAISS 索引持久化
├── requirements.txt
├── .env.example                 # 环境变量模板
└── README.md
```

---

## 5. 核心模块设计

### 5.1 配置管理 (`app/config.py`)

使用 Pydantic `BaseSettings` 管理配置，自动从环境变量和 `.env` 文件读取：

```python
class Settings(BaseSettings):
    bailian_api_key: str                    # 必填，无默认
    bailian_model: str = "qwen3.7-max-2026-05-20"
    siliconflow_api_key: str                # 必填，无默认
    siliconflow_model: str = "Qwen/Qwen3-Embedding-4B"
    knowledge_base_dir: str = "data/knowledge_base"
    index_path: str = "data/faiss_index"
    top_k: int = 5
    chunk_size: int = 1000
    chunk_overlap: int = 200
    llm_temperature: float = 0.7
    request_timeout: int = 30

    model_config = {"env_file": ".env"}
```

### 5.2 Embedding 服务 (`app/services/embedding.py`)

- 调用硅基平台 `https://api.siliconflow.cn/v1/embeddings`
- 支持单条和批量编码
- 使用 `tenacity` 实现自动重试（3 次，指数退避）
- 所有向量 L2 归一化，便于内积相似度计算

```python
async def encode(self, texts: list[str]) -> np.ndarray:
    """批量将文本列表转为向量矩阵，返回 shape=(n, dim)"""
```

### 5.3 LLM 客户端 (`app/services/llm_client.py`)

- 调用百炼平台 `https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation`
- 支持 System Prompt 设定（RAG 回答指令）
- 预留流式输出接口

```python
async def chat(self, prompt: str, system: str | None = None) -> str:
    """发送 prompt 获取 LLM 回答"""
```

### 5.4 FAISS 存储 (`app/storage/faiss_store.py`)

- 使用 `IndexFlatIP`（内积 = 余弦相似度，向量已归一化）
- 方法列表：
  - `add_vectors(vectors: np.ndarray, metadata: list[dict])`
  - `search(query_vector: np.ndarray, top_k: int) -> list[SearchResult]`
  - `save(path: str)` / `load(path: str)`
  - `reset()`
- 线程安全：使用 `asyncio.Lock` 保护索引操作

### 5.5 文档元数据存储 (`app/storage/doc_store.py`)

- JSON 文件存储，结构：
```json
{
  "chunks": [
    {"id": 0, "source_file": "java-collections.md", "chunk_index": 0, "content": "..."}
  ],
  "last_build_time": "2026-08-10T14:30:00",
  "total_chunks": 245
}
```

### 5.6 Markdown 分块器 (`app/utils/text_splitter.py`)

- 按 Markdown 标题层级切分（`#` → `##` → `###`）
- 每个分块包含：标题文本 + 正文内容
- 支持 `chunk_size` 和 `chunk_overlap` 滑动窗口
- 输出：`[{"content": str, "source_file": str, "chunk_index": int}]`

### 5.7 RAG 服务 (`app/services/rag_service.py`)

核心编排：

```python
async def query(self, question: str) -> QueryResponse:
    # 1. 向量编码
    query_vector = await self.embedding.encode([question])

    # 2. FAISS 检索
    results = self.faiss.search(query_vector[0], self.top_k)

    # 3. 拼接上下文
    context = "\n---\n".join([r.content for r in results])

    # 4. LLM 生成
    system_prompt = "你是一个专业的 Java/后端技术面试官助手。请严格基于提供的参考资料回答问题。如果参考资料中没有相关内容，请明确说明。"
    answer = await self.llm.chat(f"参考资料：\n{context}\n\n问题：{question}", system_prompt)

    # 5. 返回结果
    return QueryResponse(
        answer=answer,
        sources=[{"file": r.source_file, "chunk_index": r.chunk_index, "score": r.score} for r in results],
        chunks=[r.content for r in results]
    )
```

### 5.8 索引服务 (`app/services/index_service.py`)

```python
async def build_index(self, rebuild: bool = False) -> BuildResponse:
    # 1. 扫描 md 文件
    md_files = self._scan_md_files()

    # 2. 分块
    chunks = self.splitter.split_files(md_files)

    # 3. 批量 Embedding（分批处理，每批 32 条）
    vectors = await self.embedding.encode_batch([c["content"] for c in chunks])

    # 4. 写入 FAISS
    if rebuild:
        self.faiss.reset()
    self.faiss.add_vectors(vectors, chunks)
    self.faiss.save()
    self.doc_store.save(chunks)

    return BuildResponse(total_chunks=len(chunks), files_processed=len(md_files))
```

---

## 6. API 设计

### 6.1 POST /api/query — 问答接口

**请求：**
```json
{
  "question": "Java 中 HashMap 和 ConcurrentHashMap 的区别？"
}
```

**响应：**
```json
{
  "answer": "HashMap 和 ConcurrentHashMap 的主要区别在于线程安全性...",
  "sources": [
    {"file": "java-collections.md", "chunk_index": 3, "score": 0.92},
    {"file": "java-concurrency.md", "chunk_index": 7, "score": 0.87}
  ],
  "retrieved_chunks": [
    "ConcurrentHashMap 是 Java 并发包提供的线程安全的 Map 实现...",
    "HashMap 在多线程环境下不安全，可能导致死循环..."
  ]
}
```

**错误响应：**
- `400 Bad Request` — 问题为空或过长
- `503 Service Unavailable` — 索引未构建
- `500 Internal Server Error` — LLM/Embedding API 调用失败

### 6.2 POST /api/index/build — 索引构建

**请求：**
```json
{
  "rebuild": false
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| rebuild | bool | false | true 清空重建，false 增量追加 |

**响应：**
```json
{
  "status": "success",
  "total_chunks": 245,
  "files_processed": 12
}
```

### 6.3 GET /api/index/status — 索引状态

**响应：**
```json
{
  "index_exists": true,
  "total_chunks": 245,
  "last_build_time": "2026-08-10T14:30:00",
  "knowledge_base_files": ["java-collections.md", "java-concurrency.md"]
}
```

### 6.4 GET /api/health — 健康检查

**响应：**
```json
{
  "status": "ok",
  "faiss_index": "loaded",
  "embedding_service": "available",
  "llm_service": "available"
}
```

---

## 7. 请求/响应模型

```python
# app/api/schemas.py

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

---

## 8. 错误处理

### 8.1 自定义异常

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

### 8.2 全局异常处理

在 `main.py` 中注册 `exception_handler`，将自定义异常映射到标准 HTTP 状态码：

| 异常类型 | HTTP 状态码 | 说明 |
|----------|-----------|------|
| `IndexNotFoundError` | 503 | 索引未构建 |
| `EmbeddingAPIError` | 502 | 上游 Embedding 服务不可用 |
| `LLMAPIError` | 502 | 上游 LLM 服务不可用 |
| `IndexBuildError` | 500 | 索引构建过程异常 |
| `ValueError` | 400 | 请求参数错误 |

---

## 9. 配置管理

### 9.1 环境变量

```env
# .env.example

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

### 9.2 安全规范

- `.env` 文件加入 `.gitignore`，不提交到版本库
- 代码中不硬编码任何 API Key
- 配置缺失时，服务启动时会报错并提示需要配置的环境变量名

---

## 10. 依赖清单

```
# requirements.txt

fastapi==0.115.0
uvicorn==0.32.0
pydantic==2.9.0
faiss-cpu==1.8.0
numpy==1.26.0
httpx==0.27.0
python-dotenv==1.0.0
tenacity==9.0.0
```

---

## 11. 部署与运行

### 11.1 开发环境

```bash
# 1. 创建虚拟环境
conda create -n interview-assistant python=3.10
conda activate interview-assistant

# 2. 安装依赖
pip install -r requirements.txt

# 3. 复制配置文件并填入 API Key
cp .env.example .env
# 编辑 .env 填入真实的 API Key

# 4. 放置知识库文件
# 将 Java/后端相关的 .md 文件放入 data/knowledge_base/

# 5. 启动服务
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 11.2 API 文档

启动后访问：`http://localhost:8000/docs`（FastAPI 自动生成的 Swagger UI）

### 11.3 使用流程

```bash
# 1. 首先构建索引
curl -X POST http://localhost:8000/api/index/build -H "Content-Type: application/json" -d '{"rebuild": true}'

# 2. 然后开始问答
curl -X POST http://localhost:8000/api/query -H "Content-Type: application/json" -d '{"question": "HashMap 的扩容机制是什么？"}'

# 3. 查看索引状态
curl http://localhost:8000/api/index/status

# 4. 健康检查
curl http://localhost:8000/api/health
```

---

## 12. 扩展点

第一版在以下方面预留了扩展能力：

| 扩展方向 | 预留位置 | 说明 |
|----------|---------|------|
| 多轮对话 | `rag_service.py` | 可扩展 messages 参数支持对话历史 |
| 流式输出 | `llm_client.py` | 可改用 httpx streaming 接口 |
| 面试题生成 | 新增 `question_service.py` | 基于知识库生成面试题 |
| 回答评价 | 新增 `evaluation_service.py` | LLM 作为评委评价回答质量 |
| 追问系统 | 新增 `followup_service.py` | 根据回答生成追问 |
| 前端 | — | FastAPI 可作为前端的后端 API |
| 多知识库 | `config.py` | `knowledge_base_dir` 可扩展为多个 |
