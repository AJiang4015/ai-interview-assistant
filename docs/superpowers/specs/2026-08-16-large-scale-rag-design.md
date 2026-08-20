# 10w+ 大规模 RAG 检索优化 — 设计文档

> **For agentic workers:** 本设计经 brainstorming 逐节确认后成文，后续用 superpowers:writing-plans 生成实现计划。
> 状态：已认可（方案 A：单机内可插拔规模化升级）

**日期**：2026-08-16
**目标**：单机高并发、毫秒级检索，支撑 100 个 10 万字级文档（百万字级语料、可成长至约百万向量），一次覆盖五个痛点：入库/嵌入慢且贵、分块/召回质量差、混合检索变慢、查询延迟/内存压力。
**约束**：不改变现有 API 对外契约；不改变部署拓扑（仍在单机 FastAPI 应用内）；SiliconFlow API 嵌入（沿用现状，不引入本地模型）；OTel 仍可选启用+静默降级；嵌入式/检索/eval 全链路保持既有优雅降级约定。

---

## 1. 总体架构

```
上传/入库 → IndexingPipeline（受控并发嵌入 + 断点续传 + 幂等 + 进度）
                 ├── Chunker（递归重叠 + 段落感知 + parent-child）
                 ├── VectorStore（可插拔 ANN：flat / hnsw 默认 / ivf）
                 └── SparseRetriever（可插拔：memory / whoosh / sqlite_fts + 降级链）
                         ↓ 共用同一份 chunk 元数据
查询 → RetrievalService（混合检索 + RRF，叶候选→parent 上下文扩展）
                 └── Reranker（SiliconFlow，作用在候选集）
                         ↓ 上下文组 Prompt → LLM
```

### 组件职责（每个单元单一目的、接口清晰、可独立测试）

| 组件 | 文件 | 职责 |
|---|---|---|
| VectorStore | `app/storage/vector_store.py`（改造 `faiss_store.py`） | 索引工厂化（flat/hnsw/ivf）；读写锁优化并发 |
| Chunker | `app/services/chunker.py` | 递归重叠分块 + 段落感知 + parent-child 元数据 |
| SparseRetriever | `app/services/sparse_retriever.py` | 稀疏检索可插拔后端 + 降级链 |
| IndexPipeline | `app/services/index_pipeline.py` | 并发嵌入 + 断点续传 + 幂等 + 进度事件 |
| RetrievalService | `app/services/retrieval_service.py` | 混合检索（dense+sparse+RRF）+ parent 扩展 + Reranker |
| Config | `app/config.py` | 新增索引/分块/稀疏/并发配置项 |

不改动：`embedding.py`（仅复用其 encode 批接口）、`llm_client.py`、`rerank_service.py`、API 层对外结构。

---

## 2. 索引模块（可插拔 ANN 与高并发检索）

### 2.1 索引工厂
`VectorStore` 统一接口：`search(qv, top_k)`、`add(vectors, metadata)`、`save/load/reset`、`size`、`is_loaded`。构造按 `VECTOR_INDEX_TYPE` 选择实现：
- `flat`：`IndexFlatIP`（精确，现状）。
- `hnsw`（默认）：`IndexHNSWFlat(M, efConstruction)`；查询用 `faiss.SearchParametersHNSW(efSearch=…)` 控制召回/速度。M / efConstruction / efSearch 配成项。
- `ivf`：`IndexIVFFlat(quantizer=IndexFlatL2, nlist)`，需训练子集后 add；作为进阶项，本次实现但默认关闭，配置切换说明。
HNSW 与 Flat 同用内积，均先 `normalize_L2`，保证召回语义一致、可比。`faiss.write_index/read_index` 对 resolved index 均可持久化，文件格式不变。

### 2.2 高并发检索（读写锁）
- 现状 `asyncio.Lock()` 将所有 search 串行，是并发下主要延迟源。
- 改造：读（查询）不加互斥、直读构建完成的只读索引；写（入库 add）持排他锁，短暂阻塞读；写入为低频批量操作。
- 用 `asyncio` RW 锁（自实现简单版或依赖 `readerwriterlock`），限依赖可选、缺时回退读锁不抛错。

### 2.3 内存与召回权衡
- 默认 HNSW 全精度；百万级 1024 维 ≈ 向量 4GB + 图若干 GB，落单机可行。
- `.env` 暴露 `HNSW_M`、`EF_CONSTRUCTION`、`EF_SEARCH`、`IVF_NLIST`，按机器微调。
- 超出单机内存的量化档（SQ/PQ）或分布式（方案 B）本次不做，作为后续扩展。

---

## 3. 分块与召回质量（长文档命中 + 上下文完整性）

### 3.1 递归重叠分块
`Chunker`：
- 按层级（标题/段落/句/块）递归切分，目标块长 `CHUNK_SIZE`（默认≈600）、重叠 `CHUNK_OVERLAP`（默认≈80）、最小块容忍。
- 优先按段落/文本边界断开，避免句中硬切；中英混排按中文字符与英文单词/句号边界找断点，防把词句切坏。

### 3.2 段落/层级感知 + parent-child 检索
- 每个**叶块（leaf chunk）**：精确检索用，向量短、语义聚焦。
- 叶块元数据记录**父上下文链**：标题层级路径 `headings: ["# 并发","## 线程池",...]` 与可选**父块内容**（将子块拼回更高层段落形成的上下文块）。
- 查询：叶块检索 top-N 候选 → 取候选父上下文（父块/标题链）扩展 → 去重 → Reranker 重排 → 组 Prompt。
- 提升长文档命中与 LLM 上下文完整性，缓解块小导致的幻觉/答非所问；复用现有 Reranker 与 Faithfulness/Evaluation 验证质量。

### 3.3 去重与幂等
- 入库前对 content 规范化（去空白/换行）后 hash，已在库内则跳过。
- 持久化「块 hash → chunk_id」映射，重复灌入不致索引膨胀。

### 3.4 质量护栏
- 小型抽查/标注集断言：新 Chunker + parent 扩展后的 top-5 命中覆盖旧逻辑（回归级别）。
- 复用 `eval_testset`/Faithfulness 做端到端对比，不新增重量级评测框架。

---

## 4. 入库管道与嵌入成本优化

### 4.1 受控并发批量嵌入
- `IndexPipeline` 用 `asyncio.Semaphore(CONCURRENT_BATCHES)`（默认 4）并发多路嵌入，每路内仍按 batch=32。
- 失败批指数退避重试（沿用 tenacity 风格），重试耗尽记入失败清单不中断整体，最后返回失败文档列表。
- `CONCURRENT_BATCHES`、`BATCH_SIZE` 做成配置，避免打满 API 限流/429。

### 4.2 断点续传 + 进度事件
- 按文档粒度在 `ingest_state`（SQLite 或 Redis）保存已完成集合（文档规范 hash）。
- 中断重跑仅处理增量；向前端/监控暴露 `ingest_progress`（processed_docs/total、processed_chunks、failed_docs），复用既有异步任务 + 轮询进度模式（同 RAG Evaluation）。

### 4.3 幂等与成本兜底
- 规范化 + hash 兜底（3.3），重复上传不重复消费嵌入 API。
- 嵌入成本可选接入现有 `monitor.emit_cost` / 会话成本体系（不强求）。
- 保留全量重训按钮，UI 区分「增量入库」与「全量重建」，默认增量。

### 4.4 并行喂给两个索引
- 一次分块嵌入结果，同时追加到 VectorStore 与 SparseRetriever（同一份 chunk 元数据），保证两路召回一致、不漂移。

---

## 5. 混合检索升级与降级策略

### 5.1 稀疏检索可插拔后端
`SparseRetriever` 按 `SPARSE_BACKEND ∈ {memory, whoosh, sqlite_fts}`：
- `memory`（默认，数据量小时现状）：BM25Okapi。
- `whoosh`：纯 Python 全文索引，可配自定义 Analyzer（含中文分词，如 `ChineseAnalyzer`/jieba），检索质量更好、无需外部服务；索引构建略重。
- `sqlite_fts`：chunk 写入 SQLite FTS5 表 `MATCH` 查询；零服务、持久化；中文分词用默认 tokenizer，需评估命中质量。
- 默认推荐 `whoosh`+基础中文分词；`sqlite_fts` 作零依赖回退。RRF 融合、`top_k` 语义、`RetrievalResult` 结构保持不变，调用方无感知。

### 5.2 降级链（保持可用底线）
检索按序回退，日志标记当前档位：
1. `dense(HNSW) + sparse(whoosh)` 全开，RRF。
2. 稀疏索引缺失/构建失败 → `dense + sparse(memory BM25)`（现状）。
3. BM25 也缺失 → 仅 `dense(HNSW)`。
4. 向量索引也未构建 → 现状 `IndexNotFoundError` 提示。
`SPARSE_BACKEND=auto` 自动探测可用后端取最高档。

### 5.3 召回增强落点
叶块候选 → parent 上下文扩展（3.2） → 去重 → Reranker → Prompt；保证优化落在最终答案质量，而非仅换索引。

---

## 6. 配置项（`app/config.py` 新增）

| 配置 | 默认 | 含义 |
|---|---|---|
| `vector_index_type` | `"hnsw"` | flat / hnsw / ivf |
| `hnsw_m` / `hnsw_ef_construction` / `hnsw_ef_search` | 16 / 200 / 64 | HNSW 参数 |
| `ivf_nlist` | 200 | IVF 聚类数 |
| `chunk_size` / `chunk_overlap` / `min_chunk_size` | 600 / 80 / 100 | 分块参数 |
| `sparse_backend` | `"auto"` | memory / whoosh / sqlite_fts / auto |
| `concurrent_batches` | 4 | 嵌入并发路数 |
| `ingest_state_path` | `"data/ingest_state"`(或 Redis 命名空间) | 断点续传存储 |
| `enable_parent_expansion` | true | parent 上下文扩展开关 |

---

## 7. 错误处理与可观测
- 每层按可用档位降级，日志与既有 `grafana`/日志体系标记当前档位。
- 嵌入失败进失败清单、可重跑续传；首次成功阶段记录失败文档列表返回。
- 保持 OTel 可选启用、静默降级（现有 monitor/observability 不动倒，仅复用）。

---

## 8. 测试策略
- 索引档位召回一致性：同一查询下 flat vs hnsw 的 top-k 重合度断言。
- 分块回归：parent 扩展后 top-5 命中覆盖旧逻辑。
- 稀疏后端一致性：同一语料上 memory / whoosh / sqlite 的 top-k 候选重叠。
- 降级链：各缺失场景下 retrieve 不抛错、档位正确。
- 入库：幂等（重复灌入不膨胀）、断点续传、失败清单。
- 端到端：复用既有 eval_testset / Faithfulness 对比新旧召回质量。
- 并发：多并发 search 不被串行（延迟基线断言）。

---

## 9. 明确不做（YAGNI）
- 分布式向量库/Elasticsearch/Milvus（方案 B），当前规模单机够用。
- 本地嵌入模型（SiliconFlow API 沿用，前期已确认）。
- 量化索引档位（SQ/PQ）与 GPU 化——先稳稳吃下百万级全精度，内存告警时再加。
- 不新增重量级评测框架，复用现有 eval 机制。