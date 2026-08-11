const API_BASE = '';
const STORAGE_KEY = 'rag_current_session_id';

const state = {
    messages: [],
    isLoading: false,
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
    btnClear: document.getElementById('btn-clear'),
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
    updateSessionIndicator();

    try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`);
        if (res.ok) {
            const data = await res.json();
            state.messages = data.history || [];
            els.chatMessages.innerHTML = '';

            if (state.messages.length === 0) {
                appendSystemMessage('已切换到新会话，开始提问吧！');
            } else {
                state.messages.forEach(msg => {
                    appendMessage(msg.role, msg.content, msg.sources);
                });
            }
        }
    } catch (e) {
        console.error('Failed to load session history:', e);
    }
}

async function createSession() {
    try {
        const res = await fetch(`${API_BASE}/api/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await res.json();
        state.sessionId = data.session_id;
        localStorage.setItem(STORAGE_KEY, data.session_id);

        state.messages = [];
        els.chatMessages.innerHTML = '';
        appendSystemMessage('已创建新会话，开始提问吧！');

        await loadSessions();
        renderSessions();
        updateSessionIndicator();

        showToast('新会话已创建', 'success');
    } catch (e) {
        console.error('Failed to create session:', e);
        showToast('创建会话失败', 'error');
    }
}

async function deleteSession(sessionId) {
    if (!confirm('确定删除该会话吗？')) return;

    try {
        const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            state.sessions = state.sessions.filter(s => s.session_id !== sessionId);

            if (state.sessionId === sessionId) {
                state.sessionId = null;
                localStorage.removeItem(STORAGE_KEY);
                state.messages = [];
                els.chatMessages.innerHTML = '';
                appendSystemMessage('会话已删除，已创建新会话。');
                await createSession();
            } else {
                renderSessions();
            }
            showToast('会话已删除', 'success');
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
        const count = state.messages.filter(m => m.role !== 'system').length;
        els.sessionTurnCount.textContent = count;
    } else {
        els.sessionIndicator.style.display = 'none';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============ Chat ============
els.questionInput.addEventListener('input', () => {
    els.btnSend.disabled = els.questionInput.value.trim().length === 0 || state.isLoading;
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
    if (!question || state.isLoading) return;

    state.isLoading = true;
    els.btnSend.disabled = true;

    appendMessage('user', question);
    els.questionInput.value = '';
    autoResizeInput();

    const assistantMsg = createStreamingMessage();
    const contentDiv = assistantMsg.querySelector('.msg-content');
    let accumulatedContent = '';
    let sourcesData = null;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 180000);

        const body = { question };
        if (state.sessionId) {
            body.session_id = state.sessionId;
        }

        const res = await fetch(`${API_BASE}/api/query/stream`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (!res.ok) {
            let errorMsg = '请求失败';
            try {
                const errText = await res.text();
                const errData = JSON.parse(errText);
                errorMsg = errData.detail || errData.error || `HTTP ${res.status}`;
            } catch {}
            contentDiv.textContent = `❌ ${errorMsg}`;
            removeStreamingCursor(contentDiv);
            showToast(errorMsg, 'error');
            state.isLoading = false;
            els.btnSend.disabled = els.questionInput.value.trim().length === 0;
            return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

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
                            if (data.session_id && data.session_id !== state.sessionId) {
                                state.sessionId = data.session_id;
                                localStorage.setItem(STORAGE_KEY, data.session_id);
                                loadSessions();
                            }
                            break;

                        case 'retrieval':
                            sourcesData = data.sources;
                            break;

                        case 'token':
                            accumulatedContent += data.content;
                            contentDiv.textContent = accumulatedContent;
                            els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
                            break;

                        case 'done':
                            accumulatedContent = data.answer || accumulatedContent;
                            contentDiv.textContent = accumulatedContent;
                            removeStreamingCursor(contentDiv);

                            if (data.session_id && data.session_id !== state.sessionId) {
                                state.sessionId = data.session_id;
                                localStorage.setItem(STORAGE_KEY, data.session_id);
                                loadSessions();
                            }

                            if (data.sources && data.sources.length > 0) {
                                appendSourcesToMessage(contentDiv, data.sources);
                            }

                            state.messages.push({
                                role: 'assistant',
                                content: accumulatedContent,
                                sources: data.sources || sourcesData
                            });
                            updateSessionIndicator();
                            break;

                        case 'error':
                            contentDiv.textContent = `❌ ${data.message || '未知错误'}`;
                            removeStreamingCursor(contentDiv);
                            showToast(data.message || '请求失败', 'error');
                            break;
                    }
                } catch (e) {
                    console.error('Failed to parse SSE event:', e);
                }
            }
        }
    } catch (e) {
        contentDiv.textContent = '❌ 网络错误，请检查后端服务是否启动。';
        removeStreamingCursor(contentDiv);
        showToast('网络错误', 'error');
    } finally {
        state.isLoading = false;
        els.btnSend.disabled = els.questionInput.value.trim().length === 0;
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

function appendMessage(role, content, sources = null) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${role}`;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.textContent = role === 'user' ? '我' : 'AI';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.textContent = content;

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

    state.messages.push({ role, content, sources });
    return msgDiv;
}

function appendSystemMessage(text) {
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message system-msg';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.innerHTML = `<p>${text}</p>`;

    msgDiv.appendChild(contentDiv);
    els.chatMessages.appendChild(msgDiv);
    els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

els.btnClear.addEventListener('click', () => {
    createSession();
});

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

// ============ Init ============
checkHealth();
loadIndexStatus();
loadSessions();
setInterval(checkHealth, 30000);