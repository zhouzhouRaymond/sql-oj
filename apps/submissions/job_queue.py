"""判题消息队列：支持「进程内」与「外部 Redis」两种后端。

- ``local``：进程内队列 + Web 进程内的后台线程（默认，开发/单机足够）；
- ``redis``：外部消息队列，Web 进程只入队、独立 Worker 进程消费，
  多个 Worker 进程/容器可水平扩展。

可靠性（redis 后端）：用 ``BRPOPLPUSH`` 把任务从 pending 原子搬到 inflight，
处理成功再 ``ack`` 移除；进程崩溃导致残留的 inflight 任务由
``requeue_stale`` 在可见性超时后重新入队。

后端选择（环境变量）：

- ``JUDGE_QUEUE_BACKEND``：``auto``（默认）| ``local`` | ``redis``；
  ``auto`` 时配置了 Redis URL 就用 redis，否则用 local。
- ``JUDGE_QUEUE_REDIS_URL`` / ``REDIS_URL``：Redis 连接串。
- ``JUDGE_QUEUE_VISIBILITY_TIMEOUT``：inflight 可见性超时（秒，默认 120）。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

PENDING_KEY = "judge:queue:pending"
INFLIGHT_KEY = "judge:queue:inflight"
INFLIGHT_TS_KEY = "judge:queue:inflight:ts"


class JudgeQueueUnavailable(RuntimeError):
    """配置为 Redis 队列但不可用（缺 redis 包 / 未配置 URL / 连接失败）。"""


def redis_url() -> str:
    return (
        os.environ.get("JUDGE_QUEUE_REDIS_URL")
        or os.environ.get("REDIS_URL")
        or ""
    )


def backend_name() -> str:
    """返回实际使用的后端名：``local`` 或 ``redis``。"""
    configured = os.environ.get("JUDGE_QUEUE_BACKEND", "auto").strip().lower()
    if configured == "auto":
        return "redis" if redis_url() else "local"
    if configured not in ("local", "redis"):
        logger.warning("未知 JUDGE_QUEUE_BACKEND=%r，回退 local", configured)
        return "local"
    return configured


def use_redis() -> bool:
    return backend_name() == "redis"


def _visibility_timeout() -> int:
    try:
        return max(1, int(os.environ.get("JUDGE_QUEUE_VISIBILITY_TIMEOUT", "120")))
    except ValueError:
        return 120


def _as_str(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value)


class RedisJudgeQueue:
    """基于 Redis list + zset 的可靠判题队列。

    ``client`` 可注入（测试时传入假客户端），默认由 :func:`get_redis_queue` 创建。
    """

    def __init__(self, client: Any, visibility_timeout: Optional[int] = None):
        self._client = client
        self._visibility = visibility_timeout or _visibility_timeout()

    def enqueue(self, submission_id: int) -> None:
        self._client.lpush(PENDING_KEY, submission_id)

    def reserve(self, timeout: int = 1) -> Optional[str]:
        """阻塞取一个任务并移入 inflight；超时无任务返回 ``None``。"""
        item = self._client.brpoplpush(PENDING_KEY, INFLIGHT_KEY, timeout)
        if item is None:
            return None
        submission_id = _as_str(item)
        self._client.zadd(INFLIGHT_TS_KEY, {submission_id: time.time()})
        return submission_id

    def ack(self, submission_id: str) -> None:
        self._client.lrem(INFLIGHT_KEY, 1, submission_id)
        self._client.zrem(INFLIGHT_TS_KEY, submission_id)

    def requeue(self, submission_id: str) -> None:
        """把未处理成功的任务从 inflight 退回 pending（立即重试）。"""
        if self._client.lrem(INFLIGHT_KEY, 1, submission_id):
            self._client.lpush(PENDING_KEY, submission_id)
        self._client.zrem(INFLIGHT_TS_KEY, submission_id)

    def requeue_stale(self) -> int:
        """把超过可见性超时仍未 ack 的任务重新入队（Worker 崩溃恢复）。"""
        cutoff = time.time() - self._visibility
        stale = self._client.zrangebyscore(INFLIGHT_TS_KEY, "-inf", cutoff)
        moved = 0
        for raw in stale:
            submission_id = _as_str(raw)
            if self._client.lrem(INFLIGHT_KEY, 1, submission_id):
                self._client.lpush(PENDING_KEY, submission_id)
                moved += 1
            self._client.zrem(INFLIGHT_TS_KEY, submission_id)
        if moved:
            logger.warning("判题队列回收 %s 个超时未确认任务", moved)
        return moved

    def depth(self) -> int:
        return int(self._client.llen(PENDING_KEY))

    def inflight(self) -> int:
        return int(self._client.llen(INFLIGHT_KEY))


_redis_queue: Optional[RedisJudgeQueue] = None


def get_redis_queue() -> RedisJudgeQueue:
    """返回进程内单例 Redis 队列；不可用时抛 :class:`JudgeQueueUnavailable`。"""
    global _redis_queue
    if _redis_queue is not None:
        return _redis_queue

    url = redis_url()
    if not url:
        raise JudgeQueueUnavailable("未配置 JUDGE_QUEUE_REDIS_URL / REDIS_URL")
    try:
        import redis  # 延迟导入：未启用 Redis 时无需安装
    except ImportError as exc:
        raise JudgeQueueUnavailable(
            "使用 Redis 判题队列需先安装 redis 包（pip install redis）"
        ) from exc

    client = redis.Redis.from_url(url, decode_responses=False)
    client.ping()
    _redis_queue = RedisJudgeQueue(client)
    logger.info("判题队列后端：redis（%s）", url)
    return _redis_queue
