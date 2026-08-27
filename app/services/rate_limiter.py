"""轻量级进程内滑动窗口限流器（单 worker 适用，按 IP 计）。

核心设计：
- 内存 deque 存储每个 IP 的请求时间戳，不清除过期数据（惰性清理）。
- 每次请求到达时剔除窗口外的时间戳，若剩余量 ≥ 上限则拒绝。
- 100 个活跃 IP × 120 次/分钟 ≈ 每个 IP 最多保留 120 个时间戳。
- 不需要外部依赖，零网络开销。
"""

import time
from collections import defaultdict, deque
from typing import Callable

from fastapi import Request, HTTPException

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


class _SlidingWindowRateLimiter:
    """进程内滑动窗口限流器（单例，进程内全局共享）。"""

    def __init__(self):
        self._windows: dict[str, deque[float]] = defaultdict(deque)
        self._window_seconds = 60

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        client = request.client
        return client.host if client else "unknown"

    def check(self, request: Request) -> None:
        ip = self._client_ip(request)
        now = time.time()
        cutoff = now - self._window_seconds
        dq = self._windows[ip]
        # 清除窗口外的时间戳（惰性）
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= settings.ratelimit_per_minute:
            logger.warning(f"Rate limit exceeded for IP: {ip} ({len(dq)}/{settings.ratelimit_per_minute})")
            raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
        dq.append(now)


# 单例
_rate_limiter = _SlidingWindowRateLimiter()


def rate_limit_dependency(request: Request) -> None:
    """FastAPI Depends 可调用对象：按 IP 限流。"""
    _rate_limiter.check(request)