# 检索评测闭环：建集 → 基线+门禁 → 消融优化（Design Spec · Part A）

> 由原 Spec《检索质量评测闭环：基线→门禁→消融→面试检索升级》（`2026-08-28-retrieval-eval-closed-loop-design.md`，原文件保留备用）拆分而来。
> 状态：已确认（建集 v0 范围锁定，进入实施）
> 日期：2026-08-28
> 关联：本 Spec 是 [Part B：面试检索升级](2026-08-28-interview-retrieval-upgrade-partB.md) 的**前置条件**——只有本 Spec 的消融结论**达标**（定义见 §7）后才允许启动 Spec B。

## 1. 问题描述

1. **最弱一环 = 检索质量、无闭环**：检索管线全开关常开（`query_rewrite / hybrid_search / rerank / parent_expansion` 均为 True，见 [config.py](../../../app/config.py#L45-L52)），从未做过消融/对照实验，改检索全凭玄学。离线评估模块（`evaluation_service.py` / `eval_testset.py`）虽已存在且挂好 `/api/eval/*` 路由（[evaluation.py](../../../app/api/evaluation.py#L25-L73)），但**没有门禁、没有可重复命令、没反过来驱动过检索改动**，是「存在但没用」的摆设。
2. **无真实翻车案例**：用户手里没有可用的失败样例，检索诊断无法靠人工案例定位，只能靠「评测集跑基线 → 量化 → 消融」，因此**评测集的质量 = 诊断引擎的质量**。
3. **现有 LLM 生成测试集是「自问自答」**：`eval_testset.py`（[L52-L80](../../../app/services/eval_testset.py#L52-L80)）从 chunk 反推问题，检索必然命中，指标天然虚高，测不出真实翻车。

## 2. 目标（非目标）

**目标**：建立「评测集 → 基线 → 门禁 → 消融」的可重复闭环，产出证据化的检索管线优化结论。

**非目标**（明确不做）：
- 不做面试检索升级（属 Spec B）；
- 不做多用户/并发/成本控制架构投入；
- 不追求 OTel/评估模块美观与完备。

## 3. 影响模块 / 文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `data/eval_testset.json`（评测集文件） | 新增 | 手写刁钻核心集 + LLM 扩展集，含四死亡维度标签 |
| `app/services/eval_testset.py` | 修改 | 保留 LLM 生成逻辑；新增「手写集合并/标注」入口；确保不生成 chunk 反推虚高样本 |
| `app/services/evaluation_service.py` | 修改 | 输出基线报告；recall@k / mrr 作为门禁指标，faithfulness 等辅助 |
| `app/scripts/eval_runner.py`（或同等 CLI 入口） | 新增 | **薄封装**：加载测试集 → 基线/消融运行 → 输出对比报告 |
| `Makefile` | 新增 | `make eval` 一条可重复命令（闭环物理载体；可选 CI 步骤） |
| `.env.example` / `app/config.py` | 修改 | 门禁阈值配置（基线跑出后落定） |
| docs | 新增 | 基线报告 + 消融结论沉淀 |

**不改动**：`retrieval_service.py` / `interview_service.py` 的管线结构（消融只通过既有 `enable_*` 开关切换，属运行配置非代码重构；facade 抽取属 Spec B）。

## 4. 技术方案概要

### 4.1 评测集（混合构造）
- **手写核心集（金标准）**：30 条起，宁缺毋滥，覆盖**四死亡维度**：
  - (a) 跨章节 / 多文档推理（答案需拼 2 个以上文档）——最能戳穿检索虚高；
  - (b) 易混概念辨析（如 ArrayList vs LinkedList 底层差异）；
  - (c) 口语化 / 面试官问法（「你说说线程池呗」）——最贴合真实面试；
  - (d) 边界 / 反直觉问题（「为什么 HashMap 长度是 2 的幂」）。
- **LLM 扩展集**：从手写核心驱动、结合知识库扩到 100~150 条；**禁止直接用 chunk 反推**。
- 每条含 `question` / `expected_answer` / `expected_source` / `source_file` / `question_type`(a/b/c/d)。
- **多源标注与多源 recall 语义**（跨文档 a 类题）：`expected_source` 用列表 `[主文档, 副文档, ...]`（`source_file` 保留主文档名）。判定规则（实现于 `eval_metrics.multi_source_hit`，评估入口 `evaluation_service.run`）：
  - **hit**：主文档必须出现在 top-k，**且至少一个副文档也出现**，才记 1.0；
  - **recall@k**：top-k 中命中的期望来源数 / 全部期望来源数；
  - **mrr**：以**主文档**首次出现的排名为准；
  - 单源（字符串）样本不受影响，全部指标退化为原有单源逻辑。

### 4.2 指标与门禁
- **门禁（客观、可自动化）**：`recall@k`、`mrr`——先跑基线，门禁 = 基线数字 + 可量化提升目标（如基线 recall@3=0.55 → 目标 0.75），**不凭空拍阈值**。
- **辅助（生成层）**：`faithfulness` / `answer_relevance` / `context_relevance` 用 LLM-judge，只做辅助 + 人工抽样；judge 稳定性未校准前不作为硬门禁。相关实现须遵循 DR-008（LLM 输出健壮解析：JSON 围栏剥离与非法值兜底，judge 解析失败不阻塞流程）——该条在此作为**辅助指标的实现提醒**，非本 Spec 核心铁律。

### 4.3 消融实验（一次只动一个开关）
- 仅对 **query rewrite** 和 **rerank** 两个开关各做一次「开/关」对比（共 4 次评测运行：两开关 × 开/关），随后视结果决定是否扩展到 parent expansion / RRF 权重。
- query rewrite 重点验证：面试题是否被改写成伤了召回；
- rerank 重点验证：是否把真正该回来的文档挤出前 N。
- 产出：开关前后 recall/mrr 对比表，据实决定留删。

### 4.4 CLI 与现有 `/api/eval/*` 的关系（禁止两套实现）
- `python scripts/eval_runner.py`（及可选包装 `make eval`，有 make 的环境可用）必须是**薄封装**：核心评估逻辑全部复用 `app/services/evaluation_service.py` 与 `app/services/eval_testset.py`，CLI 只负责参数解析、开关矩阵编排与报告落盘。
- `/api/eval/*` 路由保持现状，同样调用上述服务层——**全项目只有一套评估实现**。

### 4.5 成本控制条款
- **消融阶段只用手写核心集（≥30 条）作为测试子集**，不使用全部 100~150 条 LLM 扩展集——控制 LLM/rerank API 的调用次数与时长。
- 消融总评测运行次数受限于 §4.3 的 4 次（两开关 × 开/关），不做全开关矩阵扫描。
- **基线运行使用完整评测集**（手写 + LLM 扩展）——这是基线阶段（一次性、产出基准数字），非消融阶段（反复运行、需控成本），两者成本属性不同。

## 5. 验收标准

**本次交付（建集 v0）**——范围二选一，定为方案 A：
- [x] `data/eval_testset.json` 含手写核心集（≥30 条，四维度齐全，每条带 `question_type` 标签）
- [x] 每条手写样本须包含 `question` / `expected_answer` / `expected_source` / `source_file` / `question_type` **全部字段**，缺失任一字段视为不合格（基线计算 recall/mrr 依赖 `expected_source`，生成层评估依赖 `expected_answer`）
- [x] 手写集不使用 chunk 反推生成
- [x] LLM 扩展集**生成代码就绪**（`eval_testset.py` 入口可用、可被 dry-run 验证），但**本次不实际调用 LLM 生成扩展集**（避免成本；扩展集 100~150 条留待基线阶段前补齐）
- 说明：如需 smoke test（实跑生成 30~50 条验证生成质量），属**可选动作**、不计入本次交付，由用户开工时另行决定。

**后续阶段交付（基线 / 门禁 / 消融）**
- [ ] 一条 `python scripts/eval_runner.py` 命令（或 `make eval`，在有 make 的环境）可重复复现基线数字（recall@k / mrr 分维度统计），基线用完整评测集
- [ ] 门禁阈值已根据基线落定（非凭空拍），写入配置/文档
- [ ] query rewrite、rerank 各自开关前后的指标对比表产出并沉淀到 docs（消融仅用手写核心集）
- [ ] 据对比结论，保留或关闭对应开关（有证据，非玄学）
- [ ] CLI 为薄封装，评估核心逻辑复用 `evaluation_service.py` / `eval_testset.py`，无第二套实现

**回归与铁律**
- [ ] `python -m pytest tests/` 全部通过
- [ ] 未违反 `DECISIONS.md` 对应铁律，具体为：
  - **DR-004**（缓存/去重 key 基于不变语义，只用原始问题原文，禁止混入 session_id / msg_count / username——消融与基线运行不得触碰缓存 key 逻辑）
  - **DR-003**（重排必须走 SiliconFlow `Qwen/Qwen3-Reranker-4B` API，禁止本地 `BAAI/bge-reranker-v2-m3`）
  - **DR-001**（管线各模块保持 `enable_*` 开关 + 依赖失败优雅降级——消融依赖此开关机制）
- 辅助指标（faithfulness 等 LLM-judge）的实现遵循 **DR-008**（LLM 输出健壮解析，见 §4.2），不单列为核心铁律。

## 6. 风险与未知点

1. **手写集来源**：用户需提供或确认以现有知识库内容构造手写题。
2. **门禁阈值定死时机**：须先有基线产物再落阈值；本次交付若止步于建集 v0，阈值延后。
3. **LLM-judge 稳定性**：faithfulness 等预设不作硬门禁，后续可能出现 judge 漂移需重校准。
4. **消融成本**：即便限于手写集 + 4 次运行，仍含 Embedding/Rerank API 调用；若不可接受，可进一步缩小子集（但手写集 <20 条时统计意义存疑，需明示）。

## 7. 执行顺序与「达标」定义

① 建集 v0（手写 30 条 + 生成代码就绪，不实跑 LLM）→ ② 基线（完整评测集，`python scripts/eval_runner.py` 可复现，有 make 的环境可用 `make eval`）→ ③ 门禁落定 → ④ 消融（仅手写核心集，query rewrite / rerank 各一次开关对比）→ ⑤ 结论沉淀并驱动管线配置修改。

**「消融结论达标」的硬定义**（Spec B 的启动准入条件）：
1. 基线数字已明确（完整评测集、可复现）；
2. 消融阶段已给出 query rewrite / rerank 两个开关的**明确决策**（保留或关闭）；
3. 消融后（按决策配置的管线）整体 recall/mrr **不劣于基线**；若某开关被证明显著有害，则**必须关闭**该开关。

三条同时满足即视为达标，可启动 [Spec B](2026-08-28-interview-retrieval-upgrade-partB.md)。
