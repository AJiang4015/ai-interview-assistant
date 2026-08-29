# tests/services/test_eval_runner.py
import json
from collections import Counter
from pathlib import Path

from app.services.eval_metrics import parse_expected_sources

TESTSET = Path(__file__).resolve().parents[2] / "data" / "eval_testset.json"

REQUIRED_FIELDS = {"question", "expected_answer", "expected_source", "source_file", "question_type"}


def _load():
    with open(TESTSET, encoding="utf-8") as f:
        return json.load(f)


def test_testset_field_integrity():
    items = _load()
    assert len(items) >= 100  # 满足 Spec A 100~150 区间下限
    assert isinstance(items, list)
    missing = [i for i, e in enumerate(items) if not REQUIRED_FIELDS.issubset(e.keys())]
    assert missing == []


def test_testset_four_dimensions_present():
    items = _load()
    dist = Counter(e.get("question_type") for e in items)
    for dim in "abcd":
        assert dist.get(dim, 0) >= 1  # 四维度齐全


def test_testset_has_multi_source_queries():
    items = _load()
    multi = [e for e in items if isinstance(e.get("expected_source"), list)]
    assert len(multi) >= 6  # 跨文档样本 ≥6~8 目标下限


def test_testset_no_duplicate_questions():
    from app.services.eval_testset import _normalize_question
    items = _load()
    norm = [_normalize_question(e["question"]) for e in items]
    assert len(norm) == len(set(norm))


def test_multi_source_primary_matches_source_file():
    items = _load()
    for e in items:
        if isinstance(e.get("expected_source"), list):
            primary, _ = parse_expected_sources(e["expected_source"])
            assert primary == e["source_file"]