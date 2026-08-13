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


---

### 对话搜索：FTS5 中文搜索失败

**问题描述**
使用 FTS5 全文搜索索引用户对话消息，英文关键词（Redis、MySQL）能正常搜索，但中文关键词（持久化、聚簇）返回 0 结果。

目录结构：
```
data/
  search.db          # SQLite 数据库
  knowledge_base/    # 文档知识库（FAISS 索引）
    Java基础.md
    MySQL.md
    ...
```

**根因分析**
1. FTS5 默认使用 `unicode61` 分词器，对中文按**每个字符**切分为独立 token
2. 例如"持久化"被切分为 `持` + `久` + `化` 三个独立 token，而不是一个整体 token
3. 搜索 `持久化` 时，FTS5 将查询词也切分为三个 token，但 `unicode61` 不会记录相邻 token 的位置关系，导致三个 token 各自独立匹配，无法匹配到任意一个完整内容
4. 因此 `持久化` 找不到，"持久化"找不到包含"持久化机制"的文本
5. 同理，`聚簇` 找不到包含"聚簇索引"的文本
6. 英文不受影响，因为 `unicode61` 对英文按空格/标点切词，`Redis` 和 `MySQL` 都是完整 token

**解决方案**

1. **改用 `trigram` 分词器**
   - 将 `tokenize='unicode61'` 改为 `tokenize='trigram'`
   - `trigram` 按 3 字节切分，对中文能形成有效的子串匹配
   - 例如"持久化"的 trigram 包含: `持 久 化`、`持久`、`久化` 等子串
   - 搜索 `持久化` 时，FTS5 会匹配包含这些 trigram 的文本，正确召回包含"持久化机制"的记录
   - 英文同样适用，`trigram` 对英文单词也能形成有效的子串匹配

2. **短词降级到 LIKE**
   - `trigram` 分词器的固有限制：少于 3 字符的词无法形成完整 trigram
   - 例如 `索引`（2 字符）、`聚簇`（2 字符）在 trigram 中返回 0 结果
   - 解决方案：在 `search()` 方法中判断 `len(keyword.strip()) < 3`，直接降级到 `LIKE '%keyword%'` 搜索
   - 3 字符及以上（持久化、ThreadPool）走 FTS5 trigram 搜索，2 字符及以下（索引、聚簇、AI）走 LIKE 降级

3. **修复 SQL 注释问题**
   - `sqlite3.executescript()` 不支持 `#` 注释，会导致 `unrecognized token: "#"` 错误
   - 移除 `executescript` 中的 Python 风格注释，改为在 Python 代码中注释

**为什么这么选择**

| 方案 | 选择原因 |
|------|----------|
| trigram 而非 unicode61 | `unicode61` 对 CJK 按字切分且无相邻位置信息，导致多字符中文词搜索失效。`trigram` 按 3 字节滑动窗口切分，天然支持中文等多字节字符的模糊匹配 |
| trigram 而非 ICU | ICU 分词器需要编译 SQLite 时启用 `-DSQLITE_ENABLE_ICU`，Windows 预编译的 Python sqlite3 模块通常不包含。`trigram` 是 SQLite 3.34+（2020 年）内置支持，无需额外依赖 |
| 短词降级 LIKE 而非 trigram 参数调优 | trigram 要求至少 3 个字符才能形成有效 token，这是算法层面的限制，无法通过参数绕过。LIKE 降级简单可靠，对 2 字符短词来说性能差异可忽略 |
| 短词阈值 3 而非 4 | 实测验证：3 字符中文词（持久化、AOF、IoC）在 trigram 下能正确召回，2 字符（索引、聚簇）不能，阈值精确设为 3 |

**涉及文件**
`app/storage/search_store.py` — `_init_db`（FTS5 表定义）、`search`（分词器选择 + 短词降级）


---

### 对话搜索：FTS5 索引同步与过期清理

**问题描述**
FTS5 搜索索引需要与消息表保持同步，且需要清理过期的会话数据。

**根因分析**
1. FTS5 使用 `content='messages'` 外部内容表模式，数据自动从 messages 表同步，但需要触发器保证 INSERT/DELETE/UPDATE 同步
2. `clear_all` 只清空 messages 和 sessions 表，未重建 FTS5 内部索引，导致 FTS5 内容与实际数据不一致（`database disk image is malformed`）
3. 缺少清理过期会话的机制，长期运行下 search.db 会无限增长

**解决方案**

1. **FTS5 触发器自动同步**
   - 创建 3 个触发器：
     - `messages_fts_ai`（AFTER INSERT）：写入新消息到 FTS5
     - `messages_fts_ad`（AFTER DELETE）：从 FTS5 删除消息
     - `messages_fts_au`（AFTER UPDATE）：先删后插，保持最新
   - 使 FTS5 内容表与 messages 表完全同步，无需手动维护

2. **`clear_all` 重建 FTS5 索引**
   - 清空 messages 和 sessions 后，执行 `INSERT INTO messages_fts(messages_fts) VALUES('rebuild')`
   - 强制 FTS5 重新从 messages 表读取内容，避免索引不一致

3. **`cleanup_expired` 方法**
   - 接收 `active_session_ids: set[str]` 参数（来自 Redis 中的活跃会话列表）
   - 删除 `sessions` 和 `messages` 表中不在活跃集合中的记录
   - 有删除操作时同样执行 FTS5 rebuild
   - 可在会话过期（Redis TTL）或用户主动清理时调用

4. **启动时数据迁移**
   - 每次 `_init_db` 末尾检查 FTS5 表是否为空
   - 如果为空（新建数据库），从 messages 表批量导入现有数据到 FTS5
   - 保证升级后旧数据也能被搜索

**涉及文件**
`app/storage/search_store.py` — `_init_db`（触发器 + 迁移）、`clear_all`（FTS5 rebuild）、`cleanup_expired`（新增方法）


---

### 响应缓存 Key 设计：命中率极低

**问题描述**
RAG 响应缓存的 `make_key` 方法使用 `md5(question | session_id | msg_count)` 作为缓存键。这意味着：

- 同一个问题，不同会话 → **永远不命中**
- 同一个问题，同一会话，不同轮次 → **永远不命中**（msg_count 变了）
- 同一个问题，同一会话，同一轮次 → **命中**
- 大小写/标点差异 → **永远不命中**

在实际场景中，唯一可能命中的场景是：用户在同一个会话中、同一轮对话位置、一字不差地问同一个问题，且在此之后没有其他消息。这几乎不会发生，导致缓存命中率趋近于 0。

```python
# cache_service.py — 当前实现
def make_key(self, question: str, session_id: str, msg_count: int) -> str:
    raw = f"{question}|{session_id}|{msg_count}"
    h = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"{self._prefix}{h}"
```

**根因分析**

1. **过度保守的 key 设计**
   - 加入 `session_id` 为了防止跨会话缓存污染（不同用户问"Redis 持久化"期望不同上下文）
   - 加入 `msg_count` 为了防止多轮对话中上下文变化导致答案不合适
   - 但这两个字段让 key 几乎变成唯一值，失去了缓存的意义

2. **缓存粒度选错了层级**
   - 当前缓存的是**LLM 生成后的最终答案**（response cache）
   - 这个层级的答案高度依赖上下文（会话历史、知识库版本），天然难以复用
   - 更合理的做法是缓存**检索结果**（retrieval cache），因为检索结果只依赖问题本身，与会话上下文无关

3. **未做问题归一化**
   - 原始问题文本直接参与 key 计算，没有去除大小写、标点、停用词等
   - "Redis 持久化" 和 "redis 持久化 " 被看作两个不同的问题

4. **轮次计数与上下文绑定**
   - `msg_count` 不是衡量"上下文是否变化"的好指标
   - 用户可能问了一个无关问题再回来追问，msg_count 变了但上下文没变
   - 也可能 msg_count 没变但上下文变了（比如知识库更新了）

**解决方案**

方案一：缓存检索结果而非最终答案（推荐）

```python
class RetrievalCache:
    """缓存检索结果，key 只依赖问题本身。"""

    def make_key(self, question: str) -> str:
        # 归一化：去空格、转小写、去标点
        normalized = re.sub(r'[^\w\s]', '', question).lower().strip()
        return f"cache:retrieval:{hashlib.md5(normalized.encode()).hexdigest()}"

    async def get(self, key: str) -> list[RetrievalResult] | None:
        data = await self._store.client.get(key)
        return pickle.loads(data) if data else None

    async def set(self, key: str, chunks: list[RetrievalResult], ttl: int = 3600):
        await self._store.client.setex(key, ttl, pickle.dumps(chunks))
```

**为什么选择这个方案：**
- 检索结果只依赖问题语义，不依赖会话上下文，key 可以大幅简化
- 同一个问题在不同会话、不同轮次会命中同一个检索结果
- 检索是 RAG 中最耗时的环节之一（Embedding + FAISS + BM25 + RRF），命中缓存能显著提速
- LLM 生成仍然实时执行，保证答案能结合当前会话历史
- 知识库更新时只需使检索缓存失效（TTL 到期或手动清除）

方案二：简化 response cache key（次选）

```python
def make_key(self, question: str) -> str:
    # 归一化 + 去 session_id + 去 msg_count
    normalized = re.sub(r'[^\w\s]', '', question).lower().strip()
    return f"cache:response:{hashlib.md5(normalized.encode()).hexdigest()}"
```

**为什么这是次选：**
- 实现简单，改动最小
- 但多轮对话中同一问题在不同上下文可能会得到不同答案，缓存可能返回过时回答
- 适用场景：面试助手这种「一问一答、不依赖上下文」的简单场景

方案三：检索缓存 + 响应缓存双层

```
第一层：检索缓存，key = md5(归一化问题)，TTL = 3600s
第二层：响应缓存，key = md5(归一化问题 | 前 N 轮摘要)，TTL = 600s
```

**为什么是可选方案：**
- 检索缓存覆盖大部分场景，响应缓存作为补充
- 响应缓存的 key 加入"前 N 轮对话摘要"而非 msg_count，更准确反映上下文变化
- 实现复杂，需要维护对话摘要，收益有限

方案四：语义近似缓存

```python
def find_similar(self, question: str, threshold: float = 0.95) -> str | None:
    """查找语义相似的已缓存问题。"""
    q_vec = self._embedding.encode([question])[0]  # 复用 EmbeddingService
    for cached_q, answer in self._cache_store.items():
        c_vec = self._embedding.encode([cached_q])[0]
        sim = np.dot(q_vec, c_vec) / (np.linalg.norm(q_vec) * np.linalg.norm(c_vec))
        if sim >= threshold:
            return answer
    return None
```

**为什么暂不推荐：**
- 每次查询都需要遍历所有缓存条目并计算相似度，O(n) 复杂度
- Embedding 编码本身已有开销，再查一遍缓存得不偿失
- 阈值难调：0.95 太高等于精确匹配，0.90 太低可能返回错误答案
- 需要专门的向量存储来索引缓存问题，增加了系统复杂度

**面试题**

1. **"设计一个 RAG 系统的缓存策略"**
   - 关键点：区分 retrieval cache 和 response cache 两个层级
   - retrieval cache：key 只依赖问题，命中率高，存储检索结果 chunks
   - response cache：key 依赖问题 + 上下文，命中率低，存储 LLM 最终答案
   - 候选回答：优先实现 retrieval cache，response cache 作为补充

2. **"缓存 key 应该包含哪些字段？为什么？"**
   - 核心字段：归一化后的问题文本（去空格、转小写、去标点）
   - 可选字段：知识库版本号（缓存失效时使用）
   - 不应包含的字段：session_id（跨会话不共享）、msg_count（轮次变化不改变问题语义）
   - 例外：多轮对话中如果问题依赖上下文（如"那它呢？"），需要包含上下文摘要

3. **"如何平衡缓存命中率和答案准确性？"**
   - 命中率 vs 准确性本质上是一对矛盾
   - 方案：分层缓存——检索缓存用高命中率（长 TTL），响应缓存用低命中率（短 TTL）
   - 检索缓存命中率高不影响准确性，因为 LLM 仍然实时生成答案
   - 响应缓存只在问题完全一致且上下文无变化时命中

4. **"知识库更新后如何使缓存失效？"**
   - 检索缓存：知识库重建时递增版本号，key 中加入版本号，旧版本自动失效
   - 响应缓存：TTL 到期自动失效，或手动清除所有 cache:* 前缀的 key
   - 实现：`await redis_client.delete(*await redis_client.keys("cache:*"))`

5. **"缓存穿透、缓存雪崩怎么处理？"**
   - 缓存穿透（查询不存在的数据）：布隆过滤器提前判断，或缓存空结果（短 TTL）
   - 缓存雪崩（大量缓存同时过期）：TTL 加入随机偏移量，避免集中过期
   - 实现：`ttl = base_ttl + random.randint(0, 300)` 分散过期时间

**开发问题与解决方法**

| 问题 | 场景 | 解决方法 |
|------|------|----------|
| 缓存命中率趋近于 0 | key 包含 session_id + msg_count | 改用归一化问题作为 key，或缓存检索结果 |
| 缓存污染 | 同一问题在不同上下文返回不同答案，后一个覆盖了前一个的缓存 | 检索缓存天然免疫此问题（检索结果不依赖上下文） |
| 缓存与知识库不一致 | 知识库更新后，缓存的检索结果已经过时 | 知识库重建时递增版本号，加入 cache key |
| 缓存雪崩 | 大量 key 在同一时间过期，请求全部打到 LLM | TTL 加入随机偏移量 |
| 缓存穿透 | 故意问一个不存在于知识库的问题，每次都不命中缓存 | 缓存空结果（短 TTL） |
| 内存压力 | 缓存条目过多，Redis 内存耗尽 | 设置 maxmemory-policy allkeys-lru，控制 TTL 不要过长 |
| 序列化开销 | 检索结果包含大量文本，序列化/反序列化耗时 | 使用 pickle 而非 json（更高效），或压缩后存储 |

**为什么当前选择方案一（检索缓存）**

| 维度 | 检索缓存（推荐） | 响应缓存（当前） |
|------|-----------------|-----------------|
| 命中率 | 高（同一问题在不同会话都命中） | 极低（几乎不会命中） |
| 存储对象 | 检索到的 chunks | LLM 生成的完整答案 |
| 上下文依赖 | 不依赖会话上下文 | 强依赖会话上下文 |
| 加速效果 | 消除检索阶段耗时（Embedding + FAISS + BM25 + RRF） | 消除 LLM 生成耗时 |
| 实现复杂度 | 低（key 简化，无需上下文感知） | 低（但 key 设计不合理） |
| 知识库更新影响 | 需要重建缓存 | 需要重建缓存 |
| 适用场景 | 通用 RAG 场景 | 严格的一问一答、无上下文场景 |

**结论：** 当前 response cache 的 key 设计过于保守，导致缓存形同虚设。推荐改为缓存检索结果（retrieval cache），key 仅依赖归一化后的问题文本，在保持实现简单的同时大幅提升缓存命中率。后续可考虑在检索缓存之上叠加响应缓存作为补充。

**涉及文件**
`app/services/cache_service.py` — `make_key` 方法（key 设计问题）
`app/services/rag_service.py` — `stream_query` 方法（缓存检查 + 写入逻辑）
