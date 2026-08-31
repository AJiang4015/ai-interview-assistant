# P006 — 索引陈旧 state 覆盖 / 单 worker 落盘约束

## Status

- ID：P006
- Severity：High
- Status：**Active（约束已固化，多 worker 并发锁未实现）**
- First identified：大规模 RAG 检索接入迭代期间
- Related Decision：DR-002（单 worker 落盘模型）
- Related Spec：`docs/superpowers/specs/2026-08-16-large-scale-rag-design.md`；PROBLEM.md Appendix Door 9
- Related Tests：索引幂等重建 / state 一致性测试（`tests/` 规模化回归）

---

## 1. Problem

FAISS 索引、`ingest_state.json`、运行态全局均假定**单进程**；多 worker / 并发场景下索引状态陈旧或被覆盖，且重建时缺少对陈旧 state 的强制处理。

## 2. Impact

- 并发 / 多 worker 下索引不一致：检索结果与文档不符、重启后状态异常。
- 索引文件存在但内容过期时，非 rebuild 路径不强制重建，检索可能命中陈旧数据（正确性问题）。

## 3. Evidence

- 约束固化提交：`a22cdf8`（"索引缺失时非 rebuild 强制重建覆盖陈旧 state 并声明单 worker 约束"）。
- 代码：`app/config.py` 与 `app/storage/faiss_store.py` / `index_service.py` 落盘路径注释声明单进程假定；`Dockerfile` 以 `--workers 1` 启动。

## 4. Root Cause

运行态全局（FAISS 内存索引、BM25、ingest_state）与落盘文件均为**进程级状态**，非进程间安全：多 worker 并发写会相互覆盖 / 读陈旧，而最初设计未声明这一约束，导致"看着能扩容、实际会坏数据"。

## 5. Decision / Solution

- **决策（DR-002）**：运行态全局与落盘（`ingest_state.json`、FAISS/index）假定**单 worker**；Docker 以 `--workers 1` 启动；多 worker 需另行补**进程级锁**或换**外部存储**后才可放开。
- 配套（`a22cdf8`）：索引缺失或 state 陈旧时强制重建覆盖，保证一致性优先于增量速度。

## 6. Implementation

- Dockerfile `CMD` 单 worker 启动；`config.py` / 落盘路径注释声明约束。
- `a22cdf8`：非 rebuild 路径遇陈旧 state 强制重建。

## 7. Regression / Verification

- 索引幂等重建 / 状态一致性回归测试通过（`tests/` 规模化回归）。
- 缺失项（Active 原因）：**多 worker 并发写入的进程级锁未实现**——当前仅靠部署纪律（`--workers 1`）保证，无代码级防线。

## 8. Current Status

Active（约束固化，规则已生效；多 worker 并发锁为未落地缺口）。继续以 DR-002 高压线维护于 `AGENTS.md` 与 `STORAGE_LAYER.md`。

## 9. Lessons

- 状态变更必须原子、可重入、可恢复：落盘（index / ingest_state）要么整体成功要么整体回滚，断电 / 异常后可重入续跑（[AUGMENT] 铁律 3）。
- "部署纪律型约束"（单 worker）必须与架构声明（DR-002）+ 落盘原子性（D8/D9）配套，否则多 worker 上线即坏数据。

## 10. Historical Record

- 曾出现：索引文件存在但检索结果与文档不符 / 重启后状态异常。
- Do Not Reopen Without Evidence：若并发 / 多 worker 下出现索引不一致，先确认是否绕过 `--workers 1` 部署，再检查落盘原子性是否被回退；不补进程级锁前不得直接放开多 worker。
