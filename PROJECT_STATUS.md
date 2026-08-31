# PROJECT_STATUS.md — 项目当前状态

> 性质：**当前状态快照**（只回答"现在走到哪一步"，不重复"过去做过什么"）。
> 生成日期：2026-09-01。事实基线：`git log` / `git status` / `git branch`（当前分支 `agent-dev`，main 冻结于 `6a0e385`）/ 代码核对（`app/config.py`、`app/services/agent/`、`app/services/cache_service.py`）/ `docs/evaluation/*`。
> 权威文档链：`AGENTS.md`（宪法）→ `ARCHITECTURE.md`（技术栈/模块）→ `DECISIONS.md`（DR）→ `PROBLEM.md`（问题注册表）+ `docs/problems/`（问题档案）→ `PROCESS.md`（流程）→ `docs/evaluation/`（实验证据）。

---

## 1. Current Thesis

**一句话**：这是一个从 RAG Demo 演进为**可评测、可降级、可观测、可持久化**的工程化 RAG 系统（面向 Java / 后端程序员面试场景），当前正在其上叠加**确定性编排 Agent 面试系统**（`agent-dev` 主线）。

三阶段演进主张：

1. **RAG Demo**（能跑通）：检索增强生成，回答知识库问题。
2. **工程化 RAG**（已完成）：检索质量用评测闭环量化、管线可配置可降级、缓存/SSE/持久化/隔离/成本控制全部工程化。
3. **确定性编排 Agent**（进行中）：把"面试官"从硬编码服务升级为状态机 + LLM 角色节点的可编排、可归因、可评测 Agent 系统（`interview_mode=legacy|agent`，默认 legacy）。

---

## 2. Current Phase

**Agent 编排化改造 W1（Week 0 决策冻结已完成，W1 骨架已落地）**：

- 分支 `agent-dev`（基于 main `6a0e385` 冻结点），main 保持冻结。
- W0（2026-08-31）：Spec→代码映射核对完成，OPEN-1..6 与 F7/F8/F9 决策冻结（commit `e88b8e0` / `6c44dd6` / `0fb5f38`）。
- W1（2026-09-01，Day 1–3）：状态机 / 门禁 / 逃生舱 / trace（`2e6cada`）、三角色 + 结构化输出（提取/校验/回填重试，`6de6a6e`）、Tool 层 + ProfileStore 会话内降级（`6694def`）均已落地并通过单测。
- W1 剩余：装配接线（`interview_mode` 工厂）、真实 LLM 联调——按 impl-spec v2（`docs/superpowers/specs/2026-08-31-agent-orchestration-refactor-impl-spec.md`）附录 D/A/B/C/E/F/H 推进。

> RAG 侧（Part A / Part B）已闭环完成，进入稳定维护态，仅按需跟随 agent 主线复用。

---

## 3. Current System Maturity

| 维度 | 能力 | 成熟度 |
|------|------|--------|
| **Core RAG** | ingestion（chunk 1000/200、断点续传）· retrieval（FAISS+BM25，RRF k=60）· rerank（SiliconFlow top-5）· generation（qwen-turbo，SSE）· evaluation（基线/消融闭环） | ✅ 生产可跑 + 有数据证明 |
| **Engineering** | cache（key 仅原始问题，已修复+回归）· session（Redis+SQLite 双层）· persistence（单 worker 落盘）· auth/isolation（JWT+username 透传）· SSE（多会话稳定）· graceful degradation（DR-001）· observability（OTel/metrics）· cost control（缓存/追问不检索/模型分级） | ✅ 已闭环（除门禁自动化） |
| **Product** | AI 面试（legacy 完整；agent 新实现 W1 骨架）· 简历深挖 · 复习画像 · 评测 | ✅ 功能就绪，agent 形态演进中 |
| **Agent 编排（新增主线）** | 确定性状态机（8 状态）· 门禁 G0..G9 · 全局逃生舱 · trace 归因 · 三角色 + 结构化输出重试 · Tool 层 + ProfileStore（已落地）；MCP 双工具 / 多模型分级（规划 W2） | 🚧 W1 收尾中 |

---

## 4. Key Completed Capabilities（只列已闭环）

- **检索评测闭环（Part A）**：`data/eval_testset.json`（手写核心集 + LLM 扩展集 120 条）→ 基线 → 4 组消融（qr × rr）→ 正式决策（commit `e404561`）。结论见 `docs/evaluation/retrieval_ablation_decision.md`。
- **统一检索门面（Part B）**：`RetrievalFacade` 抽出，问答与面试共用一条已验证管线；面试 MRR 0.559→0.588、recall 持平（commit `9bb26f9`）；追问默认不检索开关落地。
- **缓存 key 修复（P001 / DR-004）**：`make_key` 仅基于原始问题，+6 个回归测试（commit `e41788e`）。
- **用户隔离与双层持久化（DR-010）**：Redis 短期 + SQLite 长期 + username 逐层透传，越权 404。
- **降级链（DR-001）**：Redis 不可用→禁会话/缓存；BM25 缺失→FAISS-only；OTel 失败→静默；LLM 输出健壮解析（DR-008）。
- **可交付版本功能验收**：本地 RAG 问答 + 认证 + SSE 事件链全链路通过（`docs/evaluation/2026-08-29-local-smoke-acceptance.md`）。
- **Agent W1（Day 1–3）**：`state_machine.py`（8 状态 + 14 事件 + 门禁 + 逃生舱）、`trace.py`（JSONL 归因）、`roles.py`（三角色）、`structured_output.py`（jsonschema 校验 + 回填重试 + fallback 信号）、`tools.py`（本地工具注册表）、`profile_store.py`（会话内降级），全部带单测。

---

## 5. Key Evidence / Metrics（单一事实源：`docs/evaluation/retrieval_ablation_decision.md`）

| 配置 | 评测集 | n | recall@top-k | mrr | faithfulness |
|------|--------|----|:---:|:---:|:---:|
| qr_off · rr_off | 手写集 | 40 | 0.850 | 0.808 | 0.948 |
| qr_on · rr_off | 手写集 | 40 | 0.900 | 0.825 | 0.940 |
| qr_off · rr_on | 手写集 | 40 | 0.913 | 0.829 | 0.950 |
| qr_on · rr_on | 手写集 | 40 | 0.913 | **0.798** | **0.956** |
| 生产基线（全开） | 完整集 | 120 | 0.904 | 0.819 | 0.961 |

**读法（不是数字罗列）**：单模块开启均改善召回；**qr + rr 联合开启不产生叠加收益，MRR 反而回落（0.829→0.798）**——这是**排序问题而非召回问题**（recall 处峰值、faithfulness 最高）。结论：生产默认保留 `qr_on + rr_on`，回落信号列为 RRF k / rerank top_k / rewrite 策略的参数优化项，**不通过开关式关闭解决**。这一发现证明了"用实验决定 pipeline 配置，而非默认组件越多越好"。

**Part B 复试（面试子集 17 条）**：升级前（raw FAISS top-3）recall 0.588 / MRR 0.559 → 升级后（facade top-5）recall 0.588 / **MRR 0.588**，不劣于基线，达标。

**回归**：`python -m pytest tests/` 全量通过（Part B 验收时 143 passed）；agent W1 单测通过。

---

## 6. Blocking Issues（当前真实 blocker）

1. **W1 未收尾**：`interview_mode` 工厂装配接线 + 真实 LLM 联调未完成（状态机/结构化输出/工具层已落地）——agent 模式尚不可用。
2. **门禁自动化未落地**：PROBLEM.md Appendix Door 1–14 多数仍是"建议 Pytest/Lint"，未机器可执行（P001 的 Door 5 例外：已有回归测试）。
3. **agent 模式无对照评测**：legacy vs agent 的 17 样本对照表尚未产出（W2 下计划）。

---

## 7. Current Risks

1. **Agent 主线时间盒**：W1–W3 有严格砍单链（状态机+门禁 > 结构化输出+重试 > MCP 双工具 > 长期记忆 > 多模型分级 > LangGraph），超时必须砍，不得拖延。
2. **LLM 成本**：真实评测/联调消耗 API 额度（此前已遇免费额度耗尽）；基线 n=120 单次约 ~230 万 token。agent 联调应复用 Part A 的成本控制纪律（子集 + 控次数）。
3. **单 worker 硬约束（DR-002）**：FAISS/index/ingest_state 落盘假定单进程，Docker `--workers 1`；扩容需先补进程级锁。
4. **知识库质量短板（已登记 Part C）**：Java 集合类主题在面试检索中串题（`JAVA集合.md` 3 题全 miss，被 `test_java/Redis.md` 抢占）——属索引/基数质量，非管线问题，独立立项解决。
5. **前端契约**：agent 模式沿用 legacy 响应形状（start/answer/end/report）可零前端改动，但 demo 阶段 trace 含用户回答，展示时需人工把关。

---

## 8. Next Milestone

**W1 完成（最小闭环 demo）**：`interview_mode` 装配接线（`orchestrator.py` / `agent_service.py` / `app/main.py` 工厂）+ 真实 LLM 联调，达到"可演示最小闭环"。状态机/门禁/逃生舱/结构化输出/工具层已具备。

后续：W2 上（MCP 双工具 + model_gateway 分级）→ W2 下（legacy/agent 对照评测 + trace 断言报告落 `docs/evaluation/`）→ W3（演示打磨 + 话术训练 + LangGraph spike stretch）。

---

## 9. Exact Next Actions

1. **W1 剩余实现**（按 impl-spec v2 附录 D/A/C）：`orchestrator.py`（事件循环 + 逃生舱接线，复用已落地的 state_machine/trace）→ `agent_service.py`（镜像 legacy surface）→ `app/main.py` 装配 `interview_mode` 工厂。（roles/structured_output/tools/profile_store 已落地，勿重复实现。）
2. **联调与演示**：真实 LLM 跑通最小闭环，产出 W1 demo。
3. **文档同步（DoD）**：agent 模块落地后更新 `SERVICES_LAYER.md` 契约；agent 定稿后向 `DECISIONS.md` 沉淀新 DR（如"确定性编排 vs 自由循环"、"多模型分级"）。
4. **门禁自动化（P2）**：按 PROBLEM.md Appendix 将 Door 2/3/10/11（SSE/前端安全）等映射为可执行测试。
5. **Part C 立项（P2，独立）**：知识树驱动出题 query 优化（依赖知识树查询能力成熟确认）。

---

## 附：给下一会话的交接要点

- **当前卡点**：agent W1 Day 1–3 已落地（state_machine/trace/roles/structured_output/tools/profile_store + 单测），剩装配（orchestrator/agent_service/main 工厂）与真实 LLM 联调。
- **继续开发前**：`git status` + `git log --oneline -5` 确认工作区；主线在 `agent-dev`，main 冻结勿动。
- **铁律三连（不变）**：缓存 key 仅原始问题（DR-004/P001，已修复勿回退）；流式不改 `state.sessionId` / 不 `abort()`（DR-005/P002）；重排走 SiliconFlow API 禁本地 bge（DR-003/P003）。
- **实验纪律**：改检索/生成前必读 `PROCESS.md` §3（唯一变量、fresh 测试集、先结果后结论）；数据进 `docs/evaluation/`。
- **权威数字**：消融结论只在 `docs/evaluation/retrieval_ablation_decision.md`，其他文档引用不复制。
