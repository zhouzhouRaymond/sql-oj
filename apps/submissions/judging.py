"""判题异步执行：把耗时的判题调用放到后台线程，避免阻塞 Django 请求 worker。

设计要点：

- 进程内后台队列 + 固定数量工作线程（无需额外引入 Celery / 消息队列）；
- 入队即返回，请求线程不再等待判题完成；接口返回 ``submission_id`` 供前端轮询；
- 判题结果**异步批量**回写 ``Submission``（见 ``result_writer``），不阻塞主流程；
- 相同「题目 + SQL 规范化 + 用例 + 环境指纹」命中结果缓存时跳过判题容器；
- 判题服务连续失败触发熔断，OPEN 期间快速失败，避免雪崩；
- 队列有上限，满时抛 ``JudgeQueueFull``，由视图返回 503 实现背压。

局限：这是进程内实现，进程重启会丢失仍在队列中的任务（对应提交会停留在
``PENDING``）。可用 ``python manage.py requeue_pending`` 在重启后重新入队。
"""
import logging
import os
import queue
import threading
from typing import Dict, List

from django.db import close_old_connections

from apps.questions.cache import get_bundle

from . import job_queue
from .circuit_breaker import JudgeCircuitOpen, judge_breaker
from .judge import JudgeTransportError, judge_submission_strict
from .judge_cache import get_cached_result, set_cached_result
from .result_writer import result_writer
from .status import CACHEABLE_STATUSES, ERROR, PENDING

logger = logging.getLogger(__name__)

# 判题后台线程数与队列上限，可通过环境变量调整
JUDGE_WORKERS = int(os.environ.get('JUDGE_WORKERS', '4'))
JUDGE_QUEUE_SIZE = int(os.environ.get('JUDGE_QUEUE_SIZE', '200'))

class JudgeQueueFull(RuntimeError):
    """判题任务队列已满（服务繁忙，可稍后重试）。"""


_queue: "queue.Queue[int]" = queue.Queue(maxsize=JUDGE_QUEUE_SIZE)
_workers_started = False
_start_lock = threading.Lock()


def queue_depth() -> int:
    """当前待判题队列长度（监控指标：队列堆积量）。"""
    if job_queue.use_redis():
        try:
            return job_queue.get_redis_queue().depth()
        except job_queue.JudgeQueueUnavailable:
            return 0
    return _queue.qsize()


def _worker_loop() -> None:
    while True:
        submission_id = _queue.get()
        try:
            close_old_connections()
            run_judge_task(submission_id)
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


def _load_question_bundle(question) -> Dict:
    """取题目判题元数据（用例 / 建表语句），优先走本地缓存。

    用例按 id 固定顺序，保证用例指纹与 judge_details 的编号稳定。
    极端情况（缓存异常、题目刚删除）退回直查，保证判题不被缓存问题中断。
    """
    bundle = get_bundle(question.id)
    if bundle is not None:
        return bundle
    return {
        'test_cases': list(
            question.test_cases.order_by('id').values('test_input', 'expected_output')
        ),
        'create_table_sql': question.create_table_sql or '',
    }


def _judge_with_guards(
    question_id: int, submitted_sql: str, test_cases: List[Dict[str, str]], create_table_sql: str
) -> Dict:
    """带缓存 + 熔断的判题调用；返回判题结果字典（不抛通信异常）。"""
    cached = get_cached_result(question_id, submitted_sql, test_cases)
    if cached is not None:
        return cached

    try:
        judge_breaker.ensure_allowed()
    except JudgeCircuitOpen as exc:
        logger.warning("判题熔断：%s", exc)
        return _transport_error_result("判题服务繁忙（熔断中），请稍后重试")

    try:
        result = judge_submission_strict(submitted_sql, test_cases, create_table_sql)
    except JudgeTransportError as exc:
        judge_breaker.record_failure()
        logger.warning("判题服务通信失败：%s", exc)
        return _transport_error_result("判题服务暂时不可用，请稍后重试")

    judge_breaker.record_success()
    # 只缓存确定性结果（ACCEPTED / WRONG_ANSWER）；判题服务侧 ERROR（如连接池
    # 耗尽、DB 抖动）属瞬时故障，缓存会让相同提交在 TTL 内持续拿到旧错误。
    if result.get('execution_status') in CACHEABLE_STATUSES:
        set_cached_result(question_id, submitted_sql, test_cases, result)
    return result


def _transport_error_result(message: str) -> Dict:
    return {
        "passed": False,
        "execution_status": ERROR,
        "score": 0,
        "details": [],
        "error_message": message,
    }


def _score_for(submission, status: str, judge_score: int) -> int:
    """考试提交按该题在考试中的分值换算（ACCEPTED 得满分，否则 0）。"""
    if not submission.exam_id:
        return judge_score

    from apps.exams.models import ExamQuestion

    max_score = (
        ExamQuestion.objects.filter(
            exam_id=submission.exam_id, question_id=submission.question_id
        )
        .values_list('score', flat=True)
        .first()
    )
    return (max_score or 0) if status == 'ACCEPTED' else 0


def run_judge_task(submission_id: int) -> None:
    """执行一次判题并把结果交给异步批量写线程。"""
    from .models import Submission

    try:
        submission = Submission.objects.select_related('question').get(id=submission_id)
    except Submission.DoesNotExist:
        logger.warning("待判题提交不存在：%s", submission_id)
        return

    question = submission.question
    bundle = _load_question_bundle(question)
    test_cases = bundle['test_cases']

    try:
        result = _judge_with_guards(
            question.id, submission.submitted_sql, test_cases,
            bundle['create_table_sql'],
        )
        status = result.get('execution_status') or ERROR
        judge_score = int(result.get('score', 0) or 0)
        # 判题服务只返回「实际输出」，不含用例输入与预期输出，故可安全落库
        judge_details = {
            'cases': result.get('details') or [],
            'error_message': result.get('error_message') or '',
        }
    except Exception:  # noqa: BLE001 - 判题失败统一记为 ERROR
        logger.exception("判题失败 submission_id=%s", submission_id)
        status, judge_score = ERROR, 0
        judge_details = {
            'cases': [],
            'error_message': '判题服务异常，请稍后重试',
        }

    score = _score_for(submission, status, judge_score)
    # 硬性约束：写库异步批量，不在此处阻塞等待 UPDATE
    result_writer.enqueue(submission_id, status, score, judge_details)


def enqueue_judge(submission_id: int) -> None:
    """把一次提交放入判题队列；队列满/后端不可用时抛 ``JudgeQueueFull``。

    - ``redis`` 后端：仅入队，由独立的 judge_worker 进程消费（可水平扩展）；
    - ``local`` 后端：入进程内队列，Web 进程内的后台线程消费。
    """
    if job_queue.use_redis():
        try:
            job_queue.get_redis_queue().enqueue(submission_id)
        except job_queue.JudgeQueueUnavailable as exc:
            logger.error("判题队列不可用：%s", exc)
            raise JudgeQueueFull("判题队列不可用") from None
        return

    _ensure_workers()
    try:
        _queue.put_nowait(submission_id)
    except queue.Full:
        raise JudgeQueueFull("判题任务队列已满") from None


__all__ = [
    'JudgeQueueFull',
    'PENDING',
    'enqueue_judge',
    'queue_depth',
    'run_judge_task',
]
