# tests/services/test_interview_agent.py
from app.services.interview_agent import InterviewPlanner, PlannerContext

def test_decide_ask_after_start():
    p = InterviewPlanner()
    ctx = PlannerContext(mode="interview", total_answered=0, max_rounds=15, should_end=False, last_evaluation=None)
    assert p.decide(ctx) == "ask_question"

def test_decide_report_when_should_end():
    p = InterviewPlanner()
    ctx = PlannerContext(mode="interview", total_answered=3, max_rounds=15,
                         should_end=True, last_evaluation={"should_end": True})
    assert p.decide(ctx) == "generate_report"

def test_decide_evaluate_after_answer():
    p = InterviewPlanner()
    ctx = PlannerContext(mode="interview", total_answered=1, max_rounds=15, should_end=False,
                         last_evaluation=None, pending_evaluation=True)
    assert p.decide(ctx) == "evaluate_answer"

def test_decide_report_at_max_rounds():
    p = InterviewPlanner()
    ctx = PlannerContext(total_answered=15, max_rounds=15, should_end=False)
    assert p.decide(ctx) == "generate_report"