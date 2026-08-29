from app.services.eval_metrics import (
    hit_rate, recall_at_k, mrr, parse_expected_sources, multi_source_hit,
)

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


# ---------- 多源 recall 语义（Spec A：主文档必须出现 + 至少一个副文档出现） ----------

def test_parse_expected_sources_single_string():
    primary, all_src = parse_expected_sources("Redis.md")
    assert primary == "Redis.md"
    assert all_src == {"Redis.md"}


def test_parse_expected_sources_list():
    primary, all_src = parse_expected_sources(["Redis.md", "操作系统.md"])
    assert primary == "Redis.md"
    assert all_src == {"Redis.md", "操作系统.md"}


def test_parse_expected_sources_empty():
    assert parse_expected_sources("") == ("", set())
    assert parse_expected_sources([]) == ("", set())


def test_multi_source_hit_primary_and_secondary():
    ranked = ["Redis.md", "操作系统.md", "other.md"]
    assert multi_source_hit(ranked, ["Redis.md", "操作系统.md"], k=3) == 1.0


def test_multi_source_hit_primary_only_fails():
    # 只有主文档、没有副文档 → 不算命中
    ranked = ["Redis.md", "other.md"]
    assert multi_source_hit(ranked, ["Redis.md", "操作系统.md"], k=3) == 0.0


def test_multi_source_hit_secondary_only_fails():
    # 只有副文档、没有主文档 → 不算命中
    ranked = ["操作系统.md", "other.md"]
    assert multi_source_hit(ranked, ["Redis.md", "操作系统.md"], k=3) == 0.0


def test_multi_source_hit_single_source_degrades():
    # 单源样本退化为普通命中逻辑
    assert multi_source_hit(["a.py", "b.py"], "a.py", k=2) == 1.0
    assert multi_source_hit(["a.py", "b.py"], "c.py", k=2) == 0.0


def test_multi_source_recall_and_mrr_semantics():
    # 多源 recall：按全部期望来源的命中比例
    ranked = ["Redis.md", "操作系统.md", "other.md"]
    _, expected = parse_expected_sources(["Redis.md", "操作系统.md"])
    assert recall_at_k(ranked, expected, k=3) == 1.0
    assert recall_at_k(ranked[:1], expected, k=1) == 0.5
    # mrr 以主文档排名为准
    primary, _ = parse_expected_sources(["Redis.md", "操作系统.md"])
    assert mrr(ranked, {primary}, k=3) == 1.0
    assert mrr(["other.md", "Redis.md"], {primary}, k=3) == 0.5


# ---------- 真实手写核心集（data/eval_testset.json）中 6 条 (a) 类题的验证 ----------

import json
from pathlib import Path

TESTSET = Path(__file__).resolve().parents[2] / "data" / "eval_testset.json"


def _load_type_a_items():
    # 仅验证手写核心集（排除 LLM 扩展条目），保证评估规则测试稳定
    with open(TESTSET, encoding="utf-8") as f:
        return [e for e in json.load(f)
                if e.get("question_type") == "a"
                and e.get("origin", "handwritten") != "llm_extension"]


def test_type_a_items_count():
    items = _load_type_a_items()
    assert len(items) == 14  # 6 条原有 + 8 条新增真跨文档


def test_type_a_multi_source_items_use_list_format():
    # 多源 (a) 题必须是列表格式且首元素与 source_file（主文档）一致
    for e in _load_type_a_items():
        src = e["expected_source"]
        if isinstance(src, list):
            assert len(src) >= 2
            assert src[0] == e["source_file"]
        else:
            # 单源 (a) 题保持字符串
            assert src == e["source_file"]


def test_type_a_multi_source_recall_verification():
    """对手写集 (a) 类题逐一验证多源 recall 计算符合预期规则。"""
    items = _load_type_a_items()
    multi = [e for e in items if isinstance(e["expected_source"], list)]
    single = [e for e in items if not isinstance(e["expected_source"], list)]
    assert len(multi) == 10 and len(single) == 4  # 8 条新增均多源

    for e in multi:
        primary, expected = parse_expected_sources(e["expected_source"])
        secondary = expected - {primary}
        # 构造 ranked：主+副 → hit=1，recall=1
        ranked_ok = [primary, next(iter(secondary)), "noise.md"]
        assert multi_source_hit(ranked_ok, e["expected_source"], k=3) == 1.0
        assert recall_at_k(ranked_ok, expected, k=3) == 1.0
        # 只有主文档 → hit=0，recall=0.5
        ranked_primary_only = [primary, "noise.md"]
        assert multi_source_hit(ranked_primary_only, e["expected_source"], k=3) == 0.0
        assert recall_at_k(ranked_primary_only, expected, k=3) == 0.5
        # 只有副文档 → hit=0，recall=0.5
        ranked_secondary_only = [next(iter(secondary)), "noise.md"]
        assert multi_source_hit(ranked_secondary_only, e["expected_source"], k=3) == 0.0

    for e in single:
        primary, expected = parse_expected_sources(e["expected_source"])
        # 单源：主文档出现即 hit=1，recall=1；未出现则全 0
        assert multi_source_hit([primary, "noise.md"], e["expected_source"], k=2) == 1.0
        assert recall_at_k([primary], expected, k=1) == 1.0
        assert multi_source_hit(["noise.md"], e["expected_source"], k=1) == 0.0
        assert recall_at_k(["noise.md"], expected, k=1) == 0.0