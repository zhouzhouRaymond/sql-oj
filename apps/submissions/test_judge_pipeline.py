"""判题链路（规范化 / 缓存键 / 幂等 / 提交入队）的单元测试。"""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import SimpleTestCase
from rest_framework import status
from rest_framework.test import APITestCase

from apps.questions.models import Question
from apps.users.models import User

from .judging import JudgeQueueFull
from .models import Submission
from .normalization import normalize_sql, result_cache_key
from .services import create_submission
from .status import ERROR


class SqlNormalizationTests(SimpleTestCase):
    """SQL 规范化必须语义等价：去注释/压空白/关键字大写，但保留字面量。"""

    def test_collapses_whitespace_and_uppercases_keywords(self):
        self.assertEqual(
            normalize_sql('select  a,  b   from t'),
            'SELECT a, b FROM t',
        )

    def test_strips_line_and_block_comments_without_merging_tokens(self):
        # 关键点：注释被删除后不能把相邻 token 粘连成 "1FROM"
        self.assertEqual(normalize_sql('SELECT 1--c\nFROM t'), 'SELECT 1 FROM t')
        self.assertEqual(normalize_sql('SELECT 1 /* x\ny */ FROM t'), 'SELECT 1 FROM t')

    def test_string_literals_are_preserved(self):
        # 字面量内部的空白/大小写不可改动，否则会把语义不同的 SQL 归一为同一键
        self.assertEqual(normalize_sql("SELECT 'a  b'"), "SELECT 'a  b'")

    def test_equivalent_sql_shares_key_and_distinct_dimensions_differ(self):
        cases = [{'test_input': '', 'expected_output': 'a'}]
        same_a = result_cache_key(1, 'select a from t', cases)
        same_b = result_cache_key(1, 'SELECT   a   FROM t', cases)
        self.assertEqual(same_a, same_b)

        self.assertNotEqual(same_a, result_cache_key(2, 'select a from t', cases))
        self.assertNotEqual(
            same_a,
            result_cache_key(1, 'select a from t', [{'test_input': '', 'expected_output': 'b'}]),
        )

    def test_case_order_changes_cache_key(self):
        first = {'test_input': '', 'expected_output': 'a'}
        second = {'test_input': '', 'expected_output': 'b'}
        self.assertNotEqual(
            result_cache_key(1, 'select 1', [first, second]),
            result_cache_key(1, 'select 1', [second, first]),
        )


class SubmitIdempotencyTests(APITestCase):
    """相同提交在幂等窗口内应复用同一条提交，不重复创建判题任务。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_idem', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_idem', password='pass1234', user_type='student',
        )
        self.question = Question.objects.create(
            description='幂等题', difficulty='easy', teacher=self.teacher,
        )
        self.client.force_authenticate(self.student)

    def _submit(self, sql):
        return self.client.post(
            '/api/submissions/submit/',
            {'question_id': self.question.id, 'submitted_sql': sql},
            format='json',
        )

    def test_duplicate_submit_reuses_existing_submission(self):
        with patch('apps.submissions.services.enqueue_judge'):
            first = self._submit('select 1')
            # 仅大小写/空白不同，规范化后等价，应视为同一次提交
            second = self._submit('SELECT   1')

        self.assertEqual(first.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(second.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(Submission.objects.count(), 1)

    def test_different_sql_creates_new_submission(self):
        with patch('apps.submissions.services.enqueue_judge'):
            first = self._submit('select 1')
            second = self._submit('select 2')

        self.assertNotEqual(first.data['id'], second.data['id'])
        self.assertEqual(Submission.objects.count(), 2)


class SubmissionServiceTests(SimpleTestCase):
    """``create_submission`` 的三条分支：命中幂等 / 正常入队 / 入队失败。"""

    student = SimpleNamespace(id=1)
    question = SimpleNamespace(id=2)
    exam = SimpleNamespace(id=3)

    def setUp(self):
        cache.clear()

    @patch('apps.submissions.services.remember_submission')
    @patch('apps.submissions.services.enqueue_judge')
    @patch('apps.submissions.services.find_duplicate_submission')
    def test_duplicate_is_reused_without_enqueueing(self, find_duplicate, enqueue, remember):
        existing = SimpleNamespace(id=11)
        find_duplicate.return_value = existing

        result = create_submission(self.student, self.question, 'select 1', exam=self.exam)

        self.assertTrue(result.duplicate)
        self.assertFalse(result.queue_full)
        self.assertIs(result.submission, existing)
        enqueue.assert_not_called()
        remember.assert_called_once()

    @patch('apps.submissions.services.remember_submission')
    @patch('apps.submissions.services.enqueue_judge')
    @patch('apps.submissions.services.Submission.objects.create')
    @patch('apps.submissions.services.find_duplicate_submission', return_value=None)
    def test_new_submission_is_created_and_enqueued(self, find_duplicate, create, enqueue, remember):
        created = SimpleNamespace(id=7)
        create.return_value = created

        result = create_submission(self.student, self.question, 'select 1', exam=self.exam)

        self.assertFalse(result.duplicate)
        self.assertFalse(result.queue_full)
        self.assertIs(result.submission, created)
        enqueue.assert_called_once_with(7)
        remember.assert_called_once()

    @patch('apps.submissions.services.remember_submission')
    @patch('apps.submissions.services.enqueue_judge')
    @patch('apps.submissions.services.Submission.objects.create')
    @patch('apps.submissions.services.find_duplicate_submission', return_value=None)
    def test_queue_full_marks_submission_as_error(self, find_duplicate, create, enqueue, remember):
        created = SimpleNamespace(id=9, execution_status=None, save=Mock())
        create.return_value = created
        enqueue.side_effect = JudgeQueueFull('full')

        result = create_submission(self.student, self.question, 'select 1')

        self.assertTrue(result.queue_full)
        self.assertIs(result.submission, created)
        self.assertEqual(created.execution_status, ERROR)
        created.save.assert_called_once_with(update_fields=['execution_status'])
        remember.assert_not_called()
