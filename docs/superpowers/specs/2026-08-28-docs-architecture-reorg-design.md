# 文档架构整理方案（第一阶段：设计与迁移清单）

> 日期：2026-08-28
> 状态：**待评审**（本阶段只做设计，不执行任何文档迁移或代码修改）
> 范围：`AGENTS.md` / `PROBLEM.md` / `docs/` / 各代码层目录的文档职责边界设计与迁移清单

---

## 0. 问题描述

`AGENTS.md` 当前同时承载：Agent 硬规则、开发流程、架构说明、历史问题经验、技术决策、测试/命令等多类异质信息，且与 `PROBLEM.md`、`docs/PROJECT_OVERVIEW.md` 存在多处重复。随着项目迭代（面试、评估、可观测性、大规模 RAG），若继续向 `AGENTS.md` 追加内容，它将从"Agent 工作指南"退化为"项目百科"，规则、历史与流程混杂，无法长期维护。

本方案目标：建立 **规则 / 流程 / 决策 / 架构 / 分层契约 / 问题 / Spec / Evaluation** 八类文档的职责边界，并给出 `AGENTS.md` 现有内容的逐节分类与迁移清单。**评审通过后再执行实际迁移（第二阶段）。**

### 0.1 与任务描述的偏差声明（重要）

任务描述中提到的以下内容**在本仓库不存在**，本方案不为其编造迁移项，一律按本仓库实际现状适配：

| 任务描述中的概念 | 本仓库实际情况 |
|---|---|
| EPUB 输入格式、novel_id、canonical identity | 不存在；输入为 Markdown / PDF / Word（docx） |
| Person / RELATES_TO 数据模型、Neo4j | 不存在；存储为 FAISS + BM25 + Redis + SQLite |
| Extractor / Hygiene / Resolver / Merger / Lineage 管线 | 不存在；管线为 chunker → embedding → index → retrieval(RRF) → rerank → RAGService 编排 → LLM 生成 |
| P016 / P017 / P018、P16-b role admission gate | 不存在；问题编号至 P013（见 `PROBLEM.md` §1） |
| Task A 先于 Task B、fresh novel / fresh job、lineage observer | 无对应物；通用原则已映射到本仓库流程（见 §4） |
| `api/db/models/pipeline/schemas` 五个 Layer 目录 | 实际分层为 `app/api`、`app/services`、`app/storage`、`app/utils`（+ `app/config.py` / `exceptions.py` / `main.py` / `observability.py`） |
| AGENTS.md 约 400 行 | 实际 **185 行**（`PROBLEM.md` 约 426 行，才是最大的单文件） |

> 若任务描述实际针对另一个仓库（EPUB/知识图谱抽取项目），本方案不适用，请告知后终止。

### 0.2 现状文档盘点

| 文件 | 行数（约） | 性质 | 问题 |
|---|---|---|---|
| `AGENTS.md` | 185 | 混合：规则+架构+流程+命令+文件表 | 异质信息堆积，与 PROBLEM.md / PROJECT_OVERVIEW.md 重复 |
| `PROBLEM.md` | 426 | 问题知识库（P001–P013 + §0 规则 D1–D14 + §0a 哲学 + Appendix 门禁 Door1–14） | §0a 设计哲学实为 Decision 性质；其余职责清晰，**本轮不动** |
| `docs/PROJECT_OVERVIEW.md` | 130+ | 项目概览 | 与 `AGENTS.md` §1/§2/§3/§6 高度重复；**已定性为重定向指针页（Deprecation Pointer），第二阶段改写为轻量引导页**（见 §3.4/§5） |
| `docs/superpowers/specs/`（18 个）、`plans/`（10 个） | — | 设计 spec / 实现计划 | 职责清晰，保持 |
| `docs/docker-deploy-notes.md`、`docs/observability/` | — | 部署/可观测性知识 | 保持 |
| `docs/problems/`、`docs/evaluation/` | 不存在 | — | 目标体系中定义职责，`docs/evaluation/` 随 retrieval-eval-loop 工作自然建立，**不预建空目录** |

---

## 1. 目标文档体系与职责边界

```text
AGENTS.md      = Agent 必须遵守什么（宪法：硬规则 + 铁律摘要 + 文档地图）
PROCESS.md     = 应该怎么工作（开发/修复/实验/验收标准流程）
DECISIONS.md   = 已经决定了什么、为什么（Decision Record）
ARCHITECTURE.md = 系统怎么组织（结构、数据流、依赖方向、边界）
*_LAYER.md     = 每层负责什么、不能负责什么（Layer Contract）
PROBLEM.md     = 哪里有问题（问题知识库，保持现状）
docs/superpowers/specs/ = 准备怎么改（保持现状）
docs/evaluation/        = 改完实际怎么样（新建职责，随评估工作落盘）
```

**长期稳定规则**：后续任何新增文档/内容，必须先判断属于上述哪一类再落位置；禁止继续把所有内容追加到 `AGENTS.md`。此条本身将写入新 `AGENTS.md`。

**分层契约维护规则（Layer DoD）**：任何涉及**跨层接口变更、新增模块依赖或异常抛出**的 PR，必须同步更新受影响层级的 `*_LAYER.md`（特别是 Input/Output contract 与 Allowed dependencies），否则视为该 PR **不满足 DoD**。此条将写入新 `AGENTS.md` 硬规则，并在 §8 验收。

---

## 2. `AGENTS.md` 现有内容逐节分类（迁移表）

分类代号：A=硬规则(Rule)、B=流程(Process)、C=架构(Architecture)、D=长期决策(Decision)、E=问题历史(Problem history)、F=测试/验收(Testing)、G=过时/临时(Obsolete)。

| 当前 AGENTS.md 内容 | 行号 | 分类 | 目标文档 | 保留原位置 | 备注 |
|---|---|---|---|---|---|
| 头部：文件定位说明 | 1–8 | Meta | `AGENTS.md`（重写为"Agent 宪法"定位声明+文档地图） | ✅改写 | 新头部指向其余 7 类文档 |
| §1 项目概述（一句话目标） | 10–18 | C | `ARCHITECTURE.md` §1 | ❌ | AGENTS 仅留一句项目定位 |
| §2 技术栈表 | 22–40 | C | `ARCHITECTURE.md` §2 | ❌ | 与 PROJECT_OVERVIEW 去重后单处维护 |
| §3 架构图 + 模块对应表 | 44–71 | C | `ARCHITECTURE.md` §3（数据流+模块地图） | ❌ | 迁移 |
| §3 设计约定：可配置开关 | 74 | D | `DECISIONS.md`（DR：RAG 模块全部可开关） | ❌ | 对应 PROBLEM D7 |
| §3 设计约定：优雅降级链 | 75 | D | `DECISIONS.md`（DR：依赖失败静默降级） | ❌ | 对应 D7/Door 7 |
| §3 设计约定：单 worker 约束 | 76 | D | `DECISIONS.md`（DR：单进程落盘模型） | ❌ | 与 D9/Door 9/Dockerfile 收敛为单一记录 |
| §4.1 Python 3.10+ / Conda | 82–84 | A(弱)+C | 版本要求留 `AGENTS.md` 一行；环境细节入 `PROCESS.md` §环境准备 | ✅压缩 | — |
| §4.2 代码风格（PEP8/行宽/settings） | 86–89 | A | `AGENTS.md`（压缩为 3 条） | ✅压缩 | — |
| §4.3 命名规范 | 91–96 | A | `AGENTS.md`（压缩；schema 位置细节移 `API_LAYER.md`） | ✅压缩 | — |
| §4.4 注释与文档（中文注释/日志） | 98–101 | A | `AGENTS.md`（保留压缩版） | ✅压缩 | — |
| §4.4 Spec 落盘要求 | 102 | B | `PROCESS.md` §Spec 流程（展开为完整流程） | ✅留一句+指针 | 落盘路径/命名规则在 PROCESS 维护 |
| §4.5 架构分层（新增代码位置） | 104–110 | A | `AGENTS.md` 留"分层边界见各 *_LAYER.md，禁止越界"一条 | ✅压缩 | 分层明细下放 4 个 Layer 文档 |
| §4.6 错误与安全（统一异常/XSS/白名单） | 112–115 | A | `AGENTS.md` 保留压缩版；转义/白名单细节入 `API_LAYER.md` / `STORAGE_LAYER.md` | ✅压缩 | 对应 D10/D13 |
| §5 常用命令 + 外部服务依赖 | 119–136 | B | `PROCESS.md` §环境准备与验收命令 | ❌ | 迁移 |
| §6 关键文件说明表 | 140–164 | C | `ARCHITECTURE.md` §模块地图（与 PROJECT_OVERVIEW 合并去重） | ❌ | 迁移 |
| §7 调试流程 1–6（PROBLEM.md 使用要求） | 168–177 | B | `PROCESS.md` §问题修复流程（展开固化） | ❌ | 其中"开发/Debug 前必读 PROBLEM.md"上升为 AGENTS 硬规则保留 |
| §7.1 三大铁律（P001/P002/P003 高压线） | 179–185 | A(摘要)+E(引用) | `AGENTS.md` 保留铁律**浓缩版+指针**；事实来源始终是 `PROBLEM.md` | ✅保留 | 禁止在 AGENTS 展开细节，防两处漂移 |

分类统计：A 类保留约 60–70 行（压缩后），B 类约 30 行迁出，C 类约 90 行迁出，D 类约 3 条决策迁出，E/F 类以指针形式保留。

---

## 3. 各目标文档内容设计

### 3.1 `AGENTS.md`（重写后骨架，目标 ≤120 行）

```text
0. 文档地图（8 类文档职责一览 + 何时读哪个）
1. 硬规则
   - 开发/Debug 前必读 PROBLEM.md（§0/§1）
   - 新增内容必须先归类再落盘，禁止默认追加 AGENTS.md
   - 分层边界：新增代码必须落在 *_LAYER.md 声明的层内，禁止越界
   - Layer 契约 DoD：跨层接口变更 / 新增模块依赖 / 异常抛出的 PR 必须同步更新受影响 *_LAYER.md，否则不满足 DoD
   - 代码风格/命名（压缩版）
   - 错误与安全（统一异常、转义、白名单，压缩版）
   - Git：一问题一 commit（详见 PROCESS）
   - LLM 调用约束：qwen3.7-max / SiliconFlow，禁止本地重型模型（铁律3）
2. 三大铁律 ⛔（浓缩版 + 指向 PROBLEM.md 单一事实来源）
3. 环境最低要求（Python 3.10+，一行）
```

### 3.2 `PROCESS.md`

定位："任务应该怎么做"。固化已有工程流程，吸收 AGENTS §5/§7/§4.4：

- **开发/修复主流程**：`Problem → Evidence → 分层归因 → Spec（落盘 docs/superpowers/specs/）→ Review → Implementation → Unit → Integration → 真实 LLM evaluation → Evaluation report → Decision(如需) → Commit`
- **问题修复流程**：吸收 AGENTS §7 全部 6 条（先读 Problem Index → 按 Trigger 定位 → 解决后追加记录 → 不覆盖历史 → resolved 复现先验证不照搬旧修复 → 禁止编造）
- **验收顺序**：unit（pytest services/storage）→ integration → 真实 ingest/LLM 评估；禁止跳过前者直接改 prompt/配置"看效果"
- **实验纪律**（对应任务描述的"变量固定/fresh/唯变量"，按本仓库映射）：
  - A/B 对比必须唯一变量（只改一个开关/prompt 版本/参数，其余冻结）
  - 评估测试集必须 fresh（`eval_testset` 重新生成，不得复用调参期间已看过的集合）
  - 真实 LLM 评估结果落盘 `docs/evaluation/`，先报告后结论
- **归因与止损**：失败先归因到拥有该决策的层（见 SERVICES_LAYER 决策所有权）；同一问题连续 2 次修复失败 → 停止修改，回 PROBLEM.md 立项重查证据
- **环境准备与常用命令**：吸收 AGENTS §5

### 3.3 `DECISIONS.md`

每条格式：`Decision ID / Title / Status / Date / Context / Decision / Reason / Consequence`。首批从现有文档沉淀的长期决策（**不新造决策，只收录已事实上生效的**）：

| DR | 决策 | 现有出处 |
|---|---|---|
| DR-001 | RAG 管线各模块（改写/混合检索/重排/缓存）必须可配置开关 + 依赖失败优雅降级 | AGENTS §3、PROBLEM D7 |
| DR-002 | 运行态全局与落盘采用单 worker 模型（Dockerfile `--workers 1`） | AGENTS §3、D9、Door 9 |
| DR-003 | 重排走 SiliconFlow API（Qwen3-Reranker-4B），禁止本地 bge-reranker | 铁律3、D6、P003/P004 |
| DR-004 | 缓存/去重 key 基于不变语义（原始问题原文） | 铁律1、D5、P001 |
| DR-005 | 流式协议选型 SSE（单向），事件类型 session/retrieval/token/done/error | AGENTS §2 |
| DR-006 | 混合检索采用 RRF（k=60）融合 FAISS 稠密 + BM25 稀疏 | AGENTS §3 |
| DR-007 | 会话/缓存存储 Redis 固定实例，TTL 3600s / 20 轮；Redis 不可用即禁用相应功能 | AGENTS §2/§3 |
| DR-008 | LLM 输出健壮解析（JSON 围栏剥离、兜底），失败不阻塞主流程 | D14、P008 |
| DR-009 | 前端安全渲染链：escapeHtml + DOMPurify，CDN 失败回退纯文本 | D10、P005 |
| DR-010 | 请求上下文透传与多租户/用户数据隔离契约：API 层统一解析 Auth Token 提取 `user_id`，底层存储按用户隔离作用域，禁止跨用户访问 | `docs/superpowers/specs/2026-08-27-user-history-isolation-persistence-design.md`、`2026-08-27-user-isolation-review-profile-design.md`（PR #1 已合并主线） |

> DR-010 为占位收录：契约已在代码中生效（PR #1 squash merge，SHA `51dc39ae`），第二阶段建 DECISIONS.md 时从上述 spec 提炼正式 DR 条目；DR 表只陈述已生效事实，不新造决策。

> `PROBLEM.md` §0a 三条"核心设计哲学"具有 Decision 性质。**建议**（非本轮动作）：第二阶段在 DECISIONS.md 建立对应 DR 并在 PROBLEM.md §0a 加反向指针，原文不删。是否执行由评审决定。

### 3.4 `ARCHITECTURE.md`

全局架构地图，吸收 AGENTS §1/§2/§3/§6 并与 `docs/PROJECT_OVERVIEW.md` 合并去重：

```text
§1 项目定位（一段）
§2 技术栈（唯一事实来源表）
§3 端到端数据流：
   文档上传(md/pdf/docx) → 解析分块(chunker,1000/200)
   → 向量化(embedding) → 索引入库(FAISS + BM25, ingest_state 断点续传)
   → [查询侧] 查询改写 → 混合检索(RRF) → 重排 → Parent扩展/去重
   → Prompt构建(+会话历史) → LLM生成 → SSE/JSON
   旁路：响应缓存 · 幻觉评估 · Token成本 · OTel
§4 分层结构与依赖方向（见 §3.5）
§5 模块地图（合并 AGENTS §6 + PROJECT_OVERVIEW §3，含 api/services/storage/utils/frontend/tests 逐文件一句话）
§6 部署形态（Docker 单 worker + Redis，指向 docker-deploy-notes）
```

**`docs/PROJECT_OVERVIEW.md` 收尾方案（已定）**：改写为**重定向指针页（Deprecation Pointer）**，落盘内容示例：

```markdown
# 项目概览（已归档）

> 本文档已由 ARCHITECTURE.md 取代（2026-08-28 文档架构整理）。
> 项目一句话：用"知识库检索增强 LLM 生成"，做一款程序员面试助手。

- 架构 / 数据流 / 依赖方向 → [ARCHITECTURE.md](../ARCHITECTURE.md)
- 技术栈（唯一事实来源）   → [ARCHITECTURE.md](../ARCHITECTURE.md) §2
- 模块 / 目录索引           → [ARCHITECTURE.md](../ARCHITECTURE.md) §5
- 开发 / 修复流程           → [PROCESS.md](../PROCESS.md)
- 技术决策                 → [DECISIONS.md](../DECISIONS.md)
- 已知问题                 → [PROBLEM.md](../PROBLEM.md)
- 历史设计 spec            → [docs/superpowers/specs/](superpowers/specs/)
```

仅保留一句话介绍 + 导航链接，不含任何正文内容，从机制上杜绝双头维护导致的文档漂移。

### 3.5 Layer 文档（4 个，本仓库实际分层）

> 不机械生成 README；统一命名 `*_LAYER.md`，定位 **Layer Contract / Layer Boundary**。每个文档固定回答 11 问：Responsibility / Input contract / Output contract / Decision ownership / Allowed dependencies / Forbidden dependencies / Invariants / Failure ownership / Testing expectations / Typical changes allowed / Changes that must be implemented elsewhere。

- `app/api/API_LAYER.md`：路由、请求/响应模型（schemas.py 归属）、统一异常→HTTP 映射、SSE 事件契约、鉴权边界（JWT）、输入校验（扩展名白名单/路径穿越）；禁止包含业务逻辑与持久化。
- `app/services/SERVICES_LAYER.md`：**本项目最重要的一层**，含 RAG 管线决策所有权表（见 §3.6）。
- `app/storage/STORAGE_LAYER.md`：FAISS/BM25/Redis/SQLite 各 store 的持久化契约、原子落盘与可重入要求（D8/D9）、TTL/轮数上限属配置不属存储、禁止跨 store 直接互调。
- `app/utils/UTILS_LAYER.md`：纯函数工具（logger、text_splitter），禁止依赖 services/storage/api，禁止持有全局可变状态。

> `app/config.py` / `main.py` / `exceptions.py` / `observability.py` 不单独立 Layer 文档，在 `ARCHITECTURE.md` §5 模块地图中说明。

### 3.6 `SERVICES_LAYER.md` 决策所有权表（对齐"pipeline 决策所有权"要求）

| 服务 | Owns（拥有） | Does NOT own（明确不拥有） |
|---|---|---|
| chunker / text_splitter | 分块边界、overlap、临时文件过滤 | 检索相关性、索引状态 |
| embedding | 向量化 API 调用与降级 | 召回策略 |
| index_service / index_pipeline | 索引构建/增量/断点续传、state 落盘原子性 | 查询时行为 |
| sparse_retriever | 稀疏后端选择与降级链 | 融合排序 |
| retrieval_service（HybridRetriever） | 混合检索、RRF 融合、召回 | 精排顺序、生成质量 |
| query_rewrite | 查询背景改写（旁路，可关） | 检索结果正确性 |
| rerank_service | 精排顺序 | 召回不足（召回问题不归 rerank） |
| rag_service | 编排顺序、Prompt 构建、SSE 流式协议 | 各子模块内部决策 |
| cache_service | 缓存 key 语义（铁律1：仅原始问题） | 缓存失效策略以外的会话逻辑 |
| interview/deep_dive/evaluation 等业务服务 | 各自业务流程编排 | RAG 管线内部行为 |

**失败归因分类（必须先归到拥有该决策的层，禁止"哪里方便改哪里"）**：

```text
解析/分块失败 ≠ 索引构建失败 ≠ 召回失败 ≠ 重排失败
≠ 生成失败 ≠ 缓存失败 ≠ 会话/流式失败 ≠ 前端渲染失败
```

---

## 4. 重复 / 冲突 / 过时规则识别

| # | 问题 | 涉及位置 | 处理建议 |
|---|---|---|---|
| R1 | 项目概述/技术栈/目录结构三处重复 | `AGENTS.md` §1/§2/§6 ↔ `docs/PROJECT_OVERVIEW.md` §1/§2/§3 | 迁移后 `ARCHITECTURE.md` 为唯一事实来源；`PROJECT_OVERVIEW.md` 改为指针页或标记 deprecated（第二阶段决定，本轮不动） |
| R2 | 同一规则四处出现（铁律 ↔ D 规则 ↔ 门禁 Door） | `AGENTS.md` §7.1 ↔ `PROBLEM.md` §0a/§0/Appendix | **不是冲突，是分层引用链**：AGENTS 只留浓缩铁律+指针；PROBLEM.md 保持事实来源；门禁保持测试映射。禁止任何一处展开复述全部细节 |
| R3 | 单 worker 约束三处陈述 | AGENTS §3、PROBLEM D9、Dockerfile | 收敛为 DR-002，他处引用 |
| R4 | P013（koa-connect）已标注 Historical 不适用当前栈 | PROBLEM.md §1/§3 | 已正确处理（保留历史+标注），符合"不覆盖历史"原则，不删 |
| R5 | 潜在漂移点：AGENTS §2 称 Redis 为"会话/用户存储"，但用户体系另有 `user_store`（SQLite/文件） | AGENTS §2 ↔ app/storage/user_store.py | 非冲突，迁移时按代码事实修正描述 |
| R6 | 用户隔离/认证为 2026-08-27/28 新增（PR #1 合并），AGENTS/PROBLEM 均未覆盖其约束 | `docs/superpowers/specs/2026-08-27-*` | **已解决**：以 DR-010 占位收录（见 §3.3），第二阶段从 spec 提炼正式 DR；不新造 Decision |

---

## 5. 推荐最终文档树

```text
AGENTS.md                      # 宪法：硬规则+铁律摘要+文档地图（≤120 行）
PROCESS.md                     # 开发/修复/实验/验收标准流程
DECISIONS.md                   # Decision Record（DR-001…）
ARCHITECTURE.md                # 架构地图：结构/数据流/依赖方向/模块地图
PROBLEM.md                     # 问题知识库（保持现状，本轮零修改）

app/
  api/API_LAYER.md             # Layer Contract
  services/SERVICES_LAYER.md   # Layer Contract + 管线决策所有权表
  storage/STORAGE_LAYER.md
  utils/UTILS_LAYER.md

docs/
  superpowers/plans/           # 保持
  superpowers/specs/           # 保持
  evaluation/                  # 评估报告（随 retrieval-eval-loop 建立，不预建）
  observability/               # 保持
  docker-deploy-notes.md       # 保持
  PROJECT_OVERVIEW.md          # 改写为重定向指针页（Deprecation Pointer，见 §3.4，已定）
```

> 不拆分 `PROBLEM.md` 到 `docs/problems/`：当前 13 个问题+索引体系单文件运行良好，拆分收益低于成本，且本轮禁止重写问题体系。若未来问题数显著增长再评估。

---

## 6. 迁移顺序（第二阶段，评审后执行）

1. `git tag docs-reorg-before`（快照，保证可回滚）；冻结分支，仅文档改动。
2. 建 `DECISIONS.md`（信息最稳定，先沉淀 DR-001~009）。
3. 建 `ARCHITECTURE.md`（吸收 AGENTS §1/§2/§3/§6，与 PROJECT_OVERVIEW 去重）。
4. 建 `PROCESS.md`（吸收 AGENTS §5/§7/§4.4，固化流程与实验纪律）。
5. 建 4 个 `*_LAYER.md`（先写 SERVICES_LAYER，最重要）。
6. **最后**瘦身 `AGENTS.md`：先保留全部旧内容+新增"已迁移至 X"指针 → 评审确认无丢失 → 再删除已迁移正文。
7. 每步独立 commit（`docs: ...`），一问题一 commit 原则同样适用于文档迁移。

## 7. 防丢失机制（旧规则不丢失的保证）

1. **迁移映射表即验收清单**：本文件 §2 的表逐项勾选（行号区间 → 新位置），第二阶段执行时作为 checklist 使用。
2. **关键 token grep 校验**：每步迁移后检索 `192.168.127.101`、`RRF`、`make_key`、`DOMPurify`、`ingest_state`、`单 worker`、`DOMPurify`、`escapeHtml`、`铁律` 等 token，确认在新文档树中可检索且旧位置删除后不出现"孤儿引用"（如 AGENTS 指向已删内容）。
3. **相对路径死链扫描验收（Dead-link check）**：第二阶段完成后，扫描全库 Markdown 的相对引用链接（如 `grep -r "\](" *.md docs/ app/` 或等效脚本），逐条校验目标文件与锚点存在，确保无指向旧位置或无效章节的死链；重点检查 `PROJECT_OVERVIEW.md` 指针页、`AGENTS.md` 文档地图、各 `*_LAYER.md` 交叉引用。
4. **两步瘦身**：AGENTS.md 先加指针保留原文，隔一次评审再删正文，杜绝一次性删除。
5. **git tag + 独立 commit**：任一步可 diff、可回滚。
6. **零修改红线**：`PROBLEM.md`、`docs/superpowers/*`、`docs/evaluation/*`、全部代码/测试/prompt/config 本轮零改动。

## 8. 验收标准（第二阶段完成后）

- [ ] `AGENTS.md` ≤120 行，仅含 A 类硬规则+铁律摘要+文档地图，无架构明细/流程明细/命令表/文件表
- [ ] §2 迁移表每一行均已勾选，grep 校验全部通过
- [ ] 8 类文档各就其位且互不重复展开同一内容（引用链：AGENTS→PROBLEM/DR/Layer 单向）
- [ ] `docs/PROJECT_OVERVIEW.md` 已改写为重定向指针页，正文全部迁出，链接经死链扫描通过
- [ ] 全库 Markdown 相对路径死链扫描通过（§7 第 3 条）
- [ ] **Layer 契约 DoD**：跨层接口变更 / 新增模块依赖 / 异常抛出类 PR 必须同步更新受影响 `*_LAYER.md`（Input/Output contract、Allowed dependencies），该规则已写入 `AGENTS.md` 硬规则并作为后续 PR 验收项
- [ ] `PROBLEM.md` 与 `docs/superpowers/` 内容零改动（git diff 为空）
- [ ] 新读者仅读 AGENTS.md 即可知道"去哪找什么"

## 9. 风险与未知点

- **风险：指针腐化**。文档间引用（AGENTS→DR→PROBLEM）可能随重构漂移；缓解：验收标准含 grep 校验与死链扫描（§7 第 2/3 条），且 AGENTS 文档地图保持高层级（指向文件而非章节行号）。
- **风险：DECISIONS.md 收录边界失控**（把临时实验结论升格为永久决策）。缓解：DR 只收录已在代码/配置/门禁中生效的事实，每条 DR 必须给出代码或 PROBLEM 出处；实验结论一律只进 `docs/evaluation/`。
- **风险：Layer 契约失忆**（未来开发越界或忘记更新契约）。缓解：Layer 契约 DoD 已固化为 PR 验收项（§1 长期稳定规则 + §8 验收标准）。
- **未知点：用户任务描述疑似来自另一项目（见 §0.1），若确认本方案适用对象有误，本 spec 作废。**
