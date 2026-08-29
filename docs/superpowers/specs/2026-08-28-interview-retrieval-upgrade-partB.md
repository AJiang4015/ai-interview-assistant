# 面试检索升级：统一检索 facade + 知识点树 query（Design Spec · Part B）

> 由原 Spec《检索质量评测闭环：基线→门禁→消融→面试检索升级》（`2026-08-28-retrieval-eval-closed-loop-design.md`，原文件保留备用）拆分而来。
> 状态：待确认（**不可立即启动**，前置条件见 §2）
> 日期：2026-08-28
> 关联：前置 Spec 为 [Part A：检索评测闭环](2026-08-28-retrieval-eval-closed-loop-partA.md)。

## 1. 问题描述

核心卖点「面试与知识库联动」现状是**形式上连通、质量上裸奔**：

1. `interview_service.py::_retrieve_context()`（[L637-L659](../../../app/services/interview_service.py#L637-L659)）只用 raw FAISS 稠密检索取 top-3，**没有 hybrid / rerank / query rewrite**——面试走的是与问答主链路不同的「独木桥」。
2. 出题时的检索词是 `f"{position} 技术面试题 {difficulty}"` 这类「不是问题的问题」（[interview_service.py](../../../app/services/interview_service.py#L543-L544)），检索语义与知识库内容严重错位。

## 2. 前置条件（显式章节，不满足则本 Spec 不启动）

1. **Spec A 的消融结论达标**：只有 [Part A](2026-08-28-retrieval-eval-closed-loop-partA.md) §7 定义的「达标」三条全部满足（基线数字明确可复现；query rewrite / rerank 两开关有明确去留决策；消融后整体 recall/mrr 不劣于基线、显著有害的开关已关闭），才允许启动本 Spec。**「面试检索升级排在消融之后」**——先修好底座，再迁移核心卖点，不插队。
2. **知识点树驱动 query 的成熟度**：知识点树必须**已有成熟实现**（能稳定输出查询词，而非 `knowledge_tree_structure` 的摆设性拼接）。**否则本次只做「迁移到统一 facade」，不做 query 改造**——query 改造（知识点树驱动）推迟到知识树能力成熟后另行迭代。降级与否的决策点见 §7 风险 1。

## 3. 目标（非目标）

**目标**：
- 抽统一 `retrieval facade`，问答与面试复用同一条已被 Spec A 验证过的管线（hybrid + rerank + query rewrite + parent expansion，按消融结论配置开关）；
- 面试出题检索 query 改造为知识点树驱动（受前置条件 2 约束，可能降级为仅迁移 facade）；
- 面试评价 query 使用「问题 + 用户回答」拼接——这是面试链路与问答链路**真正不同的地方**，在 facade 之上做策略差异；
- 评价/报告输出中保留检索来源引用（文档名 + chunk 定位），支持面试者回查（见 §5.5）。

**非目标**：
- 不重做评测闭环（属 Spec A）；
- 不做多用户/并发投入；
- 不做「可展示（demo/README）」——按北极星它放最后。

## 4. 影响模块 / 文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `app/services/retrieval_service.py`（统一 facade） | 重构 | 抽 retrieval facade：问答 / 面试共用同一条已验证管线，策略差异在 facade 之上 |
| `app/services/interview_service.py` | 修改 | `_retrieve_context()` 换用 facade；出题 query、评价 query 按策略改造 |
| `app/services/rag_service.py` | 微调 | 问答链路改为经 facade 调用（行为不变，仅收口） |
| `app/main.py` | 微调 | facade 装配（如需调整服务初始化顺序） |
| `app/config.py` + `.env.example` | 修改 | 新增面试检索触发策略开关（见 §5.2） |
| `data/eval_interview_subset.json`（面试评测子集） | 新增 | 10~20 条面试场景检索样本（见 §5.4） |
| tests/ | 新增/修改 | 面试检索走 facade、触发策略的回归用例 |

## 5. 技术方案概要

### 5.1 统一 retrieval facade
- facade 封装「query rewrite → hybrid（RRF, k=60）→ rerank → parent expansion」完整管线，开关状态以 Spec A 消融结论为准；
- 问答与面试**管线之下完全复用**，facade 之上做策略差异（不同 query 构造、不同 top-k 需求）。

### 5.2 面试侧检索触发策略（默认决策，非「评估后定」）
**默认策略：面试追问环节（最多 5 层）不触发真实检索**，仅使用当前会话内已检索到的上下文；**出题与最终评价各触发一次真实检索**。即单场面试的检索调用次数 ≈ 题目数 × 2，与追问深度无关。
- 通过 `enable_interview_followup_retrieval`（默认 False）开关控制：置 True 时追问层也走真实检索（供实验对比，受成本约束）。
- 若引入缓存，**只复用现有 `cache_service`，key 仍仅基于原始问题原文**（DR-004），不新增以「问题+回答」为 key 的缓存维度。

### 5.3 面试侧 query 策略（facade 之上）
- **出题 query**：知识点树驱动（先定位考点，再检索考点内容），替代现状 `f"{position} 技术面试题 {difficulty}"`；**前置条件 2 不满足时本项跳过**，仅沿用现有 query 迁移到 facade。
- **评价 query**：「问题 + 用户回答」拼接检索，定位「答错的点对应文档哪段」。

### 5.4 面试场景评测子集（不复用通用集作为唯一依据）
- 通用问答评测集（Spec A 产物）不能完全代表面试场景的两类 query（出题 query / 评价 query 的口语化与开放性），因此**新增小型面试评测子集**：10~20 条，含 (i) 面试官问法样本（对应出题 query 形态）、(ii)「问题+真实回答」样本（对应评价 query 形态）；
- 构造方式沿用 Spec A 手写标准（禁止 chunk 反推）；**每条须包含 `query`（面试官问法或「问题+回答」拼接）/ `expected_answer` / `expected_source` / `source_file` / `sample_type`(出题形态/评价形态) 全部字段，缺失任一字段视为不合格**；
- 规模小、不追求统计显著，定位为**方向性验证**：facade 迁移与 query 改造在面试形态 query 上不劣于升级前；
- 通用集仍作为回归底座（验证 facade 收口对问答主链路无回退）。

### 5.5 溯源
- 评价 / 报告输出中保留检索来源引用（文档名 + chunk 定位），面试者可回查。

## 6. 验收标准

- [ ] `interview_service` 出题走知识库真实考点（知识点树 query），评价可溯源到具体文档【前置条件 2 满足时】
- [ ] 或（前置条件 2 不满足的降级路径）：面试检索已迁移至统一 facade，query 沿用现状，行为不回退
- [ ] 面试检索复用统一 facade，`_retrieve_context` 不再直接调用 raw faiss
- [ ] 评价 query 使用「问题 + 用户回答」拼接
- [ ] 面试评测子集（10~20 条，字段完整性符合 §5.4 要求）构造完成，升级后在该子集上指标不劣于升级前（有运行记录佐证）
- [ ] 问答链路经 facade 收口后，`/api/query`（含 stream）在通用评测集上指标与行为无回退
- [ ] 面试检索触发策略按 §5.2 默认值落地（追问不检索），开关可配置
- [ ] `python -m pytest tests/` 全部通过
- [ ] 未违反 `DECISIONS.md` 对应铁律，具体为：
  - **DR-001**（管线开关可配置 + 依赖失败优雅降级：facade 内任一环节失败不得阻塞面试主线，应降级回退）
  - **DR-003**（重排走 SiliconFlow `Qwen/Qwen3-Reranker-4B`，禁止本地 reranker 模型）
  - **DR-004**（缓存 key 基于不变语义，仅原始问题原文——面试链路不得引入含用户回答的缓存 key）
  - **DR-005**（SSE 事件协议不变；若 facade 改动影响 `retrieval` 事件结构需同步前端并回归）

## 7. 风险与未知点

1. **知识树降级决策点（需用户 Review 拍板）**：若验证发现知识点树不成熟，存在两条路线——
   - **路线甲**：接受「仅迁移 facade」作为中间交付物（基础设施先行，出题 query 质量暂不改善，核心卖点改进打折）；
   - **路线乙**：本 Spec 必须包含知识点树 query 完整实现——则先另立一个小 Spec 解决知识点树的查询词输出能力，再回来做完整升级。
   **默认路线甲**（符合「不插队」纪律与渐进交付），但该决策需用户在 Spec A 达标、知识树成熟度验证后显式确认。
2. **面试检索成本**：已按 §5.2 给出默认策略（追问不检索）控制为 题目数×2 次调用；若实测延迟/费用仍不可接受，再评估进一步收缩（如最终评价才检索）。
3. **facade 重构波及面**：`rag_service.py` 收口属行为等价重构，但 SSE `retrieval` 事件结构若有变化需前端联动回归（关联 PROBLEM.md P002 / D1~D3 流式铁律）。
4. **面试评测子集的说服力**：10~20 条仅方向性验证，若出现指标波动难以归因，需扩充子集或人工抽查定性。
5. **验收依赖 Spec A 产物**：基线数字、手写集标准均来自 Part A，Part A 未达标时本 Spec 的验收项无法执行。

## 8. 执行顺序

1. 确认 Spec A 消融结论达标（按 Part A §7 硬定义做准入检查）；
2. 验证知识点树成熟度 → 决定走完整升级（路线乙）还是降级路径（路线甲，需用户确认）；
3. 抽 facade 并将问答链路收口（行为等价回归，通用评测集验证）；
4. 构造面试评测子集（10~20 条），记录升级前指标；
5. 面试链路迁移 facade + 触发策略落地 + 评价 query 改造（+ 知识点树 query，视路线）；
6. 用面试评测子集 + 通用集复试，对照升级前数字出结论。
