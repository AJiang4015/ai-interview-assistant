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