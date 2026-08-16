"""会话级 Token 成本累计与预算告警。内存实现，接口可替换为 Redis。"""
from threading import Lock

from app.config import settings

_lock = Lock()
_cost: dict[str, float] = {}


def add(session_id: str, cost: float) -> None:
    with _lock:
        _cost[session_id] = _cost.get(session_id, 0.0) + cost


def total(session_id: str) -> float:
    with _lock:
        return _cost.get(session_id, 0.0)


def is_over_budget(session_id: str) -> bool:
    return total(session_id) > settings.session_token_budget


def reset() -> None:
    with _lock:
        _cost.clear()