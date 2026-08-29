def parse_expected_sources(expected_source) -> tuple[str, set]:
    """解析 expected_source 字段为 (主文档, 全部期望来源集合)。

    - 字符串：单源，primary 即该字符串；
    - 列表：多源（跨文档题），首元素为主文档，其余为副文档。
    """
    if isinstance(expected_source, (list, tuple)):
        sources = [str(s).strip() for s in expected_source if str(s).strip()]
        if not sources:
            return "", set()
        return sources[0], set(sources)
    s = str(expected_source).strip()
    if not s:
        return "", set()
    return s, {s}


def multi_source_hit(ranked_sources, expected_source, k) -> float:
    """多源命中规则（Spec A 多源 recall 语义）：

    - 多源（列表）：主文档必须出现在 top-k，且至少一个副文档也出现在 top-k，才记命中 1.0；
    - 单源（字符串）：退化为普通命中判断（期望来源出现在 top-k）。
    """
    primary, all_sources = parse_expected_sources(expected_source)
    if not all_sources:
        return 0.0
    top = ranked_sources[:k]
    if primary not in top:
        return 0.0
    if len(all_sources) == 1:
        return 1.0
    return 1.0 if any(s in top for s in all_sources - {primary}) else 0.0


def hit_rate(ranked_sources, expected_sources, k):
    """期望来源是否出现在 top-k，命中返回 1.0，否则 0.0。"""
    if not expected_sources:
        return 0.0
    top = ranked_sources[:k]
    return 1.0 if any(s in expected_sources for s in top) else 0.0


def recall_at_k(ranked_sources, expected_sources, k):
    """top-k 中命中的期望来源数 / 期望来源总数。"""
    if not expected_sources:
        return 0.0
    top = ranked_sources[:k]
    hit = sum(1 for s in expected_sources if s in top)
    return hit / len(expected_sources)


def mrr(ranked_sources, expected_sources, k):
    """第一个命中期望来源的倒数排名。"""
    for i, s in enumerate(ranked_sources[:k], start=1):
        if s in expected_sources:
            return 1.0 / i
    return 0.0