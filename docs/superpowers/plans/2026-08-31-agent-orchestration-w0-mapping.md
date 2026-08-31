# Agent 编排化改造 — Week 0：Spec → 现有代码实现映射

> 日期：2026-08-31　|　分支：`agent-dev`（基于 main `6a0e385` 冻结点）　|　依据：`2026-08-31-agent-orchestration-refactor-impl-spec.md` v2（已确认）
> 本阶段产出：① 真实接口核对 ② Spec→代码映射 ③ 契约冲突与决策点（OPEN）④ 前端契约确认结论。
> **本阶段未写任何业务代码。**

---

## 1. 分支与仓库状态

- `agent-dev` 已从 main 冻结点 `6a0e385` 创建并切换；三份设计文档已入分支（commit `31ace60`）。
- main 保持冻结，无新增提交。

## 2. 真实接口核对（逐一阅读源码，非假设）

### 2.1 `app/main.py`（装配点）
- 单例全部在 lifespan 装配：`faiss_store / embedding_service / llm_client / session_store / user_store / search_store / auth_service / query_rewrite_service / hybrid_retriever / rerank_service / response_cache / retrieval_facade / index_service / rag_service / resume_parser / interview_store / topic_tracker / interview_service / deep_dive_service / evaluation_service / testset_generator`。
- `interview_service = InterviewService(interview_store, llm_client, faiss_store, embedding_service, resume_parser=..., topic_tracker=..., facade=retrieval_facade)`（L199-204）。
- **`interview_mode` 工厂落点**：lifespan 内 `interview_service =` 赋值处按 `settings.interview_mode` 分支装配 legacy 或 `AgentService`。API 层 `_get_service()` 取 `app.main.interview_service`，无需改动。
- 依赖传递：AgentService 所需 `interview_store / topic_tracker / resume_parser / retrieval_facade / llm_client` 在装配点均已存在，agent 模式仅新增自身模块与 `profile_store`（W2下）。

### 2.2 `app/services/interview_service.py`（legacy 参照实现）
- 对外方法（API 层直接调用）：
  - `async start(position, username="", resume_file: Optional[UploadFile]=None, jd_text: Optional[str]=None) -> {session_id, question}` —— multipart，内含 resume/JD 解析（ResumeParser）+ 首题生成。
  - `async answer(question_id, answer, generate_next=True, username=None) -> {evaluation, is_complete, report?, next_question?, session_id}` —— **按 question_id 定位**，非 session_id。
  - `async end(session_id, username=None) -> {session_id, report}`
  - `async get_report(session_id, username=None)`（只读，不触发 LLM）
  - `get_detail(session_id, username=None)`（纯读取）
  - `history(username, limit=20)`、`stats(username)`、`async today(username, position=None)`
- 属性依赖（API 层直接访问）：`service.store.owns_session(...)`、`service.topic_tracker`（见 `app/api/interview.py` coverage 端点 L161-168）。
- 私有实现：`_generate_question(...)`（知识树/覆盖/检索注入/追问模式）、`_retrieve_context_with_sources(query)`（facade 优先 + raw FAISS 降级）、`_generate_report(session_id)`（LLM 报告 + 确定性 topic_analysis + 本地校正 score_breakdown）、`_parse_json(text)`（围栏剥离三段式）、`_difficulty_label(d)`。
- 常量：`max_rounds=15`、`min_rounds=5`、`followup_retrieval=settings.enable_interview_followup_retrieval`。

### 2.3 `app/services/retrieval_facade.py`（已核对全文）
- `async retrieve(query, top_k=None) -> FacadeResult{chunks, sources}`；`FacadeResult.to_text()`；`async rewrite(query)`。
- 全程吞异常返回空（DR-001 优雅降级），不抛。→ spec 工具 `kb_retrieve` 直接包 `facade.retrieve`。✅

### 2.4 `app/services/topic_tracker.py`（已核对全文，全同步无 LLM）
- `get_tree(position)`、`get_coverage(session_id, position)`、`get_next_suggestion(session_id, position)`、`suggest_prerequisites(topic_name, position)`、`get_coverage_summary_text(...)`、`get_tree_structure_text(position)`。
- → spec 工具 `pick_next_topic` 直接包 `get_next_suggestion`；薄弱点数据源供 `profile_store`（W2下）。✅

### 2.5 `app/storage/interview_store.py`（已核对全文，SQLite `data/interviews.db`）
- `create_session(position, username=...) / add_question(session_id, round_num, question, difficulty, source, topic, category) / update_answer(question_id, answer, evaluation, score) / complete_session(session_id, report) / update_analysis(...) / get_session / get_questions / get_current_question / list_sessions / owns_session / delete_session`。
- 表：`interview_sessions`（含 username 隔离、resume/JD 分析列）、`interview_questions`（含 topic/category/source/difficulty）。
- 注意：`add_question` 会 `UPDATE total_rounds = round_num`；`get_current_question` 按 `answer=''` 找最新未答。
- → agent 会话持久化直接复用；**follow-up 问题行打标方案见 OPEN-5**。✅

### 2.6 `app/services/llm_client.py`（已核对全文）
- `async chat(prompt, system=None, session_id=None) -> str`（非流式）；`async chat_stream(...)`。
- 内部：tenacity 3 次指数退避；`monitor.emit_cost(self.model, in_n, out_n, session_id)` 已接线（成本统计免费复用）。
- **关键约束**：`self.model = settings.bailian_model` 为实例属性，**`chat()` 不支持按调用覆盖 model** → model_gateway 分级（turbo/plus）需要最小扩展：`chat(..., model=None)`，payload 与 `emit_cost` 用实际模型名（向后兼容）。见 OPEN-2。

### 2.7 `app/api/interview.py`（API 层调用面，已核对全文）
- 端点：`POST /start`（multipart）、`POST /answer`（JSON `{question_id, answer, generate_next}`）、`POST /end`、`GET /report/{id}`、`GET /sessions/{id}/detail`、`GET /history`、`GET /stats`、`GET /today`、`GET /coverage`。
- 直接访问服务属性：coverage 端点 `hasattr(service,'topic_tracker')` + `service.store.owns_session(...)`。
- → **AgentService 必须镜像上述完整 surface（含 `store`/`topic_tracker` 属性），API 层才能零改动。** 见 OPEN-1。

### 2.8 前端契约（`frontend/js/app.js`，已核对行号）
| 端点 | 前端消费字段（行号） |
|---|---|
| start | `{session_id, question{id, content, round, difficulty, source, knowledge_tags, topic, category, sources?}}`（L1860-1863, 1988-2004） |
| answer | `{evaluation{score, comment, score_reason, reference_answer, tags, next_difficulty, should_end, sources?}, is_complete, report?, next_question?, session_id}`（L1876-1907, 1893, 1898, 1905） |
| end | `{session_id, report}`（L1950-1962） |
| report/detail/history/stats/today/coverage | 形状按 legacy 返回（L2014, 2229, 2255, 2301, 2348, 2442） |

**前端契约结论：AgentService 保持上述响应形状 + 端点不变，则前端零改动成立。** ✅

## 3. Spec → 代码映射表

| Spec 模块（附录 D） | 判定 | 映射/依据 |
|---|---|---|
| `state_machine.py` | 🆕 新建 | 无存量状态机（现存 `interview_agent.py` 是伪状态机，仅 PlannerContext+decide，无 enum/转移表/门禁；重写不演进） |
| `roles.py` | 🆕 新建 | prompt 样式可参考 legacy `QUESTION_PROMPT/EVALUATE_PROMPT/SYSTEM_START`（interview_service.py L29-122） |
| `structured_output.py` | 🆕 新建 | 复用 legacy `_parse_json`（L130-151）三段式提取思路 + 新增 jsonschema 校验 + 回填重试 |
| `tools.py` | 🆕 新建 | `kb_retrieve`→`facade.retrieve`；`pick_next_topic`→`topic_tracker.get_next_suggestion`；`get_profile/update_profile`→`profile_store`（W2下）；`mock_resume`→W2 MCP |
| `model_gateway.py` | 🆕 新建 | 依赖 `llm_client.chat`（需 OPEN-2 扩展）；成本经 `monitor.emit_cost`/`session_cost` 免费复用 |
| `mcp_client.py` | 🆕 新建（W2） | 依赖 `tools.py` 注册表降级 |
| `orchestrator.py` | 🆕 新建 | 事件循环 + 附录 A 转移表 + 附录 C 逃生舱 |
| `agent_service.py` | 🆕 新建 | **镜像 legacy 完整 surface（OPEN-1）**；组合依赖：store/topic_tracker/resume_parser/facade/llm |
| `profile_store.py` | 🆕 新建（W2下） | Redis；降级会话内；数据源复用 topic_tracker + stats 聚合 |
| `trace.py` | 🆕 新建 | 无存量 JSONL trace（OTel 为旁路，observability.py 已存在但不动） |
| `fallback.py` | 🆕 新建 | 兜底逻辑参考 legacy `_generate_question` 的解析失败兜底（L621-630）与 `_generate_report` 失败兜底（L815-823） |
| config 新增 | 🆕 追加 settings | 见 §6；沿用 `enable_*`/`interview_mode` 惯例 |
| 存量复用 | ♻️ 不动 | RetrievalFacade / TopicTracker / InterviewStore / ResumeParser / monitor / session_cost / eval_metrics / eval_testset |

## 4. 契约冲突与决策点（OPEN，按规则 8 报告，不自行改设计）

1. **OPEN-1｜AgentService 对外 surface**：spec E1 草图签名为 `start(user_id, position, resume_text)` / `answer(user_id, session_id, answer_text)`，与真实 API 面（multipart start、按 question_id answer、store/topic_tracker 属性依赖）不一致。**建议**：AgentService 镜像 legacy 完整 surface（含 `store`/`topic_tracker` 属性、`history/stats/today/get_detail` 只读方法），API 层与前端零改动成立。这符合 spec E1"与 legacy 同构、API 零改动"意图，属实现细节澄清。**需确认。**
2. **OPEN-2｜LLMClient 最小扩展**：model_gateway 分级（turbo/plus）需要 `llm_client.chat(..., model=None)` 支持按调用覆盖模型，且 `emit_cost` 用实际模型名。存量代码最小、向后兼容改动（默认 `self.model`）。**需确认**（agent-dev 上改存量文件，不动 main）。
3. **OPEN-3｜追问如何装入现有 answer 契约**：状态机 FOLLOWUP 阶段必须产出 legacy 形状响应。**建议**：主答 → 返回 `evaluation`（主答评估）+ `next_question`（追问，同 round）；追问答 → 返回 `evaluation`（本轮合并最终评估）+ `next_question`（下一主题）。一轮 = 两次 answer 调用，前端无需改动（用户见"评价→下一题（追问）→评价→下一题"）。**需确认。**
4. **OPEN-4｜"再答一次"路径**：前端 `generate_next=false`（再答一次）→ 需支持对同一 question_id 重新评估、状态不推进。spec 未提，需补进状态机（同题重评路径）。**需确认。**
5. **OPEN-5｜follow-up 问题行打标**：InterviewStore 零迁移方案 `source='followup'`（现有 source 取值 kb/llm/today），或加列。**建议**用 source 打标，避免迁移。**需确认。**
6. **OPEN-6｜报告生成归属**：agent SUMMARIZING 节点自实现报告生成（含画像更新），但**输出结构对齐 legacy report 形状**（total_score/score_breakdown/knowledge_analysis/improvement_suggestions/level/topic_analysis/recommended_study），保证 `showInterviewReport` 兼容；不调用 legacy `_generate_report`（其不含画像更新，且属冻结代码）。**需确认。**

> 以上 6 项均为接口适配决策，不改变架构与状态机语义；确认后写入 spec 附录 E 注释或 W1 实现。

## 5. 前端契约确认结论

✅ **无前端契约变更**。前提：AgentService 保持 §2.8 响应形状与端点不变（OPEN-1/3/4 的确认项即此前提的实现细节）。

## 6. config 新增清单（W1 实现时加入 `app/config.py`，禁魔法常量）

`interview_mode`(legacy|agent) · `agent_max_rounds`(15) · `agent_max_structured_retries`(3) · `agent_max_consecutive_failures`(3) · `agent_node_timeout_sec`(60) · `agent_max_transitions`(200) · `agent_max_reask_per_topic`(1) · `agent_followup_enabled`(true) · `agent_max_followup_depth`(1) · `agent_max_answer_chars`(2000) · `agent_max_context_chars`(4000) · `agent_trace_dir`(data/traces) · `agent_trace_retention`(200) · `agent_light_model`(qwen-turbo) · `agent_heavy_model`(qwen-plus) · `agent_parallel_candidates`(false)；`token_price` 增补 qwen-plus 单价。

## 7. 决策冻结（OPEN-1..6 已确认 + 三个补充发现）

> 2026-08-31 用户逐项确认。以下约束为实现硬约束，写入 W1 实现。

- **OPEN-1（已确认·镜像 legacy surface）**：AgentService 是 InterviewService 的替代实现；`interview_mode` 只负责 app.main lifespan 装配期选择；**不修改 app/api/interview.py**；Agent 核心逻辑只进 `app/services/agent/`；不复制 InterviewService/RAG/store/topic_tracker 逻辑；DI 复用 InterviewStore/TopicTracker/RetrievalFacade/LLMClient；Agent 不负责的方法经 adapter 兼容、不改 API contract。
- **OPEN-2（已确认·LLMClient 最小扩展）**：`chat/chat_stream` 加可选 `model=None`（不传用 `self.model`，向后兼容）；`emit_cost` 记录实际模型名；不引入第二套 HTTP；不提前实现跨供应商；**ModelGateway 只做策略选择（light→turbo、heavy→plus），不得绕过 LLMClient**。
- **OPEN-3（已确认·追问装入 answer 契约）**：W1 保留出题/评估/追问三角色；answer API 不新增字段；`next_question` 承载追问（同 round，复用 question_id 机制）；单问题最多 1 次 FOLLOWUP；禁止无限循环；逃生舱继续生效；不增加 Multi-Agent。
- **OPEN-4（已确认·同题重评）**：补 `generate_next=false` 路径——对同一 question_id 重新评估、状态不推进。
- **OPEN-5（已确认·source='followup'）**：见 §7.1 source 语义核对结论；followup 有独立 question_id；report/eval/coverage 统计过滤 followup；禁止计入主问题覆盖率。
- **OPEN-6（已确认·报告自实现）**：SUMMARIZING 由 Agent 自实现报告生成（确定性聚合 + LLM 自然语言 + schema 校验 + G8 兜底），输出结构严格对齐 legacy 报告形状；**不调用 legacy `_generate_report` 私有方法**。

### 7.1 补充发现 F7｜source 字段语义核对（OPEN-5 前置）

- 现状：`interview_questions.source` 由 `_generate_question` 设置（`parsed.get("source", "llm")`，prompt 指示 kb/llm），`today` 用 `'today'`，`add_question` 默认 `'kb'`。
- **全代码无任何逻辑按 source 值过滤/统计/报告**（grep 验证，仅展示性/记录性字段）。
- 结论：语义 = "题目生成来源/类型"，扩展 `'followup'` 作为"追问类型标记"兼容；无存量逻辑依赖，**安全**。
- 约束：followup 行有独立 question_id；`topic/category` 留空（coverage 天然跳过）；统计过滤见 §7.3。

### 7.2 补充发现 F8｜total_score 双重口径（影响画像正确率与对照评测，需冻结）

| 层 | 计算 | 前端展示 |
|---|---|---|
| 存储层 `interview_sessions.total_score` | **SUM(score)**（interview_store.update_answer L150-157） | history 列表"总分"（app.js L2318/2375） |
| 报告层 `report.total_score` | **AVG(score)**（_generate_report L735/774，round 1 位） | 报告"报告总分"（app.js L2104/2473） |

- **风险**：SUM 随题数膨胀，跨场次不可比；若画像"历史正确率"或对照评测误用 SUM，结论失真。
- **冻结建议（待确认）**：
  1. 画像历史正确率 = **近 N 次单题分均值**（N=10，跨场次按时间倒序，过滤 followup；兜底规则分计入并打标）；
  2. agent `report.total_score` = **均分**（与 legacy 报告口径一致，前端展示不变）；
  3. 对照评测**不依赖 total_score 字段**：用 recall@3/MRR（检索）+ 单题分分布（过滤 followup）+ 追问合理性人工分；
  4. `session.total_score`（SUM）仅保留作 legacy 展示兼容，agent 不据此做任何决策。

### 7.3 补充发现 F9｜只读端点职责归属 + 存量最小扩展点（待确认）

**职责归属**（用户要求核查）：

| 方法 | 归属 | 实现方式 |
|---|---|---|
| `start` / `answer` / `end` | **Agent 核心职责** | AgentService 自实现（状态机） |
| `get_report` / `get_detail` / `history` | 纯读 facade | AgentService 直读注入的 store（各数行，无业务逻辑复制） |
| `coverage`（属性访问） | 读 facade | AgentService 暴露 `store`/`topic_tracker` 属性，API 层直接访问（不改） |
| `stats` | 确定性聚合 facade | **委托** legacy 实例公开方法（不复制 60 行聚合逻辑） |
| `today` | 独立产品功能（非面试状态机） | **委托** legacy 实例公开方法 |

**存量最小扩展点（agent-dev 上向后兼容改动，与 OPEN-2 同类，待确认）**：
1. `LLMClient.chat/chat_stream(model=None)` —— OPEN-2 已确认。
2. `InterviewService.stats(..., exclude_sources=None)` 与 `TopicTracker.get_coverage(..., exclude_sources=None)`：默认 None 不过滤（legacy 行为不变），agent 模式传 `('followup',)`。若无此扩展，followup 行的 score 会被 stats 计入（污染薄弱点画像）、topic 会被 coverage 计入（污染覆盖率）——违反 OPEN-5 约束 3/4。
   - 替代方案（零存量改动）：followup 行不写 `answer`/`score`（stats 按 `answer==''` 跳过、coverage 按空 topic 跳过），追问链从 evaluation 字段取——但会丢失"追问回答"入库语义，且 `get_current_question`（answer='' 判未答）语义被污染。**不推荐**。

## 8. 状态

- ✅ 分支就绪；✅ 接口核对；✅ Spec→代码映射；✅ 前端契约（零改动）；✅ OPEN-1..6 已确认冻结；❌ 未写任何业务代码。
- **待确认**：F8 total_score 口径冻结建议 + F9 存量最小扩展点（stats/get_coverage source 过滤）。
- **确认后进入 W1 Day 1**。
