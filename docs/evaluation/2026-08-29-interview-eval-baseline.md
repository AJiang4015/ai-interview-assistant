# 面试检索升级前基线（Part B S2）

> 状态：已固化（升级前基线，用于 S3 迁移后对照）
> 日期：2026-08-29
> 关联 Spec：[Part B 面试检索升级](docs/superpowers/specs/2026-08-28-interview-retrieval-upgrade-partB.md) §5.4 / §6
> 数据文件：`docs/evaluation/eval_interview_baseline_rawfaiss_top3.json`

---

## 一、目的

在迁移 `interview_service` 到统一 `RetrievalFacade`（S3）之前，用**当前旧链路**对面试场景检索跑一次可复现基线，作为「升级后不劣于升级前」的对照基准（Spec B §6）。

## 二、评测子集

- 文件：`data/eval_interview_subset.json`
- 规模：**17 条**（出题形态 8 + 评价形态 9）
- 两形态定义：
  - **出题形态**：面试官口吻的考点问题（如「说说 JUC 包里的同步工具…」）——对应 `interview_service._generate_question` 的出题检索 query 形态。
  - **评价形态**：「问题 + 用户回答」拼接后追问「判断/补充/纠正」——对应 `interview_service._evaluate_answer` 的评价检索 query 形态。
- 字段：`query` / `expected_answer` / `expected_source` / `source_file` / `sample_type`（§5.4 要求，全部齐备）
- 期望来源覆盖知识库全部主题文档：JUC.md、JAVA集合.md、JVM内存模型.pdf、MySQL.md、Redis.md、Spring.md、计算机网络.md。

## 三、旧链路复刻定义

- 后端：**raw FAISS 稠密检索**（`FaissStore.asearch`，无 hybrid / rerank / query rewrite / parent）
- `top_k = 3`——与 `interview_service._retrieve_context` 现状（`faiss.search(vec, 3)`）一致
- 嵌入模型：`Qwen/Qwen3-Embedding-4B`（硅基流动）

## 四、基线指标

| 维度 | n | recall@3 | MRR |
|------|----|:---:|:---:|
| **总体** | **17** | **0.588** | **0.559** |
| 出题形态 | 8 | 0.625 | 0.563 |
| 评价形态 | 9 | 0.556 | 0.556 |

### 关键观察
- 旧链路（raw FAISS top-3）整体 recall@3 仅 **0.588**、MRR **0.559**——意味着约 **41% 的面试问题在 top-3 内找不到期望来源文档**，这正是 Part B 要解决的核心痛点（面试走 raw FAISS 独木桥、与已验证的主链路脱节）。
- 评价形态 recall 略低于出题形态（0.556 vs 0.625），因「问题+回答」拼接更长、更口语化，raw 稠密匹配更难命中——支持 Spec B §5.3「评价 query 走 facade 完整管线」的必要性。
- 命中项多数以高 mrr=1.0 命中（期望文档排第一），未命中则完全 miss——呈两极化，说明 raw 检索对相关问题是"要么准、要么完全不回"。

## 五、未命中项人工抽查（典型）

| # | 形态 | query(截断) | 期望来源 | top-3 实际 | 诊断 |
|---|------|------------|---------|-----------|------|
| 1 | 出题 | ConcurrentHashMap 怎么做到线程安全 | JUC.md | test_java.md×2, 操作系统 | 期望 JUC.md 未进 top-3；test_java 杂项干扰 |
| 2 | 出题 | ArrayList/LinkedList 底层差异 | JAVA集合.md | Redis.md×3 | 知识库 chunk 主题混杂，raw 检索召回串题 |
| 3 | 评价 | HashMap 是否线程安全+死循环判断 | JAVA集合.md | test_java.md×2, 操作系统 | 同上，HashMap 题被杂项覆盖 |
| 4 | 出题 | 线程池七个核心参数 | JUC.md | (见报告) | 期望进 top-3 但可能被串 |

> 根因方向：raw FAISS 不通稀疏腿、不重排，面试语义与知识库 chunk 措辞错位时召回不足；S3 迁移 facade（hybrid+rerank）预期改善 recall@3。

## 六、对照方式（S3 完成后）

- 用同一 `data/eval_interview_subset.json`、同一评测脚本，把 `_retrieve_context` 换成 `RetrievalFacade.retrieve(top_k=5)` 后重跑，产出 `eval_interview_upgraded_*.json`。
- 判定标准（Spec B §6）：**升级后 recall/mrr 不劣于本基线（0.588 / 0.559）**，并记录运行记录佐证。

## 七、可复现命令

```bash
# 复跑升级前基线（全部 17 条，真实 embedding 检索）
python scripts/eval_interview_baseline.py
# 冒烟（前 N 条）
python scripts/eval_interview_baseline.py --limit 3
```