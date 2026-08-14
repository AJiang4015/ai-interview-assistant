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


class InterviewAgent:
    """顶层编排：汇聚上下文 → Planner 决策 → 执行工具。"""

    def __init__(self, planner=None, tools=None, context_builder=None):
        self.planner = planner or InterviewPlanner()
        self.tools = tools or {}
        self.context_builder = context_builder

    def run_action(self, action: str):
        """根据动作分派到对应工具。tools 可为 {action: callable} 字典或含同名方法的对象。"""
        handler = getattr(self.tools, action, None)
        if handler is None and isinstance(self.tools, dict):
            handler = self.tools.get(action)
        if handler is None:
            raise ValueError(f"No handler for action: {action}")
        return handler()

    def step(self, ctx: PlannerContext) -> dict:
        action = self.planner.decide(ctx)
        return self.run_action(action)

    def build_context(self, **kwargs) -> PlannerContext:
        if self.context_builder:
            return self.context_builder(**kwargs)
        return PlannerContext(**kwargs)