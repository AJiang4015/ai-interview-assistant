# 检索质量评测闭环：基线→门禁→消融→面试检索升级（Design Spec）

> 状态：已拆分（本文件保留备用；后续执行以下述两个拆分件为准）
> 日期：2026-08-28
> 拆分产物：
> - [Part A：检索评测闭环](2026-08-28-retrieval-eval-closed-loop-partA.md)（建集 → 基线+门禁 → 消融优化）
> - [Part B：面试检索升级](2026-08-28-interview-retrieval-upgrade-partB.md)（统一 facade + 知识点树 query）
>
> 注：本文件原名为 `2026-08-28-retrieval-eval-loop-design.md`，2026-08-28 重命名为 `-closed-loop-design.md` 以对齐命名族。

## 1. 问题描述

项目现状是「RAG 知识库搜索 + AI 模拟面试助手」。经与用户结构性拷问（grill-me）后收敛出以下判断：

1. **北极星错配**：代码里已重投入 JWT 认证、用户隔离、离线评估、OTel 可观测性（产品化/多租户的信号），但实际定位是**单用户自用为主、最终面向求职作品集展示**。多租户/并发是过度投入，应降级为「能跑就行」的支撑。
2. **核心卖点未立住**：产品差异化在于「面试与知识库联动」，但现状 `interview_service.py::_retrieve_context()`（L637-L659）只用 raw FAISS 稠密检索取 top-3，**没有 hybrid / rerank / query rewrite**；且出题时的检索词是 `f"{position} 技术面试题 {difficulty}"` 这类「不是问题的问题」。联动只是形式上连通，质量上裸奔。
3. **最弱一环 = 检索质量、无闭环**：检索管线全开关常开（`query_rewrite / hybrid_search / rerank / parent_expansion` 均为 True，见 `app/config.py` L45-L52），从未做过消融/对照实验，改检索全凭玄学。离线评估模块（`evaluation_service.py` / `eval_testset.py`）虽已存在且挂好 `/api/eval/*` 路由，但**没有门禁、没有可重复命令、没反过来驱动过检索改动**，是「存在但没用」的摆设。
4. **无真实翻车案例**：用户手里没有可用的失败样例，检索诊断无法靠人工案例定位，只能靠「评测集跑基线 → 量化 → 消融」，因此**评测集的质量 = 诊断引擎的质量**。

## 2. 目标（非目标）

**目标**：建立一条「评测集 → 基线 → 门禁 → 消融 → 优化 → 复试」的可重复闭环，先修好统一检索管线，再把面试检索从独木桥迁到这条已验证的管线上。

**非目标**（明确不做，避免过度设计）：
- 不做多用户/并发/成本控制相关投入；
- 不追求 OTel/评估等支撑模块的美观与完备；
- 不在本次做「可展示（demo/README/演示数据）」——按北极星它放最后。

## 3. 影响模块 / 文件

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| 新增：评测集文件（如 `data/eval_testset.json`） | 新增 | 手写刁钻核心集 + LLM 扩展集，含四死亡维度标签 |
| `app/services/eval_testset.py` | 修改 | 保留 LLM 生成逻辑；新增「手写集合并/标注」入口；确保不生成 chunk 反推虚高样本 |
| `app/services/evaluation_service.py` | 修改 | 输出基线报告；recall@k / mrr 作为门禁指标，faithfulness 等辅助 |
| 新增：门禁/消融执行脚本（如 `app/scripts/eval_runner.py`） | 新增 | 一条命令完成：加载测试集 → 逐开关消融 → 输出对比报告 |
| `Makefile` / `pyproject.toml` | 新增配置 | `make eval` 封装可重复命令（闭环物理载体；可选 CI 步骤） |
| `app/services/retrieval_service.py`（统一 facade） | 重构 | 抽 `retrieval facade`，问答/面试共用同一已验证管线 |
| `app/services/interview_service.py` | 修改 | `_retrieve_context` 换用 facade；出题=知识点树 query，评价=问题+用户回答 query |
| `.env.example` / `app/config.py` | 修改 | 增加消融临时开关维度（若需），门禁阈值配置 |
| docs | 新增 | 基线报告 + 消融结论沉淀 |

## 4. 技术方案概要

### 4.1 评测集（混合构造）
- **手写核心集（金标准）**：30 条起，宁缺毋滥，覆盖**四死亡维度**：
  - (a) 跨章节 / 多文档推理（答案需拼 2 个以上文档）——最能戳穿检索虚高；
  - (b) 易混概念辨析（如 ArrayList vs LinkedList 底层差异）；
  - (c) 口语化 / 面试官问法（「你说说线程池呗」）——最贴合真实面试；
  - (d) 边界 / 反直觉问题（「为什么 HashMap 长度是 2 的幂」）。
- **LLM 扩展集**：从手写核心驱动、结合知识库扩到 100~150 条；**禁止直接用 chunk 反推**（那是自问自答，指标虚高）。
- 每条含 `question` / `expected_answer` / `expected_source` / `source_file` / `question_type`(a/b/c/d)。

### 4.2 指标与门禁
- **门禁（客观、可自动化）**：`recall@k`、`mrr`——先跑基线，门禁 = 基线数字 + 可量化提升目标（如基线 recall@3=0.55 → 目标 0.75），**不凭空拍阈值**。
- **辅助（生成层）**：`faithfulness` / `answer_relevance` / `context_relevance` 用 LLM-judge，只做辅助 + 人工抽样；不设自动化门禁（judge 稳定性未校准前不作为硬门禁）。

### 4.3 消融实验（一次只动一个开关）
- 从最可疑 + 最贵的开始：**query rewrite → rerank**，随后 parent expansion → hybrid 的 RRF 权重。
- query rewrite 重点验证：面试题是否被改写成伤了召回；
- rerank 重点验证：是否把真正该回来的文档挤出前 N。
- 产出：每开关开关前后的 recall/mrr 对比表，据实决定留删。

### 4.4 统一检索 facade + 面试升级
- 抽 `retrieval facade`：问答与面试复用同一条已验证管线（hybrid + rerank + query rewrite + parent expansion）。
- **策略差异在 facade 之上**：出题用**知识点树驱动 query**（替代 `"Java 技术面试题 中等"`）；评价用 **「问题 + 用户回答」** 拼接 query。
- 面试升级排在消融之后（不插队）：先修好底座，再移民核心卖点。

### 4.5 封装
- 提供一条可重复命令（`make eval`）完成：建集 → 跑基线 → 消融对比 → 出报告。CLI 与 /api/eval/* 并存，命令侧为闭环主力。

## 5. 验收标准（可勾选清单）

**评测集**
- [ ] `data/eval_testset.json` 含手写核心集（≥30，四维度齐全，每条带类型标签）与 LLM 扩展（合计 100~150）
- [ ] 手写集不使用 chunk 反推生成

**基线与门禁**
- [ ] 一条 `make eval` 命令可重复复现基线数字（recall@k / mrr 分维度统计）
- [ ] 门禁阈值已根据基线落定（非凭空拍），并写入配置/文档

**消融**
- [ ] query rewrite、rerank 各自开关前后的指标对比表产出并沉淀到 docs
- [ ] 据对比结论，保留或关闭对应开关（有证据，非玄学）

**面试联动升级**
- [ ] `interview_service` 出题走知识库真实考点（知识点树 query），评价可溯源到具体文档
- [ ] 面试检索复用统一 facade，不再走 raw faiss 独木桥
- [ ] 升级后面试检索指标不劣于升级前基线（有时间记录佐证）

**回归与铁律**
- [ ] 全管线全开关状态下整体 recall/mrr 不低于优化前基线
- [ ] `python -m pytest tests/` 全部通过
- [ ] 未违反 DECISIONS.md 中 DR-001~DR-010 对应铁律（核心：DR-004 缓存 key 基于原始问题不含 session/轮次；DR-003 重排走 SiliconFlow API；DR-001 管线开关+优雅降级）

## 6. 风险与未知点（需确认）

1. **手写集来源**：用户是否愿意目前就提供真实知识库素材用于构造手写题？若无，先以现有知识库内容构造。
2. **门禁阈值定死时机**：按共识先跑基线再定，但需要一条「基线」的初始产物触发点（本次是否只跑基线？）。
3. **消融的资源成本**：每次消融都调用 LLM/rerank API，成本与时间需可接受；是否限制消融场景子集？
4. **面试检索升级范围**：本次是否一并把「知识点树驱动 query」落地，还是仅迁移到 facade 的复用？——本轮共识为「升级」，但前置依赖知识树结构是否成熟需确认。
5. **LLM-judge 稳定性**：faithfulness 等预设不作硬门禁，是否接受后续出现 judge 漂移需重校准。
6. **执行范围（本次决策）**：用户本轮选择**仅落盘、不动手**。后续开工时按 ①建集 → ②基线+门禁 → ③消融 → ④面试升级 → ⑤可展示 顺序推进。

## 7. 执行顺序（已对齐，供后续开工使用）

① 评测集建设 → ② 基线+门禁 → ③ 消融优化（修检索）→ ④ 面试检索升级（复用统一管线）→ ⑤ 可展示（demo/README）。**不插队**，④ 必须建立在 ①~③ 修好的底线上。
