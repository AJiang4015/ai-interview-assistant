"""W1 Day 3：profile_store（会话内画像降级形态）单元测试。

对应 impl-spec v2 附录 D profile_store / E6（F8 口径）。Redis 长期画像为 W2下 范围，
本最小实现为「会话内画像」fallback（spec 砍单链降级路径）。
"""

from app.services.agent.profile_store import EMPTY_PROFILE, SessionProfileStore


def test_get_default_empty_profile():
    store = SessionProfileStore()
    p = store.get("u1")
    assert p == EMPTY_PROFILE
    assert p["weak_points"] == [] and p["level"] is None and p["accuracy"] is None


def test_update_then_get_roundtrip():
    store = SessionProfileStore()
    store.update("u1", {"level": "P6", "weak_points": ["JVM"]})
    p = store.get("u1")
    assert p["level"] == "P6"
    assert p["weak_points"] == ["JVM"]


def test_update_merges_without_dropping_fields():
    store = SessionProfileStore()
    store.update("u1", {"weak_points": ["JVM"]})
    store.update("u1", {"accuracy": 0.75})
    p = store.get("u1")
    assert p["weak_points"] == ["JVM"]
    assert p["accuracy"] == 0.75
    assert "level" in p  # 未被覆盖字段保留


def test_users_isolated():
    store = SessionProfileStore()
    store.update("u1", {"level": "P6"})
    assert store.get("u2")["level"] is None


def test_get_returns_copy_not_shared_reference():
    store = SessionProfileStore()
    store.update("u1", {"level": "P6"})
    p1 = store.get("u1")
    p1["level"] = "P9"  # 外部修改不得污染内部
    assert store.get("u1")["level"] == "P6"
