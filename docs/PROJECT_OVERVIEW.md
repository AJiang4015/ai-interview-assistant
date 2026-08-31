# 项目概览（已归档 / Deprecated）

> **本文档已由 [ARCHITECTURE.md](../ARCHITECTURE.md) 取代**（2026-08-28 文档架构整理，见 `../docs/superpowers/specs/2026-08-28-docs-architecture-reorg-design.md`）。
> 不再维护正文，仅作导航。请前往以下权威文档：

**项目一句话**：用"知识库检索增强 LLM 生成"，做一款 Java / 后端程序员面试助手。

## 导航

- 系统架构 / 数据流 / 依赖方向 → [ARCHITECTURE.md](../ARCHITECTURE.md)
- 技术栈（唯一事实来源）→ [ARCHITECTURE.md](../ARCHITECTURE.md) §2
- 模块 / 目录索引 → [ARCHITECTURE.md](../ARCHITECTURE.md) §5
- 分层契约（各层负责什么 / 禁止什么）→ [app/api/API_LAYER.md](../../app/api/API_LAYER.md) · [app/services/SERVICES_LAYER.md](../../app/services/SERVICES_LAYER.md) · [app/storage/STORAGE_LAYER.md](../../app/storage/STORAGE_LAYER.md) · [app/utils/UTILS_LAYER.md](../../app/utils/UTILS_LAYER.md)
- 开发 / 修复 / 实验 / 验收流程 → [PROCESS.md](../PROCESS.md)
- 长期技术决策（DR）→ [DECISIONS.md](../DECISIONS.md)
- 已知问题注册表（索引 + 档案）→ [PROBLEM.md](../PROBLEM.md) · [docs/problems/](problems/)
- 历史设计 spec / 实现计划 → [docs/superpowers/specs](superpowers/specs/) · [docs/superpowers/plans](superpowers/plans/)
- 评估报告 → 按 `PROCESS.md` §3/§1 落盘到 `docs/evaluation/`（目录按需创建）
- 部署与排障 → [docs/docker-deploy-notes.md](docker-deploy-notes.md)
- 可观测性部署 → [docs/observability/](observability/)

> 历史正文（技术栈 / 目录结构 / 数据流等）已迁入 `ARCHITECTURE.md`，如需查看旧版本请查阅 git 历史。