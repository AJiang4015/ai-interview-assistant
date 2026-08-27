# RAG 知识库项目概览文档

> 生成时间：2026-08-27
> 项目名称：Java 程序员智能面试助手（Interview RAG）
> 技术底座：**RAG（检索增强生成）+ LLM**

## 1. 项目定位

一个基于 **RAG + LLM** 面向 **Java / 后端技术面试准备** 的智能问答与陪练系统。用户上传个人知识库文档（Markdown / PDF / Word）构建检索索引，系统通过"查询改写 → 混合检索 → RAG 重排 → LLM 生成 → 幻觉/成本评估"的完整流水线作答；并在此之上演化出 **AI 模拟面试、简历项目深挖、复习、评估调优、可观测性** 等多条业务能力线。

## 2. 技术栈

| 层级 | 选型 |
|------|------|
| 后端框架 | Python · **FastAPI 0.115** + uvicorn + Pydantic v2 |
| LLM（文本生成） | 阿里云百炼 **qwen3.7-max**（`BAILIAN_API_KEY`） |
| Embedding（向量化） | 硅基流动 **Qwen/Qwen3-Embedding-4B**（`SILICONFLOW_API_KEY`） |
| Rerank（重排） | 硅基流动 **Qwen/Qwen3-Reranker-4B**（RAG 重排，替代本地 BGE，规避 HuggingFace 不可达问题） |
| 向量库 | **FAISS**（HNSW / IVF / Flat，本支持式切换） |
| 稀疏检索 | rank_bm25（BM25Okapi）/ 可选 Whoosh / SQLite FTS（`sparse_backend`） |
| 会话 & 用户存储 | **Redis**（固定地址 `192.168.127.101`，TTL 3600s，单会话 20 轮上限） |
| 历史问答索引 | SQLite（`search_store`，跨会话全文搜索） |
| 文档解析 | pypdf、python-docx |
| 认证 | passlib[bcrypt]（密码哈希）+ PyJWT（JWT）
| HTTP | httpx（调用 LLM / embedding API）、tenacity（重试） |
| 可观测性 | OpenTelemetry（OTLP 追踪，`otel_enabled` 开关）；Grafana + docker-compose（docs/observability）/ Prometheus 风格 metrics（monitor） |
| 前端 | 原生 HTML + CSS + JavaScript（无框架），CDN 引入 marked + highlight.js + DOMPurify |
| 流式协议 | **SSE（Server-Sent Events）**，事件类型 `session / retrieval / token / done / error` |

## 3. 目录结构

```
RAGKonwLedge/
├── app/                          # 后端主程序
│   ├── main.py                   # FastAPI 入口，服务装配/生命周期
│   ├── config.py                 # pydantic-settings 配置（含 .env）
│   ├── exceptions.py             # 统一异常定义
│   ├── observability.py          # OTel 追踪初始化（可静默降级）
│   ├── api/                      # 路由层（Pydantic schema + 端点）
│   │   ├── routes.py             # RAG问答/索引/文件/会话/搜索
│   │   ├── auth.py               # 注册/登录/JWT
│   │   ├── interview.py          # AI面试全流程
│   │   ├── deep_dive.py          # 简历项目深挖
│   │   ├── evaluation.py         # RAG 离线评估
│   │   └── schemas.py            # 请求/响应模型
│   ├── services/                 # 业务服务层
│   │   ├── rag_service.py        # 核心 RAG 编排（流式+非流式）
│   │   ├── index_service.py      # 索引构建/增量/状态
│   │   ├── index_pipeline.py     # 规模化索引管线
│   │   ├── retrieval_service.py  # 混合检索（FAISS+BM25，RRF融合）
│   │   ├── sparse_retriever.py   # 稀疏检索后端抽象
│   │   ├── query_rewrite.py      # 查询改写
│   │   ├── rerank_service.py     # RAG 重排
│   │   ├── cache_service.py      # 响应缓存（Redis）
│   │   ├── embedding.py          # Embedding 封装
│   │   ├── llm_client.py         # LLM 生成（流式/非流式）
│   │   ├── chunker.py / text_splitter.py  # 文本分块
│   │   ├── interview_service.py / interview_agent.py  # AI面试
│   │   ├── deep_dive_service.py  # 层层追问深挖
│   │   ├── resume_parser.py      # 简历 PDF 解析
│   │   ├── topic_tracker.py      # 知识点覆盖/薄弱点分析
│   │   ├── evaluation_service.py / eval_testset.py / eval_metrics.py / eval_monitor.py  # 评估
│   │   ├── auth_service.py       # 认证逻辑
│   │   ├── monitor.py            # 指标采集
│   │   └── session_cost.py       # 会话 Token 成本预算
│   ├── storage/                  # 持久化存储层
│   │   ├── faiss_store.py        # FAISS 向量存储
│   │   ├── doc_store.py          # chunk 文档存储（JSON）
│   │   ├── session_store.py      # Redis 会话
│   │   ├── user_store.py         # Redis 用户
│   │   ├── search_store.py       # SQLite 历史搜索
│   │   ├── interview_store.py / deep_dive_store.py
│   └── utils/                    # logger、文本分割
├── frontend/                     # 原生前端
│   ├── index.html                # 单页应用（AI面试/复习/问答/设置）
│   ├── css/style.css
│   └── js/app.js
├── data/                         # 运行时数据
│   ├── knowledge_base/           # 知识库原始文件（md/pdf/docx）
│   ├── knowledge_trees/          # 岗位知识树（Java后端/AI应用开发）
│   ├── faiss_index/  bm25_index.pkl(.fts.sqlite)  ingest_state.json  search.db
├── docs/
│   ├── observability/            # Grafana + docker-compose + 告警
│   └── superpowers/              # 各迭代的设计/计划文档（10+ 轮）
├── scripts/bench_rag_retrieval.py  # 检索性能基准
└── tests/                        # pytest（services + storage + 规模化回归）
```

## 4. 核心架构与数据流

### 4.1 服务装配（Lifecycle）
`main.py` 在 FastAPI lifespan 中初始化全部单例服务，依赖关系清晰：

`Redis(SessionStore/UserStore)`、`FaissStore`、`DocStore`、`EmbeddingService`、`LLMClient`
→ `SparseRetriever` + `HybridRetriever`（RRF 融合）→ `RerankService`
→ `QueryRewriteService`、`ResponseCache`
→ `IndexService`、`RAGService`
→ `ResumeParser`、`InterviewService`、`DeepDiveService`、`EvaluationService`、`TestSetGenerator`

### 4.2 RAG 检索流水线（`rag_service.py`）
对每次问答执行：
1. **查询改写**（QQ Rewrite，可用开关）→
2. **混合检索** HybridRetriever：FAISS 密向量 + 稀疏(BM25/Whoosh/FTS)，**RRF（k=60）**融合 → 取 top-20 →
3. **RAG 重排** RerankService（SiliconFlow API）→ 取 top_k=5 →
4. Parent 上下文扩展 + 去重 →
5. 拼接参考资料 + 会话历史（最近 5 轮）构建 Prompt →
6. **LLM 流式/非流式生成** →
7. SSE 或 JSON 返回，含 retrieval 的来源与 token 事件。
8. **缓存**：命中直接返回；写入 Redis。
9. **旁路监控**：抽样式幻觉评估（Faithfulness）、会话 Token 成本预算告警、OTel 追踪。

### 4.3 索引 pipeline（`index_service.py` / `index_pipeline.py`）
- 支持全量重建（`/api/index/build`）与增量单文件索引（上传后异步 `add_document`）。
- FAISS 支持 HNSW/IVF/Flat（`vector_index_type`），支持 `ingest_state.json` 断点续传、parent 块映射、并发分批入库（`concurrent_batches`）。
- 索引缺失/依赖失败时**优雅降级**（省 BM25 缺失退回 FAISS-only、Redis 不可用禁用缓存）。

### 4.4 前端（`frontend/`）
- 单页应用，四个视图：**AI面试 / 复习 / 问答 / 设置**。
- 问答视图走 SSE 流式渲染：流 ID 绑定发起会话，`requestAnimationFrame` 节流、增量 Markdown 解析、DOMPurify 安全过滤；CDN 失败回退纯文本。
- 设置视图合并**索引管理 + 知识库文件管理**；侧边栏含系统状态、会话历史、知识库文件列表。
- 主题色蓝紫系（主色 `#6054F1`）。

## 5. 核心功能清单

> 详细清单见下方独立章节（已按用户要求输出）。

## 6. 主要 API 端点

| 分组 | 端点 | 功能 |
|------|------|------|
| 问答 | `POST /api/query`<br>`POST /api/query/stream` | RAG 一次问答 / SSE 流式问答 |
| 索引 | `POST /api/index/build`<br>`GET /api/index/status` | 构建/重建索引 · 索引状态 |
| 健康 | `GET /api/health` | FAISS/Embedding/LLM/Redis 状态 |
| 会话 | `POST/GET /api/sessions`<br>`GET/DELETE /api/sessions/{id}` | 建/列/取历史/删/清空 |
| 文件 | `GET /api/files`<br>`POST /api/files/upload`<br>`DELETE /api/files/{filename}` | 知识库管理，删除后自动重建索引 |
| 搜索 | `GET /api/search?q=` | 跨会话历史全文搜索+高亮 |
| 认证 | `POST /api/auth/register` `login`<br>`GET /api/auth/me` | 注册/登录/JWT |
| 面试 | `POST /api/interview/start` `answer` `end`<br>`GET /api/interview/report` `history` `stats` `today` `coverage` | AI 模拟面试全流程 |
| 深挖 | `POST /api/deepdive/analyze` `start` `answer` `end` | 简历项目层层追问 |
| 评估 | `POST /api/eval/generate-testset` `run`<br>`GET /api/eval/jobs/{id}` `reports` | RAG 能力评估 |

## 7. 关键设计约定与容错

- **单 worker 约束**：state 与 FAISS/index 落盘假定单进程，多 worker 需自加文件锁或换外部存储。
- **优雅降级**：Redis 不可用 → 会话/缓存功能禁用；BM25 缺失 → 退回 FAISS；OTel/评估失败 → 静默不阻塞主线。
- **流式会话一致性**：SSE token 绑定发起会话 ID，切换会话不清请求；删除会话保留进行中流的数据结构使其自然收尾。
- **安全**：路径穿越防护、文件类型白名单（md/pdf/docx）、上传大小上限 50MB、`~$` 临时文件过滤。
- **评估体系**：离线 Metrics（faithfulness/recall 等）+ LLM-judge；测试集由 LLM 从知识库 chunk 生成。

## 8. 运行方式

```bash
# 1. 配置 .env（百炼 + 硅基 Key、Redis 地址）
cp .env.example .env

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动
uvicorn app.main:app --reload

# 4. 构建索引（首次或文档变更后）
curl -X POST http://localhost:8000/api/index/build -H "Content-Type: application/json" -d '{"rebuild": true}'
```

依赖服务：Redis（`192.168.127.101:6379`）；LLM/Embedding/Rerank 走远程 API；可选 Grafana/OTel Collector 用于可观测性。