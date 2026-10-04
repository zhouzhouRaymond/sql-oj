"""``run_judge_task`` 端到端单元测试（需要数据库，判题服务用 mock 替代）。"""
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.exams.models import Exam
from apps.questions.models import Question, TestCase as QuestionTestCase
from apps.users.models import User

from .judging import run_judge_task
from .models import Submission
from .status import PENDING

ACCEPTED_RESULT = {
    'passed': True,
    'execution_status': 'ACCEPTED',
    'score': 100,
    'details': [{'test_case_id': 0, 'passed': True, 'actual_output': 'id\n1'}],
}


class RunJudgeTaskTests(TestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_task', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_task', password='pass1234', user_type='student',
        )
        self.question = Question.objects.create(
            description='任务测试题', difficulty='easy', teacher=self.teacher,
            create_table_sql='CREATE TABLE t (id INT);',
        )
        QuestionTestCase.objects.create(
            question=self.question, test_input='', expected_output='id\n1',
        )
        self.submission = Submission.objects.create(
            student=self.student, question=self.question,
            submitted_sql='select 1', execution_status=PENDING, score=0,
        )

    def test_judge_result_is_handed_to_result_writer(self):
        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(ACCEPTED_RESULT),
        ), patch('apps.submissions.judging.result_writer.enqueue') as enqueue:
            run_judge_task(self.submission.id)

        enqueue.assert_called_once()
        submission_id, status, score, details = enqueue.call_args.args
        self.assertEqual(submission_id, self.submission.id)
        self.assertEqual(status, 'ACCEPTED')
        self.assertEqual(score, 100)
        self.assertEqual(details['cases'], ACCEPTED_RESULT['details'])

    def test_second_run_hits_result_cache(self):
        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(ACCEPTED_RESULT),
        ) as judge, patch('apps.submissions.judging.result_writer.enqueue'):
            run_judge_task(self.submission.id)
            run_judge_task(self.submission.id)

        self.assertEqual(judge.call_count, 1)

    def test_exam_submission_uses_exam_question_score(self):
        exam = Exam.objects.create(
            title='任务测试考试', start_time=self.question.created_at,
            end_time=self.question.created_at, total_score=100, teacher=self.teacher,
        )
        exam.exam_questions.create(question=self.question, score=30)
        self.submission.exam = exam
        self.submission.save(update_fields=['exam'])

        with patch(
            'apps.submissions.judging.judge_submission_strict',
            return_value=dict(ACCEPTED_RESULT),
        ), patch('apps.submissions.judging.result_writer.enqueue') as enqueue:
            run_judge_task(self.submission.id)

        self.assertEqual(enqueue.call_args.args[2], 30)

    def test_missing_submission_is_ignored(self):
        with patch('apps.submissions.judging.result_writer.enqueue') as enqueue:
            run_judge_task(10 ** 9)
        enqueue.assert_not_called()
