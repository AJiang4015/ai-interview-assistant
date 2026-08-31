# Agent 编排化改造 — 实现级 Design Spec（v2）

> 日期：2026-08-31　|　状态：**实现就绪（待确认）**　|　前身：`2026-08-31-agent-orchestration-refactor-design.md`（概念 spec，保留为决策史）
> 评审结论：`docs/superpowers/plans/2026-08-31-agent-orchestration-review-plan.md`（本 spec 已采纳其 B2–B12 全部调整；B1 即本文档本身；B10 已附 JD）
> 生效规则：本文档为唯一实现依据。**在本文档确认前不生成代码。**

---

## 1. 决策基线（继承 + 调整采纳）

继承原 spec 七项决策：①确定性状态机为主，LLM 仅在角色节点内；②MCP 真实现；③多模型分级调用；④纯 Python，不做 Java 移植；⑤LangGraph 时间盒；⑥候选人画像长期记忆；⑦新分支 `agent-dev`、main 冻结、`app/services/agent/`、Law of Layers。

采纳 Review 调整：
- **B3**：W3 先演示打磨 + 话术训练，LangGraph 降为 stretch（默认"读源码 + 对应关系讲解"）。
- **B5**：多模型基线 = 统一接口 + `qwen-turbo/qwen-plus` 分级 + 成本统计 + 策略表；跨供应商仅预留接口。
- **B4**：MCP 必须带本地工具注册表降级；W1 定运输方式。
- **B7**：全局逃生舱 + 统一降级矩阵（附录 C / G）。
- **B8**：画像口径：历史正确率 = 近 N 次评估分均值（LLM 分，兜底规则分计入并打标）。
- **B9**：评测含 trace 断言（附录 I）。
- **B2**：`interview_mode` 在 `app.main` 装配期工厂选 legacy/agent 实现，复用 start/answer/end/report 契约，默认零前端改动。
- **B6/B11/B12**：工具契约 + 复用清单 + trace 落盘细节见附录 F/E/H。

**W0 决策冻结（2026-08-31，详见 `docs/superpowers/plans/2026-08-31-agent-orchestration-w0-mapping.md`）**：OPEN-1..6 与补充发现 F7/F8/F9 全部确认。总原则（用户定调）：**Agent 可以新增语义，但尽量不破坏已有数据模型与 API；需要兼容时通过小的、默认行为不变的扩展点解决。** 接口约束已并入对应附录（E1/E5/E6、A6、F、I）。

---

## 2. JD 能力要求拆解与覆盖映射（3 份 JD 合并）

> 覆盖标注：🟢 已覆盖（设计/存量资产直接命中）｜🟡 部分覆盖（需新增或靠话术转译）｜🔴 未覆盖（明确不做，需话术说明）｜— N/A（非工程能力）

### 2.1 JD1 — 核心 Agent 系统实现工程师

| ID | 能力要求（原文浓缩） | 可验证形式 | 证据落点 | 覆盖 |
|---|---|---|---|---|
| JD1-1 | 编排层：多阶段流程状态机 | 代码 + 转移表单测 | 附录 A `state_machine.py` | 🟢 |
| JD1-2 | 编排层：阶段门禁 | 门禁函数 + 门禁单测 | 附录 B | 🟢 |
| JD1-3 | 编排层：变更影响传播 | 上下文传播链显式化（评估→画像/难度→下一题 prompt；画像→下次会话出题） | 附录 A §A4 + `profile_store` | 🟡 |
| JD1-4 | 编排层：多方案并行执行 | 检索侧多路并行现成（RRF 融合）；编排侧并行（如双候选题选优）列为 stretch 开关默认关 | 存量 RRF + 附录 A §A5 | 🟡 |
| JD1-5 | 角色层：角色定义 / 按阶段注入领域知识 / 结构化输出约束与失败重试 | `roles.py` + `structured_output.py` | 附录 E §E3 | 🟢 |
| JD1-6 | 工具层：规则校验 / 参数汇算 / 外部数据检索客户端(MCP) | `eval_rules`（规则校验+参数汇算示例）+ MCP 桥接 | 附录 F | 🟢 |
| JD1-7 | 模型层：多模型供应商与分级调用策略 | 统一接口 + turbo/plus 分级 + 策略表 + 成本 | 附录 E §E5 `model_gateway` | 🟡 |
| JD1-8 | 原型验证后 Java 生产实现 | **不做**（决策 4）；话术讲移植路径（转移表/工具注册为纯数据结构） | 话术主线 3 | 🔴 |
| JD1-9 | 统招本科，计算机相关 | — | 简历 | — |
| JD1-10 | Python 独立承担 / Java 读写 / 数据结构与调试 | 项目存量代码 + pytest + 复盘材料 | 存量资产 | 🟢 |
| JD1-11 | 把 JSON Schema 当接口契约 | 结构化输出 Schema + 工具 Schema 双处使用 | 附录 E/F | 🟢 |
| JD1-12 | Agent 产品深度使用；理解 Loop/Tool Use/MCP/结构化输出/上下文工程 | 工程侧：Loop=事件循环、Tool Use=工具契约、MCP=W2、结构化输出=W1、上下文工程=注入/裁剪；产品使用靠话术 | 附录 A/E/F | 🟡 |
| JD1-13 | 归因：模型/流程/数据/评估 | trace 逐字段归因演示 + legacy/agent 对照 | 附录 H + 话术主线 2 | 🟢 |
| JD1-14 | 认同确定性技术路线 | 决策 1 即主论点 | §1 | 🟢 |
| JD1-F1 | 加分：生产环境 Agent/LLM 经验 | 本项目即 LLM 应用生产实践（FastAPI+Redis+外部 API 部署） | 存量资产 | 🟡 |
| JD1-F2 | 加分：LangGraph/AgentScope 实践或源码 | W3 spike：读源码 + 手写 vs LangGraph 概念映射表 | 里程碑 W3 | 🟡 |
| JD1-F3 | 加分：LLM 微调 / 指令数据构造 | eval_testset 生成器 = 轻量指令数据构造证据 | 存量 `eval_testset.py` | 🟡 |
| JD1-F4 | 加分：小团队独立推进完整系统 | 本项目本身 | 复盘材料 | 🟢 |
| JD1-W1 | 基本功：代码质量、调试排查 | 项目 + PROCESS/PROBLEM 体系 | 存量资产 | 🟢 |
| JD1-W2 | 独立交付 | 本项目闭环（demo + 评测 + 复盘） | 里程碑 | 🟢 |
| JD1-W3 | 学习速度 | — | 话术 | — |
| JD1-W4 | AI 工具使用、对产出负责、说清判断 | trace 归因佐证"哪些判断是自己做的" | 话术主线 2 | 🟡 |

### 2.2 JD2 — 桌面办公 Agent

| ID | 能力要求（原文浓缩） | 可验证形式 | 证据落点 | 覆盖 |
|---|---|---|---|---|
| JD2-1 | 分层架构：规划调度/记忆管理/工具网关/感知执行/结果校验 + 模块通信规范 + Skill/MCP 扩展 | 本项目分层（编排/角色/工具/模型）+ 记忆(profile) + 工具网关(registry) + 结果校验(structured)；感知执行/Computer-Use 无；Skill 未覆盖（MCP 工具 = Skill 等价物话术） | 附录 D/E/F | 🟡 |
| JD2-2 | 架构取舍（轻量 vs 长任务）+ 客户端/服务端混合部署 | 浏览器 → 后端 → 云端 LLM 即混合形态雏形；取舍话术 | 话术 + 架构 | 🟡 |
| JD2-3 | LLM 选型 / 成本评估 / 调用链路 / Prompt 工程 / 长记忆 / 上下文裁剪 / 容错重试降级 | 选型=分级策略表；成本=`session_cost`；链路=`model_gateway`；Prompt=`roles`；长记忆=`profile_store`；**上下文裁剪=附录 E §E4（新增）**；容错重试降级=附录 G | 附录 E/G | 🟢（补 E4 后） |
| JD2-4 | RAG 整套工程落地（向量库/召回/降幻觉/稳定准确） | 存量全套 RAG + Part B 消融 + 评测；按决策 3 作为工具 | 存量资产 | 🟢 |
| JD2-5 | 方案选型：RAG / 知识图谱 / Wiki | RAG + 知识树有；图谱/Wiki 话术选型思考 | 存量 + 话术 | 🟡 |
| JD2-6 | Computer-Use 桌面执行链路（截图/OCR/窗口/键鼠） | **不在本项目范围**；工具层抽象保留扩展点（Tool 契约不限定实现） | §14 | 🔴 |
| JD2-7 | 全链路排查：死循环/规划失败/工具调用异常 | 逃生舱 + 降级矩阵 + trace + PROBLEM 体系 | 附录 C/G + 存量 | 🟢 |

### 2.3 JD3 — 跨境电商 AI Agent 平台

| ID | 能力要求（原文浓缩） | 可验证形式 | 证据落点 | 覆盖 |
|---|---|---|---|---|
| JD3-1 | Agent 平台前后端/客户端/大模型融合架构与编码 | 后端(FastAPI)+前端(SSE SPA)+LLM 融合有；客户端（桌面/移动）无 | 存量 + 话术 | 🟡 |
| JD3-2 | 业务流数字化/模块化/Agent 化 | 面试业务流 Agent 化（出题→评估→调整）即案例 | 话术转译 | 🟡 |
| JD3-3 | 人机协作模式（不是 0/1 博弈） | 会话式天然 HITL：用户作答→agent 调整；显式 HITL（如人工确认难度）未做 | 话术 | 🟡 |
| JD3-4 | 全栈工程底座（算法/数据结构/网络/数据库 + 一门主流语言） | FastAPI + Redis + SQLite + FAISS + Python | 存量资产 | 🟢 |
| JD3-5 | Harness 工程能力：Prompt 边界 / Agent 设计模式 / Harness / 环境感知 / 评测对齐 | 结构化输出+重试=Prompt 边界；状态机=设计模式；trace=Harness 观测；评测=附录 I；上下文注入=环境感知 | 附录 | 🟢 |
| JD3-6 | 热情/自主/务实/独立思考 | — | 话术/复盘 | — |

### 2.4 覆盖结论摘要

- 🟢 已覆盖：15 项（状态机、门禁、角色+结构化输出、工具层、确定性路线、归因、RAG 工程、排查体系、Harness/评测等）
- 🟡 部分覆盖：15 项（变更影响传播、多方案并行、多供应商、上下文裁剪、混合部署、人机协作等——多数已在本 spec 附录转成显式机制或话术钩子）
- 🔴 未覆盖：2 项，均为**有意不做**并已有话术：JD1-8 Java 生产实现（决策 4 明确）、JD2-6 Computer-Use（明确 out of scope，工具层留扩展点）
- — N/A：2 项（JD1-9 学历、JD3-6 软素质）

**结论：三份 JD 的核心工程能力要求与本设计高度重合；不存在必须新增的"重大缺失模块"。剩余工作是把 🟡 项转成 spec 内显式机制（已做）与话术表达（W3）。**

---

## 3. 技术附录 A — State / Event / Transition

### A1. 状态集合（`enum AgentState`）

| 状态 | 含义 | 持久化点 |
|---|---|---|
| `INIT` | 会话创建 | 是（Redis session） |
| `QUESTIONING` | 出题节点执行中（角色：出题人，注入 KG/RAG 知识） | 否（瞬态） |
| `AWAITING_ANSWER` | 题已交付，等待用户作答 | **是（主等待点，断点恢复在此）** |
| `FOLLOWUP` | 追问节点执行中（角色：追问者，可选，深度受限） | 否（瞬态） |
| `EVALUATING` | 评估节点执行中（角色：评估官，注入参考要点） | 否（瞬态） |
| `DIFFICULTY_ADJ` | 确定性门禁：难度调整 / 重问 / 收尾决策 | 否（瞬态） |
| `SUMMARIZING` | 收尾：报告生成 + 画像批量写 | 是（写后即终） |
| `END` | 终态 | 是 |

### A2. 事件集合（`enum AgentEvent`）

`START`、`QUESTION_READY`、`QUESTION_FALLBACK`（重试耗尽→确定性兜底题）、`ANSWER_SUBMITTED`、`FOLLOWUP_READY`、`EVALUATION_DONE`、`EVALUATION_FALLBACK`（重试耗尽→规则评分）、`DIFFICULTY_ADJUSTED`、`END_REQUESTED`、`FORCE_END`（逃生舱）。

### A3. 转移表（守卫按表序求值；同事件多行由守卫互斥保证确定性）

| # | from | event | guard | to | action |
|---|---|---|---|---|---|
| 1 | `INIT` | `START` | G0 | `QUESTIONING` | 构建上下文（画像+岗位+历史） |
| 2 | `QUESTIONING` | `QUESTION_READY` | G1 | `AWAITING_ANSWER` | 存题、去重集更新、交付 |
| 3 | `QUESTIONING` | `QUESTION_FALLBACK` | G1-F | `AWAITING_ANSWER` | 确定性兜底题（TopicTracker 下一主题），trace 打标 |
| 4 | `AWAITING_ANSWER` | `ANSWER_SUBMITTED` | G2 ∧ G9 | `FOLLOWUP` | 存回答；判定需追问 |
| 5 | `AWAITING_ANSWER` | `ANSWER_SUBMITTED` | G2 ∧ ¬G9 | `EVALUATING` | 存回答；直接评估 |
| 6 | `FOLLOWUP` | `FOLLOWUP_READY` | G1-f | `AWAITING_ANSWER` | 交付追问（追问计入本轮） |
| 7 | `EVALUATING` | `EVALUATION_DONE` | G4 | `DIFFICULTY_ADJ` | 画像统计更新（命中率/薄弱点） |
| 8 | `EVALUATING` | `EVALUATION_FALLBACK` | G4-F | `DIFFICULTY_ADJ` | 规则评分，trace 打标 |
| 9 | `DIFFICULTY_ADJ` | `DIFFICULTY_ADJUSTED` | G5-N | `QUESTIONING` | 下一知识点，难度按 delta 调整 |
| 10 | `DIFFICULTY_ADJ` | `DIFFICULTY_ADJUSTED` | G5-R | `QUESTIONING` | **降难度重问同知识点**（门禁内，重问计数受限） |
| 11 | `DIFFICULTY_ADJ` | `DIFFICULTY_ADJUSTED` | G5-E | `SUMMARIZING` | 轮数耗尽 / 用户已请求结束 |
| 12 | `QUESTIONING`/`AWAITING_ANSWER`/`FOLLOWUP`/`EVALUATING` | `END_REQUESTED` | G6 | `SUMMARIZING` | 部分总结（已答内容） |
| 13 | 任意非终态 | `FORCE_END` | G7 | `SUMMARIZING` | 逃生舱收尾，trace 记原因 |
| 14 | `SUMMARIZING` | （内部） | G8 | `END` | 报告落盘 + 画像批量写 |

> 不变量：任何状态不得在无事件驱动下自循环；LLM 侧重试计数不构成状态转移。所有节点执行均为异步，事件由 Orchestrator 在节点完成后产生。

### A4. 变更影响传播链（JD1-3，显式化）

```
评估结果(score/tags) ──► 画像(薄弱点/命中率/等级) ──► 下一题难度 delta + 主题选择
画像(跨会话) ──► 下次会话 INIT 上下文注入（薄弱点优先出题）
评估(score<5) ──► 重问门禁(G5-R)：同知识点降难度重问（≤1 次/知识点）
```
传播全部经确定性数据流（profile + session context），不依赖 LLM 隐式记忆——这正是"变更影响传播由确定性代码实现"的面试点。

### A5. 多方案并行（JD1-4）

- 存量：检索侧多路并行（FAISS 稠密 + 稀疏，RRF 融合）——已实现，直接作为证据。
- 编排侧：`parallel_candidates` 配置（默认 `false`）。开启时出题节点并行生成 2 候选题（成本 ×2）确定性选优（schema 校验 + 去重 + 与画像匹配度）。仅 W3 富余时演示，默认关。

### A6. answer 契约映射（OPEN-3/4 冻结）

状态机阶段必须装入 legacy `answer` 响应契约（前端只消费 `evaluation` + `next_question` + `is_complete`，不新增字段）：

- **追问触发时（G9 命中）**：
  - 主答提交 → 评估官对主答评估 → 返回 `{evaluation(主答评估), is_complete:false, next_question: <追问题, 同 round, source='followup'>, session_id}`；主答行写库（evaluation=主答评估）。
  - 追问答提交 → 评估官对追问链做**合并最终评估** → 返回 `{evaluation(最终评估), is_complete:false, next_question: <下一主题题, round+1>, session_id}`；追问行写库（source='followup'，topic/category 留空），主答行更新为最终评估。
- **追问未触发（¬G9）**：主答提交 → 评估 → `{evaluation, is_complete?, next_question: <下一题> | report}`，与 legacy 单次往返一致。
- **同题重评（OPEN-4，前端"再答一次"传 `generate_next=false`）**：对同一 question_id 重新执行评估节点，状态不推进（不产生下一题），返回 `{evaluation(新评估), is_complete:false, next_question:null}`。
- **单问题最多 1 次 FOLLOWUP**（G9 深度上限=1，与逃生舱配合，禁止无限循环）。
- 前端视角：一轮可能呈现"评价 → 下一题（追问）→ 评价 → 下一题"，无需任何前端改动。

---

## 4. 技术附录 B — Phase Gate（门禁）

| 门禁 | 判定（全部确定性） | 不通过时 |
|---|---|---|
| G0 `START_GATE` | position 非空；会话未在活动态 | 拒绝 start，返回错误 |
| G1 `QUESTION_GATE` | 输出符合 Question Schema；question 非空；difficulty ∈ {easy,medium,hard}；knowledge_tags 非空；question 哈希不在 asked_set | 回填错误重试（≤3）→ G1-F |
| G1-F `QUESTION_FALLBACK` | 重试耗尽 | 用 TopicTracker 下一主题生成模板题（确定性），trace 打标；题库空→FORCE_END |
| G1-f `FOLLOWUP_QUESTION_GATE` | 追问输出符合 FollowUp Schema，非空 | 回填重试（≤3）→ 放弃追问，转 EVALUATING |
| G2 `ANSWER_GATE` | answer 非空；长度 ≤ `agent_max_answer_chars`(2000) | 拒绝该次提交，提示重答（不计轮） |
| G9 `FOLLOWUP_TRIGGER_GATE` | `followup_enabled` ∧ 本轮追问数 < `max_followup_depth`(1) ∧ answer 长度 < 200（模糊作答启发式） | ¬G9 → 直接 EVALUATING |
| G4 `EVAL_GATE` | 输出符合 Evaluation Schema：score ∈ int[1,10]、comment/score_reason 非空、tags 非空 | 回填重试（≤3）→ G4-F |
| G4-F `EVAL_FALLBACK`（确定性评分规则） | 重试耗尽 | score = `round(5 + 5×hit_ratio)`，hit_ratio = 命中参考关键词数 / 期望关键词数（≤1.0）；answer < 20 字符 → score=2（答不上来）；trace 打标 `fallback=eval_rule` |
| G5 `DIFFICULTY_GATE` | 见下表 | 输出 `{action, delta}` |
| G6 `END_GATE` | 用户请求结束 | 转 SUMMARIZING |
| G7 `ESCAPE_GATE` | 附录 C 任一条件触发 | FORCE_END，trace 记 `escape_reason` |
| G8 `SUMMARY_GATE` | 已答 ≥1 轮 或 由 G6/G7 进入 | 生成报告 + 画像批量写；报告生成失败→确定性摘要（拼接 Q&A），trace 打标 |

**G5 难度调整表（确定性）**：

| 条件 | action | 难度 delta |
|---|---|---|
| score ≥ 8 | `next`（下一知识点） | +1 级（hard 封顶） |
| 5 ≤ score < 8 | `next` | 0 |
| score < 5 且该知识点未重问过（`reask_allowed`） | `reask`（重问同知识点） | −1 级（easy 保底） |
| score < 5 且已重问过 | `next` | 0，薄弱点计数 +1 |
| round ≥ `max_rounds` 或 用户结束 | `end` | — |

---

## 5. 技术附录 C — Global Escape Hatch（全局逃生舱）

全部不依赖 LLM，配置化（`app/config.py`，禁魔法常量）：

| 上限 | 默认 | 触发动作 |
|---|---|---|
| `agent_max_rounds` | 15 | G5-E → SUMMARIZING（与存量 PlannerContext.max_rounds 对齐） |
| `agent_max_structured_retries` | 3 | 节点结构化输出回填重试上限 → 该节点确定性兜底 |
| `agent_max_consecutive_failures` | 3 | 连续节点失败（重试后仍失败）→ 下一节点走确定性兜底；累计兜底 ≥5 → G7 |
| `agent_node_timeout_sec` | 60 | 节点（含 LLM 调用）墙钟超时 → 该节点兜底 |
| `agent_max_transitions` | 200 | 转移计数护栏，防状态机失控 → G7 |
| `session_cost.is_over_budget` | 复用存量 | 超预算 → G7 提前收尾 |
| 重问计数 | `max_reask_per_topic`=1 | G5-R 限制，防同知识点无限降难度循环 |

**G7 语义**：`FORCE_END` → SUMMARIZING，trace 必记 `escape_reason`；SUMMARIZING 本身失败 → 确定性摘要兜底，流程终归 `END`。逃生舱触发即"流程设计确定性"的现场演示素材。

---

## 6. 技术附录 D — Module / File List

全部新代码落在 `app/services/agent/`（Law of Layers：不依赖 API 层；DI 注入存储与服务）：

```
app/services/agent/
├── __init__.py            # 对外导出 AgentService
├── state_machine.py       # AgentState/AgentEvent/转移表/门禁函数/StateMachine 类
├── roles.py               # 角色定义：出题人/追问者/评估官（system prompt + 输出 Schema + 知识注入）
├── structured_output.py   # JSON 提取（围栏剥离）→ jsonschema 校验 → 错误回填重试（≤3）
├── tools.py               # Tool 契约 + ToolRegistry + 内置工具（含 eval_rules 规则校验/参数汇算）
├── model_gateway.py       # 统一模型接口：分级(turbo/plus) + 降级链 + 成本统计（复用 session_cost/monitor）
├── mcp_client.py          # (W2) MCP 工具桥接 + 本地注册表降级
├── orchestrator.py        # 事件循环：节点执行 → 门禁 → 转移 → trace 钩子 → 逃生舱检查
├── agent_service.py       # 对外门面：start/answer/end/report/get_state（DI RetrievalFacade/TopicTracker/ProfileStore/InterviewStore）
├── profile_store.py       # (W2下) Redis 画像；降级=会话内画像（内存 dict）
├── trace.py               # TraceRecorder：JSONL 写入/保留策略
└── fallback.py            # 降级矩阵确定性动作实现（兜底出题/规则评分/确定性摘要）
```

依赖方向：`agent/*` → `app/services/{retrieval_facade, topic_tracker, session_cost, monitor}`、`app/storage/{interview_store, session_store}`、`app/config`。跨层接口变更同步更新 `SERVICES_LAYER.md`（Layer 契约 DoD）。

**复用清单（B11，禁止重复造轮子）**：RetrievalFacade（检索）· TopicTracker（主题/薄弱点/覆盖率）· LLMClient→经 model_gateway（LLM）· session_cost/monitor（成本/指标）· tenacity（重试）· eval_metrics/eval_testset（评测）· InterviewStore（会话持久化）· settings（配置）。

---

## 7. 技术附录 E — Interface Contract

### E1. `AgentService`（OPEN-1 冻结：镜像 legacy 完整 surface，`app.main` 装配工厂二选一，API 层与前端零改动）

```python
# 契约（伪签名，非实现）—— 与 legacy InterviewService 对外方法一一对应
async def start(position, username="", resume_file=None, jd_text=None) -> {session_id, question}
async def answer(question_id, answer, generate_next=True, username=None) -> {evaluation, is_complete, report?, next_question?, session_id}
async def end(session_id, username=None) -> {session_id, report}
async def get_report(session_id, username=None) -> Optional[dict]     # 只读，不触发 LLM
def get_detail(session_id, username=None) -> Optional[dict]           # 纯读取
def history(username=None, limit=20) -> list[dict]
def stats(username=None) -> dict                                      # 见 E6（exclude_sources）
async def today(username=None, position=None) -> dict                 # 独立产品功能，委托 legacy
# 属性（API 层 coverage 端点直接访问，必须暴露）
store: InterviewStore;  topic_tracker: TopicTracker
```

- 职责归属（F9）：`start/answer/end` = Agent 核心（状态机自实现）；`get_report/get_detail/history` = 直读 store（数行，无业务复制）；`stats/today` = **委托注入的 legacy 实例公开方法**（不复制逻辑）；`coverage` = 属性暴露。
- `answer` 按 `question_id` 定位（非 session_id）；`generate_next=False` 走同题重评路径（OPEN-4，见 A6）。
- `start` 沿用 multipart 语义：可选 resume/JD 解析复用 `ResumeParser`（存量，不重写），分析结果注入首题上下文。

### E2. 节点执行契约（Role Node）

```python
NodeContext = {session_id, user_id, state, round, profile, knowledge_context,
               prev_eval, asked_set, followup_budget, trace}
NodeResult  = {output: dict(typed), meta: {model, prompt_version, retries, latency_ms,
               fallback: bool, tool_calls: [...]}}
Role 节点实现: async def run(ctx: NodeContext) -> NodeResult
```
节点内部只允许：调用 model_gateway / 调用工具 / 确定性计算；**不直接改状态**（状态变更只能经事件转移）。

### E3. 角色与结构化输出 Schema（JSON Schema 即接口契约，JD1-11）

| 角色 | 注入（按阶段） | 输出 Schema 字段（校验点） |
|---|---|---|
| 出题人 | KG/RAG 检索块（经 `kb_retrieve`）+ 画像（薄弱点/难度）+ 难度历史 | `question`(非空) · `difficulty`(enum) · `knowledge_tags`(≥1) · `topic` · `category` |
| 追问者 | 本题 + 用户回答 + 评估要点（可选） | `followup_question`(非空) · `intent`(enum: 澄清/深挖/边界) |
| 评估官 | 题目 + 回答（+追问链）+ 参考要点 | `score`(int 1-10) · `comment`(非空) · `score_reason`(非空) · `reference_answer` · `tags`(≥1) |

Schema 定义放在 `roles.py`，`structured_output.py` 用 `jsonschema` 校验；校验失败将错误信息**回填 prompt** 重试（≤3），重试耗尽走门禁兜底。

### E4. 上下文注入与裁剪（JD2-3）

- 注入顺序：system 角色 prompt → 画像摘要 → 检索上下文（截断后）→ 会话历史（最近 `max_history_turns` 轮）→ 本轮输入。
- 裁剪：检索上下文按 `agent_max_context_chars`(4000) 截断（先保留高相关 chunk）；历史用存量 `max_history_turns=20` 复用；超出部分确定性丢弃并在 trace 记录 `context_truncated`。
- 输入摘要写入 trace 前脱敏（截断 + 去敏感词启发式，demo 阶段人工把关）。

### E5. 模型接入层（`model_gateway`，JD1-7）

```python
TaskSpec = {role_level: "light"|"heavy", prompt, system, schema, session_id}
generate(TaskSpec) -> GenerationResult{text, model, cost, retries, latency_ms}
```
- 分级策略表（默认，config 可改）：light（追问/出题）→ `qwen-turbo`；heavy（评估/报告）→ `qwen-plus`。
- 降级链：`qwen-plus` → `qwen-turbo` → （接口预留第三供应商，当前抛确定性兜底）。
- 成本：经 `monitor` → `session_cost`（存量接线，免费复用）；`token_price` 增加 `qwen-plus` 单价（config 变更项）。
- 供应商适配器接口 `ProviderAdapter`（chat/chat_stream/成本），Bailian 为唯一实现，跨供应商延后（B5）。
- **OPEN-2 冻结约束**：`model_gateway` **不得绕过 LLMClient**、不引入第二套 HTTP 逻辑。LLMClient 做最小向后兼容扩展：`chat(prompt, system=None, session_id=None, model=None)` / `chat_stream(...)` 增加可选 `model` 参数，不传用 `self.model`（存量调用方零改动）；`monitor.emit_cost` 上报**实际使用的模型名**。model_gateway 仅负责策略选择（light→turbo、heavy→plus）与降级链。

### E6. 画像与报告口径（F8 冻结）与统计过滤扩展点（F9 冻结）

**F8 口径（写入 profile_store / report / evaluation 契约）**：
- **画像历史正确率** = 最近 10 次**主问题**单题评估分均值（跨场次按时间倒序，`source='followup'` 不计入；G4-F 兜底规则分**计入**但记录必须带 `fallback` 标记）。每次会话结束（SUMMARIZING）按此口径更新 profile。
- **agent `report.total_score`** = 本次会话主问题单题分**均值**（与 legacy 报告口径一致，前端展示不变；保留 `session.total_score`(SUM) 仅作 history 展示兼容，agent 不据此做任何决策）。
- **对照评测不依赖 total_score 字段**：主要指标 = 单题分分布（过滤 followup）+ recall@3 + MRR + 人工追问合理性 + trace 流程断言（见附录 I）。

**F9 存量最小扩展点（agent-dev 上向后兼容，默认行为不变）**：
- `InterviewService.stats(..., exclude_sources=None)`：`None` = legacy 行为不变；agent 模式传 `("followup",)`。
- `TopicTracker.get_coverage(..., exclude_sources=None)`（及内部统计路径）：同上。
- 约束：不新增 `is_followup` 字段；不改 schema；legacy 模式完全不受影响；followup 仍作为独立 question/answer 落库（F1）。

---

## 8. 技术附录 F — Tool Contract（工具契约）

```python
Tool = {
  name: str, description: str,
  input_schema: JSON Schema, output_schema: JSON Schema,
  handler: async callable, timeout_sec: int,
  error_policy: "degrade" | "abort",   # degrade=跳过并 trace 打标；abort=触发 G7
}
ToolRegistry: register(name, tool) / get(name) / list()   # 幂等注册，纯数据结构（可移植性话术钩子）
```

**内置工具表**：

| 工具 | input（Schema） | output（Schema） | 说明 |
|---|---|---|---|
| `kb_retrieve` | {query, top_k} | {chunks[], sources[]} | 包 `RetrievalFacade.retrieve`；**W2 经 MCP 暴露** |
| `get_profile` | {user_id} | {weak_points[], level, accuracy, history[]} | Redis 挂→返回空画像（降级） |
| `update_profile` | {user_id, patch} | {ok} | 会话末批量写（G8 处调用） |
| `mock_resume` | {user_id} | {projects[], technologies[]} | 非 RAG 外部工具（mock 简历库）；**W2 经 MCP 暴露** |
| `pick_next_topic` | {position, covered[]} | {topic, category} | 确定性，包 `TopicTracker.get_next_suggestion` |
| `eval_rules` | {score, hit_ratio, reask_allowed} | {action, delta} | **规则校验 + 参数汇算示例**（G5 的载体） |

工具执行超时走 `timeout_sec`；异常按 `error_policy` 处理（进降级矩阵）。MCP 化（W2）：`kb_retrieve` + `mock_resume` 注册为 MCP 工具，本地注册表保留为降级路径（W1 形态即降级形态）。

### F1. 问题 `source` 取值语义（F7/OPEN-5 冻结）

- 存量语义（已核对，全代码无逻辑依赖 source 值）：`kb`（知识库出题）/ `llm`（纯 LLM 出题，LLM 自选）/ `today`（今日一题）。
- **扩展取值 `followup`**（追问类型标记）：不新增字段、不改 schema（F9 约束）。followup 问题行约束：
  - 有**独立 question_id**（复用 `InterviewStore.add_question`）；
  - `topic`/`category` 留空（`TopicTracker.get_coverage` 天然跳过空值，不污染覆盖率）；
  - 完整写入 question/answer/evaluation/score（不破坏 question_id/answer/report/trace 语义）；
  - 主问题统计、coverage、profile accuracy、report 均**过滤 `source='followup'`**（见 E6 与 G8）。

---

## 9. 技术附录 G — Failure / Degradation Matrix（统一降级矩阵）

| 失败点 | 探测 | 降级动作 | 状态影响 |
|---|---|---|---|
| LLM 调用失败（网络/API/超时） | 异常 / tenacity 耗尽 | 分级降链（plus→turbo）→ 节点兜底 | 状态机照常推进 |
| 结构化输出校验失败 | jsonschema 校验 | 错误回填重试 ≤3 → 门禁兜底（G1-F/G4-F） | 照常推进，trace 打标 |
| 检索/RAG 失败 | facade 已吞异常返回空 | 无上下文纯 LLM 出题 | 照常推进 |
| MCP 不可用 | 握手/调用失败 | 本地工具注册表 | 照常推进 |
| Redis 不可用 | 连接异常 | 画像降级为会话内 | 照常推进 |
| 工具超时 | timeout_sec | error_policy=degrade 跳过；abort→G7 | 跳过或收尾 |
| 预算超限 | `session_cost.is_over_budget` | G7 提前收尾 | 收尾 |
| 节点连续失败 ≥3 / 累计兜底 ≥5 | 计数 | G7 | 收尾 |
| 前端断流（SSE 中断） | 请求自然结束（DR-005） | 状态已持久化（AWAITING_ANSWER），可恢复 | 无异常路径 |
| 报告生成失败 | 异常 | 确定性摘要（Q&A 拼接） | 照常收尾 |

原则：**任何单点故障不得使状态机卡死或产生非法转移**；所有兜底在 trace 打标，可归因。

---

## 10. 技术附录 H — Trace Schema（JSONL，每 session 一文件）

- 文件：`data/traces/{session_id}.jsonl`（config `agent_trace_dir`）；保留策略：仅保留最近 `agent_trace_retention`(200) 个文件。
- 记录类型：`node_started` / `node_finished` / `transition` / `tool_call` / `fallback` / `escape` / `session_end`。

```jsonc
{
  "schema_version": "1.0",
  "session_id": "…", "ts": "ISO8601",
  "event": "node_finished", "state": "EVALUATING",
  "node": "evaluator", "role": "评估官",
  "model": "qwen-plus", "prompt_version": "roles.v1",
  "input_summary": "…（注入上下文摘要，截断+脱敏）",
  "raw_output": "…", "validated": true, "retries": 1,
  "tool_calls": [{"tool": "kb_retrieve", "args_summary": "…", "latency_ms": 230, "ok": true}],
  "fallback_used": null,
  "cost": 0.0021, "latency_ms": 1850
}
```
- 归因演示（话术主线 2）：逐字段回答"是模型能力（model/raw_output）、流程设计（state/transition/retries）、数据质量（input_summary/检索来源）、还是评估方式（validated/fallback）的问题"。
- OTel：仅 W3 富余再包一层（存量 `observability.py`），trace JSONL 为主。

---

## 11. 技术附录 I — Evaluation Acceptance Criteria（验收标准）

**E1 单元测试（pytest，全部 mock LLM，无真实调用）**
- `state_machine`：转移表逐行 + 守卫互斥 + 非法转移拒绝 + G7 各触发条件。
- `structured_output`：围栏剥离 / 非法 JSON / 缺字段 → 回填重试 ≤3 → 兜底；计数正确。
- `tools`：Tool 契约注册幂等；input/output schema 校验；超时与 error_policy。
- `fallback`：G1-F 模板题、G4-F 规则评分（含 score=2 短答分支）、G5 难度表全分支。

**E2 集成测试（mock LLM + 注入故障）**
- 全流程：INIT→…→END 状态序合法；每条降级分支注入故障后仍达 END；trace 文件生成且字段完整。

**E3 真实 LLM 评测（对照跑数，`data/eval_interview_subset.json` 17 条）**
- legacy vs agent 各跑一遍，指标（**不依赖 total_score 字段，F8**）：单题分分布（均值/方差，过滤 followup）+ recall@3 / MRR（复用 `eval_metrics`）+ 人工抽样 5 条"追问合理性"（≥4/5 通过）。
- **trace 断言（B9）**：① 状态流转合法率 100%（trace 转移序列 ⊆ 转移表）；② 重试次数字段非空且 ≤ 上限；③ schema 失败→兜底被触发有记录；④ 工具调用耗时非空；⑤ escape_reason 记录与逃生舱触发一致。
- 报告落 `docs/evaluation/`，先报告后结论（PROCESS §1）。

**E4 验收门槛**
- W1：最小闭环 demo（真实 LLM 跑通 出题→回答→评估→难度调整→总结，全程 trace，legacy 可切换）+ E1/E2 全绿。
- W2：对照表 + 归因 trace 演示 + 画像跨会话影响难度。
- W3：话术三条主线演示脚本 + LangGraph 概念映射表（stretch）。

**E5 非目标**：不要求 agent 指标全面优于 legacy；目标是可归因、可复现、可讲述（§4.4 原则保留）。

---

## 12. 里程碑（修正版，B3 已采纳）

| 阶段 | 内容 | 出口 |
|---|---|---|
| 周 0（0.5–1 天） | 切 `agent-dev`；本 spec 评审确认；`interview_mode` 接缝确认（零前端改动） | spec 确认签署 |
| W1（40h，必须） | 附录 D 骨架 + A/B/C 状态机门禁逃生舱 + 角色/结构化输出重试 + 本地工具注册表 + trace + 装配接线 + 真实 LLM 联调 | **最小闭环 demo** |
| W2 上（20h） | MCP 双工具（`kb_retrieve`+`mock_resume`，**2 天上限**，本地降级）+ model_gateway 分级/成本 | MCP + 分级可用 |
| W2 下（20h） | profile_store（可降级会话内）+ 17 样本对照 + trace 断言，报告落 `docs/evaluation/` | 对照表 + 归因演示 |
| W3（40h） | **① 演示打磨 + 话术训练（优先）** ② LangGraph spike（stretch：读源码+对应关系映射表，完整复刻仅富余） ③ 收尾：SERVICES_LAYER 契约更新（DoD）、DECISIONS 新增 DR、复盘 | 可讲可演示闭环 |

砍单链（不变，超时执行）：状态机+门禁 > 结构化输出+重试 > MCP 双工具 > 长期记忆 > 多模型分级 > LangGraph。

---

## 13. 明确不做（Out of Scope）与话术映射

| 项 | 理由 | 话术 |
|---|---|---|
| Java 生产实现（JD1-8） | 决策 4 | 转移表/工具注册为纯数据结构，移植路径已想清 |
| Computer-Use / 桌面自动化（JD2-6） | 与本面试场景无关 | 工具契约不限定实现，抽象留扩展点；明确说明场景取舍 |
| 跨供应商多模型完整适配 | B5 | 接口预留 + 策略表，讲分级与降级设计 |
| LangGraph 完整复刻 | B3 | 读源码 + 手写 vs LangGraph 概念对应（state/channel/checkpoint） |
| 显式 HITL 人工确认 | 面试场景天然会话式协作 | 人机协作 = 用户作答 + agent 自适应调整 |

---

## 14. 待确认决策点（默认值，确认时可否决）

1. **追问默认开启**：`followup_enabled=true`，`max_followup_depth=1`（每轮最多 1 次追问；模糊作答触发）。
2. **重问策略**：score<5 且未重问过 → 降难度重问同知识点，每知识点 ≤1 次。
3. **G4-F 规则评分**：`round(5+5×hit_ratio)`，短答(<20 字)记 2 分。
4. **模型分级**：light=turbo（出题/追问）、heavy=plus（评估/报告）。
5. **LangGraph**：默认"读源码 + 对应关系讲解"，完整复刻仅在 W3 富余。
6. **上下文裁剪**：`agent_max_context_chars=4000`，历史复用 `max_history_turns=20`。
7. **trace 保留**：最近 200 文件；含用户回答（demo 阶段人工把关脱敏）。

> 以上默认值如无异议，本 spec 即视为确认，可进入实现（周 0 起步）。
