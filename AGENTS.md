# AGENTS.md — Agent 工作规则 / 项目硬约束（宪法）

> **Agent 宪法**：只保留必须长期遵守、跨任务有效、违反会导致项目不正确的规则。从"项目百科"精简而来（2026-08-28 文档架构整理，见 `docs/superpowers/specs/2026-08-28-docs-architecture-reorg-design.md`）。
> 适用项目：RAG 知识库 / Java 程序员智能面试助手（Interview RAG）。

---

## 0. 文档地图（先判断属于哪一类，再决定落盘位置）

> 硬规则：新增任何文档/内容，**必须先归类再落位，禁止默认追加到本文件**。

| 问题 | 权威文档 |
|------|----------|
| 我该遵守什么硬规则？ | **本文件（AGENTS.md）** |
| 系统怎么组织？技术栈？模块索引？ | `ARCHITECTURE.md` |
| 任务怎么做 / 流程 / 实验 / 验收？ | `PROCESS.md` |
| 为什么这么设计 / 长期决策？ | `DECISIONS.md`（DR-001…） |
| 某层允许 / 禁止做什么？ | `app/*/ *_LAYER.md`（API / SERVICES / STORAGE / UTILS） |
| 哪里有问题？ | `PROBLEM.md` |
| 准备怎么改？ | `docs/superpowers/specs/` |
| 改完实际怎么样？ | `docs/evaluation/` |

---

## 1. 硬规则（长期强制，违反即不正确）

1. **开发 / Debug 前必读 `PROBLEM.md`**：先看 §0 Critical Do/Don't 与 §1 Problem Index，确认不踩已记录规则。
2. **分层边界（Law of Layers）**：新增代码必须落在 `ARCHITECTURE.md` §4 与对应 `*_LAYER.md` 声明的层内，禁止跨层越界（API 不得直连 storage、storage 不得反向依赖 services、utils 不得依赖业务层）。
3. **Layer 契约 DoD**：任何**跨层接口变更、新增模块依赖、异常抛出**的 PR，必须同步更新受影响 `*_LAYER.md`（尤其 Input/Output contract 与 Allowed dependencies），否则不满足 DoD；该规则常驻为 PR 验收项。
4. **代码风格**：Python 3.10+，PEP 8（4 空格、行宽约 100），类 `PascalCase`、模块/函数/变量 `snake_case`、常量全大写；配置一律 `from app.config import settings`，禁止散落魔法常量。
5. **错误与安全**：统一异常经 `app/exceptions.py`，API 层映射状态码；文件操作需路径穿越防护 + 扩展名白名单（md/pdf/docx）+ `~$` 临时文件过滤；前端 `innerHTML` 注入前必须 `escapeHtml()`，Markdown 用 DOMPurify 过滤。
6. **Git 纪律**：一个行为问题一个独立 commit（细节见 `PROCESS.md` §6）。
7. **LLM / 资源约束**：LLM 用百炼 `qwen3.7-max`；Embedding/Rerank 用硅基流动；**禁止引入本地重型模型作主链路**（见下方铁律3）。
8. **新增环境/流程类硬约束**：先归入 `PROCESS.md` 或 `AGENTS.md` 相应小节，避免正文膨胀。

---

## 2. 不可协商的三大铁律 ⛔（浓缩版 + 指向单一事实来源）

> 事实与历史证据始终在 `PROBLEM.md`（§0a 铁律、§0 规则、Appendix 门禁）；本文件只保留最短强制摘要，**不得在此展开细节**，防止两处漂移。

- **⛔ 缓存键铁律（DR-004 / P001）**：`cache.make_key()` 只用原始问题原文，禁止混入 `session_id` / `msg_count` / `username` 等任何可变维度。
- **⛔ 流式会话铁律（DR-005 / P002）**：SSE 处理中禁止修改 `state.sessionId`；内容容器动态获取；切换会话禁止 `abort()` 中断进行中的流。
- **⛔ 本地重型资源铁律（DR-003 / P003/P004）**：重排强制 SiliconFlow API（`Qwen/Qwen3-Reranker-4B`），严禁加载本地 `BAAI/bge-reranker-v2-m3` 等模型。

---

## 3. 环境最低要求

- 后端 Python 3.10+；建议用 Conda 隔离环境。
- 依赖外部服务：Redis（`192.168.127.101:6379`）、百炼 LLM、硅基 Embedding/Rerank；可选 Grafana/OTel。
- 命令 / 启动 / 测试见 `PROCESS.md` §7；架构与模块索引见 `ARCHITECTURE.md`。