from app.services.eval_metrics import hit_rate, recall_at_k, mrr

def test_hit_rate_hit():
    assert hit_rate(["a.py", "b.py"], {"a.py"}, k=2) == 1.0

def test_hit_rate_miss():
    assert hit_rate(["a.py", "b.py"], {"c.py"}, k=2) == 0.0

def test_recall_at_k():
    assert recall_at_k(["a.py", "b.py"], {"a.py", "b.py", "c.py"}, k=2) == 2 / 3

def test_mrr_first_hit():
    assert mrr(["b.py", "a.py"], {"a.py"}, k=3) == 0.5

def test_mrr_no_hit():
    assert mrr(["a.py"], {"x.py"}, k=3) == 0.0

def test_hit_rate_empty_expected():
    # 期望来源为空时返回 0，避免除零
    assert hit_rate(["a.py"], set(), k=2) == 0.0