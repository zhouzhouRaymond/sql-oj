"""独立判题 Worker：从 Redis 消息队列消费提交并判题。

用法::

    python manage.py judge_worker --workers 4
    docker compose up -d --scale judge-worker=4     # 多容器水平扩展

说明：仅在 ``JUDGE_QUEUE_BACKEND=redis``（或 ``auto`` 且配置了 Redis URL）时可用；
``local`` 后端的判题线程随 Web 进程启动，无需本命令。

可靠性：``reserve`` 会把任务移入 inflight，处理完成再 ``ack``；Worker 崩溃
残留的 inflight 任务由空闲 Worker 通过 ``requeue_stale`` 回收重入队。
"""
import logging
import signal
import threading
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.submissions import job_queue
from apps.submissions.judging import run_judge_task

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = '从 Redis 判题队列消费任务（多 Worker 可水平扩展）'

    def add_arguments(self, parser):
        parser.add_argument('--workers', type=int, default=4, help='本进程内并发 Worker 线程数')
        parser.add_argument('--reserve-timeout', type=int, default=1, help='取任务的阻塞秒数')
        parser.add_argument('--once', action='store_true', help='处理完当前积压后退出（测试/排空）')

    def handle(self, *args, **options):
        if not job_queue.use_redis():
            self.stderr.write(
                '当前判题队列后端不是 redis（JUDGE_QUEUE_BACKEND=local）。'
                'local 后端的判题线程随 Web 进程启动；如需独立 Worker，'
                '请设置 JUDGE_QUEUE_BACKEND=redis 与 REDIS_URL。'
            )
            return

        queue = job_queue.get_redis_queue()
        stop = threading.Event()
        once = bool(options['once'])
        reserve_timeout = max(0, int(options['reserve_timeout']))
        workers = max(1, int(options['workers']))

        def _handle_signal(signum, frame):  # noqa: ANN001 - signal 回调
            logger.info('收到信号 %s，Worker 准备退出', signum)
            stop.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, _handle_signal)
            except (ValueError, OSError):
                # 非主线程 / 平台不支持时忽略，进程仍可被强制结束
                pass

        def worker(index: int) -> None:
            self.stdout.write(f'judge-worker-{index} started')
            while not stop.is_set():
                try:
                    submission_id = queue.reserve(timeout=reserve_timeout)
                except Exception:  # noqa: BLE001 - 队列异常不应终止 Worker
                    logger.exception('取判题任务失败，稍后重试')
                    time.sleep(1)
                    continue

                if submission_id is None:
                    # 空闲时回收超时未确认的任务，兜底 Worker 崩溃丢单
                    try:
                        queue.requeue_stale()
                    except Exception:  # noqa: BLE001
                        logger.exception('回收 inflight 任务失败')
                    if once:
                        return
                    continue

                handled = False
                try:
                    close_old_connections()
                    run_judge_task(int(submission_id))
                    handled = True
                except Exception:  # noqa: BLE001 - 单个任务失败不拖垮 Worker
                    logger.exception('判题任务处理失败 submission_id=%s', submission_id)
                finally:
                    try:
                        if handled:
                            queue.ack(submission_id)
                        else:
                            # 处理失败：退回 pending 立即重试，避免丢单
                            queue.requeue(submission_id)
                    except Exception:  # noqa: BLE001
                        logger.exception('回执判题任务失败 submission_id=%s', submission_id)
                    close_old_connections()

        threads = [
            threading.Thread(target=worker, args=(i,), name=f'judge-worker-{i}')
            for i in range(workers)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.stdout.write('judge_worker 已退出')
