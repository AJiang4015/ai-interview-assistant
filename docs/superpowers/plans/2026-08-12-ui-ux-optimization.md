# UI/UX 优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 RAG 面试助手界面，完成配色迁移（金→蓝紫）、布局重构（侧边栏缩窄+导航合并）、交互细节（导航修复+操作按钮+来源折叠）。

**Architecture:** 纯前端改造，无后端变更。三层递进：CSS 变量替换（配色）→ HTML 结构调整（布局）→ JS 逻辑新增（交互）。每层独立可验证。

**Tech Stack:** CSS3 变量、原生 JavaScript (app.js)、ES Module 脚本

## Global Constraints

- 禁止引入新的 npm 包或 CDN 库
- 配色迁移仅修改 CSS 变量值，不新增变量
- 操作按钮使用 Unicode 图标（📋 🔄）而非字体图标
- 所有改动保持对现有 session 数据的兼容性
- 确保 `style.css` 中所有 `var(--accent)` 引用同步更新

---

### Task 1: 配色迁移 — CSS 变量替换

**Files:**
- Modify: `frontend/css/style.css`

**Interfaces:**
- Consumes: 无
- Produces: 更新后的 CSS 变量 `--accent: #6054F1`, `--accent-hover: #7B6FF2`, `--accent-glow: rgba(96,84,241,0.15)`

- [ ] **Step 1: 搜索所有 CSS 变量引用**

```bash
# 在 style.css 中搜索所有 var(--accent) 引用
grep -n "var(--accent)" frontend/css/style.css
```

- [ ] **Step 2: 替换三个 CSS 变量定义**

修改 `style.css` 中 `:root` 块：

```css
/* 修改前 */
--accent: #d4a95a;
--accent-hover: #e8be6d;
--accent-glow: rgba(212, 169, 90, 0.15);

/* 修改后 */
--accent: #6054F1;
--accent-hover: #7B6FF2;
--accent-glow: rgba(96, 84, 241, 0.15);
```

- [ ] **Step 3: 替换 brand icon 渐变**

```css
/* 修改前 */
background: linear-gradient(135deg, var(--accent) 0%, #b8944f 100%);

/* 修改后 */
background: linear-gradient(135deg, var(--accent) 0%, #4F46E5 100%);
```

- [ ] **Step 4: 替换搜索高亮配色**

```css
/* 搜索高亮背景 */
--search-highlight: rgba(96, 84, 241, 0.25);

/* 搜索高亮文字 */
.search-highlight {
    color: #ffffff;
    background: var(--search-highlight);
}
```

- [ ] **Step 5: 替换进度条渐变**

```css
/* 修改前 */
.progress-fill {
    background: linear-gradient(90deg, #d4a95a, #e8be6d);
}

/* 修改后 */
.progress-fill {
    background: linear-gradient(90deg, #6054F1, #7B6FF2);
}
```

- [ ] **Step 6: 启动服务验证配色**

```bash
# 启动服务
cd e:\CodeField\RAGKonwLedge
python app/main.py
```
验证：页面加载后，brand icon、发送按钮、输入框聚焦边框、进度条均为蓝紫色，无金色残留。

---

### Task 2: 布局重构 — 侧边栏缩窄 + 导航合并

**Files:**
- Modify: `frontend/index.html` — 导航项、侧边栏结构
- Modify: `frontend/css/style.css` — 侧边栏尺寸、会话列表高度
- Modify: `frontend/js/app.js` — 视图切换、系统状态渲染

**Interfaces:**
- Consumes: Task 1 的 CSS 变量
- Produces: 侧边栏 200px、导航 2 项、会话列表弹性高度、系统状态紧凑显示

- [ ] **Step 1: 侧边栏宽度 260px → 200px**

```css
/* 修改前 */
.sidebar {
    width: 260px;
    min-width: 260px;
}

/* 修改后 */
.sidebar {
    width: 200px;
    min-width: 200px;
}
```

- [ ] **Step 2: 导航从 3 项减为 2 项**

修改 `index.html`：

```html
<!-- 修改前 -->
<nav class="sidebar-nav">
    <div class="nav-item active" data-view="chat">
        <span class="nav-icon">💬</span>
        <span>问答</span>
    </div>
    <div class="nav-item" data-view="index">
        <span class="nav-icon">📂</span>
        <span>索引管理</span>
    </div>
    <div class="nav-item" data-view="docs">
        <span class="nav-icon">📚</span>
        <span>知识库</span>
    </div>
</nav>

<!-- 修改后 -->
<nav class="sidebar-nav">
    <div class="nav-item active" data-view="chat">
        <span class="nav-icon">💬</span>
        <span>问答</span>
    </div>
    <div class="nav-item" data-view="settings">
        <span class="nav-icon">⚙️</span>
        <span>设置</span>
    </div>
</nav>
```

- [ ] **Step 3: 移除会话列表 max-height 限制**

```css
/* 修改前 */
.session-list {
    max-height: 240px;
    overflow-y: auto;
}

/* 修改后 */
.session-list {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
}
```

- [ ] **Step 4: 系统状态改为紧凑一行**

移除 `index.html` 中的系统状态面板（3 行组件），改为在 `app.js` 的 `renderSidebarStatus()` 中动态渲染：

```javascript
// 新增函数
function renderSidebarStatus() {
    const statusBar = document.querySelector('.sidebar-status');
    if (!statusBar) return;
    statusBar.innerHTML = `
        <span class="status-dot ${state.indexBuilt ? 'online' : 'offline'}"></span> 向量索引 ${state.indexBuilt ? '✓' : '✗'}
        <span class="status-dot ${state.embeddingReady ? 'online' : 'offline'}"></span> Embedding ${state.embeddingReady ? '✓' : '✗'}
        <span class="status-dot ${state.llmReady ? 'online' : 'offline'}"></span> LLM ${state.llmReady ? '✓' : '✗'}
    `;
}
```

CSS 样式：

```css
.sidebar-status {
    display: flex;
    gap: 10px;
    padding: 6px 12px;
    font-size: 11px;
    color: var(--text-secondary);
    border-top: 1px solid var(--border);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    display: inline-block;
    vertical-align: middle;
    margin-right: 2px;
}

.status-dot.online {
    background: #22c55e;
    box-shadow: 0 0 4px rgba(34,197,94,0.5);
}

.status-dot.offline {
    background: #ef4444;
    box-shadow: 0 0 4px rgba(239,68,68,0.5);
}
```

- [ ] **Step 5: 合并设置视图**

修改 `app.js` 的 `switchView()` 函数，将 `view-index` 和 `view-docs` 合并为 `view-settings`：

```javascript
// 在 switchView 中
if (view === 'settings') {
    document.getElementById('view-settings').style.display = 'flex';
    document.getElementById('view-chat').style.display = 'none';
    document.getElementById('view-index').style.display = 'none';
    document.getElementById('view-docs').style.display = 'none';
    loadSettingsView();
}
```

```html
<!-- 设置视图 HTML -->
<section class="view settings-view" id="view-settings" style="display:none;">
    <div class="settings-header">
        <h2>设置</h2>
        <p class="subtitle">索引管理与知识库文件管理</p>
    </div>
    <div class="settings-content">
        <!-- 索引状态卡片 -->
        <div class="settings-card">
            <h3>向量索引</h3>
            <div class="index-status" id="settings-index-status">加载中...</div>
            <button class="btn btn-primary" id="settings-build-index" onclick="triggerBuildIndex()">重建索引</button>
            <div class="progress-bar" id="settings-progress-bar" style="display:none;">
                <div class="progress-fill" id="settings-progress-fill"></div>
            </div>
        </div>
        <!-- 知识库文件管理 -->
        <div class="settings-card">
            <h3>知识库文件</h3>
            <div class="upload-area" id="settings-upload-area">
                <div class="upload-zone" id="settings-upload-zone">
                    <div class="upload-icon">📄</div>
                    <p>拖拽文件到此处，或 <span class="upload-link">点击选择文件</span></p>
                    <p class="upload-hint">支持 .md / .pdf / .docx，单个文件最大 50MB</p>
                    <input type="file" id="settings-file-input" hidden accept=".md,.pdf,.docx" multiple>
                </div>
                <div class="upload-progress" id="settings-upload-progress" style="display:none;">
                    <div class="upload-progress-bar">
                        <div class="upload-progress-fill" id="settings-upload-progress-fill"></div>
                    </div>
                    <span class="upload-progress-text" id="settings-upload-progress-text">上传中...</span>
                </div>
            </div>
            <div class="file-list-section">
                <div class="file-list-header">
                    <h3>文件列表 <span id="settings-file-count" class="file-count-badge">0</span></h3>
                    <button class="btn-refresh-files" id="settings-btn-refresh-files">刷新</button>
                </div>
                <div class="file-list" id="settings-file-list">
                    <div class="file-list-empty">加载中...</div>
                </div>
            </div>
        </div>
    </div>
</section>
```

- [ ] **Step 6: 删除旧的 index-view 和 docs-view 相关代码**

从 `app.js` 中移除 `switchView('index')` 和 `switchView('docs')` 相关的分支代码，以及 `loadIndexView()` 和 `loadDocsView()` 函数（内容已合并到 `loadSettingsView()`）。

- [ ] **Step 7: 启动服务验证布局**

```bash
cd e:\CodeField\RAGKonwLedge
python app/main.py
```
验证：侧边栏 200px、导航 2 项（问答/设置）、会话列表全高度可滚动、系统状态一行紧凑显示在底部。

---

### Task 3: 交互细节 — 导航修复 + 操作按钮 + 来源折叠

**Files:**
- Modify: `frontend/js/app.js` — switchSession、renderMessageElement、操作按钮逻辑
- Modify: `frontend/css/style.css` — 操作按钮样式、来源折叠样式

**Interfaces:**
- Consumes: Task 2 的 HTML 结构（侧边栏、设置视图）
- Produces: 导航自动跳转、复制/重新生成/来源折叠功能

- [ ] **Step 1: 导航 Bug 修复**

在 `switchSession()` 末尾增加：

```javascript
function switchSession(sessionId) {
    // ... 现有逻辑 ...

    // 新增：自动切换到聊天视图
    if (state.currentView !== 'chat') {
        switchView('chat');
    }
}
```

- [ ] **Step 2: 添加操作按钮 DOM 结构**

修改 `renderMessageElement()` 中 AI 消息的渲染，在消息内容后追加操作按钮行：

```javascript
function renderMessageElement(msg, sessionId) {
    const div = document.createElement('div');
    div.className = `message ${msg.role}`;
    div.dataset.sessionId = sessionId;

    const avatar = document.createElement('div');
    avatar.className = 'msg-avatar';
    avatar.textContent = msg.role === 'user' ? 'U' : 'AI';

    const content = document.createElement('div');
    content.className = 'msg-content';
    content.innerHTML = msg.role === 'user'
        ? escapeHtml(msg.content)
        : renderMarkdown(msg.content);

    div.appendChild(avatar);
    div.appendChild(content);

    // AI 消息追加操作按钮行
    if (msg.role === 'assistant') {
        const actions = document.createElement('div');
        actions.className = 'msg-actions';

        // 复制按钮
        const copyBtn = document.createElement('button');
        copyBtn.className = 'msg-action-btn';
        copyBtn.title = '复制答案';
        copyBtn.innerHTML = '📋';
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(msg.content);
            showToast('已复制到剪贴板');
        });

        // 重新生成按钮
        const regenerateBtn = document.createElement('button');
        regenerateBtn.className = 'msg-action-btn';
        regenerateBtn.title = '重新生成';
        regenerateBtn.innerHTML = '🔄';
        regenerateBtn.addEventListener('click', () => {
            regenerateAnswer(div, sessionId);
        });

        // 来源折叠按钮
        const sourcesToggle = document.createElement('button');
        sourcesToggle.className = 'msg-action-btn';
        sourcesToggle.title = '展开/收起来源';
        sourcesToggle.innerHTML = `📎 来源 (${msg.sources?.length || 0})`;
        sourcesToggle.addEventListener('click', () => {
            toggleSources(div, msg.sources);
        });

        actions.appendChild(copyBtn);
        actions.appendChild(regenerateBtn);
        actions.appendChild(sourcesToggle);
        div.appendChild(actions);
    }

    return div;
}
```

- [ ] **Step 3a: 修改 sendQuestion 支持 regenerate 参数**

在 `sendQuestion` 函数签名中增加 `regenerate` 参数，当为 `true` 时跳过添加用户消息：

```javascript
// 修改前
async function sendQuestion(question, sessionId) {
    if (!sessionId) return;
    // ...开头添加用户消息...

// 修改后
async function sendQuestion(question, sessionId, regenerate = false) {
    if (!sessionId) return;

    // 重新生成时，不添加用户消息（已存在）
    if (!regenerate) {
        const userMsg = { role: 'user', content: question };
        // ...现有添加用户消息逻辑...
    }
```

- [ ] **Step 3b: 实现重新生成逻辑**

```javascript
function regenerateAnswer(msgDiv, sessionId) {
    const messages = state.sessionMessages[sessionId];
    const userMsgIndex = messages.findLastIndex(m => m.role === 'user');
    if (userMsgIndex === -1) return;

    // 找到当前 AI 消息在数组中的索引
    const aiMsgIndex = messages.findLastIndex(m => m.role === 'assistant');
    if (aiMsgIndex === -1) return;

    const question = messages[userMsgIndex].content;

    // 移除旧 AI 消息
    messages.splice(aiMsgIndex, 1);
    msgDiv.remove();

    // 重新发送请求（regenerate=true，跳过添加用户消息）
    sendQuestion(question, sessionId, true);
}
```

- [ ] **Step 4: 实现来源折叠**

```javascript
function toggleSources(msgDiv, sources) {
    const existingSources = msgDiv.querySelector('.msg-sources');
    if (existingSources) {
        existingSources.remove();
        return;
    }

    if (!sources || sources.length === 0) {
        showToast('暂无参考来源');
        return;
    }

    const sourcesDiv = document.createElement('div');
    sourcesDiv.className = 'msg-sources';

    const header = document.createElement('div');
    header.className = 'msg-sources-header';
    header.textContent = `参考来源 (${sources.length})`;
    sourcesDiv.appendChild(header);

    sources.forEach(source => {
        const item = document.createElement('div');
        item.className = 'msg-sources-item';
        item.innerHTML = `
            <span class="msg-sources-item-file">${escapeHtml(source.filename)}</span>
            <span class="msg-sources-item-score">${(source.score || 0).toFixed(3)}</span>
        `;
        sourcesDiv.appendChild(item);
    });

    msgDiv.appendChild(sourcesDiv);
}
```

- [ ] **Step 5: 添加操作按钮和来源折叠样式**

```css
/* 操作按钮行 */
.msg-actions {
    display: flex;
    gap: 4px;
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid var(--border);
    opacity: 0;
    transition: opacity 0.2s;
}

.message:hover .msg-actions {
    opacity: 1;
}

.msg-action-btn {
    background: none;
    border: 1px solid transparent;
    color: var(--text-secondary);
    cursor: pointer;
    padding: 4px 8px;
    border-radius: 6px;
    font-size: 12px;
    transition: all 0.15s;
}

.msg-action-btn:hover {
    background: var(--bg-tertiary);
    border-color: var(--border);
    color: var(--text-primary);
}

/* 来源折叠面板 */
.msg-sources {
    margin-top: 12px;
    padding: 10px 12px;
    background: var(--bg-tertiary);
    border-radius: var(--radius-sm);
    border: 1px solid var(--border);
}

.msg-sources-header {
    font-size: 12px;
    font-weight: 600;
    color: var(--text-secondary);
    margin-bottom: 6px;
}

.msg-sources-item {
    display: flex;
    justify-content: space-between;
    padding: 4px 0;
    font-size: 13px;
}

.msg-sources-item-file {
    color: var(--accent);
}

.msg-sources-item-score {
    color: var(--text-secondary);
    font-family: var(--font-mono);
    font-size: 12px;
}
```

- [ ] **Step 6: 验证 Markdown 渲染路径**

检查 `renderMessageElement()` 中 `msg.role === 'assistant'` 分支使用 `renderMarkdown()`，用户消息使用 `escapeHtml()`。确认 `done` 事件中流式渲染使用 `renderMarkdown()`。

- [ ] **Step 7: 启动服务验证交互**

```bash
cd e:\CodeField\RAGKonwLedge
python app/main.py
```
验证：
1. 在知识库/设置视图点击会话 → 自动跳转到问答视图
2. AI 回答底部有操作按钮行（hover 显示）
3. 点击复制按钮 → Toast 提示
4. 点击重新生成 → 重新发送请求
5. 来源默认折叠，点击展开/收起

---

## 实施顺序

1. **Task 1 → Task 2 → Task 3**（严格顺序依赖）
2. 每个 Task 完成后验证再进入下一个