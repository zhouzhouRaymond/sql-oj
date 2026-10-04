"""判题反馈脱敏测试：学生只看分类，教师/明细模式看具体原因。"""
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.questions.models import Question, TestCase as QuestionTestCase
from apps.users.models import User

from .feedback import student_case_message, summarize_schema_failures
from .models import Submission
from .status import WRONG_ANSWER

CHECKS = [
    {'name': '字段 t.email 类型', 'passed': False, 'detail': '类型不符'},
    {'name': '表 t 唯一约束 (email)', 'passed': False, 'detail': '唯一约束缺失'},
    {'name': 't.email 拒绝 NULL', 'passed': False, 'detail': '预期报错，实际执行成功'},
]


class FeedbackSummaryTests(SimpleTestCase):
    def test_groups_failures_by_category(self):
        summary = summarize_schema_failures({'checks': CHECKS})
        self.assertIn('字段定义 1 项', summary)
        self.assertIn('约束 1 项', summary)
        self.assertIn('行为校验 1 项', summary)
        # 不暴露具体列名 / 约束定义
        self.assertNotIn('email', summary)

    def test_all_passed_returns_generic(self):
        self.assertEqual(
            summarize_schema_failures({'checks': [{'name': 'x', 'passed': True}]}),
            '结构校验未通过',
        )

    def test_query_case_message_is_kept(self):
        self.assertEqual(
            student_case_message({'error_message': 'SQL执行超时'}), 'SQL执行超时'
        )


class SubmissionFeedbackApiTests(APITestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username='t_feedback', password='x', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_feedback', password='x', user_type='student',
        )
        self.question = Question.objects.create(
            description='反馈脱敏测试题', difficulty='easy', teacher=self.teacher,
            judge_mode='schema',
        )
        QuestionTestCase.objects.create(
            question=self.question, test_input='', expected_output='',
            expected_schema={'tables': {'t': {}}},
        )
        self.submission = Submission.objects.create(
            student=self.student, question=self.question, submitted_sql='CREATE TABLE t ();',
            execution_status=WRONG_ANSWER, score=0,
            judge_details={
                'cases': [{
                    'test_case_id': 0, 'passed': False, 'actual_output': '表 t:',
                    'error_message': (
                        '字段 t.email 类型：类型不符；'
                        '表 t 唯一约束 (email)：唯一约束缺失'
                    ),
                    'checks': CHECKS,
                }],
                'error_message': '建表语句执行失败: relation "t" already exists',
            },
        )
        self.url = f'/api/submissions/{self.submission.id}/'

    def test_student_gets_sanitized_feedback(self):
        self.client.force_authenticate(self.student)
        response = self.client.get(self.url)

        details = response.data['judge_details']
        failed = details['failed_cases'][0]
        self.assertIn('结构校验未通过', failed['error_message'])
        self.assertNotIn('email', failed['error_message'])
        self.assertNotIn('唯一约束 (email)', failed['error_message'])
        self.assertNotIn('建表语句执行失败', details['error_message'])

    def test_teacher_gets_full_feedback(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.get(self.url)

        details = response.data['judge_details']
        failed = details['failed_cases'][0]
        self.assertIn('字段 t.email 类型', failed['error_message'])
        self.assertIn('test_input', failed)
        self.assertIn('expected_output', failed)
