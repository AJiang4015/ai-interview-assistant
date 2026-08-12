# AI 面试模块设计文档

## 概述

将当前 RAG 问答系统扩展为真正的 AI 面试系统。用户选择岗位后，AI 主动出题、评价回答、动态调整难度，最终生成面试报告。

## 用户流程

```
选择岗位 (Java后端 / AI应用开发)
      ↓
选择面试模式 → 混合模式（技术点+项目+系统设计混合）
      ↓
AI 生成第一道题（知识库优先，LLM 补充）
      ↓
用户回答
      ↓
AI 评价（评分 + 评语 + 知识点标记）
      ↓
AI 根据回答动态决定下一题（调整难度/方向）
      ↓
...循环（至少 5 题，最多 15 题，用户可随时结束）
      ↓
生成面试报告（评分 + 知识点分析 + 提升建议 + 能力评级）
```

## 架构

### 前端

- 侧边栏新增"AI面试"导航项
- 新增面试页面，分三个子状态：
  - **准备阶段**：选择岗位 → 开始面试
  - **面试阶段**：题目展示 → 用户输入回答 → 评价展示 → 下一题
  - **报告阶段**：完整面试报告展示

### 后端

新增 `InterviewService`，核心方法：

| 方法 | 说明 |
|------|------|
| `start(position)` | 初始化面试场次，生成第一道题 |
| `answer(question_id, answer)` | 提交回答，返回评价 + 下一题（或结束信号） |
| `report(session_id)` | 生成并返回面试报告 |
| `history()` | 历史面试列表 |

### 出题策略（知识库优先，LLM 补充）

```
1. 从 FAISS 知识库中检索与当前岗位/方向相关的文档片段
2. 用 LLM 基于检索到的内容生成题目
3. 如果知识库内容不足，LLM 基于自身知识补充出题
4. 每轮出题时考虑：前一轮评价、已覆盖知识点、难度动态调整
```

### 评价策略

每轮回答后，AI 给出：
- **评分**：1-10 分
- **评语**：优缺点的简要分析
- **知识点标记**：本题涉及的知识点标签
- **难度调整**：根据回答质量决定下题难度（偏难/适中/偏易）

### 数据模型

**interview_sessions**（SQLite）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT (UUID) | 场次 ID |
| position | TEXT | 岗位 |
| status | TEXT | in_progress / completed |
| total_rounds | INT | 总题数 |
| total_score | FLOAT | 总分 |
| completed_at | TEXT | 完成时间 |
| report | TEXT (JSON) | 面试报告 |

**interview_questions**（SQLite）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT (UUID) | 题目 ID |
| session_id | TEXT | 所属场次 |
| round | INT | 第几题 |
| question | TEXT | 题目内容 |
| answer | TEXT | 用户回答 |
| evaluation | TEXT (JSON) | 评价详情 |
| score | FLOAT | 本题得分 |
| difficulty | TEXT | easy/medium/hard |
| source | TEXT | 题目来源（知识库/LLM补充） |

### API 端点

```
POST /api/interview/start      → { position: "Java后端" }
  → { session_id, question: {id, content, round, difficulty} }

POST /api/interview/answer     → { question_id, answer }
  → { evaluation: {score, comment, tags}, 
      next_question: {id, content, round, difficulty} | null,
      is_complete: false }

GET  /api/interview/report/{session_id}
  → { session_id, position, total_rounds, total_score,
      score_breakdown: [{round, question, score, tags}],
      knowledge_analysis: {strengths: [...], weaknesses: [...]},
      improvement_suggestions: [...],
      level: "初级/中级/高级" }

GET  /api/interview/history
  → [{ session_id, position, total_rounds, total_score, completed_at }]
```

### 与现有 RAG 功能的关系

- 完全独立：面试数据存 `data/interviews.db`，问答数据存 `data/search.db`
- 面试中仍可复用 RAG 的检索能力（知识库出题）
- 侧边栏导航新增"AI面试"选项，两个功能互不干扰