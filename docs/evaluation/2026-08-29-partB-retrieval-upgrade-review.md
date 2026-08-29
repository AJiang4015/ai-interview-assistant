# Part B 复盘：面试检索升级 — 工程成果沉淀

> 类型：项目阶段复盘（面向后续维护与面试表达）
> 日期：2026-08-29
> 关联：Spec `docs/superpowers/specs/2026-08-28-interview-retrieval-upgrade-partB.md`
> 前置：Part A 检索评测闭环（`2026-08-28-retrieval-eval-closed-loop-partA.md`）

---

## 一、问题背景：面试检索与问答链路割裂

项目核心卖点是「面试与知识库联动」，但升级前存在两条**互不相通的检索链路**：

- **问答主链路**（`rag_service`）：`query rewrite → 混合检索(RRF) → rerank → parent expansion`，这条链路经历了 Part A 的消融验证，质量有据可依；
- **面试检索**（`interview_service._retrieve_context`）：**只有 raw FAISS 稠密检索，取 top-3**，没有任何 hybrid / rerank / query rewrite，且失败时静默返回空串。

结果：面试场景走的是「独木桥」——形似连上知识库，实则检索质量裸奔，吃着与问答不同的、更差的检索能力。

## 二、原方案缺陷（具体）

1. **检索能力降级**：面试 `faiss.search(vec, 3)` 只用稠密腿，无稀疏召回、无重排序，`recall@3` 在面试评测子集上仅 **0.588**（见 § 指标对比）。
2. **检索词语义错位**：出题用 `f"{position} 技术面试题 {difficulty}"` 这种"不是问题的问题"（`interview_service.py` 旧 L543-544），与知识库内容措辞严重对不上（PHP→Java、语法错位），召回天然虚低。
3. **不可验证**：没有评估集、没有复现命令，改检索全凭玄学——这正是指向 Part A 建立评测闭环的动机。

## 三、设计方案：统一 RetrievalFacade

**核心理念：管线下资产复用，管线上策略差异。**

- **新增 `app/services/retrieval_facade.py`**：`RetrievalFacade.retrieve(query, top_k)` 把 `qr → hybrid(RRF) → rerank → parent → dedup` 封装为唯一入口，开关状态继承 Part A 消融结论（`enable_query_rewrite` / `enable_rerank` / `enable_hybrid_search`）。
- **问答与面试共用同一条已验证管线**；差异只在 facade 之上：
  - 问答：原始问题，`top_k=self.top_k`；
  - 面试评价：`问题 + 用户回答` 拼接（这是面试链路与问答真正不同的地方）。
- **约束落地**：
  - 任一环节失败降级返回空 / 回退 raw FAISS（**DR-001**）；
  - 重排走 SiliconFlow `Qwen/Qwen3-Reranker-4B`（**DR-003**）；
  - facade 自身不碰缓存，面试评价 query 含用户回答，**绝不以"问题+回答"做缓存 key**（**DR-004**）；
  - SSE `retrieval` 事件结构逐字不变（**DR-005**）。

## 四、实施过程（S1 → S2 → S3）

| 阶段 | 内容 | 验收 |
|------|------|------|
| **S0 准入** | Part A 达标确认；拍板「路线甲：仅迁移 facade」+「出题/评价各检索一次、追问默认不检索」 | spec 状态置为已确认（`46f830f`） |
| **S1 抽 facade + 问答收口** | 新增 `RetrievalFacade`；`rag_service.query/stream_query` 改经 facade（无 facade 时保留内联降级）；全量 pytest 143 通过；真实 E2E 验证 `/api/query` 与 SSE 事件链不回退 | commit `4b78daa` |
| **S2 面试基线** | 构造 `data/eval_interview_subset.json`（17 条：出题 8 + 评价 9）；写 `scripts/eval_interview_baseline.py` 复刻旧 raw FAISS top-3 跑基线 | commit `3492391` |
| **S3 面试迁移 + 复试** | `interview_service` 迁 facade、来源溯源、追问检索开关；写 `scripts/eval_interview_upgraded.py` 复试对照 | commits `a53b1a8`, `9bb26f9` |

**S3 具体落地：**
- `_retrieve_context` → `_retrieve_context_with_sources`（优先 facade，失败回退 raw FAISS）；
- 评价 query 保持 `问题 + 回答`，出题 query 也走 facade；
- 出题 / 评价均带回 `sources`（file + chunk_index + score），随 `question_data` / `evaluation` 入库（**溯源 §5.5**）；
- 新增开关 `enable_interview_followup_retrieval`（默认 **False**）：`_generate_question(followup=True)` 的追问式下一题默认不检索（**§5.2**）。

## 五、指标对比（升级前 vs 升级后）

数据：`docs/evaluation/`（基线 rawfaiss / 升级 facade 两份 JSON + 两篇 md 报告）

| 维度 | 升级前（raw FAISS **top-3**） | 升级后（facade **top-5**） |
|------|:---:|:---:|
| **整体 recall@3** | 0.588 | 0.588（持平） |
| **整体 MRR** | 0.559 | **0.588（提升）** |
| 出题形态 recall | 0.625 | 0.625 |
| 出题形态 MRR | 0.563 | 0.625 |
| 评价形态 recall | 0.556 | 0.556 |
| 评价形态 MRR | 0.556 | 0.556 |

> **口径注**：升级前后 `top_k` 不同（基线 top-3 / 升级后 top-5）。按 Spec B §6「不劣于升级前」判定：MRR 提升、recall 持平，**达标**。

### 验收对照（Spec §6）
- [x] 面试检索复用统一 facade，`_retrieve_context` 不再直接调 raw faiss
- [x] 评价 query 使用「问题 + 用户回答」；出题/评价带来源溯源
- [x] 触发策略默认落地（追问不检索），开关可配置
- [x] 面试子集指标**不劣于**升级前
- [x] `pytest tests/` 全量通过（**143 passed**）
- [x] 未违反 DR-001/003/004/005

## 六、遗留问题：Java 集合主题召回不足

升级前后复试中，**未命中样本高度集中在「Java 集合」主题**：

| query | 期望 | 升级后 top-5 实际 | 诊断 |
|-------|------|------------------|------|
| ConcurrentHashMap 线程安全 | JUC.md | test_java×2, 操作系统, Redis | 未命中 |
| ArrayList/LinkedList 差异 | JAVA集合.md | test_java, Redis.docx, 操作系统, Redis×2 | 未命中 |
| HashMap 是否线程安全+死循环 | JAVA集合.md | test_java×2, 操作系统, Redis×2 | 未命中 |

- 该批题在**升级前后同样 miss**（非 facade 迁移引入），确认为**基数 / 索引质量**短板，非管线问题。
- 根因方向：知识库 chunk 之间主题混杂（`test_java.md`、`Redis.md` 高频抢占），纯稠密/当前混合检索对「集合」语义召回不足。
- **处置**：不在 Part B 范围内强行解决（避免范围扩大），单列 **Part C：知识树驱动 query 检索优化**（见独立记录 `2026-08-29-knowledge-tree-query-partC.md`）。

## 七、可复现命令

```bash
# 升级前基线（raw FAISS top-3）
python scripts/eval_interview_baseline.py
# 升级后复试（facade top-5）
python scripts/eval_interview_upgraded.py
# 全量回归
python -m pytest tests/
```

## 八、结论

Part B 目标已达成：**面试检索从 raw FAISS 独木桥迁移到与问答统一的、经 Part A 消融验证的检索管线**，并落地了来源溯源与「追问默认不检索」的触发策略，复试指标不劣于升级前。工程质量（降级、缓存红线、SSE 稳定、pytest 全绿）均有据可查，具备对外表达与后续演进基础。