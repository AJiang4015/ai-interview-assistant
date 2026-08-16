"""AI 指标与 Token 成本核算。OTel 可选启用，未启用时静默降级为内存计数。"""
try:
    from opentelemetry import metrics

    _OTEL_AVAILABLE = True
except ImportError:  # pragma: no cover - 依赖未安装时优雅降级
    metrics = None
    _OTEL_AVAILABLE = False

import logging

from app.config import settings
from app.services import session_cost

# 全局累计（测试与降级模式下可断言）
_total_cost = 0.0

_logger = logging.getLogger(__name__)

cost_counter = None
in_tokens = None
out_tokens = None
faithful_counter = None
vector_query_counter = None

# 内存计数：幻觉评估 / 向量检索空结果（OTel 未启用时降级统计）
_faithful_total = {"faithful": 0, "hallucination": 0}
_vector_total = {"ok": 0, "empty": 0}


def _init_otel():
    global cost_counter, in_tokens, out_tokens, faithful_counter, vector_query_counter
    meter = metrics.get_meter("ai.cost")
    cost_counter = meter.create_counter("ai.token_cost", unit="USD")
    in_tokens = meter.create_counter("ai.in_tokens", unit="tokens")
    out_tokens = meter.create_counter("ai.out_tokens", unit="tokens")
    faithful_counter = meter.create_counter("ai.eval_faithful")
    vector_query_counter = meter.create_counter("ai.vector_query")


def emit_cost(model: str, in_n: int, out_n: int, session_id: str) -> None:
    """按会话累加 Token 成本。OTel 可用则上报，否则仅更新内存计数。"""
    global _total_cost
    price = settings.token_price.get(model, {})
    cost = (in_n * price.get("input", 0) + out_n * price.get("output", 0)) / 1_000_000
    _total_cost += cost
    if session_id and session_id != "unknown":
        session_cost.add(session_id, cost)
    if settings.otel_enabled and _OTEL_AVAILABLE and cost_counter is not None:
        attrs = {"model": model, "session": session_id}
        cost_counter.add(cost, attrs)
        in_tokens.add(in_n, attrs)
        out_tokens.add(out_n, attrs)


def record_faithfulness(result: bool) -> None:
    """记录一次幻觉评估结果。True=命中幻觉，False=faithful。OTel 未启用时仅更新内存计数。"""
    if result:
        _faithful_total["hallucination"] += 1
        label = "hallucination"
    else:
        _faithful_total["faithful"] += 1
        label = "faithful"
    if settings.otel_enabled and _OTEL_AVAILABLE and faithful_counter is not None:
        faithful_counter.add(1, {"result": label})


def record_vector_query(empty: bool) -> None:
    """记录一次向量检索，标记是否命中空结果。OTel 未启用时仅更新内存计数。"""
    if empty:
        _vector_total["empty"] += 1
        label = "empty"
    else:
        _vector_total["ok"] += 1
        label = "ok"
    if settings.otel_enabled and _OTEL_AVAILABLE and vector_query_counter is not None:
        vector_query_counter.add(1, {"error": label})


def init_monitor() -> None:
    """应用启动时调用。OTel 被禁用或失败时静默降级。"""
    if not settings.otel_enabled or not _OTEL_AVAILABLE:
        return
    try:
        _init_otel()
    except Exception:
        _logger.debug("OTel init failed", exc_info=True)  # 降级为纯内存计数