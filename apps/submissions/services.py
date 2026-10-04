"""提交判题的领域逻辑：幂等去重 + 落库 + 入队。

题库提交（``apps.submissions.views``）与考试交卷（``apps.exams.services``）
都走这里，保证两条入口的幂等键、落库字段和入队语义完全一致。
视图层只负责把结果映射成 HTTP 响应，不再重复这套流程。
"""
from dataclasses import dataclass

from .idempotency import (
    find_duplicate_submission,
    idempotency_key,
    remember_submission,
)
from .judging import JudgeQueueFull, enqueue_judge
from .models import Submission
from .status import ERROR, PENDING


@dataclass(frozen=True)
class CreatedSubmission:
    """一次「提交判题」的结果。

    属性:
        submission: 新建或复用的提交记录
        duplicate: True 表示命中幂等窗口，复用了既有记录、未新建判题任务
        queue_full: True 表示已落库但入队失败，记录已被置为 ``ERROR``
    """

    submission: Submission
    duplicate: bool = False
    queue_full: bool = False


def create_submission(student, question, submitted_sql, exam=None) -> CreatedSubmission:
    """创建待判题提交并交给判题队列（幂等）。

    相同（学生 + 题目 + 考试 + SQL 规范化结果）在幂等窗口内重复调用会复用
    既有提交，不重复创建判题任务。入队失败不抛异常，而是返回
    ``queue_full=True`` 并把记录置为 ``ERROR``，由调用方决定如何回给前端。
    """
    exam_id = getattr(exam, 'id', None)
    idem_key = idempotency_key(student.id, question.id, exam_id, submitted_sql)

    duplicate = find_duplicate_submission(
        student, question, exam_id, submitted_sql, idem_key
    )
    if duplicate is not None:
        remember_submission(idem_key, duplicate.id)
        return CreatedSubmission(submission=duplicate, duplicate=True)

    submission = Submission.objects.create(
        student=student,
        question=question,
        exam=exam,
        submitted_sql=submitted_sql,
        execution_status=PENDING,
        score=0,
    )
    try:
        enqueue_judge(submission.id)
    except JudgeQueueFull:
        submission.execution_status = ERROR
        submission.save(update_fields=['execution_status'])
        return CreatedSubmission(submission=submission, queue_full=True)

    remember_submission(idem_key, submission.id)
    return CreatedSubmission(submission=submission)


__all__ = ['CreatedSubmission', 'create_submission']
