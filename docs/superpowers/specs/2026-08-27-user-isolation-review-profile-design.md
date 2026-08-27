# Spec：复习画像按用户生成 + 数据用户隔离

## 1. 问题描述

当前项目存在两个同根因问题：

1. **复习画像是全局的，不区分用户**：复习页的“薄弱点画像”与“今日一题”由 `app/services/interview_service.py` 的 `stats()` / `today()` 生成，其数据源是 SQLite `data/interviews.db` 中**所有已完成面试场次的聚合**（`list_sessions(limit=100)`，无任何用户过滤）。任何登录用户看到的画像、收到的今日一题都完全相同，且混入了其他用户的答题数据。
2. **用户数据无隔离**：`app/storage/interview_store.py` 的 `interview_sessions` / `interview_questions` 表没有 `username`/`user_id` 字段；虽然 `app/api/interview.py` 路由挂了 `Depends(get_current_user)` 登录门禁，但登录用户 A 可以通过 `/api/interview/report/{id}`、`/api/interview/answer`、`/api/interview/history` 等接口直接读写用户 B 的面试数据（水平越权）。

即：**有认证（Authentication），无授权隔离（Authorization/多租户隔离）**，复习画像因此无法“根据用户自身信息”生成。

## 2. 影响模块/文件

| 文件 | 影响 |
|------|------|
| `app/storage/interview_store.py` | **核心改动**：表结构加 `username` 列、迁移、按用户查询/校验归属 |
| `app/services/interview_service.py` | `start/stats/today/history/_generate_report` 等方法增加 `username` 参数并全链路传递 |
| `app/api/interview.py` | 路由从“仅门禁”改为“取当前用户并下传”；越权返回 403 |
| `frontend/js/app.js` | 复习页/面试页请求逻辑基本不动（fetch 已全局注入 JWT）；可选小改：画像标题显示当前用户 |
| `app/api/auth.py` | 不改，`get_current_user` 已返回 `{username, display_name, created_at}`，JWT `sub` 即 username |
| `data/interviews.db` | 存量数据迁移（归属标记） |
| `tests/` | 新增/更新用户隔离相关用例 |

不涉及：深挖模式（`deep_dive_service.py`）、RAG 问答主链路、聊天会话（Redis）、知识库文件、简历深挖记录——后三者的用户隔离不在本 Spec 范围（见风险 6.1）。

## 3. 预期行为（用户视角）

**前置**：用户通过现有登录页完成注册/登录，前端所有请求自动携带 `Authorization: Bearer <JWT>`。

1. 用户 A 登录后进入「AI 面试」完成若干场面试（题目、得分、评价正常落库，且记录归属 A）。
2. 用户 A 切到「复习」页：
   - 薄弱点画像卡片**只聚合 A 自己**的历史答题数据（分类、题数、均分、薄弱子知识点）；
   - 「今日一题」基于 **A 的最薄弱知识点**出题；A 无历史数据时按 A 的岗位方向随机出题并展示空态画像；
   - 面试历史列表只显示 A 的场次。
3. 用户 B 登录同一系统：复习页看不到任何 A 的数据；B 自己完成面试后，A/B 画像互不影响、互不可见。
4. 用户 B 若拿到 A 的 `session_id` 并调用报告/答题/结束接口，后端返回 **403**（无权访问该场次），前端展示错误提示而非静默失败。
5. 未登录或 token 失效时访问面试/复习接口，仍返回 401 并由前端引导重新登录（保持现有行为）。

## 4. 技术方案概要

### 4.1 数据层（`interview_store.py`）

- `interview_sessions` 表新增列 `username TEXT NOT NULL DEFAULT ''`，沿用现有启动时 `ALTER TABLE` 迁移模式（`_init_db` 中的加列循环）；
- 新增索引：`CREATE INDEX IF NOT EXISTS idx_is_user ON interview_sessions(username)`；
- `create_session()` 增加 `username` 入参并写入；
- `list_sessions(username: str | None)` 增加可选过滤（`WHERE username = ?`），画像/历史走用户过滤；
- `get_session()` 返回值带 `username`，供服务层做归属校验；
- **存量数据迁移**：启动时把 `username=''` 的存量场次统一归属到配置项 `LEGACY_DATA_OWNER`（`app/config.py` 新增，默认空）。默认空时存量数据不参与任何用户画像（视为未认领的旧数据），可通过 `.env` 指定归属账号一次性认领。

### 4.2 服务层（`interview_service.py`）

- `start(position, username, ...)`：创建场次时写入归属；
- `stats(username)`：只聚合 `username` 名下的已完成场次（复用现有聚合逻辑，仅收窄数据源）；
- `today(username, position)`：改为 `stats(username)` + 岗位默认取该用户**最近一场面试的 position**（替代硬编码 `"Java后端"`），无历史时回退全局默认岗位；
- `answer / end / get_report / coverage`：操作前校验 `session["username"] == 当前用户`，不匹配抛业务异常（映射 403）。

### 4.3 API 层（`app/api/interview.py`）

- 各 handler 增加 `current_user: dict = Depends(get_current_user)`，取 `current_user["username"]` 下传服务层（路由级 `dependencies` 保留或移除均可，以 handler 级注入为准）；
- 归属校验失败 → `HTTP 403 {"detail": "无权访问该面试场次"}`；
- 请求/响应模型（`app/api/schemas.py`）无结构性变更。

### 4.4 前端（`app.js`）

- 复习页/面试页接口调用**无需改动**（fetch 拦截器已全局带 JWT，见 `app.js` 顶部守卫）；
- 小改：复习页画像标题显示 `当前用户 display_name`（如“张三的复习画像”），数据为空时沿用现有空态文案；
- 403 响应统一在复习页/面试页展示后端 `detail` 错误信息（不触发 `handleAuthExpired`，它仅处理 401）。

### 4.5 不改动（明确边界）

- 不触碰 RAG 问答响应缓存逻辑（P001 缓存键铁律）、SSE 会话流程（P002）、rerank 选型（P003/P004）；
- 聊天会话（Redis）、知识库文件、简历深挖记录的隔离**暂不在本 Spec 范围**（见风险 6.1，待确认后可另立 Spec）。

## 5. 验收标准

- [ ] 用户 A 完成 2 场面试后登录查看复习页，`GET /api/interview/stats` 仅返回 A 的分类聚合数据
- [ ] 用户 B（无面试记录）登录后 `GET /api/interview/stats` 返回空 `categories`，前端展示空态文案“完成面试后，这里会聚合你的薄弱知识点。”
- [ ] A、B 各自有面试记录时，两人的 stats / today / history 结果互不包含对方数据
- [ ] `GET /api/interview/today` 对 A 基于 A 的最低均分薄弱点出题（可通过返回的 topic/category 验证）
- [ ] B 使用 A 的 `session_id` 调用 `GET /api/interview/report/{id}`、`POST /api/interview/answer`、`POST /api/interview/end` 均返回 403，前端展示错误信息
- [ ] 无 token / 无效 token 访问 `/api/interview/stats` 返回 401（现有行为不回退）
- [ ] 存量数据：设置 `LEGACY_DATA_OWNER` 后重启，旧场次出现在指定用户名下且画像包含其数据；不设置时旧数据不出现在任何用户画像中
- [ ] 用户 A 创建的新场次在 `interview_sessions` 表中 `username = 'A'`（SQLite 可查证）
- [ ] `python -m pytest tests/` 全量通过，其中包含：stats 按用户聚合、越权 403、存量迁移归属三类新用例

## 6. 风险与未知点（需要确认）

1. **隔离范围**：本 Spec 只覆盖“面试 → 复习画像”数据线。聊天会话（Redis `/api/sessions`）、知识库文件（`/api/files`，目前全局共享一套 FAISS 索引）、简历深挖记录同样没有用户隔离。是否：
   - a) 本次仅做面试/复习线（推荐，闭环最小）；b) 连聊天会话一起做；c) 全部隔离（知识库按用户分索引，工程量大，受单 worker 约束）？
2. **存量数据归属**：`data/interviews.db` 里已有的面试记录默认归谁？方案给了 `LEGACY_DATA_OWNER` 配置（可指定一个账号认领，或不配置则不参与画像）——是否符合预期，还是直接全部归属某个固定账号？
3. **“根据其信息”的边界**：画像数据源目前仅面试答题历史。是否还需要融合用户岗位（position）之外的输入，例如简历分析结论（`resume_analysis`）来加权薄弱点？默认方案不融合。
4. **今日一题的岗位来源**：前端目前调用 `/api/interview/today` 不传岗位参数，默认硬编码“Java后端”。改为“取该用户最近一场面试的岗位”是否可接受？