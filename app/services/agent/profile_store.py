"""候选人画像存储（impl-spec v2 附录 D profile_store / 附录 E6 F8 口径）。

W1 Day 3：`SessionProfileStore`（会话内降级形态）。
W2 下：`RedisProfileStore`（长期跨会话）+ `compute_session_profile_patch`（E6/F8 聚合口径）
      + `make_profile_store`（Redis 不可用 → 自动降级会话内画像）。

口径（E6/F8 冻结）：
- 历史正确率 accuracy = 最近 10 次**主问题**单题分均值（过滤 source='followup'）；
- G4-F 兜底规则分**计入**，但 history 记录保留 `fallback` 标记；
- level 由 accuracy 映射：≥8 高级 / ≥6 中级 / 其余初级；
- weak_points：近端历史中均分 < 6.0 的主题（与 legacy stats 薄弱阈值一致）。
- 会话结束（SUMMARIZING，G8）经 update_profile 工具批量写。
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any, Optional, Protocol

from app.utils.logger import get_logger

logger = get_logger(__name__)

EMPTY_PROFILE: dict[str, Any] = {
    "weak_points": [],
    "level": None,
    "accuracy": None,
    "history": [],
}

MAX_ACCURACY_WINDOW = 10
HISTORY_LIMIT = 50
_WEAK_SCORE_THRESHOLD = 6.0

_LEVEL_DIFFICULTY: dict[str, str] = {"初级": "easy", "中级": "medium", "高级": "hard"}


def level_to_difficulty(level: Optional[str]) -> str:
    """画像等级 → 初始难度（跨会话驱动难度，E6/决策 6）。未知/缺失 → medium。"""
    return _LEVEL_DIFFICULTY.get(level or "", "medium")


def compute_session_profile_patch(
    session_id: str,
    questions: list[dict],
    prev_profile: Optional[dict] = None,
) -> dict:
    """E6/F8 会话末聚合 patch：主问题（过滤 followup）分数追加进 history，
    accuracy = 最近 10 次单题分均值；weak_points / level 由历史推导。

    返回可整体写入 profile 的 patch（history 为追加后的完整列表）。
    """
    main_qs = [
        q for q in questions
        if q.get("source") != "followup" and q.get("answer")
    ]
    history: list[dict] = list((prev_profile or {}).get("history") or [])
    for q in main_qs:
        ev = q.get("evaluation") or {}
        history.append({
            "score": float(q.get("score") or 0),
            "fallback": ev.get("fallback"),  # G4-F → "eval_rule"；LLM 分 → None（保留标记）
            "session_id": session_id,
            "topic": q.get("topic") or "",
            "ts": q.get("created_at") or "",
        })
    history = history[-HISTORY_LIMIT:]

    recent = [h["score"] for h in history][-MAX_ACCURACY_WINDOW:]
    accuracy = round(sum(recent) / len(recent), 2) if recent else None

    topic_scores: dict[str, list[float]] = {}
    for h in history:
        if h["topic"]:
            topic_scores.setdefault(h["topic"], []).append(h["score"])
    weak_points = [
        t for t, scores in topic_scores.items()
        if (sum(scores) / len(scores)) < _WEAK_SCORE_THRESHOLD
    ][:10]

    level = None
    if accuracy is not None:
        level = "高级" if accuracy >= 8 else ("中级" if accuracy >= 6 else "初级")

    return {"weak_points": weak_points, "level": level, "accuracy": accuracy, "history": history}


class ProfileStore(Protocol):
    """画像存储 DI 接口（SessionProfileStore / RedisProfileStore 均满足）。"""

    def get(self, user_id: str) -> dict:
        """返回该用户画像（无记录返回空画像）。"""
        ...

    def update(self, user_id: str, patch: dict) -> None:
        """按 patch 深合并更新画像（增量写入，不整体覆盖）。"""
        ...


def _deep_merge(target: dict, patch: dict) -> None:
    """深合并：patch 中的 dict 递归合并，其余字段直接覆盖。"""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = deepcopy(value)


class SessionProfileStore:
    """会话内画像（内存 dict，按 user_id 隔离）。Redis 不可用时的降级形态。"""

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}

    def get(self, user_id: str) -> dict:
        """返回画像副本（防外部引用污染内部状态）。"""
        return deepcopy(self._profiles.get(user_id, EMPTY_PROFILE))

    def update(self, user_id: str, patch: dict) -> None:
        if user_id not in self._profiles:
            self._profiles[user_id] = deepcopy(EMPTY_PROFILE)
        _deep_merge(self._profiles[user_id], patch)


class RedisProfileStore:
    """Redis 长期画像（W2 下）：JSON 序列化存 `agent:profile:{user_id}`。

    - get：Redis 异常 → 返回空画像（工具层 degrade 语义，不抛）；
    - update：读-合并-写（TTL 可选，长期画像默认不过期）。
    """

    KEY_PREFIX = "agent:profile:"

    def __init__(self, redis_client: Any, *, key_prefix: str = KEY_PREFIX, ttl_seconds: Optional[int] = None):
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._ttl = ttl_seconds

    def _key(self, user_id: str) -> str:
        return f"{self._key_prefix}{user_id}"

    def get(self, user_id: str) -> dict:
        try:
            raw = self._redis.get(self._key(user_id))
            if not raw:
                return deepcopy(EMPTY_PROFILE)
            data = json.loads(raw)
            merged = deepcopy(EMPTY_PROFILE)
            _deep_merge(merged, data)
            return merged
        except Exception as e:  # noqa: BLE001 —— Redis 异常 → 空画像降级
            logger.warning("Redis profile get failed for %s: %s", user_id, e)
            return deepcopy(EMPTY_PROFILE)

    def update(self, user_id: str, patch: dict) -> None:
        current = self.get(user_id)
        _deep_merge(current, patch)
        self._redis.set(
            self._key(user_id), json.dumps(current, ensure_ascii=False), ex=self._ttl,
        )


def make_profile_store(
    *,
    host: str,
    port: int,
    db: int = 0,
    password: Optional[str] = None,
    timeout: float = 2.0,
    ttl_seconds: Optional[int] = None,
) -> ProfileStore:
    """装配画像存储：Redis 可用 → RedisProfileStore；不可用 → 会话内降级。"""
    try:
        import redis as redis_lib

        client = redis_lib.Redis(
            host=host, port=port, db=db, password=password or None,
            socket_connect_timeout=timeout, socket_timeout=timeout,
        )
        client.ping()
        logger.info("RedisProfileStore ready at %s:%s", host, port)
        return RedisProfileStore(client, ttl_seconds=ttl_seconds)
    except Exception as e:  # noqa: BLE001 —— Redis 不可用 → 降级会话内画像
        logger.warning("Redis profile unavailable (%s), fallback to session profile: %s", host, e)
        return SessionProfileStore()
