# P003 — 本地重排模型资源失败（OMP 崩溃 + 下载失败），改走远程 API

> 本档案合并 P003 与 P004 两条同源问题，保留各自历史 ID 以便追溯（commit / spec / 面试材料引用不失效）。

## Status

- ID：P003（主记录）；P004（合并来源，历史 ID 保留）
- Severity：P003 High；P004 Medium
- Status：Resolved（弃用本地模型，改 SiliconFlow API）
- First identified：重排能力接入迭代期间
- Related Decision：DR-003（重排强制 SiliconFlow API，禁止本地 bge-reranker）
- Related Spec：`docs/superpowers/specs/2026-08-12-rag-pipeline-upgrade-design.md`
- Related Tests：Door 6（禁用本地 bge-reranker 静态检查，未自动化）

---

## 1. Problem

- **P003**：加载本地 `BAAI/bge-reranker-v2-m3` 触发 **OMP 运行库冲突**（`libiomp5md.dll` ↔ `libomp140.x86_64.dll`）导致**进程崩溃**——系统级不可用，而非单请求失败。
- **P004**：同一模型需从 **HuggingFace 下载**，国内网络环境下下载失败，模型不可用。

## 2. Impact

- P003：进程崩溃影响**所有依赖重排的 RAG 问答请求**（重排开启时全量走该路径），属 Feature 中断级别。受影响请求占比与崩溃时长需结合当时部署节点与开关状态估算（当前无崩溃期运行数据，见 §9 局限）。
- P004：网络下载失败导致本地重排无法落地，属于部署阻断。

## 3. Evidence

- P003：加载 `BAAI/bge-reranker-v2-m3` 时 OMP 动态库冲突崩溃（`libiomp5md.dll` ↔ `libomp140.x86_64.dll`）。
- P004：HuggingFace 国内网络不可达，模型下载失败。
- 修复证据：配置切换为 SiliconFlow `Qwen/Qwen3-Reranker-4B` API（未定位独立 commit，随重排服务改造落地）。

## 4. Root Cause

- P003：本地可执行模型依赖共享动态库（OMP），与运行环境其他库冲突——"地雷型"本地重型资源。
- P004：模型权重托管于需外网访问的 HuggingFace，国内网络环境不可达。
- 共同根因：**把依赖外网下载、且携带本地动态库冲突风险的模型作为主链路组件**，环境一变化即不可用。

## 5. Decision / Solution

- **决策（DR-003）**：重排强制走 **SiliconFlow API（`Qwen/Qwen3-Reranker-4B`）**，严禁加载本地 `BAAI/bge-reranker-v2-m3` 等需外网下载或含 OMP 冲突的模型。
- 取舍：远程 API 有延迟与按量成本，但稳定可落地、免本地资源雷区；对主链路可用性收益远大于成本。

## 6. Implementation

`app/services/rerank_service.py` 改为调用 SiliconFlow Rerank API；配置 `rerank_model = "Qwen/Qwen3-Reranker-4B"`（`app/config.py`）。

## 7. Regression / Verification

- 重排链路在真实环境可用（本地 smoke 验收通过，见 `docs/evaluation/2026-08-29-local-smoke-acceptance.md`）。
- 建议（未落地）：`rerank_backend_ready`（0/1）指标 + 进程崩溃探针，同类"地雷型本地资源"加载失败时第一时间告警（对应 [AUGMENT] 铁律 2 的监控化）。

## 8. Current Status

Resolved。DR-003 作为高压线持续维护于 `AGENTS.md` 铁律 3 与 `SERVICES_LAYER.md` 不变量。

## 9. Lessons

- 分布式 / 远程环境默认禁止"地雷型"本地重型资源（本地可执行模型、需外网下载的依赖、共享动态库）——已抽象为 [AUGMENT] 铁律 2。
- 影响面量化缺口：P003 的崩溃影响面（时长 / 请求占比）无运行数据，属于知识库记录的历史局限；未来同类问题应补监控指标。

## 10. Historical Record

- P004 状态在注册表中保持为 `Merged → P003`，指向本档案。
- Do Not Reopen Without Evidence：若重排再次引入本地模型，先确认是否违反 DR-003；不要在不解决下载 / 动态库冲突的前提下回退本地方案。
