# RAG 管道质量升级设计文档

> **日期**: 2026-08-12
> **状态**: 设计定稿

## 概述

当前 RAG 管道仅有"Embedding → FAISS 检索 → LLM 生成"的简单流程，缺少中间优化环节。本次升级增加四个模块，按优先级排列为：重排序（Re-ranker）→ 查询改写（Query Rewriting）→ 混合检索（Hybrid Search）→ 响应缓存（Response Cache）。

## 架构总览

```
用户提问
    → [查询改写] LLM 改写为更利于检索的表述
    → [混合检索] FAISS 稠密 + BM25 稀疏 并行检索 (top_k=20)
    → [RRF 融合] Reciprocal Rank Fusion 归一化排序
    → [重排序] bge-reranker-v2-m3 Cross-Encoder 精排取 top_k=5
    → [响应缓存] Redis cache:hash 命中直接返回
    → LLM 生成回答
    → 返回结果
```

## 1. 重排序（Re-ranker）

### 方案
使用 Cross-Encoder 模型 `BAAI/bge-reranker-v2-m3` 对 FAISS 召回的 top-K 重新打分排序。

### 设计
- **粗召 top_k**: 20（FAISS 检索）
- **精排 top_k**: 5（Cross-Encoder 重排序后取前 5）
- **模型**: `bge-reranker-v2-m3`，本地加载推理
- **部署方式**: 首次加载时下载模型（~1GB），后续推理使用 GPU 或 CPU
- **延迟**: 首次加载 5-10 秒，后续推理 ~100ms/次（GPU）或 ~500ms/次（CPU）

### 接口
```python
class RerankService:
    async def rerank(self, query: str, documents: list[str], top_k: int = 5) -> list[RerankResult]:
        """对检索结果重排序，返回精排后的 top_k 结果"""
```

### 新增依赖
- `sentence-transformers`
- `torch`

## 2. 查询改写（Query Rewriting）

### 方案
使用百炼 LLM（已有）对用户问题进行简短语义扩展，改写结果仅用于检索阶段，不替代原始问题。

### 设计
- **改写 prompt**: 约 50 tokens，简短指令
- **调用模型**: 百炼 qwen3.7-max（已有）
- **改写结果用途**: 仅用于 Embedding + FAISS 检索
- **原始问题用途**: 仍用于 LLM 生成最终回答
- **可配置开关**: 默认开启，可通过参数关闭

### 改写 prompt 示例
```
请将以下面试问题改写为更完整、更利于检索的表述，包含相关关键词，直接输出改写结果不要多余内容：

{question}
```

### 接口
```python
class QueryRewriteService:
    async def rewrite(self, question: str) -> str:
        """改写用户问题，返回更利于检索的表述"""
```

### 新增依赖
- 无（复用已有 LLMClient）

## 3. 混合检索（Hybrid Search）

### 方案
稠密向量检索（FAISS）+ 稀疏关键词检索（BM25）并行，使用 RRF（Reciprocal Rank Fusion）融合排序。

### 设计
- **稠密检索**: FAISS IndexFlatIP（已有），top_k=20
- **稀疏检索**: BM25（rank_bm25 库），top_k=20
- **RRF 公式**: `score = 1/(60 + rank_dense) + 1/(60 + rank_sparse)`
- **索引构建**: 文档分块时同时写入 FAISS 和 BM25 索引
- **BM25 索引存储**: `data/bm25_index.pkl`（序列化到磁盘）

### 接口
```python
class HybridRetriever:
    async def retrieve(self, query: str, top_k: int = 20) -> list[SearchResult]:
        """并行执行稠密+稀疏检索，RRF 融合后返回结果"""
```

### 新增依赖
- `rank_bm25`

## 4. 响应缓存（Response Cache）

### 方案
以 `sha256(question)` 为 cache key，缓存 LLM 的完整回答到 Redis。

### 设计
- **cache key**: `sha256(question + session_id + message_count)`
- **缓存内容**: `{ answer: str, sources: list, created_at: str }`
- **TTL**: 3600 秒（与 session TTL 一致）
- **存储位置**: Redis，namespace `cache:{hash}`
- **缓存命中时**: 模拟 SSE 事件流（session → retrieval → done），前端无需改动
- **缓存策略**: 仅新会话的首次提问启用缓存，会话内追问不缓存

### 接口
```python
class ResponseCache:
    async def get(self, key: str) -> dict | None:
        """获取缓存"""
    async def set(self, key: str, answer: str, sources: list):
        """写入缓存"""
    def make_key(self, question: str, session_id: str, msg_count: int) -> str:
        """生成 cache key"""
```

### 新增依赖
- 无（复用已有 Redis 连接）

## 文件变更清单

### 新建文件
- `app/services/rerank_service.py` — 重排序服务
- `app/services/query_rewrite.py` — 查询改写服务
- `app/services/retrieval_service.py` — 混合检索服务（含 BM25 + RRF）
- `app/services/cache_service.py` — 响应缓存服务

### 修改文件
- `app/services/rag_service.py` — 重构，集成四个新模块
- `app/services/index_service.py` — 索引构建时同时写入 BM25
- `app/config.py` — 新增配置项（rerank top_k, BM25 路径等）
- `app/main.py` — 注册新服务

### 不受影响
- 全部前端代码（`frontend/`）
- API 路由定义（`app/api/routes.py`）
- session 管理（`app/storage/session_store.py`）
- SQLite 搜索索引（`app/storage/search_store.py`）
- FAISS 存储（`app/storage/faiss_store.py`）
- 数据模型（`app/api/schemas.py`）

## 配置项变更

`app/config.py` 新增：
```python
rerank_top_k: int = 5          # 重排序后保留的结果数
rerank_model: str = "BAAI/bge-reranker-v2-m3"
enable_query_rewrite: bool = True
enable_hybrid_search: bool = True
bm25_index_path: str = "data/bm25_index.pkl"
cache_ttl: int = 3600
```