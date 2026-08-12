# AI 面试模块实现计划

## 分支
feature/ai-interview

## 依赖
- 基于 `origin/main` 最新代码
- 复用现有：RAGService（FAISS + Embedding 用于知识库出题）、LLMClient（出题/评价/报告）

## 实现步骤

### Step 1: 后端存储层 — InterviewStore
- 文件：`app/storage/interview_store.py`
- SQLite 表：interview_sessions, interview_questions
- 方法：create_session, add_question, update_question, get_session, get_session_questions, list_sessions, complete_session

### Step 2: 后端服务层 — InterviewService
- 文件：`app/services/interview_service.py`
- 依赖：LLMClient, FaissStore(可选), EmbeddingService(可选)
- 核心方法：
  - `start(position)` → 初始化面试 → 生成第一题
  - `_generate_question(session, context)` → 调用 LLM 出题
  - `answer(question_id, answer)` → 评价 → 出下一题或结束
  - `_evaluate_answer(question, answer)` → LLM 评价
  - `_generate_next_question(session, last_evaluation)` → 动态出题
  - `report(session_id)` → 生成完整报告
  - `history()` → 历史列表

### Step 3: 后端 API 层
- 文件：`app/api/interview.py`
- 端点：
  - POST /api/interview/start
  - POST /api/interview/answer
  - GET /api/interview/report/{session_id}
  - GET /api/interview/history
  - POST /api/interview/end/{session_id}（提前结束）

### Step 4: 注册到 main.py
- 导入 InterviewStore, InterviewService
- 初始化并注入到 lifespan
- 注册 interview router

### Step 5: 前端 — 面试页面 HTML
- 在 `frontend/index.html` 中新增 interview-view section
- 三个子区域：准备区、面试区、报告区
- 侧边栏新增"AI面试"导航项

### Step 6: 前端 — 面试样式
- 在 `frontend/css/style.css` 中追加面试相关样式

### Step 7: 前端 — 面试逻辑 JS
- 在 `frontend/js/app.js` 中追加面试逻辑
- 面试流程状态管理、API 调用、UI 渲染

### Step 8: 验证
- 启动后端服务，确认无报错
- 前端页面可正常打开，面试流程可走通