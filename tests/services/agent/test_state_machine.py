"""W1 Day 1：state_machine 单元测试（impl-spec v2 附录 A/B/C）。

先于实现编写（TDD）。覆盖：
- 附录 A3 转移表逐行（14 行：单行 + 行 12 四来源 + 行 13 全部非终态 + 行 14 内部事件）
- 守卫互斥（行 4/5、行 9/10/11）
- 非法转移拒绝 / 终态无转移
- 附录 B 门禁（G0/G1/G1-F/G1-f/G2/G4/G4-F/G5/G6/G7/G8/G9）
- 附录 C 逃生舱各条件与默认值
"""

import pytest

from app.services.agent.state_machine import (
    AgentEvent,
    AgentState,
    EscapeHatch,
    EscapeHatchConfig,
    EscapeHatchContext,
    GateContext,
    GuardResult,
    StateMachine,
    difficulty_delta,
)


def _ctx(state, event, **kw):
    return GateContext(state=state, event=event, **kw)


# ---------------------------------------------------------------- 附录 A3 转移表逐行

def test_row_1_init_start_questioning():
    m = StateMachine()
    r = m.step(AgentState.INIT, AgentEvent.START,
               _ctx(AgentState.INIT, AgentEvent.START, position="Java后端"))
    assert r.allowed and r.next_state is AgentState.QUESTIONING


def test_row_1_g0_rejects_empty_position():
    m = StateMachine()
    r = m.step(AgentState.INIT, AgentEvent.START,
               _ctx(AgentState.INIT, AgentEvent.START, position="  "))
    assert not r.allowed
    assert r.reason == "guard_denied:g0_start"


def test_row_2_question_ready_to_awaiting():
    m = StateMachine()
    out = {"question": "请讲一下 JVM 内存模型。", "difficulty": "medium",
           "knowledge_tags": ["JVM"], "topic": "JVM", "category": "JVM"}
    r = m.step(AgentState.QUESTIONING, AgentEvent.QUESTION_READY,
               _ctx(AgentState.QUESTIONING, AgentEvent.QUESTION_READY, output=out))
    assert r.allowed and r.next_state is AgentState.AWAITING_ANSWER


def test_row_2_g1_rejects_invalid_outputs():
    m = StateMachine()
    base = dict(question="q", difficulty="medium", knowledge_tags=["t"])
    # 空题目
    bad1 = dict(base, question="  ")
    # 非法难度
    bad2 = dict(base, difficulty="insane")
    # 空知识标签
    bad3 = dict(base, knowledge_tags=[])
    for bad in (bad1, bad2, bad3):
        r = m.step(AgentState.QUESTIONING, AgentEvent.QUESTION_READY,
                   _ctx(AgentState.QUESTIONING, AgentEvent.QUESTION_READY, output=bad))
        assert not r.allowed
        assert r.reason == "guard_denied:g1_question"


def test_row_2_g1_rejects_duplicate_question():
    m = StateMachine()
    out = {"question": "重复题", "difficulty": "easy", "knowledge_tags": ["t"]}
    r = m.step(AgentState.QUESTIONING, AgentEvent.QUESTION_READY,
               _ctx(AgentState.QUESTIONING, AgentEvent.QUESTION_READY,
                    output=out, asked_set=frozenset({hash("重复题")})))
    assert not r.allowed
    assert r.reason == "guard_denied:g1_question"


def test_row_3_question_fallback_to_awaiting():
    m = StateMachine()
    out = {"question": "（兜底模板题）请介绍 Java 集合框架。", "difficulty": "medium",
           "knowledge_tags": ["集合"]}
    r = m.step(AgentState.QUESTIONING, AgentEvent.QUESTION_FALLBACK,
               _ctx(AgentState.QUESTIONING, AgentEvent.QUESTION_FALLBACK, output=out))
    assert r.allowed and r.next_state is AgentState.AWAITING_ANSWER


def test_rows_4_5_answer_submitted_mutual_exclusion():
    m = StateMachine()
    # G9 命中（短答 + 有追问预算）→ FOLLOWUP（行 4）
    r = m.step(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
               _ctx(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
                    answer_len=80, followup_enabled=True, followup_budget=1))
    assert r.allowed and r.next_state is AgentState.FOLLOWUP
    # ¬G9（长答/追问禁用/预算耗尽）→ EVALUATING（行 5）
    r2 = m.step(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
                _ctx(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
                     answer_len=500, followup_enabled=True, followup_budget=1))
    assert r2.allowed and r2.next_state is AgentState.EVALUATING
    r3 = m.step(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
                _ctx(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
                     answer_len=80, followup_enabled=False, followup_budget=1))
    assert r3.allowed and r3.next_state is AgentState.EVALUATING
    # G2 失败（空回答）→ 两行均拒绝，留在原状态
    r4 = m.step(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
                _ctx(AgentState.AWAITING_ANSWER, AgentEvent.ANSWER_SUBMITTED,
                     answer_len=0))
    assert not r4.allowed
    assert r4.reason == "guard_denied:g2_answer"


def test_row_6_followup_ready_to_awaiting():
    m = StateMachine()
    out = {"followup_question": "为什么不用分段锁？", "intent": "深挖"}
    r = m.step(AgentState.FOLLOWUP, AgentEvent.FOLLOWUP_READY,
               _ctx(AgentState.FOLLOWUP, AgentEvent.FOLLOWUP_READY, output=out))
    assert r.allowed and r.next_state is AgentState.AWAITING_ANSWER


def test_row_6_g1_followup_rejects_empty():
    m = StateMachine()
    r = m.step(AgentState.FOLLOWUP, AgentEvent.FOLLOWUP_READY,
               _ctx(AgentState.FOLLOWUP, AgentEvent.FOLLOWUP_READY, output={}))
    assert not r.allowed
    assert r.reason == "guard_denied:g1_followup"


def test_rows_7_8_evaluating_to_difficulty_adj():
    m = StateMachine()
    out_ok = {"score": 7, "comment": "不错", "score_reason": "要点覆盖全",
              "reference_answer": "ref", "tags": ["JVM"]}
    r = m.step(AgentState.EVALUATING, AgentEvent.EVALUATION_DONE,
               _ctx(AgentState.EVALUATING, AgentEvent.EVALUATION_DONE, output=out_ok))
    assert r.allowed and r.next_state is AgentState.DIFFICULTY_ADJ
    # G4 失败：score 非 int
    out_bad = dict(out_ok, score="7")
    r2 = m.step(AgentState.EVALUATING, AgentEvent.EVALUATION_DONE,
                _ctx(AgentState.EVALUATING, AgentEvent.EVALUATION_DONE, output=out_bad))
    assert not r2.allowed and r2.reason == "guard_denied:g4_eval"
    # G4-F：兜底规则分（int 1-10）放行
    r3 = m.step(AgentState.EVALUATING, AgentEvent.EVALUATION_FALLBACK,
                _ctx(AgentState.EVALUATING, AgentEvent.EVALUATION_FALLBACK,
                     output={"score": 5}))
    assert r3.allowed and r3.next_state is AgentState.DIFFICULTY_ADJ


def test_rows_9_10_11_difficulty_adjust_mutual_exclusion():
    m = StateMachine()
    # score>=8 → next（行 9）
    r = m.step(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
               _ctx(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
                    score=9.0, round=3, max_rounds=15))
    assert r.allowed and r.next_state is AgentState.QUESTIONING
    assert r.guard_payload["action"] == "next" and r.guard_payload["delta"] == 1
    # score<5 且可重问 → reask（行 10，同知识点降难度）
    r2 = m.step(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
                _ctx(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
                     score=3.0, reask_allowed=True, round=3, max_rounds=15))
    assert r2.allowed and r2.next_state is AgentState.QUESTIONING
    assert r2.guard_payload["action"] == "reask" and r2.guard_payload["delta"] == -1
    # score<5 且已重问 → next（weak_point 计数，行 9）
    r3 = m.step(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
                _ctx(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
                     score=3.0, reask_allowed=False, round=3, max_rounds=15))
    assert r3.allowed and r3.next_state is AgentState.QUESTIONING
    assert r3.guard_payload["weak_point"] is True
    # round>=max_rounds → end（行 11 → SUMMARIZING）
    r4 = m.step(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
                _ctx(AgentState.DIFFICULTY_ADJ, AgentEvent.DIFFICULTY_ADJUSTED,
                     score=9.0, round=15, max_rounds=15))
    assert r4.allowed and r4.next_state is AgentState.SUMMARIZING


def test_row_12_end_requested_from_four_states():
    m = StateMachine()
    for s in (AgentState.QUESTIONING, AgentState.AWAITING_ANSWER,
              AgentState.FOLLOWUP, AgentState.EVALUATING):
        r = m.step(s, AgentEvent.END_REQUESTED, _ctx(s, AgentEvent.END_REQUESTED))
        assert r.allowed and r.next_state is AgentState.SUMMARIZING


def test_row_13_force_end_any_nonterminal():
    m = StateMachine()
    for s in AgentState:
        if s is AgentState.END:
            continue
        r = m.step(s, AgentEvent.FORCE_END,
                   _ctx(s, AgentEvent.FORCE_END, force_end=True))
        assert r.allowed, f"FORCE_END from {s} should be allowed"
        assert r.next_state is AgentState.SUMMARIZING


def test_g7_escape_requires_trigger():
    m = StateMachine()
    r = m.step(AgentState.EVALUATING, AgentEvent.FORCE_END,
               _ctx(AgentState.EVALUATING, AgentEvent.FORCE_END, force_end=False))
    assert not r.allowed
    assert r.reason == "guard_denied:g7_escape"


def test_row_14_summarize_done_to_end():
    m = StateMachine()
    r = m.step(AgentState.SUMMARIZING, AgentEvent.SUMMARIZE_DONE,
               _ctx(AgentState.SUMMARIZING, AgentEvent.SUMMARIZE_DONE, answered_rounds=3))
    assert r.allowed and r.next_state is AgentState.END
    # G8：无数据且非 end/escape 来源 → 拒绝
    r2 = m.step(AgentState.SUMMARIZING, AgentEvent.SUMMARIZE_DONE,
                _ctx(AgentState.SUMMARIZING, AgentEvent.SUMMARIZE_DONE,
                     answered_rounds=0, summary_ready=False))
    assert not r2.allowed and r2.reason == "guard_denied:g8_summary"
    # G8：由 end/escape 进入（summary_ready=True）→ 放行
    r3 = m.step(AgentState.SUMMARIZING, AgentEvent.SUMMARIZE_DONE,
                _ctx(AgentState.SUMMARIZING, AgentEvent.SUMMARIZE_DONE,
                     answered_rounds=0, summary_ready=True))
    assert r3.allowed and r3.next_state is AgentState.END


# ---------------------------------------------------------------- 非法转移与终态

def test_illegal_transitions_rejected():
    m = StateMachine()
    cases = [
        (AgentState.QUESTIONING, AgentEvent.START),            # 非 INIT 起 START
        (AgentState.INIT, AgentEvent.ANSWER_SUBMITTED),        # INIT 收 answer
        (AgentState.AWAITING_ANSWER, AgentEvent.QUESTION_READY),
        (AgentState.DIFFICULTY_ADJ, AgentEvent.ANSWER_SUBMITTED),
        (AgentState.END, AgentEvent.START),
    ]
    for s, ev in cases:
        r = m.step(s, ev, _ctx(s, ev))
        assert not r.allowed, f"{s}/{ev} should be illegal"
        assert r.reason == "illegal_transition"


def test_terminal_state_has_no_transitions():
    assert StateMachine().allowed_events(AgentState.END) == []


def test_allowed_events_awaiting_answer():
    evts = StateMachine().allowed_events(AgentState.AWAITING_ANSWER)
    assert AgentEvent.ANSWER_SUBMITTED in evts
    assert AgentEvent.END_REQUESTED in evts
    assert AgentEvent.FORCE_END in evts


def test_gate_injection_override():
    m = StateMachine(gates={"g0_start": lambda ctx: GuardResult(passes=True)})
    r = m.step(AgentState.INIT, AgentEvent.START,
               _ctx(AgentState.INIT, AgentEvent.START, position=None))
    assert r.allowed and r.next_state is AgentState.QUESTIONING


# ---------------------------------------------------------------- 附录 B G5 难度表全分支

def test_difficulty_decision_branches():
    # score>=8 → next +1
    assert difficulty_delta(9.0, False, 3, 15, False) == {"action": "next", "delta": 1, "weak_point": False}
    # 5<=score<8 → next 0
    assert difficulty_delta(7.0, False, 3, 15, False) == {"action": "next", "delta": 0, "weak_point": False}
    # score<5 且可重问 → reask -1
    assert difficulty_delta(3.0, True, 3, 15, False) == {"action": "reask", "delta": -1, "weak_point": False}
    # score<5 且已重问 → next 0 + weak_point
    assert difficulty_delta(3.0, False, 3, 15, False) == {"action": "next", "delta": 0, "weak_point": True}
    # round>=max → end
    assert difficulty_delta(9.0, False, 15, 15, False)["action"] == "end"
    # user_ended → end
    assert difficulty_delta(9.0, False, 3, 15, True)["action"] == "end"
    # score=None（防御分支）→ end
    assert difficulty_delta(None, False, 3, 15, False)["action"] == "end"


# ---------------------------------------------------------------- 附录 C 逃生舱

def test_escape_hatch_conditions():
    hatch = EscapeHatch()
    assert hatch.check(EscapeHatchContext(consecutive_failures=3)) == "consecutive_failures_exceeded"
    assert hatch.check(EscapeHatchContext(consecutive_failures=2)) is None
    assert hatch.check(EscapeHatchContext(total_fallbacks=5)) == "fallbacks_exceeded"
    assert hatch.check(EscapeHatchContext(total_transitions=200)) == "transition_count_exceeded"
    assert hatch.check(EscapeHatchContext(over_budget=True)) == "budget_exceeded"
    assert hatch.check(EscapeHatchContext()) is None


def test_escape_hatch_config_defaults_match_spec():
    c = EscapeHatchConfig()
    assert c.max_rounds == 15
    assert c.max_structured_retries == 3
    assert c.max_consecutive_failures == 3
    assert c.node_timeout_sec == 60
    assert c.max_transitions == 200
    assert c.max_reask_per_topic == 1


def test_escape_hatch_config_override():
    c = EscapeHatchConfig(max_rounds=5, max_transitions=10)
    hatch = EscapeHatch(c)
    assert hatch.check(EscapeHatchContext(total_transitions=10)) == "transition_count_exceeded"
    assert hatch.check(EscapeHatchContext(total_transitions=9)) is None
