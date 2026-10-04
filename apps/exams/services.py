"""考试相关的领域逻辑：提交落库并入判题队列、作答草稿的兜底交卷。

放在这里而不是视图里，便于视图与 management command 共用同一套规则
（手动交卷与兜底交卷必须产生完全一致的提交记录）。
"""
from django.utils import timezone

from apps.questions.models import Question
from apps.submissions.models import Submission
from apps.submissions.services import create_submission

from .models import ExamAttempt


def create_exam_submission(exam, student, question_id, submitted_sql):
    """为某道题创建一条「待判题」的考试提交并交给判题队列。

    相同（学生 + 考试 + 题目 + SQL 规范化）在幂等窗口内重复调用会复用既有提交，
    不重复创建判题任务。落库/幂等/入队的共用逻辑见
    ``apps.submissions.services.create_submission``。

    返回 ``(submission, error)``：

    - ``error`` 为空：已成功入队（或复用了既有提交），``submission`` 即对应记录；
    - ``error`` 为「题目不存在」：``submission`` 为 None；
    - ``error`` 为「判题服务繁忙」：``submission`` 已落库但状态为 ERROR。
    """
    try:
        question = Question.objects.get(id=question_id)
    except Question.DoesNotExist:
        return None, '题目不存在'

    result = create_submission(student, question, submitted_sql, exam=exam)
    if result.queue_full:
        return result.submission, '判题服务繁忙'
    return result.submission, ''


def draft_answers_as_list(draft):
    """把 ``{题目 id: SQL}`` 草稿转成 ``[{question_id, submitted_sql}]``，忽略空作答。"""
    answers = []
    for question_id, sql in (draft or {}).items():
        sql = str(sql or '').strip()
        if not sql:
            continue
        try:
            answers.append({'question_id': int(question_id), 'submitted_sql': sql})
        except (TypeError, ValueError):
            continue
    return answers


def finalize_expired_attempts(now=None, exam=None, student=None):
    """兜底交卷：把「作答截止时间已过、且从未交卷」的考生按最后同步的草稿交卷。

    场景：学生作答到一半关掉浏览器（或断网），前端倒计时到点后无法再自动交卷，
    若不处理这次作答会永远停留在「未提交」。这里用服务端保存的草稿把它交上，
    保证成绩不漏；没有草稿（从未作答）的考生保持「未提交」，由教师决定是否重置。

    采用「懒执行」：在 start / 排名 / 导出 / 我的得分等入口调用即可，无需额外
    定时任务；也可以用 ``python manage.py finalize_expired_exams`` 手动兜底。

    返回被自动交卷的 ExamAttempt 列表。
    """
    now = now or timezone.now()
    attempts = ExamAttempt.objects.filter(deadline__lte=now).select_related('student')
    if exam is not None:
        attempts = attempts.filter(exam=exam)
    if student is not None:
        attempts = attempts.filter(student=student)

    finalized = []
    for attempt in attempts:
        # 已交过卷（手动交卷或此前已兜底）不再处理
        if Submission.objects.filter(
            exam=attempt.exam, student=attempt.student
        ).exists():
            continue
        answers = draft_answers_as_list(attempt.draft_answers)
        if not answers:
            continue

        created = False
        for ans in answers:
            submission, error = create_exam_submission(
                attempt.exam, attempt.student, ans['question_id'], ans['submitted_sql'],
            )
            if submission is not None and not error:
                created = True
        if created:
            finalized.append(attempt)
    return finalized
