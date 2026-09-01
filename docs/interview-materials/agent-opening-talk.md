# Agent 面试表达 — 三条主线

> 定位：把已完成的 Agent 工程能力转化为本人可独立讲清、可应答追问的表达材料。
> 依据：`docs/superpowers/specs/2026-08-31-agent-orchestration-refactor-impl-spec.md` v2、DR-011~016、
> `docs/evaluation/2026-09-01-agent-w3-retrospective.md`、Demo（`scripts/agent_w3_demo.py` 实测通过）。
> 原则：只讲实际实现，能指到代码 / trace / 测试证据；区分"已实现 / 部分覆盖 / out-of-scope"。

---

## 主线一：开场定位（30~60 秒）

> 场景：面试官让你先介绍项目。

**话术稿**：

"我做的项目原本是一个 Java 程序员面试助手——基于 RAG 的知识问答 + AI 模拟面试。因为目标岗位是 Agent 开发，我在主项目冻结期单独开了一个分支，把里面的『面试官模块』升级成一个**确定性编排 + LLM 角色节点**的多阶段 Agent 系统。

核心定位一句话：**面向 Java 岗位的自适应 AI 面试官——流程编排和规则校验由确定性代码实现，LLM 只在角色节点内被调用**。

我特别强调『确定性编排』，是因为这个岗位的 JD 里明确写了『认同流程编排与规则校验由确定性代码实现的技术路线』。我们的面试流程——出题、追问、评估、难度调整、总结——是一个固定阶段的状态机，每个阶段是一个角色节点，LLM 只负责节点内的生成；**阶段怎么流转、什么时候降级、什么时候收尾，全部是确定性代码**。"

**支撑事实**（被追问时抛出）：
- 状态机 8 状态 / 10 事件 / 14 行转移表 / 9 道门禁 / 全局逃生舱（`app/services/agent/state_machine.py`，DR-011）；
- 真实会话 trace 状态流转合法率 100%（评测 53 条 transition 0 非法）；
- 3 周里程碑：W1 最小闭环 → W2 MCP/分级/画像/评测 → W3 打磨，砍单链未触发。

---

## 主线二：Trace 归因（怎么区分四类问题）

> 场景：面试官问"你的 Agent 出问题，怎么排查？怎么归因？"

**核心主张**：每个阶段把关键事实写进 JSONL trace，用字段直接回答"是模型、流程、数据还是评估的问题"。

**四象限 ↔ trace 字段对照**（`data/traces/{session_id}.jsonl`，7 类事件）：

| 问题类别 | 看哪个字段 | 怎么判断 |
|---|---|---|
| **模型问题** | `node_finished.model / raw_output / validated` | raw_output 内容质量差 / validated=False（模型没按 schema 输出）→ 模型能力或 prompt 边界 |
| **流程问题** | `transition` 序列 / `retries` / `escape` | 状态流转非法、重试次数异常、触发逃生舱 → 流程设计（转移表/门禁） |
| **数据问题** | `tool_call`（kb_retrieve 命中与否）/ `input_summary` | 检索没召回 / 注入上下文缺失 → 数据/检索质量 |
| **评估问题** | `fallback_used`（eval_rule vs LLM 分）/ `validated` | 评估走了规则兜底 / 评分口径 → 评估方式 |

**现场演示锚点**（Demo 章节 2）：
- 一次 401 环境下的真实会话：出题/评估节点 `fallback=question_fallback/eval_rule` → 一眼定位"LLM 调用失败→流程兜底生效"（模型问题 + 流程设计共同起作用）；
- 评测中 recall@3=0.588：miss 集中在"评价形态"长查询 → 归因到检索（数据/检索），而非生成（模型）——**先归因再动手**（PROCESS §0：Evidence 先于 Root Cause）。

**支撑事实**：trace 字段完整性单测（必填字段 / 类型白名单 / session 一致性）、评测 trace assertions 全过（retries≤2 / schema→fallback 有记录 / tool latency 全记录）。

---

## 主线三：架构取舍（7 个为什么）

> 场景：面试官逐个挑战技术选型。原则：先答"为什么这样设计"，再给证据。

### 1. 为什么不用自由 ReAct？
- **设计**：自由 ReAct = LLM 每步选动作，循环边界由模型决定 → 不可测、不可归因、成本不可控。
- **替代**：确定性状态机 + 固定事件集，LLM 只在节点内生成，**什么时候走哪条边由转移表+门禁决定**。
- **证据**：转移表逐行单测（14 行全覆盖）+ trace 合法率 100%；JD 原文"认同确定性技术路线"直接对齐。

### 2. 为什么不做 Multi-Agent？
- **设计**：Multi-Agent 是协作/竞争架构，引入跨 agent 通信与协调成本；本场景是**单会话串行面试**，多 agent 是"为了展示而堆"。
- **证据**：明确列入不做（核心决策 2）；单 agent 内已经用"三角色节点"表达了角色分工（出题人/追问者/评估官），无需进程级多 agent。

### 3. 为什么 RAG 是 Tool？
- **设计**：项目主体是"Agent 编排"，RAG 是从既有项目继承的成熟能力，把它封装成 `kb_retrieve` 工具注入节点，**不重构 RAG、不重复实现**。
- **证据**：`tools.py` 的 `kb_retrieve` 直接包 `RetrievalFacade.retrieve`（Part B 已验证管线），零 RAG 代码新增；既保留"RAG 整套落地"能力（JD2-4），又让主体是 Agent。

### 4. 为什么手写 StateMachine，不引框架？
- **设计**：8 状态 / 10 事件 / 14 行转移表——规模小到任何状态机库都是负担；手写转移表是**纯数据结构**，可逐行单测、可讲移植路径（JD1-8：Java 生产实现时转移表原样搬运）。
- **证据**：表驱动单测 23 用例；`TRANSITIONS` 是数据不是代码。

### 5. 为什么当前不做 LangGraph full rewrite？
- **设计**：LangGraph 的价值在动态大状态集 + checkpoint/中断/生态；当前规模下收益 < 迁移成本。只做**概念映射**（State/Graph/Edge/Conditional Edge/checkpointer ↔ 手写对应物）作为学习材料，不实现。
- **证据**：复盘 §8 映射表；技术债 P2 明确 out-of-scope；"读源码 + 对应关系讲解"是砍单链批准的降级产出。

### 6. 为什么 MCP 从 stdio 调整为 streamable HTTP？
- **设计**：MCP 协议是统一的，transport 可替换。本环境（Windows + 沙箱）实测 **stdio 子进程管道被拒**（PermissionError），streamable HTTP 端到端通过 → 采用 HTTP，协议层不变。
- **证据**：transport 探测（memory/stdio/HTTP 三路实测）+ `mcp_client.py` 传输可切换 + 单测（内存 transport 跑真实协议 / HTTP 真实传输 / 失败回退本地）。

### 7. 为什么 ModelGateway 不绕过 LLMClient？
- **设计**：分级（light→turbo / heavy→plus）只是"选模型"，不是"再造客户端"。绕过 LLMClient = 第二套 HTTP / 重试 / 成本统计 / 错误处理——重复且会漂移。
- **证据**：`model_gateway.py` 的 `BailianAdapter` 只调 `llm.chat(..., model=None)`（OPEN-2 扩展）；单测断言调用链（gateway→LLMClient，无第二套 HTTP）；成本按实际模型名记录（`monitor.emit_cost`）。

**被追问时的兜底口径**：所有取舍都能落到三个词——**可测、可归因、可降级**；所有"没做"都有明确边界（out-of-scope 列表），不把没做包装成已做。
