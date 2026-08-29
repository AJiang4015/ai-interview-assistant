# tests/services/test_evaluation_service.py
from app.services.evaluation_service import _aggregate_retrieval, _aggregate_breakdown, _parse_json

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

def test_aggregate_breakdown_overall_and_by_dim():
    metrics = [
        {"question_type": "a", "recall@3": 1.0, "recall@5": 1.0, "mrr": 1.0},
        {"question_type": "a", "recall@3": 0.5, "recall@5": 0.75, "mrr": 0.5},
        {"question_type": "b", "recall@3": 0.0, "recall@5": 0.5, "mrr": 0.0},
    ]
    out = _aggregate_breakdown(metrics)
    ov = out["overall"]
    assert ov["samples"] == 3
    assert ov["recall@3"] == round((1.0 + 0.5 + 0.0) / 3, 4)
    assert ov["recall@5"] == round((1.0 + 0.75 + 0.5) / 3, 4)
    assert ov["mrr"] == round((1.0 + 0.5 + 0.0) / 3, 4)
    assert out["by_dimension"]["a"]["recall@3"] == round(1.5 / 2, 4)
    assert out["by_dimension"]["a"]["samples"] == 2
    assert out["by_dimension"]["b"]["recall@5"] == 0.5
    assert out["by_dimension"]["b"]["samples"] == 1


def test_parse_json_strips_fence():
    text = '```json\n{"score": 0.8}\n```'
    assert _parse_json(text) == {"score": 0.8}

def test_parse_json_plain():
    assert _parse_json('{"score": 0.5}') == {"score": 0.5}

def test_parse_json_none():
    assert _parse_json("") is None
    assert _parse_json("no json here") is None