"""历史通过率与难度建议：纯函数 + 教师端接口测试。"""
from django.test import SimpleTestCase
from rest_framework.test import APITestCase

from apps.submissions.models import Submission
from apps.submissions.status import ACCEPTED, WRONG_ANSWER
from apps.users.models import User

from .difficulty import MIN_SAMPLE_SIZE, recommend_difficulty
from .models import Question


class RecommendDifficultyTests(SimpleTestCase):
    """难度建议的阈值与样本量门槛。"""

    def test_no_submissions_has_no_recommendation(self):
        result = recommend_difficulty(attempted_students=0, passed_students=0)
        self.assertIsNone(result['recommended_difficulty'])
        self.assertEqual(result['confidence'], 'none')

    def test_small_sample_has_no_recommendation(self):
        result = recommend_difficulty(attempted_students=MIN_SAMPLE_SIZE - 1, passed_students=0)
        self.assertIsNone(result['recommended_difficulty'])
        self.assertEqual(result['confidence'], 'low')

    def test_high_pass_rate_is_easy(self):
        result = recommend_difficulty(attempted_students=5, passed_students=5)
        self.assertEqual(result['recommended_difficulty'], 'easy')

    def test_middle_pass_rate_is_medium(self):
        result = recommend_difficulty(attempted_students=4, passed_students=3)
        self.assertEqual(result['recommended_difficulty'], 'medium')

    def test_low_pass_rate_is_hard(self):
        result = recommend_difficulty(attempted_students=4, passed_students=1)
        self.assertEqual(result['recommended_difficulty'], 'hard')

    def test_passed_never_exceeds_attempted(self):
        result = recommend_difficulty(attempted_students=4, passed_students=99)
        self.assertEqual(result['recommended_difficulty'], 'easy')


class QuestionHistoryAPITests(APITestCase):
    """教师端题目接口附带历史通过率与难度建议。"""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username='t_history', password='pass1234', user_type='teacher',
        )
        self.students = [
            User.objects.create_user(
                username=f's_history_{i}', password='pass1234', user_type='student',
            )
            for i in range(4)
        ]
        self.question = Question.objects.create(
            title='历史表现测试题', description='用于验证通过率统计',
            difficulty='easy', teacher=self.teacher, is_visible=True,
        )

    def _submit(self, student, status_value):
        return Submission.objects.create(
            student=student, question=self.question,
            submitted_sql='SELECT 1', execution_status=status_value,
        )

    def test_teacher_detail_exposes_pass_rate_and_recommendation(self):
        for i, student in enumerate(self.students):
            self._submit(student, ACCEPTED if i < 3 else WRONG_ANSWER)

        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/questions/{self.question.id}/')

        self.assertEqual(resp.status_code, 200)
        history = resp.data['history']
        self.assertEqual(history['attempted_students'], 4)
        self.assertEqual(history['passed_students'], 3)
        self.assertEqual(history['total_submissions'], 4)
        self.assertEqual(history['accepted_submissions'], 3)
        self.assertAlmostEqual(history['student_pass_rate'], 0.75, places=4)
        self.assertEqual(history['recommended_difficulty'], 'medium')

    def test_teacher_list_includes_history(self):
        self._submit(self.students[0], ACCEPTED)

        self.client.force_authenticate(self.teacher)
        resp = self.client.get('/api/questions/', {'ordering': 'id'})

        self.assertEqual(resp.status_code, 200)
        row = next(
            item for item in resp.data['results'] if item['id'] == self.question.id
        )
        self.assertIn('history', row)
        self.assertEqual(row['history']['passed_students'], 1)
        # 只有 1 名学生尝试：展示通过率，但不给难度建议
        self.assertIsNone(row['history']['recommended_difficulty'])

    def test_student_view_never_exposes_history(self):
        self.client.force_authenticate(self.students[0])
        resp = self.client.get(f'/api/questions/{self.question.id}/')

        self.assertEqual(resp.status_code, 200)
        self.assertNotIn('history', resp.data)

    def test_teacher_trial_submissions_are_excluded(self):
        # 教师自己试做一次错题，不应拉低通过率
        self._submit(self.teacher, WRONG_ANSWER)
        for student in self.students:
            self._submit(student, ACCEPTED)

        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/questions/{self.question.id}/')

        history = resp.data['history']
        self.assertEqual(history['attempted_students'], 4)
        self.assertEqual(history['passed_students'], 4)
        self.assertEqual(history['total_submissions'], 4)
        self.assertEqual(history['recommended_difficulty'], 'easy')

    def test_multiple_submissions_count_student_once(self):
        student = self.students[0]
        self._submit(student, WRONG_ANSWER)
        self._submit(student, WRONG_ANSWER)
        self._submit(student, ACCEPTED)

        self.client.force_authenticate(self.teacher)
        resp = self.client.get(f'/api/questions/{self.question.id}/')

        history = resp.data['history']
        self.assertEqual(history['total_submissions'], 3)
        self.assertEqual(history['attempted_students'], 1)
        self.assertEqual(history['passed_students'], 1)
