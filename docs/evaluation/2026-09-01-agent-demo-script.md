# Agent 面试官 — 5 分钟 Demo 脚本（W3 Phase 1）

> 日期：2026-09-01　|　脚本：`scripts/agent_w3_demo.py`（可复现）　|　Trace 查看：`frontend/agent-trace.html`
> 只读端点：`GET /api/agent/traces/{session_id}`（Demo 定位，非产品能力；路径穿越防护，只读不建新存储）
> 环境证据：本脚本 2026-09-01 真实运行通过（真实 LLM + 真实 RAG + 真实 Redis 画像）。

---

## 0. Demo 前置环境

| 项 | 要求 | 说明 |
|---|---|---|
| 密钥 | 注入 Machine 级 `BAILIAN_API_KEY` / `SILICONFLOW_API_KEY` | DSH 沙箱过滤 env 继承，须运行命令显式注入，不落盘 |
| Redis（可选） | `REDIS_PASSWORD` 注入 | 提供 → 跨会话画像走真实 Redis；缺失 → 会话内降级（Demo 仍完整） |
| FAISS 索引 | `data/faiss_index/index.faiss` 存在 | 缺失时检索上下文为空（出题仍可用，source=llm） |
| 服务 | `python -m uvicorn app.main:app`（interview_mode=agent） | Trace 端点与静态页需要 |

运行：
```powershell
$env:BAILIAN_API_KEY=[Environment]::GetEnvironmentVariable('BAILIAN_API_KEY','Machine')
$env:SILICONFLOW_API_KEY=[Environment]::GetEnvironmentVariable('SILICONFLOW_API_KEY','Machine')
$env:REDIS_PASSWORD="..."          # 可选
python scripts/agent_w3_demo.py
```

## 1. 5 分钟主流程（脚本 5 个章节）

| 时间 | 章节 | 演示内容 | 预期 |
|---|---|---|---|
| 0:00-1:30 | 【1/5】正常流程 + FOLLOWUP | 真实出题（含 RAG 检索 context）→ 考生短答 → **自适应追问** → 追问答合并评估 → 难度调整（低分→easy）→ 多轮 → 报告 | 追问 source=followup 且独立 question_id；难度随分数下降 |
| 1:30-2:00 | 【2/5】Trace 归因 | 打印事件分布 + 四象限锚点 | 7 类事件；能指认 model/流程/数据/评估对应字段 |
| 2:00-3:00 | 【3/5】确定性降级 | LLM 挂→G1-F 兜底题→G4-F 规则分→逃生舱收尾；RAG 挂→工具 degrade 流程不断 | 兜底与逃生 trace 有记录 |
| 3:00-4:00 | 【4/5】跨会话画像 | Session A 低分→画像（accuracy/weak_points/level）→ Session B INIT 注入 | 目标难度=easy + 薄弱点进 prompt |
| 4:00-5:00 | 【5/5】再答一次 + 收尾 | generate_next=false 同题重评、状态不推进 | next_question=None |

## 2. 三个高光时刻

1. **归因 trace（章节 2）**：逐字段讲"模型能力（model/raw_output/validated）/ 流程设计（transition/retries/escape）/ 数据质量（tool_call 检索命中 / input_summary）/ 评估方式（fallback_used vs LLM 分）"——面试官直接看字段说话。
2. **确定性降级（章节 3）**：LLM 挂后流程不崩，G1-F 出模板题、G4-F 规则分、连续失败触发逃生舱强制收尾——"流程设计由确定性代码实现"的现场证明。
3. **跨会话画像（章节 4）**：一次低分面试改变下一次面试的难度起点与薄弱点注入——长期记忆不是 PPT，是可复现的链路。

## 3. 故障演练步骤（边界矩阵）

| 故障 | 注入方式 | 预期 fallback | 证据 |
|---|---|---|---|
| 正常流程 | — | — | 完整状态流 + report 落库 |
| LLM failure | `_FailingLLM`（chat 抛错） | G1-F 兜底题 → G4-F 规则分 → 连续失败逃生舱 | trace `fallback=question_fallback/eval_rule` + `escape` |
| RAG failure | `_FailingFacade`（retrieve 抛错） | kb_retrieve 工具 degrade，无上下文出题 | trace `tool_call ok=false` |
| Redis failure | 不注入 REDIS_PASSWORD | `make_profile_store` → 会话内画像降级 | 运行输出 "未注入（画像走会话内降级）" |
| schema retry/fallback | 模型输出非 JSON（mock/真实偶发） | 回填重试 ≤3 → 确定性兜底 | trace `retries` + `fallback` |
| escape hatch | `max_consecutive_failures=1` + LLM 挂 | FORCE_END → SUMMARIZING → 报告 | trace `escape` + `session_end` |
| generate_next=false | 前端"再答一次" | 同题重评、next_question=null、状态不推进 | 章节 5 |

## 4. Trace 查看方法

1. Demo 运行输出打印 `trace 文件：data/traces/{session_id}.jsonl`；
2. **只读端点**：`GET http://127.0.0.1:8000/api/agent/traces/{session_id}` → JSON 事件数组（count + events）；
3. **静态页**：`http://127.0.0.1:8000/agent-trace.html` → 输入 session_id → 按事件类型着色展示（transition 蓝 / node 紫 / tool 绿 / fallback 橙 / escape 红 / end 黑）；
4. 直读文件：`Get-Content data/traces/{session_id}.jsonl`（cat 逐条演示亦可）。

安全边界：端点只读、路径穿越防护（session_id 白名单）、不接导航、不建查询服务层（DR-016）；权限治理列入技术债 P1。

## 5. 预期结果 / 失败时的 fallback 路径

- **正常**：每章节输出 PASS 语义行；报告 total_score/level 落库；trace 7 类事件齐全。
- **真实 LLM 不可用（未注入 key）**：脚本在 main 入口直接退出并提示注入（401 场景请用 `scripts/agent_w1_smoke.py` 的降级场景演示）。
- **RAG 不可用**：自动降级无上下文出题（章节 1 的 source 可能为 llm）。
- **Redis 不可用**：跨会话画像走会话内（章节 4 仍演示，但跨进程不生效——讲解时说明生产形态为 Redis）。
- **偶发慢响应（>30s）**：LLMClient tenacity 自动重试 3 次；重试耗尽走节点兜底，Demo 不中断（可在章节 2 trace 中展示 retries 字段）。

## 6. 与 W3 验收的关系

- 5 分钟完整演示可执行：✅（2026-09-01 真实运行通过，脚本可复现）
- trace 可解释：✅（章节 2 四象限 + 静态页）
- 降级路径可复现：✅（章节 3 + 边界矩阵）
- 未新增 Tool / State / Memory / 模型供应商；未改 StateMachine / Agent API contract / frontend 交互；未做 LangGraph / OTel / 跨供应商。
