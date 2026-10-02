from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.exams.models import Exam
from apps.questions.models import Question
from apps.users.models import User
from .models import Submission


class ExamSubmissionFilterTests(APITestCase):
    """提交列表支持按考试过滤（`?exam=`）——教师端「考试提交情况」依赖它。

    教师能看到本场考试所有学生的提交（含他人），学生只会看到自己的；
    同时校验：其它考试、练习提交（exam 为空）都不会混进来，非法参数返回 400。
    """

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_subfilter', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_subfilter', password='pass1234', user_type='student',
        )
        self.other = User.objects.create_user(
            username='s_subfilter_other', password='pass1234', user_type='student',
        )
        now = timezone.now()
        self.exam = Exam.objects.create(
            title='过滤考试A', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher, student_scope='all',
        )
        self.other_exam = Exam.objects.create(
            title='过滤考试B', start_time=now - timedelta(hours=1),
            end_time=now + timedelta(hours=1), total_score=100,
            teacher=self.teacher, student_scope='all',
        )
        self.question = Question.objects.create(
            description='过滤题', difficulty='easy', teacher=self.teacher,
        )

    def _submit(self, exam, student=None, score=10):
        return Submission.objects.create(
            student=student or self.student, question=self.question, exam=exam,
            submitted_sql='SELECT 1', score=score, execution_status='ACCEPTED',
        )

    def _ids(self, params):
        resp = self.client.get('/api/submissions/', params)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return [row['id'] for row in resp.data['results']]

    def test_teacher_sees_every_student_of_that_exam(self):
        mine = self._submit(self.exam)
        others = self._submit(self.exam, student=self.other)
        # 其它考试的提交、练习提交（exam 为空）都不应出现
        self._submit(self.other_exam)
        Submission.objects.create(
            student=self.student, question=self.question, exam=None,
            submitted_sql='SELECT 1', score=10, execution_status='ACCEPTED',
        )

        self.client.force_authenticate(self.teacher)
        self.assertCountEqual(self._ids({'exam': self.exam.id}), [mine.id, others.id])

    def test_student_sees_only_own_submissions_of_that_exam(self):
        mine = self._submit(self.exam)
        self._submit(self.exam, student=self.other)

        self.client.force_authenticate(self.student)
        self.assertEqual(self._ids({'exam': self.exam.id}), [mine.id])

    def test_exam_filter_combines_with_student_filter(self):
        mine = self._submit(self.exam)
        self._submit(self.exam, student=self.other)

        self.client.force_authenticate(self.teacher)
        ids = self._ids({'exam': self.exam.id, 'student_id': self.student.id})
        self.assertEqual(ids, [mine.id])

    def test_invalid_exam_param_returns_400(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.get('/api/submissions/', {'exam': 'abc'})
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_exposes_student_login_name(self):
        """教师端列表需要同时拿到学生用户名与登录名（用于区分同名用户）。"""
        self._submit(self.exam)
        self.client.force_authenticate(self.teacher)
        resp = self.client.get('/api/submissions/', {'exam': self.exam.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row = resp.data['results'][0]
        self.assertEqual(row['student_name'], self.student.name)
        self.assertEqual(row['student_username'], self.student.username)

    def test_list_exposes_exam_title(self):
        """列表要给出考试名称，前端「来源」列才能显示标题而不是光秃秃的考试 id。"""
        self._submit(self.exam)
        self.client.force_authenticate(self.teacher)
        resp = self.client.get('/api/submissions/', {'exam': self.exam.id})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['results'][0]['exam_title'], self.exam.title)

    def test_exam_title_is_none_for_practice_submissions(self):
        """练习提交不属于任何考试：exam 与 exam_title 都应为 None（前端据此显示「练习」）。"""
        Submission.objects.create(
            student=self.student, question=self.question, exam=None,
            submitted_sql='SELECT 1', score=10, execution_status='ACCEPTED',
        )
        self.client.force_authenticate(self.student)
        resp = self.client.get('/api/submissions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        row = resp.data['results'][0]
        self.assertIsNone(row['exam'])
        self.assertIsNone(row['exam_title'])

