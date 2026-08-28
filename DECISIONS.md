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

- 三者共同构成"本地重型资源 + 落盘 + 缓存键"三条高压线，已在 `PROBLEM.md` §0a 三条铁律与 `AGENTS.md` 铁律汇总中有浓缩护栏；本文件为决策事实层，`PROBLEM.md` 为历史证据层，`AGENTS.md` 只保留最短强制摘要，三者单向引用，不重复展开。

---

## 3. 变更记录

- 2026-08-28：随"文档架构整理"（`docs/superpowers/specs/2026-08-28-docs-architecture-reorg-design.md`）从原 `AGENTS.md`、`PROBLEM.md`、相关 Spec 沉淀首批 DR-001~010。