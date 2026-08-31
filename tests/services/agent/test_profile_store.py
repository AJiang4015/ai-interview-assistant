"""W1 Day 3 + W2 下：profile_store 单元测试。

W1：SessionProfileStore（会话内降级形态）。
W2 下：RedisProfileStore + compute_session_profile_patch（E6/F8 口径）+ make_profile_store 降级。
"""

from app.services.agent.profile_store import (
    EMPTY_PROFILE,
    RedisProfileStore,
    SessionProfileStore,
    compute_session_profile_patch,
    make_profile_store,
)


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


# ---------------------------------------------------------------- W2 下：画像聚合口径（E6/F8）

def _q(score, topic, source="llm", fallback=None, round_num=1):
    return {
        "round": round_num, "question": f"q{topic}", "answer": "a", "score": float(score),
        "topic": topic, "category": topic, "source": source,
        "evaluation": {"fallback": fallback, "tags": [topic]}, "created_at": "2026-09-01T00:00:00",
    }


def test_profile_patch_excludes_followup_keeps_fallback_marker():
    questions = [
        _q(7.0, "JVM"),                      # 主问题，LLM 分
        _q(5.0, "JVM", source="followup"),   # followup 不计入
        _q(3.0, "Redis", fallback="eval_rule"),  # G4-F 分计入，保留 fallback 标记
    ]
    patch = compute_session_profile_patch("s1", questions)
    assert len(patch["history"]) == 2
    assert patch["history"][0]["fallback"] is None
    assert patch["history"][1]["fallback"] == "eval_rule"
    assert patch["accuracy"] == 5.0  # (7+3)/2
    assert "Redis" in patch["weak_points"]  # 3 < 6 → 薄弱
    assert "JVM" not in patch["weak_points"]  # 7 ≥ 6
    assert patch["level"] == "初级"


def test_profile_patch_accuracy_window_last_10():
    questions = [_q(float(i), f"T{i % 3}") for i in range(1, 13)]  # 12 个主问题
    patch = compute_session_profile_patch("s1", questions)
    assert len(patch["history"]) == 12  # history 保留全部（上限 50）
    assert patch["accuracy"] == 7.5  # 最近 10 个：3..12 均值


def test_profile_patch_merges_prev_history():
    prev = {"history": [{"score": 9.0, "fallback": None, "session_id": "s0", "topic": "JVM", "ts": ""}]}
    patch = compute_session_profile_patch("s2", [_q(7.0, "JVM")], prev)
    assert len(patch["history"]) == 2
    assert patch["accuracy"] == 8.0  # (9+7)/2


def test_profile_patch_empty_questions():
    patch = compute_session_profile_patch("s1", [])
    assert patch["accuracy"] is None
    assert patch["history"] == [] and patch["weak_points"] == []


# ---------------------------------------------------------------- W2 下：RedisProfileStore

class _FakeRedis:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value
        return True

    def ping(self):
        return True


def test_redis_profile_roundtrip():
    r = RedisProfileStore(_FakeRedis())
    assert r.get("u1") == EMPTY_PROFILE
    r.update("u1", {"level": "中级", "weak_points": ["JVM"], "accuracy": 0.7})
    p = r.get("u1")
    assert p["level"] == "中级" and p["weak_points"] == ["JVM"] and p["accuracy"] == 0.7


def test_redis_profile_merge_keeps_fields():
    r = RedisProfileStore(_FakeRedis())
    r.update("u1", {"weak_points": ["JVM"]})
    r.update("u1", {"accuracy": 0.8})
    p = r.get("u1")
    assert p["weak_points"] == ["JVM"] and p["accuracy"] == 0.8 and p["level"] is None


def test_redis_profile_degrade_on_redis_error():
    class _Boom:
        def get(self, key):
            raise ConnectionError("redis down")

    r = RedisProfileStore(_Boom())
    assert r.get("u1") == EMPTY_PROFILE  # 异常 → 空画像，不抛（工具 degrade 语义）


# ---------------------------------------------------------------- W2 下：make_profile_store 降级

def test_make_profile_store_fallback_to_session_on_unreachable():
    p = make_profile_store(host="127.0.0.1", port=1, timeout=0.5)
    assert isinstance(p, SessionProfileStore)

