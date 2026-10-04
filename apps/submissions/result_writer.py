"""判题结果**异步批量**回写。

硬性约束：写库一律异步批量，禁止阻塞主判题流程。

判题工作者不再逐条 ``UPDATE``，而是把结果交给本模块的后台写线程：

- 结果先入内存缓冲（同一提交以最后一次为准），由后台线程按
  ``JUDGE_RESULT_FLUSH_INTERVAL`` 秒或 ``JUDGE_RESULT_FLUSH_BATCH`` 条批量刷库；
- 批量落库使用 ``bulk_update``，把 N 次 UPDATE 合并为一条语句；
- 进程退出（``atexit``）时尽力 flush 一次，减少结果滞留。

说明：缓冲丢失（如进程被 kill -9）会让对应提交停留在 ``PENDING``，
可用 ``python manage.py requeue_pending`` 重新入队，与现有队列模型一致。
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
from typing import Any, Dict, Optional, Tuple

from django.db import close_old_connections

logger = logging.getLogger(__name__)


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, str(default)))
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


FLUSH_INTERVAL = _env_float("JUDGE_RESULT_FLUSH_INTERVAL", 0.2)
FLUSH_BATCH = max(1, _env_int("JUDGE_RESULT_FLUSH_BATCH", 100))

# submission_id -> (status, score, judge_details)
_Pending = Tuple[str, int, Dict[str, Any]]


class SubmissionResultWriter:
    """后台批量回写判题结果；线程安全、懒启动。"""

    def __init__(self, flush_interval: float = FLUSH_INTERVAL, flush_batch: int = FLUSH_BATCH):
        self._flush_interval = max(0.01, flush_interval)
        self._flush_batch = max(1, flush_batch)
        self._buffer: Dict[int, _Pending] = {}
        self._lock = threading.Lock()
        self._wakeup = threading.Event()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- 对外接口 -----------------------------------------------------
    def enqueue(
        self,
        submission_id: int,
        status: str,
        score: int,
        judge_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """把一条判题结果加入缓冲（不落库、不阻塞）。"""
        self._ensure_started()
        with self._lock:
            self._buffer[submission_id] = (status, int(score or 0), judge_details or {})
            should_wake = len(self._buffer) >= self._flush_batch
        if should_wake:
            self._wakeup.set()

    def flush(self) -> int:
        """立即落库当前缓冲，返回写入条数（供测试/停机调用）。"""
        with self._lock:
            if not self._buffer:
                return 0
            batch = self._buffer
            self._buffer = {}
        return self._write(batch)

    def stop(self, flush: bool = True) -> None:
        """停止后台线程（测试用），可选先 flush。"""
        self._stop.set()
        self._wakeup.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if flush:
            self.flush()

    # ---- 内部实现 -----------------------------------------------------
    def _ensure_started(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop, name="judge-result-writer", daemon=True
            )
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wakeup.wait(self._flush_interval)
            self._wakeup.clear()
            try:
                self.flush()
            except Exception:  # noqa: BLE001 - 写失败不能让后台线程退出
                logger.exception("判题结果批量回写失败")

    @staticmethod
    def _write(batch: Dict[int, _Pending]) -> int:
        from .models import Submission

        close_old_connections()
        objs = [
            Submission(
                id=submission_id,
                execution_status=status,
                score=score,
                judge_details=judge_details,
            )
            for submission_id, (status, score, judge_details) in batch.items()
        ]
        try:
            Submission.objects.bulk_update(
                objs, ["execution_status", "score", "judge_details"]
            )
        except Exception:
            # 不吞异常：交给调用方（后台循环）记录；对象已被本地引用，重试由上层决定
            raise
        finally:
            close_old_connections()
        return len(objs)


# 进程内单例：所有判题工作者共用一个写线程
result_writer = SubmissionResultWriter()

# 进程退出时尽力 flush，减少结果滞留（如 gunicorn worker 优雅退出）
atexit.register(lambda: _safe_flush(result_writer))


def _safe_flush(writer: SubmissionResultWriter) -> None:
    try:
        writer.flush()
    except Exception:  # noqa: BLE001
        logger.exception("退出前刷写判题结果失败")


def flush_results() -> int:
    """便捷函数：立即刷写缓冲（测试 / 管理命令用）。"""
    return result_writer.flush()


__all__ = ["SubmissionResultWriter", "result_writer", "flush_results"]
