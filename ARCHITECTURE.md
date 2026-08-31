# ARCHITECTURE.md — 系统架构

> 回答"系统是什么 / 核心数据流 / 核心模块 / 边界在哪里"。全局架构地图，**不**写成每个 Python 文件的实现说明，**不**重复问题调查（那是 `PROBLEM.md` + `docs/problems/`）。
> 适用项目：RAG 知识库 / Java 程序员智能面试助手（Interview RAG）— FastAPI + Redis + FAISS，当前主线为确定性编排 Agent 面试系统（分支 `agent-dev`）。
>
> 本文档是**技术栈与模块索引的唯一事实来源**。分层职责见 `app/*/ *_LAYER.md`；技术决策与原因见 `DECISIONS.md`（DR）；问题注册表见 `PROBLEM.md`；问题档案见 `docs/problems/`。

---

## §1 Project Thesis

**一句话**：从 RAG Demo 演进为**可评测、可降级、可观测、可持久化**的工程化 RAG 系统，面向 Java / 后端程序员面试场景；当前正在其上叠加**确定性编排 Agent 面试系统**。

三阶段演进主张：

1. **RAG Demo**（能跑通）：检索增强生成，回答知识库问题。
2. **工程化 RAG**（已完成）：检索质量用评测闭环量化（Testset → Baseline → Ablation → Decision → Gate）；管线可配置、可降级；缓存 / SSE / 持久化 / 用户隔离 / 成本控制全部工程化。
3. **确定性编排 Agent**（进行中，`agent-dev`）：把"面试官"从硬编码服务升级为**状态机 + LLM 角色节点**的可编排、可归因、可评测 Agent 系统（`interview_mode=legacy|agent`，默认 legacy）。

> 核心工程主张：**检索与生成的取舍要用实验数据决定，而不是默认"组件越多越好"**——消融实验证明 qr+rr 同开 MRR 反而回落（见 §3.2），这是本项目最重要的工程故事之一。

---

## §2 技术栈（唯一事实来源）

> 变更选型时同步更新此处与 `.env.example`，其它文档一律引用本表。

| 层级 | 选型 |
|------|------|
| 后端框架 | Python · **FastAPI 0.115** + uvicorn + Pydantic v2 / pydantic-settings |
| LLM（文本生成） | 阿里云百炼 **qwen-turbo**（`BAILIAN_API_KEY`）；agent 分级 heavy 用 `qwen-plus`（DR：多模型分级，见 Agent spec） |
| Embedding（向量化） | 硅基流动 **Qwen/Qwen3-Embedding-4B**（`SILICONFLOW_API_KEY`） |
| Rerank（重排） | 硅基流动 **Qwen/Qwen3-Reranker-4B**（替代本地 BGE，规避 OMP/HF 失败，见 DR-003 / P003） |
| 向量库 | **FAISS**（faiss-cpu，HNSW / IVF / Flat，`vector_index_type`） |
| 稀疏检索 | rank_bm25（BM25Okapi）/ 可选 Whoosh / SQLite FTS（`sparse_backend`） |
| 会话 & 用户热数据 | **Redis**（固定 `192.168.127.101:6379`，会话 TTL 3600s，单会话 20 轮）；Redis 不可用→禁用相应功能（DR-001/007） |
| 历史问答索引（长期事实源） | **SQLite**（`search_store`，跨会话全文搜索 + 用户历史持久化，DR-010） |
| 文档解析 | pypdf、python-docx |
| 认证 | passlib[bcrypt] + PyJWT，`get_current_user` 依赖注入 |
| HTTP | httpx（调 LLM / Embedding / Rerank API）、tenacity（重试） |
| 流式协议 | **SSE**：事件 `session / retrieval / token / done / error`（DR-005 / P002） |
| 可观测性 | OpenTelemetry（OTLP，`otel_enabled` 开关）+ Prometheus 风格 metrics（monitor）；Grafana + docker-compose（`docs/observability/`） |
| Agent 编排（进行中） | 确定性状态机（`app/services/agent/state_machine.py`）+ trace 归因记录器；规划：结构化输出重试 / MCP 工具 / model_gateway 分级（见 `2026-08-31-agent-orchestration-refactor-impl-spec.md`） |
| 测试 | pytest（`tests/`） |
| 前端 | 原生 HTML + CSS + JS；CDN 引入 marked + highlight.js + DOMPurify（安全链 DR-009 / P005） |

---

## §3 核心 RAG Pipeline

### 3.1 查询侧检索链（生产默认全开，每步可关 / 可降级）

```text
问题输入
→ [qr] 查询改写（enable_query_rewrite，可关）
→ [hybrid] 混合检索：FAISS 稠密 + BM25 稀疏，RRF（k=60）融合，top-20（enable_hybrid_search）
→ [rr] 重排（SiliconFlow，top_k=5，enable_rerank）
→ Parent 上下文扩展 + 去重
→ Prompt 构建（+ 会话历史最近 N 轮 + 用户短期/长期记忆）
→ [gen] LLM 生成（qwen-turbo，流式/非流式）
→ SSE / JSON 返回（含 retrieval 来源与 token 事件）
```

旁路：响应缓存（key 仅原始问题，DR-004 / P001）· 幻觉评估（Faithfulness）· 会话 Token 成本预算 · OTel 链路追踪。

**统一检索门面 `RetrievalFacade`**（Part B 产物）：问答与面试复用同一条已验证管线，策略差异在 facade 之上（问答=原始问题；面试评价=「问题 + 回答」拼接；追问默认不检索，`enable_interview_followup_retrieval`）。任一环节失败优雅降级（DR-001），facade 失败回退 raw FAISS。

### 3.2 质量闭环（Retrieval Quality Loop）

```text
Testset（手写核心集 + LLM 扩展，四维度）→ Baseline → Ablation（qr × rr 4 组）
→ Metrics（recall@k / mrr / faithfulness）→ Decision → Gate（门禁 Door 1–14）
```

- 数据集 / 指标口径 / 结论的**唯一事实源**：`docs/evaluation/retrieval_ablation_decision.md`。
- 关键实验事实（一句话 + 指针，不复制正文）：单模块开启均改善召回；**qr + rr 联合开启无叠加收益、MRR 反而回落（0.829→0.798），属排序问题而非召回问题** → 生产默认保留 `qr_on + rr_on`，回落列为参数优化项。详见 `docs/evaluation/retrieval_ablation_decision.md`。

### 3.3 索引侧

```text
文档上传(md/pdf/docx，白名单+路径穿越防护)
→ 解析分块（chunker：chunk_size=1000, overlap=200）
→ 向量化（embedding）→ 索引入库（FAISS + BM25，ingest_state.json 断点续传，幂等可重入）
```

---

## §4 Engineering Reliability Architecture（可靠性架构）

> 统一工程思想：**外部依赖不可靠，核心 RAG 主链路不能依赖任何单一可选组件才能工作。** 本表是散落在各处的降级规则（DR-001/002/003/007/008/010）的收敛视图。

### 4.1 三级模型

| 级别 | 组件 | 失效时行为 |
|------|------|-----------|
| **核心主链路**（必须可用） | FAISS 稠密检索 · LLM 生成（qwen-turbo） | 无降级路径，直接不可用（health 检查暴露） |
| **可选增强**（不可用则降级） | Redis 会话/缓存 · BM25 稀疏 · query rewrite · rerank · parent 扩展 · OTel · SQLite 历史恢复 · agent 角色节点 | 见下表，禁用或回退，不阻塞主线 |
| **旁路 / 支撑** | 幻觉评估 · 成本预算 · 限流 · trace | 失败静默或记录，不影响回答 |

### 4.2 失败 fallback 矩阵（DR-001 及各档案）

| 依赖 | 失败 → fallback | 依据 |
|------|-----------------|------|
| Redis unavailable | 会话 / 缓存禁用（`available=False`），问答降级为无状态 | DR-001/007；D7 |
| BM25 / sparse 缺失 | 回退 FAISS-only（稠密检索仍可用） | DR-001；D7 |
| Rerank API 失败 | 跳过重排，直接用 RRF 结果 | DR-001/003 |
| query rewrite 失败 | 用原始问题直接检索 | DR-001 |
| OTel unavailable | 可观测性禁用，静默 | DR-001 |
| LLM 结构化输出 malformed | parser 剥离围栏 / 兜底默认值，失败不阻塞主流程 | DR-008 / P008 |
| SQLite 异常 | Redis-only 降级（历史恢复失效，会话仍可用） | DR-010 |
| facade 失败 | 回退 raw FAISS | Part B 设计 |
| agent 角色节点失败 | 结构化输出重试（≤3 次）→ 逃生舱 / 规则兜底（题目作废跳下一考点） | Agent spec 附录 B/C |

---

## §5 分层结构与依赖方向（Law of Layers）

```text
API 层 (app/api)         把关 HTTP/Schema/鉴权/错误映射 —— api/API_LAYER.md
   │ 路由 → 调用
服务层 (app/services)     业务编排与 RAG 管线（决策所有权表见 SERVICES_LAYER.md §6）
   │ 调用
存储层 (app/storage)      持久化与检索原语 —— storage/STORAGE_LAYER.md
工具层 (app/utils)        纯函数工具 —— utils/UTILS_LAYER.md
```

- 允许：API → Services → Storage / Utils；禁止反向 / 横向越界。
- 地基组件：`app/config.py`（统一配置）、`app/exceptions.py`（统一异常）、`app/main.py`（唯一装配点，lifespan 初始化单例；`interview_mode` 工厂在此分支装配 legacy / agent）。
- 配置铁律：业务代码不散落魔法常量，一律 `from app.config import settings`；修改 `.env`/`config.py` 需重启进程（`Settings()` import 时一次性读取，D12）。

---

## §6 模块地图（按层一句话索引；契约以 `*_LAYER.md` 为准）

```text
app/
├── main.py / config.py / exceptions.py / observability.py   装配点 / 配置中心 / 统一异常 / OTel 初始化
├── api/             routes（问答/索引/文件/会话/搜索）· auth · interview · deep_dive · evaluation · schemas
├── services/
│   ├── rag_service · retrieval_facade · retrieval_service(Hybrid,RRF) · sparse_retriever
│   ├── query_rewrite · rerank_service · embedding · llm_client · chunker · index_service · index_pipeline
│   ├── cache_service（DR-004）· auth_service · rate_limiter · session_cost · monitor · eval_monitor
│   ├── interview_service(legacy) · interview_agent · deep_dive_service · resume_parser · topic_tracker
│   ├── evaluation_service · eval_testset · eval_metrics
│   └── agent/        （主线）state_machine · trace（W1 已落地）；roles/structured_output/tools/orchestrator/model_gateway（W1–W2 规划）
├── storage/          faiss_store · doc_store · session_store(Redis) · user_store · search_store(SQLite) · interview_store · deep_dive_store
└── utils/            logger · text_splitter

frontend/   原生 SPA（AI面试/复习/问答/设置）+ SSE 流式渲染
data/       knowledge_base/ · faiss_index/ · bm25_index.pkl · ingest_state.json · search.db · eval_testset.json · interviews.db
tests/      pytest：services + storage + 规模化回归（含 agent 单测）
docs/       PROBLEM.md + docs/problems/ · evaluation/ · superpowers/ · interview-materials/ · observability/ · docker-deploy-notes.md
```

---

## §7 部署形态

- **Docker**：`docker-compose.yml` 编排 `rag-app` + `redis` 双服务，`8000:8000`，`./data` 卷挂载持久化，`.env` 注入密钥，健康检查。
- `Dockerfile`：`python:3.11-slim`，`CMD` 以**单 worker（`--workers 1`）** 启动（DR-002 / P006 单进程落盘约束）。
- 外部依赖：Redis、百炼 LLM、硅基 Embedding/Rerank；可选 Grafana / OTel Collector。
- 详细部署 / 排障见 `docs/docker-deploy-notes.md`；可观测性部署见 `docs/observability/`。

---

## 附：主要 API 端点（分组速览，细节见代码与 PROCESS §7）

| 分组 | 端点 |
|------|------|
| 问答 | `POST /api/query` · `/api/query/stream`（SSE） |
| 索引/健康 | `POST /api/index/build` · `GET /api/index/status` · `GET /api/health` |
| 会话/文件/搜索 | `/api/sessions*` · `/api/files*` · `GET /api/search?q=`（均按用户隔离，DR-010） |
| 认证 | `/api/auth/register|login|me` |
| 产品 | `/api/interview/start|answer|end|report|history|stats|today|coverage`（legacy/agent 同契约）· `/api/deepdive/*` |
| 评估 | `/api/eval/generate-testset|run` · `/api/eval/jobs/{id}|reports` |

---

## 文档导航

> 新增文档先判断类别再落位（见 `AGENTS.md` §0）。

| 问题 | 去哪读 |
|------|--------|
| 我该遵守什么硬规则？ | `AGENTS.md` |
| 任务怎么做 / 流程 / 验收？ | `PROCESS.md` |
| 为什么这么设计 / 长期决策？ | `DECISIONS.md` |
| 系统怎么组织？ | 本文件（ARCHITECTURE.md） |
| 某层负责什么 / 禁止什么？ | `app/*/ *_LAYER.md` |
| 哪里有问题（注册表）？ | `PROBLEM.md`（详细档案 `docs/problems/`） |
| 准备怎么改？ | `docs/superpowers/specs/` |
| 改完实际怎么样？ | `docs/evaluation/` |
