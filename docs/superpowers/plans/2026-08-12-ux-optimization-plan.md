# 用户体验优化 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复三个用户体验功能的 8 个安全、性能和正确性问题，不新增功能。

**Architecture:** 最小修复方案：前端添加 DOMPurify 防 XSS + 流式 Markdown 无高亮渲染 + 文件大小前端校验 + 相对时间显示；后端修改时间格式为 ISO + 上传改为后台索引重建 + 搜索改用 SQLite FTS5 + 过期会话 404 处理。

**Tech Stack:** JavaScript (vanilla), Python/FastAPI, SQLite FTS5, DOMPurify CDN, marked.js, highlight.js

## Global Constraints

- 不新增功能，只修复正确性、安全性和性能问题
- Redis 服务地址固定为 192.168.127.101
- 原 messages 表保留，FTS5 作为独立虚拟表
- 前端无构建工具，所有依赖通过 CDN 引入

---

## File Structure

| 文件 | 职责 | 变更类型 |
|------|------|----------|
| `frontend/index.html` | HTML 入口，引入 CDN 依赖 | 修改：添加 DOMPurify |
| `frontend/js/app.js` | 前端核心逻辑 | 修改：Markdown 渲染、文件管理、搜索 |
| `app/api/routes.py` | API 路由 | 修改：时间格式、异步重建、404 |
| `app/storage/search_store.py` | SQLite 搜索存储 | 修改：FTS5 升级 |

---

### Task 1: Markdown 渲染 — XSS 防护 + 流式性能优化

**Files:**
- Modify: `frontend/index.html` —— 添加 DOMPurify CDN
- Modify: `frontend/js/app.js` —— 更新 renderMarkdown、新增 renderMarkdownNoHighlight、修改 token 和 done 事件、修改 renderMessages 的 pending 渲染

**Interfaces:**
- Produces: `renderMarkdownNoHighlight(text: string) → string` —— sanitized HTML，无代码高亮
- Modifies: `renderMarkdown(text: string) → string` —— 输出现在经过 DOMPurify 消毒
- Modifies: token 事件处理 —— 使用 renderMarkdownNoHighlight（无高亮 Markdown 渲染）
- Modifies: done 事件处理 —— 使用 renderMarkdown（含高亮 + DOMPurify）
- Modifies: `renderMessages()` pending stream 渲染 —— 使用 renderMarkdownNoHighlight

- [ ] **Step 1: 在 index.html 添加 DOMPurify CDN**

在 `frontend/index.html` 第 11 行之后添加：

```html
    <script src="https://cdn.jsdelivr.net/npm/highlight.js@11.9.0/highlight.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js"></script>
```

- [ ] **Step 2: 更新 renderMarkdown() 添加 DOMPurify 消毒**

在 `frontend/js/app.js` 中，修改 `renderMarkdown()` 函数（L406-L417）：

```javascript
// 修改前
function renderMarkdown(text) {
    if (!text) return '';
    const html = marked.parse(text, { breaks: true, gfm: true });
    const wrapper = document.createElement('div');
    wrapper.innerHTML = html;
    wrapper.querySelectorAll('pre code').forEach(block => {
        hljs.highlightElement(block);
    });
    return wrapper.innerHTML;
}

// 修改后
function renderMarkdown(text) {
    if (!text) return '';
    const html = marked.parse(text, { breaks: true, gfm: true });
    const wrapper = document.createElement('div');
    wrapper.innerHTML = DOMPurify.sanitize(html);
    wrapper.querySelectorAll('pre code').forEach(block => {
        hljs.highlightElement(block);
    });
    return wrapper.innerHTML;
}
```

- [ ] **Step 3: 新增 renderMarkdownNoHighlight() 函数**

在 `renderMarkdown()` 函数之后（L417 之后）添加：

```javascript
// 流式渲染用：Markdown 格式化 + DOMPurify 消毒，不含代码高亮（性能优化）
function renderMarkdownNoHighlight(text) {
    if (!text) return '';
    const html = marked.parse(text, { breaks: true, gfm: true });
    return DOMPurify.sanitize(html);
}
```

- [ ] **Step 4: 修改 token 事件中的流式渲染**

在 `frontend/js/app.js` 中，修改 token 事件处理（L590-L598），将 `renderMarkdown(accumulatedContent)` 替换为 `renderMarkdownNoHighlight(accumulatedContent)`：

```javascript
// 修改前
const tokenDiv = getStreamingContentDiv(finalSessionId);
if (tokenDiv) {
    tokenDiv.innerHTML = renderMarkdown(accumulatedContent);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

// 修改后
const tokenDiv = getStreamingContentDiv(finalSessionId);
if (tokenDiv) {
    tokenDiv.innerHTML = renderMarkdownNoHighlight(accumulatedContent);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}
```

- [ ] **Step 5: 修改 done 事件中的渲染**

在 `frontend/js/app.js` 中，修改 done 事件处理（L630-L636）。原有代码使用 `renderMarkdown(accumulatedContent)` 保持不变（done 事件时做完整渲染含高亮），但需确认 `renderMarkdown` 现已包含 DOMPurify。

**无需修改**——done 事件中 `renderMarkdown(accumulatedContent)` 的调用不需要改动，因为第 2 步已更新 `renderMarkdown()` 内部实现。

- [ ] **Step 6: 修改 renderMessages() 中 pending stream 的渲染**

在 `frontend/js/app.js` 中，修改 `renderMessages()` 函数内 pending stream 的渲染（L324）：

```javascript
// 修改前
contentDiv.innerHTML = renderMarkdown(pending.accumulatedContent) || '<span class="streaming-cursor"></span>';

// 修改后
contentDiv.innerHTML = renderMarkdownNoHighlight(pending.accumulatedContent) || '<span class="streaming-cursor"></span>';
```

- [ ] **Step 7: 验证**

```bash
# 启动服务
cd e:\CodeField\RAGKonwLedge
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

验证点：
- 提问一个会返回代码块的 Java 问题（如"HashMap 的扩容机制"），观察流式输出过程中 Markdown 格式正常显示（标题、列表、粗体等），代码块初始为纯文本
- 流式完成后，代码块自动高亮
- 打开浏览器 DevTools Console，确认无 JavaScript 错误

---

### Task 2: 文件管理 — 时间格式 + 前端校验

**Files:**
- Modify: `app/api/routes.py` —— `list_files()` 中 modified_time 改为 ISO 格式
- Modify: `frontend/js/app.js` —— 新增 `formatRelativeTime()`、修改 `loadFileList()` 和 `handleFileUpload()`

**Interfaces:**
- Produces: `formatRelativeTime(isoStr: string) → string` —— 人类可读的相对时间
- Modifies: `loadFileList()` —— 文件列表中的 file-meta 使用 formatRelativeTime
- Modifies: `handleFileUpload(files: FileList)` —— 开头添加文件大小校验

- [ ] **Step 1: 后端 modified_time 改为 ISO 格式**

在 `app/api/routes.py` 中，修改 `list_files()` 函数（L215-L240），将 `str(stat.st_mtime)` 替换为 ISO 格式。需要先在文件顶部添加 `from datetime import datetime`：

```python
# 文件顶部添加（如果尚未导入）
from datetime import datetime

# 在 list_files() 中修改（L236）
# 修改前
modified_time=str(stat.st_mtime),

# 修改后
modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
```

- [ ] **Step 2: 前端新增 formatRelativeTime() 函数**

在 `frontend/js/app.js` 中，在 `formatFileSize()` 函数之后（L859 之后）添加：

```javascript
// 格式化相对时间：ISO 字符串 → "2 小时前"
function formatRelativeTime(isoStr) {
    const date = new Date(isoStr);
    const now = new Date();
    const diff = (now - date) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
    if (diff < 2592000) return `${Math.floor(diff / 86400)} 天前`;
    return date.toLocaleDateString('zh-CN');
}
```

- [ ] **Step 3: 修改 loadFileList() 使用 formatRelativeTime**

在 `frontend/js/app.js` 中，修改 `loadFileList()` 函数中文件列表的 file-meta 渲染（L887）：

```javascript
// 修改前
<div class="file-meta">${formatFileSize(f.size)} · ${f.file_type.toUpperCase()}</div>

// 修改后
<div class="file-meta">${formatFileSize(f.size)} · ${f.file_type.toUpperCase()} · ${formatRelativeTime(f.modified_time)}</div>
```

- [ ] **Step 4: 修改 handleFileUpload() 添加前端文件大小校验**

在 `frontend/js/app.js` 中，修改 `handleFileUpload()` 函数开头（L903-L906）：

```javascript
// 修改前
function handleFileUpload(files) {
    if (!files || files.length === 0) return;

    const file = files[0];
    const formData = new FormData();

// 修改后
function handleFileUpload(files) {
    if (!files || files.length === 0) return;

    const file = files[0];
    const MAX_SIZE = 50 * 1024 * 1024; // 50MB
    if (file.size > MAX_SIZE) {
        showToast(`文件大小超过限制（${formatFileSize(MAX_SIZE)}），请压缩后重试`, 'error');
        return;
    }

    const formData = new FormData();
```

- [ ] **Step 5: 验证**

```bash
cd e:\CodeField\RAGKonwLedge
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

验证点：
- 切换到「知识库」标签页，确认文件列表中的时间显示为"2 小时前"等人类可读格式
- 尝试选择一个超过 50MB 的文件，应弹出错误提示，不发起上传请求
- 正常上传一个小文件，确认上传成功

---

### Task 3: 文件管理 — 上传时异步索引重建

**Files:**
- Modify: `app/api/routes.py` —— `upload_file()` 改为后台索引重建

**Interfaces:**
- Modifies: `POST /api/files/upload` —— 返回 `index_rebuilt: false`，索引在后台重建

- [ ] **Step 1: 添加 asyncio 导入**

在 `app/api/routes.py` 文件顶部添加：

```python
import asyncio
```

- [ ] **Step 2: 修改 upload_file() 为后台索引重建**

在 `app/api/routes.py` 中，修改 `upload_file()` 函数（L273-L291）：

```python
# 修改前（L273-L291）
    # 自动重建索引
    indexer = _get_indexer()
    try:
        result = await indexer.build_index(rebuild=True)
        return FileUploadResponse(
            success=True,
            filename=filename,
            message=f"文件上传成功，索引已重建",
            index_rebuilt=True,
            total_chunks=result.total_chunks
        )
    except Exception as e:
        logger.exception(f"Index rebuild after upload failed: {e}")
        return FileUploadResponse(
            success=True,
            filename=filename,
            message=f"文件上传成功，但索引重建失败: {e}",
            index_rebuilt=False
        )

# 修改后
    # 后台异步重建索引，不阻塞上传响应
    async def rebuild_index_background():
        try:
            indexer = _get_indexer()
            result = await indexer.build_index(rebuild=True)
            logger.info(f"Background index rebuild done: {result.total_chunks} chunks")
        except Exception as e:
            logger.exception(f"Background index rebuild failed: {e}")

    asyncio.create_task(rebuild_index_background())

    return FileUploadResponse(
        success=True,
        filename=filename,
        message="文件上传成功，索引正在后台重建",
        index_rebuilt=False,
        total_chunks=0
    )
```

- [ ] **Step 3: 修改前端上传完成等待时间**

在 `frontend/js/app.js` 中，修改 `handleFileUpload()` 的 `xhr.addEventListener('load', ...)` 中 setTimeout 延迟（L929），从 1500ms 改为 2000ms：

```javascript
// 修改前
setTimeout(() => {
    fileEls.uploadProgress.style.display = 'none';
    loadFileList();
}, 1500);

// 修改后
setTimeout(() => {
    fileEls.uploadProgress.style.display = 'none';
    loadFileList();
}, 2000);
```

- [ ] **Step 4: 验证**

验证点：
- 上传一个文件后，立即返回"文件上传成功，索引正在后台重建"，不阻塞
- 等待 2-3 秒后刷新文件列表，确认文件已出现
- 检查后端日志，确认 `Background index rebuild done` 消息出现

---

### Task 4: 对话搜索 — SQLite FTS5 全文搜索升级

**Files:**
- Modify: `app/storage/search_store.py` —— 新增 FTS5 虚拟表，更新所有方法

**Interfaces:**
- Modifies: `_init_db()` —— 新增 `messages_fts` FTS5 虚拟表
- Modifies: `index_message(session_id, role, content)` —— 同步插入 FTS5 表
- Modifies: `search(keyword, limit=50) → list[dict]` —— 改用 FTS5 MATCH 查询
- Modifies: `delete_session(session_id)` —— 同步删除 FTS5 数据
- Modifies: `clear_all()` —— 同步清空 FTS5 数据

- [ ] **Step 1: 修改 _init_db() 添加 FTS5 虚拟表**

在 `app/storage/search_store.py` 中，修改 `_init_db()` 方法（L26-L45）：

```python
# 修改前
def _init_db(self):
    """创建表和索引（如果不存在）"""
    with sqlite3.connect(self.db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                title        TEXT,
                created_at   TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                role         TEXT NOT NULL,
                content      TEXT NOT NULL,
                created_at   TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_content ON messages(content);
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
        """)

# 修改后
def _init_db(self):
    """创建表和索引（如果不存在）"""
    with sqlite3.connect(self.db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id   TEXT PRIMARY KEY,
                title        TEXT,
                created_at   TEXT
            );
            CREATE TABLE IF NOT EXISTS messages (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id   TEXT NOT NULL,
                role         TEXT NOT NULL,
                content      TEXT NOT NULL,
                created_at   TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id)
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);
            -- FTS5 全文搜索虚拟表（独立存储，非外部内容表）
            CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
                content,
                session_id UNINDEXED,
                role UNINDEXED
            );
        """)
```

注意：移除了 `idx_messages_content` 索引（不再需要 LIKE 查询），新增 FTS5 虚拟表。

- [ ] **Step 2: 修改 index_message() 同步插入 FTS5**

在 `app/storage/search_store.py` 中，修改 `index_message()` 方法（L65-L75）：

```python
# 修改前
def index_message(self, session_id: str, role: str, content: str):
    """写入一条消息到搜索索引"""
    try:
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO messages (session_id, role, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, role, content, self._now())
            )
    except Exception as e:
        logger.error(f"Failed to index message for session {session_id}: {e}")

# 修改后
def index_message(self, session_id: str, role: str, content: str):
    """写入一条消息到搜索索引（messages 表 + FTS5 虚拟表）"""
    try:
        with self._get_conn() as conn:
            conn.execute(
                """INSERT INTO messages (session_id, role, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, role, content, self._now())
            )
            conn.execute(
                """INSERT INTO messages_fts (content, session_id, role)
                   VALUES (?, ?, ?)""",
                (content, session_id, role)
            )
    except Exception as e:
        logger.error(f"Failed to index message for session {session_id}: {e}")
```

- [ ] **Step 3: 修改 search() 使用 FTS5 MATCH 查询**

在 `app/storage/search_store.py` 中，修改 `search()` 方法（L96-L112）：

```python
# 修改前
def search(self, keyword: str, limit: int = 50) -> list[dict]:
    """全文搜索消息，返回匹配结果"""
    try:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT m.session_id, m.role, m.content, m.created_at, s.title
                   FROM messages m
                   LEFT JOIN sessions s ON m.session_id = s.session_id
                   WHERE m.content LIKE ?
                   ORDER BY m.created_at DESC
                   LIMIT ?""",
                (f"%{keyword}%", limit)
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Search failed for '{keyword}': {e}")
        return []

# 修改后
def search(self, keyword: str, limit: int = 50) -> list[dict]:
    """全文搜索消息（FTS5），返回匹配结果"""
    try:
        with self._get_conn() as conn:
            # 双引号包裹关键词，作为短语查询，避免 * / OR / AND 等特殊字符破坏语法
            safe_keyword = f'"{keyword}"'
            rows = conn.execute(
                """SELECT f.session_id, f.role, f.content, m.created_at, s.title
                   FROM messages_fts f
                   LEFT JOIN messages m ON m.session_id = f.session_id AND m.content = f.content
                   LEFT JOIN sessions s ON f.session_id = s.session_id
                   WHERE messages_fts MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (safe_keyword, limit)
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Search failed for '{keyword}': {e}")
        # FTS5 MATCH 失败时，回退到 LIKE 查询
        return self._search_fallback(keyword, limit)

def _search_fallback(self, keyword: str, limit: int = 50) -> list[dict]:
    """FTS5 查询失败时的 LIKE 回退方案"""
    try:
        with self._get_conn() as conn:
            rows = conn.execute(
                """SELECT m.session_id, m.role, m.content, m.created_at, s.title
                   FROM messages m
                   LEFT JOIN sessions s ON m.session_id = s.session_id
                   WHERE m.content LIKE ?
                   ORDER BY m.created_at DESC
                   LIMIT ?""",
                (f"%{keyword}%", limit)
            ).fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Fallback search also failed for '{keyword}': {e}")
        return []
```

- [ ] **Step 4: 修改 delete_session() 同步删除 FTS5 数据**

在 `app/storage/search_store.py` 中，修改 `delete_session()` 方法（L77-L84）：

```python
# 修改前
def delete_session(self, session_id: str):
    """删除会话及其所有消息"""
    try:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    except Exception as e:
        logger.error(f"Failed to delete session {session_id} from search index: {e}")

# 修改后
def delete_session(self, session_id: str):
    """删除会话及其所有消息（messages 表 + FTS5 虚拟表）"""
    try:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    except Exception as e:
        logger.error(f"Failed to delete session {session_id} from search index: {e}")
```

- [ ] **Step 5: 修改 clear_all() 同步清空 FTS5 数据**

在 `app/storage/search_store.py` 中，修改 `clear_all()` 方法（L86-L94）：

```python
# 修改前
def clear_all(self):
    """清空所有搜索索引数据"""
    try:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM sessions")
        logger.info("Search index cleared")
    except Exception as e:
        logger.error(f"Failed to clear search index: {e}")

# 修改后
def clear_all(self):
    """清空所有搜索索引数据（messages 表 + FTS5 虚拟表）"""
    try:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages")
            conn.execute("DELETE FROM messages_fts")
            conn.execute("DELETE FROM sessions")
        logger.info("Search index cleared")
    except Exception as e:
        logger.error(f"Failed to clear search index: {e}")
```

- [ ] **Step 6: 删除旧的 search.db 文件（如果存在）**

由于表结构变更，旧的 `search.db` 可能与新结构不兼容。删除后重启服务会自动重建：

```bash
Remove-Item -Force e:\CodeField\RAGKonwLedge\data\search.db
```

- [ ] **Step 7: 验证**

验证点：
- 启动服务后，确认 `data/search.db` 自动创建，包含 FTS5 表
- 发送几个提问，然后搜索关键词（如"Redis"），确认搜索结果正常返回
- 搜索特殊字符（如 `*`），确认不会报错（FTS5 双引号包裹保护）

---

### Task 5: 对话搜索 — 过期会话清理 + 清空体验修复

**Files:**
- Modify: `app/api/routes.py` —— `get_session_history()` 返回 404 并清理搜索索引
- Modify: `frontend/js/app.js` —— 搜索清空逻辑、`switchSession()` 404 处理

**Interfaces:**
- Modifies: `GET /api/sessions/{session_id}` —— 会话不存在时返回 404（而非 500）
- Modifies: 搜索框清空事件 —— 检查 sessions 为空时重新加载
- Modifies: `switchSession(sessionId)` —— 处理 404 状态码

- [ ] **Step 1: 修改 get_session_history() 返回 404**

在 `app/api/routes.py` 中，修改 `get_session_history()` 函数（L158-L173）：

```python
# 修改前
@router.get("/sessions/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str):
    """Get conversation history for a specific session."""
    rag = _get_rag()
    try:
        history = await rag.get_session_history(session_id)
        return SessionHistoryResponse(
            session_id=session_id,
            history=history,
            total_turns=len(history),
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Get session history failed: {e}")
        raise HTTPException(status_code=500, detail=str(e) or "获取会话历史失败")

# 修改后
@router.get("/sessions/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str):
    """Get conversation history for a specific session."""
    rag = _get_rag()
    try:
        history = await rag.get_session_history(session_id)
        if not history:
            # 会话不存在或已过期，清理搜索索引
            from app.main import search_store
            if search_store:
                search_store.delete_session(session_id)
            raise HTTPException(status_code=404, detail="会话不存在或已过期")
        return SessionHistoryResponse(
            session_id=session_id,
            history=history,
            total_turns=len(history),
        )
    except HTTPException:
        raise
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.exception(f"Get session history failed: {e}")
        raise HTTPException(status_code=500, detail=str(e) or "获取会话历史失败")
```

- [ ] **Step 2: 修改搜索框清空逻辑**

在 `frontend/js/app.js` 中，修改搜索输入事件中的清空逻辑（L1011-L1026）：

```javascript
// 修改前
if (!query) {
    // 清空搜索，恢复会话列表
    renderSessions();
    return;
}

// 修改后
if (!query) {
    // 清空搜索，恢复会话列表
    if (state.sessions.length === 0) {
        loadSessions();
    } else {
        renderSessions();
    }
    return;
}
```

- [ ] **Step 3: 修改 switchSession() 处理 404 会话过期**

在 `frontend/js/app.js` 中，修改 `switchSession()` 函数中的 fetch 错误处理（L187-L191）：

```javascript
// 修改前
} else {
    state.sessionMessages[sessionId] = [
        { role: 'system', content: '已切换到新会话，开始提问吧！' }
    ];
}

// 修改后
} else if (res.status === 404) {
    // 会话已过期（Redis TTL），从搜索索引中清理
    state.sessionMessages[sessionId] = [
        { role: 'system', content: '该会话已过期，请从其他搜索结果中选择。' }
    ];
    state.sessions = state.sessions.filter(s => s.session_id !== sessionId);
    renderSessions();
} else {
    state.sessionMessages[sessionId] = [
        { role: 'system', content: '已切换到新会话，开始提问吧！' }
    ];
}
```

注意：`switchSession()` 中第 1 行 `if (state.sessionId === sessionId) return;` 保持不变。404 分支在 `res.ok` 为 false 时进入，需要检查 `res.status`。

- [ ] **Step 4: 验证**

验证点：
- 搜索框中输入关键词，确认搜索结果正常显示
- 清空搜索框，确认会话列表恢复显示
- 如果存在已过期的会话搜索结果，点击跳转后应显示"该会话已过期"，并从侧边栏移除

---

## 验证清单

全部修复完成后，启动服务进行完整手动测试：

```bash
cd e:\CodeField\RAGKonwLedge
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

| # | 验证项 | 预期结果 |
|---|--------|----------|
| 1 | 提问含代码块的问题 | 流式输出中 Markdown 格式正常，代码块完成后高亮 |
| 2 | 检查 Console 无 JS 错误 | 无 `marked is not defined`、`DOMPurify is not defined` 等错误 |
| 3 | 知识库文件列表时间 | 显示"2 小时前"等人类可读格式 |
| 4 | 选择超 50MB 文件上传 | 提示错误，不发起上传请求 |
| 5 | 上传正常文件 | 立即返回成功，索引后台重建 |
| 6 | 搜索历史关键词 | 返回匹配结果，关键字高亮 |
| 7 | 清空搜索框 | 会话列表恢复 |
| 8 | 点击过期会话搜索结果 | 显示"该会话已过期"，侧边栏移除 |