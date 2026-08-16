from app.services import session_cost


def test_budget_alarm(monkeypatch):
    monkeypatch.setattr("app.config.settings.session_token_budget", 0.001)
    session_cost.reset()
    session_cost.add("s1", 0.0006)
    session_cost.add("s1", 0.0006)  # 累计 0.0012 > 0.001
    assert session_cost.is_over_budget("s1") is True