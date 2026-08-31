"""候选人画像存储（impl-spec v2 附录 D profile_store / 附录 E6 F8 口径）。

W2下 将实现 Redis 长期画像（跨会话）；当前为**「会话内画像」降级形态**
（spec 砍单链：长期记忆可降为会话内画像）。接口保持 DI 友好，
W2下 以 Redis 实现替换 `SessionProfileStore` 即可，工具层无需改动。

口径（E6/F8 冻结）：
- 历史正确率 = 近 10 次主问题单题分均值（本最小实现仅做存取；
  聚合与过滤 `source='followup'` 由上层（profile 写入方）完成）。
- 空画像默认：`{"weak_points": [], "level": None, "accuracy": None, "history": []}`。
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

EMPTY_PROFILE: dict[str, Any] = {
    "weak_points": [],
    "level": None,
    "accuracy": None,
    "history": [],
}


class ProfileStore(Protocol):
    """画像存储 DI 接口（W2下 Redis 实现满足同一协议）。"""

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
    """会话内画像（内存 dict，按 user_id 隔离）。W2下 Redis 版的降级形态。"""

    def __init__(self) -> None:
        self._profiles: dict[str, dict[str, Any]] = {}

    def get(self, user_id: str) -> dict:
        """返回画像副本（防外部引用污染内部状态）。"""
        return deepcopy(self._profiles.get(user_id, EMPTY_PROFILE))

    def update(self, user_id: str, patch: dict) -> None:
        if user_id not in self._profiles:
            self._profiles[user_id] = deepcopy(EMPTY_PROFILE)
        _deep_merge(self._profiles[user_id], patch)
