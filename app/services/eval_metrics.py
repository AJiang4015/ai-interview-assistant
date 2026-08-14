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