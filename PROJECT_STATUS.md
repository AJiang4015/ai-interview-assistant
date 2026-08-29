# PROJECT_STATUS.md — 项目状态恢复快照

> 生成目的：作为项目负责人帮你恢复开发上下文（跨 AI IDE 迁移丢失上下文后）。
> 性质：**只读调研结论**，未改动任何业务代码、未重新设计架构、未引入新技术。
> 快照时间：2026-08-29。事实依据：`git log` / `git status` / `ARCHITECTURE.md` / `PROBLEM.md` / `DECISIONS.md` / `docs/superpowers/specs/*` / `docs/evaluation/*`。

---

# 项目目标

用「知识库检索增强 LLM 生成」构建一款 **Java / 后端程序员面试助手**（Interview RAG）：

1. 用户上传个人技术知识库（md / pdf / docx）→ 构建检索索引；
2. 系统走「查询改写 → 混合检索(RRF) → 重排 → LLM 生成 → 幻觉/成本评估」完整管线作答；
3. 扩展出 **AI 模拟面试、简历项目深挖、复习画像、会话/认证、离线评测调优、可观测性** 等产品能力线。

核心心智模型的一句话（来自 ARCHITECTURE §1，唯一事实来源）：**用「知识库检索增强 LLM 生成」，做一款程序员面试助手。**

---

# 当前架构

**技术栈（唯一事实来源 `ARCHITECTURE.md` §2）**

| 层 | 选型 |
|----|------|
| 后端 | FastAPI 0.115 + uvicorn + Pydantic v2 / pydantic-settings |
| LLM | 阿里云百炼 `qwen-turbo`（config 未提交改动默认值，⚠见风险） |
| Embedding / Rerank | 硅基流动 `Qwen/Qwen3-Embedding-4B` / `Qwen/Qwen3-Reranker-4B` |
| 向量库 | FAISS（faiss-cpu，Flat / HNSW）× 命中 top-20 |
| 稀疏检索 | rank_bm25 / Whoosh / SQLite FTS（`sparse_backend`，降级链 memory） |
| 会话/用户热数据 | Redis（固定 `192.168.127.101:6379`，TTL 3600s，单会话 20 轮） |
| 长期事实源 | SQLite `search_store`（跨会话全文搜索 + 用户历史持久化，DR-010） |
| 认证 | passlib[bcrypt] + PyJWT，`get_current_user` 依赖注入 |
| 流式 | SSE（事件 `session / retrieval / token / done / error`，DR-005） |
| 可观测性 | OpenTelemetry(可选) + Prometheus 风格 metrics + Grafana（`docs/observability/`） |
| 前端 | 原生 HTML/CSS/JS，CDN marked + highlight.js + DOMPurify（DR-009） |

**分层依赖方向（Law of Layers）**：API → Services → Storage / Utils；禁止反向/横向越界（各 `*_LAYER.md` 为契约）。

**关键约束**：单 worker 落盘模型（DR-002）；依赖失败优雅降级（DR-001）；缓存 key 仅原始问题（DR-004，⚠见未完成）。

---

# 已完成

**核心 RAG 问答（已打通生产链路，`main.py` lifespan 装配）**
- 非流式 + SSE 流式问答，`retrieval / token / done / error` 事件闭环。
- 查询改写 → HybridRetriever(RRF k=60 融合 FAISS+稀疏) → SiliconFlow Rerank(top5) → Parent 上下文扩展 → LLM 生成 → 幻觉评估 → 会话落 Redis。

**大规模 RAG 检索（2026-08-16 plan 已完成接入生产）**
- `Chunker`：递归重叠 + 段落感知 + parent-child（chunk 1000 / overlap 200）。
- 向量索引工厂化（Flat / HNSW）+ 线程池并发检索。
- 可插拔稀疏检索后端（内存 / whoosh / sqlite_fts）+ 显式降级链。
- `index_pipeline`：受控并发嵌入入库、断点续传、幂等、进度回传。
- 端到端护栏测试（召回一致性 / 降级 / 幂等）/ 基准脚本。

**产品能力线**
- AI 模拟面试：`InterviewAgent` + `InterviewPlanner`，面试会话/逐题/评分原因/参考答案/报告/历史/统计/复习画像，按用户隔离。
- 简历深挖：`DeepDiveService` + `ResumeParser`（简历/JD 解析与匹配）。
- 认证 + 全栈用户隔离 + 限流 + 会话历史持久化 + Redis 会话（`d2ace2f` / `dfd1a88` / `55483ae`）。
- 前端四视图（AI面试/复习/问答/设置）SPA + SSE 流式渲染（切换会话不中断，D1–D4/D11）。
- 离线评估：`evaluation_service` / `eval_testset` / `eval_metrics` / `/api/eval/*` + 异步后台任务进度。
- 可观测性：OTel Trace + Token 成本核算 + 会话成本预算告警 + 幻觉评估监控。

**离线评测闭环 Part A（实验数据已产出，但收尾未完成 → 见「未完成」）**
- 手写评测集已落盘 `data/eval_testset.json`（32 条核心集，四维度布局：跨文档 / 易混辨析 / 口语面试 / 边界反直觉）。
- `scripts/eval_runner.py` 已实现基线 + query-rewrite/rerank 4 组合消融矩阵。
- 产物已落盘 `docs/evaluation/`（基线与消融见「当前风险/下一步」详情）。

**工程 / 部署**
- Docker：`docker-compose.yml`（rag-app + redis）、`Dockerfile`（单 worker）、`.env.example`、`Makefile`（未提交）。
- 文档体系：`ARCHITECTURE.md` / `DECISIONS.md`(DR-001~DR-010) / `PROCESS.md` / `PROBLEM.md` / 各 `*_LAYER.md`；spec/plan 归档 `docs/superpowers/`。

---

# 未完成

**A. 离线评测闭环 Part A「收尾」未做（当前工作区正在进行的半成品）** — Spec `2026-08-28-retrieval-eval-closed-loop-partA.md` 验收清单中「建集 v0」已勾选，但「后续阶段（基线/门禁/消融）」多未勾选：
- 消融实验**数据已出**（4 组 qr×rr + 基线已跑），但**结论尚未写成决策文档**。
- **门禁阈值未按基线落定**到配置/文档（Spec 明确要求「不凭空拍，先有基线再落阈值」）。
- **管线 `enable_*` 开关未按消融结论调整**（当前仍全开）。
- `make eval` 可重复命令、`pytest tests/` 全量通过 未确认完成。
- 相关改动**大量尚未 git 提交**（见「当前风险」）。

**B. Spec Part B：面试检索升级 — 尚未启动**（`2026-08-28-interview-retrieval-upgrade-partB.md`）
- 前置条件是「Part A 消融结论达标」（基线明确 + qr/rr 明确决策 + 消融后整体不劣于基线，三条件同时满足）。
- 已规划未实现：统一 retrieval facade、默认「追问不检索」的触发策略、`enable_interview_followup_retrieval` 开关。

**C. 遗留 Active 问题（规则已定，代码未落地）**
- **P001（High）响应缓存 key 含 `session_id`/`msg_count`** → 命中率趋近 0；已确认正确方向是「key 仅用原始问题」（DR-004 / D5），但 `cache_service.make_key` 未改。Spec 也将其列为最高性价比门禁（P5 Door5 未落地）。
- **P006（High）单 worker 落盘 / 索引陈旧 state**：规则已固化（`a22cdf8`），但无多 worker 并发的进程级锁。
- **门禁自动化（PROBLEM.md Appendix P1–P14）**：多数 Door 是「建议 Pytest/Lint」，尚未机器可执行落地。

**D. 其它未收口**
- 评测集 LLM 扩展集（100~150 条）**生成代码就绪但未实跑**（Spec 明确本次不跑以控成本；基线阶段前需补齐，但基线当前已用完整集跑出）。
- 前端「复习」视图与设置视图的部分交互、以及前端对认证/评分原因的完整覆盖，按子代理核查存在「功能就绪但与后端契约细节待核对」的不确定性（如 `deep_dive` 服务的用户隔离校验较 `interview` 弱）。

---

# 当前风险

1. **⚠ 大量未提交改动（高优先级）**：当前分支 `feature/large-scale-rag`，`git status` 显示约 17 个文件、+1550/-197 行未提交，涵盖：Part A 核心实现（`eval_metrics.py`/`eval_testset.py`/`evaluation_service.py` + 对应测试）、新增 `data/eval_testset.json`、新增 `JUC.md`(1137 行)、`scripts/eval_runner.py`、`Makefile`、spec 文档、`.env.example`/`config.py`/`requirements.txt` 改动。**跨 IDE 迁移后这些是「未落盘的工作成果」，务必先提交入库，勿丢失。**

2. **⚠ 模型命名事实源不一致**：`config.py` 未提交 diff 将默认 `bailian_model` 从 `qwen3.7-max` 改为 `qwen-turbo`、`token_price` 同步更新；而 Memory 记录为 `qwen3.7-plus`、AGENTS 铁律写 `qwen-turbo`。**三方不一致**，需统一唯一事实源（按 `ARCHITECTURE.md` §2 规约，应落一处并在 `.env`/`config.py` 生效）。

3. **消融结论需要严谨化才能驱动配置**：4 组消融（40 条手写集）关键指标：
   | 组合 | recall@top-k | mrr | faithfulness |
   |------|------|------|------|
   | qr_off · rr_off | 0.850 | 0.808 | 0.948 |
   | qr_on · rr_off | 0.900 | 0.825 | 0.940 |
   | qr_off · rr_on | 0.913 | 0.829 | 0.950 |
   | qr_on · rr_on | 0.913 | 0.798 | 0.956 |
     基线（完整集，生产全开）0.904 / 0.819 / 0.961。观察：任一开关开启召回均提升；但 **rr 与 qr 同时开启时 mrr(0.798) 反而低于 rr 单独(0.829)** → 需判断是否要调 `rr top-k`/RRF 权重，或考虑单独保留 rr、qr 视场景。这是「给 Part B 放行的最后一步」。

4. **P001 缓存失效叠加成本**：响应缓存当前几乎不命中，高频重复问题会重复消耗 LLM/Embedding，放大 Session token 预算告警（P011 关联）。

5. **单 worker 约束**：`<--workers 1` 是硬约束（D9/DR-002），部署 / 未来扩容时不能直接多开。

6. **LLM 成本已投入**：基线完整集（120 条，一次）约 ~230 万 token / ~$3；消融 4 组已跑（受控 40 条）。继续跑实验前需确认百炼配额/预算（此前已遇 Dashscope 免费额度耗尽）。

---

# 下一步建议

按 Spec 自带的执行顺序（Part A ①→⑤ → Part B）推进，不要跳步，也不要在此刻重新设计架构。

1. **先入库（P0）**：把当前 `feature/large-scale-rag` 上未提交的 Part A 改动提交为独立 commit（按 `PROCESS.md` §6「一个行为一个问题一个 commit」，可拆为：评测核心实现 + 评测集 + 评测脚本/报告 + JUC 知识库 + config/依赖），把「完成一半的实验结果」固化，防止跨 IDE 迁移再丢上下文。
2. **Part A 收尾（P0）**：依据已产出的基线+消融数据写「消融结论」文档（落到 `docs/evaluation/`），给出 qr / rr 的**明确保留/关闭决策**；据结论更新 `.env`/`config.py` 中对应 `enable_*` 开关与 RRF top-k；按基线落定门禁阈值到配置/文档；补 `make eval`/验收项；验证 `pytest tests/` 全量通过（`requirements.txt` 已加 pytest，需在 Conda 环境跑）。
3. **修复 P001（P0）**：改 `cache_service.make_key` 为仅基于原始问题哈希，并补 `test_make_key_no_session_dimension` 回归（PROBLEM.md Door5 / DR-004）。收益最大、改动小。
4. **达到 Part A 门槛后启动 Part B（P1）**：`interview-retrieval-upgrade-partB`——统一 retrieval facade、默认追问不检索、`enable_interview_followup_retrieval` 开关。
5. **统一模型名事实源（P1）**：消除 qwen-turbo / qwen3.7-max / qwen3.7-plus 三处不一致，以 `ARCHITECTURE.md` §2 + `.env` 为唯一事实来源并同步 `config.py` 默认值。
6. **门禁自动化（P2）**：按 `PROBLEM.md` Appendix P1–P14 将 D1–D14 映射为可执行 Pytest/Lint，优先 Door5（P001）、Door10/2/3（前端安全/流式）。
7. **可交付版本验证（P1，里程碑）**：跑一次完整冒烟——`pytest` 全绿 + Docker 部署（`docker-compose up`）+ 前端四视图端到端（含 SSE 切换会话、认证隔离、设置/评测），作为「第一个可交付版本」的验收。

---

# 优先级排序

| 优先级 | 事项 | 说明 |
|--------|------|------|
| **P0-1** | **提交当前未提交改动** | 防止已完成的 Part A 实验/代码因 IDE 迁移丢失；最高优先 |
| **P0-2** | **Part A 收尾**：消融结论沉淀 + 门禁落定 + 按结论调整 `enable_*`/RRF + `make eval` + pytest 全过 | 这是卡住 Spec B 的唯一前置，也是「第一个可交付」门禁质量的依据 |
| **P0-3** | **修复 P001 缓存 key**（仅原始问题）+ Door5 回归测试 | 改动小、收益大、为成本兜底，PROBLEM.md 自评最高性价比 |
| P1 | 关键路径模型命名事实源统一（qwen 系列三处不一致） | 防线上用错模型/计价 |
| P1 | 依据 Part A 达标结果启动 **Spec B 面试检索升级** | 前置 = Part A 达标，勿提前 |
| P1 | 可交付版本端到端验收（pytest + Docker + 前端四视图） | 里程碑验收 |
| P2 | 门禁自动化（PROBLEM.md Appendix P1–P14 落地） | 把「请遵守」变成「会被 CI 拦」 |
| P2 | 评测集 LLM 扩展集实跑 + 前端 deep_dive 用户隔离校验补齐 | 增强评估覆盖与一致性 |

---

## 附：给下一会话的交接要点
- 权威文档链：`AGENTS.md`(宪法) → `ARCHITECTURE.md`(技术栈/模块) → `PROCESS.md`(流程/命令) → `DECISIONS.md`(DR) → `PROBLEM.md`(已知问题/门禁)。
- **当前正卡在 Part A 的「第⑤步：结论沉淀并驱动配置」**：实验数据已产出，缺决策与落地。
- 继续开发前先 `git status` 确认工作区，再决定是否先提交 Part A 改动。
- 铁律三连：缓存 key 仅原始问题（DR-004）；流式不改 `state.sessionId`/不 `abort()`（DR-005/D1–D4）；重排走 SiliconFlow API 禁本地 bge（DR-003）。