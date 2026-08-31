"""W1 Day 4：orchestrator 集成测试（完整状态流 / FOLLOWUP / 同题重评 / fallback /
tool degrade / escape hatch / 非法转移 / trace 事件）。全部 mock LLM。"""

import json

import pytest

from app.services.agent.state_machine import AgentState, EscapeHatch, EscapeHatchConfig
from tests.services.agent._helpers import build_stack


async def _start(s):
    return await s["svc"].start("Java后端", username="u1")


# ---------------------------------------------------------------- 1. 正常完整状态流

@pytest.mark.asyncio
async def test_normal_complete_flow(env_dir):
    s = build_stack(env_dir, max_rounds=1)
    res = await _start(s)
    sid, qid = res["session_id"], res["question"]["id"]
    assert s["orch"].get_state(sid) is AgentState.AWAITING_ANSWER

    # 长回答（≥200 字符）→ ¬G9 → EVALUATING → DIFFICULTY_ADJ → (round>=max) SUMMARIZING → END
    ans = await s["svc"].answer(
        qid, "JVM 内存模型包含程序计数器、虚拟机栈、本地方法栈、堆、方法区。" * 10, username="u1",
    )
    assert ans["is_complete"] is True
    assert ans["report"]["total_score"] == 7.0
    assert ans["evaluation"]["score"] == 7
    assert s["orch"].get_state(sid) is AgentState.END
    # 报告落库
    assert s["store"].get_session(sid)["status"] == "completed"


# ---------------------------------------------------------------- 2. FOLLOWUP 流 + 持久化

@pytest.mark.asyncio
async def test_followup_flow_and_persistence(env_dir):
    s = build_stack(env_dir, max_rounds=2)
    res = await _start(s)
    sid, qid = res["session_id"], res["question"]["id"]

    # 短答 → G9 → 主答评估 + next_question=追问题
    ans1 = await s["svc"].answer(qid, "答得比较简短", username="u1")
    assert ans1["is_complete"] is False
    assert ans1["evaluation"]["score"] == 7  # 主答评估
    nq = ans1["next_question"]
    assert nq is not None and nq["id"] != qid
    assert nq["source"] == "followup"  # A6：前端不感知 FOLLOWUP，但行标记 source
    assert nq["round"] == res["question"]["round"]

    # 持久化：主答 + 追问答 两行，追问行 topic/category 留空
    qs = s["store"].get_questions(sid)
    main_rows = [q for q in qs if q["source"] != "followup"]
    fu_rows = [q for q in qs if q["source"] == "followup"]
    assert len(main_rows) == 1 and len(fu_rows) == 1
    assert fu_rows[0]["topic"] == "" and fu_rows[0]["category"] == ""

    # 追问答 → 合并最终评估 + 下一主题题（round 2）
    ans2 = await s["svc"].answer(nq["id"], "因为分段锁粒度太粗，锁竞争激烈", username="u1")
    assert ans2["is_complete"] is False
    assert ans2["evaluation"]["score"] == 7  # 最终评估
    nq2 = ans2["next_question"]
    assert nq2 is not None and nq2["round"] == 2 and nq2["source"] != "followup"

    # 主答行被更新为最终评估
    main_row = s["store"].get_question(qid)
    assert main_row["evaluation"]["score"] == 7

    # round 2 回答 → round>=max → 收尾
    ans3 = await s["svc"].answer(nq2["id"], "第二题回答，内容足够长避免追问：" + "x" * 300, username="u1")
    assert ans3["is_complete"] is True and ans3["report"]["total_score"] is not None


# ---------------------------------------------------------------- 3. generate_next=false 同题重评

@pytest.mark.asyncio
async def test_generate_next_false_reanswer(env_dir):
    s = build_stack(env_dir, max_rounds=2)
    res = await _start(s)
    sid, qid = res["session_id"], res["question"]["id"]

    ans = await s["svc"].answer(qid, "第一次回答，内容足够长避免追问：" + "y" * 300, generate_next=False, username="u1")
    assert ans["is_complete"] is False
    assert ans["next_question"] is None  # 状态不推进
    assert ans["evaluation"]["score"] == 7

    # 同题再次作答（再答一次）
    ans2 = await s["svc"].answer(qid, "改进后的回答，内容足够长避免追问：" + "z" * 300, generate_next=False, username="u1")
    assert ans2["next_question"] is None
    row = s["store"].get_question(qid)
    assert row["answer"].startswith("改进后的回答")
    assert row["evaluation"]["score"] == 7

    # 之后正常推进
    ans3 = await s["svc"].answer(qid, "第三遍回答，这次要推进：" + "w" * 300, username="u1")
    assert ans3["is_complete"] is False and ans3["next_question"] is not None


# ---------------------------------------------------------------- 4. question fallback（G1-F）

@pytest.mark.asyncio
async def test_question_fallback(env_dir):
    s = build_stack(env_dir, max_rounds=1, question="完全不是 JSON 的输出")
    res = await _start(s)
    assert res["question"]["content"]  # 兜底题存在
    assert s["store"].get_questions(res["session_id"])  # 兜底题已落库
    # 流程仍可继续
    ans = await s["svc"].answer(res["question"]["id"], "回答内容足够长避免追问：" + "q" * 300, username="u1")
    assert ans["is_complete"] is True


# ---------------------------------------------------------------- 5. evaluation fallback（G4-F）

@pytest.mark.asyncio
async def test_evaluation_fallback_rule_score(env_dir):
    s = build_stack(env_dir, max_rounds=1, evaluation="垃圾输出")
    res = await _start(s)
    ans = await s["svc"].answer(res["question"]["id"], "回答内容足够长避免追问：" + "e" * 300, username="u1")
    assert ans["evaluation"]["score"] == 5  # 未命中期望知识点 → round(5+0)
    assert ans["is_complete"] is True


# ---------------------------------------------------------------- 6. tool degrade

@pytest.mark.asyncio
async def test_tool_degrade_continues(env_dir):
    s = build_stack(env_dir, max_rounds=1, facade_ok=False)  # kb_retrieve 抛异常
    res = await _start(s)  # 出题节点 kb_retrieve 失败 → 降级为无上下文出题
    assert res["question"]["content"]
    ans = await s["svc"].answer(res["question"]["id"], "回答内容足够长避免追问：" + "t" * 300, username="u1")
    assert ans["is_complete"] is True


# ---------------------------------------------------------------- 6b. LLM 调用失败 → 确定性降级（spec G）

@pytest.mark.asyncio
async def test_llm_failure_degrades_to_fallback(env_dir):
    """LLM 调用异常 → 节点确定性兜底（G1-F 兜底题 / G4-F 规则分），不再冒泡崩溃。"""

    async def boom(prompt, system=None):
        raise RuntimeError("llm down")

    s = build_stack(env_dir, max_rounds=1)
    s["orch"]._llm_call = boom
    res = await _start(s)
    assert res["question"]["content"]  # G1-F
    ans = await s["svc"].answer(res["question"]["id"], "回答内容足够长避免追问：" + "L" * 300, username="u1")
    assert ans["evaluation"]["score"] == 5  # G4-F 未命中 → round(5+0)
    assert ans["is_complete"] is True
    # trace 至少两个 fallback 事件（question_fallback + eval_rule）
    tf = s["env"] / "traces" / f"{res['session_id']}.jsonl"
    events = [json.loads(line)["event"] for line in tf.read_text(encoding="utf-8").strip().splitlines()]
    assert events.count("fallback") >= 2


# ---------------------------------------------------------------- 7. escape hatch → SUMMARIZING

@pytest.mark.asyncio
async def test_escape_hatch_force_end(env_dir):
    # 连续失败上限=1：评估节点必失败 → 一次 fallback 即触发逃生
    hatch = EscapeHatch(EscapeHatchConfig(max_rounds=5, max_consecutive_failures=1))
    s = build_stack(env_dir, max_rounds=5, evaluation="垃圾输出", escape=hatch)
    res = await _start(s)
    ans = await s["svc"].answer(res["question"]["id"], "回答内容足够长避免追问：" + "h" * 300, username="u1")
    assert ans["is_complete"] is True  # 逃生 → 强制收尾
    assert s["orch"].get_state(res["session_id"]) is AgentState.END
    assert ans["report"]["total_score"] is not None


# ---------------------------------------------------------------- 8. 非法状态转移

@pytest.mark.asyncio
async def test_illegal_transition_after_end(env_dir):
    s = build_stack(env_dir, max_rounds=1)
    res = await _start(s)
    await s["svc"].answer(res["question"]["id"], "回答内容足够长避免追问：" + "i" * 300, username="u1")
    # 会话已 END，再次提交 → 非法转移
    with pytest.raises(ValueError):
        await s["svc"].answer(res["question"]["id"], "再来一次", username="u1")


# ---------------------------------------------------------------- 10. trace 关键事件

@pytest.mark.asyncio
async def test_trace_contains_key_events(env_dir):
    # 组合场景：追问（G9）+ 评估兜底（G4-F）→ 事件齐全
    s = build_stack(env_dir, max_rounds=1, evaluation="垃圾输出")
    res = await _start(s)
    await s["svc"].answer(res["question"]["id"], "短答触发追问", username="u1")
    qs = s["store"].get_questions(res["session_id"])
    fu = [q for q in qs if q["source"] == "followup"][0]
    await s["svc"].answer(fu["id"], "追问的回答，内容略长一些避免再次追问", username="u1")

    trace_file = s["env"] / "traces" / f"{res['session_id']}.jsonl"
    assert trace_file.exists()
    events = [json.loads(line)["event"] for line in trace_file.read_text(encoding="utf-8").strip().splitlines()]
    assert "transition" in events
    assert "node_finished" in events
    assert "tool_call" in events
    assert "fallback" in events
    assert "session_end" in events
