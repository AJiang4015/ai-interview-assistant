### 用户发送一句话之后，你的系统到底经历了什么？
用户提问
  → ① Embedding 编码原问题（无重写）
  → ② FAISS 检索 Top-K 相似 chunk
  → ③ 去重（set 过滤重复 chunk）
  → ④ 构造 Prompt（System + 参考资料 + 原问题）
  → ⑤ 调用 LLM 生成答案
  → ⑥ 组装响应（answer + sources + retrieved_chunks）
rag_service.py query() 方法

### 文档是怎么进入系统的？
1. scan_md_files()       扫描 data/knowledge_base/ 下所有 .md

2. split_file()          读取文件 → split_text()
   ├─ _split_by_headers()    按 #/##/### 三级标题分段
   └─ _split_into_blocks()   按段落切分 + 超长段滑动窗口

3. embedding.encode()     所有 chunk → 向量化（分批 32 条/批）

4. faiss.add_vectors()   写入 FAISS + 元数据

5. faiss.save()          持久化向量索引到磁盘

6. doc_store.save()      持久化文档元数据到 JSON


### 为什么要 metadata？
1.  来源追溯            记录每个chunk来自哪个文件，第几个chunk
2.  API 引用展示        问答响应中返回 sources 字段，告知用户答案的出处
3.  索引状态报告         GET /api/index/status 返回知识库文件列表、chunk 数量
_metadata[i] = {
    "_id": 0,              # 内部自增 ID
    "source_file": "Java基础.md",  # 来源文件
    "chunk_index": 3,      # 在原文件中的 chunk 序号
    "content": "## HashMap\n\n..."  # chunk 原文
}

### Chunk是怎么做的？为什么选取 CHUNK_SIZE=1000，CHUNK_OVERLAP=200
分块实现（两阶段策略）
def _split_by_headers(self, text):
    pattern = r'^(#{1,3})\s+(.+)$'   # 匹配 #/##/### 标题
    # 逐行扫描，遇到标题就开始新 section
    # 每个 chunk 保留所属标题名作为上下文

def _split_into_blocks(self, title, content):
    # 1. 添加标题头: "## 标题名\n\n内容"
    # 2. 如果总长度 ≤ 1000 → 整块保留
    # 3. 按 \n\n 段落分割，凑满 1000 字
    # 4. 超长段落 → 滑动窗口 (步长 = 1000-200 = 800)

从语义粒度、Token限制、检索精度考虑，1000大约覆盖一个完整知识点，LLM上下文窗口充足，1000*5不超限，太小，噪音大，太大，多个知识点，匹配不精确

### 当前项目的切分策略是什么？为什么选择这种策略？
标题划分 + 段落/滑窗切块
Markdown 原文
    ↓
① 按 #/##/### 标题分段      ← 你提到的这一步
    ↓
② 按段落 (\n\n) 凑 chunk_size
    ↓
③ 超长段落用滑动窗口切分

1. 知识库特点   技术文档，标题层级清晰，天生适合
2. 语意完整性   先按标题分段，保证每个 chunk 不会跨多个主题
3. 长度适配     再按 chunk_size 切块，适配 Embedding 模型输入限制
4. 实现简单     纯Python字符串操作，零依赖，易于调试

### Embedding 到底是什么？
用神经网络把离散文本映射到连续向量空间的过程。
维度高 = 参数多/计算贵，语义质量取决于模型训练数据和方法，而非维度本身。4B 参数量 + 1024 维是性价比选择
归一化后用**内积（Inner Product）**等价于余弦相似度

### 为什么两个语义相近的句子，它们的向量距离可能更近？
Embedding 模型通过对比学习被训练成"把语义相近的文本放在向量空间的相邻位置"

### 向量数据库到底干了什么？
存储文本的向量值，检索时获取相似度最高的文本

### FAISS 是什么？
FAISS（Facebook AI Similarity Search）是 Meta 开源的向量相似度搜索库，不是传统意义上的"数据库索引"。


### Top-K 为什么不是越大越好？为什么选取 TOP_K=5
K 太小 → 漏掉相关 chunk，答案信息不足
K 太大 → 引入噪音 chunk，干扰 LLM 生成
K = 5 为经验值。
召回率	5 个 chunk 通常足够覆盖一个知识点的完整描述
Token 预算	5 × ~1000 字 ≈ 5000 字上下文，留足空间给 system prompt 和问题
噪音控制	超过 5 个后，低质量 chunk 的边际效益递减，反而稀释信号
去重效果	滑窗分块后可能 5 个中有 2-3 个是重复的，去重后仍有 3-4 个有效 chunk


### Prompt 到底怎么构造？
划分角色，任务，目标，输出格式，

### 最后搞清楚 LLM 到底拿到了什么
LLM 拿到的是结构化的 messages 数组
messages = [
    {"role": "system", "content": "你是专业的Java面试官助手..."},  # 角色指令
    {"role": "user", "content": "参考资料：\n[chunk内容]\n\n问题：[问题]"}  # 检索结果 + 用户问题
]


### 为什么需要 Rerank？
粗检索的局限	Embedding 做的是"粗粒度相似"，可能把不相关但"沾边"的 chunk 也拉进来
信号稀释	当 5 个 chunk 中有 2 个不相关时，LLM 注意力被分散，答案质量下降
Rerank 做什么	用 Cross-Encoder（交叉编码器）对粗检结果做精排，重新判断每个 chunk 与问题的相关性

### RAG到底为什么会失败？

1. 检索失败
   ├─ 知识库中没有相关内容
   ├─ 切分策略导致知识点被截断
   └─ Embedding 模型对领域词汇理解不足

2. 检索噪音（你说的这一层）
   ├─ Top-K 中混入不相关 chunk
   └─ 相似度过低的 chunk 被拉进来

3. 生成阶段失败
   ├─ 上下文过长导致 LLM 注意力分散
   ├─ LLM 忽略参考资料自行发挥（幻觉）
   └─ Prompt 没有明确约束

4. 知识库问题
   ├─ 文档过期/过时
   └─ 知识点覆盖不全

5. 评估缺失
   └─ 没有自动化评测，失败了也不知道


### 你怎么判断你的 RAG 做得好不好？
检索层	Recall@K, MRR	正确 chunk 是否被召回、排名如何
生成层	Faithfulness, Relevance, Coherence	答案是否忠实于原文、是否相关、是否连贯
端到端	正确率、引用准确率	最终答案是否正确、引用是否准确

### 如何解决长文档？
指定合适的切分策略

### 如何解决文档更新？
全量重建	rebuild=True，清空后重新索引所有文件

### RAG 和 Fine-tuning 有什么区别？
维度	RAG	Fine-tuning
知识注入	推理时从外部检索	训练时烘焙进模型权重
更新成本	加文件→重建索引（分钟级）	重新训练（小时/天级）
可解释性	可展示引用来源	黑箱，无法追溯
适用场景	知识库问答、实时更新	风格迁移、特定领域微调
幻觉风险	较低（有原文约束）	较高（可能遗忘/扭曲）
部署成本	低（只需索引）	高（需训练资源）

### RAG 和 Agent 有什么区别？
维度	    RAG	                                Agent
核心能力	知识增强（Knowledge Augmentation）	任务自动化（Task Automation）
工作方式	单次问答：检索→生成	                多步推理：规划→执行→观察→再规划
工具使用	通常只用检索工具	                    可以调用多个工具（搜索、计算、代码执行...）
训练需求	无需训练	                            无需训练（用同样的 LLM）
典型场景	"HashMap 扩容是什么？"	            "帮我查 HashMap 扩容，写示例代码，再跑测试"

### 你的 RAG 支持哪些文件？
md, word, pdf

### 文件解析流程是如何的？
根据不同文件选择不同的文件解析器
    ↓
DocumentParser.parse_file(file_path)
    ├─ .md → _parse_markdown()   # 直接读取
    ├─ .pdf → _parse_pdf()       # pypdf 逐页提取
    └─ .docx → _parse_docx()    # python-docx 段落+表格
    ↓
对文本进行标题切分
    ↓
按段落/滑动窗口划分
    ↓
批量向量化

### PDF解析如何实现？
使用pypdf

### 扫描 PDF 怎么办？


### 不同文件解析后怎么进入同一套 RAG？
保证不同文件经解析后提取内容格式一致。

### 不同文件解析到向量库如何实现？ 遇到了什么问题？
DocumentParser.parse_file(file_path)
    ↓
返回统一格式的纯文本
    ↓
MarkdownSplitter.split_file(file_path)
    ↓
按标题分段 → 按大小切块
    ↓
返回带元数据的 chunks（每个 chunk 包含 source_file）
    ↓
EmbeddingService.encode(contents)
    ↓
FaissStore.add_vectors(vectors, chunks)

PDF 中文乱码	生成 PDF 时注册系统字体（SimHei）
Word 临时文件	过滤 ~$ 开头的文件
加密 PDF 解析失败	捕获异常，记录日志，跳过处理
FAISS 索引重复	rebuild=True 时先 reset() 清空


---

### 会话管理：切换会话后 AI 回复丢失

**问题描述**
用户在会话 A 发送问题后，立即切换到会话 B。AI 回复完成后，前端未将回复写入会话 A，导致刷新后对话丢失，侧边栏也没有新增记录。

**根因分析**
1. 全局 `state.messages` 被所有会话共享，切换时被覆盖
2. `state.sessionId` 在 `sendQuestion` 执行中途被切换，导致 `done` 事件无法定位到正确的会话
3. 切换会话时调用 `abort()` 中断了后台 SSE 请求

**解决方案**
- 废弃全局 `state.messages`，改用 `state.sessionMessages = { [sessionId]: Message[] }` 按会话隔离存储
- 废弃 `state.activeRequestSessionId`，改用 `state.pendingStreams = { [sessionId]: {...} }` 跟踪进行中的流
- `sendQuestion` 开头捕获 `const requestSessionId = state.sessionId || '__pending__'`，后续所有 SSE 事件都以此 ID 为准
- `switchSession` 不再调用 `abort()`，让 SSE 请求自然完成，完成后 toast 通知用户
- `done` 事件无条件写入 `state.sessionMessages[finalSessionId]`，不关心当前激活的是哪个会话
- 首次提问（无 sessionId）使用 `'__pending__'` 临时 key，收到后端 `session` 事件后迁移到真实 ID

**涉及文件**
`frontend/js/app.js` — state 结构、sendQuestion、switchSession、renderMessages


---

### 会话管理：删除当前会话后自动新建

**问题描述**
删除当前会话后，系统自动创建了一个新会话。用户希望删除后由自己决定是否新建。

**根因分析**
`deleteSession` 函数在删除当前会话的分支中无条件调用了 `await createSession()`，违背了用户的预期行为。

**解决方案**
- 移除 `deleteSession` 中的 `await createSession()` 调用
- 删除后显示引导文案：「会话已删除，点击右上角「+」创建新会话。」
- 将 `state.sessionId` 置为 `null`，`localStorage` 清除对应 key
- 调用 `updateSessionIndicator()` 重置指示器状态

**涉及文件**
`frontend/js/app.js` — deleteSession 函数


---

### 会话管理：删除有进行中流的会话导致数据丢失

**问题描述**
AI 回复过程中删除当前会话，前端立即清除 `sessionMessages` 和 `pendingStreams`，导致 SSE 流完成后 `done` 事件无法找到消息数组来写入回复。

**根因分析**
`deleteSession` 在删除会话时无差别地执行 `delete state.sessionMessages[sessionId]` 和 `delete state.pendingStreams[sessionId]`，如果此时有正在进行的 SSE 流，`done` 事件的 `state.sessionMessages[finalSessionId].push(...)` 会因为数组不存在而静默失败。

**解决方案**
- 在删除前检查 `const hasPendingStream = !!state.pendingStreams[sessionId]`
- 有进行中流时**不删除** `sessionMessages` 和 `pendingStreams`，保留数据结构让 SSE 流自然完成
- 删除后若 `hasPendingStream` 为真，显示「会话已删除，正在接收最后的 AI 回复…」提示
- SSE 流完成后，`done` 事件会将 AI 回复写入保留的数组，用户刷新或切回时可看到完整对话

**涉及文件**
`frontend/js/app.js` — deleteSession 函数的删除逻辑


---

### 会话管理：流式响应切换会话后中断

**问题描述**
AI 正在流式响应时，切换会话再切回来，流式输出中断，后续 token 不再更新到 UI。

**根因分析**
1. `sendQuestion` 在 `fetch` 之前就创建了 `contentDiv` 并引用到局部变量
2. 切换会话时 `els.chatMessages.innerHTML = ''` 清空 DOM，原 `contentDiv` 被销毁
3. 切回原会话时 `renderMessages` 基于 `sessionMessages` 渲染历史消息，但不含正在流式的 AI 回复
4. 后续 `token` 事件中 `if (contentDiv)` 判断为 false（局部变量已失效），UI 不再更新
5. `updateSendButtonState` 中的自动清理逻辑会遍历 `loadingSessions` 删除无 `pendingStreams` 的项，可能在流式处理过程中误删状态
6. `token` 事件中每个 token 都直接操作 `textContent`，频繁重绘影响性能

**解决方案**

1. **将 DOM 操作延迟到流建立之后**
   - `sendQuestion` 中先执行 `fetch`，成功后再创建用户消息和 AI 占位消息
   - 避免在 HTTP 流建立前触发 DOM 重排，消除浏览器 HTTP 栈与渲染管线之间的潜在干扰

2. **移除 `updateSendButtonState` 中的自动清理逻辑**
   - 删除遍历 `loadingSessions` 清理无 `pendingStreams` 项的代码
   - 改为纯粹的状态查询：`hasText` + `loadingSessions.has(sessionId)`
   - 状态清理职责明确归属 `done`/`error`/`finally` 三个出口，避免在按钮状态查询时产生副作用

3. **使用节流批量更新 token DOM**
   - `token` 事件中引入 `lastDomUpdate` 时间戳，DOM 更新间隔不低于 50ms
   - `accumulatedContent` 始终更新（保证数据完整），但 `textContent` 赋值和滚动操作被节流
   - 减少高频 `textContent` 赋值导致的重绘开销

4. **为 `reader.read()` 添加超时保护**
   - 使用 `Promise.race` 将 `reader.read()` 与 120 秒超时 Promise 竞争
   - 超时后抛出 `stream_read_timeout` 错误，进入 catch 块清理状态
   - 防止因网络异常或后端卡死导致的永久挂起

**为什么这么选择**

| 方案 | 选择原因 |
|------|----------|
| 延迟 DOM 到 fetch 后 | 根因定位发现 DOM 操作在流建立前执行，浏览器渲染管线与 HTTP 流读取之间存在时序冲突，延迟后问题消失 |
| 移除自动清理而非修复 | 清理逻辑本身是防御性代码，但放在 `updateSendButtonState`（一个高频调用的纯查询函数）中违反单一职责，正确做法是在状态变更点清理 |
| 节流而非 requestAnimationFrame | `requestAnimationFrame` 与屏幕刷新率绑定（16ms），而 SSE token 间隔不固定（30-60ms），50ms 节流更贴合实际到达频率，且避免 rAF 在标签页不可见时暂停的问题 |
| 120 秒超时 | LLM 单次响应通常 10-30 秒，120 秒留足余量，不会误杀正常慢响应，同时防止无限挂起 |

**涉及文件**
`frontend/js/app.js` — sendQuestion 函数（DOM 延迟、节流、超时保护）、updateSendButtonState 函数（移除自动清理）
`app/services/rag_service.py` — stream_query 方法（清理调试日志，恢复原始逻辑）
