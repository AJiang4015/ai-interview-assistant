"""Agent 编排层（impl-spec v2 附录 D：app/services/agent/）。

W1 进度：Day 1 state_machine（附录 A/B/C）+ trace（附录 H）；Day 2 roles（附录 E3）+ structured_output（§4.1）。
后续按里程碑补充：tools / model_gateway / mcp_client / orchestrator / agent_service / profile_store / fallback。
"""

from app.services.agent.roles import (
    EVALUATOR_ROLE,
    FOLLOWUPER_ROLE,
    QUESTIONER_ROLE,
    ROLES,
    Evaluation,
    FollowUp,
    Question,
    build_evaluation_prompt,
    build_followup_prompt,
    build_question_prompt,
)
from app.services.agent.state_machine import (
    DEFAULT_GATES,
    TRANSITIONS,
    AgentEvent,
    AgentState,
    EscapeHatch,
    EscapeHatchConfig,
    EscapeHatchContext,
    GateContext,
    GuardResult,
    StateMachine,
    StepResult,
    Transition,
    difficulty_delta,
)
from app.services.agent.structured_output import (
    MAX_ATTEMPTS_DEFAULT,
    StructuredResult,
    build_feedback_prompt,
    extract_json,
    generate_structured,
    validate_against_schema,
)
from app.services.agent.trace import (
    TRACE_EVENT_TYPES,
    TRACE_SCHEMA_VERSION,
    ToolCallTrace,
    TraceRecorder,
    TraceRecord,
)

__all__ = [
    # state_machine
    "AgentEvent",
    "AgentState",
    "DEFAULT_GATES",
    "TRANSITIONS",
    "Transition",
    "GateContext",
    "GuardResult",
    "StateMachine",
    "StepResult",
    "difficulty_delta",
    "EscapeHatch",
    "EscapeHatchConfig",
    "EscapeHatchContext",
    # roles
    "QUESTIONER_ROLE",
    "FOLLOWUPER_ROLE",
    "EVALUATOR_ROLE",
    "ROLES",
    "Question",
    "FollowUp",
    "Evaluation",
    "build_question_prompt",
    "build_followup_prompt",
    "build_evaluation_prompt",
    # structured_output
    "MAX_ATTEMPTS_DEFAULT",
    "StructuredResult",
    "build_feedback_prompt",
    "extract_json",
    "generate_structured",
    "validate_against_schema",
    # trace
    "TRACE_SCHEMA_VERSION",
    "TRACE_EVENT_TYPES",
    "ToolCallTrace",
    "TraceRecord",
    "TraceRecorder",
]
