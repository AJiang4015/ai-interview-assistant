# 项目深挖 / RAG 评测 / Interview Agent 设计

## 1. 概述

本设计围绕三个能力展开，按优先级由前到后落地：

1. **项目经历深挖**：从简历项目中识别技术点，由"恶劣面试官"逐层对抗式追问，深挖用户真实掌握程度。
2. **RAG Evaluation**：构建固定测试集，量化评测检索与生成质量，让 RAG 效果"可证明、可对比"。
3. **Interview Agent**：将现有面试流程重构为 Planner 驱动的 Agent 编排，统一普通面试与项目深挖。

**核心目标：**
- 面试从"照题朗读"升级为"基于简历技术的对抗式深挖"，更贴近真实面试
- 用可复现的指标（Hit Rate / Recall / MRR + Faithfulness / Answer Relevance / Context Relevance）证明 RAG 改进
- 以统一的 Interview Agent + Planner 编排层承载上述能力，为后续扩展留出口

三个能力的依赖关系：#1、#2 作为独立能力先落地，#3 将 #1（新动作）与现有流程统一到同一套 Agent 骨架，并可选引用 #2 的评测上下文。

---

## 2. 功能一：项目经历深挖（Deep Dive）

### 2.1 架构

```
面试首屏「项目深挖」模式
      │
      ▼
DeepDiveService
      │            ┌─────────────┐
      ├───────────►│ ResumeParser │ 解析 projects[].technologies / skills
      │            └─────────────┘
      │            ┌─────────────┐
      ├───────────►│ LLMClient    │ 恶劣面试官 prompt（纯 LLM 驱动）
      │            └─────────────┘
      │            ┌─────────────┐
      └───────────►│ DeepDiveStore│ 深挖会话 & 追问链（SQLite）
                   └─────────────┘
```

### 2.2 状态机

```
SELECT_PROJECT → EXTRACT_TECH → SELECT_TECH → ASK
   → ANSWER → 判定（继续追问 / 换技术点 / 结束）
   → 兜底（达最大层数 或 用户答不上来）→ SUMMARY
```

- `SELECT_PROJECT`：从简历 `projects` 列表选择一个项目（默认第一个）。
- `EXTRACT_TECH`：取该项目 `technologies` 作为候选技术点；为空时由 LLM 从项目描述反推。
- `SELECT_TECH`：用户选一个技术点，或"随机出题"。
- `ASK`：恶劣面试官针对当前技术点 + 用户上一回答，出对抗式追问。
- `ANSWER`：用户作答，LLM 判定回答质量与是否"答不上来"。
- 每层回答后，用户选择：**继续追问 / 换个技术点 / 结束**。
- 兜底条件：达到最大层数（默认 5）或 LLM 判定用户答不上来 → 自动收尾。
- `SUMMARY`：生成深挖总结（薄弱点 + 标准答案要点），可并入复习页画像。

### 2.3 「恶劣面试官」Prompt 设计

核心是**挑战用户的选择**，而非索要知识点罗列。示例追问逻辑：

- 用户自称用了某项技术 → "为什么不直接 X？"（质疑必要性）
- 用户给出方案 → "你用的是 A 还是 B？"（要求精确归因）
- 用户给出归因 → "为什么？"（要求原理）
- 用户给出原理 → "规模从 20 到 1000，方案还能用吗？"（要求边界与扩展性）

Prompt 约束：单轮只问一个问题，语气对抗但不攻击人格，追问必须基于用户上一回答，不能自问自答。

### 2.4 存储

复用 `interview_store`，新增深挖相关表：

- `deep_dive_sessions`：id、project_name、tech_point、status、fraud/薄弱点摘要、created_at
- `deep_dive_questions`：id、session_id、round、question、answer、score、llm_judgment

### 2.5 错误处理

- 简历未上传或无可识别技术点：提示用户补全简历或手动输入技术点。
- LLM 追问解析失败：回退为通用追问 prompt，保证流程不中断。
- 用户中途退出：以当前追问链生成部分总结。

---

## 3. 功能二：RAG Evaluation

### 3.1 架构

```
知识库 chunk ──► TestSetGenerator ──► data/eval_testset.json
                                          │
                                          ▼
                              StrategyRunner（管线开关：hybrid/rerank）
                                          │
                                          ▼
                              Evaluator（Retrieval + Generation 指标）
                                          │
                                          ├──► data/eval_reports/*.json
                                          ▼
                              前端「RAG 评测」板块（对比表/图表）
```

### 3.2 测试集

- 自动生成：对每个知识库 chunk，让 LLM 反推一个问题；`expected_answer` 取 chunk 内容，`expected_source` 取 chunk 来源文件。
- 存储：`data/eval_testset.json`，结构 `[{question, expected_answer, expected_source, source_file}]`。
- 幂等：支持"追加生成"与"按 source_file 去重"，避免重复建集。

### 3.3 策略对比（管线开关）

复用现有 RAG 管线开关（`app/config.py` 的 `enable_hybrid_search` / `enable_rerank`），对比以下配置：

| 配置 | 说明 |
|---|---|
| hybrid + rerank | 全量管线（当前生产配置） |
| dense-only | 仅 FAISS 向量检索，无混合、无重排 |
| no-rerank | 混合检索但不做重排 |

### 3.4 指标

**Retrieval（纯代码计算，无需 LLM）**
- `Hit Rate@k`：期望来源是否出现在 top-k
- `Recall@k`：期望来源命中数 / 期望来源总数
- `MRR@k`：首个命中期望来源的倒数排名

**Generation（LLM-as-judge，逐条打分取均值）**
- `Faithfulness`：回答是否忠于检索上下文（无幻觉）
- `Answer Relevance`：回答是否切题
- `Context Relevance`：检索上下文对问题是否相关

### 3.5 报告落盘

`data/eval_reports/{timestamp}.json`，含各策略的 Retrieval 均值、Generation 均值、逐条明细与对比表。

### 3.6 错误处理

- 知识库为空 / 测试集为空：提示先构建索引或先生成测试集。
- LLM-as-judge 调用失败：该条 Generation 指标置空并在报告中标注，Retrieval 指标不受影响。
- 评测为异步长任务：前端轮询进度，避免阻塞。

---

## 4. 功能三：Interview Agent（Planner 重构）

### 4.1 架构

```
               Interview Agent
                  │       三路上下文
      ┌───────────┼───────────┐
      ↓           ↓           ↓
   知识检索     面试题库     用户历史/简历
      └───────────┼───────────┘
                  ↓
            Interview Planner       ← 决策 ask/evaluate/retrieve/report
                  │
      ┌───────────┼───────────┐
      ↓           ↓           ↓
   出题工具     评分工具     知识库工具
      └───────────┼───────────┘
                  ↓
               下一动作
```

### 4.2 动作集

Planner 依据当前状态输出一个动作：

| 动作 | 说明 |
|---|---|
| `ask_question` | 出下一题（普通面试 / 项目深挖统一走此动作） |
| `evaluate_answer` | 评价回答、更新覆盖统计 |
| `retrieve_knowledge` | 检索知识库以支撑出题/追问 |
| `generate_report` | 生成面试/深挖报告 |

### 4.3 与现有代码的关系

- **重构** `app/services/interview_service.py`：将「出题→评价→报告」的隐式流程显式化为 Planner 决策循环。
- 现有 `TopicTracker`、`ResumeParser`、`RetrievalService` 作为**工具**注入 Agent。
- 项目深挖（功能一）作为新动作类型接入：`ask_question` 时若模式为 deep_dive，走恶劣面试官追问逻辑。
- 保持现有 API（`/start`、`/answer`、`/end`、`/report`）对外契约不变，避免前端大改。

### 4.4 数据流

1. Agent 收集三路上下文（知识检索结果、题库状态、用户历史/简历画像）。
2. Planner 综合上下文决定当前动作。
3. 执行对应工具，产出输出。
4. 更新会话状态，Agent 依据新状态决定下一动作。

### 4.5 错误处理

- Planner 决策异常：回退到默认动作（普通面试默认 `ask_question`），保证流程不断。
- 工具失败（如检索不可用）：降级为纯 LLM，不阻塞面试。

---

## 5. 前端改动

- **面试首屏**：新增「项目深挖」模式入口，与普通面试并列。
- **深挖交互**：复用现有面试进度/回答/评价 UI，追加「继续追问 / 换个技术点 / 结束」按钮；结束展示深挖总结。
- **评测板块**：在设置页或复习页新增「RAG 评测」，含"生成测试集 / 运行评测"按钮与对比表/图表。
- **主导航**：保持不变（AI面试 / 复习 / 问答 / 设置）。

---

## 6. 实施顺序与范围界定

按优先级拆分，每阶段独立可交付：

1. **阶段一（功能一）**：项目深挖 —— 新的独立模式 + 前端入口 + 存储。
2. **阶段二（功能二）**：RAG 评测 —— 测试集生成 + 指标计算 + 前端评测板块。
3. **阶段三（功能三）**：Interview Agent 重构 —— 将普通面试与项目深挖统一到 Planner 编排。

**明确不在本期范围：**
- 不引入新的 LLM 提供商或向量库（复用现有 Qwen/Bailian、FAISS）。
- 不改变现有 API 对外契约（内部重构）。
- 不做多用户权限隔离（沿用现有单机会话模型）。

---

## 7. 测试与验收

- **功能一**：上传含 RAG/Rerank 的简历，验证技术点识别、对抗式追问续接、达层数与答不上来自动收尾、总结生成。
- **功能二**：对现有知识库生成测试集并运行评测，验证 Hit Rate / Recall / MRR 与三个 Generation 指标落盘，三策略对比表可读。
- **功能三**：普通面试全流程回归（start→answer→end→report）不回归；项目深挖作为动作接入后正常。