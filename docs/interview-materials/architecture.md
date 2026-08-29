# 系统架构说明（面试用）

> 配图：`architecture.svg`（可直接浏览器打开 / 拖入笔记 / 转 PNG）。
> 用途：讲清「检索底座 + 问答/面试两条消费链路」的整体结构。

---

## 架构图核心画面（口述版）

```
前端 SPA（原生 JS，SSE 流式）
   ↓
API 层：/api/query · /stream · /interview · /auth(JWT) · /eval · /sessions
   ↓
服务层
   ├─ 🌟 RetrievalFacade（统一检索门面）   ← Part B 核心
   │     query rewrite → hybrid(RRF) → rerank → parent expansion
   │     问答 & 面试共用这条已验证管线
   ├─ 业务服务：RAGService（问答/SSE）、InterviewService（AI 面试）、EvaluationService（评测）
   ├─ 横切：cache_service · eval_monitor(幻觉) · session_cost(成本) · monitor(OTel)
   ↓
存储层：FaissStore(向量) · SparseRetriever(BM25/Whoosh/SQLite) ·
        SessionStore(Redis 会话) · SearchStore(SQLite 历史) · DocStore · UserStore
   ↓
外部：百炼 LLM · 硅基 Embedding/Rerank · Redis · 可选 OTel/Grafana
```

## 分层依赖（Law of Layers）

`API → Services → Storage/Utils`，禁止反向/横向越界（各 `*_LAYER.md` 为契约）。

## 关键：RetrievalFacade 为什么是中心

- **好处 1 复用**：问答和面试不再各写一套检索，共用已被 Part A 消融验证的完整管线。
- **好处 2 策略隔离**：管线之下完全相同，差异只在 facade 之上——问答用原始问题、面试评价用「问题+回答」拼接。
- **好处 3 可测试**：facade 是唯一检索入口，单测可覆盖编排/降级；评测脚本 `eval_interview_{baseline,upgraded}.py` 直接打它。

## 数据流简述

1. **索引侧**：文档(md/pdf/docx) → 分块(1000/200) → Embedding → FAISS + 稀疏索引，断点续传入库。
2. **问答侧**：问题 → facade（改写→混合→重排→parent）→ 提示词(+会话历史) → LLM 流式 → 幻觉/成本评估 → 会话落 Redis。
3. **面试侧**：出题（facade 检索）→ 答题 → 评价（「问题+回答」再次 facade 检索，带来源溯源）→ 生成下一题/报告。（追问默认不检索，成本受控。）

## 为什么软件架构合理（一句话）

它把"检索质量"抽成一个**可评测、可复用、可降级**的独立底座，业务（问答/面试）作为消费方共享它——符合"分离稳定部分与变化部分"的分层思想，也让每次检索优化都能同时惠及全部业务。

---

## 被追问时的延伸点（配套材料）

- 检索链路细节 → 见 [关键技术决策说明](key-decisions.md)
- 检索质量量化过程（消融）→ 见 [Part B 复盘](../../docs/evaluation/2026-08-29-partB-retrieval-upgrade-review.md) 与 Part A spec
- 为什么面试检索迁移、而没继续优化出题 query → 见 [为何暂缓知识树 query](why-not-knowledge-tree-query.md) + Part C