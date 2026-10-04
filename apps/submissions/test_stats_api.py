"""统计分析接口测试（教师看板依赖）。"""
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from apps.questions.models import Question
from apps.users.models import User

from .models import Submission
from .status import ACCEPTED, WRONG_ANSWER


class StatsApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_stats_api', password='x', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_stats_api', password='x', user_type='student',
        )
        self.question = Question.objects.create(
            title='统计题', description='统计题', difficulty='easy', teacher=self.teacher,
        )
        Submission.objects.create(
            student=self.student, question=self.question, submitted_sql='select 1',
            execution_status=ACCEPTED, score=100,
        )
        Submission.objects.create(
            student=self.student, question=self.question, submitted_sql='select 2',
            execution_status=WRONG_ANSWER, score=0,
        )

    def test_overview_counts(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.get('/api/stats/overview/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_submissions'], 2)
        self.assertEqual(response.data['total_questions'], 1)
        self.assertEqual(response.data['average_pass_rate'], 0.5)

    def test_question_stats_ranking(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.get(
            '/api/stats/question/', {'question_id': self.question.id}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_submissions'], 2)
        self.assertEqual(response.data['accepted_submissions'], 1)
        self.assertEqual(response.data['passed_students'], 1)
        self.assertEqual(response.data['student_ranking'][0]['username'], self.student.username)

    def test_teacher_only_reports_reject_students(self):
        self.client.force_authenticate(self.student)
        for url in ('/api/stats/questions/', '/api/stats/students/'):
            with self.subTest(url=url):
                self.assertEqual(
                    self.client.get(url).status_code, status.HTTP_403_FORBIDDEN
                )
        self.assertEqual(
            self.client.get(
                '/api/stats/question/', {'question_id': self.question.id}
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )
