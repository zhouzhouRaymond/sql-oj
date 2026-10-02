"""判题异步执行：把耗时的判题调用放到后台线程，避免阻塞 Django 请求 worker。

设计要点：
- 进程内后台队列 + 固定数量工作线程（无需额外引入 Celery / 消息队列）；
- 入队即返回，请求线程不再等待判题完成，判题结果异步写回 ``Submission``；
- 队列有上限，满时抛 ``JudgeQueueFull``，由视图返回 503 实现背压；
- 每个任务前后调用 ``close_old_connections()``，避免后台线程持留失效的 MySQL 连接。

局限：这是进程内实现，进程重启会丢失仍在队列中的任务（对应提交会停留在
``PENDING``）。可用 ``python manage.py requeue_pending`` 在重启后重新入队。
"""
import logging
import os
import queue
import threading

from django.db import close_old_connections

logger = logging.getLogger(__name__)

# 判题后台线程数与队列上限，可通过环境变量调整
JUDGE_WORKERS = int(os.environ.get('JUDGE_WORKERS', '4'))
JUDGE_QUEUE_SIZE = int(os.environ.get('JUDGE_QUEUE_SIZE', '200'))

# 待判题状态：非该值即视为已出结果
PENDING = 'PENDING'


class JudgeQueueFull(RuntimeError):
    """判题任务队列已满（服务繁忙，可稍后重试）。"""


_queue: "queue.Queue[int]" = queue.Queue(maxsize=JUDGE_QUEUE_SIZE)
_workers_started = False
_start_lock = threading.Lock()


def _worker_loop() -> None:
    while True:
        submission_id = _queue.get()
        try:
            close_old_connections()
            _run_judge(submission_id)
        except Exception:  # noqa: BLE001 - 单个任务失败不应拖垮工作线程
            logger.exception("后台判题异常 submission_id=%s", submission_id)
        finally:
            close_old_connections()
            _queue.task_done()


def _ensure_workers() -> None:
    """惰性启动后台判题线程（首次入队时触发，管理命令不会启动它们）。"""
    global _workers_started
    with _start_lock:
        if _workers_started:
            return
        for i in range(max(1, JUDGE_WORKERS)):
            threading.Thread(
                target=_worker_loop, name=f"judge-worker-{i}", daemon=True
            ).start()
        _workers_started = True
        logger.info("判题后台线程已启动：%s 个（队列上限 %s）", JUDGE_WORKERS, JUDGE_QUEUE_SIZE)


def _run_judge(submission_id: int) -> None:
    """执行一次判题并把结果写回 ``Submission``。"""
    from apps.exams.models import ExamQuestion

    from .judge import judge_submission
    from .models import Submission

    try:
        submission = Submission.objects.select_related('question').get(id=submission_id)
    except Submission.DoesNotExist:
        logger.warning("待判题提交不存在：%s", submission_id)
        return

    question = submission.question
    # 按 id 固定顺序，保证用例序号稳定（judge_details 里的 test_case_id 与之对应）
    test_cases = list(
        question.test_cases.order_by('id').values('test_input', 'expected_output')
    )
    try:
        result = judge_submission(
            submission.submitted_sql, test_cases, question.create_table_sql or ''
        )
        status = result.get('execution_status') or 'ERROR'
        judge_score = int(result.get('score', 0) or 0)
        # 保存用例明细（判题服务只返回「实际输出」，不含用例输入与预期输出）
        judge_details = {
            'cases': result.get('details') or [],
            'error_message': result.get('error_message') or '',
        }
    except Exception:  # noqa: BLE001 - 判题失败统一记为 ERROR
        logger.exception("判题失败 submission_id=%s", submission_id)
        status, judge_score = 'ERROR', 0
        judge_details = {
            'cases': [],
            'error_message': '判题服务异常，请稍后重试',
        }

    # 考试提交：得分按该题在考试中的分值换算（ACCEPTED 得满分，否则 0）
    if submission.exam_id:
        max_score = (
            ExamQuestion.objects.filter(
                exam_id=submission.exam_id, question_id=submission.question_id
            )
            .values_list('score', flat=True)
            .first()
        )
        score = (max_score or 0) if status == 'ACCEPTED' else 0
    else:
        score = judge_score

    Submission.objects.filter(id=submission_id).update(
        execution_status=status, score=score, judge_details=judge_details
    )


def enqueue_judge(submission_id: int) -> None:
    """把一次提交放入后台判题队列；队列满时抛 ``JudgeQueueFull``。"""
    _ensure_workers()
    try:
        _queue.put_nowait(submission_id)
    except queue.Full:
        raise JudgeQueueFull("判题任务队列已满") from None
