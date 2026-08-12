# 用户体验优化 — 审查修复设计文档

> 创建日期：2026-08-12
> 状态：待审核
> 方案：方案 A — 最小修复

---

## 1. 背景

三个用户体验功能已实现：
1. 答案 Markdown 渲染 + 代码语法高亮
2. 知识库文件管理 UI（上传/删除/列表）
3. 对话搜索 / 全文检索

本次审查发现 8 个问题，按功能优先级 1→2→3 逐个修复。不新增功能，只修复正确性、安全性和性能问题。

---

## 2. 功能 1：Markdown 渲染 + 代码语法高亮

### 2.1 问题：XSS 风险

**位置**：`frontend/js/app.js` `renderMarkdown()` 函数（L406-L417）

**现状**：`marked.parse(text)` 输出直接赋值给 `innerHTML`，marked 12.x 无内置消毒。LLM 输出 `<script>` 或 `onerror=` 等恶意标签会被执行。

**修复**：
- `frontend/index.html`：添加 DOMPurify CDN（`https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js`）
- `frontend/js/app.js`：`renderMarkdown()` 中对 marked 输出做 `DOMPurify.sanitize()`

```javascript
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

### 2.2 问题：流式渲染性能

**位置**：`frontend/js/app.js` token 事件处理（L584-L598）

**现状**：每 50ms 节流更新时，对完整累积内容执行 `marked.parse()` + 遍历所有 `pre code` 做 `hljs.highlightElement()`。2000+ 字时每次更新卡顿。

**修复**：流式过程中只做 `marked.parse()`（Markdown 格式化），跳过 `hljs.highlightElement()`。`done` 事件时再做完整高亮。

- token 事件：`contentDiv.innerHTML = marked.parse(accumulatedContent)`
- done 事件：`contentDiv.innerHTML = renderMarkdown(accumulatedContent)`（含高亮）

新增辅助函数：
```javascript
function renderMarkdownNoHighlight(text) {
    if (!text) return '';
    const html = marked.parse(text, { breaks: true, gfm: true });
    return DOMPurify.sanitize(html);
}
```

**影响文件**：
- `frontend/index.html`：添加 DOMPurify CDN
- `frontend/js/app.js`：修改 `renderMarkdown()`、token 事件处理

---

## 3. 功能 2：知识库文件管理 UI

### 3.1 问题：`modified_time` 不可读

**位置**：`app/api/routes.py` `list_files()`（L236）、`frontend/js/app.js` `loadFileList()`（L887）

**现状**：后端返回 `str(stat.st_mtime)`（如 `"1723478923.123456"`），前端直接展示。

**修复**：
- 后端：`modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat()`
- 前端：新增 `formatRelativeTime(isoStr)` 函数，展示"2 小时前"格式

```javascript
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

### 3.2 问题：前端缺少文件大小校验

**位置**：`frontend/js/app.js` `handleFileUpload()`（L903-L951）

**现状**：50MB 限制仅在后端检查，用户选大文件上传完才报错。

**修复**：`handleFileUpload()` 开头检查 `file.size > 50 * 1024 * 1024`，超限直接提示并 return。

```javascript
function handleFileUpload(files) {
    if (!files || files.length === 0) return;
    const file = files[0];
    const MAX_SIZE = 50 * 1024 * 1024;
    if (file.size > MAX_SIZE) {
        showToast(`文件大小超过限制（${formatFileSize(MAX_SIZE)}），请压缩后重试`, 'error');
        return;
    }
    // ... 原有上传逻辑
}
```

### 3.3 问题：上传时索引重建阻塞

**位置**：`app/api/routes.py` `upload_file()`（L243-L291）

**现状**：`await indexer.build_index(rebuild=True)` 同步等待，大文件场景前端长时间无响应。

**修复**：上传文件后立即返回，索引重建改为后台任务。

```python
import asyncio

@router.post("/files/upload", response_model=FileUploadResponse)
async def upload_file(file: UploadFile = File(...)):
    # ... 文件校验和写入逻辑不变 ...

    # 后台异步重建索引
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

前端 `handleFileUpload` 的 `xhr.addEventListener('load', ...)` 中：
- 上传完成后显示"索引重建中..."提示
- 2 秒后刷新文件列表（给后台重建留时间）

**影响文件**：
- `app/api/routes.py`：修改 `list_files()` 时间格式、`upload_file()` 改为后台重建
- `frontend/js/app.js`：新增 `formatRelativeTime()`、修改 `handleFileUpload()` 和 `loadFileList()`

---

## 4. 功能 3：对话搜索 / 全文检索

### 4.1 问题：LIKE 查询性能差

**位置**：`app/storage/search_store.py` `search()` 方法（L96-L112）

**现状**：`WHERE m.content LIKE '%keyword%'` 全表扫描，无法利用索引。

**修复**：改用 SQLite FTS5 全文搜索引擎。使用独立 FTS5 表（非外部内容表），存储自己的副本，避免触发器同步复杂度。

`_init_db()` 新增 FTS5 虚拟表（原有 sessions 和 messages 表不变）：
```python
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content,
    session_id UNINDEXED,
    role UNINDEXED
);
```

`index_message()` 方法中同步插入 FTS5 表：
```python
def index_message(self, session_id: str, role: str, content: str):
    try:
        with self._get_conn() as conn:
            # 原有 messages 表插入不变
            conn.execute(
                """INSERT INTO messages (session_id, role, content, created_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, role, content, self._now())
            )
            # 同步插入 FTS5 索引
            conn.execute(
                """INSERT INTO messages_fts (content, session_id, role)
                   VALUES (?, ?, ?)""",
                (content, session_id, role)
            )
    except Exception as e:
        logger.error(f"Failed to index message for session {session_id}: {e}")
```

搜索方法改为（关键词用双引号包裹，避免 FTS5 特殊字符破坏查询语法）：
```python
def search(self, keyword: str, limit: int = 50) -> list[dict]:
    try:
        with self._get_conn() as conn:
            # 用双引号包裹关键词，作为短语查询，避免 *, OR, AND 等特殊字符破坏语法
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
        return []
```

`delete_session()` 方法中同步删除 FTS5 表数据：
```python
def delete_session(self, session_id: str):
    try:
        with self._get_conn() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
    except Exception as e:
        logger.error(f"Failed to delete session {session_id} from search index: {e}")
```

### 4.2 问题：搜索清空体验

**位置**：`frontend/js/app.js` 搜索输入事件（L1011-L1026）

**现状**：清空搜索框时调用 `renderSessions()`，但如果 `state.sessions` 为空，显示"暂无会话"而非重新加载。

**修复**：
```javascript
if (!query) {
    if (state.sessions.length === 0) {
        loadSessions();
    } else {
        renderSessions();
    }
    return;
}
```

### 4.3 问题：Redis TTL 过期后搜索索引残留

**位置**：`frontend/js/app.js` `switchSession()`（L162-L205）、`app/api/routes.py` `get_session_history()`（L158-L173）

**现状**：Redis 会话 TTL 过期后，搜索结果点击跳转加载失败，显示空会话。

**修复**：
- 后端 `get_session_history()`：会话不存在时返回 404（当前返回 500）
- 前端 `switchSession()`：fetch 返回 404 时显示"该会话已过期"，并调用 `/api/search` 清理接口或直接从搜索索引删除

后端修改（`get_session_history` 会话不存在时返回 404 并清理搜索索引）：
```python
@router.get("/sessions/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(session_id: str):
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

前端修改：
```javascript
if (res.status === 404) {
    state.sessionMessages[sessionId] = [
        { role: 'system', content: '该会话已过期，请从其他搜索结果中选择。' }
    ];
    // 从会话列表中移除过期会话
    state.sessions = state.sessions.filter(s => s.session_id !== sessionId);
    renderSessions();
} else {
    state.sessionMessages[sessionId] = [
        { role: 'system', content: '已切换到新会话，开始提问吧！' }
    ];
}
```

**影响文件**：
- `app/storage/search_store.py`：FTS5 虚拟表、`index_message()` 同步插入、`search()` 改为 MATCH、`delete_session()` 同步删除 FTS5、`clear_all()` 同步清空 FTS5
- `app/api/routes.py`：`get_session_history()` 返回 404 并清理搜索索引
- `frontend/js/app.js`：搜索清空逻辑、`switchSession()` 404 处理

---

## 5. 修改文件清单

| 文件 | 修改内容 |
|------|----------|
| `frontend/index.html` | 添加 DOMPurify CDN |
| `frontend/js/app.js` | XSS 消毒、流式渲染优化、文件大小校验、相对时间、搜索清空、404 处理 |
| `app/api/routes.py` | 时间格式、后台索引重建、会话 404 |
| `app/storage/search_store.py` | FTS5 虚拟表、`index_message()`、`search()`、`delete_session()`、`clear_all()` |

## 6. 验证方式

修复完成后启动后端服务，用户手动测试：
1. Markdown 渲染：提问获得含代码块的回答，验证流式格式 + 完成后语法高亮
2. 文件管理：上传文件、删除文件、查看文件列表（时间可读）
3. 对话搜索：搜索关键词、点击搜索结果跳转、清空搜索恢复会话列表
