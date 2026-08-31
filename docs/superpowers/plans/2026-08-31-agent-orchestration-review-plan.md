# Agent 编排化改造 — Design Review & MVP 实施计划

> 评审对象：`docs/superpowers/specs/2026-08-31-agent-orchestration-refactor-design.md`（2026-08-31 定稿，三轮 grill）
> 评审日期：2026-08-31　|　评审性质：架构 Review / 风险检查 / MVP 范围确认 / 实现指导
> 结论：**方向正确，可进入实现；但 spec 需补技术附录，里程碑排布需修正（W3 优先级倒置），其余按 B 项调整后开工。**
>
> **状态更新（2026-08-31）**：B1 已由 `docs/superpowers/specs/2026-08-31-agent-orchestration-refactor-impl-spec.md`（实现级 Design Spec v2）完成；B10 已由用户提供 3 份 JD 并完成拆解与映射（见 v2 §2）。v2 待确认后进入实现。

---

## A. Design Review

### A1. 总体判断

设计方向与四条核心决策（不自由 ReAct、不堆 Multi-Agent、RAG 作 Tool、五大优先项）**完全一致**，且与项目现状咬合良好：

- 已有资产全部可复用：`RetrievalFacade`（MCP 封装接缝现成）、`TopicTracker`（薄弱点/覆盖率，画像记忆的数据源）、`session_cost`（成本统计自动接线）、`eval_interview_subset.json`（17 条：出题形态 8 + 评价形态 9）、`observability.py`（OTel 可选旁路）、`interview_agent.py`（现存最小 Planner，仅骨架，需重写为真状态机）。
- "确定性状态机 + LLM Role Node" 是业界主流的生产型 Agent 架构（对照 LangGraph 的 StateGraph 思路的手写版），面试可讲性高：状态机、门禁、结构化输出、重试、工具调用、归因，六样东西全是 JD 高频词。
- 风险不在方向，在**执行细节缺失**：spec 目前是"概念 spec"，未达到 PROCESS.md §1.1 对 Spec 的要求（状态/事件/转移表、模块清单、接口契约、验收标准、风险清单均未定义）。

### A2. 与 Agent Developer 岗位预期的匹配度

按 spec §1 的 JD 职责映射表逐条核对（**前提：JD 原文未随 spec 提供，映射表不可审计，见 B10**）：

| JD 职责（映射表声称） | 设计覆盖度 | 评价 |
|---|---|---|
| 多阶段状态机、阶段门禁 | 有决策，无定义 | 需要附录补状态/事件/转移表/门禁/全局上限（B1/B7） |
| 角色定义、按阶段注入知识、结构化输出+重试 | 完整 | §4.1 方案正确，最不该砍（C5） |
| 确定性工具层、MCP 客户端 | 有决策，无契约 | 需定义工具注册表 schema 与 MCP 降级路径（B4/B6） |
| 统一模型接入、分级调用 | 部分 | turbo/plus 分级可行；双供应商完整版超范围（B5） |

**缺口（JD 可能涵盖但设计未覆盖的 Agent 工程能力）**：输入/输出 guardrails（长度、安全过滤）、会话状态持久化与断点恢复（SSE 断流/服务重启后状态机状态是否落 Redis）、工具超时与错误上报契约、agent 级评测（流程级 trace 断言，非仅 RAG 指标）、prompt/schema 版本化（trace 里记录版本号）、统一降级矩阵（RAG 挂 / LLM 挂 / 工具超时 / schema 校验失败各有确定性兜底）。其中**降级矩阵**与**trace 断言**影响交付质量，建议进 MVP；guardrails/版本化/prompt 版本管理可延后。

### A3. 架构一致性

- **分层**：`app/services/agent/` + DI RetrievalFacade + Law of Layers —— 正确，与 SERVICES_LAYER 决策所有权一致。
- **切换接缝**：API 层经 `app.main` 单例取 `interview_service`（已核实 `app/api/interview.py:31-37`）。`interview_mode=legacy|agent` 最省事的落点是 **app.main 装配期工厂**：按 settings 选择 legacy 或 agent 服务实现，API 层与前端**零改动**。spec 未写明这个接缝（B2）。
- **状态机**：spec 只给了"enum + 转移表 + 门禁函数"一句话，未给状态/事件/转移表本身。出题→追问→评估→难度调整→总结 五个阶段必须落成显式表（B1）。
- **成本/限流**：LLMClient 已接 `monitor` → `session_cost`（已核实 monitor.py:66），agent 节点若复用 LLMClient 则成本统计自动生效，**无需新造**（B11 复用清单）。
- **对照开关**：`enable_*` 开关惯例已存在，`interview_mode` 沿用该惯例（C7）。
- **trace**：JSONL 每 session 一文件，schema 已在 §4.3 列出字段；需补路径/保留策略/与 OTel 的关系（B12）。

### A4. 过度设计检查

| 候选 | 判断 | 处理 |
|---|---|---|
| MCP 双工具 | 不过度（JD 硬指标），但有环境风险（Windows + stdio 子进程） | 保留，必须带本地工具降级，2 天上限（B4） |
| 多模型"完整版"双供应商 | **过度** | 降为"接口预留+策略表"为基线；turbo/plus 分级（同一 API 底座）为默认实现；跨供应商完整适配延后（B5） |
| LangGraph 完整复刻 | **过度**（产品价值低，纯话术项） | 降为 stretch spike，默认走"读源码+对应关系讲解"（B3） |
| 候选人画像长期记忆 | 不过度，但要做薄 | 复用 TopicTracker + 一个小 profile schema；禁止造"记忆子系统"（摘要管线等）；可降为会话内画像 |
| 结构化输出"提示词+jsonschema+回填重试" | 正确范围 | 不再加 function-calling 强约束 / grammar 解码 |
| 状态机"enum+转移表+门禁"手写 | 正确范围 | 不引状态机库、不做并行状态/嵌套机 |
| trace JSONL | 正确范围 | OTel 仅富余再包（已有 observability.py，成本低，可顺手） |

**结论：设计总体不过度；三处需要收敛 —— 双供应商、LangGraph 复刻、记忆子系统。**

### A5. 优先级核对（按用户四大优先 + 四问）

- State Machine ✅ **必须**（W1，含门禁与全局上限）
- Tool Calling ✅ **必须**（W1 本地函数调用 → W2 MCP 化）
- Structured Output + Retry ✅ **必须**（W1；spec 自己标注"最不该砍"，认同）
- Trace ✅ **必须**（W1 就带最小完整 schema，别等 W2）
- Evaluation ✅ **必须**（W2 下对照跑数；但 trace 断言应从 W1 随 trace 一起长出来）
- **MCP：符合当前优先级**（JD 亮点），但必须带本地工具降级，严格 2 天。
- **多模型：部分符合**。分级调用（turbo/plus）+ 成本统计符合；双供应商完整适配**不符合**当前优先级，延后。
- **Memory：符合**，但默认接受降级路径（会话内画像）；跨会话画像放 W2 下，做薄。
- **LangGraph：不符合当前优先级**。它是"话术道具"不是"交付物"，应延后为 W3 stretch spike。

### A6. 风险清单（按严重度）

1. **【高】W1 超载**：状态机 + 3 角色 prompt + 结构化输出重试 + 本地工具 + trace + 切换接缝，40h 内要出"最小闭环"——必须砍到不能再砍（见 D）。
2. **【高】MCP 在 Windows/stdio 的环境风险**：进程生命周期、SDK 稳定性；需 W1 决策运输方式并写死本地降级。
3. **【中】前端契约假设未确认**：设计未提前端；若 agent 模式 API 契约与 legacy 不一致，前端改动会吃掉时间。**默认零前端改动**（B2）。
4. **【中】状态机死循环/卡死**：门禁条件永不满足、评估一直重试失败——需要全局轮次上限与逃生舱（B7）。
5. **【中】对照跑数结果不佳的心态风险**：legacy 已有多轮优化，agent 未必赢。"有意识地在测"原则正确，但要防"为演示调参"。
6. **【低】画像"历史正确率"口径**：评分来源（LLM 分 vs 规则分）不定义则不可审计（B8）。
7. **【低】trace 含用户回答内容**：demo 场景注意展示脱敏。

---

## B. 必须调整项

1. **B1｜spec 补技术附录**：状态机（状态/事件/转移表/门禁/全局上限）、模块与文件清单、接口契约（工具 schema、Role 节点 I/O、trace schema）、验收标准（量化）、风险清单。不补则无法进入实现评审。
2. **B2｜定义 legacy/agent 接缝**：`interview_mode` 在 `app.main` 装配期按 settings 选服务实现；agent 模式复用 `start/answer/end/report` 契约；**默认零前端改动**，如有例外需显式声明。
3. **B3｜修正 W3 优先级倒置**：先"演示打磨 + 话术训练"，LangGraph 复刻降为 stretch（默认走"读源码 + 对应关系讲解"）。砍单链顺序本身正确，是里程碑排布与之矛盾。
4. **B4｜MCP 降级写死**：MCP 不可用时 agent 必须能用本地工具注册表跑完整流程（W1 的本地函数调用即降级形态）；W1 决策运输方式（stdio / streamable HTTP）并写明 Windows 风险。
5. **B5｜多模型降级基线化**：把"接口预留 + 策略表"从砍单链提升为**默认方案**；turbo/plus 分级（同一 API 底座）为默认实现；跨供应商完整适配列入 stretch。
6. **B6｜工具调用契约与超时**：定义 tool registry（name / description / input schema / output / 超时 / 错误上报）；agent 每轮 2–3 次 LLM 调用，延迟与成本显著上升，复用 `session_cost`（已自动接线）并在状态机层加节点级超时。
7. **B7｜全局逃生舱 + 统一降级矩阵**：全局轮次上限、连续失败上限、总时长上限（不依赖 LLM）；降级矩阵覆盖：RAG 挂 / LLM 挂 / 工具超时 / schema 校验失败，各有确定性兜底。§4.1 的"评估失败→题目作废"是矩阵的**一个实例**，要泛化。
8. **B8｜画像数据口径**：`历史正确率` 评分来源必须明确（LLM 评估分 vs 规则分）、schema 与更新时机（每答 vs 会话末批量）写明；否则"正确率"不可审计。
9. **B9｜评测补流程级断言**：除 recall@3 / MRR + 人工追问合理性外，加 trace 断言（状态流转合法、重试次数、schema 失败→兜底触发、工具耗时记录），把 Evaluation 从"指标"升级为"可归因审计"。
10. **B10｜附 JD 原文**：spec §1 映射表基于未提供的 JD，无法审计。把 JD 关键条目原文（或文件链接）贴入 spec。
11. **B11｜显式复用清单**：声明复用 RetrievalFacade / TopicTracker / session_cost / monitor / tenacity / eval_metrics，防止重复造轮子。
12. **B12｜trace 落盘细节**：路径（`data/traces/{session_id}.jsonl`）、保留策略（保留最近 N 个）、与 OTel 关系（JSONL 为主，OTel 可选旁路）。

---

## C. 保留项

1. 确定性状态机为主，LLM 只在角色节点内（决策 1）——与"不改为自由 ReAct"一致，是面试主论点。
2. 不做 Multi-Agent（决策 2）——保留，不为展示堆砌。
3. RAG 作为 Tool 而非主体（决策 3）——保留；RetrievalFacade 是正确接缝。
4. 纯 Python 实现、不做 Java 移植（决策 4）——保留，话术钩子有效。
5. 结构化输出 = 提示词约束 + 本地 jsonschema 校验 + 回填重试最多 3 次（§4.1）——最不该砍。
6. 评估节点 3 次失败 → 确定性兜底"题目作废跳下一知识点"（§4.1）——保留并泛化为降级矩阵（B7）。
7. legacy vs agent 对照组 + `interview_mode` 开关（§4.2）——保留（接缝见 B2）。
8. JSONL trace 每 session 一文件 + 归因演示（§4.3）——保留；OTel 仅富余再包。
9. 评测沿用 17 样本子集 + recall@3 / MRR + 人工追问合理性（§4.4）——保留（补断言见 B9）。
10. 砍单链优先级排序（状态机+门禁 > 结构化输出+重试 > MCP 双工具 > 长期记忆 > 多模型分级 > LangGraph）——顺序保留，里程碑排布修正（B3）。
11. 新分支 `agent-dev`、main 冻结、编排层放 `app/services/agent/`、DI RetrievalFacade、Law of Layers（决策 7 / §6）——保留。
12. 面试话术三条主线（开场定位 / 归因 trace / 取舍）——保留，且表达训练要提前启动（D-W3 前）。
13. 配置一律走 config.py + .env（§6）——保留（agent 配置并入 settings：max_retries、trace 路径、模型分级表等）。
14. "指标不需要赢，需要有意识地在测"——保留，防对照结果不佳时乱改。

---

## D. MVP Implementation Plan（3 周 × 8h）

> 遵守 PROCESS.md §1：Spec → Review → 实现 → Unit → Integration → 真实 LLM 评估 → Report → Commit（一行为一 commit）。
> 禁止项：LangGraph 不先于演示打磨；双供应商不做完整适配；无 B2 确认不做前端改动；砍单链执行不犹豫。

### 周 0（半天～1 天）：分支与规格补全
1. `git checkout -b agent-dev`（从 main 冻结点切出；设计文档先 commit 到 agent-dev）。
2. 按 B1 补 spec 技术附录：状态机定义（5 阶段状态 + 事件 + 转移表 + 门禁 + 全局上限）、模块清单、接口契约、验收标准、风险清单；按 B10 附 JD 原文。
3. 按 B2 确认接缝：`interview_mode` 装配期工厂 + 零前端改动假设。
4. 产出本计划的落地版：里程碑排布修正（B3）。

### W1（必须，40h）：最小闭环骨架
| 日 | 任务 | 出口 |
|---|---|---|
| 1 | `app/services/agent/` 骨架：`state_machine.py`（enum+转移表+门禁+全局上限）、`trace.py`（JSONL 最小完整 schema） | 状态机单测全绿；trace 空跑可写 |
| 2 | `roles.py`（出题人/追问者/评估官 3 角色 prompt + Pydantic schema）+ `structured_output.py`（JSON 提取 + jsonschema 校验 + 错误回填重试 ≤3 次） | 校验/重试单测（mock LLM） |
| 3 | `tools.py` 本地工具注册表：`retrieve`（包 RetrievalFacade）/ `query_profile` / `mock_resume`；定义 schema+超时 | 工具契约文档 + 单测 |
| 4 | `orchestrator.py` 运行循环 + `agent_service.py`（对外 start/answer/end/report，DI RetrievalFacade/TopicTracker）+ 降级矩阵（B7）+ 逃生舱 | 集成测试：全流程 mock 跑通 |
| 5 | `interview_mode` 装配工厂接线（B2）+ 3 角色真实 LLM 联调 + trace 检查 | **周末验收：agent 模式最小闭环 demo**（出题→回答→评估→难度调整→总结，全程 trace，legacy 可切换） |

**W1 验收锚点**：状态机单测 + 重试/兜底单测 + 集成测试全绿（PROCESS §1.2）；真实 LLM 跑通闭环；trace 文件字段完整。

### W2（40h）：闭环完整化 + 对照
- **2上（20h）· MCP + 多模型分级**：
  - MCP 化：`RetrievalFacade` → MCP 工具 + 1 个非 RAG 工具（mock 简历库）；W1 本地注册表保留为**降级路径**；W1 已定运输方式；**严格 2 天上限**，超时砍到"一个 MCP 工具 + 本地降级"。
  - 多模型：统一接口 + `turbo（轻任务）/ plus（生成）` 分级 + 成本统计（复用 session_cost）+ 策略表（默认）；跨供应商只留接口。
- **2下（20h）· 画像记忆 + 评测对照**：
  - Memory：`profile_store.py`（Redis，schema：薄弱点/等级/历史正确率，复用 TopicTracker 数据），会话末批量写；降级=会话内画像。
  - Eval：17 样本 legacy vs agent 对照（复用 eval_metrics）+ **trace 断言**（B9）；报告落 `docs/evaluation/`。
- **周末验收**：对照表 + 归因 trace 演示 + 画像跨会话影响难度。

### W3（40h）：打磨与表达（LangGraph 靠后！）
1. **演示打磨（优先）**：边界场景演练（LLM 挂/RAG 挂/连续失败→逃生舱）；trace 查看入口（只读端点 `/api/agent/traces/{session}` 或直接演示 cat 文件）；话术三条主线 + 归因逐字段讲解脚本（3–5 个 demo 脚本）。
2. **LangGraph spike（stretch，默认读源码+对应关系）**：手写状态机 vs LangGraph state/channel/checkpoint 映射表 + 一页总结；**仅在演示与话术打磨完成后**才做"完整复刻"。
3. **收尾**：SERVICES_LAYER.md 契约更新（Layer 契约 DoD）、DECISIONS.md 新增 DR（MCP 选型 / 确定性编排决策）、技术复盘（docs/evaluation/ 或复盘文档）、合入评审。

### 必须 / 延后 / stretch 一览
| 类别 | 模块 |
|---|---|
| **必须（W1）** | 状态机+门禁+逃生舱 · 结构化输出+重试+确定性兜底 · 本地工具注册表 · trace JSONL · legacy/agent 切换 · 最小闭环 demo |
| **必须（W2）** | MCP 双工具（带本地降级）· turbo/plus 分级+成本 · 画像记忆（可降级会话内）· 17 样本对照 + trace 断言 |
| **延后（超 3 周）** | 跨供应商多模型完整适配 · OTel 包装 · guardrails/内容审查 · prompt 版本化 UI · 成本看板 · 非 mock 简历解析工具 |
| **stretch（W3 富余）** | LangGraph 完整复刻（默认"读源码+讲解"） |

### 风险对冲
- MCP 失败 → 本地工具注册表照常跑（W1 已具备）。
- W1 时间爆 → 砍 trace 富余字段与第三个角色（追问者合并进出题人），保留"评估官+出题人"双角色闭环。
- 对照跑数 agent 不赢 → 用 trace 归因讲"差异在哪"，不调参硬凹。
- Windows 下 MCP 子进程问题 → 改 streamable HTTP 或进程内 server，本地降级兜底。
