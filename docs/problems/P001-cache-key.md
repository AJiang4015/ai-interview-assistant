# P001 — RAG 响应缓存 key 混入会话维度，命中率趋近 0

## Status

- ID：P001
- Severity：High
- Status：**Resolved**（2026-08-30 修复，commit `e41788e`）
- First identified：RAG 管道升级迭代期间
- Related Decision：DR-004（缓存 / 去重 key 基于不变语义）
- Related Spec：`docs/superpowers/plans/2026-08-12-rag-pipeline-upgrade-plan.md`；PROBLEM.md Appendix Door 5
- Related Tests：`tests/services/test_cache_service.py`（6 个回归用例，随 `e41788e` 新增）

---

## 1. Problem

相同问题多次提问时，响应基本每次都重新生成，`Cache hit` 日志几乎不出现，缓存命中率趋近 0。

## 2. Impact

- 缓存形同虚设：相同查询重复消耗 LLM / Embedding token 与成本（放大 P011 的成本预算告警）。
- 命中率每下降 10%，相同流量下 LLM 支出近似反比上升，高频重复问题放大最明显。

## 3. Evidence

- 代码（修复前）：`make_key` = `md5(f"{question}|{session_id}|{msg_count}")`（`app/services/cache_service.py:28-31` 旧实现）。
- 观测：日志中 `Cache hit` 几乎不出现；相同问题重复提问仍走完整 LLM 生成链路。
- 定性结论：key 同时含 `session_id` 与 `msg_count`，二者任一变化即生成新 key；只有"同一会话 + 同一轮次"才可能命中 → 命中率 ≈ 0。未做线上压测，命中率提升幅度为估算（相同问题跨会话复用理论上可到 ≈90%+，受 TTL 与首次提问影响）。

## 4. Root Cause

缓存 key 混入 `session_id` 与 `msg_count` 两个**易变化维度**：会话不同或轮次计数不同即生成全新 key；而业务上恰需要"相同问题跨会话 / 轮次复用"，形成根本矛盾。

初版设计为了让缓存跟随会话上下文变化（多轮历史的答案不同），但未区分"应该事实性复用"与"应随上下文变化的回答"，把变化维度无条件并入了 key。

**流程根因**（为什么没被评审拦下）：缺失"缓存 key 维度审查标准"；交付时无 `cache_hit_rate` 度量，也没有"相同问题命中"的单元 / 集成测试，导致缺陷无声合入且上线后无告警识别。

## 5. Decision / Solution

- **决策（DR-004）**：cache key 只基于**原始用户问题**哈希，去除会话 / id / 序数等一切可变维度；把"跟随上下文"交给 LLM 生成层，而不是缓存维度。
- 备选方案对比：
  - ✅ 方案 A（采用）"仅原始问题"：`key = md5(question)`。命中收益 > 个性化损失，TTL 3600s 防陈旧。
  - ❌ 方案 B（否定）"原始问题 + 意图摘要"：额外一次 LLM 调用 + 摘要非确定性，收益不确定而复杂度明显。
  - ❌ 方案 C（否定）"保留会话维度仅缩小范围"：本质与现实现相同，已证伪。

## 6. Implementation

commit `e41788e`（`fix(cache): 响应缓存 key 仅基于原始问题`）：

```python
def make_key(self, question: str, _session_id: str = "", _msg_count: int = 0) -> str:
    # DR-004 / P001：缓存 key 只基于原始问题原文。
    # session_id / msg_count 等可变维度一律不参与，使相同问题可跨会话、跨轮次命中。
    h = hashlib.md5(question.encode("utf-8")).hexdigest()
    return f"{self._prefix}{h}"
```

参数保留 `_session_id` / `_msg_count` 仅为向后兼容调用点，不参与 key 计算。

## 7. Regression / Verification

`tests/services/test_cache_service.py`（随 `e41788e` 新增 6 个用例，全部通过）：

- `test_make_key_same_question_cross_session_same_key`：相同问题、不同 session / msg_count → 必须命中同一 key（P001 核心回归）。
- `test_make_key_different_question_different_key`：不同问题 → 不同 key。
- `test_make_key_removes_session_and_msg_count_from_hash_input`：key 值不得沾有 session_id / msg_count 的明文痕迹。
- `test_make_key_uses_configured_prefix`、`test_available_false_without_store`（Redis 不可用 → 缓存降级不可用）、`test_available_true_with_connected_store`。

验证方式：同一问题在 A 会话提出后再在 B 会话首次提问，应命中并直接返回缓存答案（`Cache hit` 日志出现、不触发 LLM 流）。

## 8. Current Status

已修复并带回归测试。`PROBLEM.md` 注册表状态：Resolved。缓存 key 铁律（DR-004）继续作为高压线维护于 `AGENTS.md` 铁律与 `SERVICES_LAYER.md` 不变量。

## 9. Lessons

- 缓存 / 幂等 / 去重 key 只能取自"业务上稳定不变"的维度（原始问题原文），绝不能混入易变化状态变量（session_id、消息序数、时间戳、随机数）——已抽象为 [AUGMENT] 铁律 1。
- 这类"看着能跑、线上才显形"的缺陷，靠直觉审查拦不住；必须靠指标（hit rate）+ 回归测试兜底（对应 Door 5 的落地形态）。

## 10. Historical Record

- 修复前完整调查路径：`make_key` 实现 → 确认含可变维度 → 核对记忆约束"Response cache keys must use the original user question" → 改 key → 补回归。
- 曾尝试的失败路径：在 key 中追加 `session_id` / `msg_count`（即旧实现本身）——不会提升命中，反而制造更多孤立缓存。
- Do Not Reopen Without Evidence：若再次出现"缓存完全不命中"，先验证 `make_key` 是否确实去掉了 session_id / msg_count，再检查是否存在代码回退，不要直接改回旧含会话维度的 key。
