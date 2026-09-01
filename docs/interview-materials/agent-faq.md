# Agent 面试表达 — 20 个高频追问应答

> 原则（2.5）：所有回答基于当前实际实现，能指出代码 / trace / 测试证据；区分"已实现 / 未来可做"；
> 不虚构能力；先答"为什么这样设计"。
> 代码路径：`app/services/agent/`　决策：DR-011~016　测试：`tests/services/agent/`　评测：`docs/evaluation/`

---

### 1. 为什么不用 ReAct？
自由 ReAct 的循环边界由模型决定 → 不可测、不可归因、成本不可控。我用**确定性状态机**：转移表 + 门禁决定"什么时候走哪条边"，LLM 只在节点内生成。证据：转移表逐行单测、trace 合法率 100%；JD 原文"认同确定性技术路线"直接对齐。**边界**：如果未来任务开放到无法预枚举（如开放域自主探索），ReAct 才有价值——那是另一个场景。

### 2. Agent 和普通 Workflow 的区别？
普通 Workflow = 固定 if-else 管线；Agent = **在固定骨架内，由 LLM 在每个角色节点做"内容决策"**（出什么题、怎么追问、怎么评估），而"结构决策"（阶段流转/门禁/降级）是确定性的。我的系统是两者的结合：**骨架确定、内容生成交给 LLM、质量由门禁兜底**。

### 3. 你的 Agent 到底在哪里做了决策？
两类决策分得很清：**结构决策**（出题→追问→评估→难度→收尾）在 `state_machine.py` 转移表 + 门禁；**内容决策**（题目文本/追问文本/评分理由）在三个角色节点（roles + structured_output）。追问要不要触发是门禁 G9（确定性：短答+预算）；怎么追问是模型。这是设计核心，不是模糊地带。

### 4. 为什么 RAG 是 Tool？
项目主体是 Agent 编排；RAG 是继承的成熟能力。封装成 `kb_retrieve` 工具注入节点，**不重构、不重复实现**，既保留"RAG 整套落地"（JD2-4）又让主体是 Agent。证据：`tools.py` 直接包 `RetrievalFacade`，RAG 零新增代码。

### 5. 为什么要 JSON Schema？
因为 LLM 输出不可信。JSON Schema 是**接口契约**（JD1-11）：提示词约束 + 本地 `jsonschema` 校验 + 校验失败把错误回填 prompt 重试。防漂移设计：schema 由 Pydantic 模型 `model_json_schema()` 生成（单一事实来源），jsonschema 与 pydantic 双方 strict 判定一致（有防漂移单测）。**先契约后生成**，而不是"生成后猜结构"。

### 6. Retry 为什么是 3 次总尝试？
口径已冻结：`max_attempts=3` = **1 次初始生成 + 最多 2 次重试**，第 3 次仍失败 → `fallback=True`。理由：①与逃生舱 `max_structured_retries=3` 对齐；②重试不是盲试——每次把校验错误回填 prompt（告诉模型哪里错了）；③重试耗尽必须走确定性兜底（G1-F/G4-F），不能无限烧成本。trace 里 `retries=attempts-1` ≤ 2。

### 7. LLM 挂了怎么办？
降级矩阵（spec G）：LLM 调用失败 → 分级降链（heavy plus→light turbo）→ 节点确定性兜底（出题 G1-F 模板题 / 评估 G4-F 规则分 / 报告 G8 确定性摘要）→ 连续失败触发逃生舱强制收尾。真实证据：401 环境冒烟 29/29、Demo 章节 3 现场演示。**任何单点故障不会让状态机卡死**。

### 8. Tool 挂了怎么办？
`error_policy`：degrade = 跳过并 trace 打标（如 kb_retrieve 挂 → 无上下文出题）；abort = 触发逃生舱（G7）。工具异常统一 `ToolError` 层级，编排层捕获进降级矩阵。证据：`test_tools.py` degrade/abort 用例 + Demo RAG 故障演示。

### 9. MCP 为什么不用 stdio？
先做了 transport 探测：本环境（Windows + 沙箱）**stdio 子进程管道被拒**（PermissionError 实测），streamable HTTP 端到端通过。MCP 协议统一、transport 可替换 → 采用 HTTP。单测用 SDK 官方内存 transport 跑真实协议（无 IO 依赖）。**这是实测决策不是偏好**（DR-012）。

### 10. 为什么不用 LangGraph？
当前状态集固定（8 状态/10 事件/14 转移），手写转移表 = 纯数据结构，可逐行单测、可讲 Java 移植路径；LangGraph 的收益（动态状态、checkpoint/中断、生态）在这个规模下小于迁移成本。我只做了**概念映射**学习（State/Graph/Edge/Conditional Edge/checkpointer ↔ 手写对应物，复盘 §8），不实现——这是砍单链批准的产出。

### 11. 为什么不用 Multi-Agent？
单会话串行面试不需要跨 agent 协作；Multi-Agent 引入通信与协调成本，是"为展示而堆"。角色分工（出题/追问/评估）已在单 agent 内用角色节点表达。**核心决策 2 明确不做**。

### 12. Memory 保存什么？
四字段：`{weak_points, level, accuracy, history}`。做薄：不做记忆层级/摘要管线/检索式记忆。RedisProfileStore（`agent:profile:{user_id}`）+ 不可用降级会话内；SUMMARIZING 会话末批量写。证据：真实 Redis roundtrip 13/13。

### 13. historical accuracy 怎么算？
`accuracy = 最近 10 次主问题单题分均值`（E6/F8 冻结口径）。实现：`compute_session_profile_patch` 把每场会话主问题分数追加进 history，取最近 10 条算均值，同时推导 weak_points（均分 <6 的主题）与 level（≥8 高级/≥6 中级/初级）。**不依赖 total_score 字段**（存储层 SUM 与报告层 AVG 双口径问题已在 W0 发现并规避）。

### 14. 为什么 followup 不计入 accuracy？
followup 是同一道主题的澄清，不是独立考察点；计入会稀释主问题评分口径并污染覆盖率。实现：followup 行 `source='followup'`，stats/coverage/画像全部 `exclude_sources` 过滤（F9，默认行为不变）；追问行 topic/category 留空天然不入覆盖统计。

### 15. Agent vs legacy 如何评估？
同一批 17 条子集（`data/eval_interview_subset.json`）：recall@3/MRR（共享检索管线）+ 单题分分布 + 追问合理性（人工，5/5 确认）+ trace assertions（流转合法率 100% 等 5 项）。**先原始结果、不调参**；报告先于结论（PROCESS §1）。

### 16. 为什么 agent 指标没有全面超过 legacy？
如实回答：单题分 agent [2,2,2] mean 2.0 vs legacy [3,1,3] mean 2.33——**agent 评估官更严格稳定**（qwen-plus），这是评估风格差异不是质量结论，且样本仅 3 轮不具统计意义；recall@3 是共享管线指标（同一 RetrievalFacade），与 agent/legacy 无关。**我不宣称赢**——这个系统的价值在可测、可归因、可降级，不是分数碾压。扩大样本与真实用户回答是后续工作。

### 17. Trace 能解决什么问题？
归因（模型/流程/数据/评估四象限）+ 复现（每 session 一 JSONL，7 类事件）+ 审计（retries/fallback/escape 全记录）。demo 里 401 场景一眼定位"LLM 失败→兜底生效"。**先归因再动手**，避免盲改（PROCESS §0）。

### 18. 如果状态机死循环怎么办？
全局逃生舱（附录 C）：最大轮数 15 / 连续失败 3 / 累计兜底 5 / 转移计数 200 / 单节点超时 60s / 预算超限——全部不依赖 LLM，触发即 FORCE_END → 收尾。转移计数护栏从机制上杜绝死循环；trace 记录 escape_reason。单测覆盖 G7 各条件。

### 19. 为什么 ModelGateway 不直接 HTTP？
分级（light/heavy）只是"选模型"；直接 HTTP = 第二套请求/重试/成本/错误处理——重复且与 LLMClient 漂移。`BailianAdapter` 只调 `llm.chat(..., model=None)`（OPEN-2 最小扩展），成本按实际模型名记录。证据：单测断言调用链 gateway→LLMClient。

### 20. 如果让你继续做，下一步是什么？
按技术债清单（复盘 §9）讲优先级：**P0** ① 进程内会话状态 → Redis 持久化（断点恢复）；② MCP adapter 生命周期正式接线（startup/shutdown）+ app.main 启用开关；**P1** ③ trace 权限治理；④ prompt/schema 版本管理；⑤ 评测样本扩大（真实用户回答）；然后才考虑 P2（跨供应商、LangGraph 迁移评估）。**边界清晰：先把生产化债还完，再谈新能力**。
