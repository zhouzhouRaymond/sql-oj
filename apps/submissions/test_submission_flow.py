"""提交链路集成测试（需要数据库）：API 入口、考试交卷服务与重入队命令。"""
from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.exams.models import Exam
from apps.exams.services import create_exam_submission
from apps.questions.models import Question, TestCase as QuestionTestCase
from apps.users.models import User

from .judging import JudgeQueueFull
from .models import Submission
from .status import ERROR, PENDING


def _make_question(teacher, **overrides):
    fields = {
        'description': '提交链路测试题',
        'difficulty': 'easy',
        'teacher': teacher,
        'create_table_sql': 'CREATE TABLE t (id INT);',
    }
    fields.update(overrides)
    return Question.objects.create(**fields)


def _make_exam(teacher, *, open_now=True):
    now = timezone.now()
    if open_now:
        start, end = now - timedelta(hours=1), now + timedelta(hours=1)
    else:
        start, end = now - timedelta(hours=2), now - timedelta(hours=1)
    return Exam.objects.create(
        title='提交链路考试', start_time=start, end_time=end,
        total_score=100, teacher=teacher,
    )


class SubmissionApiFlowTests(APITestCase):
    """``POST /api/submissions/submit/`` 的关键分支。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_flow', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_flow', password='pass1234', user_type='student',
        )
        self.question = _make_question(self.teacher)
        self.client.force_authenticate(self.student)

    def _submit(self, **extra):
        payload = {'question_id': self.question.id, 'submitted_sql': 'select 1'}
        payload.update(extra)
        return self.client.post('/api/submissions/submit/', payload, format='json')

    @patch('apps.submissions.services.enqueue_judge')
    def test_submit_returns_202_and_enqueues(self, enqueue):
        response = self._submit()

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        submission = Submission.objects.get(id=response.data['id'])
        self.assertEqual(submission.execution_status, PENDING)
        self.assertEqual(submission.score, 0)
        enqueue.assert_called_once_with(submission.id)

    @patch('apps.submissions.services.enqueue_judge', side_effect=JudgeQueueFull('full'))
    def test_queue_full_returns_503_and_marks_error(self, enqueue):
        response = self._submit()

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        submission = Submission.objects.get(id=response.data['submission_id'])
        self.assertEqual(submission.execution_status, ERROR)

    @patch('apps.submissions.services.enqueue_judge')
    def test_exam_submission_inside_window_is_queued(self, enqueue):
        exam = _make_exam(self.teacher, open_now=True)
        response = self._submit(exam_id=exam.id)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        submission = Submission.objects.get(id=response.data['id'])
        self.assertEqual(submission.exam_id, exam.id)
        enqueue.assert_called_once_with(submission.id)

    def test_exam_submission_outside_window_is_rejected(self):
        exam = _make_exam(self.teacher, open_now=False)
        response = self._submit(exam_id=exam.id)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Submission.objects.count(), 0)

    def test_missing_required_fields_returns_400(self):
        response = self.client.post('/api/submissions/submit/', {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ExamSubmissionServiceTests(TestCase):
    """``create_exam_submission`` 的幂等、缺题与入队失败分支。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_exam_flow', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_exam_flow', password='pass1234', user_type='student',
        )
        self.question = _make_question(self.teacher)
        self.exam = _make_exam(self.teacher)

    def test_missing_question_returns_error(self):
        submission, error = create_exam_submission(
            self.exam, self.student, 999999, 'select 1'
        )
        self.assertIsNone(submission)
        self.assertEqual(error, '题目不存在')

    @patch('apps.submissions.services.enqueue_judge')
    def test_duplicate_exam_submission_is_reused(self, enqueue):
        first, first_error = create_exam_submission(
            self.exam, self.student, self.question.id, 'select 1'
        )
        second, second_error = create_exam_submission(
            self.exam, self.student, self.question.id, 'SELECT   1'
        )

        self.assertEqual(first_error, '')
        self.assertEqual(second_error, '')
        self.assertEqual(first.id, second.id)
        self.assertEqual(Submission.objects.count(), 1)
        enqueue.assert_called_once()

    @patch('apps.submissions.services.enqueue_judge', side_effect=JudgeQueueFull('full'))
    def test_queue_full_marks_exam_submission_error(self, enqueue):
        submission, error = create_exam_submission(
            self.exam, self.student, self.question.id, 'select 1'
        )

        self.assertEqual(error, '判题服务繁忙')
        self.assertEqual(submission.execution_status, ERROR)


class RequeuePendingCommandTests(TestCase):
    """``manage.py requeue_pending`` 只重新入队 PENDING 的提交。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_requeue', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_requeue', password='pass1234', user_type='student',
        )
        self.question = _make_question(self.teacher)
        self.pending = Submission.objects.create(
            student=self.student, question=self.question,
            submitted_sql='select 1', execution_status=PENDING, score=0,
        )
        Submission.objects.create(
            student=self.student, question=self.question,
            submitted_sql='select 2', execution_status='ACCEPTED', score=100,
        )

    @patch('apps.submissions.management.commands.requeue_pending.enqueue_judge')
    def test_requeues_only_pending_submissions(self, enqueue):
        call_command('requeue_pending')
        enqueue.assert_called_once_with(self.pending.id)
