# RAG Knowledge Assistant — 检索增强的 Java 技术面试助手

用 **RAG（检索增强生成）+ 统一检索底座** 构建的 **Java / 后端技术面试准备与问答系统**：上传个人知识库（Markdown / PDF / Word），系统通过 `查询改写 → 混合检索 → 重排 → Parent 扩展 → LLM 生成` 流水线作答，并支持**多轮 AI 模拟面试**（出题、答题评价、报告、复习画像）。

> 项目的工程重点不是"接一个 LLM"，而是把**检索质量工程化**：用评测闭环量化、用统一检索门面复用、用消融实验驱动配置决策。

---

## 功能特性

- **知识库问答**：上传 md / pdf / docx → 分块(1000/200) → Embedding → FAISS + 稀疏索引。
- **SSE 流式回答**：`session / retrieval / token / done` 事件流，支持多会话并行与切换不中断。
- **AI 模拟面试**：按岗位/简历/JD 出题 → 答题评价（含评分原因、参考答案、来源溯源）→ 生成报告与知识点覆盖画像。
- **统一检索门面 `RetrievalFacade`**：问答与面试复用同一条已验证管线，管线上做策略差异。
- **检索评测闭环**：手写评测集 → 基线 → 门禁 → 消融，用数据决定 query rewrite / rerank 去留。
- **工程约束**：JWT 认证 + 全栈用户隔离、Redis 会话、响应缓存（key 仅原始问题）、成本/幻觉监控、优雅降级。

---

## 核心架构

```text
前端 SPA（原生 JS，SSE 流式）
   │
API 层（FastAPI）：/api/query · /stream · /interview · /auth(JWT) · /eval · /files · /sessions
   │
服务层
   ├─ 🌟 RetrievalFacade（统一检索门面）
   │     query rewrite → hybrid(RRF) → rerank → parent expansion → dedup
   │     （问答 & 面试共用，任一步骤失败优雅降级）
   ├─ RAGService（问答/流式） · InterviewService（AI 面试） · EvaluationService（评测）
   ├─ cache_service · eval_monitor(幻觉) · session_cost(成本) · monitor(OTel)
   │
存储层
   ├─ FaissStore（向量，flat/HNSW） · SparseRetriever（BM25/Whoosh/SQLite FTS）
   ├─ SessionStore（Redis 会话） · SearchStore（SQLite 长期历史）
   └─ DocStore · UserStore · InterviewStore
   │
外部依赖：阿里云百炼(LLM) · 硅基流动(Embedding/Rerank) · Redis · 可选 OTel/Grafana
```

技术选型：**FastAPI** + **FAISS** + **Redis** + **SQLite** + **SSE**；生成走百炼 `qwen-turbo`，Embedding/重排走硅基流动 `Qwen3` 系列；可观测性走 OpenTelemetry + Prometheus/Grafana。

---

## 当前完成能力

### Part A：检索评测闭环（基线 + 消融）
- 手写评测集（四类难题：跨文档推理 / 易混辨析 / 口语面试 / 边界反直觉）+ LLM 扩展集。
- `python scripts/eval_runner.py` 产出基线与 query rewrite × rerank 消融矩阵。
- 结论：**rerank 召回收益最大(+0.063)**，query rewrite 正向；两者同开会带来 MRR 回落（0.829→0.798，排序问题而非召回问题）。据此保留 `qr_on + rr_on`。

### Part B：面试检索升级
- 抽取 `RetrievalFacade`，问答与面试统一检索底座。
- `InterviewService` 迁移到 facade（不再走 raw FAISS 独木桥），评价查询用「问题 + 用户回答」，出题/评价带**来源溯源**。
- 落地「追问默认不检索」成本开关 `enable_interview_followup_retrieval`。

### 验证结果
- `pytest`：**143 passed**。
- 真实 RAG 问答验证通过（检索 558 向量 → 真实 LLM 生成，来源命中知识库多文档）。
- SSE 事件链验证通过：`session → retrieval → token(×N) → done`。
- 面试检索 **baseline vs upgraded**：MRR 0.559 → **0.588**（提升），recall 持平 0.588（不劣于升级前）。

---

## 快速开始

### 前置
- Python 3.10+（建议 Conda 隔离环境）
- Redis（本示例默认 `192.168.127.101:6379`，可在 `.env` 覆盖，含密码场景需配 `REDIS_PASSWORD`）
- 阿里云百炼 `BAILIAN_API_KEY`、硅基流动 `SILICONFLOW_API_KEY`

### 本地运行

```bash
# 1) 配置环境（复制模板并填写真实 Key）
cp .env.example .env
#    编辑 .env：BAILIAN_API_KEY / SILICONFLOW_API_KEY / JWT_SECRET 等

# 2) 安装依赖
pip install -r requirements.txt

# 3) 启动（依赖 Redis）
uvicorn app.main:app --reload

# 4) 构建知识库索引（首次或文档变更后）
curl -X POST http://localhost:8000/api/index/build -H "Content-Type: application/json" -d '{"rebuild": true}'

# 5) 浏览器访问 http://localhost:8000
```

> **注意**：`Settings` 在 `import` 时一次性读取，修改 `.env` 后需**重启进程**生效。

### Docker Compose 运行

```bash
docker compose up -d --build   # 启动 rag-app + 内置 redis（数据卷挂载 ./data）
docker compose ps              # 应为 Running / healthy
curl http://127.0.0.1:8000/api/health
```

> compose 内置 Redis 无密码，与应用在 Docker 内网通信；若改用外部带密码 Redis，请同步调整 `REDIS_PASSWORD`（见 [部署笔记](docs/docker-deploy-notes.md)）。

### 环境变量说明

| 变量 | 说明 | 默认 |
|------|------|------|
| `BAILIAN_API_KEY` / `BAILIAN_MODEL` | 阿里云百炼 LLM | `qwen-turbo` |
| `SILICONFLOW_API_KEY` / `SILICONFLOW_MODEL` | 硅基 Embedding | `Qwen/Qwen3-Embedding-4B` |
| `RERANK_MODEL` | 硅基 Rerank | `Qwen/Qwen3-Reranker-4B` |
| `REDIS_HOST/PORT/DB` / `REDIS_PASSWORD` | Redis 会话/缓存 | `192.168.127.101:6379` |
| `JWT_SECRET` | 认证签名密钥（**必填**） | — |
| `CORS_ORIGINS` | 前端来源白名单 | localhost:8000 |
| `ENABLE_HISTORY_PERSISTENCE` | Redis 过期后从 SQLite 恢复会话 | `true` |
| `ENABLE_INTERVIEW_FOLLOWUP_RETRIEVAL` | 面试追问是否触发检索 | `false` |

完整配置见 [app/config.py](app/config.py) 与 [.env.example](.env.example)。

---

## 评测与检索优化

```bash
# 检索评测基线 / 消融（Part A）
python scripts/eval_runner.py --limit 5        # 冒烟；去掉 --limit 跑全量 120 条

# 面试检索 baseline（旧 raw FAISS）与升级后（facade）对照（Part B）
python scripts/eval_interview_baseline.py
python scripts/eval_interview_upgraded.py

# 全量测试
python -m pytest tests/
```

评测报告与决策沉淀在 [docs/evaluation](docs/evaluation/)。

---

## 后续规划

- **知识树 query 检索优化（Part C）**：将面试出题 query 从填空式改为「知识点树定位考点 → 考点驱动检索」，针对性改善 Java 集合类主题召回。
- **检索质量进一步提升**：重排参数（RRF k / rerank top_k / query rewrite 规则）调优与再消融。
- **可观测性完善**：幻觉/成本指标接入 Grafana 看板。

---

## 文档导航

| 内容 | 位置 |
|------|------|
| 系统架构 / 技术栈 | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 长期技术决策（DR） | [DECISIONS.md](DECISIONS.md) |
| 开发 / 验收流程 | [PROCESS.md](PROCESS.md) |
| 已知问题 / 门禁 | [PROBLEM.md](PROBLEM.md) |
| Docker 部署 / 排障 | [docs/docker-deploy-notes.md](docs/docker-deploy-notes.md) |
| 面试表达材料 | [docs/interview-materials/](docs/interview-materials/) |

## License

[MIT](LICENSE)