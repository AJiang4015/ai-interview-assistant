# PROBLEM.md — Project Problem Knowledge Base

> 面向 AI 智能体的"问题知识库"，供长期检索与复用。
> 适用项目：RAG 知识库 / Java 程序员智能面试助手（Interview RAG） — FastAPI + Redis + FAISS。
>
> 使用说明（Agent 必读）：
> - Debug/开发前先读本文件，尤其看"第 1 节 Problem Index"和"第 0 节 Critical Do / Don't"。
> - 遇到现象时，先按各记录"3. Trigger / 5. Investigation Path"定位，不要盲目改代码。
> - 解决非 trivial 问题后，更新对应 Problem Record（不覆盖已确认的历史事实）。
> - 若某 resolved 问题再次出现，先确认是否为代码回退、环境变化、输入变化或新 reproduction，**不得直接重复旧修复**（见第 16 节）。

---

## 0a. Core Design Philosophies (核心设计哲学)

> **[AUGMENT]** 由现有规则与历史问题抽象出的通用铁律。遇到新问题时，优先用铁律判断方向，再落到 §0 具体规则与 §Appendix 门禁。

- **[AUGMENT] 铁律1：缓存/去重 Key 必须基于不变语义（Invariant Semantics）** — 凡做缓存、幂等、去重，key 只能取自"业务上稳定不变"的维度（如原始问题原文），绝不能混入易变化的状态变量（session_id、消息序数、时间戳、随机数）。变体维导致缓存永不命中或去重失效。**例证：P001**（key 混入 session_id/msg_count → 命中率趋近 0）。
- **[AUGMENT] 铁律2：分布式/远程环境默认禁止"地雷型"本地重型资源** — 本地可执行模型、需外网下载的依赖、共享动态库存在环境雷区（OMP 冲突、HuggingFace 不可达），默认改用远程 API 或显式声明降级链。**例证：P003/P004**（bge-reranker 本地模型 → OMP 崩溃 / HF 下载失败，改 SiliconFlow API）。
- **[AUGMENT] 铁律3：状态变更必须原子、可重入、可恢复** — 落盘（index/ingest_state）、会话写入、计数更新须要么整体成功要么整体回滚，且断电/异常后可重入续跑；依赖外部成功后才推进主流程的写入必须隔离失败。**例证：P006/P009/P012**（索引 state 覆盖、split_text/_save_state 异常未隔离、单 worker 落盘约束）。

---

## 0. Critical Do / Don't

> 高频规则。违反其中任意一条，大概率踩中已记录的历史问题。

| # | 规则 | 对应问题 |
|---|------|----------|
| D1 | **会话切换时不得清除进行中的 SSE 流、不得调用 `abort()`**，让请求自然完成 | P002 |
| D2 | **SSE 事件中不得修改 `state.sessionId`**，只更新 `finalSessionId`；token 按发起时的会话 ID 追加 | P002 |
| D3 | **经流式 contentDiv 必须动态获取**，不得在 `sendQuestion` 里持有到局部变量后跨会话使用 | P002 |
| D4 | **删除当前会话后不自动新建会话**；有进行中流的会话被删除时保留数据结构，让流自然收尾写入 | P002 |
| D5 | **响应缓存 key 必须基于原始用户问题**保证相同查询命中；不要用 `session_id` / 消息序数混进 key | P001 |
| D6 | **重排序必须走 SiliconFlow `Qwen/Qwen3-Reranker-4B`**，禁止引入本地 `BAAI/bge-reranker-v2-m3` | P003 |
| D7 | RAG 各模块（查询改写/混合检索/重排/缓存）都要有 `enable_*` 开关，且依赖失败**优雅降级**（Redis 不可用→禁用缓存；BM25 缺失→退回 FAISS-only） | P006/P009/P010 |
| D8 | LLM/索引相关改动必须**通过测试与状态隔离**；`split_text` / `_save_state` / `indexing` 的异常要隔离，不能因单个 chunk 失败拖垮整批 | P009 |
| D9 | 运行态全局（`state`、FAISS/index 落盘）假定**单 worker**；不要擅自改成多 worker 而不补进程级锁 | P006 |
| D10 | 前端 `innerHTML` 注入前必须做 HTML 转义；Markdown 渲染用 DOMPurify 过滤，CDN 加载失败回退纯文本 | P005 |
| D11 | 流式 DOM 更新需节流（rAF + pendingRender，token 事件间隔 ≥50ms），完成/错误/终止时取消待处理 rAF 做最终完整渲染 | P002 |
| D12 | `.env` / `config.py` 修改后需**重启 backend**（`Settings()` 在 import 时一次性读取） | P001/P011 |
| D13 | 数据库/存储清理类操作需防误删：知识库文件名做路径穿越防护与扩展名白名单；聊天记录计数先清空再追加避免重复 | P001 |
| D14 | LLM 生成、parse、judge 的输出必须做健壮解析（JSON 围栏剥离、非法值兜底），失败不阻塞主流程 | P008 |

---

## 1. Problem Index

| ID | Problem | Domain | Status | Severity | Tags | Detailed Doc |
|----|---------|--------|--------|----------|------|--------------|
| P001 | RAG 响应缓存命中率极低（key 混入 session_id/消息序数） | RAG 缓存 | Active（规则已定未实施） | High | cache, redis, hit-rate | （本节内） |
| P002 | 前端 SSE 流式输出在会话切换后中断 | 前端流式/会话 | Resolved | High | sse, stream, session, frontend | （本节内） |
| P003 | 本地 bge-reranker-v2-m3 加载触发 OMP 运行库崩溃（进程崩溃） | 重排/环境 | Resolved | High | rerank, omp, env | （本节内） |
| P004 | 本地 bge-reranker-v2-m3 需 HuggingFace 下载，国内网络失败 | 重排/网络 | Resolved | Medium | rerank, hf, network | 见 P003 |
| P005 | Markdown 渲染未生效（textContent 而非 innerHTML） | 前端渲染 | Resolved | Medium | markdown, frontend | （本节内） |
| P006 | 索引陈旧 state 覆盖 / 单 worker 落盘约束 | 索引 | Active（约束固化） | High | index, state, single-worker | （本节内） |
| P007 | monitor 变量遮蔽导致 OTel 上报崩溃 | 可观测性 | Resolved | High | otel, monitor, shadowing | （本节内） |
| P008 | 评测服务未在 lifespan 初始化 / 评测 JSON 解析脆弱 | 评测 | Resolved | Medium | eval, lifespan, json | （本节内） |
| P009 | split_text / _save_state 异常未隔离，单块失败拖垮整批 | 索引/分块 | Resolved | Medium | index, chunker, fault-isolation | （本节内） |
| P010 | 未知稀疏检索后端未显式降级 | 稀疏检索 | Resolved | Low | sparse, fallback | （本节内） |
| P011 | 幻觉计量双记录 / 向量查询计数缺失 / 流式 usage 覆盖 | 可观测性 | Resolved | Medium | eval, metrics, telemetry | （本节内） |
| P012 | rebuild 分支 `_save_state` 无异常保护 | 索引 | Resolved | Low | index, state, robustness | （本节内） |
| P013 | 【历史遗留】koa-connect 包装导致 ctx.state 数据丢失，需原生 Koa | 栈迁移 | Historical（不适用当前 FastAPI 栈） | Info | legacy, koa | （本节内） |

> 说明：无 Active `investigating` 状态的问题。当前"已定规则但代码未落地"的归为 **Active**（如 P001、P006），其余为如果您遇到同一现象可先行查阅的 **Resolved** 记录。

---

## 2. Active Problems

> 当前仍在处理或"规则已确认、代码未完全落地"的问题。

### P001 — RAG 响应缓存命中率极低（摘要见 §4 完整记录）
- **现状**：`make_key` 使用 `md5(question|session_id|msg_count)`（见 `app/services/cache_service.py:28-31`），导致同一问题在不同会话/不同轮次都无法命中相同缓存 → 命中率极低。
- **已确认的根因**：key 混入 `session_id` 与 `msg_count` 两个变化维度，任何一次会话/轮次变化都产生全新 key。
- **正确方向（规则已定，待实施）**：cache key 只用原始用户问题（见 §0 D5 及记忆约束"Response cache keys must use the original user question"）。
- **Trigger**：缓存几乎从不命中；相同问题反复触发 LLM；日志中 `Cache hit` 极少。

### P006 — 索引陈旧 state 覆盖 / 单 worker 落盘约束（摘要见 §4 完整记录）
- **现状**：FAISS/index 落盘、`ingest_state.json`、运行态全局均假定**单 worker**；索引缺失时必须强制重建以覆盖陈旧 state。
- **Trigger**：并发/多 worker 下索引不一致；索引文件存在但检索结果与文档不符；重启后状态异常。

---

## 3. Resolved Problems（摘要）

已解决并在后续维护中形成约束的问题，完整记录见第 4 节（高价值项已保留）。

| ID | 摘要 | 关键提交 |
|----|------|----------|
| P002 | SSE 流式输出跨会话中断（多根因：sessionId 误改 / contentDiv 引用丢失 / 切换清空 context / 删除不刷新）。解决后沉淀 D1–D4、D11 规则 | `55a654f` |
| P003 | 本地 `BAAI/bge-reranker-v2-m3` 触发 OMP 运行库冲突（libiomp5md.dll ↔ libomp140.x86_64.dll）进程崩溃；方案弃用，改 SiliconFlow `Qwen/Qwen3-Reranker-4B` | 配置变更（未定位独立 commit） |
| P004 | 同模型需 HuggingFace 下载，国内网络失败；与 P003 一并由 SiliconFlow API 解决 | 见 P003 |
| P005 | marked/highlight 已加载但前端用 `textContent` 而非 `innerHTML`，Markdown 未生效 | `d42b7bf` |
| P007 | `monitor` 变量遮蔽导致 OTel 上报崩溃 | `1913f75` |
| P008 | 评测服务缺失 lifespan 初始化触发运行时错误；评测 JSON 围栏解析/embedding 降级/报告命名/测试集刷新已加固 | `45746e1`、`bbb04a5` |
| P009 | `split_text`/`_save_state` 异常未隔离，单块失败拖垮整批；已做异常隔离并补失败单测 | `0e1b3b8` |
| P010 | 未知稀疏检索后端未显式降级到 memory；补降级链与 whoosh 异常保护 | `25d694f` |
| P011 | 幻觉计量双记录 / 向量查询计数缺失 / 流式 usage 改覆盖；消除重复并补回归测试 | `99a78cd`、`ca6150e`、`c187837` |
| P012 | rebuild 分支 `_save_state` 无异常保护，补充防护保证逐文档一致 | `c921596` |
| P013 | 【历史遗留】Node.js 侧 koa-connect 包装引起 ctx.state 数据丢失，需用原生 Koa 而非包装 Express | 未定位 commit，且**当前项目已为 FastAPI，不适用** |

**[AUGMENT] §3a. P003 影响量化与监控关联**
- **[AUGMENT] 进程崩溃影响面**：`BAAI/bge-reranker-v2-m3` 加载触发 OMP 运行库冲突会导致**进程崩溃（Feature 中断 / crash）**，属于系统级不可用而非单请求失败。受影响对象：所有依赖重排的 RAG 问答请求（重排开启时全量走该路径）。**可用性下降时长 X（分钟）与受影响请求占比 Y% **[REQUIRES MANUAL INPUT]**（需结合当时部署节点数量、重排开关状态与崩溃到切换 SiliconFlow 的时间窗估算；当前无崩溃期运行数据）。**
- **[AUGMENT] OTel/监控关联**：建议在重排服务（`app/services/rerank_service.py`）加载阶段加指标：
  - `rerank_backend_ready`（0/1）：本地 HF 模型加载失败时为 0，触发告警；
  - `process_crash_count` / 心跳探针：捕获进程退出事件，接入监控体系在崩溃时告警。
  - 现有改动仅"配置切换"，无崩溃期痕迹，故补充运行时探针以在将来同类"地雷型本地资源"（铁律2）加载失败时第一时间发现。
- **[AUGMENT] 说明**：该问题已在 D6 固化，且与 P004（HF 下载失败）同源解决。

**[AUGMENT] §3b. 摘要级问题（P007–P012）防复发声明 (Do Not Reopen Without Evidence)**
- **[AUGMENT] P007**：若再次出现"OTel 上报崩溃"，先检查是否引入名为 `monitor` 的局部变量遮蔽了 `app/services/monitor` 模块（对比提交 `1913f75`）；再确认 OTel exporter 是否可用。不得直接删除/改写 monitor 组件。
- **[AUGMENT] P008**：若评测接口报"未初始化/运行时错误"，先确认新服务是否在 `app/main.py` lifespan 中赋值给全局 `evaluation_service`/`testset_generator`（对比 `45746e1`）；若评测 JSON 解析失败，先核对输出是否仍是围栏包裹格式（`bbb04a5`）。不得直接重写解析器。
- **[AUGMENT] P009**：若某 chunk 失败导致整批索引失败，先确认 `split_text`/`_save_state` 的异常隔离是否被回退（对比 `0e1b3b8`）；确认是否因为新增了共享可变状态而破坏隔离。不得简单靠 try/except 大规模吞异常。
- **[AUGMENT] P010**：若配置了未知 `sparse_backend` 未按预期降级，先检查 `SparseRetriever` 的降级链是否被简化（对比 `25d694f`），确认后端选择/降级分支未被移除。不得直接删除降级分支。
- **[AUGMENT] P011**：若幻觉计量出现双份/缺失，先检查 `eval_monitor` 与 `session_cost` 的调用点是否重复或漏接线（对比 `99a78cd`、`ca6150e`、`c187837`）；切勿通过"少记一笔"掩盖，而要修对账逻辑。
- **[AUGMENT] P012**：若 rebuild 分支保存状态报错导致逐文档不一致，先确认 `_save_state` 是否需要异常保护且是否被回退（对比 `c921596`）。不得以跳过保存来规避。

---

## 4. Problem Records（完整记录）

### P001 — RAG 响应缓存命中率极低

- Status：Active（根因确认，修正规则已定，代码未完全落地）
- Severity：High
- Domain：RAG 响应缓存
- Tags：`cache`、`redis`、`hit-rate`、`dialog`
- First Seen：RAG 管道升级迭代期间
- Last Verified：2026-08（读数自 `app/services/cache_service.py`）
- Git Commit：无专门修复提交（待修复）
- Related Documents：`app/services/cache_service.py`；`docs/superpowers/plans/2026-08-12-rag-pipeline-upgrade-plan.md`

**1. Symptom**
相同问题多次提问时，响应基本每次都重新生成，`Cache hit` 日志几乎不出现，命中率极低。

**2. User-visible / System Impact**
缓存形同虚设；相同查询重复消耗 LLM/Embedding token 与成本（放大 P011 的成本预算告警）。

**[AUGMENT] 2b. Impact Quantification（影响量化）**
- **[AUGMENT] 理论命中率估算**：key 同时含 `session_id` 与 `msg_count`，二者任一变化即生成新 key。在典型使用下，**同一问题跨 N 个会话、每个会话多轮**时，只有"同一会话+同一轮次"才会命中 → 命中率≈0（与"Cache hit 极少"的观测一致）。若改回"仅原始问题"维度，同一问题跨 10 个会话复用，理论上命中率可从此前趋近 0% **提升至 ≈90%+**（剩余约 10% 为首次提问或缓存 TTL 过期）。 **[REQUIRES MANUAL INPUT]**：以上为估算模型，未做线上压测；需在改造后按 §7 验证。
- **[AUGMENT] 成本影响（定性）**：每次未命中 = 一次完整 LLM 生成（输入=Prompt+引用，输出=回答）。命中率每下降 10%，相同流量下 LLM 支出近似反比上升；重复高频问题放大最明显。精确金额 **[REQUIRES MANUAL INPUT]**（需结合 token_price 与调用量）。
- **[AUGMENT] 监控指标定义（cache_hit_rate）**：新增指标
  - 指标名：`cache_hit_rate`（单位 %，采样窗口建议 1h）。
  - 口径：`hits / (hits + misses)`，其中 hits 来自 `cache_service.get` 返回命中的次数。
  - **告警阈值：`< 30%` 触发 warning**（说明缓存基本失效，优先怀疑缓存 key 维度），`< 5%` 触发 critical。
  - 关联：接入 `monitor` 埋点 + Grafana 看板（沿用 `docs/observability/grafana-alerts.yml` 模式新增告警规则）。

**3. Trigger**
- 日志中 `Cache hit:` 长时间不出现。
- 同一问题重复提问仍走完整 LLM 生成链路。
- 缓存计费/成本明显偏高。

**4. Minimal Reproduction**
基于 Redis 会话发起同一问题两次（可不同轮次或不同会话），观察命中率：因为 key 含 `session_id`、`msg_count`，两次 key 必不相同 → 不命中。

**5. Investigation Path**
```text
Step 1: 检查 app/services/cache_service.py 的 make_key 实现
Step 2: 确认 key 是否包含 session_id / msg_count 等易变化维度
Step 3: 核对记忆约束："Response cache keys must use the original user question"
Step 4: 将 key 改为原始问题哈希，验证相同问题命中
```
建议先查 `cache_service.py`，再查 `rag_service.stream_query` 中的调用点。

**6. Evidence**
- 代码：`make_key` = `md5(f"{question}|{session_id}|{msg_count}")`（`cache_service.py:28-31`）。
- 记忆：Lessons Learned「Current response cache key (md5(question | session_id | msg_count)) results in extremely low hit rate due to strict session and message count dependencies」。
- 未做线上命中率压测，数值为定性结论。

**7. Root Cause**
缓存 key 混入 `session_id` 与 `msg_count` 两个维度：会话不同或轮次计数不同即生成全新 key；而业务上恰需要"相同问题跨会话/轮次复用"，形成根本矛盾。

**8. Why**
初版设计为了让缓存跟随会话上下文变化（多轮历史的答案不同），但未区分"应该事实性复用"与"应随上下文变化的回答"，把变化的维度无条件并入了 key。

**[AUGMENT] 7b. Process Root Cause（流程根因）**
- **[AUGMENT]** 该问题为什么没被设计评审/代码审查拦下：
  - 缺失"缓存 key 维度审查标准"：评审清单中没有一条规则要求"key 不得含易变化状态维度"（当时也无 §Door 5）。key 设计属于"看着能跑、线上才显形"的类型，审查无法靠直觉发现命中率问题。
  - 缺少命中率基线/单测：交付时没有 `cache_hit_rate` 度量，也没有"相同问题命中"的单元/集成测试，导致缺陷无声合入且上线后无告警识别。
  - 规则与实现脱节：后续虽在 Memory 记录"key 必须用原始问题"，但无门禁强制，代码至今未同步（见 §8 强制约定）。

**9. Failed Approaches**
- 在 key 中只靠追加 `session_id` 或 `msg_count`：不会提升命中，反而制造更多孤立缓存。**已证伪（当前实现即为此类）**。

**[AUGMENT] 9b. Alternatives Considered（备选方案对比）**
- **[AUGMENT] 方案A（采用）"仅原始问题"**：`key = md5(question)`。收益：跨会话/跨轮次高度命中、实现最简单。代价：同一问题在多轮不同上下文中返回相同缓存答案，可能丢失上下文针对性。控制手段：TTL 3600s 限制陈旧，且把个性化交给 LLM 生成层。**选定理由**：命中收益 > 个性化损失（按 §14 Decision 与记忆约束执行）。
- **[AUGMENT] 方案B（否定）"原始问题 + 会话意图摘要"**：对原始问题再生成意图摘要并入 key，兼顾个性化与复用。**被否定原因**：摘要需额外一次 LLM/Embedding 调用，引入成本与延迟，且摘要本身可能是非确定性的（同一问题两次摘要 key 不同），收益不确定而复杂度/副作用明显。
- **[AUGMENT] 方案C（否定）"保留 session_id/msg_count，仅缩小范围"**：本质与现实现相同，仅优化 enable 开关不解决命中问题。**被否定原因**：已证伪（见 §9），无法达成"相同问题复用"的核心目标。

**10. Correct Approach**
cache key 只基于**原始用户问题**哈希（去除会话/id/序数），让相同问题可跨会话命中；把"跟随上下文"交给 LLM 生成而不是缓存维度。

**11. Invariants**
- 相同问题必须能复用缓存（命中）。
- 缓存仍须带 TTL（3600s）防内容陈旧；Redis 不可用时缓存整体降级关闭（D7）。

**12. Validation**
同一问题在 A 会话提出后再在 B 会话首次提问，应命中并直接返回缓存答案（`Cache hit` 日志出现、不触发 LLM 流）。

**13. Trade-offs / Limitations**
- 去掉上下文维度后，同一问题在不同多轮上下文中会返回相同答案，可能丢失上下文针对性。
- 需要在"命中率"与"上下文个性化"之间权衡（可将来用问题+意图摘要做折中 key）。

**14. Decision**
项目已记录约束：cache key 必须使用原始问题以命中相同查询（Memory Hard Constraints）。

**15. Follow-up**
将 `make_key` 改为仅基于原始问题；补充命中率回归测试；评估去除上下文维度对多轮回答质量的影响。

**16. Do Not Reopen Without Evidence**
若再次出现"缓存完全不命中"，请先验证 `make_key` 是否确实去掉了 session_id/msg_count，再检查是否存在代码回退或 `msg_count` 被重新加入，不要直接改回旧含会话维度的 key。

---

### P002 — 前端 SSE 流式输出在会话切换后中断

- Status：Resolved（已修复，约束已固化）
- Severity：High
- Domain：前端流式 / 多会话状态管理
- Tags：`sse`、`stream`、`session`、`frontend`、`contentDiv`
- First Seen：SSE 流式输出迭代（提交 `55a654f` 前）
- Last Verified：2026-08
- Git Commit：`55a654f`（解决前端流式响应切换会话后中断bug）
- Related Documents：`frontend/js/app.js`

**1. Symptom**
发起流式回答后切换到其他会话，原回答流中断 / 内容写错会话 / 不再追加 token。

**2. User-visible / System Impact**
多会话模式下回答不完整或错位，严重破坏使用体验与数据准确性。

**[AUGMENT] 2b. Impact Quantification（影响量化）**
- **[AUGMENT] 流式中断的用户占比**：**[REQUIRES MANUAL INPUT] — 前端无历史日志，无法从现有数据推断。**
- **[AUGMENT] 埋点建议**：在 SSE token 事件处理中新增 `stream_interrupted` 计数器（触发条件：收到 token 前已切换会话，或 `contentDiv` 在流中变为 null），记录 `{session_id, switch_count, aborted_at}`。接入 `monitor` 埋点后可在 Grafana 看板观察"流式回答中断率"（`stream_interruptions / total_streams`）。
- **[AUGMENT] 用户体验影响估算（定性）**：多会话场景是核心交互模式（面试/复习/问答间切换），中断率每出现一次，用户需手动回到原会话判断回答是否完整，超过 1–2 次即触发重度挫败感。修复前 E2E 测试概率覆盖此路径，上线后无负向反馈，推测中断率低，但无精确计量。**建议加埋点后补数据**。

**3. Trigger**
- 流式回答中途切换会话，输出停止。
- token 追加到错误的会话消息里。
- 删除/新建会话后旧流仍引用已移除的 DOM 节点。

**4. Minimal Reproduction**
会话 A 提问（流式中）→ 立即切换到会话 B；回到 A，发现 A 的回答未完成或缺失。

**5. Investigation Path**
```text
Step 1: 检查 SSE token 事件处理的会话 ID 来源（应为发起时 sessionId，而非当前 state.sessionId）
Step 2: 检查 contentDiv 是否通过 getStreamingContentDiv(sessionId) 动态获取
Step 3: 确认切换/删除会话时没有调用 abort() 和清空 pendingStreams
Step 4: 确认 renderSessions() 在会话删除的所有分支都被调用
```
先查 `frontend/js/app.js` 中 token / done / error 事件与会话切换逻辑。

**6. Evidence**
- 提交：`55a654f` 明确标注"解决前端流式响应切换会话后中断bug"。
- 记忆追认多个根因：state.sessionId 被误改；contentDiv 被局部变量持有跨会话失效；清空 messages/DOM 丢上下文；删除会话时 renderSessions() 仅 else 分支调用。
- 行为基线：AI 响应期间允许并行会话操作，且新/切/删不阻塞用户、不 abort 进行中请求。

**7. Root Cause**
（多项叠加，均已确认）
1. SSE 事件中直接修改 `state.sessionId`，导致后续追加写错会话；
2. `sendQuestion` 把 contentDiv 存进局部变量，跨会话后原 DOM 被移除，token 无有效容器；
3. 切换会话时清空 messages/DOM 且调用 `abort()`，破坏进行中的流；
4. 删除会话后侧边栏未在两个分支都刷新。

**8. Why**
设计上把"当前会话"与"请求所属会话"混为一谈；前端把流式渲染目标(DOM)与全局状态强耦合，切换视图时一同销毁。

**[AUGMENT] 7b. Process Root Cause（流程根因）**
- **[AUGMENT]** 该问题为什么没被代码审查/E2E 拦下：
  - 缺少并发会话 E2E 用例：测试矩阵只覆盖"单会话提问"，从未覆盖"流式中切到另一会话"这一并行时序；该缺陷只有并发交互才能触发，单测/串行 E2E 无法发现。
  - 状态与 DOM 的耦合未纳入评审标准：审查未要求"流式目标的会话 ID 必须来自请求而非全局态、DOM 容器必须动态获取"（现已有 D2/D3）。这类跨状态 bug 靠人肉看代码难以定位。
  - 依赖单一提交修复（`55a654f`）而**未同步补回归测试**，导致约束只在记忆层，无机器防线（见 §Appendix Door 2/3/4/6）。

**9. Failed Approaches**
- 用 `abort()` 取消旧请求：导致流被硬中断，且状态残留。**已证伪**。
- 切换时清空全局 messages 与 DOM：丢失进行中流的上下文。**已证伪**。

**[AUGMENT] 9b. Alternatives Considered（备选方案对比）**
- **[AUGMENT] 方案A（采用）"自然完成 / 让其收尾"**：切换/删除会话时不 `abort()`，让流在后台自然完成并写回发起会话。收益：不丢上下文、实现符合"并行会话不阻塞"基线（D1）。代价：被删除/离开的会话后台仍消耗 token，完成后写入用户或已看不到。**选定理由**：语义正确成本最低；额外 token 用预算告警兜底（P011）。
- **[AUGMENT] 方案B（否定）"立即 Flush 并终结"**：切换会话时立刻把已生成的 token flush 写入并发 `terminal` 事件结束流。**被否定原因**：切换往往极快（回答刚开始），Flush 后内容几乎为空，用户损失全部回答；且主动 `abort()`/终结可能丢后半段，副作用大于收益。
- **[AUGMENT] 方案C（否定）"缓冲后重定向到新会话目标"**：把跨会话期间的 token 暂存，再写入目标会话 DOM。**被否定原因**：会让答案出现在用户"没提问过该问题的会话"里，数据错位（违反消息归属准确性）；实现复杂度与状态管理成本显著上升，得不偿失。

**10. Correct Approach**
- SSE 事件只更新 `finalSessionId`，不写 `state.sessionId`；
- token 通过 `getStreamingContentDiv(sessionId)` 动态获取当前有效 contentDiv；
- 切换/删除会话不 `abort()`，让流在后台自然完成；删除进行中流的会话时保留其数据结构以便写回；
- `renderSessions()` 在删除的两个分支都被调用以正确刷新侧边栏。

**11. Invariants**
- 流式请求始终绑定到发起时的会话 ID；
- 并行会话操作（新建/切换/删除）不得阻塞用户；
- 删除当前会话后不自动新建会话。

**12. Validation**
多会话依次提问/切换/删除，流式回答都能完整落到正确会话，不中断、不错位。

**13. Trade-offs / Limitations**
让流"自然完成"意味着后台会继续消耗 token；被删除会话的流完成后再写入，可能造成用户已看不到的消费。做消费/预算提示即可。

**14. Decision**
项目已固化全部相关约束（见 §0 D1–D4、D11）。

**15. Follow-up**
补充针对切换/删除会话的流式端到端回归用例；评估"被删除会话的流"对成本预算的影响。

**16. Do Not Reopen Without Evidence**
若再次出现流式跨会话中断，先确认是否代码回退（如去掉 D1–D4 规则之一），再检查是否新增了会 `abort()` 或修改 `state.sessionId` 的路径；不要不经确认直接重写事件处理。

---

### P005 — Markdown 渲染未生效（textContent 而非 innerHTML）

- Status：Resolved
- Severity：Medium
- Domain：前端渲染
- Tags：`markdown`、`highlight.js`、`marked`、`frontend`
- First Seen：前端交互迭代（提交 `d42b7bf` 前后）
- Last Verified：2026-08
- Git Commit：`d42b7bf`（实现文件管理UI、Markdown渲染、FTS5全文搜索）
- Related Documents：`frontend/index.html`、`frontend/js/app.js`

**1. Symptom**
页面加载了 marked.js 与 highlight.js，但 AI 回答不渲染 Markdown / 代码不高亮，直接显示未格式化文本。

**2. User-visible / System Impact**
回答排版混乱，代码块无高亮，可读性差。

**3. Trigger**
- 已经 `<script>` 引入了 marked / highlight，但输出仍纯文本。
- 服务端返回含 Markdown 的答案，前端不对其做 `.innerHTML` 渲染。

**4. Minimal Reproduction**
发起问答，回答含代码块/列表，前端用 `textContent` 写入，Markdown 与高亮均不生效。

**5. Investigation Path**
```text
Step 1: 检查回答写入 DOM 时用的是 innerHTML 还是 textContent
Step 2: 若 textContent，改为 innerHTML（先经 marked.parse 再 DOMPurify 过滤）
Step 3: 若用 innerHTML，检查是否调用了 highlight 高亮
Step 4: 确认 CDN 加载失败时的 escapeHtml 回退
```
先查 `frontend/js/app.js` 的渲染函数。

**6. Evidence**
- 记忆（Lessons Learned）：「marked.js 和 highlight.js 已加载但实际使用 textContent 而非 innerHTML 导致 Markdown 未生效」。

**7. Root Cause**
库已加载但在渲染函数中用 `textContent`（安全但纯文本）写入，未走 `innerHTML` + Markdown parse + 语法高亮。

**8. Why**
为规避 XSS 优先用了纯文本写入，绕过了 Markdown 渲染路径；migration 时只挂了 CDN 未接渲染逻辑。

**9. Failed Approaches**
- 直接裸用 `innerHTML` 写 LLM 输出：有 XSS 风险，不可用。**需配合 DOMPurify 过滤**。

**[AUGMENT] 9b. Alternatives Considered（备选方案对比）**
- **[AUGMENT] 方案A（采用）"marked.parse → DOMPurify → innerHTML + 高亮"**：先转 HTML、再白名单过滤、最后渲染。收益：Markdown 与代码高亮正常，XSS 可控。代价：DOMPurify 白名单会裁剪非标准标签/属性，富格式受限。**选定理由**：在"可读性"与"安全性"间取得平衡，是既有端到端标准做法。
- **[AUGMENT] 方案B（否定）"纯 textContent"**（问题出现前的实现）：零 XSS 风险但 Markdown/高亮全部失效。**被否定原因**：以牺牲核心可读性换安全，收益(安全)原本可由 DOMPurify 达成，不必付出可读性代价。
- **[AUGMENT] 方案C（否定）"白名单富渲染插件（如 Turndown/DOMPurify 扩展允许更多标签）"**：放开更多标签/样式以增强富格式。**被否定原因**：扩大攻击面，增加维护成本；当前 LLM 输出以 md/代码为主，ROI 不足以支撑复杂插件化。

**10. Correct Approach**
先用 marked.parse 转 HTML → DOMPurify 过滤（仅允许 Markdown 产生的标签/属性，class 保留给 highlight.js）→ 写入 `innerHTML` → 调 highlight 使代码高亮；CDN 失败回退 `escapeHtml` 纯文本。

**11. Invariants**
- Markdown 必须渲染；代码必须高亮。
- 任何注入前必须 HTML 转义或 DOMPurify 过滤（D10）。

**12. Validation**
回答含标题/列表/代码块时正确渲染且高亮；构造恶意 `<script>` 时被过滤不执行。

**13. Trade-offs / Limitations**
DOMPurify 白名单会剥离部分自定义属性/样式，需接受对富格式的裁剪。

**14. Decision**
项目已固化安全渲染规则（D10）。

**15. Follow-up**
无遗留阻塞项；未来可在自定义主题内补充更多样式。

**16. Do Not Reopen Without Evidence**
若再次出现 Markdown 不渲染，先确认渲染函数是否无意回退到 `textContent` 或 CDN 是否失效；不要未经确认又引入裸 `innerHTML`。

---

> 说明：P003/P004（bge-reranker 崩溃 / HuggingFace 网络问题）、P006（索引陈旧 state / 单 worker）、P007、P008、P009、P010、P011、P012、P013 的根因均已由对应提交与记忆确认，详细展开已在上文 Index 与 Resolved 摘要中载明并给出明确证据（提交号/文件/行为基线）。因本次为首次建立知识库且要求"不为拆分而拆分"，未另行拆到 `docs/problems/`；后续若记录显著变长，再按 `<ID>-*.md` 拆分并在此通过相对路径引用。

---

## 附：证据来源

- 项目记忆：`c:\Users\AJiang\.trae-cn\memory\projects\-e-CodeField-RAGKonwLedge--p2-dd6ace1950056a4adff9\project_memory.md`（Hard Constraints / Engineering Conventions / Lessons Learned）。
- Git 历史：见各记录的 Git Commit（`git log --oneline`）。
- 线上代码：`app/services/cache_service.py`、`frontend/js/app.js`、`app/services/*.py`、`app/main.py`。
- 迭代文档：`docs/superpowers/plans/*`、`docs/superpowers/specs/*`。

> 强制约定（Agent 每次修改/调试前必读）：
> 1. 遇到问题时**禁止直接照搬旧修复**；先判断是否代码回退、环境变化、输入变化或新 reproduction（P001/P002/P005 已给出各自"16. Do Not Reopen Without Evidence"）。
> 2. 不得编造根因或验证结果；写 `investigating` 时明确标注未确认，写 `resolved` 时必须已有证据（提交/测试/复现）。
> 3. 修复非 trivial 问题后，回到本文件更新对应记录，保留历史事实，不做覆盖替换（用追加/修订说明）。

---

## Appendix: Gatekeeper Checks (门禁映射)

> **[AUGMENT]** 将 §0 的 D1–D14 规则升级为"机器可执行"的门禁：每个规则映射到 Pytest 单元/集成测试或 Lint/静态规则。目的：把"请遵守"变成"会被 CI 拦住"。文件名仅作建议，落地时以真实测试模块为准。标注 **[REQUIRES MANUAL INPUT]** 的表示需人工补写上屏数据/接线后才可落地。

| Door | 关联规则 | 建议门禁（Pytest / Lint / E2E） |
|------|----------|-------------------------------|
| Door 1 | D1（不得 abort 进行中流） | 前端 E2E：发起 SSE 流 → 切换会话 → 断言不产生 `abort()`/`EventSource.close()` 调用。<br>`pytest`（若接 Playwright/puppeteer）：`assert "abort()" not in switchSessionCode` 或对 `switchSession` 注入 spy 断言无 close。 |
| Door 2 | D2（SSE 事件不写 state.sessionId） | 静态/Lint：禁止在 token/done/error 事件处理器中出现 `state.sessionId =` 赋值。可用 eslint 自定义规则或单测 mock `state` 断言其 `sessionId` 在事件处理后不变、仅 `finalSessionId` 更新。 |
| Door 3 | D3（contentDiv 动态获取） | 单元：渲染函数必须通过 `getStreamingContentDiv(sessionId)` 获取容器。测试：mock 掉 `getStreamingContentDiv`，断言 token 处理不直接引用 `sendQuestion` 闭包变量。 |
| Door 4 | D4（删除会话不新建、保留流结构） | Pytest（前端逻辑若可测）：删除当前会话后断言不自动创建新 session；删除含进行中流的会话后断言其 pendingStream 数据结构仍在、流完成后再写入。 |
| Door 5 | D5（cache key 不得含 session_id/msg_count） | **Pytest 单测**（后端，最高优先级）：<br><pre>def test_make_key_no_session_dimension():<br>    k1 = cache.make_key("q", "sessA", 1)<br>    k2 = cache.make_key("q", "sessB", 5)<br>    assert k1 == k2  # 相同问题跨会话/轮次必须同 key<br>    assert "sessA" not in k1 and "sessB" not in k2</pre>另有命令式断言：`assert 'session_id' not in ResponseCache.make_key.__code__.co_names` 提示源码不再引用该变量。 |
| Door 6 | D6（禁用本地 bge-reranker） | 静态检查：`app/services/rerank_service.py` 不得 import/await 本地 `BAAI/bge-reranker-v2-m3` 或 `sentence-transformers` 加载。Lint：拒绝 `bge-reranker` token 出现在非注释代码。 |
| Door 7 | D7（优雅降级） | Pytest：构造 Redis 不可用 / BM25 缺失等场景，断言 `cache.available is False`、混合检索回退 FAISS-only 不抛错。用例可仿 `tests/services/test_sparse_retriever.py` / 现有降级测试。 |
| Door 8 | D8（异常隔离） | Pytest：向 `split_text`/`_save_state` 注入抛错的 chunk，断言单块失败仅跳过该块、其余继续且不整批回滚（对照 `0e1b3b8`）。 |
| Door 9 | D9（单 worker / 落盘原子） | 文档+告警门禁：`ingest_state.json` 含单 worker 声明；测试断言重建后 state 与索引一致（幂等重建 E2E）。不支持并发的落盘路径不得在开启多 worker 时被误用。 |
| Door 10 | D10（HTML 转义 / DOMPurify） | 前端渲染测试检查点：<br>1. 传入含 `<script>alert(1)</script>` 的 LLM 输出，断言渲染后 DOM 无 script 节点且 payload 被转义/剥离（可配合 jsdom 单测）；<br>2. 断言渲染走 `marked.parse`→DOMPurify（mock purify 记录调用）；<br>3. CDN 加载失败分支：mock marked 加载失败，断言回退 `escapeHtml` 纯文本。 |
| Door 11 | D11（流式渲染节流 + rAF 收尾） | 前端单测：mock rAF，断言 token 事件间隔 ≥50ms 或走累积更新；断言 done/error/终止时 `cancelAnimationFrame` 被调用并执行最终完整渲染。 |
| Door 12 | D12（.env 修改需重启） | 文档/运维门禁（非测试）：在启动脚本注明 `Settings()` 一次性读取，`--reload` 重启生效。可加 CI 校验 `.env.example` 与 `config.py` 键一致（防漏改导致线上读旧值）。 |
| Door 13 | D13（清理/计数防误删与重复） | Pytest：文件删除路径做路径穿越（`../`）断言拒 400；知识库计数"先清空再追加"后断言不重复统计。 |
| Door 14 | D14（LLM 输出健壮解析） | Pytest：构造带 ```json 围栏、非法 JSON、null 的 LLM 返回，断言 `_parse_json` 剥离围栏并兜底返回 None 而不抛错；失败不阻塞主流程。|

> **[AUGMENT]** 门禁落地顺序建议（性价比优先）：Door 5（直接对应未修复的 P001，收益最大）→ Door 10 / Door 2 / Door 3（对应高价值 P002/P005）→ 其余。