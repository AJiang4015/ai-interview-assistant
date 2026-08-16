from app.services import monitor

def test_emit_cost_updates_internal_counters():
    before = monitor._total_cost
    monitor.emit_cost("qwen3.7-max", in_tokens=1000, out_tokens=500, session_id="s1")
    assert monitor._total_cost > before