# 面试表达材料包（Interview Presentation Kit）

> 定位：把 Part A/B 的工程成果整理成可面试表达的材料。
> 日期：2026-08-29

## 内容清单

| 材料 | 文件 | 用途 |
|------|------|------|
| 3~5 分钟项目介绍（含 10s 电梯版） | [project-intro-3min.md](project-intro-3min.md) | 开场自我介绍 / 项目深挖主线 |
| 系统架构图（SVG） | [architecture.svg](architecture.svg) | 讲清检索底座 + 问答/面试消费链路 |
| 架构说明（配图口述版） | [architecture.md](architecture.md) | 口述架构、落脚 RetrievalFacade |
| 关键技术决策说明 | [key-decisions.md](key-decisions.md) | 被追问"为什么/怎么权衡"的弹药库 |
| 为何暂缓知识树 query + Part C | [../evaluation/2026-08-29-knowledge-tree-query-partC.md](../evaluation/2026-08-29-knowledge-tree-query-partC.md) | 体现范围控制 / 工程纪律 |
| Part B 完整复盘 | [../evaluation/2026-08-29-partB-retrieval-upgrade-review.md](../evaluation/2026-08-29-partB-retrieval-upgrade-review.md) | 深度复盘 / 面试官深挖 |

## 建议讲述动线（3~5 分钟）

1. **一句话定位**（10s）→ 2. **为什么做 / 痛点**（检索质量没人管）→
3. **最重要的两件事**（消融实验定基线；统一检索门面复用）→
4. **工程化细节**（缓存红线 / 降级 / 流式稳定 / 成本开关）→
5. **一句话收尾强调"用证据做决策"**。

## 关联源码 / 证据

- 统一检索门面：`app/services/retrieval_facade.py`
- 评测闭环：`scripts/eval_runner.py`、`data/eval_testset.json`
- 面试检索基线/复试：`scripts/eval_interview_{baseline,upgraded}.py`、`data/eval_interview_subset.json`
- 评测报告：`docs/evaluation/*.json`
- 技术决策：`DECISIONS.md`（DR-001~DR-010）
- 已知问题：`PROBLEM.md`（注册表：P001/P002/P003… + Door 门禁）+ `docs/problems/`（P001/P002/P003/P005/P006 完整档案）