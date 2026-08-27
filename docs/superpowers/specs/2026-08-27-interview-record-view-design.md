# Spec：面试记录查看（列表 / 面试详情 / 逐题问答详情）

> 日期：2026-08-27
> 状态：待确认

## 1. 问题描述

用户反馈无法获取「面试记录、面试详细、每道问题的问答详情」。代码走读结论：**数据已完整落库，但读取链路断裂在 API 层与前端**：

| 层 | 现状 |
|---|---|
| 数据层 | ✅ 完整。SQLite `data/interviews.db` 有 `interview_sessions` + `interview_questions` 两张表，逐题的 question/answer/evaluation/score 均已存储，且 `get_session()` / `get_questions()` / `list_sessions()` 读取方法已存在（`app/storage/interview_store.py`） |
| API 层 | ❌ 缺口。仅有 `GET /history`（摘要列表）和 `GET /report/{session_id}`（汇总报告）。**`get_questions()` 从未暴露为接口**，逐题问答详情无任何途径获取；且报告接口对 `in_progress` 会话会自动触发 LLM 生成报告并落库（有副作用） |
| 用户隔离 | ❌ 缺失。表结构无 `user_id`，`history()` 不按登录用户过滤——所有用户的记录混在一起，且任何登录用户可读任意 `session_id`（越权） |
| 前端 | ❌ 缺口。`showHistoryDetail()` 只渲染报告汇总（总分/优劣势/建议），无逐题问答 UI；错误时仅 toast「报告加载失败」无原因 |

## 2. 影响模块 / 文件

| 文件 | 变更类型 |
|---|---|
| `app/storage/interview_store.py` | 修改：`interview_sessions` 增加 `user_id` 列（ALTER TABLE 兼容迁移）；`create_session` / `list_sessions` / `get_session` 增加 user 维度 |
| `app/services/interview_service.py` | 修改：`start()` 接收 user_id 并落库；`history()` 按用户过滤；新增 `get_detail()` 读取方法 |
| `app/api/interview.py` | 修改：各端点注入 `current_user`；`history` 传 username。新增：`GET /sessions/{session_id}/detail` 端点 |
| `frontend/js/app.js` | 修改：`showHistoryDetail()` 改为调用 detail 接口，渲染逐题问答；报告区块仅 completed 会话时请求 |
| `frontend/index.html` | 修改：复习视图详情面板新增逐题问答的 DOM 容器与样式 |
| `tests/` | 新增：用户隔离、详情接口、越权 404 的 pytest 用例 |

## 3. 预期行为（用户视角）

**流程 A — 查看面试记录列表**：用户登录 → 进入「复习」视图 → 显示**该用户自己**的面试记录列表（岗位、开始时间、状态徽章、轮数、总分）。

**流程 B — 查看面试详情与逐题问答**：点击列表中某条记录 → 详情面板展示：
- 会话元信息：岗位、状态、开始/完成时间、总分；
- 逐题列表（按 round 升序）：每题显示题目、难度/分类标签、我的回答、AI 评价（comment + 单题得分 + tags）；
- 未作答的题显示「未作答」占位，不显示空白或报错。

**流程 C — 进行中会话**：点击状态为「进行中」的记录 → 同样展示已作答题目的问答详情 + 顶部提示「该面试未完成」；**纯 SQLite 读取，不触发任何 LLM 调用、不改变会话状态**。

**流程 D — 异常路径**：
- 后端 401 → 前端触发既有 `handleAuthExpired()` 重新登录引导；
- 后端 404（记录不存在或不属于当前用户）→ 详情面板顶部显示「记录不存在」；
- 后端 500 → 详情面板顶部显示错误信息（含状态码），而非仅 toast。

## 4. 技术方案概要

**数据层**（`interview_store.py`）：
- `_init_db()` 中沿用现有 `ALTER TABLE ... try/except` 迁移模式，为 `interview_sessions` 追加 `user_id TEXT DEFAULT ''` 列；
- `create_session(user_id, position, ...)` 写入归属；`list_sessions(user_id, limit)` 加 `WHERE user_id = ?`；`get_session()` 原样保留（归属校验放 service 层）。

**API 层**（`interview.py`）：
- 端点签名统一改为 `current_user: dict = Depends(get_current_user)`，取 `current_user["username"]` 作为 user_id；
- `GET /api/interview/history`：`service.history(username)`，响应增加 `limit` Query 参数（默认 20）；
- **新增** `GET /api/interview/sessions/{session_id}/detail`：返回 `{"session": {...元信息}, "questions": [{id, round, question, answer, evaluation, score, difficulty, topic, category, created_at}, ...]}`；归属校验失败或不存在时抛 404；不生成报告、无副作用；
- `GET /report/{session_id}`：保持现状（仅 completed 会话），补充归属校验，并移除「自动生成报告」副作用。

**前端**（`app.js` + `index.html`）：
- `showHistoryDetail()` 改为：先 `GET /sessions/{id}/detail` 渲染元信息 + 逐题折叠面板（题目为标题，点击展开回答/评价）；
- `status === 'completed'` 时再 `GET /report/{id}` 渲染汇总报告区块；`in_progress` 则渲染「未完成」提示条；
- `!res.ok` 时在详情面板顶部渲染具体错误（状态码 + 后端 detail）。

**测试**（`tests/`）：
- 用户 A 创建的记录，用户 B 在 history 中不可见；B 直接请求 A 的 detail 返回 404；
- detail 接口返回逐题完整字段；in_progress 会话调用后 `status` 字段与 `report` 字段不变（验证无副作用）。

## 5. 验收标准

- [ ] 用户 A 在「复习」视图仅能看到自己创建的面试记录；用户 B 的记录不可见
- [ ] 列表每条显示：岗位、开始时间（格式化）、状态徽章（已完成/进行中）、轮数、总分
- [ ] 点击记录后，详情面板展示会话元信息 + **逐题问答列表**（题目/回答/AI 评价/单题得分/难度/分类）
- [ ] 未作答题目显示「未作答」占位
- [ ] 逐题查看**不触发 LLM 请求**（可通过后端日志 / OTel trace 验证，纯 SQLite 读取，2 秒内返回）
- [ ] 点击「进行中」的记录：显示已作答题目 + 「该面试未完成」提示，会话状态不被改变
- [ ] 访问不属于当前用户的 session_id：后端返回 404，前端显示「记录不存在」
- [ ] 后端返回 401：前端触发统一重新登录引导（复用现有 handleAuthExpired）
- [ ] 后端返回 500：详情面板顶部显示含状态码的错误信息
- [ ] 存量 `data/interviews.db`（无 user_id 的旧记录）迁移后服务可正常启动，旧记录可访问（归属策略见第 6 节 Q2）
- [ ] 新增 pytest 用例全部通过；`python -m pytest tests/` 无回归

## 6. 风险与未知点（需要确认）

**Q1. 具体现象**：用户说「无法获取」——是 (a) 接口报错（401/500）？(b) 列表为空？(c) 功能入口缺失？本 Spec 按「补全读取链路 + 增加用户隔离」设计；若实际是运行时报错，需提供现象（浏览器 Console / 后端日志），可能另有 bug。

**Q2. 存量数据归属**：现有 `interviews.db` 中的记录没有 user_id，如何处理？
- (a) 迁移时全部归给首个登录用户 / 指定账号；
- (b) `user_id = ''` 的记录对**所有登录用户可见**（共享池）；
- (c) 不处理（旧记录任何人都看不到）。
倾向 **(b)**，改动最小且不丢数据。

**Q3. 「进行中」会话是否需要恢复作答**（刷新页面后继续面试流程）？本 Spec 按「仅查看」处理，恢复作答不在范围内。

**Q4. 列表是否需要分页**？当前 `list_sessions` 固定 `limit=20`，方案中已支持 `limit` 参数，是否需要 `offset`/游标分页？

**Q5. deep_dive（简历项目深挖）模块**也有同构的记录查看缺口，是否一并处理？（建议本次不动，避免范围蔓延）

**技术风险**：
- evaluation 为 LLM 生成的非固定结构 dict，前端渲染需逐字段容错（缺失显示占位）；
- `report` 接口现有的「自动生成报告」副作用建议一并移除（查看不应改变状态），但这是行为变更，需确认。