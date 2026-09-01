# Agent 项目最终技术审查（角色：技术审查员 / 面试官模拟 / 架构 Reviewer）

> 日期：2026-09-01　|　对象：W1–W3 全部交付（commit `31ace60`..`1b2d3fc`）
> 方法：以代码 / trace / 测试 / 评测文档为证据的对抗式审查；重点查「文档表述 vs 实现事实」一致性。
> 基线：161 tests / smoke 27/27 / Redis 13/13 / trace assertions 全过。
> **审查结论：实现自洽、无阻塞性 bug；但存在 4 处"文档表述强于实现事实"的差距与若干表达风险，需在面试中精确化。**（不提出代码修改方案。）

---

## A. 当前项目最强面试卖点（基于真实实现，按强度排序）

1. **可测性 = 转移表数据化 + 门禁单测**：`TRANSITIONS` 是纯数据结构（14 行），23 个状态机单测逐行覆盖；真实会话 trace 流转合法率 100%（53/53）。"流程正确性可证明"是真实成立的，且能现场指代码。
2. **Trace 归因四象限字段齐全**：7 类事件 + `model/retries/validated/fallback_used/latency` 字段，评测 trace assertions 5 项全过。归因不是口头承诺，是字段级可审计。
3. **结构化输出防漂移设计（少见地严谨）**：Pydantic 模型为单一事实来源 → `model_json_schema()` 生成对外契约，jsonschema 与 pydantic 双方 strict 判定一致（防漂移单测 11 组）。"JSON Schema 当接口契约"（JD1-11）是真实落地且有测试背书。
4. **降级矩阵被真实故障验证过**：401（LLM 挂）→ G1-F/G4-F/逃生全链路；沙箱拒绝 MCP stdio → streamable HTTP 实测切换；Redis 无凭据 → 运行时真实降级。这些不是演练脚本编的，是环境逼出来的真实故障路径。
5. **3 周内完整覆盖 Agent 工程能力面**：状态机/门禁/工具契约/MCP/分级模型/结构化输出/重试/兜底/记忆/评测/trace 全部落地且有测试。广度和完成度是真实卖点。
6. **诚实边界本身是差异化**：out-of-scope 清单、评测不宣称赢、技术债 P0/P1/P2 分级——在"面试造火箭"语境下，讲得清的边界比吹牛更有说服力（前提：表述精确，见 C）。

## B. 最容易被面试官攻击的问题（按风险排序，均附证据）

| # | 攻击点 | 证据 | 风险 |
|---|---|---|---|
| B1 | **"生产可用吗？"（JD1 岗位职责原文"实现并推进到生产可用"）** | 进程内 session（重启即丢）；MCP 未正式接线（app.main 无 attach_mcp_tools）；trace 无权限；单 worker 演示级 | **极高**——最大软肋，必须主动声明边界 |
| B2 | **"预算超限会逃生吗？"** | `orchestrator.py:378` `over_budget=False` **硬编码**——附录 C 声称的预算逃生从未接线 | 高（文档 vs 实现不一致，被抓即露馅） |
| B3 | **"难度调整是确定性的吗？"** | `state_machine.py:136` 门禁只校验 enum，**不校验是否等于目标难度**——LLM 可无视"目标难度：easy"返回 hard，照样过门禁 | 高（"确定性/自适应"表述过强） |
| B4 | **"对照评测里 legacy 和 agent 用的是同一模型吗？"** | 评测脚本：legacy=`LLMClient()`（settings.bailian_model=qwen3.8-max），agent=gateway（qwen-turbo/plus）——**模型混淆变量**；"agent 更严格"结论被模型差异污染 | 高（评测设计硬伤，报告未充分标注） |
| B5 | **"你的 LLM 会自己选工具吗？"** | 编排层**显式按角色调用**工具（orchestrator 直接调 kb_retrieve），非 LLM 自主 tool-calling loop | 中高（Tool Use 语义需精确：是"确定性工具层"不是 LLM 驱动） |
| B6 | **"结构化输出成功率 / 重试率 / 兜底率是多少？"** | **无此类聚合指标**——只有单测保证机制，无真实统计 | 中高（"可归因"缺配套度量） |
| B7 | **"MCP 和第三方 MCP server 互通验证过吗？"** | 只测了自建 server↔自建 client（内存/HTTP），未做异构互操作 | 中（如实声明即可） |
| B8 | **"单题分方差 0 说明什么？"** | agent [2,2,2] var=0：三题同分——**评估区分度存疑**（半真实模板输入 + 样本 3） | 中（须承认样本/输入限制） |
| B9 | **"生产模式的成本统计呢？"** | `GenerationResult.cost=0.0` 占位；成本经 monitor 记录但**无按 light/heavy 级别聚合**（决策 3"按级别成本统计"未落地） | 中 |
| B10 | **"线上 LLM 慢（>30s）怎么办？"** | tenacity 重试 3 次（指数退避）→ 节点兜底；但无聚合告警 | 中（机制在，观测缺） |

## C. 存在夸大风险的表述（逐条校准）

| 文档/话术表述 | 实际实现 | 校准后说法 |
|---|---|---|
| "自适应难度调整" | 难度是**软约束**：prompt 注入目标难度，LLM 输出仅校验 enum（B3） | "难度经 prompt 目标注入 + 门禁枚举校验；不强制模型遵循目标（如实）" |
| "全局逃生舱（预算超限→收尾）" | over_budget 恒 False（B2） | 逃生舱 6 项已生效，预算项未接线 |
| "MCP 双工具" | 能力+测试验证，**app.main 未接线**（生产 agent 模式跑本地工具） | "MCP 协议链路已验证（含回退）；生产接线是 P0 债" |
| "多模型分级 + 成本统计" | 分级✅；成本按模型名记录✅；按级别聚合❌（B9） | 分开说：分级已落地，成本聚合未做 |
| "可归因" | trace 字段齐全✅；无聚合指标/告警（B6） | "可逐会话审计；跨会话度量与告警是 P1" |
| "agent 评估更严格稳定" | 模型混淆（B4）——不能把架构差异与模型差异分开 | 撤回或重述："两者模型不同，差异不可归因" |
| "生产可用"（若被 JD1 逼问） | 演示级 + P0 债清单 | 主动讲边界：哪些演示级、哪些生产化路径 |
| "Tool Use"（若被理解成 LLM 自主调用） | 确定性工具层，编排层按角色调用 | 明确："确定性工具调用（JD1-6），非 LLM 自主 tool loop" |

**原则**：所有"强表述"先自降一档再说；被追问细节时先给"实现事实"，再给"为什么这样设计"。

## D. 需要重点熟悉的代码路径（面试被追问时能秒定位）

1. `app/services/agent/state_machine.py` —— `TRANSITIONS`（14 行）、`GateContext`、`g1_question`/`g9_followup_trigger`/`g5_*`、`EscapeHatch.check`。
2. `app/services/agent/orchestrator.py` —— `submit_answer`（A6 契约：追问/再答/合并评估）、`_step`（非法转移拒绝）、`_run_role_node`（LLM 失败→兜底包装）、`_summarize`（画像批量写）、**`_escape_reason`（over_budget=False，B2）**。
3. `app/services/agent/structured_output.py` —— `generate_structured`（3 次总尝试）、`build_feedback_prompt`（错误回填）、`extract_json`。
4. `app/services/agent/roles.py` —— 三模型 + `_schema_instruction`（防漂移设计锚点）。
5. `app/services/agent/tools.py` —— `Tool` 契约、`ToolRegistry.execute`（schema/超时/policy）、`make_eval_rules_tool`。
6. `app/services/agent/model_gateway.py` —— `_chain`（降级链）、`BailianAdapter`（不绕过 LLMClient）。
7. `app/services/agent/mcp_client.py` —— `attach_mcp_tools`（回退语义）、transport 切换。
8. `app/services/agent/profile_store.py` —— `compute_session_profile_patch`（F8 口径）、`make_profile_store`（降级）。
9. `app/services/agent/trace.py` —— `TraceRecord.validate`、保留策略。
10. `tests/services/agent/` —— 状态机 23 / 结构化 16 / 工具 / gateway 9 / mcp 6 / profile / orchestrator 集成（含跨会话）。

## E. 模拟 10 个高级 Agent 面试追问（含应答方向）

1. **"你的系统是 Agent 还是 Workflow？LLM 到底做了哪个不可替代的决策？"**
   方向：结构决策（转移/门禁/降级）确定性；内容决策（出题文本/追问文本/评分理由）LLM；"不可替代"= 内容生成 + 质量由门禁兜底。
2. **"你说难度自适应，LLM 输出 hard 但你要 easy，系统会怎么做？"**
   方向：诚实承认是软约束（B3），讲为什么（避免强校验破坏生成、当前用 prompt 目标+枚举门禁）；未来可加"难度合规门禁"。
3. **"你的逃生舱触发过几次？budget_exceeded 出现过吗？"**
   方向：诚实——over_budget 未接线（B2）；触发过的只有 consecutive_failures（冒烟/演示）；这是文档-实现差距，已列入审查。
4. **"legacy 和 agent 评测用的模型一样吗？"**
   方向：如实——不同（qwen3.8-max vs turbo/plus），结论不可归因（B4）；正确口径是"架构+模型联合差异"或先统一模型再比。
5. **"你的 Tool Use 和 Claude Code 的 tool calling 是一回事吗？"**
   方向：不是——我们是确定性工具层（JD1-6），编排层按角色显式调用；不伪装成 LLM 自主选工具。
6. **"结构化输出的真实成功率是多少？"**
   方向：无聚合统计（B6）；机制有单测，真实成功率待观测；如果要答，可用 demo 观察（本次 demo 评估为 LLM 分、非兜底）。
7. **"重启服务，进行到一半的面试会怎样？"**
   方向：进程内 session 丢失，`end()` 可从 store 重建最小上下文兜底，但断点恢复缺失——P0 债，Redis 持久化是明确路径。
8. **"MCP 你验证过和别的 server 互通吗？为什么线上没启用？"**
   方向：只做了自验证（协议链路 + 回退）；线上未接线是 P0；讲 transport 取舍实测（stdio 被拒→HTTP）。
9. **"单题分方差 0，你信你的评估吗？"**
   方向：不信（样本 3 + 模板输入 + 模型混淆）；评估区分度需要真实回答 + 更大样本；这也是评测报告的自我批评。
10. **"如果 JD 明确要 Java 生产实现，你 3 周能交付什么？"**
    方向：讲移植路径（转移表/工具注册/schema 是纯数据结构）——但诚实：3 周只够 Python 侧验证 + Java 骨架，生产化（持久化/权限/观测）是更长周期；不吹"3 周交付 Java 生产"。

---

## 附：审查发现汇总（文档 vs 实现一致性）

| # | 发现 | 证据 | 级别 |
|---|---|---|---|
| F1 | 附录 C"预算超限→逃生"未接线（over_budget 恒 False） | `orchestrator.py:378` | 文档-实现差距（非阻塞） |
| F2 | 难度调整是软约束，与"确定性/自适应"表述不符 | `state_machine.py:136` | 表述过强 |
| F3 | MCP 生产链路未接线，与"MCP 双工具"表述不符 | `app/main.py` 无 attach | 表述过强 |
| F4 | 对照评测存在模型混淆变量，报告结论需重述 | 评测脚本（legacy=qwen3.8-max vs agent=turbo/plus） | 评测严谨性 |
| F5 | 无结构化输出成功率/兜底率聚合指标，"可归因"缺配套度量 | 全仓无此类统计 | 度量缺失（P1） |
| F6 | 成本按级别聚合未落地（决策 3"按级别成本统计"） | `model_gateway.py` GenerationResult.cost=0.0 | 部分落地 |

以上均不构成阻塞性 bug；按角色要求不提出代码修改方案。
