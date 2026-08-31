# RAG Knowledge Assistant — 可评测、可降级、可观测、可持久化的工程化 RAG 系统

**面向 Java / 后端程序员面试场景**：从 RAG Demo 演进而来的工程化 RAG 系统——用户上传个人技术知识库（Markdown / PDF / Word），系统通过 `查询改写 → 混合检索(RRF) → 重排 → LLM 生成` 流水线作答，并扩展出 AI 模拟面试、简历深挖、复习画像、离线评测；当前主线正在其上构建**确定性编排 Agent 面试系统**。

> 项目的工程重点不是"接一个 LLM"，而是把**检索质量工程化**：用评测闭环量化、用统一检索门面复用、用消融实验驱动配置决策，并让核心链路在外部依赖故障时优雅降级。

---

## 一、四条技术主线

### 1. Retrieval Quality Loop — 检索质量可评测、可优化

```text
Testset → Baseline → Ablation → Metrics(recall@k / mrr / faithfulness) → Decision → Gate
```

- 手写核心评测集（四类难题：跨文档推理 / 易混辨析 / 口语面试 / 边界反直觉）+ LLM 扩展集（120 条）。
- 对 `query rewrite × rerank` 做 4 组开关消融，用数据决定去留，而非"组件越多越好"。
- **关键发现**：单模块开启均改善召回；**qr + rr 联合开启无叠加收益、MRR 反而回落（0.829→0.798）**——识别出这是**排序问题而非召回问题**，据此保留生产默认 `qr_on + rr_on`，把回落列为参数优化项而非开关项。
- 权威数据与结论：[`docs/evaluation/retrieval_ablation_decision.md`](docs/evaluation/retrieval_ablation_decision.md)（唯一事实源，其余文档只引用）。

### 2. Reliability / Graceful Degradation — 外部依赖不可靠，核心链路不依赖任何单一可选组件

外部依赖（Redis / BM25 / Rerank API / OTel / LLM 输出格式）故障时各自降级，不阻塞主链路：

| 依赖失败 | fallback |
|---|---|
| Redis 不可用 | 会话 / 缓存禁用（无状态问答仍可用） |
| BM25 缺失 | 回退 FAISS-only |
| Rerank 失败 | 跳过重排用 RRF 结果 |
| OTel 不可用 | 可观测性禁用（静默） |
| LLM 结构化输出 malformed | parser 兜底默认值，不阻塞 |

完整降级矩阵见 [ARCHITECTURE.md §4](ARCHITECTURE.md)。统一思想：**核心主链路 = FAISS 检索 + LLM 生成**，其余皆为可选增强。

### 3. Engineering Incident → Root Cause → Decision — 关键工程问题有完整证据链

每个重大问题都有独立的 `Problem → Evidence → Root Cause → Decision → Regression` 档案，并沉淀为长期工程约束（DR）：

| 问题 | 教训 | 约束 |
|---|---|---|
| **缓存 key 混入会话维度 → 命中率≈0**（P001） | key 必须基于不变语义 | DR-004：只用原始问题 |
| **SSE 流式跨会话中断**（P002） | 请求归属 ≠ UI 当前焦点 | DR-005：流绑定发起会话 |
| **本地 reranker OMP 崩溃 / 下载失败**（P003/P004） | 禁止"地雷型"本地重型资源 | DR-003：重排走 API |
| **单 worker 落盘约束**（P006） | 状态必须原子可重入 | DR-002：`--workers 1` |

注册表：[PROBLEM.md](PROBLEM.md) · 完整档案：[docs/problems/](docs/problems/)

### 4. Demo → Engineering System — 不止"堆功能"

- **Core RAG**：ingestion · retrieval · rerank · generation · evaluation
- **Engineering**：cache · session · persistence · auth/isolation · SSE · graceful degradation · observability · cost control
- **Product**：AI 面试（legacy + 进行中的确定性编排 Agent）· 简历深挖 · 复习画像

---

## 二、核心指标速览

| 实验 | 结果 |
|------|------|
| 检索消融（40 条手写集） | 全开 recall 0.913 / mrr 0.798 / faithfulness 0.956；单开 rerank mrr 最高 0.829 |
| 生产基线（120 条完整集） | recall 0.904 / mrr 0.819 / faithfulness 0.961 |
| 面试检索升级（Part B，17 条） | MRR **0.559 → 0.588**，recall 持平 0.588（不劣于升级前） |
| 回归 | `pytest` 全量通过（Part B 验收时 143 passed；agent W1 单测通过） |

> 数字口径与完整分析以 [`docs/evaluation/`](docs/evaluation/) 为准。

---

## 三、快速开始

### 前置

- Python 3.10+（建议 Conda 隔离环境）
- Redis（默认 `192.168.127.101:6379`，可在 `.env` 覆盖，含密码场景需配 `REDIS_PASSWORD`）
- 阿里云百炼 `BAILIAN_API_KEY`、硅基流动 `SILICONFLOW_API_KEY`

### 本地运行

```bash
# 1) 配置环境（复制模板并填写真实 Key；改 .env 后需重启进程生效）
cp .env.example .env

# 2) 安装依赖
pip install -r requirements.txt

# 3) 启动（依赖 Redis）
uvicorn app.main:app --reload

# 4) 构建知识库索引（首次或文档变更后）
curl -X POST http://localhost:8000/api/index/build -H "Content-Type: application/json" -d '{"rebuild": true}'

# 5) 浏览器访问 http://localhost:8000
```

### Docker Compose 运行

```bash
docker compose up -d --build   # rag-app + 内置 redis（数据卷挂载 ./data）
curl http://127.0.0.1:8000/api/health
```

> compose 内置 Redis 无密码与应用内网通信；改用外部带密码 Redis 时同步调整 `REDIS_PASSWORD`（见 [部署笔记](docs/docker-deploy-notes.md)）。**注意单 worker 硬约束**（DR-002/P006）：Docker 以 `--workers 1` 启动。

### 关键环境变量

| 变量 | 说明 | 默认 |
|------|------|------|
| `BAILIAN_API_KEY` / `BAILIAN_MODEL` | 阿里云百炼 LLM | `qwen-turbo` |
| `SILICONFLOW_API_KEY` / `SILICONFLOW_MODEL` | 硅基 Embedding | `Qwen/Qwen3-Embedding-4B` |
| `RERANK_MODEL` | 硅基 Rerank | `Qwen/Qwen3-Reranker-4B` |
| `JWT_SECRET` | 认证签名密钥（**必填**） | — |
| `INTERVIEW_MODE` | `legacy`（默认）/ `agent`（确定性编排，进行中） | `legacy` |

完整配置见 [app/config.py](app/config.py) 与 [.env.example](.env.example)。

---

## 四、评测与实验

```bash
# 检索评测基线 / 消融（Part A）
python scripts/eval_runner.py --limit 5        # 冒烟；去掉 --limit 跑全量 120 条

# 面试检索 baseline（旧 raw FAISS）与升级后（facade）对照（Part B）
python scripts/eval_interview_baseline.py
python scripts/eval_interview_upgraded.py

# 全量测试
python -m pytest tests/
```

评测报告与决策沉淀在 [docs/evaluation](docs/evaluation/)。实验纪律（唯一变量 / fresh 测试集 / 先结果后结论）见 [PROCESS.md §3](PROCESS.md)。

---

## 五、当前状态

分支 `agent-dev`（main 冻结）：Agent 编排化改造 W1 进行中（状态机 / 门禁 / 逃生舱 / trace 已落地），RAG 侧 Part A/B 已闭环。当前阶段、Blockers、风险与下一步见 [PROJECT_STATUS.md](PROJECT_STATUS.md)。

---

## 文档导航

| 内容 | 位置 |
|------|------|
| 系统架构 / 技术栈（唯一事实源） | [ARCHITECTURE.md](ARCHITECTURE.md) |
| 长期技术决策（DR） | [DECISIONS.md](DECISIONS.md) |
| 开发 / 验收流程 | [PROCESS.md](PROCESS.md) |
| 问题注册表 / 门禁 | [PROBLEM.md](PROBLEM.md) · [docs/problems/](docs/problems/) |
| 当前状态 / 下一步 | [PROJECT_STATUS.md](PROJECT_STATUS.md) |
| 实验数据 / 评测结论 | [docs/evaluation/](docs/evaluation/) |
| Docker 部署 / 排障 | [docs/docker-deploy-notes.md](docs/docker-deploy-notes.md) |
| 面试表达材料 | [docs/interview-materials/](docs/interview-materials/) |

## License

[MIT](LICENSE)
