# P005 — Markdown 渲染未生效（textContent 而非 innerHTML）

## Status

- ID：P005
- Severity：Medium
- Status：Resolved
- First identified：前端交互迭代期间（commit `d42b7bf` 前后）
- Related Decision：DR-009（前端安全渲染链：escapeHtml + DOMPurify，CDN 失败回退纯文本）
- Related Tests：Door 10（前端渲染安全检查点，未自动化）

---

## 1. Problem

页面已加载 marked.js 与 highlight.js，但 AI 回答不渲染 Markdown / 代码不高亮，直接显示未格式化文本。

## 2. Impact

回答排版混乱、代码块无高亮、可读性差——直接影响问答与面试场景的内容消费体验。

## 3. Evidence

- 记忆（Lessons Learned）：「marked.js 和 highlight.js 已加载但实际使用 textContent 而非 innerHTML 导致 Markdown 未生效」。
- 修复提交：`d42b7bf`（"实现文件管理UI、Markdown渲染、FTS5全文搜索"）。

## 4. Root Cause

库已加载但在渲染函数中用 `textContent`（安全但纯文本）写入，未走 `innerHTML` + Markdown parse + 语法高亮。为规避 XSS 优先用了纯文本写入，绕过了 Markdown 渲染路径；migration 时只挂了 CDN 未接渲染逻辑。

## 5. Decision / Solution

- **决策（DR-009）**：`marked.parse → DOMPurify → innerHTML + highlight` 的安全渲染链；CDN 加载失败回退 `escapeHtml` 纯文本。
- 备选方案对比：
  - ✅ 方案 A（采用）"marked.parse → DOMPurify → innerHTML + 高亮"：Markdown 与代码高亮正常，XSS 可控；DOMPurify 白名单裁剪非标准标签/属性为可接受代价。
  - ❌ 方案 B（否定）"纯 textContent"（问题出现前的实现）：零 XSS 风险但 Markdown / 高亮全部失效，以牺牲核心可读性换安全。
  - ❌ 方案 C（否定）"白名单富渲染插件"：扩大攻击面、增加维护成本，当前 LLM 输出以 md/代码为主，ROI 不足。

## 6. Implementation

commit `d42b7bf`（`frontend/js/app.js` 渲染函数）：marked.parse 转 HTML → DOMPurify 白名单过滤（保留 class 给 highlight.js）→ innerHTML 写入 → 调 highlight 使代码高亮；CDN 失败回退 escapeHtml。

## 7. Regression / Verification

- 回答含标题 / 列表 / 代码块时正确渲染且高亮；构造恶意 `<script>` 时被过滤不执行。
- 建议补（Door 10）：LLM 输出含 `<script>` 的渲染断言（DOM 无 script 节点）、渲染走 marked→DOMPurify 的调用断言、CDN 失败回退断言。

## 8. Current Status

Resolved。DR-009 作为前端安全渲染链持续维护于 `AGENTS.md` 安全规则与 `API_LAYER.md` 契约。

## 9. Lessons

- "安全优先"的实现（textContent）若直接跳过渲染管线，会同时丢掉产品能力——安全与可读性不是二选一，DOMPurify 白名单可以同时满足两者。
- 任何注入前必须 HTML 转义或 DOMPurify 过滤（D10），是 XSS 的红线，也是渲染正确性的前置条件。

## 10. Historical Record

- 失败路径（已证伪）：直接裸用 `innerHTML` 写 LLM 输出（XSS 风险，不可用，需配合 DOMPurify）。
- Do Not Reopen Without Evidence：若再次出现 Markdown 不渲染，先确认渲染函数是否无意回退到 `textContent` 或 CDN 是否失效；不要未经确认又引入裸 `innerHTML`。
