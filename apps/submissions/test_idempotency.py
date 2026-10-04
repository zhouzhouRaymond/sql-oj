"""提交幂等的直接单元测试（缓存窗口 + PENDING 兜底 + 已出结果不复用）。"""
import os
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.exams.models import Exam
from apps.questions.models import Question
from apps.users.models import User

from .idempotency import (
    find_duplicate_submission,
    idempotency_key,
    remember_submission,
)
from .models import Submission
from .status import ACCEPTED, PENDING


class IdempotencyTests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_idem2', password='x', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_idem2', password='x', user_type='student',
        )
        self.question = Question.objects.create(
            description='幂等测试题', difficulty='easy', teacher=self.teacher,
        )

    def _key(self, sql='select 1', exam_id=None):
        return idempotency_key(self.student.id, self.question.id, exam_id, sql)

    def _submission(self, status=PENDING, exam=None, sql='select 1'):
        return Submission.objects.create(
            student=self.student, question=self.question, exam=exam,
            submitted_sql=sql, execution_status=status, score=0,
        )

    def test_remembered_submission_is_reused(self):
        first = self._submission()
        key = self._key()
        remember_submission(key, first.id)

        found = find_duplicate_submission(
            self.student, self.question, None, 'select 1', key
        )
        self.assertEqual(found.id, first.id)

    def test_pending_submission_is_reused_without_cache(self):
        first = self._submission()
        found = find_duplicate_submission(
            self.student, self.question, None, 'select 1', self._key()
        )
        self.assertEqual(found.id, first.id)

    def test_completed_submission_is_not_reused(self):
        self._submission(status=ACCEPTED)
        found = find_duplicate_submission(
            self.student, self.question, None, 'select 1', self._key()
        )
        self.assertIsNone(found)

    def test_zero_ttl_disables_cache_window(self):
        with patch.dict(os.environ, {'JUDGE_IDEMPOTENCY_TTL': '0'}):
            key = self._key()
            first = self._submission()
            remember_submission(key, first.id)
            self.assertIsNone(cache.get(key))
            # 缓存窗口关闭后，仍靠 PENDING 兜底
            found = find_duplicate_submission(
                self.student, self.question, None, 'select 1', key
            )
            self.assertEqual(found.id, first.id)

    def test_different_exam_is_not_reused(self):
        now = timezone.now()
        exam = Exam.objects.create(
            title='幂等考试', start_time=now, end_time=now,
            total_score=100, teacher=self.teacher,
        )
        self._submission(exam=None)
        found = find_duplicate_submission(
            self.student, self.question, exam.id, 'select 1',
            self._key(exam_id=exam.id),
        )
        self.assertIsNone(found)
