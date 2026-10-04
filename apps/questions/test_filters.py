"""题目列表筛选（search / difficulty / is_visible）的接口测试。"""
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.users.models import User

from .models import Question


class QuestionFilterTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_filter', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_filter', password='pass1234', user_type='student',
        )
        self.easy = Question.objects.create(
            title='两数之和', description='用 SQL 求两数之和',
            difficulty='easy', teacher=self.teacher, is_visible=True,
        )
        self.hard = Question.objects.create(
            title='员工连接', description='inner join 练习',
            difficulty='hard', teacher=self.teacher, is_visible=True,
        )
        self.hidden = Question.objects.create(
            title='草稿题', description='尚未公开的草稿',
            difficulty='medium', teacher=self.teacher, is_visible=False,
        )

    def _ids(self, **params):
        response = self.client.get('/api/questions/', params)
        self.assertEqual(response.status_code, 200)
        data = response.data
        rows = data['results'] if isinstance(data, dict) else data
        return {row['id'] for row in rows}

    def test_search_matches_title_but_not_description(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self._ids(search='两数'), {self.easy.id})
        # 'join' 只出现在 hard 的描述里，按「只匹配名称和题号」的规则不应命中
        self.assertEqual(self._ids(search='join'), set())
        self.assertEqual(self._ids(search='员工'), {self.hard.id})

    def test_teacher_can_search_by_question_id(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self._ids(search=str(self.hidden.id)), {self.hidden.id})

    def test_numeric_search_matches_question_id_and_title_only(self):
        """纯数字匹配题号（精确）与名称，描述里含该数字的题目不参与。"""
        self.client.force_authenticate(self.teacher)
        title_match = Question.objects.create(
            title=f'练习题 {self.easy.id}',
            description='标题含数字',
            difficulty='medium', teacher=self.teacher, is_visible=True,
        )
        description_only = Question.objects.create(
            title='标题不含数字',
            description=f'描述里含数字 {self.easy.id}',
            difficulty='medium', teacher=self.teacher, is_visible=True,
        )

        self.assertEqual(
            self._ids(search=str(self.easy.id)),
            {self.easy.id, title_match.id},
        )
        self.assertNotIn(description_only.id, self._ids(search=str(self.easy.id)))

    def test_difficulty_filter_and_invalid_value(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self._ids(difficulty='hard'), {self.hard.id})
        self.assertEqual(
            self._ids(difficulty='impossible'),
            {self.easy.id, self.hard.id, self.hidden.id},
        )

    def test_teacher_can_filter_hidden_questions(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(self._ids(is_visible='false'), {self.hidden.id})
        self.assertEqual(
            self._ids(is_visible='true'), {self.easy.id, self.hard.id}
        )

    def test_student_only_sees_visible_questions_even_with_filter(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self._ids(is_visible='false'), {self.easy.id, self.hard.id})
        self.assertEqual(self._ids(search='草稿'), set())

    def test_student_search_matches_visible_questions(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(self._ids(search='员工'), {self.hard.id})
