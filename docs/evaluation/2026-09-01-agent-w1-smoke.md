# Agent 编排化改造 — W1 Day 5 冒烟与验收报告

> 日期：2026-09-01　|　分支：`agent-dev`　|　依据：`docs/superpowers/specs/2026-08-31-agent-orchestration-refactor-impl-spec.md` v2
> 范围：W1 最后一天 —— 装配接线 + 真实 LLM 联调 + W1 验收（不扩展功能）
> 冒烟脚本：`scripts/agent_w1_smoke.py`（可复现）

---

## 1. 执行摘要

**冒烟 29/29 PASS；agent 单测 126 passed；存量关键测试（legacy planner/config）无回归。**

**重要环境限制（如实记录）**：`.env` 中 `BAILIAN_API_KEY` 无效（真实调用返回 `401 Unauthorized`，
网络可达但凭证失败；`BAILIAN_MODEL=qwen3.8-max` 亦非标准可用模型名）。因此**真实模型推理无法执行**。
Day 5 的处理方式：
- 真实客户端路径（`LLMClient` + 真实网络 + 真实 401）用于验证**失败降级矩阵**——这是当前密钥下
  Agent 的真实可观测行为（LLM 失败 → 重试 → 确定性兜底 → 流程完成；逃生舱 → 强制收尾）；
- 正常出题/追问/评估路径用**可工作模型适配器**跑在**真实工厂装配**上（真实 InterviewStore /
  TopicTracker / settings 配置 / 六工具注册表 / 状态机 / 逃生舱），证明装配与状态流本身正确。
- **真实模型可用后**（有效 key），可直接运行 `scripts/agent_w1_smoke.py` 场景 2 复验（适配器返回值
  替换为真实响应即可，无需改装配代码）。

## 2. 装配验证（interview_mode）

| 检查 | 结果 |
|---|---|
| `settings.interview_mode` 默认 `legacy`（存量行为不变） | PASS |
| agent 模式产物为 `AgentService`；legacy 模式产物仍为 `InterviewService` | PASS |
| agent surface 兼容 8 方法：start/answer/end/get_report/get_detail/history/stats/today | PASS |
| `store` / `topic_tracker` 属性（API coverage 端点直接访问） | PASS |
| `stats` 委托 legacy 且传 `exclude_sources=("followup",)` | PASS |
| API/frontend contract 零改动（API 层未修改；响应形状逐字段兼容） | PASS |

## 3. 真实运行链（真实装配 + 可工作模型适配器）

```
INIT → QUESTIONING → AWAITING_ANSWER → FOLLOWUP → AWAITING_ANSWER
     → EVALUATING → DIFFICULTY_ADJ → QUESTIONING → AWAITING_ANSWER
     → EVALUATING → DIFFICULTY_ADJ → SUMMARIZING → END
```
- start → 首题；短答 → 追问（next_question.source='followup'，独立 question_id）；追问答 →
  最终评估 + 下一题；第二轮 → 收尾 `is_complete=True`；report 落库 `status='completed'`；
  终态 `state=END`。**全链路 PASS。**

## 4. trace 校验（附录 H 7 类事件）

跨场景共 75 条 trace 事件，7 类齐全：
`transition / node_started / node_finished / tool_call / fallback / escape / session_end`。PASS。

## 5. 三个异常演练（全部 PASS）

| 异常 | 真实路径 | 结果 |
|---|---|---|
| schema 校验失败 → 回填重试 → 成功 | 注入非 JSON 输出 ×2 → 第 3 次成功（attempts=3） | PASS |
| LLM/工具失败 → 确定性降级 | 真实 LLMClient(401)：出题→G1-F 兜底题；评估→G4-F 规则分（score=5）；kb_retrieve 失败→degrade 跳过 | PASS |
| 逃生舱 → SUMMARIZING → END | `max_consecutive_failures=1` + LLM 失败 → escape 事件 → 强制收尾 + report | PASS |

## 6. W1 最终验收清单

| 项 | 状态 |
|---|---|
| legacy 可切换（interview_mode 装配，默认 legacy 行为不变） | ✅ |
| agent 真实装配闭环（状态流 + followup + 报告落库 + END） | ✅（模型推理待有效 key 复验） |
| trace 完整（7 类事件） | ✅ |
| report 落库（completed + total_score） | ✅ |
| Agent 测试全绿（126 passed） | ✅ |
| 存量关键测试无回归（legacy planner / config） | ✅ |

## 7. 已知限制（交付摘要必载项）

> **`AWAITING_ANSWER` 当前为单进程状态，Redis 持久化属于后续生产化范围。**
> 进程内 `SessionContext` registry 支撑 W1 单 worker 演示；断点恢复/重启恢复需在 W2/W3
> 生产化时以 Redis 会话存储实现（spec 附录 A1 持久化点）。

## 8. 遗留事项

- **有效 `BAILIAN_API_KEY` 待提供**：到位后运行 `python scripts/agent_w1_smoke.py` 场景 2/4/5
  复验真实模型推理路径（预期：happy path 以真实出题/评估/追问输出跑通；401 场景自动变为不可复现）。
- 本报告先于结论（PROCESS §1）：结论 = Agent 编排链路在真实装配下可运行、可降级、可归因；
  真实模型质量结论待有效密钥后补测。
