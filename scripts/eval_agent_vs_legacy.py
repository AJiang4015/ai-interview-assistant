"""W2 下评测：legacy vs agent（同一批 data/eval_interview_subset.json 17 条）。

指标（先原始结果，不调参）：
1. recall@3 / MRR —— 共享检索管线（RetrievalFacade，legacy/agent 同一套，Part B）上对 17 条 query 计算；
2. legacy vs agent 主问题单题分分布（均值/方差）—— 真实 LLM 各跑一个会话（4 轮）；
3. agent 追问合理性人工抽样 5 条（输出待人工标注，目标 ≥4/5）；
4. trace assertions：状态流转合法率 100% / retries ≤ 上限 / schema→fallback 有记录 /
   tool latency 有记录 / escape_reason 与 escape 事件一致。

运行（需注入 Machine 级 BAILIAN/SILICONFLOW key，不落盘）：
    $env:BAILIAN_API_KEY=[Environment]::GetEnvironmentVariable('BAILIAN_API_KEY','Machine')
    $env:SILICONFLOW_API_KEY=[Environment]::GetEnvironmentVariable('SILICONFLOW_API_KEY','Machine')
    python scripts/eval_agent_vs_legacy.py
"""

import asyncio
import json
import statistics
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.storage.faiss_store import FaissStore  # noqa: E402
from app.services.embedding import EmbeddingService  # noqa: E402
from app.services.sparse_retriever import SparseRetriever  # noqa: E402
from app.services.retrieval_service import HybridRetriever  # noqa: E402
from app.services.rerank_service import RerankService  # noqa: E402
from app.services.query_rewrite import QueryRewriteService  # noqa: E402
from app.services.retrieval_facade import RetrievalFacade  # noqa: E402
from app.services.llm_client import LLMClient  # noqa: E402
from app.services.interview_service import InterviewService  # noqa: E402
from app.services.topic_tracker import TopicTracker  # noqa: E402
from app.storage.interview_store import InterviewStore  # noqa: E402

LONG_ANSWER = "结合我的项目实践，这个问题的核心要点是稳定性与性能的权衡，我会从原理、实现、边界三个方面展开说明：" + "x" * 400
SHORT_ANSWER = "我了解一些，但想再确认一下细节。"


def topic_answer(qid, store) -> str:
    """主题锚定回答（评测输入：半真实内容，避免通用模板触底，非调参）。"""
    q = store.get_question(qid)
    topic = (q or {}).get("topic") or "该知识点"
    return (
        f"关于「{topic}」这个主题，我理解其核心机制包括初始化、状态管理与边界条件处理；"
        "实际项目里我会结合业务场景做权衡，先保证正确性再优化性能，并补充必要的监控与回退。"
    )


def load_subset() -> list[dict]:
    data = json.loads(Path("data/eval_interview_subset.json").read_text(encoding="utf-8"))
    return data


def build_facade() -> RetrievalFacade:
    """复刻 app.main 检索装配（真实索引 + 真实 embedding/rerank）。"""
    faiss_store = FaissStore()
    if (Path(settings.idx_path) / "index.faiss").exists():
        faiss_store.load(settings.idx_path)
    else:
        raise RuntimeError("FAISS index missing")
    embedding = EmbeddingService()
    llm = LLMClient()
    qr = QueryRewriteService(llm=llm, enabled=settings.enable_query_rewrite)
    sparse = SparseRetriever(backend=settings.sparse_backend)
    if faiss_store.is_loaded():
        meta = faiss_store.get_all_metadata()
        if meta:
            sparse.add_documents([
                {"_id": m.get("_id", i), "content": m.get("content", ""),
                 "source_file": m.get("source_file", ""), "chunk_index": m.get("chunk_index", 0)}
                for i, m in enumerate(meta)
            ])
    hybrid = HybridRetriever(
        faiss_store=faiss_store, embedding=embedding,
        bm25_index_path=settings.bm25_index_path, enabled=settings.enable_hybrid_search, sparse=sparse,
    )
    hybrid.load_bm25()
    rerank = RerankService(
        api_key=settings.siliconflow_api_key, model_name=settings.rerank_model,
        enabled=settings.enable_rerank,
    )
    return RetrievalFacade(
        faiss_store=faiss_store, embedding=embedding, query_rewriter=qr,
        hybrid_retriever=hybrid, reranker=rerank,
    )


async def retrieval_metrics(facade, items):
    """recall@3 / MRR（共享检索管线，legacy/agent 同一套）。"""
    ranks = []
    for it in items:
        try:
            res = await facade.retrieve(it["query"], top_k=3)
            files = [s.file for s in res.sources][:3]
        except Exception as e:
            print("  retrieve fail:", it["query"][:30], e)
            files = []
        expected = it["expected_source"]
        rank = next((i + 1 for i, f in enumerate(files) if f == expected), None)
        ranks.append(rank)
    recall = sum(1 for r in ranks if r is not None) / len(ranks)
    mrr = sum(1 / r for r in ranks if r is not None) / len(ranks)
    return recall, mrr, ranks


async def collect_scores(mode: str, facade, n_rounds: int = 4) -> list[float]:
    """真实 LLM 会话：收集主问题单题分。"""
    db = str(PROJECT_ROOT / "data" / "agent_smoke" / f"eval_{mode}.db")
    store = InterviewStore(db_path=db)
    tracker = TopicTracker(interview_store=store, tree_dir=str(PROJECT_ROOT / "data" / "knowledge_trees"))
    scores: list[float] = []
    if mode == "legacy":
        svc = InterviewService(store, LLMClient(), facade=facade, topic_tracker=tracker)
        res = await svc.start("Java后端", username="eval")
        qid = res["question"]["id"]
        for _ in range(n_rounds):
            ans = await svc.answer(qid, topic_answer(qid, store), username="eval")
            scores.append(float(ans["evaluation"]["score"]))
            if ans.get("is_complete"):
                break
            nq = ans.get("next_question")
            if not nq:
                break
            qid = nq["id"]
    else:
        from app.services.agent.agent_service import build_agent_service
        from app.services.agent.state_machine import EscapeHatchConfig

        svc = build_agent_service(
            store=store, llm=LLMClient(), facade=facade, topic_tracker=tracker,
            trace_dir=str(PROJECT_ROOT / "data" / "agent_smoke" / "traces_eval"),
            escape_config=EscapeHatchConfig(max_rounds=n_rounds),
        )
        res = await svc.start("Java后端", username="eval")
        qid = res["question"]["id"]
        for _ in range(n_rounds):
            ans = await svc.answer(qid, topic_answer(qid, store), username="eval")
            scores.append(float(ans["evaluation"]["score"]))
            if ans.get("is_complete"):
                break
            nq = ans.get("next_question")
            if not nq:
                break
            qid = nq["id"]
    return scores


async def collect_followups(facade, limit: int = 5) -> list[dict]:
    """agent 追问样本（短答触发追问），供人工标注合理性。"""
    from app.services.agent.agent_service import build_agent_service
    from app.services.agent.state_machine import EscapeHatchConfig

    db = str(PROJECT_ROOT / "data" / "agent_smoke" / "eval_followup.db")
    store = InterviewStore(db_path=db)
    tracker = TopicTracker(interview_store=store, tree_dir=str(PROJECT_ROOT / "data" / "knowledge_trees"))
    svc = build_agent_service(
        store=store, llm=LLMClient(), facade=facade, topic_tracker=tracker,
        trace_dir=str(PROJECT_ROOT / "data" / "agent_smoke" / "traces_eval"),
        escape_config=EscapeHatchConfig(max_rounds=10),
    )
    res = await svc.start("Java后端", username="eval")
    qid = res["question"]["id"]
    samples: list[dict] = []
    for _ in range(30):
        if len(samples) >= limit:
            break
        ans = await svc.answer(qid, SHORT_ANSWER, username="eval")
        nq = ans.get("next_question")
        if nq is None:
            break
        if nq.get("source") == "followup":
            samples.append({"main": qid, "followup": nq["content"]})
            ans2 = await svc.answer(nq["id"], "追问回答：这个要看具体场景，一般会权衡性能和一致性，细节上需要注意边界条件。", username="eval")
            nq2 = ans2.get("next_question")
            if not nq2:
                break
            qid = nq2["id"]
        else:
            qid = nq["id"]
    return samples


def check_trace_assertions(trace_dir: Path) -> dict:
    """trace assertions（附录 I E3）：状态流转合法率 / retries / fallback / latency / escape。"""
    from app.services.agent.state_machine import AgentState, TRANSITIONS

    allowed_pairs = {(t.from_state, t.to_state) for t in TRANSITIONS}
    state_names = {s.value for s in AgentState}
    total_transitions = 0
    illegal = 0
    retries_over = 0
    node_finished = 0
    schema_fail_no_fallback = 0
    tool_calls_total = 0
    tool_latency_missing = 0
    escape_events = []
    sessions = {}

    for tf in trace_dir.glob("*.jsonl"):
        prev_state = "init"
        for line in tf.read_text(encoding="utf-8").strip().splitlines():
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            ev = rec["event"]
            if ev == "transition":
                total_transitions += 1
                cur = rec.get("state")
                sessions.setdefault(tf.stem, []).append(cur)
                # 状态流转合法：来源→目标 必须存在于转移表（来源 = 上一条 transition 的目标/INIT）
                try:
                    legal = (
                        cur in state_names
                        and (AgentState(prev_state), AgentState(cur)) in allowed_pairs
                    )
                except ValueError:
                    legal = False
                if not legal:
                    illegal += 1
                prev_state = cur
            elif ev == "node_finished":
                node_finished += 1
                if rec.get("retries", 0) > 2:  # attempts≤3 → retries≤2
                    retries_over += 1
                if rec.get("validated") is False and not rec.get("fallback_used"):
                    schema_fail_no_fallback += 1
            elif ev == "tool_call":
                tool_calls_total += 1
                calls = rec.get("tool_calls") or []
                if not calls or all(c.get("latency_ms") is None for c in calls):
                    tool_latency_missing += 1
            elif ev == "escape":
                escape_events.append(rec.get("fallback_used"))
    return {
        "total_transitions": total_transitions,
        "illegal_transitions": illegal,
        "transition_legality_rate": (total_transitions - illegal) / max(total_transitions, 1),
        "node_finished": node_finished,
        "retries_over_limit": retries_over,
        "schema_fail_no_fallback": schema_fail_no_fallback,
        "tool_calls_total": tool_calls_total,
        "tool_latency_missing": tool_latency_missing,
        "escape_events": escape_events,
    }


async def main() -> None:
    print("=== W2 下评测：legacy vs agent（17 条子集）===", flush=True)
    items = load_subset()
    print(f"子集条目：{len(items)}（出题 {sum(1 for i in items if i['sample_type']=='出题形态')} / 评价 {sum(1 for i in items if i['sample_type']=='评价形态')}）")

    facade = build_facade()

    results: dict = {"subset": len(items)}

    print("\n--- 1. recall@3 / MRR（共享检索管线）---", flush=True)
    try:
        recall, mrr, ranks = await retrieval_metrics(facade, items)
        hits = [r for r in ranks if r is not None]
        print(f"recall@3 = {recall:.3f}（{len(hits)}/{len(items)} 命中）")
        print(f"MRR = {mrr:.3f}")
        results.update({"recall@3": recall, "MRR": mrr, "hits": hits})
    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print("section 1 FAILED:", e)

    print("\n--- 2. legacy vs agent 单题分分布（真实 LLM，各 3 轮）---", flush=True)
    for mode in ("legacy", "agent"):
        try:
            scores = await collect_scores(mode, facade, n_rounds=3)
            mean = statistics.mean(scores) if scores else float("nan")
            var = statistics.variance(scores) if len(scores) > 1 else 0.0
            print(f"{mode}: n={len(scores)} mean={mean:.2f} var={var:.2f} scores={scores}", flush=True)
            results[f"{mode}_scores"] = scores
        except Exception as e:  # noqa: BLE001
            import traceback

            traceback.print_exc()
            print(f"section 2 {mode} FAILED:", e)

    print("\n--- 3. agent 追问样本（5 条，人工标注合理性，目标 ≥4/5）---", flush=True)
    try:
        samples = await collect_followups(facade)
        for i, s in enumerate(samples, 1):
            print(f"  [{i}] 追问：{s['followup']}")
        results["followup_samples"] = samples
    except Exception as e:  # noqa: BLE001
        import traceback

        traceback.print_exc()
        print("section 3 FAILED:", e)

    print("\n--- 4. trace assertions ---", flush=True)
    tr = check_trace_assertions(PROJECT_ROOT / "data" / "agent_smoke" / "traces_eval")
    for k, v in tr.items():
        print(f"  {k} = {v}")
    results["trace_assertions"] = tr

    out = PROJECT_ROOT / "data" / "eval_reports" / "agent_vs_legacy_w2.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n原始结果落盘：{out}")


if __name__ == "__main__":
    asyncio.run(main())
