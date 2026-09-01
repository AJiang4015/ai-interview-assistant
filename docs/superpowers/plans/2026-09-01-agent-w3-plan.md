# Agent 编排化改造 — W3 执行计划（打磨 / 表达 / 复盘 / 决策补全）

> 日期：2026-09-01　|　分支：agent-dev　|　前序：W1（Day1-5 验收通过）→ W2 上（MCP+Gateway 验收通过）→ W2 下（Profile+Eval 验收通过，追问 5/5 合理入报告，redis 凭据 12345678 已提供）
> 状态：**计划待确认**（确认前不修改业务代码）

---

## 0. 目标切换与边界

**W3 不做能力开发**：从「继续开发」切换为 **Demo 打磨 / 面试表达 / 架构复盘 / 决策文档补全** 四件事。

**禁止主动扩展**（除非发现阻塞性 bug，否则不进入功能开发）：
- 新 Agent 能力 · 新 Tool · 新状态 · 新 Memory 机制 · 新模型供应商
- 不实现 LangGraph / OTel / 跨供应商 / 前端交互扩展

**可触碰代码的边界**：仅 Demo 打磨所需的「只读 trace 查看入口」（API 端点 + 静态展示页，不改现有前端交互逻辑）；其余全部为文档/材料产出。

---

## 1. Demo 打磨（约 12h）

| # | 动作 | 产出 | 是否动代码 |
|---|---|---|---|
| 1.1 | 端到端 Demo 脚本（真实 LLM，注入 Machine key）：固定脚本化演示路径 出题→回答→追问→评估→难度调整→报告 | `scripts/agent_w3_demo.py`（可复现、预置 Java 主题问答） | 新增脚本（非业务代码） |
| 1.2 | 三个高光时刻固化：①归因 trace 逐字段讲解（模型/流程/数据/评估四象限）②降级演示（LLM 不可用→G1-F/G4-F→逃生舱）③跨会话画像影响难度 | demo 走查脚本 + trace 样例 | 复用 smoke |
| 1.3 | trace 只读查看入口：`GET /api/agent/traces/{session_id}`（读 JSONL 返回）+ 独立静态页（不挂进现有导航） | 只读端点 + `frontend/agent-trace.html` | **唯一代码改动**（不动现有前端交互） |
| 1.4 | 边界演练清单：LLM 挂 / RAG 挂 / Redis 挂 / 连续失败 / 中途退出 / 再答一次 | `docs/evaluation/2026-09-01-agent-demo-script.md` | 文档 |

## 2. 面试表达准备（约 12h）

| # | 动作 | 产出 |
|---|---|---|
| 2.1 | 三条主线话术稿：开场定位（确定性编排）/ 归因（trace 四象限）/ 取舍（ReAct/LangGraph/Java/MCP transport） | `docs/interview-materials/agent-*-talk.md` |
| 2.2 | JD 能力要求 ↔ 本项目证据映射（复用 W0 拆解，转成面试版） | `docs/interview-materials/agent-jd-evidence.md` |
| 2.3 | 5 分钟 demo 讲解稿 + 3 分钟电梯稿 + 高频追问应答（为什么不用自由循环 / 为什么 agent 评分更严格 / stdio 为何改 HTTP 等） | 同上目录 |
| 2.4 | 一次完整 demo 演练（真实 LLM，录 trace 供讲解） | 演练记录并入 1.4 文档 |

## 3. 架构复盘（约 8h）

| # | 动作 | 产出 |
|---|---|---|
| 3.1 | W1-W2 复盘：交付 vs 计划 vs spec、砍单链执行、时间盒遵守、风险命中（MCP stdio 沙箱拒绝→HTTP；401→Machine key 注入）、偏差与原因 | `docs/evaluation/2026-09-01-agent-w3-retrospective.md` |
| 3.2 | 手写状态机 vs LangGraph 概念对应（state/channel/checkpoint 映射表 + 一页总结；**读源码+讲解，不实现**） | 并入复盘文档或独立小节 |
| 3.3 | 技术债清单：进程内 session（Redis 持久化）、MCP 生命周期正式接线、app.main 启用 MCP 开关、gateway 成本统计完善、Redis roundtrip smoke（凭据 12345678 可用→补验）、评测样本扩大 | 并入复盘文档 |

## 4. 决策文档补全（约 8h）

| # | 动作 | 产出 |
|---|---|---|
| 4.1 | DECISIONS.md 新增 DR：确定性编排架构 / MCP 选型（stdio→streamable HTTP 实测）/ Model Gateway 分级（经 LLMClient，无第二套 HTTP）/ Profile 口径（F8）/ followup source 契约 / trace 归因 schema | DECISIONS.md |
| 4.2 | SERVICES_LAYER.md 补 agent/ 层契约（模块、接口、依赖，Layer 契约 DoD） | SERVICES_LAYER.md |
| 4.3 | ARCHITECTURE.md 模块地图补 `app/services/agent/` | ARCHITECTURE.md |
| 4.4 | impl spec 状态标记（W1-W2 完成；W3=打磨期） | impl-spec v2 头部 |

---

## 5. 执行顺序与验收

- 顺序：先 4（决策补全，固化成果）→ 3（复盘，先证据后结论）→ 1（Demo 打磨）→ 2（表达材料，依赖 demo 实际表现）。
  - 说明：与用户列出的顺序（1→2→3→4）相比，调整为 4→3→1→2，理由：决策/复盘先行可固化冻结口径（防成果漂移），Demo 与话术放在后段（依赖真实运行表现与复盘结论）。**如你希望保持原顺序，可改。**
- 验收：demo 脚本可复现 + trace 入口可用 + 话术材料齐 + 复盘报告落盘 + DECISIONS/LAYER/ARCHITECTURE 更新 + 全量测试仍绿（157）。
- 已知待补验（不阻塞）：Redis roundtrip smoke（凭据 12345678 已提供 → 计划 4.1/3.3 时顺手补一次，不改代码逻辑）。

---

## 6. 禁止清单复核

不新增 Agent 能力 / Tool / 状态 / Memory / 模型供应商；不实现 LangGraph / OTel / 跨供应商；不改前端交互；不重构 StateMachine / Agent API。仅 1.3 的只读 trace 端点 + 静态页为唯一代码改动（且为新增，非修改现有逻辑）。
