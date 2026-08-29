"""P001 / DR-004 回归测试：缓存 key 只基于原始问题，去除 session_id / msg_count 可变维度。

背景（PROBLEM.md P001）：旧实现 key = md5(question|session_id|msg_count)，导致
同一问题在不同会话/轮次产生不同 key，缓存命中率趋近 0。DR-004 要求 key 仅取材自
业务上稳定不变的原始问题原文。
"""

from app.services.cache_service import ResponseCache


def _cache(store=None, prefix: str = "cache:rag:"):
    return ResponseCache(store, ttl=3600, prefix=prefix)


def test_make_key_same_question_cross_session_same_key():
    """相同问题，不同 session / 不同 msg_count，必须命中同一 key（P001 核心回归）。"""
    c = _cache(None)
    k1 = c.make_key("什么是HashMap", "sessionA", 1)
    k2 = c.make_key("什么是HashMap", "sessionB", 5)
    assert k1 == k2


def test_make_key_different_question_different_key():
    """不同问题必须得到不同 key。"""
    c = _cache(None)
    assert c.make_key("问题甲", "s1", 1) != c.make_key("问题乙", "s1", 1)


def test_make_key_removes_session_and_msg_count_from_hash_input():
    """key 值不得粘有任何 session_id / msg_count 的明文痕迹。"""
    c = _cache(None)
    k = c.make_key("q", "secretSession", 42)
    assert "secretSession" not in k
    assert "cache:rag:" in k
    assert k.startswith("cache:rag:")


def test_make_key_uses_configured_prefix():
    """key 前缀取自构造参数 prefix。"""
    c = _cache(None, prefix="cache:custom:")
    assert c.make_key("q", "s", 1).startswith("cache:custom:")


def test_available_false_without_store():
    """无 Redis 连接时缓存不可用（优雅降级）。"""
    assert _cache(None).available is False


def test_available_true_with_connected_store():
    class FakeStore:
        is_connected = True

    assert _cache(FakeStore()).available is True