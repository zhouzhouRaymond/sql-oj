"""schema 判题链路的端到端单元测试（判题服务用 mock，其余走真实代码）。"""
from unittest.mock import Mock, patch

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from apps.exams.models import Exam
from apps.questions.models import Question, TestCase as QuestionTestCase
from apps.users.models import User

from .judging import run_judge_task
from .models import Submission
from .status import PENDING

EXPECTED_SCHEMA = {
    'tables': {
        'users': {
            'columns': [
                {'name': 'id', 'type': 'integer', 'not_null': True, 'default': 'serial'},
                {'name': 'email', 'type': 'character varying(100)', 'not_null': True, 'default': None},
            ],
            'primary_key': {'name': 'users_pkey', 'columns': ['id']},
            'unique': [{'name': 'users_email_key', 'columns': ['email']}],
            'checks': [],
            'foreign_keys': [],
            'indexes': [
                {'name': 'users_pkey', 'columns': ['id'], 'unique': True, 'method': 'btree',
                 'predicate': None, 'include': [], 'desc': [False], 'nulls_first': [False]},
            ],
        },
    },
}
ACCEPTED_RESULT = {
    'passed': True,
    'execution_status': 'ACCEPTED',
    'score': 100,
    'details': [{
        'test_case_id': 0,
        'passed': True,
        'actual_output': '表 users:',
        'error_message': '',
        'checks': [{'name': '表 users', 'passed': True, 'detail': ''}],
    }],
}


class SchemaSubmissionFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_schema_flow', password='x', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_schema_flow', password='x', user_type='student',
        )
        self.question = Question.objects.create(
            description='schema 链路测试题', difficulty='medium', teacher=self.teacher,
            judge_mode='schema',
        )
        QuestionTestCase.objects.create(
            question=self.question, test_input='', expected_output='',
            expected_schema=EXPECTED_SCHEMA,
            probes=[{'sql': 'x', 'expect': 'ok', 'description': '示例探针'}],
        )
        self.submission = Submission.objects.create(
            student=self.student, question=self.question,
            submitted_sql='CREATE TABLE users (id SERIAL PRIMARY KEY, email VARCHAR(100) NOT NULL UNIQUE);',
            execution_status=PENDING, score=0,
        )

    def _mock_response(self):
        response = Mock()
        response.raise_for_status = Mock()
        response.json = Mock(return_value=dict(ACCEPTED_RESULT))
        return response

    def test_schema_payload_is_sent_and_result_reaches_writer(self):
        with patch(
            'apps.submissions.judge.requests.post', return_value=self._mock_response()
        ) as post, patch('apps.submissions.judging.result_writer.enqueue') as enqueue:
            run_judge_task(self.submission.id)

        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['mode'], 'schema')
        self.assertEqual(payload['strictness'], 'subset')
        self.assertFalse(payload['compare_names'])
        case = payload['test_cases'][0]
        self.assertEqual(case['expected_schema'], EXPECTED_SCHEMA)
        self.assertEqual(case['probes'][0]['description'], '示例探针')
        self.assertNotIn('create_table_sql', payload)

        enqueue.assert_called_once()
        args = enqueue.call_args.args
        self.assertEqual(args[0], self.submission.id)
        self.assertEqual(args[1], 'ACCEPTED')
        self.assertEqual(args[2], 100)

    def test_strictness_options_are_forwarded(self):
        self.question.judge_strictness = 'exact'
        self.question.judge_compare_names = True
        self.question.save(update_fields=['judge_strictness', 'judge_compare_names'])

        with patch(
            'apps.submissions.judge.requests.post', return_value=self._mock_response()
        ) as post, patch('apps.submissions.judging.result_writer.enqueue'):
            run_judge_task(self.submission.id)

        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['strictness'], 'exact')
        self.assertTrue(payload['compare_names'])

    def test_exam_schema_submission_uses_exam_score(self):
        exam = Exam.objects.create(
            title='schema 考试', start_time=timezone.now(), end_time=timezone.now(),
            total_score=100, teacher=self.teacher,
        )
        exam.exam_questions.create(question=self.question, score=35)
        self.submission.exam = exam
        self.submission.save(update_fields=['exam'])

        with patch(
            'apps.submissions.judge.requests.post', return_value=self._mock_response()
        ), patch('apps.submissions.judging.result_writer.enqueue') as enqueue:
            run_judge_task(self.submission.id)

        self.assertEqual(enqueue.call_args.args[2], 35)
