# 问答历史的用户隔离与持久化（短期记忆 + 长期记忆）（Spec）

> 状态：待确认（风险点 §6 待用户选择后进入实现）
> 日期：2026-08-27

## 1. 问题描述

当前系统已具备 JWT 登录（`app/api/auth.py`）和 Redis 会话存储（`app/storage/session_store.py`），但问答历史存在三个缺陷：

1. **无用户隔离**：会话在 Redis 中以 `session:{session_id}` 存储，不含任何用户归属字段。
   - `GET /api/sessions` 全局扫描 `session:*`，任何登录用户都能看到**所有人**的会话列表（前端侧边栏因此共享）；
   - `GET /api/sessions/{id}`、`DELETE /api/sessions/{id}` 无归属校验，存在水平越权（可读/可删他人会话）；
   - `/api/query`、`/api/query/stream` 对传入的任意 `session_id` 直接写入；
   - `GET /api/search`（SQLite 全文搜索，`app/storage/search_store.py`）同样无用户过滤，能搜到他人问答内容。
2. **无长期保存**：Redis 会话 TTL=3600s，1 小时不活动即整体过期删除；重启 Redis 同样丢失。SQLite（`data/search.db`）虽然随每条消息同步写入（`rag_service.py:331-346`），但它**只服务于搜索**——`get_session_history` 仅从 Redis 读取，Redis 过期后用户永远找不回历史（即使 SQLite 里有完整数据）。
3. **术语定义**（本 Spec 语境）：
   - **短期记忆** = 当前会话的多轮上下文（Redis，供 LLM prompt 构建，已存在，需保留并加归属）；
   - **长期记忆** = 跨会话、跨 TTL/重启的历史问答持久化，按用户隔离，可列出、可回看、可继续对话。

## 2. 影响模块 / 文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `app/storage/session_store.py` | 修改 | session_data 增加 `username`；list/delete/clear 按用户过滤；维护 per-user 会话集合索引 |
| `app/storage/search_store.py` | 修改 | `sessions` 表加 `username`、`updated_at` 列（含存量库迁移）；`search()` 按 username 过滤；新增按用户列出会话/读取消息的方法 |
| `app/services/rag_service.py` | 修改 | `query/stream_query/create_session/get_session_history/delete_session/list_sessions/clear_all_sessions` 透传 username；增加“Redis miss → SQLite 恢复回填”逻辑 |
| `app/api/routes.py` | 修改 | 会话端点与 `/api/search` 注入 `current_user`，做归属校验（非本人 → 404） |
| `app/config.py` + `.env.example` | 修改 | 新增 `enable_history_persistence` 开关 |
| `frontend/js/app.js` | 微调 | 无结构性改动；历史会话恢复时 loading 提示（可选） |
| tests/ | 新增 | 用户隔离、持久化恢复的 pytest 用例 |

不改动：`user_store.py`（用户本体已在 Redis 持久存储，无 TTL）、interview/deep_dive 等其它 store（见风险第 6 条）。

## 3. 预期行为（用户视角 + 前后端交互流程）

1. **登录后只见自己的会话**：用户 A 登录，左侧边栏只显示 A 自己的历史会话列表；用户 B 登录后看不到 A 的任何会话。
2. **历史不过期**：A 昨天提过的问，今天（Redis TTL 早已过期）重新登录，侧边栏仍能看到昨天的会话（含标题、时间）。
3. **回看与续聊**：A 点击昨天的会话，完整消息记录加载显示；直接继续提问，AI 的回答能引用该会话之前的上下文（短期记忆被恢复）。
4. **删除即彻底删除**：A 删除会话后，刷新页面/换设备登录均不再出现，搜索中也搜不到。
5. **搜索只搜自己**：`/api/search` 全文搜索仅返回当前用户自己的历史问答。
6. **越权防护**：B 猜到/拿到 A 的 session_id，读取、删除、向其写入均被拒绝（404）。

## 4. 技术方案概要

**总体设计**：以 `username`（JWT `sub`，来自现有 `get_current_user`）作为隔离维度；**Redis = 短期热数据**（多轮上下文快路径，保持 TTL 3600s 不变），**SQLite = 长期事实源**（会话列表与消息的唯一可信来源，每条消息写入时已同步，本方案补齐读取与恢复路径）。

### 4.1 数据层

**SQLite（data/search.db）迁移**（`SearchStore._init_db` 内做幂等迁移）：

```sql
ALTER TABLE sessions ADD COLUMN username TEXT;      -- 存量行为 NULL(legacy)
ALTER TABLE sessions ADD COLUMN updated_at TEXT;
CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username);
```

`SearchStore` 新增方法：
- `list_user_sessions(username, limit=100) -> list[dict]`：按 `updated_at` 倒序列出该用户会话（含 title）；
- `get_messages(session_id) -> list[dict]`：按 id 顺序取全部消息（供恢复）；
- `touch_session(session_id, username, title)`：更新 `updated_at`（复用现有 `index_session` 并补列）；
- `search(keyword, username, limit)`：现有 FTS5 查询 JOIN sessions 后加 `WHERE s.username = ?`；
- `delete_user_sessions(username)` / `delete_session(session_id, username)`。

**Redis（SessionStore）**：
- `create_session(session_id, username)`：session_data 写入 `username`；
- 新增 per-user 索引 `SADD user_sessions:{username} {session_id}`（删除/清空时同步 SREM），`list_sessions(username)` 改为读集合而非全局 scan；
- `get_session` 返回值含 `username`，供归属校验；所有按 session_id 的操作先比对 `username`。

### 4.2 服务层（RAGService）

- 上述 7 个方法签名增加 `username: str`；`query/stream_query` 写入消息时同步 `search_store.touch_session(...)` 更新 `updated_at`；
- **恢复逻辑**（核心新增）：`get_session_history(session_id, username)` → Redis 有则直接返回；Redis miss 但 SQLite 有该会话且归属匹配 → 从 SQLite 读取全部消息 `rpush` 回填 Redis（刷新 TTL），返回历史；两边都没有 → 404；
- `list_sessions(username)`：优先合并 Redis 活跃会话与 SQLite 历史会话（以 SQLite 为准去重排序）；
- SQLite 任何异常：`logger.error` 后走 Redis-only 降级，不阻塞问答主线（遵循 D7/D8）。

### 4.3 接口层（routes.py）

| 接口 | 变更 |
|------|------|
| `GET /api/sessions` | 注入 `Depends(get_current_user)`，仅返回当前用户会话 |
| `POST /api/sessions` | 创建时绑定 `username` |
| `GET /api/sessions/{id}` | 归属校验；非本人 → 404；支持 SQLite 恢复 |
| `DELETE /api/sessions/{id}` | 归属校验；Redis + SQLite 同删 |
| `DELETE /api/sessions` | 语义从“全局清空”改为“清空当前用户全部会话” |
| `POST /api/query`、`/api/query/stream` | 传入他人 session_id → 404（不自动新建，避免历史串号） |
| `GET /api/search` | 增加 username 过滤 |

### 4.4 前端（app.js）

- `loadSessions()`/会话切换逻辑不变（后端已过滤、已恢复）；仅调整：登录用户切换后强制 `loadSessions()` 刷新（现已有）。

### 4.5 配置

- `enable_history_persistence: bool = True`：关闭时列表/恢复仅走 Redis（行为回到现状）。

## 5. 验收标准（可勾选清单）

**用户隔离**
- [ ] 用户 A、B 各自登录；A 创建会话并提问后，B 的 `GET /api/sessions` 列表不包含 A 的会话
- [ ] B 以 A 的 session_id 请求 `GET /api/sessions/{id}` → 404
- [ ] B 以 A 的 session_id 请求 `DELETE /api/sessions/{id}` → 404
- [ ] B 以 A 的 session_id 调 `POST /api/query`（含 stream）→ 404，且 A 的会话历史未被污染
- [ ] B 通过 `GET /api/search?q=关键词` 搜不到 A 的问答内容（用 A 提过的独特关键词验证）

**长期记忆（持久化与恢复）**
- [ ] A 提问后使 Redis 会话过期（等 TTL 或 `redis-cli DEL session:{id}` / `session:{id}:messages`），再调 `GET /api/sessions` 仍能看到该会话（来自 SQLite，含标题）
- [ ] 调 `GET /api/sessions/{id}` 返回完整消息历史（从 SQLite 恢复，顺序与角色正确）
- [ ] 恢复后继续提问，回答能正确引用恢复的上下文（验证 Redis 回填生效）
- [ ] 重启后端进程 + 重启 Redis，A 的历史会话与消息仍完整可见
- [ ] 删除会话后：Redis、SQLite 均无残留；`/api/search` 也搜不到已删内容

**短期记忆（回归）**
- [ ] 同一会话连续多轮提问，回答体现上下文（现有能力不回退）
- [ ] 超过 20 轮后仅最近 20 轮进入 prompt（`max_history_turns` 截断不回退）

**兼容与降级**
- [ ] 存量 `search.db`（sessions 无 username）启动迁移不报错，旧行标记 legacy、不出现在任何用户列表
- [ ] Redis 不可用时：问答仍成功（无多轮上下文），会话列表走 SQLite 仍可显示
- [ ] SQLite 写入失败时不阻塞问答响应，仅日志告警
- [ ] 响应缓存 key 仍仅基于原始问题，**未混入 username/session_id**（P001/D5 铁律回归测试）
- [ ] `python -m pytest tests/` 全部通过，含新增隔离与恢复用例

## 6. 风险与未知点（需确认）

1. **“长期记忆”的范围**：本 Spec 定义为“历史会话持久化 + 隔离 + 可续聊”。是否还需要**跨会话记忆**（新会话中自动引用该用户历史问答沉淀的偏好/知识点）？若需要，建议二期另立 Spec。
2. **存量数据处理**：Redis 中现存无归属会话 → 建议**不迁移，等 TTL 自然消亡**（≤1 小时）；SQLite 存量消息（无 username）→ 建议标记 legacy 不可见。还是你希望直接清空 `search.db` 重来？
3. **会话列表性能**：per-user Redis SET 索引（推荐，O(1) 列举）vs 维持全局 scan 过滤（改动小但会话多时慢）。默认按推荐实施？
4. **`DELETE /api/sessions` 语义变更**：从“全局清空”改为“清空当前用户”，是否接受？是否需要保留管理员级全局清理入口？
5. **越权时返回码**：统一 404（不暴露存在性）还是 403（明示无权）？本 Spec 默认 404。
6. **范围边界**：面试记录（`interview_store`）、简历深挖（`deep_dive_store`）目前同样无用户隔离，本 Spec 不含——是否需要一并处理（建议另开 Spec）？
7. **多端登录**：同一账号多处登录共享同一会话空间（本 Spec 默认如此），确认无冲突需求。