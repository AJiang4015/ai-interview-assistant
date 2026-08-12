const API_BASE = '';
const STORAGE_KEY = 'rag_current_session_id';

const state = {
    sessionMessages: {},
    pendingStreams: {},
    loadingSessions: new Set(),
    currentView: 'chat',
    sessionId: null,
    sessions: []
};

const els = {
    navItems: document.querySelectorAll('.nav-item'),
    views: {
        chat: document.getElementById('view-chat'),
        index: document.getElementById('view-index'),
        docs: document.getElementById('view-docs')
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
    if (view === 'index') {
        loadIndexStatus();
    }
    if (view === 'docs') {
        loadFileList();
    }
}

// ============ Status ============
async function checkHealth() {
    try {
        const res = await fetch(`${API_BASE}/api/health`);
        const data = await res.json();
        updateStatus('faiss', data.faiss_index === 'empty' ? 'offline' : 'online', data.faiss_index);
        updateStatus('embedding', data.embedding_service === 'available' ? 'online' : 'offline', data.embedding_service);
        updateStatus('llm', data.llm_service === 'available' ? 'online' : 'offline', data.llm_service);
    } catch (e) {
        updateStatus('faiss', 'offline', 'unreachable');
        updateStatus('embedding', 'offline', 'unreachable');
        updateStatus('llm', 'offline', 'unreachable');
    }
}

function updateStatus(key, status, value) {
    const dot = els['dot' + key.charAt(0).toUpperCase() + key.slice(1)];
    const val = els['val' + key.charAt(0).toUpperCase() + key.slice(1)];
    dot.className = 'status-dot' + (status === 'online' ? ' online' : status === 'warning' ? ' warning' : ' offline');
    val.textContent = value || status;
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

    els.sessionsList.querySelectorAll('.session-item').forEach(item => {
        const sessionId = item.dataset.sessionId;
        item.addEventListener('click', (e) => {
            if (e.target.classList.contains('session-item-delete')) return;
            switchSession(sessionId);
        });
    });

    els.sessionsList.querySelectorAll('.session-item-delete').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            deleteSession(btn.dataset.deleteId);
        });
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

        const contentDiv = document.createElement('div');
        contentDiv.className = 'msg-content streaming';
        contentDiv.innerHTML = renderMarkdownNoHighlight(pending.accumulatedContent) || '<span class="streaming-cursor"></span>';

        msgDiv.appendChild(avatar);
        msgDiv.appendChild(contentDiv);
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

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    // AI 消息用 Markdown 渲染，用户消息纯文本
    if (role === 'assistant') {
        contentDiv.innerHTML = renderMarkdown(content);
    } else {
        contentDiv.textContent = content;
    }

    if (sources && sources.length > 0) {
        const sourcesDiv = document.createElement('div');
        sourcesDiv.className = 'sources-list';
        const title = document.createElement('div');
        title.className = 'sources-title';
        title.textContent = `参考来源 (${sources.length})`;
        sourcesDiv.appendChild(title);
        sources.forEach(s => {
            const item = document.createElement('div');
            item.className = 'source-item';
            const file = document.createElement('span');
            file.className = 'source-file';
            file.textContent = s.file;
            const score = document.createElement('span');
            score.className = 'source-score';
            score.textContent = (s.score || 0).toFixed(3);
            item.appendChild(file);
            item.appendChild(score);
            sourcesDiv.appendChild(item);
        });
        contentDiv.appendChild(sourcesDiv);
    }

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    els.chatMessages.appendChild(msgDiv);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
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
    wrapper.querySelectorAll('pre code').forEach(block => {
        hljs.highlightElement(block);
    });
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

els.btnSend.addEventListener('click', sendQuestion);
els.btnNewSession?.addEventListener('click', createSession);

function autoResizeInput() {
    const el = els.questionInput;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

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
        accumulatedContent: '',
        sourcesData: null,
        contentDiv: null,
        lastRenderedLength: 0,
        pendingRender: false,
        rafId: null
    };
    els.questionInput.value = '';
    autoResizeInput();

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
                                if (sourcesData && sourcesData.length > 0) {
                                    appendSourcesToMessage(doneDiv, sourcesData);
                                }
                                removeStreamingCursor(doneDiv);
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

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content streaming';
    contentDiv.innerHTML = '<span class="streaming-cursor"></span>';

    msgDiv.appendChild(avatar);
    msgDiv.appendChild(contentDiv);
    els.chatMessages.appendChild(msgDiv);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;

    return msgDiv;
}

function removeStreamingCursor(contentDiv) {
    const cursor = contentDiv.querySelector('.streaming-cursor');
    if (cursor) cursor.remove();
    contentDiv.classList.remove('streaming');
}

function appendSourcesToMessage(contentDiv, sources) {
    if (!sources || sources.length === 0) return;

    const sourcesDiv = document.createElement('div');
    sourcesDiv.className = 'sources-list';
    const title = document.createElement('div');
    title.className = 'sources-title';
    title.textContent = `参考来源 (${sources.length})`;
    sourcesDiv.appendChild(title);
    sources.forEach(s => {
        const item = document.createElement('div');
        item.className = 'source-item';
        const file = document.createElement('span');
        file.className = 'source-file';
        file.textContent = s.file;
        const score = document.createElement('span');
        score.className = 'source-score';
        score.textContent = (s.score || 0).toFixed(3);
        item.appendChild(file);
        item.appendChild(score);
        sourcesDiv.appendChild(item);
    });
    contentDiv.appendChild(sourcesDiv);
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

    els.sessionsList.querySelectorAll('.search-result-item').forEach(item => {
        item.addEventListener('click', () => {
            const sessionId = item.dataset.sessionId;
            searchInput.value = '';
            switchSession(sessionId);
        });
    });
}

// ============ Auth Module ============

const AUTH_TOKEN_KEY = 'rag_auth_token';
const AUTH_USER_KEY = 'rag_auth_user';

let authState = {
    user: null,
    token: null,
    isRegisterMode: false
};

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
    document.getElementById('login-modal').style.display = 'flex';
    setTimeout(() => document.getElementById('login-username').focus(), 100);
}

function closeLoginModal() {
    document.getElementById('login-modal').style.display = 'none';
}

function switchAuthMode() {
    authState.isRegisterMode = !authState.isRegisterMode;
    updateAuthModalUI();
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
            const err = await res.json();
            throw new Error(err.detail || '请求失败');
        }

        const data = await res.json();
        authState.token = data.token;
        authState.user = data.user;

        localStorage.setItem(AUTH_TOKEN_KEY, data.token);
        localStorage.setItem(AUTH_USER_KEY, JSON.stringify(data.user));

        showUserPanel();
        closeLoginModal();
        showToast(authState.isRegisterMode ? '注册成功' : '登录成功', 'success');

        document.getElementById('login-username').value = '';
        document.getElementById('login-password').value = '';
        document.getElementById('register-display-name').value = '';

    } catch (e) {
        showToast(e.message, 'error');
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

// ============ Init ============
checkHealth();
loadIndexStatus();
loadSessions();
initAuth();
setInterval(checkHealth, 30000);