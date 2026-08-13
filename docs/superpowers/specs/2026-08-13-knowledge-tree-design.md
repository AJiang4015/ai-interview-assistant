# 面试题知识图谱 / 题目标签体系

## 1. 概述

为 AI 面试模块引入结构化知识树体系，使面试出题有据可依、覆盖可追踪、报告可细化。

**核心目标：**
- 知识树作为配置定义，可扩展多岗位（Java后端、AI应用开发等）
- 面试过程中 LLM 出题时自动打标签，匹配知识树节点
- 追踪每场面试的 topic 覆盖度，引导下一题走向薄弱方向
- 报告细化到 topic 级别，输出分类得分和学习建议

## 2. 架构

```
knowledge_trees/*.json  ──→  TopicTracker  ──→  InterviewService
       ↑                          │                    │
  配置定义（岗位独立）       覆盖统计+推荐            Prompt 注入
                                                     │
                                               interview_questions
                                               (新增 topic/category)
```

## 3. 知识树定义格式

存放路径：`data/knowledge_trees/{position}.json`

### 3.1 数据结构

```json
{
  "position": "Java后端",
  "version": "1.0",
  "categories": [
    {
      "name": "Java集合",
      "description": "Collection框架、Map、线程安全集合",
      "topics": [
        {
          "name": "HashMap",
          "difficulty": 3,
          "type": "原理题",
          "knowledge_points": ["数组", "链表", "红黑树", "扩容", "哈希冲突"],
          "prerequisites": []
        },
        {
          "name": "ConcurrentHashMap",
          "difficulty": 4,
          "type": "原理题",
          "knowledge_points": ["分段锁", "CAS", "synchronized", "并发扩容"],
          "prerequisites": ["HashMap"]
        }
      ]
    },
    {
      "name": "JVM",
      "description": "内存模型、GC、类加载、性能调优",
      "topics": [
        {
          "name": "内存模型",
          "difficulty": 3,
          "type": "原理题",
          "knowledge_points": ["堆", "栈", "方法区", "直接内存"],
          "prerequisites": []
        },
        {
          "name": "GC",
          "difficulty": 4,
          "type": "原理题",
          "knowledge_points": ["可达性分析", "GC算法", "CMS", "G1"],
          "prerequisites": ["内存模型"]
        }
      ]
    }
  ]
}
```

### 3.2 字段说明

| 字段 | 说明 |
|------|------|
| `position` | 岗位标识，匹配前端选择的岗位 |
| `categories` | 分类列表，如 "Java集合"、"JVM" |
| `topics[].name` | 具体知识点，如 "HashMap" |
| `topics[].difficulty` | 1-5 数值，映射 easy/medium/hard |
| `topics[].prerequisites` | 前置知识点，必须覆盖后才能出该 topic 的题 |
| `knowledge_points` | LLM 出题时参考的细粒度知识点列表 |

### 3.3 扩展方式

新增岗位只需在 `data/knowledge_trees/` 下创建对应的 JSON 文件，无需修改代码。

## 4. 数据库 Schema 变更

### interview_questions 表新增字段

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `topic` | TEXT | '' | 知识树中的 topic 名称，如 "HashMap" |
| `category` | TEXT | '' | 所属 category，如 "Java集合" |

保留原有 `knowledge_tags` 字段，作为 LLM 自由补充的细粒度标签。

## 5. TopicTracker 组件

### 5.1 职责

- 加载指定岗位的知识树 JSON
- 查询当前会话的 topic 覆盖统计
- 推荐下一个应出题的方向

### 5.2 接口设计

```python
class TopicTracker:
    def __init__(self, tree_dir: str = "data/knowledge_trees")

    def get_tree(self, position: str) -> dict
        """加载指定岗位的知识树"""

    def get_coverage(self, session_id: str, position: str) -> dict
        """
        返回当前会话的覆盖统计：
        {
            "categories": {
                "Java集合": { "total": 5, "covered": 2, "topics": {...} },
                "JVM":      { "total": 3, "covered": 0, "topics": {...} }
            },
            "weakest": "JVM",            // 覆盖最少的 category
            "untouched": ["JVM"],         // 完全没覆盖的 category
            "total_covered": 2,
            "total_topics": 8
        }
        """

    def get_next_suggestion(self, session_id: str, position: str) -> dict
        """
        推荐下一个出题方向：
        {
            "category": "JVM",
            "topic": "内存模型",
            "reason": "JVM 方向尚未考察"
        }
        """

    def suggest_prerequisites(self, topic: str, position: str) -> list
        """检查指定 topic 的前置知识点是否已覆盖，返回未覆盖的前置列表"""
```

### 5.3 推荐逻辑

1. 优先推荐完全未覆盖的 category
2. category 内优先推荐未覆盖的 topic
3. 检查 topic 的 prerequisites，如果前置未覆盖，先推荐前置
4. 全部覆盖后，从覆盖最少的 topic 开始循环

## 6. Prompt 集成

### 6.1 出题 Prompt 改造

在现有 `QUESTION_PROMPT` 中注入知识覆盖统计和知识树结构：

```
你正在进行 {position} 岗位的面试，当前是第 {round} 题。

【知识覆盖统计】
{coverage_summary}
→ 薄弱方向：{weakest_category}（尚未考察）
→ 建议优先出题方向：{suggested_topic}

【知识树参考】
{knowledge_tree_structure}

请从「{suggested_category}」方向出一道{difficulty}的面试题。
要求：
- 题目应覆盖该方向的核心知识点
- 请从知识树中选择最匹配的 topic 和 category
- 如果是进阶题，尽量避开与前面题目重复的方向

输出 JSON 格式：
{
    "question": "...",
    "difficulty": "easy/medium/hard",
    "topic": "HashMap",           // 从知识树中选择
    "category": "Java集合",       // 从知识树中选择
    "knowledge_points": ["数组", "扩容"],
    "source": "kb/llm"
}
```

### 6.2 结构化输出

LLM 输出必须包含 `topic` 和 `category` 字段，InterviewService 将其存入数据库。TopicTracker 利用这些字段统计覆盖度。

## 7. 报告增强

### 7.1 新增 topic 级别分析

报告中新增 `topic_analysis` 字段：

```json
{
    "topic_analysis": [
        { "category": "Java集合", "topics_covered": 2, "avg_score": 8.5, "status": "strong" },
        { "category": "JVM",      "topics_covered": 1, "avg_score": 6.0, "status": "weak" },
        { "category": "并发",     "topics_covered": 0, "avg_score": 0,   "status": "untouched" }
    ],
    "recommended_study": [
        { "category": "JVM", "priority": "high", "reason": "得分偏低，建议重点复习" },
        { "category": "并发", "priority": "medium", "reason": "未考察，建议补充" }
    ]
}
```

### 7.2 生成方式

数据直接从 TopicTracker 的覆盖统计 + 数据库中的得分计算得出，不需要 LLM 参与。

## 8. 文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `data/knowledge_trees/Java后端.json` | 新增 | Java 后端知识树配置 |
| `data/knowledge_trees/AI应用开发.json` | 新增 | AI 应用开发知识树配置 |
| `app/services/topic_tracker.py` | 新增 | TopicTracker 组件 |
| `app/storage/interview_store.py` | 修改 | 新增 topic/category 字段 |
| `app/services/interview_service.py` | 修改 | Prompt 注入、TopicTracker 集成 |
| `app/services/interview_service.py` | 修改 | 报告生成增加 topic_analysis |

## 9. 错误处理

- 知识树文件不存在：回退到无知识树的旧模式，记录警告日志
- LLM 输出的 topic/category 不在知识树中：接受并存储，不拒绝
- 数据库迁移兼容：新增字段有默认值，旧数据不受影响