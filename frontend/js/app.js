const API_BASE = '';
const STORAGE_KEY = 'rag_current_session_id';

const state = {
    sessionMessages: {},
    pendingStreams: {},
    loadingSessions: new Set(),
    currentView: 'interview',
    sessionId: null,
    sessions: []
};

const els = {
    navItems: document.querySelectorAll('.nav-item'),
    views: {
        chat: document.getElementById('view-chat'),
        interview: document.getElementById('view-interview'),
        review: document.getElementById('view-review'),
        settings: document.getElementById('view-settings')
    },
    dotFaiss: document.getElementById('dot-faiss'),
    dotEmbedding: document.getElementById('dot-embedding'),
    dotLlm: document.getElementById('dot-llm'),
    valFaiss: document.getElementById('val-faiss'),
    valEmbedding: document.getElementById('val-embedding'),
    valLlm: document.getElementById('val-llm'),
    kbPanel: document.getElementById('kb-panel'),
    kbList: document.getElementById('kb-list'),
    kbMeta: document.getElementById('kb-meta'),
    chatMessages: document.getElementById('chat-messages'),
    chatSubtitle: document.getElementById('chat-subtitle'),
    questionInput: document.getElementById('question-input'),
    btnSend: document.getElementById('btn-send'),
    btnBuild: document.getElementById('btn-build'),
    btnRebuild: document.getElementById('btn-rebuild'),
    badgeIndex: document.getElementById('badge-index'),
    metricChunks: document.getElementById('metric-chunks'),
    metricFiles: document.getElementById('metric-files'),
    metricTime: document.getElementById('metric-time'),
    filesList: document.getElementById('files-list'),
    progressWrapper: document.getElementById('progress-wrapper'),
    progressFill: document.getElementById('progress-fill'),
    progressText: document.getElementById('progress-text'),
    sessionsList: document.getElementById('sessions-list'),
    btnNewSession: document.getElementById('btn-new-session'),
    sessionIndicator: document.getElementById('session-indicator'),
    sessionTurnCount: document.getElementById('session-turn-count'),
    toast: document.getElementById('toast')
};

// 文件管理 DOM 元素
const fileEls = {
    uploadZone: document.getElementById('upload-zone'),
    fileInput: document.getElementById('file-input'),
    uploadProgress: document.getElementById('upload-progress'),
    progressFill: document.getElementById('upload-progress-fill'),
    progressText: document.getElementById('upload-progress-text'),
    fileList: document.getElementById('file-list'),
    fileCount: document.getElementById('file-count'),
    btnRefresh: document.getElementById('btn-refresh-files')
};

// 守卫：为所有 fetch 统一注入 JWT（等价 axios 拦截器）。
// token 缺失时 getAuthHeaders() 返回空对象，因此公开接口（/api/health、/api/auth/*）不受影响。
// 后端已把所有业务路由纳入 JWT 鉴权，故此处的统一注入是前端保证登录态的关键入口。
// note: getAuthHeaders / handleAuthExpired / showLoginPrompt 均为模块级函数声明，会被提升，此处可安全引用。
{
    const _origFetch = window.fetch.bind(window);
    window.fetch = async (input, init = {}) => {
        const headers = { ...getAuthHeaders(), ...(init.headers || {}) };
        const res = await _origFetch(input, { ...init, headers });
        // token 失效或未登录：清除缓存并引导重新登录（排除登录/注册接口自身）
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        if (res.status === 401 && url.indexOf('/api/auth/') === -1) {
            handleAuthExpired();
        }
        return res;
    };
}

function applyXhrAuth(xhr) {
    const h = getAuthHeaders();
    if (h.Authorization) xhr.setRequestHeader('Authorization', h.Authorization);
}

// ============ Navigation ============
els.navItems.forEach(item => {
    item.addEventListener('click', () => {
        const view = item.dataset.view;
        switchView(view);
    });
});

function switchView(view) {
    state.currentView = view;
    els.navItems.forEach(item => {
        item.classList.toggle('active', item.dataset.view === view);
    });
    Object.entries(els.views).forEach(([key, el]) => {
        el.classList.toggle('active', key === view);
    });
    if (view === 'settings') {
        switchSettingsTab('index');
        loadIndexStatus();
    }
    if (view === 'review') {
        loadReviewData();
    }
}

// ============ Settings Tabs ============
function initSettingsTabs() {
    const tabs = document.querySelectorAll('.settings-tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            switchSettingsTab(tab.dataset.tab);
        });
    });
}

function switchSettingsTab(tab) {
    const tabs = document.querySelectorAll('.settings-tab');
    tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    const indexPanel = document.getElementById('view-index');
    const docsPanel = document.getElementById('view-docs');
    if (indexPanel) indexPanel.style.display = tab === 'index' ? 'block' : 'none';
    if (docsPanel) docsPanel.style.display = tab === 'docs' ? 'block' : 'none';
    if (tab === 'index') {
        loadIndexStatus();
    } else if (tab === 'docs') {
        loadFileList();
    }
}

// ============ Status ============
async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        const data = await res.json();
        updateStatus('faiss',
            data.faiss_index === 'empty' ? 'offline' : 'online',
            data.faiss_index === 'empty' ? '未构建' : '正常');
        updateStatus('embedding',
            data.embedding_service === 'available' ? 'online' : 'offline',
            data.embedding_service === 'available' ? '正常' : '不可用');
        updateStatus('llm',
            data.llm_service === 'available' ? 'online' : 'offline',
            data.llm_service === 'available' ? '正常' : '不可用');
    } catch (e) {
        updateStatus('faiss', 'offline', '无法连接');
        updateStatus('embedding', 'offline', '无法连接');
        updateStatus('llm', 'offline', '无法连接');
    }
}

function updateStatus(key, status, value) {
    const dot = els['dot' + key.charAt(0).toUpperCase() + key.slice(1)];
    const val = els['val' + key.charAt(0).toUpperCase() + key.slice(1)];
    dot.className = 'status-dot' + (status === 'online' ? ' online' : status === 'warning' ? ' warning' : ' offline');
    val.textContent = value || (status === 'online' ? '正常' : '不可用');
}

// ============ Session Management ============
async function loadSessions() {
    try {
        const res = await fetch(`${API_BASE}/api/sessions`);
        const data = await res.json();
        state.sessions = data.sessions || [];
        renderSessions();

        if (!state.sessionId && state.sessions.length > 0) {
            const savedId = localStorage.getItem(STORAGE_KEY);
            if (savedId && state.sessions.some(s => s.session_id === savedId)) {
                await switchSession(savedId);
            }
        }
    } catch (e) {
        console.error('Failed to load sessions:', e);
    }
}

function renderSessions() {
    if (!els.sessionsList) return;

    if (state.sessions.length === 0) {
        els.sessionsList.innerHTML = '<div class="session-empty">暂无会话</div>';
        return;
    }

    els.sessionsList.innerHTML = state.sessions.map(s => {
        const title = s.title || `会话 ${s.session_id.slice(0, 8)}`;
        const activeClass = s.session_id === state.sessionId ? ' active' : '';
        return `
            <div class="session-item${activeClass}" data-session-id="${s.session_id}">
                <span class="session-item-title" title="${escapeHtml(title)}">${escapeHtml(title)}</span>
                <span class="session-item-delete" data-delete-id="${s.session_id}" title="删除">×</span>
            </div>
        `;
    }).join('');
}

// 事件委托：监听 sessions-list 上的点击事件，避免重复绑定/解绑
if (els.sessionsList) {
    els.sessionsList.addEventListener('click', (e) => {
        const deleteBtn = e.target.closest('.session-item-delete');
        if (deleteBtn) {
            e.stopPropagation();
            deleteSession(deleteBtn.dataset.deleteId);
            return;
        }

        const sessionItem = e.target.closest('.session-item');
        if (sessionItem) {
            switchSession(sessionItem.dataset.sessionId);
            return;
        }

        const searchResult = e.target.closest('.search-result-item');
        if (searchResult) {
            const sessionId = searchResult.dataset.sessionId;
            if (searchInput) searchInput.value = '';
            switchSession(sessionId);
        }
    });
}

async function switchSession(sessionId) {
    if (state.sessionId === sessionId) return;

    state.sessionId = sessionId;
    localStorage.setItem(STORAGE_KEY, sessionId);
    renderSessions();

    if (!state.sessionMessages[sessionId]) {
        try {
            const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
            if (res.ok) {
                const data = await res.json();
                const history = data.history || [];
                const messages = history.map(msg => ({
                    role: msg.role,
                    content: msg.content,
                    sources: msg.sources || null
                }));
                state.sessionMessages[sessionId] = messages;

                if (messages.length === 0) {
                    state.sessionMessages[sessionId] = [
                        { role: 'system', content: '已切换到新会话，开始提问吧！' }
                    ];
                }
            } else {
                state.sessionMessages[sessionId] = [
                    { role: 'system', content: '已切换到新会话，开始提问吧！' }
                ];
            }
        } catch (e) {
            console.error('Failed to load session history:', e);
            if (!state.sessionMessages[sessionId]) {
                state.sessionMessages[sessionId] = [
                    { role: 'system', content: '已切换到新会话，开始提问吧！' }
                ];
            }
        }
    }

    renderMessages(sessionId);
    updateSessionIndicator();
    updateSendButtonState();

    // 自动切换到聊天视图
    if (state.currentView !== 'chat') {
        switchView('chat');
    }
}

async function createSession() {
    try {
        const res = await fetch(`${API_BASE}/api/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        const newSessionId = data.session_id;

        state.sessionMessages[newSessionId] = [
            { role: 'system', content: '已创建新会话，开始提问吧！' }
        ];

        state.sessionId = newSessionId;
        localStorage.setItem(STORAGE_KEY, newSessionId);

        state.loadingSessions.delete(newSessionId);

        els.chatMessages.innerHTML = '';
        appendSystemMessage('已创建新会话，开始提问吧！');

        await loadSessions();
        renderSessions();
        updateSessionIndicator();
        updateSendButtonState();

        showToast('新会话已创建', 'success');
    } catch (e) {
        console.error('Failed to create session:', e);
        showToast('创建会话失败', 'error');
    }
}

async function deleteSession(sessionId) {
    if (!confirm('确定删除该会话吗？')) return;

    const hasPendingStream = !!state.pendingStreams[sessionId];

    try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            state.sessions = state.sessions.filter(s => s.session_id !== sessionId);

            if (!hasPendingStream) {
                delete state.sessionMessages[sessionId];
                delete state.pendingStreams[sessionId];
            }

            if (state.sessionId === sessionId) {
                state.sessionId = null;
                state.loadingSessions.delete(sessionId);
                localStorage.removeItem(STORAGE_KEY);
                els.chatMessages.innerHTML = '';
                appendSystemMessage(
                    hasPendingStream
                        ? '会话已删除，正在接收最后的 AI 回复…'
                        : '会话已删除，点击右上角「+」创建新会话。'
                );
                updateSessionIndicator();
                updateSendButtonState();
            }

            renderSessions();
            showToast(hasPendingStream
                ? '会话已删除，AI 回复将在后台完成'
                : '会话已删除', 'success');
        }
    } catch (e) {
        console.error('Failed to delete session:', e);
        showToast('删除会话失败', 'error');
    }
}

function updateSessionIndicator() {
    if (!els.sessionIndicator) return;

    if (state.sessionId) {
        els.sessionIndicator.style.display = 'flex';
        const messages = getMessages(state.sessionId);
        const count = messages.filter(m => m.role !== 'system').length;
        els.sessionTurnCount.textContent = count;
    } else {
        els.sessionIndicator.style.display = 'none';
        els.sessionTurnCount.textContent = '0';
    }
}

function getMessages(sessionId) {
    if (!sessionId) return [];
    return state.sessionMessages[sessionId] || [];
}

function renderMessages(sessionId) {
    const messages = getMessages(sessionId);
    els.chatMessages.innerHTML = '';

    messages.forEach(msg => {
        if (msg.role === 'system') {
            appendSystemMessage(msg.content);
        } else {
            renderMessageElement(msg.role, msg.content, msg.sources);
        }
    });

    const pending = state.pendingStreams[sessionId];
    if (pending) {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message assistant';

        const avatar = document.createElement('div');
        avatar.className = 'avatar';
        avatar.textContent = 'AI';

        const bodyDiv = document.createElement('div');
        bodyDiv.className = 'msg-body';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content streaming';
        contentDiv.innerHTML = renderMarkdownNoHighlight(pending.accumulatedContent) || '<span class="streaming-cursor"></span>';

        bodyDiv.appendChild(contentDiv);
        msgDiv.appendChild(avatar);
        msgDiv.appendChild(bodyDiv);
        els.chatMessages.appendChild(msgDiv);
        els.chatMessages.scrollTop = els.chatMessages.scrollHeight;

        pending.contentDiv = contentDiv;
        pending.lastRenderedLength = pending.accumulatedContent.length;
        pending.pendingRender = false;
        pending.rafId = null;
    }
}

function renderMessageElement(role, content, sources = null) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? '我' : 'AI';

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'msg-body';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    // AI 消息用 Markdown 渲染，用户消息纯文本
    if (role === 'assistant') {
        contentDiv.innerHTML = renderMarkdown(content);
    } else {
        contentDiv.textContent = content;
    }

    bodyDiv.appendChild(contentDiv);
    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bodyDiv);

    // AI 消息追加操作按钮行（追加到 bodyDiv 中，位于内容下方）
    if (role === 'assistant') {
        addActionButtons(bodyDiv, content, sources);
        if (sources && sources.length > 0) {
            appendSourcesToMessage(bodyDiv, sources);
        }
    }

    els.chatMessages.appendChild(msgDiv);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

function addActionButtons(msgDiv, content, sources = null) {
    if (msgDiv.querySelector('.msg-actions')) return;
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
    const sourcesCount = sources?.length || 0;
    sourcesToggle.innerHTML = `📎 来源 (${sourcesCount})`;
    sourcesToggle.addEventListener('click', () => {
        const existing = msgDiv.querySelector('.msg-sources');
        if (existing) {
            existing.style.display = existing.style.display === 'none' ? 'block' : 'none';
        } else {
            showToast('暂无参考来源');
        }
    });

    actions.appendChild(copyBtn);
    actions.appendChild(regenerateBtn);
    actions.appendChild(sourcesToggle);
    msgDiv.appendChild(actions);
}

function appendMessage(role, content, sources = null) {
    if (!state.sessionId) return;

    const messages = getMessages(state.sessionId);
    messages.push({ role, content, sources });
    state.sessionMessages[state.sessionId] = messages;

    renderMessageElement(role, content, sources);
    updateSessionIndicator();
    return messages[messages.length - 1];
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 生成可折叠详情块（默认折叠）；content 为空时返回空串（判空降级）
function buildEvalCollapse(label, content) {
    if (!content) return '';
    return `
        <div class="eval-collapse">
            <button type="button" class="eval-collapse-toggle" data-label="${escapeHtml(label)}">${escapeHtml(label)}</button>
            <div class="eval-collapse-body" style="display:none;">${escapeHtml(content)}</div>
        </div>
    `;
}

// 折叠事件委托：容器级绑定一次，兼容动态插入内容
function bindEvalCollapse(container) {
    if (!container) return;
    container.addEventListener('click', (e) => {
        const btn = e.target.closest('.eval-collapse-toggle');
        if (!btn) return;
        const body = btn.parentElement.querySelector('.eval-collapse-body');
        if (!body) return;
        const hidden = body.style.display === 'none';
        body.style.display = hidden ? 'block' : 'none';
        const label = btn.dataset.label || '';
        btn.textContent = hidden ? ('收起' + label) : label;
    });
}

// DOMPurify 白名单配置：只允许 Markdown 渲染产生的 HTML 标签和属性
const DOMPurifyConfig = {
    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 's', 'del', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'code', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'hr', 'img', 'span', 'div', 'input'],
    ALLOWED_ATTR: ['href', 'title', 'target', 'src', 'alt', 'class', 'type', 'checked', 'disabled']
};

// ============ Chat ============
function isSessionLoading(sessionId) {
    if (!sessionId) return false;
    return state.loadingSessions.has(sessionId);
}

// Markdown 渲染 + 代码语法高亮
function renderMarkdown(text) {
    if (!text) return '';
    // marked 未加载时降级为纯文本
    if (typeof marked === 'undefined') {
        return `<p>${escapeHtml(text)}</p>`;
    }
    // marked 解析 Markdown 为 HTML
    const html = marked.parse(text, { breaks: true, gfm: true });
    // highlight.js 高亮所有 <code> 块
    const wrapper = document.createElement('div');
    wrapper.innerHTML = DOMPurify.sanitize(html, DOMPurifyConfig);
    if (typeof hljs !== 'undefined') {
        wrapper.querySelectorAll('pre code').forEach(block => {
            try { hljs.highlightElement(block); } catch (e) {}
        });
    }
    return wrapper.innerHTML;
}

// 流式渲染用：Markdown 格式化 + DOMPurify 消毒，不含代码高亮（性能优化）
function renderMarkdownNoHighlight(text) {
    if (!text) return '';
    // marked 未加载时降级为纯文本
    if (typeof marked === 'undefined') {
        return `<p>${escapeHtml(text)}</p>`;
    }
    const html = marked.parse(text, { breaks: true, gfm: true });
    return DOMPurify.sanitize(html, DOMPurifyConfig);
}

function getStreamingContentDiv(sessionId) {
    const pending = state.pendingStreams[sessionId];
    return pending ? pending.contentDiv : null;
}

function updateSendButtonState() {
    const hasText = els.questionInput.value.trim().length > 0;
    const locked = state.sessionId ? state.loadingSessions.has(state.sessionId) : false;
    els.btnSend.disabled = !hasText || locked;
}

els.questionInput.addEventListener('input', () => {
    updateSendButtonState();
    autoResizeInput();
});

els.questionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
    }
});

els.btnSend.addEventListener('click', () => sendQuestion());
els.btnNewSession?.addEventListener('click', createSession);

function autoResizeInput() {
    const el = els.questionInput;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

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

    updateSendButtonState();

    let accumulatedContent = '';
    let sourcesData = null;
    let finalSessionId = requestSessionId;

    try {
        const res = await fetch(`${API_BASE}/api/query/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question,
                session_id: state.sessionId || undefined
            })
        });

        if (!res.ok) {
            let errorMsg = '请求失败';
            try {
                const errText = await res.text();
                const errData = JSON.parse(errText);
                errorMsg = errData.detail || errData.error || `HTTP ${res.status}`;
            } catch {}
            showToast(errorMsg, 'error');
            state.loadingSessions.delete(requestSessionId);
            delete state.pendingStreams[requestSessionId];
            updateSendButtonState();
            return;
        }

        // 流已建立，现在安全地创建 DOM 元素
        const isCurrentSession = state.sessionId === requestSessionId;
        if (isCurrentSession) {
            renderMessageElement('user', question, null);
            const assistantMsg = createStreamingMessage();
            const contentDiv = assistantMsg.querySelector('.msg-content');
            state.pendingStreams[requestSessionId].contentDiv = contentDiv;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            // 为 reader.read() 添加超时保护
            const readResult = await Promise.race([
                reader.read(),
                new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('stream_read_timeout')), 120000)
                )
            ]);
            const { done, value } = readResult;
            if (done) {
                if (buffer.trim()) {
                    console.warn('[SSE] stream ended with unprocessed buffer:', buffer.slice(0, 200));
                }
                break;
            }

            buffer += decoder.decode(value, { stream: true });

            const events = buffer.split('\n\n');
            buffer = events.pop();

            for (const event of events) {
                const lines = event.split('\n');
                let eventType = 'message';
                let dataStr = '';

                for (const line of lines) {
                    if (line.startsWith('event: ')) {
                        eventType = line.slice(7);
                    } else if (line.startsWith('data: ')) {
                        dataStr = line.slice(6);
                    }
                }

                if (!dataStr) continue;

                try {
                    const data = JSON.parse(dataStr);

                    switch (eventType) {
                        case 'session':
                            if (data.session_id && finalSessionId === '__pending__') {
                                finalSessionId = data.session_id;
                                state.sessionMessages[data.session_id] =
                                    state.sessionMessages['__pending__'] || [];
                                delete state.sessionMessages['__pending__'];
                                state.pendingStreams[data.session_id] =
                                    state.pendingStreams['__pending__'];
                                delete state.pendingStreams['__pending__'];
                                state.loadingSessions.delete('__pending__');
                                state.loadingSessions.add(data.session_id);
                                state.sessionId = data.session_id;
                                localStorage.setItem(STORAGE_KEY, data.session_id);
                                renderSessions();
                                updateSessionIndicator();
                            }
                            break;

                        case 'retrieval':
                            sourcesData = data.sources;
                            if (state.pendingStreams[finalSessionId]) {
                                state.pendingStreams[finalSessionId].sourcesData = sourcesData;
                            }
                            break;

                        case 'token':
                            accumulatedContent += data.content;
                            const tokenStream = state.pendingStreams[finalSessionId];
                            if (tokenStream) {
                                tokenStream.accumulatedContent = accumulatedContent;
                                if (!tokenStream.pendingRender) {
                                    tokenStream.pendingRender = true;
                                    tokenStream.rafId = requestAnimationFrame(() => {
                                        tokenStream.pendingRender = false;
                                        tokenStream.rafId = null;
                                        const tokenDiv = tokenStream.contentDiv;
                                        if (!tokenDiv) return;

                                        const delta = accumulatedContent.slice(tokenStream.lastRenderedLength);
                                        if (!delta) return;

                                        const lastDoubleNewline = delta.lastIndexOf('\n\n');
                                        if (lastDoubleNewline === -1) {
                                            // 无安全断点，等待下一次 tick
                                            els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
                                            return;
                                        }

                                        const safeChunk = delta.slice(0, lastDoubleNewline + 2);
                                        const rendered = renderMarkdownNoHighlight(safeChunk);
                                        tokenDiv.insertAdjacentHTML('beforeend', rendered);
                                        tokenStream.lastRenderedLength += safeChunk.length;
                                        els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
                                    });
                                }
                            }
                            break;

                        case 'done':
                            accumulatedContent = data.answer || accumulatedContent;

                            if (data.session_id) {
                                finalSessionId = data.session_id;
                            }

                            if (data.sources && data.sources.length > 0) {
                                sourcesData = data.sources;
                            }

                            if (finalSessionId) {
                                if (!state.sessionMessages[finalSessionId]) {
                                    state.sessionMessages[finalSessionId] = [];
                                }
                                state.sessionMessages[finalSessionId].push({
                                    role: 'assistant',
                                    content: accumulatedContent,
                                    sources: sourcesData
                                });
                            }

                            const doneStream = state.pendingStreams[finalSessionId];
                            const doneDiv = doneStream ? doneStream.contentDiv : null;

                            // 取消待处理的增量渲染回调
                            if (doneStream && doneStream.rafId) {
                                cancelAnimationFrame(doneStream.rafId);
                            }

                            delete state.pendingStreams[finalSessionId];
                            state.loadingSessions.delete(finalSessionId);
                            state.loadingSessions.delete(requestSessionId);
                            updateSendButtonState();

                            if (doneDiv) {
                                doneDiv.innerHTML = renderMarkdown(accumulatedContent);
                                removeStreamingCursor(doneDiv);

                                // 添加操作按钮到 msg-body 中
                                const msgBody = doneDiv.closest('.msg-body');
                                if (msgBody) {
                                    addActionButtons(msgBody, accumulatedContent, sourcesData);
                                    if (sourcesData && sourcesData.length > 0) {
                                        appendSourcesToMessage(msgBody, sourcesData);
                                    }
                                }
                            }

                            if (state.sessionId === finalSessionId) {
                                updateSessionIndicator();
                            } else {
                                showToast(`会话 ${finalSessionId.slice(0, 8)} 的 AI 回复已完成`, 'info');
                            }

                            loadSessions();
                            break;

                        case 'error':
                            const errStream = state.pendingStreams[finalSessionId];
                            if (errStream && errStream.rafId) {
                                cancelAnimationFrame(errStream.rafId);
                            }
                            const errDiv = errStream ? errStream.contentDiv : null;
                            if (errDiv) {
                                errDiv.textContent = `❌ ${data.message || '未知错误'}`;
                                removeStreamingCursor(errDiv);
                            }
                            delete state.pendingStreams[finalSessionId];
                            state.loadingSessions.delete(finalSessionId);
                            updateSendButtonState();
                            showToast(data.message || '请求失败', 'error');
                            break;
                    }
                } catch (e) {
                    console.error('Failed to parse SSE event:', e);
                }
            }
        }
    } catch (e) {
        if (e.message === 'stream_read_timeout') {
            console.error('[SSE] reader.read() timed out after 120s');
            showToast('流式响应超时，请重试', 'error');
        } else {
            showToast('网络错误', 'error');
        }
        const netDiv = getStreamingContentDiv(finalSessionId);
        if (netDiv) {
            netDiv.textContent = '❌ 网络错误，请检查后端服务是否启动。';
            removeStreamingCursor(netDiv);
        }
        state.loadingSessions.delete(finalSessionId);
        updateSendButtonState();
    } finally {
        if (finalSessionId) {
            const finalStream = state.pendingStreams[finalSessionId];
            if (finalStream && finalStream.rafId) {
                cancelAnimationFrame(finalStream.rafId);
            }
            delete state.pendingStreams[finalSessionId];
        }
        state.loadingSessions.delete(finalSessionId);
        state.loadingSessions.delete(requestSessionId);
        state.loadingSessions.delete('__pending__');
        updateSendButtonState();
    }
}

function createStreamingMessage() {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message assistant';

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = 'AI';

    const bodyDiv = document.createElement('div');
    bodyDiv.className = 'msg-body';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content streaming';
    contentDiv.innerHTML = '<span class="streaming-cursor"></span>';

    bodyDiv.appendChild(contentDiv);
    msgDiv.appendChild(avatar);
    msgDiv.appendChild(bodyDiv);
    els.chatMessages.appendChild(msgDiv);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;

    return msgDiv;
}

function removeStreamingCursor(contentDiv) {
    const cursor = contentDiv.querySelector('.streaming-cursor');
    if (cursor) cursor.remove();
    contentDiv.classList.remove('streaming');
}

function appendSourcesToMessage(msgDiv, sources) {
    if (!sources || sources.length === 0) return;

    // 移除已存在的来源面板
    const existing = msgDiv.querySelector('.msg-sources');
    if (existing) existing.remove();

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

    // 插入到操作按钮之前
    const actions = msgDiv.querySelector('.msg-actions');
    if (actions) {
        msgDiv.insertBefore(sourcesDiv, actions);
    } else {
        msgDiv.appendChild(sourcesDiv);
    }

    // 更新来源按钮计数
    const toggleBtn = msgDiv.querySelector('.msg-action-btn[title*="来源"]');
    if (toggleBtn) {
        toggleBtn.innerHTML = `📎 来源 (${sources.length})`;
    }
}

function appendSystemMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message system-msg';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = `<p>${escapeHtml(text)}</p>`;

    msgDiv.appendChild(contentDiv);
    els.chatMessages.appendChild(msgDiv);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

// ============ Index Management ============

els.btnBuild.addEventListener('click', () => buildIndex(false));
els.btnRebuild.addEventListener('click', () => buildIndex(true));

async function buildIndex(rebuild) {
    const btn = rebuild ? els.btnRebuild : els.btnBuild;
    btn.disabled = true;
    btn.textContent = '构建中...';
    els.progressWrapper.style.display = 'block';
    els.progressFill.style.width = '0%';
    els.progressText.textContent = rebuild ? '正在重建索引...' : '正在构建索引...';

    try {
        const res = await fetch(`${API_BASE}/api/index/build`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rebuild })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        els.progressFill.style.width = '100%';
        els.progressText.textContent = `构建完成：${data.total_chunks} 个文本块，${data.files_processed} 个文件`;
        showToast('索引构建成功', 'success');
        setTimeout(() => {
            els.progressWrapper.style.display = 'none';
            els.progressFill.style.width = '0%';
            btn.disabled = false;
            btn.textContent = rebuild ? '重建索引' : '构建索引';
            loadIndexStatus();
        }, 2000);
    } catch (e) {
        showToast('构建失败：' + e.message, 'error');
        btn.disabled = false;
        btn.textContent = rebuild ? '重建索引' : '构建索引';
        els.progressWrapper.style.display = 'none';
    }
}

async function loadIndexStatus() {
    try {
        const res = await fetch(`${API_BASE}/api/index/status`);
        const data = await res.json();

        if (data.index_exists) {
            els.badgeIndex.textContent = '已构建';
            els.badgeIndex.className = 'badge success';
            els.metricChunks.textContent = data.total_chunks || 0;
            els.metricFiles.textContent = data.knowledge_base_files?.length || 0;
            els.metricTime.textContent = '就绪';

            if (data.knowledge_base_files?.length > 0) {
                els.kbPanel.style.display = 'block';
                els.kbList.innerHTML = data.knowledge_base_files.map(f => `
                    <div class="kb-file">
                        <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 2h8l2 2v8H2V2z" stroke="currentColor" stroke-width="1.2" fill="none"/><path d="M10 2v2h2" stroke="currentColor" stroke-width="1.2"/></svg>
                        <span class="kb-file-name">${f}</span>
                    </div>
                `).join('');
                els.kbMeta.textContent = `${data.knowledge_base_files.length} 个文件`;

                els.filesList.innerHTML = data.knowledge_base_files.map(f => `
                    <div class="file-item">
                        <svg class="file-item-icon" width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 2h8l2 2v8H2V2z" stroke="currentColor" stroke-width="1.2" fill="none"/></svg>
                        <span class="file-item-name">${f}</span>
                    </div>
                `).join('');
            }
        } else {
            els.badgeIndex.textContent = '未构建';
            els.badgeIndex.className = 'badge warning';
            els.metricChunks.textContent = '0';
            els.metricFiles.textContent = '0';
            els.metricTime.textContent = '-';
            els.kbPanel.style.display = 'none';
            els.filesList.innerHTML = '<p class="empty-state">暂无数据，请先构建索引</p>';
        }
    } catch (e) {
        els.badgeIndex.textContent = '错误';
        els.badgeIndex.className = 'badge error';
        els.filesList.innerHTML = '<p class="empty-state">无法连接后端服务</p>';
    }
}

// ============ Toast ============
function showToast(message, type = 'info') {
    els.toast.textContent = message;
    els.toast.className = `toast show ${type}`;
    setTimeout(() => {
        els.toast.className = 'toast';
    }, 3000);
}

// ============ File Management ============

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

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

function getFileIcon(fileType) {
    const icons = { md: '📝', pdf: '📄', docx: '📘' };
    return icons[fileType] || '📄';
}

async function loadFileList() {
    if (!fileEls.fileList) return;
    fileEls.fileList.innerHTML = '<div class="file-list-empty">加载中...</div>';

    try {
        const res = await fetch(`${API_BASE}/api/files`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        fileEls.fileCount.textContent = data.total_files;

        if (data.files.length === 0) {
            fileEls.fileList.innerHTML = '<div class="file-list-empty">暂无知识库文件，请上传</div>';
            return;
        }

        fileEls.fileList.innerHTML = data.files.map(f => `
            <div class="file-item">
                <span class="file-icon">${getFileIcon(f.file_type)}</span>
                <div class="file-info">
                    <div class="file-name">${escapeHtml(f.filename)}</div>
                    <div class="file-meta">${formatFileSize(f.size)} · ${f.file_type.toUpperCase()} · ${formatRelativeTime(f.modified_time)}</div>
                </div>
                <span class="file-type-badge">${f.file_type}</span>
                <button class="btn-delete-file" data-filename="${escapeHtml(f.filename)}" title="删除">×</button>
            </div>
        `).join('');

        fileEls.fileList.querySelectorAll('.btn-delete-file').forEach(btn => {
            btn.addEventListener('click', () => handleFileDelete(btn.dataset.filename));
        });
    } catch (e) {
        console.error('Failed to load file list:', e);
        fileEls.fileList.innerHTML = '<div class="file-list-empty">加载失败，请检查后端服务</div>';
    }
}

function handleFileUpload(files) {
    if (!files || files.length === 0) return;

    const file = files[0];
    const MAX_SIZE = 50 * 1024 * 1024; // 50MB
    if (file.size > MAX_SIZE) {
        showToast(`文件大小超过限制（${formatFileSize(MAX_SIZE)}），请压缩后重试`, 'error');
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    fileEls.uploadProgress.style.display = 'flex';
    fileEls.progressFill.style.width = '0%';
    fileEls.progressText.textContent = `上传中: ${file.name}`;

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
            const percent = Math.round((e.loaded / e.total) * 100);
            fileEls.progressFill.style.width = percent + '%';
            fileEls.progressText.textContent = `上传中... ${percent}%`;
        }
    });

    xhr.addEventListener('load', () => {
        if (xhr.status >= 200 && xhr.status < 300) {
            const data = JSON.parse(xhr.responseText);
            showToast(data.message, 'success');
            fileEls.progressText.textContent = '索引重建中...';
            setTimeout(() => {
                fileEls.uploadProgress.style.display = 'none';
                loadFileList();
            }, 1500);
        } else {
            let errMsg = '上传失败';
            try {
                const errData = JSON.parse(xhr.responseText);
                errMsg = errData.detail || errMsg;
            } catch {}
            showToast(errMsg, 'error');
            fileEls.uploadProgress.style.display = 'none';
        }
    });

    xhr.addEventListener('error', () => {
        showToast('网络错误，上传失败', 'error');
        fileEls.uploadProgress.style.display = 'none';
    });

    xhr.open('POST', `${API_BASE}/api/files/upload`);
    applyXhrAuth(xhr);
    xhr.send(formData);
}

async function handleFileDelete(filename) {
    if (!confirm(`确定删除文件「${filename}」吗？删除后将自动重建索引。`)) return;

    try {
        const res = await fetch(`${API_BASE}/api/files/${encodeURIComponent(filename)}`, {
            method: 'DELETE'
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || `HTTP ${res.status}`);
        }

        const data = await res.json();
        showToast(data.message, 'success');
        loadFileList();
    } catch (e) {
        console.error('Delete failed:', e);
        showToast('删除失败: ' + e.message, 'error');
    }
}

// 文件管理事件监听
if (fileEls.uploadZone) {
    fileEls.uploadZone.addEventListener('click', () => {
        fileEls.fileInput.click();
    });

    fileEls.fileInput.addEventListener('change', (e) => {
        handleFileUpload(e.target.files);
        e.target.value = '';
    });

    fileEls.uploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        fileEls.uploadZone.classList.add('dragover');
    });

    fileEls.uploadZone.addEventListener('dragleave', () => {
        fileEls.uploadZone.classList.remove('dragover');
    });

    fileEls.uploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        fileEls.uploadZone.classList.remove('dragover');
        handleFileUpload(e.dataTransfer.files);
    });
}

if (fileEls.btnRefresh) {
    fileEls.btnRefresh.addEventListener('click', loadFileList);
}

// ============ Session Search ============

const searchInput = document.getElementById('session-search');
let searchDebounceTimer = null;

if (searchInput) {
    searchInput.addEventListener('input', () => {
        clearTimeout(searchDebounceTimer);
        const query = searchInput.value.trim();

        if (!query) {
            // 清空搜索，恢复会话列表
            renderSessions();
            return;
        }

        searchDebounceTimer = setTimeout(() => {
            handleSessionSearch(query);
        }, 300);
    });
}

async function handleSessionSearch(query) {
    try {
        const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(query)}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderSearchResults(data.results, query);
    } catch (e) {
        console.error('Search failed:', e);
        els.sessionsList.innerHTML = '<div class="session-empty">搜索失败</div>';
    }
}

function renderSearchResults(results, query) {
    if (!els.sessionsList) return;

    if (results.length === 0) {
        els.sessionsList.innerHTML = `<div class="session-empty">未找到包含「${escapeHtml(query)}」的对话</div>`;
        return;
    }

    els.sessionsList.innerHTML = results.map(r => {
        const title = r.title || `会话 ${r.session_id.slice(0, 8)}`;
        const roleLabel = r.role === 'user' ? '提问' : '回答';

        // 高亮关键词
        const escapedSnippet = escapeHtml(r.content_snippet);
        const escapedQuery = escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const highlightedSnippet = escapedSnippet.replace(
            new RegExp(`(${escapedQuery})`, 'gi'),
            '<mark class="search-highlight">$1</mark>'
        );

        return `
            <div class="search-result-item" data-session-id="${r.session_id}">
                <div class="search-result-title">${escapeHtml(title)}</div>
                <div class="search-result-snippet">${highlightedSnippet}</div>
                <div class="search-result-meta">${roleLabel}</div>
            </div>
        `;
    }).join('');

    }

// ============ Auth Module ============

const AUTH_TOKEN_KEY = 'rag_auth_token';
const AUTH_USER_KEY = 'rag_auth_user';

let authState = {
    user: null,
    token: null,
    isRegisterMode: false
};

// Pydantic 422 校验错误的字段名 -> 中文映射。
const AUTH_FIELD_LABELS = {
    username: '用户名',
    password: '密码',
    display_name: '显示名称'
};

// Pydantic v2 校验错误类型 -> 中文消息模板。不支持的类型回退显示原始 msg。
function formatValidationError(item) {
    const loc = item.loc || [];
    // loc 形如 ["body", "username"]，取最后一个作为字段名
    let field = loc[loc.length - 1];
    field = typeof field === 'string' ? field : null;
    const label = field ? (AUTH_FIELD_LABELS[field] || field) : null;

    const type = item.type || '';
    const ctx = item.ctx || {};
    const minLen = typeof ctx.min_length === 'number' ? ctx.min_length : null;
    const maxLen = typeof ctx.max_length === 'number' ? ctx.max_length : null;

    let message = null;
    if (type === 'string_too_short' && minLen !== null) {
        message = (label ? `${label}长度至少 ${minLen} 个字符` : `长度至少 ${minLen} 个字符`);
    } else if (type === 'string_too_long' && maxLen !== null) {
        message = (label ? `${label}长度不能超过 ${maxLen} 个字符` : `长度不能超过 ${maxLen} 个字符`);
    } else if (type === 'missing' && label) {
        message = `${label}不能为空`;
    } else if (type === 'string_type' && label) {
        message = `${label}格式不正确`;
    } else {
        // 未知类型：回退原始 msg，保证不丢信息
        message = item.msg || '请求参数有误';
    }
    return message;
}

// 解析 API 错误响应：
// - detail 为字符串（400/401 等）-> 原样返回；
// - detail 为数组（Pydantic 422）-> 逐条中文化，返回字符串数组；
// - 其他 -> fallback。
function parseApiError(errJson, status, fallback) {
    if (errJson && typeof errJson.detail === 'string') {
        return errJson.detail || fallback;
    }
    if (errJson && Array.isArray(errJson.detail)) {
        const messages = errJson.detail
            .map(item => formatValidationError(item))
            .filter(Boolean);
        if (messages.length > 0) {
            return messages;
        }
    }
    if (fallback) return fallback;
    return status ? `请求失败（HTTP ${status}）` : '请求失败';
}

function getAuthErrorEl() {
    return document.getElementById('auth-error');
}

// 在登录模态框表单上方展示验证错误（多条逐行），并附加一条汇总 toast。
function showAuthError(message) {
    const el = getAuthErrorEl();
    const elEls = Array.isArray(message) ? message : [message];
    const messages = elEls.filter(Boolean);
    if (el && messages.length > 0) {
        const safeText = messages.map(m => escapeHtml(String(m)));
        el.innerHTML = safeText.join('<br>');
        el.style.display = 'block';
    }
    showToast(Array.isArray(message) ? message[0] : message, 'error');
}

function clearAuthError() {
    const el = getAuthErrorEl();
    if (el) {
        el.innerHTML = '';
        el.style.display = 'none';
    }
}

function initAuth() {
    authState.token = localStorage.getItem(AUTH_TOKEN_KEY);
    authState.user = JSON.parse(localStorage.getItem(AUTH_USER_KEY) || 'null');

    if (authState.token && authState.user) {
        showUserPanel();
    } else {
        showLoginPrompt();
    }

    document.getElementById('btn-login').addEventListener('click', openLoginModal);
    document.getElementById('btn-logout').addEventListener('click', handleLogout);
    document.getElementById('modal-close').addEventListener('click', closeLoginModal);
    document.getElementById('btn-switch-form').addEventListener('click', switchAuthMode);
    document.getElementById('btn-submit-login').addEventListener('click', handleAuthSubmit);

    const pwdInput = document.getElementById('login-password');
    const usrInput = document.getElementById('login-username');
    if (pwdInput) {
        pwdInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') handleAuthSubmit();
        });
    }
    if (usrInput) {
        usrInput.addEventListener('keydown', e => {
            if (e.key === 'Enter') handleAuthSubmit();
        });
    }
}

function openLoginModal() {
    authState.isRegisterMode = false;
    updateAuthModalUI();
    clearAuthError();
    document.getElementById('login-modal').style.display = 'flex';
    setTimeout(() => document.getElementById('login-username').focus(), 100);
}

function closeLoginModal() {
    document.getElementById('login-modal').style.display = 'none';
}

function switchAuthMode() {
    authState.isRegisterMode = !authState.isRegisterMode;
    updateAuthModalUI();
    clearAuthError();
}

function updateAuthModalUI() {
    const modalTitle = document.getElementById('modal-title');
    const submitBtn = document.getElementById('btn-submit-login');
    const switchText = document.getElementById('switch-text');
    const switchBtn = document.getElementById('btn-switch-form');
    const displayNameGroup = document.getElementById('display-name-group');

    if (authState.isRegisterMode) {
        modalTitle.textContent = '注册账号';
        submitBtn.textContent = '注册';
        switchText.textContent = '已有账号？';
        switchBtn.textContent = '立即登录';
        displayNameGroup.style.display = 'block';
    } else {
        modalTitle.textContent = '登录';
        submitBtn.textContent = '登录';
        switchText.textContent = '还没有账号？';
        switchBtn.textContent = '立即注册';
        displayNameGroup.style.display = 'none';
    }
}

async function handleAuthSubmit() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const displayName = document.getElementById('register-display-name')?.value.trim();

    if (!username || !password) {
        showToast('请输入用户名和密码', 'error');
        return;
    }

    const btn = document.getElementById('btn-submit-login');
    btn.disabled = true;
    const originalText = btn.textContent;
    btn.textContent = authState.isRegisterMode ? '注册中...' : '登录中...';

    try {
        let res;
        if (authState.isRegisterMode) {
            res = await fetch(`${API_BASE}/api/auth/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username,
                    password,
                    display_name: displayName || null
                })
            });
        } else {
            res = await fetch(`${API_BASE}/api/auth/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, password })
            });
        }

        if (!res.ok) {
            let errJson = null;
            try { errJson = await res.json(); } catch { errJson = null; }
            // 422 时 detail 为数组，parseApiError 负责中文化；400/401 字符串原样展示
            const message = parseApiError(errJson, res.status);
            showAuthError(message);
            return;
        }

        const data = await res.json();
        authState.token = data.token;
        authState.user = data.user;

        localStorage.setItem(AUTH_TOKEN_KEY, data.token);
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user));

        showUserPanel();
        clearAuthError();
        closeLoginModal();
        showToast(authState.isRegisterMode ? '注册成功' : '登录成功', 'success');

        // 登录/注册后拉取当前用户自己的会话列表，避免残留上一用户的会话
        await loadSessions();

        document.getElementById('login-username').value = '';
        document.getElementById('login-password').value = '';
        document.getElementById('register-display-name').value = '';

    } catch (e) {
        showAuthError('网络错误，请稍后重试');
    } finally {
        btn.disabled = false;
        btn.textContent = originalText;
    }
}

async function handleLogout() {
    if (!confirm('确定要退出登录吗？')) return;

    authState.token = null;
    authState.user = null;
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(AUTH_USER_KEY);

    showLoginPrompt();
    showToast('已退出登录', 'info');
}

function showUserPanel() {
    const panel = document.getElementById('user-panel');
    const prompt = document.getElementById('login-prompt');

    panel.style.display = 'flex';
    prompt.style.display = 'none';

    const nameEl = document.getElementById('user-name');
    const avatarEl = document.getElementById('user-avatar');
    if (authState.user) {
        nameEl.textContent = authState.user.display_name || authState.user.username;
        avatarEl.textContent = (authState.user.display_name || authState.user.username).charAt(0).toUpperCase();
    }
}

function showLoginPrompt() {
    const panel = document.getElementById('user-panel');
    const prompt = document.getElementById('login-prompt');

    panel.style.display = 'none';
    prompt.style.display = 'block';
}

function getAuthHeaders() {
    if (authState.token) {
        return { 'Authorization': `Bearer ${authState.token}` };
    }
    return {};
}

// token 失效或未登录时：清除缓存并回到登录提示态
function handleAuthExpired() {
    authState.token = null;
    authState.user = null;
    localStorage.removeItem(AUTH_TOKEN_KEY);
    localStorage.removeItem(AUTH_USER_KEY);
    showLoginPrompt();
    showToast('登录已过期，请重新登录', 'error');
}

// ============ Init ============
checkHealth();
loadIndexStatus();
loadSessions();
initAuth();
initSettingsTabs();
setInterval(checkHealth, 30000);

// ============ Interview Module ============

const interviewState = {
    sessionId: null,
    currentQuestionId: null,
    currentRound: 0,
    position: '',
    isSubmitting: false,
    isComplete: false,
    resumeFile: null,
    nextQuestion: null,
    reanswering: false,
};

const interviewEls = {
    ready: document.getElementById('interview-ready'),
    progress: document.getElementById('interview-progress'),
    loading: document.getElementById('interview-loading'),
    report: document.getElementById('interview-report'),
    positionBadge: document.getElementById('interview-position-badge'),
    round: document.getElementById('interview-round'),
    difficulty: document.getElementById('interview-difficulty'),
    questionText: document.getElementById('question-text'),
    questionTags: document.getElementById('question-tags'),
    tagCategory: document.getElementById('tag-category'),
    tagTopic: document.getElementById('tag-topic'),
    coverageStats: document.getElementById('coverage-stats'),
    coverageCount: document.getElementById('coverage-count'),
    coverageBars: document.getElementById('coverage-bars'),
    answerInput: document.getElementById('answer-input'),
    btnSubmit: document.getElementById('btn-submit-answer'),
    btnStart: document.getElementById('btn-start-interview'),
    btnEnd: document.getElementById('btn-end-interview'),
    evaluationArea: document.getElementById('evaluation-area'),
    evaluationScore: document.getElementById('evaluation-score'),
    evaluationComment: document.getElementById('evaluation-comment'),
    evaluationDetail: document.getElementById('evaluation-detail'),
    evaluationReason: document.getElementById('evaluation-reason'),
    referenceBlock: document.getElementById('reference-block'),
    btnToggleReference: document.getElementById('btn-toggle-reference'),
    referenceAnswer: document.getElementById('reference-answer'),
    evaluationTags: document.getElementById('evaluation-tags'),
    evaluationActions: document.getElementById('evaluation-actions'),
    btnNextQuestion: document.getElementById('btn-next-question'),
    btnReanswer: document.getElementById('btn-reanswer'),
    btnEndAfterAnswer: document.getElementById('btn-end-after-answer'),
    loadingText: document.getElementById('loading-text'),
    reportScore: document.getElementById('report-score-num'),
    reportLevel: document.getElementById('report-level'),
    reportPosition: document.getElementById('report-position'),
    reportScores: document.getElementById('report-scores'),
    reportStrengths: document.getElementById('report-strengths'),
    reportWeaknesses: document.getElementById('report-weaknesses'),
    reportSuggestions: document.getElementById('report-suggestions'),
    reportTopicSection: document.getElementById('report-topic-section'),
    topicAnalysis: document.getElementById('topic-analysis'),
    reportStudySection: document.getElementById('report-study-section'),
    recommendedStudy: document.getElementById('recommended-study'),
    btnNew: document.getElementById('btn-new-interview'),
    btnHistory: document.getElementById('btn-view-history'),
    positionBtns: document.querySelectorAll('.position-btn'),
    resumeUploadZone: document.getElementById('resume-upload-zone'),
    resumeFileInput: document.getElementById('resume-file-input'),
    resumeFileInfo: document.getElementById('resume-file-info'),
    resumeFileName: document.getElementById('resume-file-name'),
    resumeFileRemove: document.getElementById('resume-file-remove'),
    resumeUploadProgress: document.getElementById('resume-upload-progress'),
    resumeUploadProgressFill: document.getElementById('resume-upload-progress-fill'),
    resumeUploadProgressText: document.getElementById('resume-upload-progress-text'),
    jdInput: document.getElementById('jd-input'),
};

const reviewEls = {
    todayPlaceholder: document.getElementById('today-placeholder'),
    todayQuestion: document.getElementById('today-question'),
    todayTags: document.getElementById('today-tags'),
    todayText: document.getElementById('today-text'),
    todayPosition: document.getElementById('today-position'),
    btnTodayRefresh: document.getElementById('btn-today-refresh'),
    statsTotal: document.getElementById('stats-total'),
    weakStats: document.getElementById('weak-stats'),
    historyList: document.getElementById('history-list'),
    historyEmpty: document.getElementById('history-empty'),
    btnRefreshHistory: document.getElementById('btn-refresh-history'),
    historyDetail: document.getElementById('history-detail'),
};

function initInterview() {
    // 岗位选择
    interviewEls.positionBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            interviewEls.positionBtns.forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            interviewState.position = btn.dataset.position;
            interviewEls.btnStart.disabled = false;
        });
    });

    // 开始面试
    interviewEls.btnStart.addEventListener('click', startInterview);
    interviewEls.btnSubmit.addEventListener('click', submitAnswer);
    interviewEls.btnEnd.addEventListener('click', endInterview);
    interviewEls.btnNew.addEventListener('click', resetInterview);
    interviewEls.btnHistory.addEventListener('click', () => switchView('review'));

    // 用户可控节奏：下一题 / 再答一次 / 结束
    interviewEls.btnNextQuestion.addEventListener('click', goNextQuestion);
    interviewEls.btnReanswer.addEventListener('click', reanswerQuestion);
    interviewEls.btnEndAfterAnswer.addEventListener('click', endInterview);

    // 参考答案折叠切换（静态按钮，仅绑定一次）
    if (interviewEls.btnToggleReference) {
        interviewEls.btnToggleReference.addEventListener('click', () => {
            const hidden = interviewEls.referenceAnswer.style.display === 'none';
            interviewEls.referenceAnswer.style.display = hidden ? 'block' : 'none';
            interviewEls.btnToggleReference.textContent = hidden ? '收起参考答案' : '查看参考答案';
        });
    }

    // 回答输入
    interviewEls.answerInput.addEventListener('input', () => {
        interviewEls.btnSubmit.disabled = !interviewEls.answerInput.value.trim() || interviewState.isSubmitting;
    });
    interviewEls.answerInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
            e.preventDefault();
            submitAnswer();
        }
    });

    // Resume upload: click to select
    interviewEls.resumeUploadZone.addEventListener('click', () => {
        interviewEls.resumeFileInput.click();
    });

    // Resume file selected
    interviewEls.resumeFileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            interviewState.resumeFile = file;
            interviewEls.resumeFileName.textContent = file.name;
            interviewEls.resumeFileInfo.style.display = 'flex';
            interviewEls.resumeUploadZone.style.display = 'none';
        }
    });

    // Resume file remove
    interviewEls.resumeFileRemove.addEventListener('click', (e) => {
        e.stopPropagation();
        interviewState.resumeFile = null;
        interviewEls.resumeFileInput.value = '';
        interviewEls.resumeFileInfo.style.display = 'none';
        interviewEls.resumeUploadZone.style.display = 'block';
    });

    // Resume drag & drop
    interviewEls.resumeUploadZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        interviewEls.resumeUploadZone.classList.add('dragover');
    });
    interviewEls.resumeUploadZone.addEventListener('dragleave', () => {
        interviewEls.resumeUploadZone.classList.remove('dragover');
    });
    interviewEls.resumeUploadZone.addEventListener('drop', (e) => {
        e.preventDefault();
        interviewEls.resumeUploadZone.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.type === 'application/pdf') {
            interviewState.resumeFile = file;
            interviewEls.resumeFileName.textContent = file.name;
            interviewEls.resumeFileInfo.style.display = 'flex';
            interviewEls.resumeUploadZone.style.display = 'none';
        }
    });
}

function startInterview() {
    if (!interviewState.position) return;

    showInterviewLoading('AI 面试官正在出题...');
    interviewState.isComplete = false;

    const formData = new FormData();
    formData.append('position', interviewState.position);

    if (interviewState.resumeFile) {
        formData.append('resume_file', interviewState.resumeFile);
    }

    const jdText = interviewEls.jdInput.value.trim();
    if (jdText) {
        formData.append('jd_text', jdText);
    }

    // 有简历时显示上传进度条
    if (interviewState.resumeFile && interviewEls.resumeUploadProgress) {
        interviewEls.resumeUploadProgress.style.display = 'flex';
        interviewEls.resumeUploadProgressFill.style.width = '0%';
        interviewEls.resumeUploadProgressText.textContent = `上传中: ${interviewState.resumeFile.name}`;
    }

    const xhr = new XMLHttpRequest();

    xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable && interviewEls.resumeUploadProgress) {
            const percent = Math.round((e.loaded / e.total) * 100);
            interviewEls.resumeUploadProgressFill.style.width = percent + '%';
            interviewEls.resumeUploadProgressText.textContent = `上传中... ${percent}%`;
        }
    });

    xhr.addEventListener('load', () => {
        if (interviewEls.resumeUploadProgress) {
            interviewEls.resumeUploadProgress.style.display = 'none';
        }
        if (xhr.status >= 200 && xhr.status < 300) {
            let data;
            try { data = JSON.parse(xhr.responseText); } catch { data = null; }
            if (!data) { showToast('error', '出题失败: 响应解析失败'); showInterviewReady(); return; }
            interviewState.sessionId = data.session_id;
            interviewState.currentQuestionId = data.question.id;
            interviewState.currentRound = data.question.round;
            interviewState.nextQuestion = null;
            interviewState.reanswering = false;
            showInterviewProgress(data.question);
        } else {
            let errMsg = '出题失败';
            try { const errData = JSON.parse(xhr.responseText); errMsg = '出题失败: ' + (errData.detail || '请求失败'); } catch {}
            showToast('error', errMsg);
            showInterviewReady();
        }
    });

    xhr.addEventListener('error', () => {
        if (interviewEls.resumeUploadProgress) {
            interviewEls.resumeUploadProgress.style.display = 'none';
        }
        showToast('error', '网络错误，出题失败');
        showInterviewReady();
    });

    xhr.open('POST', `${API_BASE}/api/interview/start`);
    applyXhrAuth(xhr);
    xhr.send(formData);
}

async function submitAnswer() {
    if (ddState.mode) { return submitDeepDiveAnswer(); }
    const answer = interviewEls.answerInput.value.trim();
    if (!answer || interviewState.isSubmitting) return;

    interviewState.isSubmitting = true;
    interviewEls.btnSubmit.disabled = true;
    interviewEls.btnSubmit.textContent = '评价中...';
    interviewEls.answerInput.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/api/interview/answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question_id: interviewState.currentQuestionId,
                answer: answer,
                // 再答一次时不重新生成下一题，保留上一轮的结果，避免重复题目落库
                generate_next: !interviewState.reanswering
            })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '提交回答失败');
        }

        const data = await res.json();
        showEvaluation(data.evaluation);

        interviewState.isSubmitting = false;
        interviewEls.btnSubmit.textContent = '提交回答';

        if (data.is_complete && data.report) {
            // 面试自然结束，直接展示报告
            setTimeout(() => showInterviewReport(data.report, interviewState.position), 800);
            return;
        }

        // 保存下一题（再答一次时后端不生成，沿用上一轮结果）
        if (data.next_question) {
            interviewState.nextQuestion = data.next_question;
        }

        // 把节奏交给用户：展示「下一题 / 再答一次 / 结束面试」
        interviewEls.evaluationActions.style.display = 'flex';
    } catch (e) {
        showToast('提交失败: ' + e.message, 'error');
        interviewState.isSubmitting = false;
        interviewEls.btnSubmit.disabled = false;
        interviewEls.btnSubmit.textContent = '提交回答';
        interviewEls.answerInput.disabled = false;
    }
}

function goNextQuestion() {
    const q = interviewState.nextQuestion;
    if (!q) return;
    interviewState.currentQuestionId = q.id;
    interviewState.currentRound = q.round;
    interviewState.nextQuestion = null;
    interviewState.reanswering = false;
    hideEvaluation();
    showInterviewProgress(q);
}

function reanswerQuestion() {
    // 留在当前题，重新作答并重新评价
    interviewState.reanswering = true;
    interviewEls.evaluationActions.style.display = 'none';
    hideEvaluation();
    interviewEls.answerInput.disabled = false;
    interviewEls.answerInput.value = '';
    interviewEls.btnSubmit.disabled = true;
    interviewEls.btnSubmit.textContent = '提交回答';
    interviewEls.answerInput.focus();
}

async function endInterview() {
    if (!confirm('确定结束当前面试吗？')) return;
    if (!interviewState.sessionId) return;

    showInterviewLoading('正在生成面试报告...');

    try {
        const res = await fetch(`${API_BASE}/api/interview/end`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: interviewState.sessionId })
        });

        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '结束面试失败');
        }

        const data = await res.json();
        showInterviewReport(data.report, interviewState.position);
    } catch (e) {
        showToast('结束面试失败: ' + e.message, 'error');
        showInterviewProgress({});
    }
}

function showInterviewLoading(text) {
    interviewEls.ready.style.display = 'none';
    interviewEls.progress.style.display = 'none';
    interviewEls.report.style.display = 'none';
    interviewEls.loading.style.display = 'flex';
    interviewEls.loadingText.textContent = text || 'AI 面试官正在出题...';
}

function showInterviewProgress(question) {
    interviewEls.ready.style.display = 'none';
    interviewEls.loading.style.display = 'none';
    interviewEls.report.style.display = 'none';
    interviewEls.progress.style.display = 'flex';

    // 新题展示时隐藏评价与操作按钮
    interviewEls.evaluationArea.style.display = 'none';
    interviewEls.evaluationActions.style.display = 'none';

    interviewEls.positionBadge.textContent = interviewState.position;
    interviewEls.round.textContent = `第 ${question.round || 1} 题`;
    interviewEls.difficulty.textContent = `难度：${question.difficulty === 'easy' ? '偏易' : question.difficulty === 'hard' ? '偏难' : '适中'}`;
    interviewEls.questionText.textContent = question.content || '加载中...';
    interviewEls.answerInput.value = '';
    interviewEls.answerInput.disabled = false;
    interviewEls.btnSubmit.disabled = true;
    interviewEls.btnSubmit.textContent = '提交回答';
    interviewEls.answerInput.focus();

    // 显示 topic/category 标签
    if (question.topic || question.category) {
        interviewEls.questionTags.style.display = 'flex';
        interviewEls.tagCategory.textContent = question.category || '';
        interviewEls.tagTopic.textContent = question.topic || '';
    } else {
        interviewEls.questionTags.style.display = 'none';
    }

    // 获取并显示覆盖统计
    if (interviewState.sessionId) {
        fetchCoverageStats(interviewState.sessionId, interviewState.position);
    }
}

async function fetchCoverageStats(sessionId, position) {
    try {
        const res = await fetch(`${API_BASE}/api/interview/coverage?session_id=${encodeURIComponent(sessionId)}&position=${encodeURIComponent(position)}`);
        if (!res.ok) {
            interviewEls.coverageStats.style.display = 'none';
            return;
        }
        const data = await res.json();
        renderCoverageStats(data);
    } catch (e) {
        interviewEls.coverageStats.style.display = 'none';
    }
}

function renderCoverageStats(coverage) {
    const categories = coverage.categories || {};
    const keys = Object.keys(categories);
    if (keys.length === 0) {
        interviewEls.coverageStats.style.display = 'none';
        return;
    }

    interviewEls.coverageStats.style.display = 'block';
    interviewEls.coverageCount.textContent = `${coverage.total_covered || 0}/${coverage.total_topics || 0}`;

    interviewEls.coverageBars.innerHTML = keys.map(catName => {
        const info = categories[catName];
        const pct = info.total > 0 ? Math.round((info.covered / info.total) * 100) : 0;
        const status = pct === 100 ? 'done' : pct > 0 ? 'partial' : 'empty';
        return `
            <div class="coverage-item">
                <div class="coverage-item-header">
                    <span class="coverage-item-name">${escapeHtml(catName)}</span>
                    <span class="coverage-item-count">${info.covered}/${info.total}</span>
                </div>
                <div class="coverage-bar">
                    <div class="coverage-bar-fill ${status}" style="width:${pct}%"></div>
                </div>
            </div>
        `;
    }).join('');
}

function showInterviewReady() {
    interviewEls.loading.style.display = 'none';
    interviewEls.progress.style.display = 'none';
    interviewEls.report.style.display = 'none';
    interviewEls.ready.style.display = 'flex';
}

function showEvaluation(evaluation) {
    interviewEls.evaluationArea.style.display = 'block';
    interviewEls.evaluationScore.textContent = `${evaluation.score}/10`;
    interviewEls.evaluationComment.textContent = evaluation.comment || '';

    // 评分原因 + 参考答案（判空降级：缺失字段或元素不存在时隐藏对应区块）
    const reason = evaluation.score_reason || '';
    const ref = evaluation.reference_answer || '';
    if (interviewEls.evaluationReason) {
        interviewEls.evaluationReason.textContent = reason;
        const reasonBlock = interviewEls.evaluationReason.closest('.eval-block');
        if (reasonBlock) reasonBlock.style.display = reason ? 'block' : 'none';
    }
    if (interviewEls.referenceAnswer && interviewEls.btnToggleReference) {
        interviewEls.referenceAnswer.textContent = ref;
        interviewEls.referenceAnswer.style.display = 'none';
        interviewEls.btnToggleReference.textContent = '查看参考答案';
    }
    if (interviewEls.referenceBlock) interviewEls.referenceBlock.style.display = ref ? 'block' : 'none';
    if (interviewEls.evaluationDetail) interviewEls.evaluationDetail.style.display = (reason || ref) ? 'block' : 'none';

    interviewEls.evaluationTags.innerHTML = (evaluation.tags || []).map(tag =>
        `<span class="evaluation-tag">${escapeHtml(tag)}</span>`
    ).join('');
    interviewEls.evaluationArea.scrollIntoView({ behavior: 'smooth' });
}

function hideEvaluation() {
    interviewEls.evaluationArea.style.display = 'none';
    interviewEls.evaluationArea.style.animation = 'none';
    // Force reflow to re-trigger animation
    void interviewEls.evaluationArea.offsetWidth;
    interviewEls.evaluationArea.style.animation = '';
}

function showInterviewReport(report, position) {
    interviewEls.loading.style.display = 'none';
    interviewEls.progress.style.display = 'none';
    interviewEls.ready.style.display = 'none';
    interviewEls.report.style.display = 'flex';

    interviewEls.reportPosition.textContent = position || interviewState.position;
    interviewEls.reportScore.textContent = report.total_score || '0';
    interviewEls.reportLevel.textContent = report.level || '未知';

    // 得分详情
    interviewEls.reportScores.innerHTML = '';
    if (report.score_breakdown) {
        report.score_breakdown.forEach(item => {
            const div = document.createElement('div');
            div.className = 'report-score-item';
            div.innerHTML = `
                <div class="report-score-item-row">
                    <span class="report-score-round">${item.round}</span>
                    <span class="report-score-question">${escapeHtml(item.question || '')}</span>
                    <div class="report-score-tags">${(item.tags || []).map(t => `<span class="report-score-tag">${escapeHtml(t)}</span>`).join('')}</div>
                    <span class="report-score-value">${item.score}</span>
                </div>
                ${buildEvalCollapse('评分原因', item.score_reason)}
                ${buildEvalCollapse('参考答案', item.reference_answer)}
            `;
            interviewEls.reportScores.appendChild(div);
        });
        bindEvalCollapse(interviewEls.reportScores);
    }

    // 知识分析
    const analysis = report.knowledge_analysis || {};
    interviewEls.reportStrengths.innerHTML = (analysis.strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('');
    interviewEls.reportWeaknesses.innerHTML = (analysis.weaknesses || []).map(w => `<li>${escapeHtml(w)}</li>`).join('');

    // 改进建议
    interviewEls.reportSuggestions.innerHTML = (report.improvement_suggestions || []).map(s =>
        `<li>${escapeHtml(s)}</li>`
    ).join('');

    // topic_analysis 知识分类分析
    if (report.topic_analysis && report.topic_analysis.length > 0) {
        interviewEls.reportTopicSection.style.display = 'block';
        interviewEls.topicAnalysis.innerHTML = report.topic_analysis.map(ta => {
            const statusLabel = ta.status === 'strong' ? '掌握较好' : ta.status === 'moderate' ? '基础尚可' : '需要加强';
            const statusClass = ta.status === 'strong' ? 'ta-strong' : ta.status === 'moderate' ? 'ta-moderate' : 'ta-weak';
            const pct = Math.round((ta.avg_score / 10) * 100);
            return `
                <div class="ta-item">
                    <div class="ta-header">
                        <span class="ta-category">${escapeHtml(ta.category)}</span>
                        <span class="ta-badge ${statusClass}">${statusLabel}</span>
                    </div>
                    <div class="ta-bar">
                        <div class="ta-bar-fill ${statusClass}" style="width:${pct}%"></div>
                    </div>
                    <div class="ta-meta">
                        <span>覆盖 ${ta.topics_covered} 个知识点</span>
                        <span>均分 ${ta.avg_score}/10</span>
                    </div>
                </div>
            `;
        }).join('');
    } else {
        interviewEls.reportTopicSection.style.display = 'none';
    }

    // recommended_study 学习建议
    if (report.recommended_study && report.recommended_study.length > 0) {
        interviewEls.reportStudySection.style.display = 'block';
        interviewEls.recommendedStudy.innerHTML = report.recommended_study.map(rs => {
            const priorityLabel = rs.priority === 'high' ? '高优先级' : '中优先级';
            const priorityClass = rs.priority === 'high' ? 'rs-high' : 'rs-medium';
            return `
                <div class="rs-item">
                    <div class="rs-header">
                        <span class="rs-category">${escapeHtml(rs.category)}</span>
                        <span class="rs-priority ${priorityClass}">${priorityLabel}</span>
                    </div>
                    <div class="rs-reason">${escapeHtml(rs.reason)}</div>
                </div>
            `;
        }).join('');
    } else {
        interviewEls.reportStudySection.style.display = 'none';
    }
}

function resetInterview() {
    interviewState.sessionId = null;
    interviewState.currentQuestionId = null;
    interviewState.currentRound = 0;
    interviewState.isSubmitting = false;
    interviewState.isComplete = false;
    interviewState.nextQuestion = null;
    interviewState.reanswering = false;

    interviewEls.positionBtns.forEach(b => b.classList.remove('selected'));
    interviewEls.btnStart.disabled = true;
    interviewEls.evaluationArea.style.display = 'none';
    interviewEls.evaluationActions.style.display = 'none';

    // Reset resume + JD
    interviewState.resumeFile = null;
    interviewEls.resumeFileInput.value = '';
    interviewEls.resumeFileInfo.style.display = 'none';
    interviewEls.resumeUploadZone.style.display = 'block';
    interviewEls.jdInput.value = '';

    showInterviewReady();
}

// 初始化面试模块
initInterview();

// ============ Review Page Module ============

async function loadReviewData() {
    // 复习画像按用户隔离：副标题显示当前用户显示名
    const subtitle = document.getElementById('review-subtitle');
    if (subtitle) {
        const displayName = (authState.user && (authState.user.display_name || authState.user.username)) || '';
        subtitle.textContent = displayName
            ? `${displayName} 的复习画像：回看面试记录，针对薄弱知识点持续练习`
            : '回看面试记录，针对薄弱知识点持续练习';
    }
    await Promise.all([loadToday(), loadStats(), loadHistory()]);
}

async function loadToday() {
    try {
        const res = await fetch(`${API_BASE}/api/interview/today`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderToday(data);
    } catch (e) {
        reviewEls.todayPlaceholder.textContent = '今日一题加载失败，请稍后刷新。';
        reviewEls.todayPlaceholder.style.display = 'block';
        reviewEls.todayQuestion.style.display = 'none';
    }
}

function renderToday(data) {
    reviewEls.todayPlaceholder.style.display = 'none';
    reviewEls.todayQuestion.style.display = 'block';
    reviewEls.todayText.textContent = data.question || '';
    reviewEls.todayTags.innerHTML = '';
    if (data.category) {
        reviewEls.todayTags.innerHTML += `<span class="tag-category">${escapeHtml(data.category)}</span>`;
    }
    if (data.topic) {
        reviewEls.todayTags.innerHTML += `<span class="tag-topic">${escapeHtml(data.topic)}</span>`;
    }
}

async function loadStats() {
    try {
        const res = await fetch(`${API_BASE}/api/interview/stats`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderStats(data);
    } catch (e) {
        reviewEls.weakStats.innerHTML = '<div class="empty-state">薄弱点数据加载失败</div>';
    }
}

function renderStats(data) {
    const cats = data.categories || [];
    if (cats.length === 0) {
        reviewEls.statsTotal.textContent = '暂无数据';
        reviewEls.weakStats.innerHTML = '<div class="empty-state">完成面试后，这里会聚合你的薄弱知识点。</div>';
        return;
    }
    reviewEls.statsTotal.textContent = `共 ${data.total_questions || 0} 题 · ${cats.length} 个分类`;
    reviewEls.weakStats.innerHTML = cats.map(cat => {
        const pct = Math.round((cat.avg_score / 10) * 100);
        const barColor = cat.avg_score < 5 ? '#f87171' : '#fbbf24';
        const topics = (cat.weak_topics || []).map(t =>
            `<span class="weak-topic-chip">${escapeHtml(t.topic)} · ${t.avg_score}分</span>`
        ).join('');
        return `
            <div class="weak-stat-item">
                <div class="weak-stat-header">
                    <span class="weak-stat-category">${escapeHtml(cat.category)}</span>
                    <span class="weak-stat-meta">${cat.total_questions} 题 · 均分 ${cat.avg_score}</span>
                </div>
                <div class="weak-stat-bar"><div class="weak-stat-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
                ${topics ? `<div class="weak-stat-topics">${topics}</div>` : '<div class="weak-stat-meta">暂无明显薄弱点</div>'}
            </div>
        `;
    }).join('');
}

function formatDateTime(isoStr) {
    if (!isoStr) return '';
    const d = new Date(isoStr);
    if (isNaN(d.getTime())) return '';
    const pad = n => String(n).padStart(2, '0');
    return `${d.getMonth() + 1}月${d.getDate()}日 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

async function loadHistory() {
    try {
        const res = await fetch(`${API_BASE}/api/interview/history`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderHistory(data.sessions || []);
    } catch (e) {
        reviewEls.historyList.innerHTML = '<div class="empty-state">面试记录加载失败</div>';
    }
}

function renderHistory(sessions) {
    if (sessions.length === 0) {
        reviewEls.historyList.innerHTML = '<div class="empty-state">暂无面试记录，去「AI面试」开始第一场吧。</div>';
        return;
    }
    reviewEls.historyList.innerHTML = sessions.map(s => {
        const status = s.status === 'completed' ? '已完成' : '进行中';
        const statusClass = s.status === 'completed' ? 'done' : 'incomplete';
        const score = s.total_score != null ? s.total_score : '-';
        return `
            <div class="history-item" data-session-id="${escapeHtml(s.id)}">
                <div class="history-item-main">
                    <span class="history-item-pos">${escapeHtml(s.position || '未命名')}</span>
                    <span class="history-item-meta">${formatDateTime(s.started_at)}</span>
                </div>
                <div class="history-item-right">
                    <span class="history-item-status ${statusClass}">${status}</span>
                    <span class="history-item-score">${score}</span>
                </div>
            </div>
        `;
    }).join('');
}

async function showHistoryDetail(sessionId) {
    const detailTitle = `
        <div class="history-detail-header">
            <h4>面试详情</h4>
            <button class="history-detail-close" id="history-detail-close">&times;</button>
        </div>`;
    const bindClose = () => {
        const cb = document.getElementById('history-detail-close');
        if (cb) cb.addEventListener('click', () => { reviewEls.historyDetail.style.display = 'none'; });
    };
    const open = () => { reviewEls.historyDetail.style.display = 'block'; };

    let res;
    try {
        res = await fetch(`${API_BASE}/api/interview/sessions/${encodeURIComponent(sessionId)}/detail`);
    } catch (e) {
        reviewEls.historyDetail.innerHTML = `${detailTitle}
            <div class="history-detail-error">加载失败（${e instanceof TypeError ? '网络错误' : '未知错误'}）</div>`;
        open();
        bindClose();
        return;
    }
    if (!res.ok) {
        const reason = await readErrorDetail(res);
        reviewEls.historyDetail.innerHTML = `${detailTitle}
            <div class="history-detail-error">加载失败（HTTP ${res.status}）${reason}</div>`;
        open();
        bindClose();
        return;
    }

    const data = await res.json();
    const session = data.session || {};
    const questions = data.questions || [];
    const isCompleted = session.status === 'completed';
    const answeredCount = questions.filter(q => (q.answer || '') !== '').length;

    let meta = `
        <div class="history-detail-meta">
            <span class="history-detail-pos">${escapeHtml(session.position || '未命名')}</span>
            <span class="history-item-status ${isCompleted ? 'done' : 'incomplete'}">${isCompleted ? '已完成' : '进行中'}</span>
            <span class="history-detail-meta-score">总分 ${session.total_score != null ? session.total_score : '-'}</span>
        </div>
        <div class="history-detail-time">开始 ${formatDateTime(session.started_at)}${session.completed_at ? ' · 完成 ' + formatDateTime(session.completed_at) : ''}</div>`;
    if (!isCompleted) {
        meta += `<div class="history-detail-notice">该面试未完成</div>`;
    }

    const questionsHtml = questions.length
        ? questions.map((q, i) => renderQuestionItem(q, i)).join('')
        : '<div class="history-detail-empty">暂无题目记录</div>';

    reviewEls.historyDetail.innerHTML = `${detailTitle}
        ${meta}
        <div class="history-detail-sub">逐题问答（已作答 ${answeredCount}/${questions.length}）</div>
        <div class="history-q-list">${questionsHtml}</div>
        <div id="history-report-block"></div>`;
    bindEvalCollapse(reviewEls.historyDetail);
    open();
    bindClose();

    // 仅已完成会话异步加载汇总报告；进行中会话不请求，避免任何副作用与额外调用
    if (isCompleted) {
        loadReportBlock(sessionId);
    }
}

function renderQuestionItem(q, idx) {
    const round = q.round || (idx + 1);
    const answered = (q.answer || '') !== '';
    const evalObj = q.evaluation && typeof q.evaluation === 'object' ? q.evaluation : {};
    const comment = evalObj.comment || '';
    const tags = Array.isArray(evalObj.tags) ? evalObj.tags : [];
    const difficulty = ({ easy: '偏易', medium: '适中', hard: '偏难' })[q.difficulty] || q.difficulty || '';
    const answerHtml = answered
        ? `<div class="history-q-label">我的回答</div><div class="history-q-answer">${escapeHtml(q.answer)}</div>`
        : '<div class="history-q-answer unanswered">未作答</div>';
    const commentHtml = answered && comment
        ? `<div class="history-q-label">AI 评价</div><div class="history-q-eval">${escapeHtml(comment)}</div>` : '';
    // 评分原因 / 参考答案（折叠设计；未作答或旧数据缺失字段时自动隐藏）
    const detailHtml = answered
        ? buildEvalCollapse('评分原因', evalObj.score_reason) + buildEvalCollapse('参考答案', evalObj.reference_answer)
        : '';
    const tagsHtml = tags.length
        ? `<div class="history-q-tags">${tags.map(t => `<span class="history-q-tag">${escapeHtml(t)}</span>`).join('')}</div>` : '';
    return `
        <div class="history-q-item">
            <div class="history-q-head">
                <div class="history-q-title">
                    <span class="history-q-round">第 ${round} 题</span>
                    ${difficulty ? `<span class="history-q-diff">${escapeHtml(difficulty)}</span>` : ''}
                </div>
                <span class="history-q-score">${answered ? (q.score != null ? q.score : 0) + ' 分' : '未作答'}</span>
            </div>
            <div class="history-q-question">${escapeHtml(q.question || '')}</div>
            ${answerHtml}
            ${commentHtml}
            ${detailHtml}
            ${tagsHtml}
        </div>
    `;
}

async function loadReportBlock(sessionId) {
    const block = document.getElementById('history-report-block');
    if (!block) return;
    let res;
    try {
        res = await fetch(`${API_BASE}/api/interview/report/${encodeURIComponent(sessionId)}`);
    } catch (e) {
        block.innerHTML = '';
        return;
    }
    if (!res.ok) {
        block.innerHTML = '';
        return;
    }
    const data = await res.json();
    const report = data.report || {};
    const analysis = report.knowledge_analysis || {};
    const strengths = (analysis.strengths || []).map(s => `<li>${escapeHtml(s)}</li>`).join('') || '<li>暂无数据</li>';
    const weaknesses = (analysis.weaknesses || []).map(s => `<li>${escapeHtml(s)}</li>`).join('') || '<li>暂无数据</li>';
    const suggestions = (report.improvement_suggestions || []).map(s => `<li>${escapeHtml(s)}</li>`).join('') || '<li>暂无数据</li>';
    const breakdownHtml = (report.score_breakdown || []).map(item => `
        <div class="history-q-item">
            <div class="history-q-head">
                <div class="history-q-title">
                    <span class="history-q-round">第 ${item.round} 题</span>
                </div>
                <span class="history-q-score">${item.score != null ? item.score + ' 分' : ''}</span>
            </div>
            <div class="history-q-question">${escapeHtml(item.question || '')}</div>
            <div class="history-q-tags">${(item.tags || []).map(t => `<span class="history-q-tag">${escapeHtml(t)}</span>`).join('')}</div>
            ${buildEvalCollapse('评分原因', item.score_reason)}
            ${buildEvalCollapse('参考答案', item.reference_answer)}
        </div>
    `).join('');
    block.innerHTML = `
        <div class="history-detail-title">面试报告</div>
        <div class="history-detail-score">报告总分 ${report.total_score ?? '-'} · ${escapeHtml(report.level || '未知')}</div>
        ${breakdownHtml ? `<div class="history-detail-sub">逐题评分与解析</div><div class="history-q-list">${breakdownHtml}</div>` : ''}
        <div class="history-detail-section">
            <h5>掌握较好</h5>
            <ul>${strengths}</ul>
        </div>
        <div class="history-detail-section">
            <h5>需要加强</h5>
            <ul>${weaknesses}</ul>
        </div>
        <div class="history-detail-section">
            <h5>改进建议</h5>
            <ul>${suggestions}</ul>
        </div>
    `;
    bindEvalCollapse(block);
}

async function readErrorDetail(res) {
    try {
        const d = await res.json();
        if (!d || !d.detail) return '';
        const msg = typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail);
        return `：${escapeHtml(msg)}`;
    } catch (e) {
        return '';
    }
}

if (reviewEls.historyList) {
    reviewEls.historyList.addEventListener('click', async (e) => {
        const item = e.target.closest('.history-item');
        if (!item) return;
        await showHistoryDetail(item.dataset.sessionId);
    });
}

if (reviewEls.btnRefreshHistory) {
    reviewEls.btnRefreshHistory.addEventListener('click', loadHistory);
}

if (reviewEls.btnTodayRefresh) {
    reviewEls.btnTodayRefresh.addEventListener('click', loadToday);
}

// ============ Deep Dive Module ============
const ddState = {
    projects: [], selectedProject: null, selectedTech: '',
    sessionId: null, currentQuestionId: null, nextQuestion: null,
    mode: false, isSubmitting: false,
};
const ddEls = {
    zone: document.getElementById('dd-resume-zone'),
    input: document.getElementById('dd-resume-input'),
    projectSelect: document.getElementById('dd-project-select'),
    projectOptions: document.getElementById('dd-project-options'),
    techOptions: document.getElementById('dd-tech-options'),
    btnStart: document.getElementById('btn-start-deepdive'),
    actions: document.getElementById('dd-actions'),
    btnContinue: document.getElementById('btn-dd-continue'),
    btnSwitch: document.getElementById('btn-dd-switch'),
    btnEnd: document.getElementById('btn-dd-end'),
};

function initDeepDive() {
    if (!ddEls.zone) return;
    ddEls.zone.addEventListener('click', () => ddEls.input.click());
    ddEls.zone.addEventListener('dragover', e => { e.preventDefault(); ddEls.zone.classList.add('dragover'); });
    ddEls.zone.addEventListener('dragleave', () => ddEls.zone.classList.remove('dragover'));
    ddEls.zone.addEventListener('drop', e => { e.preventDefault(); ddEls.zone.classList.remove('dragover'); handleDDUpload(e.dataTransfer.files[0]); });
    ddEls.input.addEventListener('change', e => { handleDDUpload(e.target.files[0]); e.target.value = ''; });
    ddEls.btnStart.addEventListener('click', startDeepDive);
    ddEls.btnContinue.addEventListener('click', ddContinue);
    ddEls.btnSwitch.addEventListener('click', ddSwitchTech);
    ddEls.btnEnd.addEventListener('click', endDeepDive);
}

async function handleDDUpload(file) {
    if (!file) return;
    const formData = new FormData();
    formData.append('resume_file', file);
    showToast('正在解析简历...', 'info');
    try {
        const res = await fetch('/api/deepdive/analyze', { method: 'POST', body: formData });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        ddState.projects = data.projects || [];
        renderDDProjects();
    } catch (e) {
        showToast('简历解析失败: ' + e.message, 'error');
    }
}

function renderDDProjects() {
    ddEls.projectSelect.style.display = 'block';
    if (ddState.projects.length === 0) {
        ddEls.projectOptions.innerHTML = '<span class="deepdive-hint">未识别到项目，请检查简历内容。</span>';
        return;
    }
    ddEls.projectOptions.innerHTML = ddState.projects.map((p, i) =>
        `<button class="position-btn dd-option" data-i="${i}">${escapeHtml(p.name)}</button>`
    ).join('');
    ddEls.projectOptions.querySelectorAll('.dd-option').forEach(btn => {
        btn.addEventListener('click', () => {
            ddEls.projectOptions.querySelectorAll('.dd-option').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            ddState.selectedProject = ddState.projects[btn.dataset.i];
            renderDDTechs();
        });
    });
}

function renderDDTechs() {
    const techs = (ddState.selectedProject && ddState.selectedProject.technologies) || [];
    ddEls.techOptions.innerHTML = techs.map(t =>
        `<button class="position-btn dd-option" data-t="${escapeHtml(t)}">${escapeHtml(t)}</button>`
    ).join('');
    ddEls.techOptions.querySelectorAll('.dd-option').forEach(btn => {
        btn.addEventListener('click', () => {
            ddEls.techOptions.querySelectorAll('.dd-option').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            ddState.selectedTech = btn.dataset.t;
            ddEls.btnStart.disabled = false;
        });
    });
}

async function startDeepDive() {
    if (!ddState.selectedTech) return;
    showInterviewLoading('恶劣面试官正在酝酿第一个问题...');
    try {
        const res = await fetch('/api/deepdive/start', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                project_name: ddState.selectedProject.name,
                tech_point: ddState.selectedTech,
                description: ddState.selectedProject.description || ''
            })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '启动失败');
        }
        const data = await res.json();
        ddState.sessionId = data.session_id;
        ddState.currentQuestionId = data.question.id;
        ddState.mode = true;
        showDeepDiveQuestion(data.question);
    } catch (e) {
        showToast('深挖启动失败: ' + e.message, 'error');
        showInterviewReady();
    }
}

function showDeepDiveQuestion(question) {
    ddState.currentQuestionId = question.id;
    ddState.round = question.round || 1;
    interviewEls.ready.style.display = 'none';
    interviewEls.loading.style.display = 'none';
    interviewEls.report.style.display = 'none';
    interviewEls.progress.style.display = 'flex';
    interviewEls.positionBadge.textContent = ddState.selectedTech || '项目深挖';
    interviewEls.round.textContent = `第 ${question.round || 1} 层`;
    interviewEls.difficulty.textContent = '';
    interviewEls.questionText.textContent = question.question || '';
    interviewEls.answerInput.value = '';
    interviewEls.answerInput.disabled = false;
    interviewEls.btnSubmit.disabled = true;
    interviewEls.btnSubmit.textContent = '提交回答';
    interviewEls.questionTags.style.display = 'none';
    interviewEls.coverageStats.style.display = 'none';
    interviewEls.evaluationArea.style.display = 'none';
    ddEls.actions.style.display = 'none';
    interviewEls.answerInput.focus();
}

function showDeepDiveEvaluation(judgment) {
    interviewEls.evaluationArea.style.display = 'block';
    interviewEls.evaluationScore.textContent = `${judgment.score || 0}/10`;
    interviewEls.evaluationComment.textContent = judgment.judgment || '已记录回答';
    interviewEls.evaluationTags.innerHTML = '';
    ddEls.actions.style.display = 'flex';
    interviewEls.evaluationArea.scrollIntoView({ behavior: 'smooth' });
}

async function submitDeepDiveAnswer() {
    const answer = interviewEls.answerInput.value.trim();
    if (!answer || ddState.isSubmitting) return;
    ddState.isSubmitting = true;
    interviewEls.btnSubmit.disabled = true;
    interviewEls.btnSubmit.textContent = '评价中...';
    interviewEls.answerInput.disabled = true;
    try {
        const res = await fetch('/api/deepdive/answer', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question_id: ddState.currentQuestionId, answer, action: 'continue' })
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || '提交回答失败');
        }
        const data = await res.json();
        ddState.isSubmitting = false;
        interviewEls.btnSubmit.textContent = '提交回答';
        if (data.is_complete) {
            showDeepDiveSummary(data.summary);
        } else {
            ddState.nextQuestion = data.next_question;
            showDeepDiveEvaluation(data.judgment);
        }
    } catch (e) {
        showToast('提交失败: ' + e.message, 'error');
        ddState.isSubmitting = false;
        interviewEls.btnSubmit.textContent = '提交回答';
        interviewEls.btnSubmit.disabled = false;
        interviewEls.answerInput.disabled = false;
    }
}

function ddContinue() {
    if (!ddState.nextQuestion) return;
    showDeepDiveQuestion(ddState.nextQuestion);
}

function ddSwitchTech() {
    if (ddState.sessionId) {
        fetch('/api/deepdive/end', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ session_id: ddState.sessionId }) })
            .catch(() => {});
    }
    ddState.mode = false;
    ddState.currentQuestionId = null;
    ddState.nextQuestion = null;
    ddState.sessionId = null;
    showInterviewReady();
}

async function endDeepDive() {
    if (!ddState.sessionId) { showInterviewReady(); return; }
    showInterviewLoading('正在生成深挖总结...');
    try {
        const res = await fetch('/api/deepdive/end', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: ddState.sessionId })
        });
        if (!res.ok) throw new Error('结束失败');
        const data = await res.json();
        showDeepDiveSummary(data.summary);
    } catch (e) {
        showToast('结束失败: ' + e.message, 'error');
    }
}

function showDeepDiveSummary(summary) {
    interviewEls.loading.style.display = 'none';
    interviewEls.progress.style.display = 'none';
    interviewEls.ready.style.display = 'none';
    interviewEls.report.style.display = 'flex';
    interviewEls.reportPosition.textContent = '项目深挖总结';
    interviewEls.reportScore.textContent = '-';
    interviewEls.reportLevel.textContent = '深挖完成';
    interviewEls.reportScores.innerHTML = '';
    const keyPoints = (summary.key_points || []).map(k => `<li>${escapeHtml(k)}</li>`).join('') || '<li>暂无</li>';
    const weaknesses = (summary.weaknesses || []).map(w => `<li>${escapeHtml(w)}</li>`).join('') || '<li>暂无</li>';
    interviewEls.reportStrengths.innerHTML = keyPoints;
    interviewEls.reportWeaknesses.innerHTML = weaknesses;
    interviewEls.reportSuggestions.innerHTML = `<li>${escapeHtml(summary.overall || '深挖结束。')}</li>`;
    const topicSec = document.getElementById('report-topic-section');
    const studySec = document.getElementById('report-study-section');
    if (topicSec) topicSec.style.display = 'none';
    if (studySec) studySec.style.display = 'none';
    ddState.mode = false;
}

initDeepDive();

// ============ RAG Evaluation Module ============
const evalEls = {
    btnGen: document.getElementById('btn-gen-testset'),
    btnRun: document.getElementById('btn-run-eval'),
    result: document.getElementById('eval-result'),
    progress: document.getElementById('eval-progress'),
    progressFill: document.getElementById('eval-progress-fill'),
    progressText: document.getElementById('eval-progress-text'),
};

if (evalEls.btnGen) {
    evalEls.btnGen.addEventListener('click', async () => {
        evalEls.btnGen.disabled = true;
        evalEls.btnGen.textContent = '生成中...';
        showToast('正在生成测试集...', 'info');
        try {
            const res = await fetch('/api/eval/generate-testset', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            const data = await res.json();
            showToast(`测试集生成完成：${data.total} 条`, 'success');
        } catch (e) { showToast('生成失败: ' + e.message, 'error'); }
        finally {
            evalEls.btnGen.disabled = false;
            evalEls.btnGen.textContent = '生成测试集';
        }
    });
    evalEls.btnRun.addEventListener('click', async () => {
        evalEls.btnRun.disabled = true; evalEls.btnRun.textContent = '评测中...';
        evalEls.result.style.display = 'none';
        try {
            const res = await fetch('/api/eval/run', {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
            const data = await res.json();
            await pollEvalJob(data.job_id);
        } catch (e) { showToast('启动评测失败: ' + e.message, 'error'); }
        finally { evalEls.btnRun.disabled = false; evalEls.btnRun.textContent = '运行评测'; }
    });
}

async function pollEvalJob(jobId) {
    for (let i = 0; i < 600; i++) {  // 最多轮询约 20 分钟
        const res = await fetch(`/api/eval/jobs/${jobId}`);
        const job = await res.json();
        if (job.status === 'done') {
            hideEvalProgress();
            renderEvalResult(job.result);
            return;
        }
        if (job.status === 'error') {
            hideEvalProgress();
            showToast('评测失败: ' + (job.error || '未知'), 'error');
            return;
        }
        // 更新进度条 + 阶段日志
        if (job.progress) {
            renderEvalProgress(job.progress);
        }
        await new Promise(r => setTimeout(r, 1000));
    }
    hideEvalProgress();
    showToast('评测超时，请稍后重试', 'error');
}

function renderEvalProgress(p) {
    if (!evalEls.progress) return;
    evalEls.progress.style.display = 'flex';
    const cfg = p.total_configs ? p.current_config : 0;
    const cfgDesc = p.total_configs ? `策略 ${cfg}/${p.total_configs}：${p.stage || ''}` : '';
    let text = cfgDesc;
    if (p.total_items) {
        // 跨配置累计进度
        const accumulated = (p.current_config - 1) * (p.total_items / p.total_configs) + p.current_item;
        const percent = Math.round((p.current_item / (p.total_items / p.total_configs)) * 100);
        text += `，条目 ${p.current_item}/${p.total_items / p.total_configs}`;
        evalEls.progressFill.style.width = percent + '%';
    } else {
        evalEls.progressFill.style.width = '0%';
    }
    evalEls.progressText.textContent = text.trim() || '评测中...';
}

function hideEvalProgress() {
    if (evalEls.progress) { evalEls.progress.style.display = 'none'; }
}

function renderEvalResult(data) {
    if (data.error) { showToast(data.error, 'error'); return; }
    const rows = (data.configs || []).map(c => `
        <tr>
            <td>${escapeHtml(c.name)}</td>
            <td>${c.retrieval.hit_rate}</td><td>${c.retrieval.recall}</td><td>${c.retrieval.mrr}</td>
            <td>${c.generation.faithfulness}</td><td>${c.generation.answer_relevance}</td><td>${c.generation.context_relevance}</td>
        </tr>`).join('');
    evalEls.result.innerHTML = `
        <table class="eval-table"><thead><tr>
            <th>策略</th><th>Hit Rate</th><th>Recall</th><th>MRR</th>
            <th>Faithfulness</th><th>Answer Rel.</th><th>Context Rel.</th>
        </tr></thead><tbody>${rows}</tbody></table>`;
    evalEls.result.style.display = 'block';
}