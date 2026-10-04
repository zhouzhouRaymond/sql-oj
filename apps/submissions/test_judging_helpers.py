"""judging.py 的辅助逻辑与入队分支测试，不依赖数据库。"""
import queue
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from .job_queue import JudgeQueueUnavailable
from .judging import (
    JudgeQueueFull,
    _load_question_bundle,
    _score_for,
    _transport_error_result,
    enqueue_judge,
    queue_depth,
)
from .status import ERROR


class JudgeResultHelperTests(SimpleTestCase):
    def test_transport_error_result_is_retryable_error(self):
        result = _transport_error_result('judge down')
        self.assertFalse(result['passed'])
        self.assertEqual(result['execution_status'], ERROR)
        self.assertEqual(result['score'], 0)
        self.assertEqual(result['error_message'], 'judge down')

    def test_practice_score_uses_judge_score(self):
        submission = SimpleNamespace(exam_id=None)
        self.assertEqual(_score_for(submission, 'ACCEPTED', 80), 80)
        self.assertEqual(_score_for(submission, 'WRONG_ANSWER', 40), 40)

    def test_exam_score_uses_exam_question_score(self):
        submission = SimpleNamespace(exam_id=1, question_id=2)
        with patch('apps.exams.models.ExamQuestion.objects.filter') as query:
            query.return_value.values_list.return_value.first.return_value = 30
            self.assertEqual(_score_for(submission, 'ACCEPTED', 100), 30)
            self.assertEqual(_score_for(submission, 'WRONG_ANSWER', 0), 0)

    def test_exam_score_defaults_to_zero_without_mapping(self):
        submission = SimpleNamespace(exam_id=1, question_id=2)
        with patch('apps.exams.models.ExamQuestion.objects.filter') as query:
            query.return_value.values_list.return_value.first.return_value = None
            self.assertEqual(_score_for(submission, 'ACCEPTED', 100), 0)


class QuestionBundleTests(SimpleTestCase):
    def test_uses_cached_bundle_when_present(self):
        bundle = {'test_cases': [], 'create_table_sql': 'cached'}
        question = Mock(id=5)
        with patch('apps.submissions.judging.get_bundle', return_value=bundle):
            self.assertIs(_load_question_bundle(question), bundle)

    def test_falls_back_to_database_when_cache_miss(self):
        cases = [{'test_input': 'a', 'expected_output': 'b'}]
        question = Mock(id=5)
        question.create_table_sql = 'CREATE TABLE t (id INT);'
        question.test_cases.order_by.return_value.values.return_value = cases

        with patch('apps.submissions.judging.get_bundle', return_value=None):
            bundle = _load_question_bundle(question)

        self.assertEqual(bundle['test_cases'], cases)
        self.assertEqual(bundle['create_table_sql'], 'CREATE TABLE t (id INT);')


class EnqueueJudgeTests(SimpleTestCase):
    def test_redis_backend_only_enqueues(self):
        redis_queue = Mock()
        with patch('apps.submissions.judging.job_queue.use_redis', return_value=True), patch(
            'apps.submissions.judging.job_queue.get_redis_queue',
            return_value=redis_queue,
        ):
            enqueue_judge(9)
        redis_queue.enqueue.assert_called_once_with(9)

    def test_redis_unavailable_raises_queue_full(self):
        with patch('apps.submissions.judging.job_queue.use_redis', return_value=True), patch(
            'apps.submissions.judging.job_queue.get_redis_queue',
            side_effect=JudgeQueueUnavailable('down'),
        ):
            with self.assertRaises(JudgeQueueFull):
                enqueue_judge(1)

    def test_local_backend_puts_into_process_queue(self):
        local_queue = Mock()
        with patch('apps.submissions.judging.job_queue.use_redis', return_value=False), patch(
            'apps.submissions.judging._ensure_workers'
        ), patch('apps.submissions.judging._queue', local_queue):
            enqueue_judge(3)
        local_queue.put_nowait.assert_called_once_with(3)

    def test_local_queue_full_raises_queue_full(self):
        local_queue = Mock()
        local_queue.put_nowait.side_effect = queue.Full
        with patch('apps.submissions.judging.job_queue.use_redis', return_value=False), patch(
            'apps.submissions.judging._ensure_workers'
        ), patch('apps.submissions.judging._queue', local_queue):
            with self.assertRaises(JudgeQueueFull):
                enqueue_judge(3)


class QueueDepthTests(SimpleTestCase):
    def test_local_queue_depth(self):
        local_queue = Mock(qsize=Mock(return_value=5))
        with patch('apps.submissions.judging.job_queue.use_redis', return_value=False), patch(
            'apps.submissions.judging._queue', local_queue
        ):
            self.assertEqual(queue_depth(), 5)

    def test_redis_queue_depth(self):
        redis_queue = Mock(depth=Mock(return_value=7))
        with patch('apps.submissions.judging.job_queue.use_redis', return_value=True), patch(
            'apps.submissions.judging.job_queue.get_redis_queue',
            return_value=redis_queue,
        ):
            self.assertEqual(queue_depth(), 7)

    def test_redis_failure_reports_zero_depth(self):
        with patch('apps.submissions.judging.job_queue.use_redis', return_value=True), patch(
            'apps.submissions.judging.job_queue.get_redis_queue',
            side_effect=JudgeQueueUnavailable('down'),
        ):
            self.assertEqual(queue_depth(), 0)
