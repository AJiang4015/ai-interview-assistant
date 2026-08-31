# DECISIONS.md — Decision Record

> 已做出的、未来仍需要遵守的架构 / 工程决策，以及为什么这样决定。
> 适用项目：RAG 知识库 / Java 程序员智能面试助手（Interview RAG） — FastAPI + Redis + FAISS。
>
> 使用规则：
> - 本文件只收录**已在代码 / 配置 / 门禁 / 流程中生效的事实决策**，每条必须给出出处（代码 / PROBLEM.md / Spec）。
> - **禁止**把"某次实验发生了什么"写进本文件；实验结果一律进 `docs/evaluation/`。
> - 新增决策时先判断真伪：临时方案 / 未落地的讨论 / 单次实验结论 → 不收录。
> - 每条决策遵循固定格式：`Decision ID / Title / Status / Date / Context / Decision / Reason / Consequence`。

---

## 0. 格式说明

| 字段 | 含义 |
|------|------|
| Decision ID | `DR-###`，全局唯一，一旦分配不改 |
| Title | 决策一句话 |
| Status | `Active / Deferred / Superseded` |
| Date | 决策固化到文档/代码的日期 |
| Context | 为什么需要决策（背景 / 冲突） |
| Decision | 最终选择 |
| Reason | 选择依据 |
| Consequence | 长期影响 / 衍生约束 |

> 为便于速览，下表以压缩形式呈现；`Consequence` 中带出的约束会在对应 Layer / PROCESS 文档引用。

---

## 1. Decision 汇总

| ID | Title / Decision 要点 | Status | Date | 出处 |
|----|----------------------|--------|------|------|
| DR-001 | **RAG 管线各模块必须可配置开关 + 依赖失败优雅降级**：查询改写 / 混合检索 / 重排 / 缓存均提供 `enable_*` 开关（`config.py` + `.env`）；依赖失败不阻塞主线（Redis 不可用→禁用会话/缓存；BM25 缺失→回退 FAISS-only；OTel/评估失败→静默降级） | Active | 2026-08-28 | `PROBLEM.md` D7 / Door 7；原 `AGENTS.md` §3 |
| DR-002 | **单 worker 落盘模型**：运行态全局与 FAISS/index 落盘（`ingest_state.json`）假定单进程；Docker 以 `--workers 1` 启动；多 worker 需另行补进程级锁或换外部存储 | Active | 2026-08-28 | `PROBLEM.md` D9 / Door 9 / P006；Dockerfile |
| DR-003 | **重排走 SiliconFlow API（Qwen/Qwen3-Reranker-4B）**，禁止加载本地 `BAAI/bge-reranker-v2-m3` 等需外网下载或含 OMP 冲突的模型 | Active | 2026-08-28 | `PROBLEM.md` D6 / P003 / P004；原 `AGENTS.md` 铁律3 |
| DR-004 | **缓存 / 去重 key 基于不变语义**：`cache.make_key()` 只用原始问题原文，禁止混入 `session_id` / `msg_count` / `username` 等可变维度 | Active | 2026-08-28 | `PROBLEM.md` D5 / P001 / Door 5 |
| DR-005 | **流式协议选型 SSE（单向）**：事件类型 `session / retrieval / token / done / error`；非 WebSocket | Active | 2026-08-28 | 原 `AGENTS.md` §2 |
| DR-006 | **混合检索采用 RRF（k=60）融合**：FAISS 稠密 + BM25 稀疏结果取 Reciprocal Rank Fusion | Active | 2026-08-28 | 原 `AGENTS.md` §3；`retrieval_service.py` |
| DR-007 | **Redis 固定实例承载会话/缓存**：地址 `192.168.127.101:6379`，会话 TTL 3600s、单会话 ≤20 轮；Redis 不可用→禁用相应功能 | Active | 2026-08-28 | 原 `AGENTS.md` §2/§3 |
| DR-008 | **LLM 输出健壮解析**：生成 / parse / judge 输出做 JSON 围栏剥离与非法值兜底，失败不阻塞主流程 | Active | 2026-08-28 | `PROBLEM.md` D14 / P008 |
| DR-009 | **前端安全渲染链**：`innerHTML` 注入前 `escapeHtml()` 转义；Markdown 经 `marked.parse → DOMPurify` 过滤；CDN 加载失败回退纯文本 | Active | 2026-08-28 | `PROBLEM.md` D10 / P005 |
| DR-010 | **请求上下文透传与用户数据隔离契约**：API 层经 `Depends(get_current_user)` 解析 Token 得到 `username`（JWT `sub`），逐层透传到存储作隔离作用域；会话 CUD / 查询 / 搜索均按用户过滤，跨用户访问一律 404；Redis = 短期热数据，SQLite = 长期事实源（Redis miss → SQLite 恢复回填） | Active | 2026-08-28 | `docs/superpowers/specs/2026-08-27-user-history-isolation-persistence-design.md`、`2026-08-27-user-isolation-review-profile-design.md`（PR #1 已合入，squash SHA `51dc39ae`） |
| DR-011 | **Agent 采用确定性编排状态机**：手写 enum+转移表+门禁（`app/services/agent/state_machine.py`），LLM 只在角色节点内被调用；不做自由 ReAct 循环、不堆 Multi-Agent；转移/门禁/逃生舱全部确定性代码，非法转移拒绝 | Active | 2026-09-01 | `docs/superpowers/specs/2026-08-31-agent-orchestration-refactor-design.md`（决策1）+ impl-spec v2 附录 A/B/C |
| DR-012 | **MCP 采用官方 SDK + streamable HTTP 运输**：`kb_retrieve`/`mock_resume` 暴露为真实 MCP tools（handler 复用 tools.py）；运输方式经实测 stdio 在本环境被拒（子进程管道 PermissionError）→ 改 streamable HTTP；MCP 不可用自动回退本地 ToolRegistry | Active | 2026-09-01 | impl-spec v2 决策2 / 附录 F / B4；`app/services/agent/mcp_client.py` |
| DR-013 | **统一模型接入经 LLMClient 分级调用**：`ModelGateway` 只做 TaskSpec / light→qwen-turbo / heavy→qwen-plus / plus→turbo 降级链；必须经 `LLMClient.chat(..., model=None)`（OPEN-2 冻结），不存在第二套 HTTP；成本按实际模型名记录；跨供应商仅保留 `ProviderAdapter` 接口 | Active | 2026-09-01 | impl-spec v2 附录 E5 / W0 OPEN-2/B5；`app/services/agent/model_gateway.py` |
| DR-014 | **候选人画像口径（F8 冻结）**：`{weak_points, level, accuracy, history}`；accuracy = 最近 10 次主问题单题分均值（过滤 `source='followup'`）；G4-F 兜底分计入但保留 fallback 标记；SUMMARIZING 批量写；RedisProfileStore + Redis 不可用降级会话内；跨会话驱动初始难度与主题注入 | Active | 2026-09-01 | impl-spec v2 附录 E6 / W0 F8；`app/services/agent/profile_store.py` |
| DR-015 | **追问（FOLLOWUP）契约**：独立 question_id + `source='followup'` + topic/category 留空；统计 / coverage / 画像一律过滤 followup（stats/get_coverage `exclude_sources` 扩展，默认行为不变）；单问题最多 1 次追问；追问生成失败 → 预算置 0 走评估（G1-f，无新增状态） | Active | 2026-09-01 | impl-spec v2 附录 A6 / F1 / W0 OPEN-3/4/5、F9 |
| DR-016 | **Trace 作为归因基础设施（附录 H）**：JSONL 每 session 一文件（`data/traces/{session_id}.jsonl`），7 类事件（transition/node_started/node_finished/tool_call/fallback/escape/session_end），字段含 retries/validated/fallback_used/latency/cost；保留最近 N 个；用于归因四象限（模型/流程/数据/评估） | Active | 2026-09-01 | impl-spec v2 附录 H；`app/services/agent/trace.py` |

---

## 2. 重要决策详解

### DR-010 用户隔离与持久化契约（2026-08-27/28 新增主线）

> 由 `2026-08-27-user-history-isolation-persistence-design.md` 固化，PR #1 合并后已生效。分 `username` 隔离维度与`短期/长期记忆`双层存储。

- **Context**：原有会话以 `session:{id}` 无归属存储，`GET /api/sessions` 全局扫描可见所有人，CUD 无归属校验（水平越权），Redis TTL 过期即永久丢失历史。
- **Decision**：
  - 隔离维度 = `username`（JWT `sub`，复用现有 `get_current_user`）；
  - Redis（`SessionStore`）= 短期热数据，多轮上下文快路径，TTL 3600s 不变；新增 `user_sessions:{username}` 集合索引，`list_sessions` 改读集合而非全局 scan；
  - SQLite（`SearchStore`）= 长期事实源，`sessions` 表加 `username`/`updated_at` 列（幂等迁移），`search` 按 username 过滤；
  - 恢复逻辑：`get_session_history` Redis miss 且 SQLite 归属匹配 → 从 SQLite 读取全部消息回填 Redis（刷新 TTL）；
  - 越权统一 404（不暴露存在性）；`DELETE /api/sessions` 语义改为"清空当前用户"；
  - 兼容：存量无 `username` 行标记 legacy 不可见、不迁移；SQLite 异常走 Redis-only 降级（遵循 DR-001）。
- **Reason**：既要短期多轮上下文（LLM prompt）又要跨 TTL/重启的长期可回看，遂以"DB 分离 + 恢复回填"覆盖两种时效；逐层透传 username 避免存储做身份判断。
- **Consequence**：RAGService 的 7 个会话方法签名透传 `username`（`query` / `stream_query` / `create_session` / `get_session_history` / `delete_session` / `list_sessions` / `clear_user_sessions`，见 `app/services/rag_service.py`）；`api` 层承担归属校验；`enable_history_persistence` 开关控制该特性；缓存 key 铁律（DR-004）仍不混入 username；`DELETE /api/sessions`（清空当前用户全部会话）已实现于 `app/api/routes.py:234`。

### DR-002 / DR-003 / DR-004 的连带约束

- 三者共同构成"本地重型资源 + 落盘 + 缓存键"三条高压线，已在 `PROBLEM.md` §4 高频规则与 `AGENTS.md` 铁律汇总中有浓缩护栏；本文件为决策事实层，`PROBLEM.md`（注册表）与 `docs/problems/`（问题档案）为历史证据层，`AGENTS.md` 只保留最短强制摘要，三者单向引用，不重复展开。

### DR-011~016 的连带约束（Agent 编排线）

- **为什么选确定性状态机（DR-011）**：可测（转移表逐行单测）、可归因（trace 事件对齐状态）、可降级（门禁/逃生舱确定性兜底）；自由 ReAct 在确定性、可测性与归因三方面均弱于本路线，且与目标 JD"流程编排与规则校验由确定性代码实现"直接对齐。
- **为什么 MCP 从 stdio 改 HTTP（DR-012）**：实测本环境 stdio 子进程管道被沙箱拒绝（PermissionError），streamable HTTP 端到端通过；决策留出"运输方式可替换"（memory 供单测，HTTP 供运行时），协议层不变。
- **为什么 Gateway 不绕过 LLMClient（DR-013）**：复用既有 retry（tenacity）、成本（monitor.emit_cost 按实际模型名）、错误处理与超时链路；避免第二套 HTTP 请求逻辑的维护与漂移；分级只是"选模型"，不是"再造客户端"。
- **为什么 Memory 做薄（DR-014）**：只存四字段 + 最近 10 次主问题分均值；不做记忆层级/摘要管线/检索式记忆；降级路径（会话内）与生产路径（Redis）同协议。
- **为什么 followup 用 source 标记而非加列（DR-015）**：不迁移 schema、不破坏存量；统计/画像用 `exclude_sources` 过滤（默认行为不变，F9）。
- **Trace 只读，不建查询服务层（DR-016）**：trace 是归因/演示基础设施，读取由 W3 只读端点直读文件完成，不进入产品查询链路。

---

## 3. 变更记录

- 2026-09-01：Agent 编排线决策固化——DR-011 确定性状态机、DR-012 MCP 选型与运输、DR-013 Model Gateway 分级、DR-014 画像口径（F8）、DR-015 追问契约、DR-016 Trace 归因 schema（出处：impl-spec v2 与 W0 决策冻结）。
- 2026-08-28：随"文档架构整理"（`docs/superpowers/specs/2026-08-28-docs-architecture-reorg-design.md`）从原 `AGENTS.md`、`PROBLEM.md`、相关 Spec 沉淀首批 DR-001~010。