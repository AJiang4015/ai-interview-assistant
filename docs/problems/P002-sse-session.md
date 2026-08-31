# P002 — 前端 SSE 流式输出在会话切换后中断 / 写错会话

## Status

- ID：P002
- Severity：High
- Status：Resolved（已修复并固化约束）
- First identified：SSE 流式输出迭代期间（commit `55a654f` 前）
- Related Decision：DR-005（流式协议选型 SSE + 事件语义）；PROBLEM.md 高频规则 D1–D4 / D11
- Related Spec：`docs/superpowers/specs/2026-08-12-rag-pipeline-upgrade-design.md`（SSE 事件契约）
- Related Tests：Door 2 / Door 3 / Door 4 / Door 11（前端门禁，尚未自动化，见 PROBLEM.md Appendix）

---

## 1. Problem

发起流式回答后切换到其他会话，原回答流中断 / 内容写错会话 / 不再追加 token。

## 2. Impact

多会话模式下回答不完整或错位，严重破坏使用体验与数据准确性。多会话场景是核心交互模式（面试 / 复习 / 问答间切换），中断每出现一次，用户需手动回到原会话判断回答是否完整。

## 3. Evidence

- 修复提交：`55a654f`（"解决前端流式响应切换会话后中断bug"）。
- 记忆追认多个根因（见 §4）：`state.sessionId` 被误改；contentDiv 被局部变量持有跨会话失效；清空 messages/DOM 丢上下文；删除会话时 `renderSessions()` 仅 else 分支调用。
- 行为基线：AI 响应期间允许并行会话操作，新 / 切 / 删不阻塞用户、不 abort 进行中请求。

## 4. Root Cause

（多项叠加，均已确认）

1. SSE 事件中直接修改 `state.sessionId`，导致后续追加写错会话；
2. `sendQuestion` 把 contentDiv 存进局部变量，跨会话后原 DOM 被移除，token 无有效容器；
3. 切换会话时清空 messages/DOM 且调用 `abort()`，破坏进行中的流；
4. 删除会话后侧边栏未在两个分支都刷新。

设计根因：把"当前会话"与"请求所属会话"混为一谈；前端把流式渲染目标（DOM）与全局状态强耦合，切换视图时一同销毁。

**流程根因**（为什么没被 E2E 拦下）：测试矩阵只覆盖"单会话提问"，从未覆盖"流式中切到另一会话"的并行时序；状态与 DOM 的耦合未纳入评审标准；依赖单一提交修复（`55a654f`）而**未同步补回归测试**。

## 5. Decision / Solution

- **决策（DR-005 配套前端铁律，固化于 D1–D4 / D11）**：
  - SSE 事件只更新 `finalSessionId`，不写 `state.sessionId`；
  - token 通过 `getStreamingContentDiv(sessionId)` 动态获取当前有效 contentDiv；
  - 切换 / 删除会话不 `abort()`，让流在后台自然完成写回发起会话；删除进行中流的会话时保留其数据结构；
  - `renderSessions()` 在删除的两个分支都被调用；
  - 流式 DOM 更新节流（rAF + pendingRender，token 间隔 ≥50ms），done/error/终止时取消待处理 rAF 做最终完整渲染。
- 备选方案对比：
  - ✅ 方案 A（采用）"自然完成 / 让其收尾"：不 abort，后台收尾写回。语义正确成本最低；额外 token 用预算告警兜底（P011）。
  - ❌ 方案 B（否定）"立即 Flush 并终结"：切换往往在回答刚开始，Flush 后内容几乎为空，用户损失全部回答。
  - ❌ 方案 C（否定）"缓冲后重定向到新会话目标"：会让答案出现在用户"没提问过该问题的会话"里，数据错位。

## 6. Implementation

commit `55a654f`（前端 `frontend/js/app.js`）：事件处理改为绑定发起时 sessionId、动态获取 contentDiv、切换/删除不中断流、删除分支全量刷新。

## 7. Regression / Verification

- 多会话依次提问 / 切换 / 删除，流式回答都能完整落到正确会话，不中断、不错位。
- 建议补：切换 / 删除会话的流式端到端回归用例（Door 2/3/4/11 尚未自动化）。

## 8. Current Status

Resolved。约束已固化（D1–D4 / D11 持续维护于 PROBLEM.md 高频规则与 `AGENTS.md` 流式会话铁律）。

## 9. Lessons

- 流式请求必须始终绑定到**发起时的会话 ID**，而非全局"当前会话"状态——"请求归属"与"UI 当前焦点"是两个概念。
- 并行会话操作（新建 / 切换 / 删除）不得阻塞用户；让流自然完成（后台继续消耗 token）的代价用成本预算兜底。
- 这类并发时序 bug 只能靠并发 E2E 与状态不变量发现，单测 / 串行 E2E 无法覆盖——门禁必须落在"事件不写 state.sessionId"这类静态 / 行为断言上。

## 10. Historical Record

- 失败路径（已证伪）：用 `abort()` 取消旧请求（流硬中断 + 状态残留）；切换时清空全局 messages 与 DOM（丢失进行中流上下文）。
- Do Not Reopen Without Evidence：若再次出现流式跨会话中断，先确认是否代码回退（如去掉 D1–D4 规则之一），再检查是否新增了会 `abort()` 或修改 `state.sessionId` 的路径；不要不经确认直接重写事件处理。
