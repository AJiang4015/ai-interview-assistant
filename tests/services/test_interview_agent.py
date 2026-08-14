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

def test_agent_run_action_dispatches():
    from app.services.interview_agent import InterviewAgent
    class FakeTools:
        def ask_question(self): return {"kind": "ask"}
        def generate_report(self): return {"kind": "report"}
    agent = InterviewAgent(tools=FakeTools())
    assert agent.run_action("ask_question") == {"kind": "ask"}
    assert agent.run_action("generate_report") == {"kind": "report"}

def test_agent_step_uses_planner():
    from app.services.interview_agent import InterviewAgent, PlannerContext
    class FakeTools:
        def ask_question(self): return {"kind": "ask"}
        def generate_report(self): return {"kind": "report"}
    agent = InterviewAgent(tools=FakeTools())
    from unittest.mock import MagicMock
    planner = MagicMock()
    planner.decide.return_value = "generate_report"
    agent.planner = planner
    ctx = PlannerContext(total_answered=15, max_rounds=15)
    out = agent.step(ctx)
    assert out == {"kind": "report"}
    planner.decide.assert_called_once_with(ctx)