# STORAGE_LAYER.md — 存储层契约 / 边界（Layer Contract）

> **Layer Contract / Layer Boundary**，不是代码使用说明。回答：这一层负责什么、不能负责什么。
> 适用目录：`app/storage/`。变更纪律（DoD）见 `SERVICES_LAYER.md` 头部，同理适用本契约。

## 1. Responsibility（职责）
- 持久化与检索原语：向量（FAISS）、chunk 文档、会话（Redis）、用户（Redis）、历史（SQLite）、面试/深挖数据。
- 连接生命周期、schema（含幂等迁移）、原子落盘与可重入恢复。

## 2. Input contract（输入契约）
- 接收来自服务层的领域对象 / 键（如 `session_id`、`username`、chunk 列表、向量）。
- 隔离维度 `username` 由上层透传，store **不做身份判断**，但按传入作用域读写。

## 3. Output contract（输出契约）
- 返回存储对象 / 检索结果（向量近似检索、消息列表、会话列表）。
- 返回结果不含连接 / 游标，可被服务层直接消费。

## 4. Decision ownership（决策所有权）
- 拥有：索引/存储格式、schema、连接管理、原子性与降级原语（如 Redis 不可用时的可用标记）。
- 不拥有：召回策略、缓存 key 语义、业务编排。

## 5. Allowed dependencies（允许依赖）
- `app/config.py`、`app/utils/*`（如文本切分仅供内部适度复用）、第三方客户端（redis/faiss/sqlite）。

## 6. Forbidden dependencies（禁止依赖）
- **禁止依赖 `app/services/*` 与 `app/api/*`**（不反向调用业务或感知 HTTP）。
- 禁止多个 store 之间直接横向互调（跨 store 会话需经服务层编排）。

## 7. Invariants（不变量）
- **单 worker 落盘**：FAISS/index/`ingest_state.json` 假定单进程，`--workers 1`（DR-002）。
- **原子 + 可重入**：`split_text` / `_save_state` / 索引写入须隔离单块失败，不拖垮整批（DR-001 / P009）。
- 会话 TTL 3600s、单会话 20 轮；Redis = 短期热数据，SQLite = 长期事实源（DR-010）。
- 会话/搜索按 `username` 隔离，删除时 Redis + SQLite 同步清（DR-010）。
- 外部依赖失败提供降级标记（Redis 不可用 → `cache.available=False`），不抛穿主流程。

## 8. Failure ownership（失败归属）
- 自己拥有读写失败的降级与恢复（如 Redis miss → SQLite 回填）。
- 存储异常向上抛出可识别的信号，由服务层决定降级，而非 API 层处理细节。

## 9. Testing expectations（测试期望）
- `tests/storage/` 单测：schema 迁移幂等、原子落盘、降级、隔离、规模（`test_faiss_store_scale.py`）。

## 10. Typical changes allowed here（允许在此的改动）
- 修正 schema、迁移逻辑、索引格式、原子性 / 可重入错误、连接参数。

## 11. Changes that must be implemented elsewhere（必须改在别处的改动）
- 缓存 key 语义 → `services/cache_service.py`。
- 召回 / 精排策略 → `services/`。
- 配置缺省（Redis 地址、TTL）→ `app/config.py`。