# PROBLEM.md — Problem Registry / Index（问题注册表）

> **定位：Problem Registry / Index，不是 Problem Encyclopedia。**
> 本文件只负责问题的**注册、状态与导航**：ID、Severity、Status、一句话摘要、关联 DR / Spec / Test、修复证据与链接。
> 重大 / 重要问题的完整调查过程（Investigation / Evidence / Root Cause / Solution / Regression / History）一律在 **`docs/problems/Pxxx-*.md`**，本文件**禁止复制完整正文**。
> 适用项目：RAG 知识库 / Java 程序员智能面试助手（Interview RAG）。

---

## 0. 使用说明（Agent 必读）

- Debug / 开发前先看 §1 Problem Index 与 §4 高频规则，确认不踩已记录规则。
- 遇到现象时，先按对应 `docs/problems/` 档案的 Evidence / Root Cause 定位，不要盲目改代码。
- 解决非 trivial 问题后：更新本注册表状态 + 在对应 Problem Record 追加（不覆盖已确认的历史事实）。
- 若某 resolved 问题再次出现，先确认是否为代码回退、环境变化、输入变化或新 reproduction，**不得直接重复旧修复**。
- 新增 Problem 判定：达到"重大 / 重要"标准（Severity High / 长期影响 / 支撑 DR / 可复用教训 / 解释现状 / 独立回归价值）→ 建 `docs/problems/Pxxx-*.md`；一次性小问题只在 §1 留摘要行。

---

## 1. Problem Index

| ID | Severity | Status | 一句话摘要 | 关联 DR | 关联 Spec / Test | 详细档案 |
|----|----------|--------|-----------|--------|------------------|----------|
| P001 | High | **Resolved**（`e41788e`） | 响应缓存 key 混入 session_id/msg_count，命中率趋近 0；已改为仅原始问题 + 6 回归测试 | DR-004 | Door 5；`tests/services/test_cache_service.py` | [P001-cache-key.md](problems/P001-cache-key.md) |
| P002 | High | Resolved（`55a654f`） | 前端 SSE 流式输出在会话切换后中断/写错会话；多根因，已固化 D1–D4/D11 | DR-005 | Door 2/3/4/11 | [P002-sse-session.md](problems/P002-sse-session.md) |
| P003 | High | Resolved | 本地 bge-reranker 加载触发 OMP 崩溃；改走 SiliconFlow API | DR-003 | Door 6 | [P003-local-reranker-resource-failure.md](problems/P003-local-reranker-resource-failure.md) |
| P004 | Medium | **Merged → P003** | 本地 reranker 需 HuggingFace 下载，国内网络失败；与 P003 同源解决 | DR-003 | 见 P003 | 见 P003 档案 |
| P005 | Medium | Resolved（`d42b7bf`） | Markdown 渲染未生效（textContent 而非 innerHTML）；改走 marked→DOMPurify 安全链 | DR-009 | Door 10 | [P005-markdown-render.md](problems/P005-markdown-render.md) |
| P006 | High | **Active**（约束固化） | 索引陈旧 state / 单 worker 落盘约束；约束已固化，多 worker 进程级锁未实现 | DR-002 | Door 9；索引幂等重建测试 | [P006-single-worker-persistence.md](problems/P006-single-worker-persistence.md) |
| P007 | High | Resolved（`1913f75`） | `monitor` 变量遮蔽导致 OTel 上报崩溃 | — | — | （摘要级） |
| P008 | Medium | Resolved（`45746e1`/`bbb04a5`） | 评测服务未初始化 / 评测 JSON 解析脆弱；已加固 | DR-008 | Door 14 | （摘要级） |
| P009 | Medium | Resolved（`0e1b3b8`） | split_text/_save_state 异常未隔离，单块失败拖垮整批 | — | Door 8 | （摘要级） |
| P010 | Low | Resolved（`25d694f`） | 未知稀疏检索后端未显式降级 memory | — | Door 7 | （摘要级） |
| P011 | Medium | Resolved（`99a78cd` 等） | 幻觉计量双记录 / 向量查询计数缺失 / 流式 usage 覆盖 | — | — | （摘要级） |
| P012 | Low | Resolved（`c921596`） | rebuild 分支 `_save_state` 无异常保护 | — | Door 8 | （摘要级） |
| P013 | Info | Historical | 【历史遗留】koa-connect 包装导致 ctx.state 丢失；不适用当前 FastAPI 栈 | — | — | （Git history 可查） |

> 说明：P007–P013 为一次性 / 低复用价值问题，仅在注册表保留摘要行；详细修复证据见对应 git commit。P001–P006 为重大 / 重要问题，完整生命周期见 `docs/problems/`。

---

## 2. Active Problems

| ID | Severity | 摘要 | 缺口 |
|----|----------|------|------|
| P006 | High | 单 worker 落盘约束（DR-002） | 规则已固化、幂等重建测试已有；**多 worker 并发进程级锁未实现**，当前靠部署纪律（`--workers 1`）保证 |

> 当前无 `investigating` 状态问题。

---

## 3. Resolved Problems（摘要）

| ID | 摘要 | 关键提交 |
|----|------|----------|
| P001 | 缓存 key 仅原始问题，跨会话可命中；6 个回归用例 | `e41788e` |
| P002 | SSE 流式跨会话稳定；固化 D1–D4/D11 | `55a654f` |
| P003 | 本地 reranker 弃用，改 SiliconFlow API | 配置变更（随重排改造落地） |
| P004 | 与 P003 同源解决（Merged） | 见 P003 |
| P005 | Markdown 走 marked→DOMPurify 安全渲染链 | `d42b7bf` |
| P007 | monitor 遮蔽修复 | `1913f75` |
| P008 | 评测服务 lifespan 初始化 + JSON 围栏解析加固 | `45746e1`、`bbb04a5` |
| P009 | 分块/保存异常隔离 | `0e1b3b8` |
| P010 | 稀疏后端显式降级链 | `25d694f` |
| P011 | 幻觉计量去重 / 计数补齐 | `99a78cd`、`ca6150e`、`c187837` |
| P012 | rebuild 保存异常保护 | `c921596` |
| P013 | 历史遗留（不适用当前栈） | 未定位 commit |

---

## 4. 高频规则（Critical Do / Don't — 浓缩护栏）

> 违反任意一条大概率踩中已记录问题；完整分析见对应 `docs/problems/` 档案。

| # | 规则 | 对应问题 |
|---|------|----------|
| D1 | 会话切换时不得清除进行中的 SSE 流、不得调用 `abort()`，让请求自然完成 | P002 |
| D2 | SSE 事件中不得修改 `state.sessionId`，只更新 `finalSessionId`；token 按发起时的会话 ID 追加 | P002 |
| D3 | 经流式 contentDiv 必须动态获取，不得在 `sendQuestion` 里持有到局部变量后跨会话使用 | P002 |
| D4 | 删除当前会话后不自动新建会话；有进行中流的会话被删除时保留数据结构，让流自然收尾写入 | P002 |
| D5 | 响应缓存 key 必须基于原始用户问题，保证相同查询命中；不要用 `session_id` / 消息序数混进 key | P001 |
| D6 | 重排必须走 SiliconFlow `Qwen/Qwen3-Reranker-4B`，禁止引入本地 `BAAI/bge-reranker-v2-m3` | P003 |
| D7 | RAG 各模块（查询改写/混合检索/重排/缓存）都要有 `enable_*` 开关，且依赖失败**优雅降级**（Redis 不可用→禁用缓存；BM25 缺失→退回 FAISS-only） | P006/P009/P010 |
| D8 | LLM/索引相关改动必须**通过测试与状态隔离**；`split_text` / `_save_state` / `indexing` 的异常要隔离，不能因单个 chunk 失败拖垮整批 | P009 |
| D9 | 运行态全局（`state`、FAISS/index 落盘）假定**单 worker**；不要擅自改成多 worker 而不补进程级锁 | P006 |
| D10 | 前端 `innerHTML` 注入前必须做 HTML 转义；Markdown 渲染用 DOMPurify 过滤，CDN 加载失败回退纯文本 | P005 |
| D11 | 流式 DOM 更新需节流（rAF + pendingRender，token 事件间隔 ≥50ms），完成/错误/终止时取消待处理 rAF 做最终完整渲染 | P002 |
| D12 | `.env` / `config.py` 修改后需**重启 backend**（`Settings()` 在 import 时一次性读取） | P001/P011 |
| D13 | 数据库/存储清理类操作需防误删：知识库文件名做路径穿越防护与扩展名白名单；聊天记录计数先清空再追加避免重复 | P001 |
| D14 | LLM 生成、parse、judge 的输出必须做健壮解析（JSON 围栏剥离、非法值兜底），失败不阻塞主流程 | P008 |

---

## 5. Appendix: Gatekeeper Checks（门禁映射）

> 将 §4 的 D1–D14 规则升级为"机器可执行"门禁（Pytest / Lint / E2E），把"请遵守"变成"会被 CI 拦住"。文件名仅为建议，落地时以真实测试模块为准。标注 **[REQUIRES MANUAL INPUT]** 表示需人工补数据/接线后才可落地。

| Door | 关联规则 | 建议门禁（Pytest / Lint / E2E） | 落地状态 |
|------|----------|-------------------------------|----------|
| Door 1 | D1（不得 abort 进行中流） | 前端 E2E：发起 SSE 流 → 切换会话 → 断言不产生 `abort()`/`EventSource.close()` | ⬜ 未自动化 |
| Door 2 | D2（SSE 事件不写 state.sessionId） | 静态/Lint：禁止 token/done/error 事件处理器中出现 `state.sessionId =` 赋值 | ⬜ 未自动化 |
| Door 3 | D3（contentDiv 动态获取） | 单元：渲染函数必须通过 `getStreamingContentDiv(sessionId)` 获取容器 | ⬜ 未自动化 |
| Door 4 | D4（删除会话不新建、保留流结构） | 前端逻辑单测：删除后不自动创建新 session；进行中流的 pendingStream 结构保留 | ⬜ 未自动化 |
| Door 5 | D5（cache key 不得含 session_id/msg_count） | **✅ 已落地**：`tests/services/test_cache_service.py`（相同问题跨会话/轮次同 key；key 不含会话维度） | ✅ 已自动化 |
| Door 6 | D6（禁用本地 bge-reranker） | 静态检查：`rerank_service.py` 不得 import/await 本地 bge-reranker / sentence-transformers | ⬜ 未自动化 |
| Door 7 | D7（优雅降级） | Pytest：Redis 不可用 / BM25 缺失场景，断言 cache.available=False、混合检索回退 FAISS-only | ⬜ 未自动化（有存量降级测试） |
| Door 8 | D8（异常隔离） | Pytest：注入抛错 chunk，断言单块失败仅跳过、其余继续（对照 `0e1b3b8`） | ⬜ 未自动化 |
| Door 9 | D9（单 worker / 落盘原子） | 文档+告警门禁：`ingest_state.json` 含单 worker 声明；幂等重建 E2E | ⬜ 部分（有幂等重建测试） |
| Door 10 | D10（HTML 转义 / DOMPurify） | 前端渲染检查：`<script>` 注入断言、marked→DOMPurify 调用断言、CDN 失败回退断言 | ⬜ 未自动化 |
| Door 11 | D11（流式渲染节流 + rAF 收尾） | 前端单测：mock rAF，断言 token 间隔 ≥50ms、done/error 时 cancelAnimationFrame + 最终渲染 | ⬜ 未自动化 |
| Door 12 | D12（.env 修改需重启） | 文档/运维门禁：启动脚本注明 `Settings()` 一次性读取；CI 校验 `.env.example` 与 `config.py` 键一致 | ⬜ 未自动化 |
| Door 13 | D13（清理/计数防误删与重复） | Pytest：文件删除路径穿越断言拒 400；计数"先清空再追加"后不重复统计 | ⬜ 未自动化 |
| Door 14 | D14（LLM 输出健壮解析） | Pytest：构造带 ```json 围栏、非法 JSON、null 的 LLM 返回，断言剥离围栏并兜底不抛错 | ⬜ 未自动化 |

> 落地顺序建议（性价比优先）：Door 5（✅ 已完成）→ Door 10 / Door 2 / Door 3（高价值 P002/P005）→ 其余。

---

## 6. 证据来源

- 代码：`app/services/cache_service.py`、`frontend/js/app.js`、`app/services/*.py`、`app/main.py`。
- Git 历史：各记录 Key Commits（`git log --oneline`）。
- 迭代文档：`docs/superpowers/plans/*`、`docs/superpowers/specs/*`。
- 详细档案：`docs/problems/Pxxx-*.md`。

> 强制约定：
> 1. 遇到问题**禁止直接照搬旧修复**；先判断是否代码回退、环境变化、输入变化或新 reproduction（各档案 "Do Not Reopen Without Evidence"）。
> 2. 不得编造根因或验证结果；写 `investigating` 明确标注未确认，写 `resolved` 必须有证据（提交/测试/复现）。
> 3. 修复非 trivial 问题后，回注册表更新状态 + 在对应档案追加，保留历史事实，不做覆盖替换。
