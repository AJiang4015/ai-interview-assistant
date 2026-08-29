from app.config import settings
from app.services import monitor, session_cost

MODEL = next(iter(settings.token_price))  # 取配置中真实存在的模型名，避免硬编码

def test_emit_cost_updates_internal_counters():
    before = monitor._total_cost
    monitor.emit_cost(MODEL, in_n=1000, out_n=500, session_id="s1")
    assert monitor._total_cost > before


def test_emit_cost_adds_session_cost():
    session_cost.reset()
    monitor.emit_cost(MODEL, in_n=1000, out_n=500, session_id="s-test")
    assert session_cost.total("s-test") > 0


def test_record_faithfulness_and_vector_do_not_raise():
    # 重置共享内存计数，保证隔离（eval_monitor 复用了同一模块级计数）
    monitor._faithful_total = {"faithful": 0, "hallucination": 0}
    monitor._vector_total = {"ok": 0, "empty": 0}
    monitor.record_faithfulness(True)
    monitor.record_faithfulness(False)
    monitor.record_vector_query(False)
    monitor.record_vector_query(True)
    assert monitor._faithful_total["hallucination"] == 1
    assert monitor._vector_total["empty"] == 1