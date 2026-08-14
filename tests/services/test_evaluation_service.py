# tests/services/test_evaluation_service.py
from app.services.evaluation_service import _aggregate_retrieval

def test_aggregate_retrieval():
    metrics = [
        {"hit": 1.0, "recall": 0.5, "mrr": 1.0},
        {"hit": 0.0, "recall": 0.25, "mrr": 0.5},
    ]
    agg = _aggregate_retrieval(metrics)
    assert agg["hit_rate"] == 0.5
    assert agg["recall"] == 0.375
    assert agg["mrr"] == 0.75
    assert agg["samples"] == 2