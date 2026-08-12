### Task 3: 交互细节 — 导航修复 + 操作按钮 + 来源折叠

**Files:**
- Modify: `frontend/js/app.js` — switchSession、renderMessageElement、sendQuestion、操作按钮逻辑
- Modify: `frontend/css/style.css` — 操作按钮样式、来源折叠样式

**Interfaces:**
- Consumes: Task 2 的 HTML 结构（侧边栏、导航已改为 2 项：chat 和 settings）
- Produces: 导航自动跳转、复制/重新生成/来源折叠功能

- [ ] **Step 1: 导航 Bug 修复**

在 `switchSession()` 末尾（renderMessages 和 update 调用之后）增加：

```javascript
// 自动切换到聊天视图
if (state.currentView !== 'chat') {
    switchView('chat');
}
```

- [ ] **Step 2: 修改 sendQuestion 支持 regenerate 参数**

当前 `sendQuestion()` 无参数（从 `els.questionInput.value` 读取）。改为接受 `(question, sessionId, regenerate = false)`：

```javascript
// 修改前
async function sendQuestion() {
    const question = els.questionInput.value.trim();
    if (!question) return;

    const requestSessionId = state.sessionId || '__pending__';
    if (state.loadingSessions.has(requestSessionId)) return;

    state.loadingSessions.add(requestSessionId);

    const messages = getMessages(requestSessionId);
    messages.push({ role: 'user', content: question, sources: null });
    state.sessionMessages[requestSessionId] = messages;

    state.pendingStreams[requestSessionId] = {
        // ...
    };
    els.questionInput.value = '';
    // ...

// 修改后
async function sendQuestion(question, sessionId, regenerate = false) {
    if (!question) {
        if (regenerate) return;
        question = els.questionInput.value.trim();
        if (!question) return;
    }

    const requestSessionId = sessionId || state.sessionId || '__pending__';
    if (state.loadingSessions.has(requestSessionId)) return;

    state.loadingSessions.add(requestSessionId);

    // 重新生成时不添加用户消息（已存在）
    if (!regenerate) {
        const messages = getMessages(requestSessionId);
        messages.push({ role: 'user', content: question, sources: null });
        state.sessionMessages[requestSessionId] = messages;
        els.questionInput.value = '';
        autoResizeInput();
    }

    state.pendingStreams[requestSessionId] = {
        accumulatedContent: '',
        sourcesData: null,
        contentDiv: null,
        lastRenderedLength: 0,
        pendingRender: false,
        rafId: null
    };
    // ... 其余逻辑不变 ...
```

- [ ] **Step 3: 添加操作按钮 DOM 结构**

修改 `renderMessageElement()` 中 AI 消息的渲染，在消息内容后追加操作按钮行。当前函数签名 `renderMessageElement(role, content, sources)`，需要在 AI 消息末尾追加一个 `msg-actions` div。

注意：当前 `renderMessageElement` 内部已经渲染了 sources（L355-376），但新的设计需要将 sources 改为折叠的（默认隐藏），由按钮控制展开/收起。

```javascript
function renderMessageElement(role, content, sources = null) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? '我' : 'AI';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    if (role === 'assistant') {
        contentDiv.innerHTML = renderMarkdown(content);
    } else {
        contentDiv.textContent = content;
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);

    // AI 消息追加操作按钮行
    if (role === 'assistant') {
        const actions = document.createElement('div');
        actions.className = 'msg-actions';

        // 复制按钮
        const copyBtn = document.createElement('button');
        copyBtn.className = 'msg-action-btn';
        copyBtn.title = '复制答案';
        copyBtn.innerHTML = '📋';
        copyBtn.addEventListener('click', () => {
            navigator.clipboard.writeText(content);
            showToast('已复制到剪贴板');
        });

        // 重新生成按钮
        const regenerateBtn = document.createElement('button');
        regenerateBtn.className = 'msg-action-btn';
        regenerateBtn.title = '重新生成';
        regenerateBtn.innerHTML = '🔄';
        regenerateBtn.addEventListener('click', () => {
            // 在当前 session 找最后一个 user 消息
            const sessionId = state.sessionId;
            if (!sessionId) return;
            const messages = state.sessionMessages[sessionId];
            if (!messages) return;
            const userMsgIndex = messages.findLastIndex(m => m.role === 'user');
            if (userMsgIndex === -1) return;
            const aiMsgIndex = messages.findLastIndex(m => m.role === 'assistant');
            if (aiMsgIndex === -1) return;
            const question = messages[userMsgIndex].content;
            // 移除旧 AI 消息
            messages.splice(aiMsgIndex, 1);
            msgDiv.remove();
            // 重新发送
            sendQuestion(question, sessionId, true);
        });

        // 来源折叠按钮
        const sourcesToggle = document.createElement('button');
        sourcesToggle.className = 'msg-action-btn';
        sourcesToggle.title = '展开/收起来源';
        sourcesToggle.innerHTML = `📎 来源 (${sources?.length || 0})`;
        sourcesToggle.addEventListener('click', () => {
            // 切换来源显示
            const existing = msgDiv.querySelector('.msg-sources');
            if (existing) {
                existing.remove();
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
            sources.forEach(s => {
                const item = document.createElement('div');
                item.className = 'msg-sources-item';
                const file = document.createElement('span');
                file.className = 'msg-sources-item-file';
                file.textContent = s.file;
                const score = document.createElement('span');
                score.className = 'msg-sources-item-score';
                score.textContent = (s.score || 0).toFixed(3);
                item.appendChild(file);
                item.appendChild(score);
                sourcesDiv.appendChild(item);
            });
            msgDiv.appendChild(sourcesDiv);
        });

        actions.appendChild(copyBtn);
        actions.appendChild(regenerateBtn);
        actions.appendChild(sourcesToggle);
        msgDiv.appendChild(actions);
    }

    els.chatMessages.appendChild(msgDiv);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}
```

- [ ] **Step 4: 处理 done 事件中的来源**

当前 `done` 事件中调用 `appendSourcesToMessage(doneDiv, sourcesData)` 始终显示来源。改为仅在 `appendSourcesToMessage` 内部保留，但操作按钮中的来源折叠按钮会控制显示。

修改 `appendSourcesToMessage` 使其始终添加来源（但由按钮控制），或者简化：保持 `done` 事件中的来源显示逻辑不变，但操作按钮中的来源折叠按钮可以折叠/展开它。

实际上，更简单的方式：保持 `done` 事件中的来源显示，但操作按钮中的来源折叠按钮控制其显示状态。

- [ ] **Step 5: 添加操作按钮和来源折叠 CSS**

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

检查 `renderMessageElement()` 中 `msg.role === 'assistant'` 分支使用 `renderMarkdown()`，用户消息使用 `textContent` 赋值。确认 `done` 事件中流式渲染使用 `renderMarkdown()`。

- [ ] **Step 7: 启动服务验证交互**

```bash
cd e:\CodeField\RAGKonwLedge
python app/main.py
```
验证：
1. 在设置视图点击会话 → 自动跳转到问答视图
2. AI 回答底部有操作按钮行（hover 显示）
3. 点击复制按钮 → Toast 提示
4. 点击重新生成 → 发送新请求，旧 AI 消息被替换
5. 来源默认显示，但可通过折叠按钮控制