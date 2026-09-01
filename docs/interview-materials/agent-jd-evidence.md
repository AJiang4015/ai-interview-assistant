# Agent 面试表达 — JD Evidence（要求 → 实现 → 证据 → 证明方式）

> 依据：W0 JD 拆解（3 份 JD，32 项要求）+ impl-spec v2 + DR-011~016 + 实测证据。
> 覆盖标记：✅ 已实现　🟡 部分覆盖（有实现但范围受限，如实说明）　🔴 out-of-scope（明确不做，有边界与话术）
> **原则：out-of-scope 绝不描述成"已经实现"。**

---

## 12 个重点能力映射

### 1. State Machine ✅
- **JD**：多阶段流程状态机（JD1-1）；确定性技术路线（JD1-14）。
- **实现**：手写 enum + 转移表 + 门禁（`app/services/agent/state_machine.py`）：8 状态 / 10 事件 / 14 行转移 / G0-G9 门禁 / 全局逃生舱；非法转移拒绝。
- **证据**：`tests/services/agent/test_state_machine.py` 23 用例（转移表逐行、门禁互斥、非法转移、G7 条件）；评测真实 trace 流转合法率 100%。
- **面试证明**：现场指出 `TRANSITIONS` 是纯数据结构；讲"行 4/5 同事件互斥由守卫保证"；讲逃生舱 4 类触发。

### 2. Gate ✅
- **JD**：阶段门禁（JD1-2）。
- **实现**：G0-G9 确定性守卫（position/answer 长度/难度 enum/去重/评分范围/追问触发/难度调整/收尾/逃生）。
- **证据**：门禁单测（守卫互斥、拒绝原因 `guard_denied:<gate>`）；G5 难度表全分支单测。
- **面试证明**：举 G9（短答触发追问：`followup_budget>0 ∧ answer_len<200`）说明"门禁 = 确定性规则，不依赖 LLM 判断"。

### 3. Tool Use ✅
- **JD**：确定性工具层：规则校验 / 参数汇算 / 外部检索（JD1-6）。
- **实现**：`Tool` 契约（name/description/input/output schema/handler/timeout/error_policy）+ `ToolRegistry` + 六内置工具（kb_retrieve / get_profile / update_profile / mock_resume / pick_next_topic / eval_rules）。
- **证据**：`tests/.../test_tools.py`（注册幂等 / schema 校验 / timeout / degrade-abort）；编排层零改动经统一接口使用工具。
- **面试证明**：讲 `eval_rules` 是"规则校验+参数汇算"示例（G5 载体）；讲工具失败进降级矩阵。

### 4. MCP ✅（transport 已实测调整）
- **JD**：外部数据检索客户端(MCP)（JD1-6）；基于 MCP 扩展工具（JD2-1）。
- **实现**：官方 mcp SDK 2.1.1，`kb_retrieve`+`mock_resume` 暴露为真实 MCP tools（handler 复用 tools.py）；**streamable HTTP**（stdio 实测被拒）；内存 transport 供单测；MCP 不可用自动回退本地 ToolRegistry。
- **证据**：`tests/.../test_mcp_client.py` 6 用例（内存真实协议 / HTTP 真实传输 / 占用端口回退本地）；DR-012。
- **面试证明**：讲"协议统一、transport 可替换"的取舍过程（探测三 transport 的实测结论）；讲回退不破坏 W1 链路。

### 5. Structured Output ✅
- **JD**：结构化输出约束（JD1-5）；把 JSON Schema 当接口契约（JD1-11）。
- **实现**：Pydantic 模型为单一事实来源 → `model_json_schema()` 生成对外契约；`structured_output.py` 提取 → jsonschema 校验 → 错误回填重试。
- **证据**：`test_roles.py` 防漂移测试（jsonschema 与 pydantic 判定一致）；`test_structured_output.py` 16 用例。
- **面试证明**：讲"JSON Schema 即接口契约"：schema 从模型生成、双方 strict 一致，杜绝两套 schema 漂移。

### 6. Retry ✅（口径已冻结）
- **JD**：失败重试（JD1-5/2-3）。
- **实现**：`max_attempts=3` = 1 次初始生成 + 最多 2 次重试，第 3 次仍失败 → `fallback=True`；重试时把校验错误回填 prompt。
- **证据**：单测（第 1/2/3 次成功、3 次全败→fallback、retries=attempts-1）；trace 的 retries 字段 ≤2。
- **面试证明**：讲清"3 次总尝试"语义（避免"3 次重试"歧义，已冻结进 spec）；讲错误回填（不是盲目重试）。

### 7. Fallback ✅
- **JD**：重试降级逻辑（JD2-3）。
- **实现**：确定性兜底三件套：G1-F 兜底题 / G4-F 规则评分（`round(5+5×hit_ratio)`，短答记 2）/ G8 确定性摘要；统一降级矩阵（LLM/RAG/工具/Redis/预算/超时）；逃生舱。
- **证据**：`test_fallback.py` + orchestrator 降级单测（LLM 失败→G1-F/G4-F）+ 真实 401 冒烟 29/29 + 逃生场景。
- **面试证明**：现场演示 Demo 章节 3（LLM 挂→兜底→逃生，trace 可见）。

### 8. Model Routing ✅（跨供应商 🟡/🔴）
- **JD**：多模型供应商与分级调用策略（JD1-7）；LLM 选型与成本（JD2-3）。
- **实现**：`model_gateway.py`：light→qwen-turbo / heavy→qwen-plus / plus→turbo 降级链；经 LLMClient（无第二套 HTTP）；成本按实际模型名记录。
- **覆盖说明**：分级与降级 ✅；**跨供应商只保留 `ProviderAdapter` 接口，未实现第二供应商（B5，out-of-scope）**。
- **证据**：`test_model_gateway.py` 9 用例（light/heavy/降级/不绕过/接线集成）。
- **面试证明**：讲"分级是策略、客户端只有一个"；主动声明跨供应商是接口预留。

### 9. Memory ✅（做薄）
- **JD**：长记忆存储（JD2-3）；长期记忆驱动策略（决策 6）。
- **实现**：`{weak_points, level, accuracy, history}`；RedisProfileStore（异常降级会话内）；SUMMARIZING 批量写；跨会话驱动初始难度与薄弱点注入。
- **证据**：`test_profile_store.py`（口径/Redis/降级）+ 跨会话集成单测 + **真实 Redis roundtrip 13/13**。
- **面试证明**：讲"Memory 做薄"：只存 4 字段 + 最近 10 次主问题分，不做记忆层级/摘要管线；降级路径同协议。

### 10. Evaluation ✅（原始基线，不宣称赢）
- **JD**：出问题能归因（JD1-13）；Agent 评测/对齐（JD3-5）。
- **实现**：17 条子集 legacy vs agent；recall@3/MRR（共享检索管线）+ 单题分分布 + 追问合理性（5/5 人工确认）+ trace assertions。
- **原始结果**：recall@3=0.588；legacy scores [3,1,3] mean 2.33 / agent [2,2,2] mean 2.0；trace 合法率 100%。
- **面试证明**：**不宣称 agent 优于 legacy**——讲"评估风格差异（agent 更严格稳定）+ 检索召回是共享管线指标"；讲"先原始结果、不调参"的评测纪律。

### 11. Trace ✅
- **JD**：归因能力（JD1-13）；Harness 观测（JD3-5）。
- **实现**：JSONL 每 session 一文件，7 类事件，字段含 retries/validated/fallback_used/latency/cost；只读端点 + 静态页（Demo）。
- **证据**：`test_trace.py` 9 用例；评测 trace assertions 全过；真实 demo trace 可读。
- **面试证明**：四象限归因现场演示（模型/流程/数据/评估）。

### 12. Context Engineering ✅（🟡 部分）
- **JD**：上下文工程（JD1-12）；上下文裁剪（JD2-3）。
- **实现**：按阶段注入（出题注入 KG/RAG+画像+建议方向；评估注入参考要点）；`max_context_chars` 裁剪 + 历史复用 `max_history_turns`。
- **覆盖说明**：注入与裁剪 ✅；**Prompt 版本管理 🟡**（trace 有 `prompt_version` 字段，但无版本化机制，技术债 P1）。
- **证据**：`roles.py` 注入构建 + 编排层调用链 + demo 真实注入效果。
- **面试证明**：讲"按阶段注入 = 角色节点的上下文契约"，承认版本管理是未做的 P1。

---

## 3 份 JD 的覆盖结论（沿用 W0 拆解，不重新设计）

| JD | 覆盖结论 |
|---|---|
| JD1 核心 Agent 实现 | 12 项要求：状态机/门禁/角色/工具/MCP/结构化输出/归因/确定性路线全部 ✅；Java 生产实现 🔴（决策 4：纯 Python，话术讲移植路径） |
| JD2 桌面办公 Agent | RAG 落地 ✅；分层/取舍/混合部署 🟡（本项目是浏览器→后端→云端模型雏形）；Computer-Use 🔴（明确 out-of-scope，工具契约留扩展点） |
| JD3 跨境电商 Agent 平台 | Harness/评测/环境感知 ✅（trace+eval+上下文注入）；前端/客户端融合 🟡；业务流 Agent 化 🟡（面试场景即案例） |

**话术要点**：对 🔴 项一律主动声明"这是明确不做，不是没做到"，并给出边界理由（JD1-8 移植路径 / JD2-6 场景取舍）；对 🟡 项讲"已有实现 + 缺口在哪 + 如果要做怎么补"。
