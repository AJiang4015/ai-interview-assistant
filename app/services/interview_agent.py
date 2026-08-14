from dataclasses import dataclass


@dataclass
class PlannerContext:
    mode: str = "interview"          # interview | deep_dive
    total_answered: int = 0
    max_rounds: int = 15
    should_end: bool = False
    last_evaluation: dict | None = None
    pending_evaluation: bool = False  # 刚提交回答待评价


class InterviewPlanner:
    """根据当前状态决策下一个动作。"""

    def decide(self, ctx: PlannerContext) -> str:
        if ctx.pending_evaluation:
            return "evaluate_answer"
        if ctx.should_end or (ctx.last_evaluation and ctx.last_evaluation.get("should_end")):
            return "generate_report"
        if ctx.total_answered < ctx.max_rounds:
            return "ask_question"
        return "generate_report"