"""判题服务熔断器。

硬性约束（推荐架构「熔断降级」）：判题容器错误率过高时暂停新任务，
避免每个请求都去撞一个已经出问题的判题服务而雪崩。

实现要素：

- 进程内统计**连续**失败次数；达到阈值后进入 OPEN 状态；
- OPEN 状态用 Django 缓存记录到期时间戳，缓存指向 Redis 时可多进程共享；
- OPEN 期间新任务快速失败（不调用判题服务），冷却结束后放行探测请求；
- 探测成功即清零、恢复 CLOSED。
"""
from __future__ import annotations

import logging
import os
import threading
import time

from django.core.cache import cache

logger = logging.getLogger(__name__)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError:
        return default


FAILURE_THRESHOLD = max(1, _env_int("JUDGE_BREAKER_THRESHOLD", 5))
COOLDOWN_SECONDS = max(1.0, _env_float("JUDGE_BREAKER_COOLDOWN", 10.0))
_OPEN_UNTIL_KEY = "judge:breaker:open_until"


class JudgeCircuitOpen(RuntimeError):
    """判题服务处于熔断 OPEN 状态，新任务被快速拒绝（可稍后重试）。"""


class CircuitBreaker:
    """连续失败触发的简单熔断器（进程内计数 + 缓存共享 OPEN 标志）。"""

    def __init__(
        self,
        threshold: int = FAILURE_THRESHOLD,
        cooldown: float = COOLDOWN_SECONDS,
        open_key: str = _OPEN_UNTIL_KEY,
    ):
        self._threshold = max(1, threshold)
        self._cooldown = max(1.0, cooldown)
        self._open_key = open_key
        self._lock = threading.Lock()
        self._failures = 0

    def allow(self) -> bool:
        """当前是否放行（CLOSED / HALF_OPEN）。OPEN 且未到冷却时间返回 False。"""
        open_until = cache.get(self._open_key)
        if open_until is None:
            return True
        try:
            return time.time() >= float(open_until)
        except (TypeError, ValueError):
            cache.delete(self._open_key)
            return True

    def ensure_allowed(self) -> None:
        """OPEN 时抛 :class:`JudgeCircuitOpen`，否则放行。"""
        if not self.allow():
            raise JudgeCircuitOpen("判题服务熔断中，暂停接收新任务")

    def record_success(self) -> None:
        with self._lock:
            self._failures = 0
        cache.delete(self._open_key)

    def record_failure(self) -> None:
        with self._lock:
            self._failures += 1
            tripped = self._failures >= self._threshold
            if tripped:
                self._failures = 0
        if tripped:
            open_until = time.time() + self._cooldown
            cache.set(self._open_key, open_until, timeout=int(self._cooldown) + 1)
            logger.warning(
                "判题服务连续失败达 %s 次，熔断 %ss", self._threshold, self._cooldown
            )


# 进程内单例
judge_breaker = CircuitBreaker()
