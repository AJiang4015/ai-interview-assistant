# SERVICES_LAYER.md — 服务层契约 / 边界（Layer Contract）

> **Layer Contract / Layer Boundary**，不是代码使用说明。回答：这一层负责什么、不能负责什么。
> 适用目录：`app/services/`。系 `ARCHITECTURE.md` §4 依赖方向在服务层的细化。
>
> 变更纪律（DoD）：任何**跨层接口变更、新增模块依赖、异常抛出**都可能改动本契约；PR 必须同步更新本节相关条目，否则不满足 DoD（见 `AGENTS.md` 硬规则 / `PROCESS.md` §5）。

---

## 1. Responsibility（职责）

- 承载全部**业务编排与 RAG 管线**：索引构建、检索、重排、生成、缓存、会话，以及面试 / 深挖 / 评估等业务能力线。
- 向上为 `app/api` 提供可编排的领域操作；向下组合 `app/storage` 与 `app/utils`。
- 持有本层各模块的**决策所有权**（见 §6）。

## 2. Input contract（输入契约）

- 业务对象（问题、文件、会话 id、username、参数）由 API 层传入；服务层**不直接解析 HTTP 请求体**。
- 配置一律经 `from app.config import settings` 获取，不在服务内散落魔法常量。
- 用户隔离维度：接收 `username`（来自 JWT sub，API 层解析后透传），服务层**不自己判定身份**。

## 3. Output contract（输出契约）

- 返回领域对象 / 结构化结果；流式场景经 SSE 事件（`token` 等）回传，服务层负责编排但**不负责 HTTP 协议细节**。
- 缓存命中 / 未命中、降级路径要有明确返回值或日志，便于可观测。
- 结果可被 API 层序列化；不直接暴露存储游标 / 连接。

## 4. Decision ownership（决策所有权）

见 §6 决策所有权表与 §7 失败归因。核心原则：**一个决策只属于一个模块**，失败归到拥有该决策的层。

## 5. Allowed dependencies（允许依赖）

- 同层模块（业务编排层内合法依赖）。
- `app/storage/*`（持久化 / 检索原语）。
- `app/utils/*`（纯工具）。
- `app/config.py`、`app/exceptions.py`。

## 6. Forbidden dependencies（禁止依赖）

- **禁止反向 / 抽象泄漏依赖 API 层**（不 import `app/api/*`，不感知 HTTP / schema）。
- 禁止直连第三方（Redis/FAISS/SQLite 的连接细节归 storage）。
- 禁止依赖 `app/main.py`（装配点）或 import 彼此的模块级单例以绕过装配。

## 7. Invariants（不变量）

- **响应缓存 key 只用原始问题**，绝不混入 `session_id` / `msg_count` / `username`（DR-004 / 铁律1）。
- **SSE 事件不修改会话归属**；流绑定发起时会话 ID（DR-005 配套前端铁律）。
- **重排走 SiliconFlow API**，禁止加载本地 bge-reranker（DR-003 / 铁律3）。
- **单 worker 落盘**，索引 / state 假定单进程（DR-002）。
- 依赖失败优雅降级，不阻塞主线（DR-001）。
- `username` 隔离必须逐层透传，禁止跨用户读写（DR-010）。

## 8. Failure ownership（失败归属）

- 各模块对自己拥有的决策失败负责；跨模块失败向上抛出统一异常由 API 层映射状态码。
- 外部依赖（Redis / LLM API / Embedding API）失败 → 走降级链并在日志记录，不静默吞掉。

## 9. Testing expectations（测试期望）

- `python -m pytest tests/services/` 长期全绿。
- 涉及真实 LLM / 检索的模块需有真实评估（`docs/evaluation/`），单测覆盖降级与边界。

## 10. Typical changes allowed here（允许在此的典型改动）

- 新增 / 调整业务编排、RAG 管线段组合顺序与开关。
- 在所属模块内修正召回 / 重排 / 生成 / 缓存逻辑（不越过决策边界）。

## 11. Changes that must be implemented elsewhere（必须改在别处的改动）

- 新增 / 改 HTTP 端点或 request/response 模型 → `app/api/`。
- 存储 schema 迁移、连接管理、原子落盘 → `app/storage/`。
- 纯文本切分、日志等通用工具 → `app/utils/`。
- 全局配置项 → `app/config.py`。

---

## 6. 决策所有权表（关键：本层最重要契约）

| 模块 | Owns（拥有） | Does NOT own（明确不拥有） |
|------|--------------|---------------------------|
| chunker / text_splitter | 分块边界、overlap、临时文件（`~$`）过滤 | 检索相关性、索引状态 |
| embedding | 向量化 API 调用与降级 | 召回策略、生成质量 |
| index_service / index_pipeline | 索引构建 / 增量 / 断点续传、state 落盘原子性（幂等 / 可重入） | 查询时行为 |
| sparse_retriever | 稀疏后端选择与降级链（BM25 / Whoosh / SQLite FTS） | 融合排序 |
| retrieval_service（HybridRetriever） | 混合检索、RRF 融合、召回与 top-k | 精排顺序、生成质量 |
| query_rewrite | 查询背景改写（旁路，可关） | 检索结果正确性 |
| rerank_service | 精排顺序（SiliconFlow） | 召回不足（召回问题不归 rerank） |
| rag_service | 编排顺序、Prompt 构建、SSE 流式协议编排 | 各子模块内部决策 |
| cache_service | 缓存 key 语义（DR-004：仅原始问题）、命中 / 失效策略 | 缓存失效以外的会话逻辑 |
| llm_client | LLM 调用、流式 / 非流式封装、输出健壮解析（DR-008） | 检索内容正确性 |
| interview / deep_dive / evaluation 等业务服务 | 各自业务流程编排 | RAG 管线内部行为 |
| **agent/state_machine** | 状态 / 事件 / 转移表 / 门禁 / 逃生舱（确定性，DR-011） | 节点业务、工具、画像 |
| **agent/orchestrator** | 事件驱动编排：节点执行、转移、fallback 接线、trace 钩子、逃生舱检查 | 状态机 / Role / Tool / fallback 的内部实现（只组合不吸收） |
| **agent/roles** | 角色定义（出题 / 追问 / 评估）：system prompt、输入注入、输出 Schema（Pydantic 单一事实来源） | 校验重试（structured_output） |
| **agent/structured_output** | JSON 提取 → jsonschema 校验 → 错误回填重试（≤3 次总尝试）→ fallback 信号 | 模型调用、状态流转 |
| **agent/tools** | Tool 契约 / 注册表 / 内置六工具（kb_retrieve 等，复用存量能力）/ error_policy | 状态机转移、画像聚合 |
| **agent/model_gateway** | TaskSpec / light-turbo / heavy-plus / plus→turbo 降级链（经 LLMClient，DR-013） | LLM 请求细节（LLMClient）、跨供应商实现 |
| **agent/mcp_client** | MCP server/client 桥接（kb_retrieve + mock_resume，streamable HTTP，本地回退，DR-012） | 工具业务实现（复用 tools） |
| **agent/profile_store** | 画像存取（Redis / 会话内降级）与 E6/F8 聚合口径（DR-014） | 会话状态机、报告生成 |
| **agent/agent_service** | legacy 兼容 facade（start/answer/end + 只读委托），interview_mode 装配 | 编排细节（orchestrator） |
| **agent/trace** | trace JSONL 写入 / 保留策略 / 字段完整性（DR-016） | 归因解释（演示/复盘侧） |
| **agent/fallback** | 确定性兜底：G1-F 出题 / G4-F 规则分 / G8 确定性摘要 | 结构化输出重试主体 |

## 7. 失败归因分类（必须先归到拥有该决策的层，禁止"哪里方便改哪里"）

```text
解析 / 分块失败 ≠ 索引构建失败 ≠ 召回失败 ≠ 重排失败
≠ 生成失败 ≠ 缓存失败 ≠ 会话 / 流式失败 ≠ 前端渲染失败
```

- 召回不足 → 归 `retrieval_service`，不改 rerank / 生成。
- 精排顺序差 → 归 `rerank_service`，不回退去改检索。
- 命中率低 → 归 `cache_service`（检查 key 是否混入可变维度）。
- 某 chunk 失败拖垮整批 → 归 `index` / `chunker` 的异常隔离。

**Agent 编排线失败归因**（DR-011~016）：

```text
状态非法 / 卡死 ≠ 节点输出不合 schema ≠ 工具失败 ≠ 模型调用失败 ≠ 画像口径错误
```

- 状态流转非法 → 归 `agent/state_machine`（转移表 / 门禁 / 逃生舱），不绕到 orchestrator 改流程。
- LLM 输出不合 schema → 归 `agent/structured_output`（提取 / jsonschema / 回填重试 / fallback 信号）。
- 工具执行失败 → 归 `agent/tools`（degrade 跳过打标 / abort 触发逃生舱，进降级矩阵 G）。
- 模型调用失败 → 归 `model_gateway` 降级链（plus→turbo）→ 仍失败归 LLMClient 错误处理。
- 画像 accuracy 口径偏差 → 归 `agent/profile_store`（E6/F8），不在 orchestrator 内另算。
- 归因不清 → 归 `agent/trace` 缺事件 / 缺字段（先补 trace 再下结论）。