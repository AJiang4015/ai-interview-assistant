# tests/services/test_interview_service.py
from app.services.interview_service import InterviewService


def make_svc():
    # _decide_action 只依赖 self.planner 与 self.max_rounds，无需 store/llm
    return InterviewService(store=None, llm=None)


def test_decide_action_continue_below_max():
    assert make_svc()._decide_action("interview", 3, False, None) == "ask_question"


def test_decide_action_report_at_max():
    assert make_svc()._decide_action("interview", 15, False, None) == "generate_report"


def test_decide_action_report_on_should_end():
    assert make_svc()._decide_action("interview", 3, True, None) == "generate_report"


def test_decide_action_report_on_eval_should_end():
    assert make_svc()._decide_action("interview", 3, False, {"should_end": True}) == "generate_report"