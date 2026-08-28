# ARCHITECTURE.md — 系统架构地图

> 系统整体结构、数据流、依赖方向与核心边界。全局架构地图，**不**写成每个 Python 文件的实现说明。
> 适用项目：RAG 知识库 / Java 程序员智能面试助手（Interview RAG） — FastAPI + Redis + FAISS。
>
> 本文档是**技术栈与模块索引的唯一事实来源**。分层职责边界见 `app/*/ *_LAYER.md`；技术决策与原因见 `DECISIONS.md`；历史问题见 `PROBLEM.md`。

---

## §1 项目定位

一个基于 **RAG（检索增强生成）+ LLM**、面向 **Java / 后端技术面试准备** 的智能问答与陪练系统。用户上传个人技术知识库（Markdown / PDF / Word）构建检索索引，系统通过"查询改写 → 混合检索(RRF) → 重排 → LLM 生成 → 幻觉/成本评估"完整流水线作答；并扩展出 **AI 模拟面试、简历项目深挖、复习、评估调优、可观测性** 等产品能力线。

一句话：**用"知识库检索增强 LLM 生成"，做一款程序员面试助手。**

---

## §2 技术栈（唯一事实来源）

> 变更选型时同步更新此处与 `.env.example`，其它文档一律引用本表。

| 层级 | 选型 |
|------|------|
| 后端框架 | Python · **FastAPI 0.115** + uvicorn + Pydantic v2 / pydantic-settings |
| LLM（文本生成） | 阿里云百炼 **qwen3.7-max**（`BAILIAN_API_KEY`） |
| Embedding（向量化） | 硅基流动 **Qwen/Qwen3-Embedding-4B**（`SILICONFLOW_API_KEY`） |
| Rerank（重排） | 硅基流动 **Qwen/Qwen3-Reranker-4B**（替代本地 BGE，规避 HuggingFace 不可达/ OMP 冲突，见 DECISIONS.md DR-003） |
| 向量库 | **FAISS**（faiss-cpu，HNSW / IVF / Flat，`vector_index_type`） |
| 稀疏检索 | rank_bm25（BM25Okapi）/ 可选 Whoosh / SQLite FTS（`sparse_backend`） |
| 会话 & 用户存储 | **Redis**（固定 `192.168.127.101:6379`，会话 TTL 3600s，单会话 20 轮）；Redis 不可用→禁用相应功能 |
| 历史问答索引（长期事实源） | **SQLite**（`search_store`，跨会话全文搜索 + 用户历史持久化，见 DR-010） |
| 文档解析 | pypdf、python-docx |
| 认证 | passlib[bcrypt]（密码哈希）+ PyJWT（JWT），`get_current_user` 依赖注入 |
| HTTP | httpx（调 LLM / Embedding / Rerank API）、tenacity（重试） |
| 流式协议 | **SSE**（Server-Sent Events）：事件 `session / retrieval / token / done / error`（见 DR-005） |
| 可观测性 | OpenTelemetry（OTLP，`otel_enabled` 开关）、Prometheus 风格 metrics（monitor）；Grafana + docker-compose（`docs/observability/`） |
| 测试 | pytest（`tests/`） |
| 前端 | 原生 HTML + CSS + JS；CDN 引入 marked + highlight.js + DOMPurify（安全链见 DR-009） |

---

## §3 端到端数据流

```
【索引侧】
文档上传(md/pdf/docx) → 解析分块(chunker: chunk_size=1000, overlap=200)
→ 向量化(embedding) → 索引入库(FAISS + BM25, ingest_state.json 断点续传)

【查询侧】
问题输入 → 查询改写(可关) → 混合检索(HybridRetriever, RRF k=60 融合 FAISS 稠密+稀疏, top-20)
→ 重排(RerankService, top_k=5) → Parent 上下文扩展 + 去重
→ Prompt 构建(+ 会话历史最近 5 轮 + 用户短期记忆/长期恢复) → LLM 流式/非流式生成
→ SSE/JSON 返回（含 retrieval 来源与 token 事件）

【旁路】
响应缓存(仅原始问题为 key) · 幻觉评估(Faithfulness) · 会话 Token 成本预算 · OTel 链路追踪
```

- 服务装配（lifespan）：`Storage(SessionStore/UserStore/SearchStore/FaissStore/DocStore)` + `Embedding/LLMClient`
  → `SparseRetriever` + `HybridRetriever` → `RerankService` → `QueryRewrite` + `ResponseCache`
  → `IndexService` → `RAGService` → 业务服务（`InterviewService` / `DeepDiveService` / `EvaluationService`）。
- 单 worker 落盘模型见 DR-002；依赖失败优雅降级见 DR-001。

---

## §4 分层结构与依赖方向

```
API 层 (app/api)         把关 HTTP/Schema/鉴权/错误映射 —— 见 api/API_LAYER.md
   │ 路由 → 调用
服务层 (app/services)     业务编排与 RAG 管线 —— 见 services/SERVICES_LAYER.md
   │ 调用
存储层 (app/storage)      持久化与检索原语 —— 见 storage/STORAGE_LAYER.md
工具层 (app/utils)        纯函数工具 —— 见 utils/UTILS_LAYER.md
```

**依赖方向（禁止反向 / 横向越界）**：
- 允许：API → Services → Storage / Utils。
- 禁止：Services 反向依赖 API；Storage 依赖 Services；Utils 依赖任何上层或持有全局可变状态；同一层模块间尽量不横向直接互调（需经所属层编排）。
- 地基组件：`app/config.py`（统一配置，settings）贯串所有层；`app/exceptions.py`（统一异常，API 层映射为状态码）；`app/main.py`（唯一装配点，lifespan 初始化全部单例）。
- 配置铁律：业务代码不散落魔法常量，一律 `from app.config import settings`；修改 `.env`/`config.py` 需重启进程（`Settings()` 在 import 时一次性读取）。

---

## §5 模块地图（逐文件一句话索引）

> 分层职责与契约以对应 `*_LAYER.md` 为准，此处仅为快速定位文件。

```
app/
├── main.py                FastAPI 入口：CORS、路由挂载、lifespan 装配全部单例、前端静态目录
├── config.py              配置中心：pydantic-settings，集中管理 LLM/Redis/RAG/可观测
├── exceptions.py          统一异常定义；API 层捕获并映射 HTTP 状态码
├── observability.py       OTel 链路追踪初始化（可选，失败静默降级）
├── api/                   【Layer: API_LAYER】
│   ├── routes.py          RAG 问答 / 索引 / 文件 / 会话 / 搜索 核心 REST/SSE 端点
│   ├── auth.py            注册 / 登录 / JWT / get_current_user 依赖
│   ├── interview.py       AI 模拟面试全流程端点
│   ├── deep_dive.py       简历项目深挖端点
│   ├── evaluation.py      RAG 离线评估端点
│   └── schemas.py         请求 / 响应 Pydantic 模型
├── services/              【Layer: SERVICES_LAYER，含 RAG 管线决策所有权】
│   ├── rag_service.py     核心 RAG 编排（.query / .stream_query）
│   ├── retrieval_service.py  混合检索 HybridRetriever（FAISS + 稀疏 + RRF k=60）
│   ├── sparse_retriever.py   稀疏检索后端抽象与降级链
│   ├── index_service.py      索引构建 / 状态 / 增量更新
│   ├── index_pipeline.py     规模化索引管线（断点续传、并发分批）
│   ├── chunker.py / utils/text_splitter.py  文本分块（1000 / 200）
│   ├── embedding.py           Embedding API 封装与降级
│   ├── llm_client.py          LLM 生成（流式 / 非流式）
│   ├── query_rewrite.py       查询背景改写（可开关）
│   ├── rerank_service.py      SiliconFlow Rerank 精排
│   ├── cache_service.py       Redis 响应缓存（key 仅原始问题，见 DR-004）
│   ├── auth_service.py        认证逻辑
│   ├── rate_limiter.py / session_cost.py  限流 / 会话 Token 成本预算
│   ├── monitor.py / eval_monitor.py        指标采集
│   ├── interview_service.py / interview_agent.py  AI 面试
│   ├── deep_dive_service.py / resume_parser.py  简历深挖 / 简历解析
│   ├── topic_tracker.py       知识点覆盖 / 薄弱点分析
│   └── evaluation_service.py / eval_testset.py / eval_metrics.py  评估
├── storage/               【Layer: STORAGE_LAYER】
│   ├── faiss_store.py       FAISS 向量存储（保存/加载/近似检索/元数据）
│   ├── doc_store.py         chunk 文档持久化（JSON）
│   ├── session_store.py     Redis 会话（短期热数据，多轮上下文，见 DR-010）
│   ├── user_store.py        Redis 用户本体（认证）
│   ├── search_store.py      SQLite 历史搜索 + 长期记忆（DR-010）
│   ├── interview_store.py / deep_dive_store.py  业务数据持久化
└── utils/                 【Layer: UTILS_LAYER】
    ├── logger.py            日志
    └── text_splitter.py     文本切分（供 chunker）

frontend/                  原生 SPA：index.html（AI面试/复习/问答/设置）+ css/style.css + js/app.js
data/                      运行时数据：knowledge_base/ · faiss_index/ · bm25_index.pkl · ingest_state.json · search.db
tests/                     pytest：services + storage + 规模化回归
docs/                      架构/决策/流程/问题/spec/evaluation（见「文档导航」）
```

---

## §6 部署形态

- **Docker**：`docker-compose.yml` 编排 `rag-app` + `redis` 双服务，`8000:8000`，`./data` 卷挂载持久化，`.env` 注入密钥，健康检查。
- `Dockerfile`：`python:3.11-slim` 基础，`CMD` 以 **单 worker（`--workers 1`）** 启动（符合 DR-002 单进程落盘约束）。
- 详细部署 / 排障见 `docs/docker-deploy-notes.md`；可观测性部署见 `docs/observability/`。
- 外部依赖：Redis、百炼 LLM、硅基 Embedding/Rerank；可选 Grafana / OTel Collector。

---

## 主要 API 端点速览

| 分组 | 端点 | 功能 |
|------|------|------|
| 问答 | `POST /api/query` · `POST /api/query/stream` | RAG 问答 / SSE 流式 |
| 索引 | `POST /api/index/build` · `GET /api/index/status` | 构建 / 重建 · 状态 |
| 健康 | `GET /api/health` | FAISS / Embedding / LLM / Redis |
| 会话 | `POST/GET /api/sessions` · `GET/DELETE /api/sessions/{id}` | 建 / 列 / 取 / 删 / 清空（按用户隔离，DR-010） |
| 文件 | `GET /api/files` · `POST /api/files/upload` · `DELETE /api/files/{filename}` | 知识库管理 |
| 搜索 | `GET /api/search?q=` | 跨会话历史全文搜索+高亮（按用户） |
| 认证 | `POST /api/auth/register` `login` · `GET /api/auth/me` | 注册 / 登录 / JWT |
| 面试 | `POST /api/interview/start` `answer` `end` · `GET .../report` `history` `stats` `today` `coverage` | AI 模拟面试 |
| 深挖 | `POST /api/deepdive/analyze` `start` `answer` `end` | 简历项目追问 |
| 评估 | `POST /api/eval/generate-testset` `run` · `GET /api/eval/jobs/{id}` `reports` | RAG 能力评估 |

---

## 文档导航

> 新增文档先判断类别再落位（见 `AGENTS.md` §0）。

| 问题 | 去哪读 |
|------|--------|
| 我该遵守什么硬规则？ | `AGENTS.md` |
| 任务怎么做 / 流程 / 验收？ | `PROCESS.md` |
| 为什么这么设计 / 长期决策？ | `DECISIONS.md` |
| 系统怎么组织？ | 本文件（ARCHITECTURE.md） |
| 某层允许负责什么 / 禁止什么？ | `app/*/ *_LAYER.md` |
| 哪里有问题？ | `PROBLEM.md` |
| 准备怎么改？ | `docs/superpowers/specs/` |
| 改完实际怎么样？ | `docs/evaluation/` |