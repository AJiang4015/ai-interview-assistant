from app.observability import init_tracing


def test_init_tracing_disabled_does_not_raise(monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "otel_enabled", False)
    # 传入 None 模拟假 app，不会真正 instrument
    init_tracing(None)