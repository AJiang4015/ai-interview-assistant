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