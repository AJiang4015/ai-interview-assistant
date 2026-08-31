"""W3 Phase 1：5 分钟面试官 Demo 脚本（真实 LLM，正式 Agent 装配，可复现）。

运行（注入 Machine 级密钥，不落盘）：
    $env:BAILIAN_API_KEY=[Environment]::GetEnvironmentVariable('BAILIAN_API_KEY','Machine')
    $env:SILICONFLOW_API_KEY=[Environment]::GetEnvironmentVariable('SILICONFLOW_API_KEY','Machine')
    $env:REDIS_PASSWORD=...   # 可选：提供则跨会话画像走真实 Redis，否则会话内
    python scripts/agent_w3_demo.py

演示目标（对应 W3 Phase 1）：
1. 正常 Agent 面试流程（出题→回答→追问→评估→难度调整→报告）
2. 自适应 FOLLOWUP（短答触发追问，追问答合并评估）
3. Trace 归因（事件分布 + 四象限讲解锚点）
4. 确定性故障降级（LLM 挂→G1-F/G4-F→逃生舱；RAG 挂→工具 degrade）
5. 跨会话画像影响（低分会话→画像→新会话 INIT 注入难度/薄弱点）

约束：仅驱动现有装配（build_agent_service），不修改 Agent Core、不新增业务逻辑。
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402
from app.services.llm_client import LLMClient  # noqa: E402
from app.services.topic_tracker import TopicTracker  # noqa: E402
from app.storage.interview_store import InterviewStore  # noqa: E402

LONG_ANSWER = (
    "结合我的项目实践，我认为核心是先保证正确性再考虑性能：我会先说明原理与数据结构，"
    "再讲实际项目里的取舍（比如读写比例、缓存一致性），最后补充边界条件与监控回退。" + "x" * 260
)
SHORT_ANSWER = "我了解大概，但细节想再确认一下。"


def hr(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}", flush=True)


def build_facade():
    """真实检索装配（复用 eval 脚本）。"""
    from scripts.eval_agent_vs_legacy import build_facade as _build_facade

    return _build_facade()


def build_stack(store, llm, facade, profile_store, max_rounds=2):
    from app.services.agent.agent_service import build_agent_service
    from app.services.agent.state_machine import EscapeHatchConfig

    tracker = TopicTracker(interview_store=store, tree_dir=str(PROJECT_ROOT / "data" / "knowledge_trees"))
    return build_agent_service(
        store=store, llm=llm, facade=facade, topic_tracker=tracker,
        profile_store=profile_store,
        trace_dir=settings.agent_trace_dir, trace_retention=200,
        escape_config=EscapeHatchConfig(max_rounds=max_rounds),
    )


def profile_store():
    from app.services.agent.profile_store import make_profile_store

    return make_profile_store(
        host=settings.redis_host, port=settings.redis_port, db=settings.redis_db,
        password=os.environ.get("REDIS_PASSWORD") or None, timeout=3.0,
    )


async def section_1_normal_and_followup(facade, pstore) -> str:
    """正常流程 + 自适应 FOLLOWUP（真实 LLM）。返回 session_id。"""
    hr("【1/5】正常 Agent 面试流程 + 自适应 FOLLOWUP（真实 LLM）")
    store = InterviewStore(db_path=str(PROJECT_ROOT / "data" / "agent_smoke" / "demo1.db"))
    svc = build_stack(store, LLMClient(), facade, pstore, max_rounds=2)
    res = await svc.start("Java后端", username="demo_user")
    sid = res["session_id"]
    print(f">> 出题（round1）：{res['question']['content']}")
    print(f"  topic={res['question']['topic']} difficulty={res['question']['difficulty']} source={res['question']['source']}")

    # 短答 → 触发追问
    ans = await svc.answer(res["question"]["id"], SHORT_ANSWER, username="demo_user")
    fu = ans.get("next_question")
    print(f">> 短答 → 自适应 FOLLOWUP：{'是' if fu and fu.get('source') == 'followup' else '否'}")
    if fu:
        print(f"  追问：{fu['content']}  （source={fu['source']}，独立 question_id）")
        print(f"  主答评估：score={ans['evaluation']['score']}")

        # 追问答 → 合并最终评估 + 下一题
        ans2 = await svc.answer(fu["id"], "追问回答：这个要看具体场景，一般会权衡性能和一致性，注意边界条件。", username="demo_user")
        print(f">> 追问答 → 合并最终评估：score={ans2['evaluation']['score']}")
        nq = ans2.get("next_question")
        if nq:
            print(f">> 出题（round2）：{nq['content']}")
            print(f"  难度调整后 difficulty={nq['difficulty']}")
            # 长答 → 不再追问 → 评估 → 收尾
            ans3 = await svc.answer(nq["id"], LONG_ANSWER, username="demo_user")
            print(f">> round2 评估：score={ans3['evaluation']['score']}")
            if ans3.get("is_complete"):
                print(f">> 面试结束：report.total_score={ans3['report']['total_score']} level={ans3['report']['level']}")
            else:
                nq3 = ans3.get("next_question")
                if nq3:
                    print(f">> 出题（round3）：{nq3['content']}")
                    ans4 = await svc.answer(nq3["id"], LONG_ANSWER, username="demo_user")
                    print(f">> round3 评估：score={ans4['evaluation']['score']} is_complete={ans4.get('is_complete')}")
    else:
        print(f"  主答评估：score={ans['evaluation']['score']}（未触发追问）")
    print(f">> trace 文件：{Path(settings.agent_trace_dir) / sid}.jsonl")
    return sid


def section_2_trace(sid: str) -> None:
    """Trace 归因：事件分布 + 四象限讲解锚点。"""
    hr("【2/5】Trace 归因（只读）")
    tf = Path(settings.agent_trace_dir) / f"{sid}.jsonl"
    if not tf.exists():
        print("trace 文件不存在")
        return
    events = [json.loads(l) for l in tf.read_text(encoding="utf-8").strip().splitlines()]
    kinds: dict[str, int] = {}
    for e in events:
        kinds[e["event"]] = kinds.get(e["event"], 0) + 1
    print(f"事件分布（共 {len(events)} 条）：{kinds}")
    print("归因四象限锚点：")
    print("  · 模型能力 → node_finished.model / raw_output / validated")
    print("  · 流程设计 → transition 序列 / retries / escape")
    print("  · 数据质量 → tool_call(kb_retrieve) 命中与否 / input_summary")
    print("  · 评估方式 → fallback_used（eval_rule vs LLM 分）/ validated")
    sample = next((e for e in events if e["event"] == "fallback"), None)
    if sample:
        print(f"  样本 fallback 事件：{json.dumps(sample, ensure_ascii=False)[:200]}")


async def section_3_degradation(pstore) -> None:
    """确定性故障降级：LLM 挂 → G1-F/G4-F → 逃生舱；RAG 挂 → 工具 degrade。"""
    hr("【3/5】确定性故障降级")
    from app.services.agent.agent_service import build_agent_service
    from app.services.agent.state_machine import EscapeHatchConfig

    class _FailingLLM:
        """LLM 挂（确定性）：所有调用抛错。"""

        async def chat(self, prompt, system=None, session_id=None, model=None):
            raise RuntimeError("LLM provider down (simulated)")

    class _FailingFacade:
        async def retrieve(self, query, top_k=5):
            raise RuntimeError("RAG down (simulated)")

    # 3a LLM 挂 → G1-F 兜底题 → G4-F 规则分 → 逃生舱收尾
    store = InterviewStore(db_path=str(PROJECT_ROOT / "data" / "agent_smoke" / "demo3a.db"))
    tracker = TopicTracker(interview_store=store, tree_dir=str(PROJECT_ROOT / "data" / "knowledge_trees"))
    svc = build_agent_service(
        store=store, llm=_FailingLLM(), facade=None, topic_tracker=tracker, profile_store=pstore,
        trace_dir=settings.agent_trace_dir,
        escape_config=EscapeHatchConfig(max_rounds=5, max_consecutive_failures=1),
    )
    res = await svc.start("Java后端", username="demo_user")
    print(">> LLM 挂 → 出题走 G1-F 确定性兜底：", res["question"]["content"][:50], "...")
    ans = await svc.answer(res["question"]["id"], LONG_ANSWER, username="demo_user")
    print(f">> 评估走 G4-F 规则分：score={ans['evaluation']['score']} fallback={ans['evaluation'].get('fallback')}")
    print(f">> 连续失败触发逃生舱 → 强制收尾：is_complete={ans.get('is_complete')}")

    # 3b RAG 挂 → kb_retrieve 工具 degrade（出题仍走真实 LLM，无上下文）
    store2 = InterviewStore(db_path=str(PROJECT_ROOT / "data" / "agent_smoke" / "demo3b.db"))
    svc2 = build_agent_service(
        store=store2, llm=LLMClient(), facade=_FailingFacade(), topic_tracker=tracker, profile_store=pstore,
        trace_dir=settings.agent_trace_dir,
        escape_config=EscapeHatchConfig(max_rounds=1),
    )
    res2 = await svc2.start("Java后端", username="demo_user")
    print(f">> RAG 挂 → kb_retrieve degrade（无上下文出题，流程不断）：{res2['question']['content'][:40]}...")


async def section_4_cross_session_profile(pstore) -> None:
    """跨会话画像影响：低分会话 → 画像 → 新会话 INIT 注入难度/薄弱点。"""
    hr("【4/5】跨会话画像影响")
    from app.services.agent.agent_service import build_agent_service
    from app.services.agent.state_machine import EscapeHatchConfig

    class _MockLLM:
        """确定性 mock：Session A 固定低分（3），Session B 捕获 prompt。"""

        def __init__(self, score=None, capture=None):
            self.score = score
            self.capture = capture

        async def chat(self, prompt, system=None, session_id=None, model=None):
            if self.capture is not None and '"score_reason"' not in prompt:
                self.capture["prompt"] = prompt
            if '"score_reason"' in prompt and self.score is not None:
                return (f'{{"score": {int(self.score)}, "comment": "c", "score_reason": "r", '
                        '"reference_answer": "ref", "tags": ["JVM"]}}')
            return ('{"question": "什么是 JVM 内存模型？", "difficulty": "medium", '
                    '"knowledge_tags": ["JVM"], "topic": "JVM", "category": "JVM"}')

    tracker = TopicTracker(
        interview_store=InterviewStore(db_path=str(PROJECT_ROOT / "data" / "agent_smoke" / "demo4.db")),
        tree_dir=str(PROJECT_ROOT / "data" / "knowledge_trees"),
    )
    import uuid as _uuid

    user = f"demo_profile_{_uuid.uuid4().hex[:8]}"  # 每次运行独立用户，避免历史画像污染演示
    # Session A：低分 → 画像写库（Redis 或会话内）
    store_a = InterviewStore(db_path=str(PROJECT_ROOT / "data" / "agent_smoke" / "demo4a.db"))
    svc_a = build_agent_service(
        store=store_a, llm=_MockLLM(score=3), facade=None, topic_tracker=tracker, profile_store=pstore,
        trace_dir=settings.agent_trace_dir, escape_config=EscapeHatchConfig(max_rounds=1),
    )
    res_a = await svc_a.start("Java后端", username=user)
    await svc_a.answer(res_a["question"]["id"], LONG_ANSWER, username=user)
    prof = pstore.get(user)
    print(f">> Session A（低分）→ 画像：accuracy={prof.get('accuracy')} weak_points={prof.get('weak_points')} level={prof.get('level')}")

    # Session B：INIT 注入（capture prompt）
    captured = {}
    store_b = InterviewStore(db_path=str(PROJECT_ROOT / "data" / "agent_smoke" / "demo4b.db"))
    svc_b = build_agent_service(
        store=store_b, llm=_MockLLM(capture=captured), facade=None, topic_tracker=tracker, profile_store=pstore,
        trace_dir=settings.agent_trace_dir, escape_config=EscapeHatchConfig(max_rounds=1),
    )
    res_b = await svc_b.start("Java后端", username=user)
    prompt = captured.get("prompt", "")
    print(f">> Session B INIT 注入：目标难度={'easy' if '目标难度：easy' in prompt else '非easy'} "
          f"薄弱点={'已注入' if ('薄弱点' in prompt and 'JVM' in prompt) else '未注入'}")
    print(f"  prompt 片段：{prompt[:120]}...")


async def section_5_reanswer(pstore, facade) -> None:
    """generate_next=False 再答一次：同题重评、状态不推进。"""
    hr("【5/5】generate_next=false 再答一次")
    store = InterviewStore(db_path=str(PROJECT_ROOT / "data" / "agent_smoke" / "demo5.db"))
    svc = build_stack(store, LLMClient(), facade, pstore, max_rounds=1)
    res = await svc.start("Java后端", username="demo_user")
    qid = res["question"]["id"]
    ans = await svc.answer(qid, LONG_ANSWER, generate_next=False, username="demo_user")
    print(f">> 再答一次（generate_next=false）：next_question={ans.get('next_question')}（应为 None，状态不推进）")
    ans2 = await svc.answer(qid, LONG_ANSWER + "（补充：我会再讲一下异常路径的处理）", username="demo_user")
    print(f">> 随后正常推进：is_complete={ans2.get('is_complete')} score={ans2['evaluation']['score']}")


async def main() -> None:
    if "BAILIAN_API_KEY" not in os.environ:
        print("需要注入 BAILIAN_API_KEY（运行前从 Machine 级环境变量读取注入，不落盘）。")
        raise SystemExit(1)
    print("Demo 前置：", {
        "BAILIAN_API_KEY": "已注入",
        "SILICONFLOW_API_KEY": "已注入" if "SILICONFLOW_API_KEY" in os.environ else "未注入（检索上下文为空）",
        "REDIS_PASSWORD": "已注入（画像走真实 Redis）" if os.environ.get("REDIS_PASSWORD") else "未注入（画像走会话内降级）",
        "FAISS index": "存在" if (Path(settings.idx_path) / "index.faiss").exists() else "缺失",
    })

    facade = build_facade()
    pstore = profile_store()

    sid = await section_1_normal_and_followup(facade, pstore)
    section_2_trace(sid)
    await section_3_degradation(pstore)
    await section_4_cross_session_profile(pstore)
    await section_5_reanswer(pstore, facade)

    hr("Demo 结束")
    print("· Trace 查看：打开 http://127.0.0.1:8000/agent-trace.html 输入上面的 session_id")
    print("· 或直接 GET /api/agent/traces/{session_id}")


if __name__ == "__main__":
    asyncio.run(main())
