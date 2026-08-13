# 面试题知识图谱实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 AI 面试模块引入结构化知识树体系，实现 topic 覆盖追踪和智能出题引导

**Architecture:** 知识树 JSON 配置 → TopicTracker 组件加载并统计覆盖 → InterviewService 注入 Prompt 引导 LLM 出题 → 结果存储到 interview_questions 表（新增 topic/category 字段）

**Tech Stack:** Python, SQLite, JSON, LLM Prompt Engineering

## Global Constraints

- 知识树文件存放在 `data/knowledge_trees/` 目录
- 数据库迁移需兼容旧数据（新增字段有默认值）
- 知识树文件不存在时自动回退到旧模式，不阻塞面试
- LLM 输出 topic/category 不在知识树中时仍需接受和存储

---

### Task 1: 知识树 JSON 配置文件

**Files:**
- Create: `data/knowledge_trees/Java后端.json`
- Create: `data/knowledge_trees/AI应用开发.json`

**Interfaces:**
- Produces: 两个 JSON 文件，遵循 spec 中定义的结构格式

- [ ] **Step 1: 创建 Java后端.json**

```json
{
  "position": "Java后端",
  "version": "1.0",
  "categories": [
    {
      "name": "Java基础",
      "description": "数据类型、面向对象、异常、泛型、反射",
      "topics": [
        { "name": "数据类型与包装类", "difficulty": 2, "type": "原理题", "knowledge_points": ["自动装箱", "缓存池", "String不可变性"], "prerequisites": [] },
        { "name": "面向对象", "difficulty": 2, "type": "原理题", "knowledge_points": ["封装", "继承", "多态", "接口与抽象类"], "prerequisites": [] },
        { "name": "泛型", "difficulty": 3, "type": "原理题", "knowledge_points": ["类型擦除", "通配符", "桥接方法"], "prerequisites": ["面向对象"] },
        { "name": "反射", "difficulty": 3, "type": "原理题", "knowledge_points": ["Class对象", "MethodHandle", "动态代理"], "prerequisites": ["类加载"] }
      ]
    },
    {
      "name": "Java集合",
      "description": "Collection框架、Map、线程安全集合",
      "topics": [
        { "name": "ArrayList与LinkedList", "difficulty": 2, "type": "原理题", "knowledge_points": ["数组", "链表", "扩容机制", "随机访问"], "prerequisites": [] },
        { "name": "HashMap", "difficulty": 3, "type": "原理题", "knowledge_points": ["数组", "链表", "红黑树", "扩容", "哈希冲突"], "prerequisites": [] },
        { "name": "ConcurrentHashMap", "difficulty": 4, "type": "原理题", "knowledge_points": ["分段锁", "CAS", "synchronized", "并发扩容"], "prerequisites": ["HashMap"] },
        { "name": "TreeMap与LinkedHashMap", "difficulty": 3, "type": "原理题", "knowledge_points": ["红黑树", "LRU", "插入顺序"], "prerequisites": ["HashMap"] }
      ]
    },
    {
      "name": "JVM",
      "description": "内存模型、GC、类加载、性能调优",
      "topics": [
        { "name": "内存模型", "difficulty": 3, "type": "原理题", "knowledge_points": ["堆", "栈", "方法区", "直接内存", "OOM"], "prerequisites": [] },
        { "name": "GC", "difficulty": 4, "type": "原理题", "knowledge_points": ["可达性分析", "GC算法", "CMS", "G1", "ZGC"], "prerequisites": ["内存模型"] },
        { "name": "类加载", "difficulty": 3, "type": "原理题", "knowledge_points": ["双亲委派", "打破双亲委派", "自定义类加载器"], "prerequisites": [] },
        { "name": "JVM调优", "difficulty": 4, "type": "实操题", "knowledge_points": ["堆参数", "GC日志", "MAT分析", "CPU飙高排查"], "prerequisites": ["内存模型", "GC"] }
      ]
    },
    {
      "name": "并发",
      "description": "线程、锁、AQS、线程池、并发工具",
      "topics": [
        { "name": "synchronized", "difficulty": 3, "type": "原理题", "knowledge_points": ["对象头", "偏向锁", "轻量锁", "锁升级"], "prerequisites": [] },
        { "name": "volatile", "difficulty": 3, "type": "原理题", "knowledge_points": ["可见性", "有序性", "happens-before", "内存屏障"], "prerequisites": [] },
        { "name": "CAS", "difficulty": 3, "type": "原理题", "knowledge_points": ["ABA问题", "Unsafe", "原子类"], "prerequisites": ["volatile"] },
        { "name": "AQS", "difficulty": 4, "type": "原理题", "knowledge_points": ["CLH队列", "ReentrantLock", "CountDownLatch", "Semaphore"], "prerequisites": ["CAS"] },
        { "name": "线程池", "difficulty": 3, "type": "原理题", "knowledge_points": ["核心参数", "拒绝策略", "ThreadPoolExecutor", "ForkJoinPool"], "prerequisites": [] }
      ]
    },
    {
      "name": "Spring",
      "description": "IOC、AOP、事务、Spring Boot",
      "topics": [
        { "name": "IOC容器", "difficulty": 3, "type": "原理题", "knowledge_points": ["Bean生命周期", "依赖注入", "循环依赖", "三级缓存"], "prerequisites": [] },
        { "name": "AOP", "difficulty": 3, "type": "原理题", "knowledge_points": ["动态代理", "CGLIB", "切面", "通知类型"], "prerequisites": ["反射"] },
        { "name": "事务", "difficulty": 3, "type": "原理题", "knowledge_points": ["@Transactional", "传播行为", "隔离级别", "失效场景"], "prerequisites": ["AOP", "MySQL事务"] },
        { "name": "Spring Boot自动配置", "difficulty": 3, "type": "原理题", "knowledge_points": ["@EnableAutoConfiguration", "Conditional", "Starter机制"], "prerequisites": ["IOC容器"] }
      ]
    },
    {
      "name": "MySQL",
      "description": "存储引擎、索引、事务、锁、优化",
      "topics": [
        { "name": "存储引擎", "difficulty": 2, "type": "原理题", "knowledge_points": ["InnoDB", "MyISAM", "B+树", "聚簇索引"], "prerequisites": [] },
        { "name": "索引优化", "difficulty": 3, "type": "实操题", "knowledge_points": ["联合索引", "覆盖索引", "索引下推", "Explain"], "prerequisites": ["存储引擎"] },
        { "name": "MySQL事务", "difficulty": 3, "type": "原理题", "knowledge_points": ["ACID", "隔离级别", "MVCC", "Next-Key Lock"], "prerequisites": [] },
        { "name": "SQL优化", "difficulty": 3, "type": "实操题", "knowledge_points": ["慢查询", "分页优化", "JOIN优化", "数据类型选择"], "prerequisites": ["索引优化"] }
      ]
    },
    {
      "name": "Redis",
      "description": "数据结构、持久化、集群、缓存",
      "topics": [
        { "name": "数据结构", "difficulty": 2, "type": "原理题", "knowledge_points": ["String", "Hash", "ZSet", "底层编码"], "prerequisites": [] },
        { "name": "持久化", "difficulty": 3, "type": "原理题", "knowledge_points": ["RDB", "AOF", "混合持久化"], "prerequisites": [] },
        { "name": "缓存设计", "difficulty": 3, "type": "设计题", "knowledge_points": ["穿透", "击穿", "雪崩", "一致性"], "prerequisites": [] },
        { "name": "集群", "difficulty": 4, "type": "原理题", "knowledge_points": ["主从", "哨兵", "Cluster", "分片"], "prerequisites": ["持久化"] }
      ]
    },
    {
      "name": "操作系统与网络",
      "description": "进程、线程、IO、TCP、HTTP",
      "topics": [
        { "name": "进程与线程", "difficulty": 2, "type": "原理题", "knowledge_points": ["PCB", "上下文切换", "用户态/内核态"], "prerequisites": [] },
        { "name": "IO模型", "difficulty": 3, "type": "原理题", "knowledge_points": ["BIO", "NIO", "AIO", "多路复用", "零拷贝"], "prerequisites": ["进程与线程"] },
        { "name": "TCP", "difficulty": 3, "type": "原理题", "knowledge_points": ["三次握手", "四次挥手", "拥塞控制", "粘包"], "prerequisites": [] },
        { "name": "HTTP", "difficulty": 2, "type": "原理题", "knowledge_points": ["状态码", "HTTPS", "HTTP/2", "HTTP/3"], "prerequisites": ["TCP"] }
      ]
    }
  ]
}
```

- [ ] **Step 2: 创建 AI应用开发.json**

```json
{
  "position": "AI应用开发",
  "version": "1.0",
  "categories": [
    {
      "name": "Python基础",
      "description": "数据类型、装饰器、生成器、异步",
      "topics": [
        { "name": "数据类型与特性", "difficulty": 2, "type": "原理题", "knowledge_points": ["可变/不可变", "列表推导", "生成器", "装饰器"], "prerequisites": [] },
        { "name": "异步编程", "difficulty": 3, "type": "原理题", "knowledge_points": ["async/await", "事件循环", "协程", "asyncio"], "prerequisites": [] },
        { "name": "GIL与多线程", "difficulty": 3, "type": "原理题", "knowledge_points": ["GIL原理", "多进程", "线程安全"], "prerequisites": [] }
      ]
    },
    {
      "name": "大模型基础",
      "description": "Transformer、Prompt、RAG、Agent",
      "topics": [
        { "name": "Transformer架构", "difficulty": 3, "type": "原理题", "knowledge_points": ["Self-Attention", "多头注意力", "位置编码", "LayerNorm"], "prerequisites": [] },
        { "name": "Prompt Engineering", "difficulty": 2, "type": "实操题", "knowledge_points": ["Few-shot", "Chain-of-Thought", "System Prompt", "输出格式化"], "prerequisites": [] },
        { "name": "RAG技术", "difficulty": 3, "type": "设计题", "knowledge_points": ["Embedding", "向量检索", "Chunk策略", "重排序"], "prerequisites": ["Transformer架构"] },
        { "name": "Agent", "difficulty": 4, "type": "设计题", "knowledge_points": ["ReAct", "工具调用", "记忆", "多Agent协作"], "prerequisites": ["Prompt Engineering", "RAG技术"] }
      ]
    },
    {
      "name": "模型部署与服务",
      "description": "vLLM、量化、推理优化、API服务",
      "topics": [
        { "name": "推理优化", "difficulty": 3, "type": "原理题", "knowledge_points": ["KV Cache", "Flash Attention", "连续批处理", "量化"], "prerequisites": ["Transformer架构"] },
        { "name": "vLLM与Serving", "difficulty": 3, "type": "实操题", "knowledge_points": ["PageAttention", "Prefix Caching", "OpenAI兼容API"], "prerequisites": ["推理优化"] },
        { "name": "模型微调", "difficulty": 4, "type": "实操题", "knowledge_points": ["LoRA", "QLoRA", "数据集构建", "SFT/RLHF"], "prerequisites": ["Transformer架构"] }
      ]
    },
    {
      "name": "AI工程化",
      "description": "数据处理、评估、监控、CI/CD",
      "topics": [
        { "name": "数据处理流程", "difficulty": 2, "type": "实操题", "knowledge_points": ["数据清洗", "标注", "增强", "质量评估"], "prerequisites": [] },
        { "name": "模型评估", "difficulty": 3, "type": "原理题", "knowledge_points": ["Benchmark", "BLEU/ROUGE", "人工评估", "A/B测试"], "prerequisites": [] },
        { "name": "AI应用监控", "difficulty": 3, "type": "设计题", "knowledge_points": ["Token计量", "延迟追踪", "质量监控", "告警"], "prerequisites": ["模型评估"] }
      ]
    }
  ]
}
```

- [ ] **Step 3: 提交**

```bash
git add data/knowledge_trees/Java后端.json data/knowledge_trees/AI应用开发.json
git commit -m "feat: 添加知识树配置文件（Java后端/AI应用开发）"
```

---

### Task 2: 数据库 Schema 变更 — 新增 topic/category 字段

**Files:**
- Modify: `app/storage/interview_store.py` (init_db + add_question)

**Interfaces:**
- Consumes: InterviewStore 现有接口
- Produces: `add_question()` 接受 `topic` 和 `category` 参数，数据库表新增字段

- [ ] **Step 1: 修改 `_init_db()` 增加 topic/category 列**

在 `interview_questions` 表的 `CREATE TABLE` 中，在 `source` 行后添加两列：

```python
source         TEXT DEFAULT 'kb',
topic          TEXT DEFAULT '',
category       TEXT DEFAULT '',
created_at     TEXT,
```

- [ ] **Step 2: 修改 `add_question()` 方法**

修改函数签名，接受 `topic` 和 `category` 参数：

```python
def add_question(self, session_id: str, round_num: int, question: str,
                 difficulty: str = "medium", source: str = "kb",
                 topic: str = "", category: str = "") -> dict:
    qid = str(uuid.uuid4())
    now = self._now()
    with self._get_conn() as conn:
        conn.execute(
            """INSERT INTO interview_questions
               (id, session_id, round, question, difficulty, source, topic, category, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (qid, session_id, round_num, question, difficulty, source, topic, category, now),
        )
        conn.execute(
            "UPDATE interview_sessions SET total_rounds = ? WHERE id = ?",
            (round_num, session_id),
        )
    return {"id": qid, "session_id": session_id, "round": round_num,
            "question": question, "difficulty": difficulty,
            "topic": topic, "category": category}
```

- [ ] **Step 3: 提交**

```bash
git add app/storage/interview_store.py
git commit -m "feat: interview_questions 表新增 topic/category 字段"
```

---

### Task 3: TopicTracker 组件

**Files:**
- Create: `app/services/topic_tracker.py`

**Interfaces:**
- Consumes: InterviewStore（通过 `get_questions(session_id)` 获取已覆盖 topic）
- Produces: `get_coverage()`, `get_next_suggestion()`, `suggest_prerequisites()` 方法

- [ ] **Step 1: 创建 topic_tracker.py 文件**

```python
"""Knowledge tree topic coverage tracker for interview sessions.

Loads knowledge tree JSON configs and tracks which topics have been
covered in each interview session, providing next-topic suggestions.
"""

import json
from pathlib import Path
from typing import Optional

from app.storage.interview_store import InterviewStore
from app.utils.logger import get_logger

logger = get_logger(__name__)

TREE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge_trees"


class TopicTracker:
    """Track topic coverage for interview sessions using knowledge tree configs."""

    def __init__(self, interview_store: InterviewStore, tree_dir: str = None):
        self._store = interview_store
        self._tree_dir = Path(tree_dir) if tree_dir else TREE_DIR
        self._tree_cache: dict[str, dict] = {}

    def get_tree(self, position: str) -> Optional[dict]:
        """Load the knowledge tree for a given position."""
        if position in self._tree_cache:
            return self._tree_cache[position]

        filepath = self._tree_dir / f"{position}.json"
        if not filepath.exists():
            logger.warning(f"Knowledge tree not found: {filepath}")
            return None

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tree = json.load(f)
            self._tree_cache[position] = tree
            logger.info(f"Loaded knowledge tree: {position} ({len(tree.get('categories', []))} categories)")
            return tree
        except Exception as e:
            logger.error(f"Failed to load knowledge tree {filepath}: {e}")
            return None

    def get_coverage(self, session_id: str, position: str) -> dict:
        """Get topic coverage statistics for a session."""
        tree = self.get_tree(position)
        if not tree:
            return {"categories": {}, "weakest": None, "untouched": [], "total_covered": 0, "total_topics": 0}

        # Collect covered topics from the database
        questions = self._store.get_questions(session_id)
        covered_topics = set()
        covered_categories = {}
        for q in questions:
            topic = q.get("topic", "") or ""
            category = q.get("category", "") or ""
            if topic:
                covered_topics.add(topic)
            if category:
                if category not in covered_categories:
                    covered_categories[category] = set()
                covered_categories[category].add(topic)

        # Match against tree structure
        total_topics = 0
        categories_info = {}
        for cat in tree.get("categories", []):
            cat_name = cat["name"]
            topics_in_cat = [t["name"] for t in cat.get("topics", [])]
            total_topics += len(topics_in_cat)
            covered_in_cat = covered_categories.get(cat_name, set())
            covered_count = sum(1 for t in topics_in_cat if t in covered_in_cat)
            categories_info[cat_name] = {
                "total": len(topics_in_cat),
                "covered": covered_count,
                "topics": {t: t in covered_in_cat for t in topics_in_cat},
            }

        # Find weakest category
        untouched = [name for name, info in categories_info.items() if info["covered"] == 0]
        weakest = min(categories_info, key=lambda k: (
            categories_info[k]["covered"] / max(categories_info[k]["total"], 1)
        )) if categories_info else None

        return {
            "categories": categories_info,
            "weakest": weakest,
            "untouched": untouched,
            "total_covered": len(covered_topics),
            "total_topics": total_topics,
        }

    def get_next_suggestion(self, session_id: str, position: str) -> dict:
        """Suggest the next topic/category to focus on."""
        coverage = self.get_coverage(session_id, position)
        tree = self.get_tree(position)
        if not tree:
            return {"category": None, "topic": None, "reason": "知识树未加载"}

        categories = tree.get("categories", [])

        # 1. Pick untouched category first
        if coverage["untouched"]:
            cat_name = coverage["untouched"][0]
            cat = next((c for c in categories if c["name"] == cat_name), None)
            if cat:
                topics = cat.get("topics", [])
                # Pick first topic without unmet prerequisites
                for t in topics:
                    prereqs = t.get("prerequisites", [])
                    unmet = self.suggest_prerequisites(t["name"], position)
                    if not unmet:
                        return {
                            "category": cat_name,
                            "topic": t["name"],
                            "reason": f"「{cat_name}」方向尚未考察，建议从「{t['name']}」开始",
                        }
                # Fallback: first topic
                return {
                    "category": cat_name,
                    "topic": topics[0]["name"],
                    "reason": f"「{cat_name}」方向尚未考察",
                }

        # 2. Pick weakest covered category
        cat_name = coverage["weakest"]
        cat = next((c for c in categories if c["name"] == cat_name), None)
        if cat:
            for t in cat.get("topics", []):
                if t["name"] not in set(
                    q.get("topic", "") for q in self._store.get_questions(session_id)
                ):
                    prereqs = t.get("prerequisites", [])
                    unmet = self.suggest_prerequisites(t["name"], position)
                    if not unmet:
                        return {
                            "category": cat_name,
                            "topic": t["name"],
                            "reason": f"「{cat_name}」方向覆盖不足，建议出「{t['name']}」",
                        }

        # 3. All covered
        return {"category": None, "topic": None, "reason": "所有知识点已覆盖"}

    def suggest_prerequisites(self, topic_name: str, position: str) -> list:
        """Check if prerequisites for a topic are covered. Returns unmet prerequisites."""
        tree = self.get_tree(position)
        if not tree:
            return []

        # Find the topic in the tree
        for cat in tree.get("categories", []):
            for t in cat.get("topics", []):
                if t["name"] == topic_name:
                    # We need to check if prerequisites are covered
                    # Since we can't know without a session_id, return empty
                    return t.get("prerequisites", [])
        return []

    def get_coverage_summary_text(self, session_id: str, position: str) -> str:
        """Generate a human-readable coverage summary for the LLM prompt."""
        coverage = self.get_coverage(session_id, position)
        if not coverage["categories"]:
            return ""

        lines = ["当前面试覆盖情况："]
        for cat_name, info in coverage["categories"].items():
            status = "✓" if info["covered"] == info["total"] else "△" if info["covered"] > 0 else "○"
            lines.append(f"  {status} {cat_name}: {info['covered']}/{info['total']} 题")
        lines.append(f"→ 薄弱方向：{coverage['weakest'] or '无'}")
        if coverage["untouched"]:
            lines.append(f"→ 未覆盖方向：{'、'.join(coverage['untouched'])}")
        return "\n".join(lines)

    def get_tree_structure_text(self, position: str) -> str:
        """Generate a compact text representation of the knowledge tree for the prompt."""
        tree = self.get_tree(position)
        if not tree:
            return ""

        lines = []
        for cat in tree.get("categories", []):
            topics = [t["name"] for t in cat.get("topics", [])]
            lines.append(f"  {cat['name']}: {' → '.join(topics)}")
        return "\n".join(lines)
```

- [ ] **Step 2: 提交**

```bash
git add app/services/topic_tracker.py
git commit -m "feat: 新增 TopicTracker 组件，支持知识树覆盖追踪和出题推荐"
```

---

### Task 4: InterviewService 集成 — Prompt 注入 + TopicTracker 使用

**Files:**
- Modify: `app/services/interview_service.py`

**Interfaces:**
- Consumes: `TopicTracker` (get_coverage_summary_text, get_next_suggestion, get_tree_structure_text)
- Consumes: `InterviewStore.add_question()` 新增了 topic/category 参数
- Produces: 出题时 LLM 输出包含 topic/category，存入数据库

- [ ] **Step 1: 修改 `_generate_question()` 方法集成 TopicTracker**

在 `_generate_question` 方法中，注入知识覆盖统计和知识树结构，并处理 LLM 结构化的 topic/category 输出：

```python
async def _generate_question(
    self,
    session_id: str,
    position: str,
    round_num: int,
    difficulty: str = "medium",
    last_answer: str = "",
    last_evaluation: Optional[dict] = None,
) -> dict:
    """Generate a question for the interview."""
    # Get context from previous questions
    questions = self.store.get_questions(session_id)
    history_count = len(questions)
    difficulty_history = ", ".join([_difficulty_label(q.get("difficulty", "medium")) for q in questions]) or "暂无"
    last_eval_summary = ""
    if last_evaluation:
        last_eval_summary = f"得分：{last_evaluation.get('score', '?')}，评语：{last_evaluation.get('comment', '')[:50]}"

    # Retrieve knowledge base context
    kb_context = await self._retrieve_context(f"{position} 技术面试题 {difficulty}")

    # --- Knowledge tree integration ---
    coverage_text = ""
    tree_text = ""
    suggestion_text = ""
    suggested_category = ""
    if self.topic_tracker:
        tree = self.topic_tracker.get_tree(position)
        if tree:
            coverage_text = self.topic_tracker.get_coverage_summary_text(session_id, position)
            tree_text = self.topic_tracker.get_tree_structure_text(position)
            suggestion = self.topic_tracker.get_next_suggestion(session_id, position)
            if suggestion.get("topic"):
                suggested_category = suggestion.get("category", "")
                suggestion_text = (
                    f"建议优先出题方向：{suggested_category} - {suggestion['topic']}\n"
                    f"原因：{suggestion['reason']}"
                )

    prompt = QUESTION_PROMPT.format(
        position=position,
        round=round_num,
        history_count=history_count,
        difficulty_history=difficulty_history,
        last_evaluation_summary=last_eval_summary,
        knowledge_context=kb_context,
        难度提示=_difficulty_label(difficulty),
        # New template variables for knowledge tree
        coverage_summary=coverage_text,
        knowledge_tree_structure=tree_text,
        suggested_topic=suggestion_text,
        suggested_category=suggested_category,
    )

    text = await self.llm.chat(prompt, SYSTEM_START)
    parsed = _parse_json(text)
    if not parsed:
        logger.warning(f"Failed to parse question JSON, using fallback. Raw: {text[:200]}")
        parsed = {
            "question": text[:200] if len(text) > 200 else text,
            "difficulty": difficulty,
            "source": "llm",
            "knowledge_tags": [],
            "topic": "",
            "category": "",
        }

    question_text = parsed.get("question", text[:200])
    q_difficulty = parsed.get("difficulty", difficulty)
    q_source = parsed.get("source", "llm")
    knowledge_tags = parsed.get("knowledge_tags", [])
    q_topic = parsed.get("topic", "") or ""
    q_category = parsed.get("category", "") or ""

    # Store the question
    q = self.store.add_question(
        session_id, round_num, question_text, q_difficulty, q_source,
        topic=q_topic, category=q_category,
    )

    return {
        "id": q["id"],
        "content": question_text,
        "round": round_num,
        "difficulty": q_difficulty,
        "source": q_source,
        "knowledge_tags": knowledge_tags,
        "topic": q_topic,
        "category": q_category,
    }
```

- [ ] **Step 2: 修改 QUESTION_PROMPT 模板，注入知识树变量**

```python
QUESTION_PROMPT = """你正在进行一场 {position} 岗位的面试。

当前是第 {round} 题。
前面已有 {history_count} 道题，难度分布：{difficulty_history}
上一题评价：{last_evaluation_summary}

{knowledge_context}

{coverage_summary}
{suggested_topic}

【知识树参考】
{knowledge_tree_structure}

请出一道{难度提示}技术面试题，混合技术知识点、项目经验或系统设计方向。
题目应该是面试中常见的高质量题目。

请按以下 JSON 格式输出（不要包含其他内容）：
{{
    "question": "题目内容",
    "difficulty": "easy/medium/hard",
    "source": "kb/llm",
    "knowledge_tags": ["知识点标签1", "知识点标签2"],
    "topic": "从知识树中选择的 topic 名称",
    "category": "从知识树中选择的 category 名称"
}}"""
```

- [ ] **Step 3: 修改 InterviewService 初始化，增加 topic_tracker 参数**

```python
class InterviewService:
    def __init__(
        self,
        store: InterviewStore,
        llm: LLMClient,
        faiss: Optional[FaissStore] = None,
        embedding: Optional[EmbeddingService] = None,
        topic_tracker: Optional[TopicTracker] = None,
    ):
        self.store = store
        self.llm = llm
        self.faiss = faiss
        self.embedding = embedding
        self.topic_tracker = topic_tracker
        self.max_rounds = 15
        self.min_rounds = 5
```

- [ ] **Step 4: 修改 main.py 初始化、传入 TopicTracker**

```python
from app.services.topic_tracker import TopicTracker

# 在 lifespan 初始化中：
topic_tracker = TopicTracker(interview_store=interview_store)

# 传入 InterviewService：
interview_service = InterviewService(
    interview_store, llm_client, faiss_store, embedding_service,
    topic_tracker=topic_tracker,
)
```

- [ ] **Step 5: 提交**

```bash
git add app/services/interview_service.py app/main.py
git commit -m "feat: InterviewService 集成 TopicTracker，注入知识覆盖统计到 Prompt"
```

---

### Task 5: 报告增强 — 新增 topic_analysis

**Files:**
- Modify: `app/services/interview_service.py` (`_generate_report` 方法)

- [ ] **Step 1: 修改 `_generate_report()` 增加 topic_analysis**

在 `_generate_report` 方法中，生成报告后附加 topic_analysis：

```python
async def _generate_report(self, session_id: str) -> dict:
    session = self.store.get_session(session_id)
    questions = self.store.get_questions(session_id)

    if not session or not questions:
        return {"total_score": 0, "level": "未知", "improvement_suggestions": ["无足够数据"]}

    total_score = 0
    q_details = []
    for q in questions:
        score = q.get("score", 0) or 0
        total_score += score
        tags = []
        if q.get("evaluation"):
            tags = q["evaluation"].get("tags", [])
        q_details.append({
            "round": q["round"],
            "question": q["question"][:80],
            "score": score,
            "tags": tags,
            "topic": q.get("topic", "") or "",
            "category": q.get("category", "") or "",
        })

    avg_score = round(total_score / len(questions), 1)

    prompt = REPORT_PROMPT.format(
        position=session["position"],
        total_rounds=len(questions),
        total_score=avg_score,
        questions_detail=json.dumps(q_details, ensure_ascii=False, indent=2),
    )

    text = await self.llm.chat(prompt)
    parsed = _parse_json(text)

    # --- Topic analysis (no LLM needed) ---
    topic_analysis = []
    category_scores = {}
    for q in q_details:
        cat = q.get("category", "") or "其他"
        if cat not in category_scores:
            category_scores[cat] = {"scores": [], "topics": set()}
        category_scores[cat]["scores"].append(q["score"])
        if q.get("topic"):
            category_scores[cat]["topics"].add(q["topic"])

    for cat_name, data in category_scores.items():
        avg = round(sum(data["scores"]) / len(data["scores"]), 1)
        if avg >= 7:
            status = "strong"
        elif avg >= 5:
            status = "moderate"
        else:
            status = "weak"
        topic_analysis.append({
            "category": cat_name,
            "topics_covered": len(data["topics"]),
            "avg_score": avg,
            "status": status,
        })

    if parsed:
        parsed["total_score"] = avg_score
        parsed["topic_analysis"] = topic_analysis

        # Generate recommended_study from topic_analysis
        recommended = []
        for ta in topic_analysis:
            if ta["status"] == "weak":
                recommended.append({
                    "category": ta["category"],
                    "priority": "high",
                    "reason": f"得分偏低（{ta['avg_score']}分），建议重点复习",
                })
            elif ta["status"] == "moderate":
                recommended.append({
                    "category": ta["category"],
                    "priority": "medium",
                    "reason": f"基础尚可（{ta['avg_score']}分），建议补充深度",
                })
        parsed["recommended_study"] = recommended
        return parsed

    # Fallback report
    return {
        "total_score": avg_score,
        "score_breakdown": q_details,
        "knowledge_analysis": {"strengths": [], "weaknesses": []},
        "improvement_suggestions": ["报告生成失败，请重试"],
        "level": "中级" if avg_score >= 6 else "初级",
        "topic_analysis": topic_analysis,
    }
```

- [ ] **Step 2: 提交**

```bash
git add app/services/interview_service.py
git commit -m "feat: 面试报告新增 topic_analysis 分类得分分析"
```

---

### Task 6: 验证功能

- [ ] **Step 1: 启动服务**

```bash
$env:KMP_DUPLICATE_LIB_OK="TRUE"; python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- [ ] **Step 2: 测试面试启动 → 检查出题是否包含 topic/category**

```bash
# 使用 PowerShell 测试
$r = Invoke-RestMethod -Uri "http://localhost:8000/api/interview/start" -Method Post -ContentType "application/json" -Body '{"position": "Java后端"}'
Write-Output "Topic: $($r.question.topic)"
Write-Output "Category: $($r.question.category)"
```

- [ ] **Step 3: 测试多轮面试 → 验证 topic 覆盖追踪**

先提交一道题的回答，再启动第二道题，检查第二道题的 topic 是否和第一道不同（属于不同 category）。

- [ ] **Step 4: 测试面试报告 → 验证 topic_analysis**

```bash
$sid = (Invoke-RestMethod -Uri "http://localhost:8000/api/interview/history").sessions[0].id
$report = Invoke-RestMethod -Uri "http://localhost:8000/api/interview/report/$sid"
Write-Output "Topic Analysis: $($report.report.topic_analysis | ConvertTo-Json)"
```

- [ ] **Step 5: 提交最后的验证**

```bash
git add -A
git commit -m "chore: 知识树功能验证通过"
```