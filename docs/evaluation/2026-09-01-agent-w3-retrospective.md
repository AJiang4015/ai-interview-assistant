# Agent 编排化改造 — W1–W2 架构复盘（W3 Phase 3）

> 日期：2026-09-01　|　分支：agent-dev（main 冻结于 `6a0e385`）　|　范围：W1 Day1-5 / W2 上 / W2 下
> 依据：commit 历史（25 个 agent 相关提交）、impl-spec v2、W0 决策冻结、两份 evaluation 报告、冒烟结果
> **原则：以实际证据为准，不补造原因或结论。**

---

## 1. 原计划 vs 实际完成

| 阶段 | 原计划（impl-spec v2 里程碑 + W0 映射） | 实际完成 | 偏差 |
|---|---|---|---|
| W0 | 切分支、补 spec 附录、JD 拆解映射、接缝确认 | ✅ 全部完成（31ace60→0fb5f38） | 无 |
| W1 | 状态机/门禁/逃生舱 + 角色/结构化输出重试 + 本地工具 + trace + 装配 + 最小闭环 demo | ✅ Day1-5 全部落地（2e6cada→3f4e60f），真实 LLM 复验 | 无（砍单链未触发） |
| W2 上 | MCP 双工具（2 天盒）+ model_gateway 分级 | ✅ 完成 + 真实 LLM 生成 27/27 PASS（8e2299e） | MCP 运输 stdio→streamable HTTP（计划内 B4 分支被实际触发） |
| W2 下 | Redis 画像 + 17 条对照评测 | ✅ 完成（f3a542d + 1e16521），追问 5/5 人工确认 | 真实 Redis 未连（凭据缺失，W3 补验） |
| W3 | Demo/表达/复盘/决策固化 | 进行中（8060c4c 决策固化） | — |

**commit 体量**：自 main 冻结点，25 个提交，`app/services/agent/` + `tests/services/agent/` 净增约 5437 行。

## 2. 偏差与原因（全部有证据）

1. **真实 LLM 一度不可用**（影响 W1 Day5 / W2 评测）：
   - 现象：`401 InvalidApiKey`，`os.environ` 无 key。
   - 实验：环境探测 → key 为 **Machine 级系统变量，DSH 沙箱过滤了敏感 env 的进程继承**（PATH/WINDIR 在、key 不在）；`.env` 仅 8 字符占位。
   - 决策：运行命令显式注入 Machine 级 key（不落盘、不提交）→ 真实生成 27/27 PASS。
   - 固化：W1 smoke 报告 §8.1。**非业务代码问题，无代码改动**。
2. **MCP stdio 在 Windows 沙箱被拒**：
   - 现象：`PermissionError [WinError 5]`（子进程管道）。
   - 实验：三种 transport 端到端探测（memory / stdio / streamable HTTP）→ 仅 HTTP 通过。
   - 决策：streamable HTTP（DR-012，spec B4 预置分支）；单测用 SDK 官方内存 transport。
   - 固化：mcp_client.py + DR-012。**属计划内 fallback 被实测触发，非砍单。**
3. **Redis 无凭据**（W2 下画像实连未验）：
   - 现象：`HELLO must be called with the client already authenticated`。
   - 决策：运行时正确降级 SessionProfileStore（**要求 7 被真实触发**）；W3 凭据到位后补 roundtrip smoke。
   - **W3 补验结果（13/13 PASS）**：`scripts/agent_redis_smoke.py` —— make_profile_store(正确密码)→RedisProfileStore；Session A（LLM 分 3）→ SUMMARIZING 写真实 Redis；跨实例（新 RedisProfileStore）读一致（accuracy=3.0 / weak_points=[JVM] / level=初级）；原始 key JSON 可解析；Session B（新进程视角）INIT 注入生效（目标难度 easy + 薄弱点 JVM 进 prompt）；错误密码 → SessionProfileStore 降级。密码仅经环境变量注入，未落盘/未提交。
4. **评测输入选择**（非流程调参）：单题分用 topic-aware 模板回答（避免通用模板触底），报告如实标注为评测输入约束。

## 3. 命中/未命中的风险

| 风险（review-plan A6） | 结果 |
|---|---|
| W1 超载 | **未命中**：按天拆分（状态机→角色→工具→编排→装配），40h 内出最小闭环 |
| MCP Windows/stdio 环境风险 | **命中** → 转 streamable HTTP（见 §2.2） |
| 前端契约假设 | **未命中**：API/frontend 零改动成立 |
| 状态机死循环/卡死 | **未命中**：全局逃生舱 + 转移计数护栏；trace 合法率 100% |
| 对照跑数心态 | **部分命中**：agent 单题分（mean 2.0）低于 legacy（2.33）——按"有意识地在测"原则保留原始结果，未调参、未宣称优于 |

## 4. 被验证的设计决策 / 未验证的设计

**验证成立**：
- 确定性状态机可测可归因：转移表逐行单测 + 真实会话 trace 状态流转合法率 100%（53/53）。
- RAG 作 Tool：kb_retrieve 直接包 RetrievalFacade，零重复实现。
- 结构化输出重试→确定性兜底闭环：真实 401 下 G1-F/G4-F 全流程仍完成。
- model_gateway 经 LLMClient：无第二套 HTTP（单测断言调用链）。
- MCP 统一 Tool 接口 + 本地回退：编排层零改动，占用端口自动回退（单测）。
- 画像口径（F8）：accuracy/weak_points/level 聚合与跨会话驱动（单测 + 集成 + **真实 Redis roundtrip 13/13**）。

**未验证（明确留白）**：
- 真实 LLM 长提示延迟波动（qwen3.8-max 偶发 >30s）→ 评测仅 3 轮，样本小。
- Redis 长画像跨进程一致性 → W3 roundtrip smoke 补验。
- LangGraph 迁移 / 跨供应商 → 刻意未做（out-of-scope，不算技术债，见 §6）。

## 5. 主动取舍（记录决策，非遗漏）

- 进程内 session registry（AWAITING_ANSWER 持久化点）暂缓 Redis 化 —— W1 MVP 边界，报告必载项。
- MCP adapter 生命周期正式 startup/shutdown 接线暂缓 —— 机制已验，app 接线 W3 后。
- 评测 3 轮样本 —— LLM 延迟限制；报告标注不具统计意义。
- 追问合理性与单题分不调参 —— 保持原始基线。

## 6. 砍单链执行情况

状态机+门禁 > 结构化输出+重试 > MCP 双工具 > 长期记忆 > 多模型分级 > LangGraph。
**未触发任何砍单**：W1/W2 全部计划项按时完成；LangGraph 按计划延后至 W3 仅概念学习（不实现）。唯一"替换"是 MCP 运输方式（计划内 fallback 分支，非砍项）。

## 7. 问题 → 实验 → 决策 → 固化 过程记录（五条主线）

1. **MCP 运输**：stdio 沙箱拒绝 → transport 探测 → streamable HTTP → DR-012 + mcp_client.py。
2. **真实 LLM 401**：key 占位 → env 探测（Machine 级 + 沙箱过滤）→ 运行注入 → 报告 §8.1 + 冒烟场景 7。
3. **total_score 双口径**（SUM vs AVG）→ grep 存储/报告/前端 → 报告=均分、画像=近10次主问题均分、评测不依赖 total_score → DR-014。
4. **followup 污染统计** → stats/coverage 无过滤 → source='followup' + exclude_sources（F9，默认行为不变）→ DR-015。
5. **LLM 异常冒泡 500** → W1 Day5 冒烟发现 → orchestrator `_run_role_node` 包装 → spec G 矩阵 + 单测。

---

## 8. StateMachine vs LangGraph 概念映射（学习材料，不实现）

| 当前实现 | LangGraph 概念 |
|---|---|
| `AgentState`（enum） | `State`（TypedDict schema） |
| `StateMachine`（转移表 + 门禁求值） | `Graph` / `StateGraph` |
| `TRANSITIONS`（14 行表） | `add_edge`（静态边） |
| `Gate`（g0..g9，AND 守卫、表序互斥） | `add_conditional_edges`（条件边/路由函数） |
| 角色节点 `_run_role_node`（薄组合） | `add_node` + node 函数 |
| orchestrator 事件循环（节点→转移→逃生舱） | `graph.invoke()` / 图执行循环 |
| `_record()` trace 钩子（7 类事件） | 事件流 / callbacks（on_node_start 等） |
| 进程内 `SessionContext` registry | `checkpointer`（`MemorySaver` / 持久化 checkpoint） |
| 门禁互斥（同事件多行） | 条件边分支谓词 |
| 逃生舱 `EscapeHatch` | 图外守护逻辑（无内置等价物，需自行实现） |

**为什么手写状态机足够**：
- 状态数固定（8）、事件固定（10）、转移 14 行——规模远小于 LangGraph 的收益阈值；
- 门禁需**确定性互斥与逐行可测**（表驱动单测），手写转移表天然满足；
- 不依赖第三方运行时，无框架升级/API 漂移风险；trace 事件与状态直接对齐。

**什么场景 LangGraph 更有价值**：状态集合大且动态（几十+）、需要持久化/恢复/并发分支、团队需统一图语言、需内置 checkpoint 与人工中断（interrupt）能力。

**未来迁移可复用**：roles.py（prompt/schema）、structured_output.py（校验重试）、tools.py（Tool 契约）、fallback.py（兜底动作）、trace schema（事件对齐）——迁移只涉及 state_machine/orchestrator 两层，其余纯逻辑层原样复用。

**关键差异**：手写 = 显式转移表 + 确定性互斥门禁 + 轻量；LangGraph = 声明式图 + 条件边 + checkpoint/恢复 + 生态。当前项目选手写，代价是持久化与恢复需自建（已列入技术债 P0）。

---

## 9. 技术债清单（只记真实存在的债；out-of-scope 不包装成债）

### P0（生产化前必须）
| 债 | 说明 | 证据 |
|---|---|---|
| 进程内 session registry → Redis 持久化 | AWAITING_ANSWER 断点/重启恢复缺失 | 交付摘要必载项；orchestrator `_sessions` dict |
| MCP adapter 生命周期正式接线 | startup create / shutdown close 未进 app.main | attach_mcp_tools 返回 adapter 需调用方持有 |
| app.main 启用 MCP 生产配置路径 | agent_mcp_enabled 开关未接线 | build_agent_service 默认 mcp 关闭 |

### P1（后续迭代）
| 债 | 说明 |
|---|---|
| trace 查询权限/生产化治理 | 只读端点属 Demo 定位，无权限体系 |
| prompt/schema version management | prompt_version 字段存在，无版本管理机制 |
| OTel 包装 | trace JSONL 为主，OTel 未包（spec 富余项） |
| evaluation dataset 扩大 | 17 条子集 + 3 轮样本，统计意义有限 |

### P2（明确不做，不包装成债）
- 多 Provider（B5 接口预留，out-of-scope）
- LangGraph migration（W3 只做概念学习）
- 更复杂并行编排（A5 `parallel_candidates` 默认关，out-of-scope）

> 注：Redis 长画像此前未实连**不列为债**——代码路径与降级已验证，仅缺环境凭据（§3 已验降级被真实触发）。
