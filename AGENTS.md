# AGENTS.md

> 面向 AI 智能体的项目开发指南
> 适用项目：RAG 知识库 / Java 程序员智能面试助手（Interview RAG）

本文件用于帮助 AI 智能体（及新开发者）快速理解本项目，遵守项目约定，安全地进行阅读、修改与扩展。

---

## 1. 项目概述

这是一个 **RAG（Retrieval-Augmented Generation，检索增强生成）** 项目，核心目标：

- 让用户上传个人技术知识库（Markdown / PDF / Word），自动构建向量索引；
- 基于 **检索增强生成** 回答「Java / 后端技术」相关问题，并支持 SSE 流式输出；
- 在此基础上扩展出 **AI 模拟面试、简历项目深挖、复习、RAG 离线评估、可观测性** 等产品能力线。

一句话：**用"知识库检索增强 LLM 生成"，做一款程序员面试助手。**

---

## 2. 技术栈

| 分类 | 选型 |
|------|------|
| Web 框架 | **Python · FastAPI 0.115** + uvicorn + Pydantic v2 / pydantic-settings |
| LLM（生成） | 阿里云百炼 **qwen3.7-max**（`BAILIAN_API_KEY` / `BAILIAN_MODEL`） |
| Embedding（向量化） | 硅基流动 **Qwen/Qwen3-Embedding-4B**（`SILICONFLOW_API_KEY`） |
| Rerank（重排） | 硅基流动 **Qwen/Qwen3-Reranker-4B** |
| 向量数据库 | **FAISS**（faiss-cpu，支持 HNSW / IVF / Flat） |
| 稀疏检索 | rank_bm25（BM25Okapi）· 可选 Whoosh · SQLite FTS |
| 会话/用户存储 | **Redis**（固定 `192.168.127.101:6379`，TTL 3600s，单会话 20 轮） |
| 历史问答搜索 | SQLite |
| 文档解析 | pypdf、python-docx |
| 认证 | passlib[bcrypt] + PyJWT |
| HTTP 客户端 | httpx（调用 LLM/Embedding API）、tenacity（重试） |
| 流式协议 | **SSE（Server-Sent Events）**：事件 `session / retrieval / token / done / error` |
| 可观测性 | OpenTelemetry（OTLP）、Prometheus 风格指标、Grafana（docs/observability） |
| 测试 | pytest（tests/ 目录） |
| 前端 | 原生 HTML + CSS + JS；CDN 引入 marked + highlight.js + DOMPurify |

---

## 3. 核心架构（RAG 流程关键模块）

```
文档加载/解析 ─→ 分块 ─→ 向量化 ─→ 索引入库（FAISS + BM25）
                                      │
问题输入 ─→ 查询改写 ─→ 混合检索(RRF融合) ─→ 重排 ─→ Parent扩展/去重
                                      │
                              ┌─────────┴─────────┐
                    检索结果+会话历史 ─→ Prompt 构建 ─→ LLM 生成 ─→ SSE/JSON 返回
                         │
                         旁路：响应缓存 · 幻觉评估(Faithfulness) · Token成本预算 · OTel
```

关键模块对应文件（均在 `app/services/`）：

| 阶段 | 模块 | 说明 |
|------|------|------|
| 文档解析 | `chunker.py` / `utils/text_splitter.py` | 读取 md/pdf/docx 并分块（`chunk_size=1000`，`overlap=200`） |
| 向量化 | `embedding.py` | 封装 Embedding API |
| 索引构建 | `index_service.py` / `index_pipeline.py` | 全量重建 + 增量索引，断点续传 `ingest_state.json` |
| 向量/元数据存储 | `storage/faiss_store.py` / `doc_store.py` | FAISS + chunk 文档持久化 |
| 稀疏检索 | `sparse_retriever.py` | BM25 / Whoosh / SQLite FTS 后端抽象 |
| 混合检索 | `retrieval_service.py`（`HybridRetriever`） | FAISS 稠密 + 稀疏，**RRF**（k=60）融合 |
| 查询改写 | `query_rewrite.py` | 背景改写，提升检索召回 |
| 重排 | `rerank_service.py` | SiliconFlow Rerank API 精排 |
| 缓存 | `cache_service.py` | Redis 响应缓存 |
| 生成编排 | `rag_service.py`（`RAGService`） | **核心编排**，流式/非流式全流程 |
| 会话存储 | `storage/session_store.py` | Redis 多轮对话历史 |

设计约定：
- **可配置开关**：查询改写/混合检索/重排/缓存等均有 `enable_*` 开关（`config.py` + `.env`）。
- **优雅降级**：Redis 不可用→禁用会话/缓存；BM25 缺失→退回 FAISS；OTel/评估失败→静默不阻塞主线。
- **单 worker 约束**：state 与 FAISS/index 落盘假定单进程，多 worker 需另行处理锁或换外部存储。

---

## 4. 开发规范

### 4.1 语言与环境
- 后端为 **Python 3.10+**，使用类型标注（PEP 484），项目大量使用 `X | None`、`list[dict]`、dataclass 等新语法。
- 建议用 Conda 隔离环境（见"常用命令"）。

### 4.2 代码风格（Python）
- 遵循 **PEP 8**；
- 提交前建议黑名单：无格式化工具强制时，至少保持 4 空格缩进、行宽约 100 字符；
- 使用 `from app.config import settings` 获取配置，不要在业务代码里散落魔法常量。

### 4.3 命名规范
- **模块/文件/函数/变量**：蛇形 `snake_case`（如 `index_service.py`、`build_index()`）；
- **类**：帕斯卡 `PascalCase`（如 `RAGService`、`HybridRetriever`、`FaissStore`）；
- **常量/枚举值**：全大写（如 `ALLOWED_EXTENSIONS`、`RRF_K`、`SYSTEM_PROMPT`、事件类型字符串用小写）；
- **路由前缀**：统一 `/api`（如 `/api/query`、`/api/interview`）；
- **Pydantic schema**：置于 `app/api/schemas.py` 或各 router 同文件（现有代码两种并存，新增优先放 `schemas.py` 或路由模块顶部）。

### 4.4 注释与文档
- 中文注释为主，重要模块/类加 docstring，说明职责与调用关系；
- 中文日志（`logger.info/logger.warning`）便于可观测；
- 注释说明"为什么"，而非复述代码。
- **Spec 落盘要求**：凡为新问题/新功能输出 Spec（问题描述、影响模块/文件、预期行为、技术方案概要、验收标准、风险与未知点），必须同步以 Markdown 文件写入 `docs/superpowers/specs/`，命名遵循 `YYYY-MM-DD-<主题>-design.md`（与目录内既有文件保持一致），禁止仅停留在对话中不落盘。

### 4.5 架构分层（新增代码的位置）
- 路由定义 → `app/api/`；请求/响应模型 → 各 API 模块或 `schemas.py`；
- 业务逻辑 → `app/services/`；
- 持久化 → `app/storage/`；
- 通用工具 → `app/utils/`；
- 配置 → `app/config.py`（不要硬编码地址/阈值）。
- 新增服务需在 `app/main.py` 的 lifespan 中完成初始化装配。

### 4.6 错误与安全
- 使用 `app/exceptions.py` 中的统一异常；API 层捕获并映射 HTTP 状态码；
- 文件操作注意路径穿越防护、扩展名白名单（md/pdf/docx）、临时文件（`~$`）过滤；
- 前端 DOM 注入 `innerHTML` 前必须 `escapeHtml()` 转义，Markdown 渲染用 DOMPurify 过滤。

---

## 5. 常用命令

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env   # 并填入 BAILIAN_API_KEY / SILICONFLOW_API_KEY 等

# 启动服务（开发，支持热重载）
uvicorn app.main:app --reload

# 运行测试
python -m pytest tests/            # 全部
python -m pytest tests/services/   # 仅服务层
```

依赖的外部服务：Redis（`192.168.127.101:6379`）、百炼 LLM API、硅基流动 Embedding/Rerank API（可选 Grafana/OTel Collector）。

---

## 6. 关键文件说明

| 文件 | 作用 |
|------|------|
| `app/main.py` | **后端入口**。FastAPI 应用、CORS、路由挂载、`lifespan` 中初始化全部单例服务，前端静态目录挂载 |
| `app/config.py` | **配置中心**。`Settings`（pydantic-settings），集中管理 LLM/Redis/RAG/可观测性等全部配置项 |
| `app/api/routes.py` | RAG 问答、索引、文件管理、会话管理、历史搜索等核心 REST/SSE 端点 |
| `app/services/rag_service.py` | **RAG 核心编排**。`RAGService(.query / .stream_query)`，串联改写→检索→重排→生成 |
| `app/services/retrieval_service.py` | 混合检索 `HybridRetriever`，FAISS + 稀疏 + RRF 融合 |
| `app/services/index_service.py` | 索引构建 / 状态查询 / 增量更新 |
| `app/services/interview_service.py` | AI 模拟面试逻辑（出题、评价、报告、薄弱点分析） |
| `app/services/deep_dive_service.py` | 简历项目深挖（层层追问，最大深度 5 层） |
| `app/services/evaluation_service.py` | RAG 离线评估（测试集生成 + 指标 + 报告） |
| `app/observability.py` | OTel 链路追踪初始化（可选，失败静默降级） |
| `app/storage/session_store.py` | Redis 多轮会话存储（历史存取、列表、清理） |
| `app/storage/faiss_store.py` | FAISS 向量存储（保存/加载/近似检索/元数据） |
| `frontend/index.html` · `frontend/js/app.js` | 前端单页应用入口与业务逻辑（面试/复习/问答/设置四视图） |
| `requirements.txt` | Python 依赖清单 |
| `.env.example` | 环境变量模板 |
| `tests/` | pytest 测试（services / storage / 规模化 e2e） |
| `PROBLEM.md` | **问题知识库**。Agent 调试/开发前提要，记录已确认的 Problem / Root Cause / Solution/git commit / 规则（详见第 7 节） |
| `docs/superpowers/` | 各功能迭代的实现计划与设计 spec（`plans/` 与 `specs/`） |
| `Dockerfile` | 部署镜像菜谱。`python:3.11-slim` 基础，`CMD` 以单 worker（`--workers 1`）启动，符合单进程约束 |
| `docker-compose.yml` | **Docker 部署总指挥**。`rag-app` + `redis` 双服务、`8000:8000` 端口、`./data` 卷挂载持久化、`.env` 注入密钥、健康检查 |
| `docs/docker-deploy-notes.md` | **Docker 部署/排障知识沉淀**。核心概念、部署命令、`docker compose` 底层逻辑、报错分层排查、配置与代码如何生效 |

---

## 7. Agent 调试流程（PROBLEM.md 使用要求）

> 本项目维护 `PROBLEM.md`（问题知识库）作为 Agent 长期复用的事实来源。**开发与 Debug 前必读。**

1. **开发 / Debug 前先读 `PROBLEM.md`**：先看"第 0 节 Critical Do/Don't"与"第 1 节 Problem Index"，确认自己的工作不会踩中已记录规则（缓存 key、SSE 会话、reranker 选型、单 worker 等）。
2. **按 Trigger 判断是否读具体记录**：遇到 `PROBLEM.md` 中出现的现象（如"流式中切换会话输出中断""缓存总不命中""进程 OMP 崩溃"），用对应记录的 `3. Trigger` / `5. Investigation Path` 定位，再决定是否深入。
3. **解决非 trivial 问题后更新对应 Problem Record**：回到 `PROBLEM.md` 对应 `PXX` 记录追加/修订（不清空历史），若无法映射则新建记录。
4. **不覆盖历史事实**：不得修改已确认的 Root Cause / Solution / commit / Status；新增证据用追加方式说明。
5. **resolved 问题复现先验证，不盲目重复修复**：若某已解决问题再次出现，先检查旧方案是否被代码回退、环境是否变化、输入是否变化、是否有新 reproduction，再动手——不得直接照搬旧修复。
6. **禁止编造**：`investigating` 状态如实标注未确认根因；写 `resolved` 必须有证据（提交号 / 测试 / 复现）。

### 7.1 不可协商的三大铁律 ⛔（Agent 入场必读）

> **[AUGMENT]** 从 `PROBLEM.md` 提炼的高压线，任何改动都不得违反。详细复盘、量化影响及门禁映射，参见项目根目录 `PROBLEM.md`（尤其 **§0a 核心哲学** 与 **Appendix 门禁**）。

- **⛔ 缓存键铁律（P001）**：`cache_service.make_key()` 绝对禁止混入 `session_id`、`msg_count` 或任何会话/轮次维度。相同原始问题必须生成完全相同的 Key。违反此条将导致缓存命中率归零（对应 §0-D5、PROBLEM.md P001、Appendix Door 5）。
- **⛔ 流式会话铁律（P002）**：SSE 事件处理中绝对禁止修改 `state.sessionId`。内容容器（`contentDiv`）必须通过 `getStreamingContentDiv(sessionId)` 动态获取，严禁闭包持有。切换会话时绝对禁止调用 `abort()` 中断进行中的流（对应 §0-D1/D2/D3、PROBLEM.md P002、Appendix Door 2/3）。
- **⛔ 本地重型资源铁律（P003/P004）**：RAG 重排模块强制使用 SiliconFlow API（`Qwen/Qwen3-Reranker-4B`），严禁加载本地 `BAAI/bge-reranker-v2-m3` 等需外网下载或含 OMP 冲突的模型（对应 §0-D6、PROBLEM.md P003/P004、Appendix Door 6）。