"""Agent 编排层（impl-spec v2 附录 D：app/services/agent/）。

W1 Day 1 范围：state_machine（附录 A/B/C）+ trace（附录 H）。
后续按里程碑补充：roles / structured_output / tools / model_gateway / mcp_client /
orchestrator / agent_service / profile_store / fallback。
"""

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
from app.services.agent.trace import (
    TRACE_EVENT_TYPES,
    TRACE_SCHEMA_VERSION,
    ToolCallTrace,
    TraceRecorder,
    TraceRecord,
)

__all__ = [
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
    "TRACE_SCHEMA_VERSION",
    "TRACE_EVENT_TYPES",
    "ToolCallTrace",
    "TraceRecord",
    "TraceRecorder",
]
