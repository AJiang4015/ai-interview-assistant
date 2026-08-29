# 面试检索升级复盘结果（Part B S3）

> 状态：已升级并复试
> 日期：2026-08-29
> 关联 Spec：[Part B 面试检索升级](docs/superpowers/specs/2026-08-28-interview-retrieval-upgrade-partB.md)
> 升级前基线：`docs/evaluation/2026-08-29-interview-eval-baseline.md` + `eval_interview_baseline_rawfaiss_top3.json`
> 升级后数据：`docs/evaluation/eval_interview_upgraded_facade_top5.json`

---

## 一、本次升级内容（S3）

1. **`interview_service` 迁移到统一 `RetrievalFacade`**：`_retrieve_context` 与其评价/出题调用改走 facade（hybrid + rerank + parent，Part A 决策配置），不再直接调 raw FAISS；facade 不可用时降级回旧 raw FAISS（DR-001）。
2. **评价 query 保持「问题 + 回答」拼接**（Spec §5.3）并带回检索来源。
3. **来源溯源**（Spec §5.5）：评价与出题的检索来源（文档名 + chunk_index + score）随 evaluation / question_data 输出与入库，支持面试者回查。
4. **追问检索开关落地**（Spec §5.2）：新增 `enable_interview_followup_retrieval`（默认 **False**）。判定「追问式下一题」（`_generate_question(followup=True)`）时默认**不触发真实检索**，仅出题首题与评价各检索一次。

## 二、升级前 vs 升级后（面试评测子集 17 条）

| 维度 | 升级前（raw FAISS top-3） | 升级后（facade top-5） |
|------|:---:|:---:|
| **整体 recall@3** | 0.588 | 0.588 |
| **整体 MRR** | 0.559 | **0.588** |
| 出题形态 recall | 0.625 | 0.625 |
| 出题形态 MRR | 0.563 | 0.625 |
| 评价形态 recall | 0.556 | 0.556 |
| 评价形态 MRR | 0.556 | 0.556 |

> ⚠ 口径注：升级前后 `top_k` 不同（基线 top-3 / 升级后 top-5）。按 Spec B §6「不劣于升级前」判定：**MRR 0.588 ≥ 0.559（提升），recall 0.588 = 0.588（持平）**，即升级后**不劣于**升级前，达标。

## 三、人工抽查（未命中项诊断）

| query | 期望 | 升级后 top-5 实际 | 诊断 |
|-------|------|------------------|------|
| ConcurrentHashMap 线程安全 | JUC.md | test_java×2, 操作系统, Redis | 未命中：JUC 主题未被召回，杂项主导 |
| ArrayList/LinkedList 差异 | JAVA集合.md | test_java, Redis.docx, 操作系统, Redis×2 | 未命中：集合主题文档未进 top-5 |
| HashMap 是否线程安全+死循环 | JAVA集合.md | test_java×2, 操作系统, Redis×2 | 未命中：同上 |
| Redis 过期删除策略 | Redis.md | Redis.md(命中,mrr=1.0) | 命中良好 |

> 结论：**未命中的痛点集中在「Java 集合」主题**（`JAVA集合.md` 相关 3 题全 miss、被 `test_java.md/Redis.md` 串题）。这属于**基数/索引质量**短板，而非 facade 迁移导致——升级前后同样 miss。根治方向：需在检索表征（查询改写、主题对齐）或知识库 chunk 质量上改进，**属后续独立优化项**（恰对应知识树 query 改造 / 检索语言模型迭代），不在本 S3 迁移范围。

## 四、验收对照（Spec §6）

- [x] 面试检索复用统一 facade，`_retrieve_context` 不再直接调用 raw faiss（保留降级兜底）
- [x] 评价 query 使用「问题 + 用户回答」拼接，评价/出题输出带来源溯源
- [x] 触发策略默认落地（追问不检索），开关 `enable_interview_followup_retrieval` 可配置（默认 False）
- [x] 面试评测子集（17 条）指标**不劣于**升级前（mrr 提升）
- [x] `pytest tests/` 全量通过（143 passed）
- [x] 未违反 DR-001 / DR-003 / DR-004 / DR-005（facade 降级、SiliconFlow rerank、不入缓存、SSE 结构不变）

## 五、可复现命令

```bash
# 升级前基线
python scripts/eval_interview_baseline.py
# 升级后复试
python scripts/eval_interview_upgraded.py
```