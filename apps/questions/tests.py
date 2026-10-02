from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User
from .models import Question


class QuestionVisibilityTests(APITestCase):
    """教师可控制题目是否对学生可见（is_visible）。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_vis', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_vis', password='pass1234', user_type='student',
        )
        self.visible = Question.objects.create(
            description='公开题', difficulty='easy',
            teacher=self.teacher, is_visible=True,
        )
        self.hidden = Question.objects.create(
            description='隐藏题', difficulty='easy',
            teacher=self.teacher, is_visible=False,
        )

    def _list_ids(self):
        resp = self.client.get('/api/questions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        return [row['id'] for row in resp.data['results']]

    def test_new_question_is_visible_by_default(self):
        q = Question.objects.create(
            description='默认可见', difficulty='easy', teacher=self.teacher,
        )
        self.assertTrue(q.is_visible)

    def test_student_list_excludes_hidden(self):
        self.client.force_authenticate(self.student)
        ids = self._list_ids()
        self.assertIn(self.visible.id, ids)
        self.assertNotIn(self.hidden.id, ids)

    def test_student_cannot_open_hidden_detail(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(
            self.client.get(f'/api/questions/{self.hidden.id}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )
        self.assertEqual(
            self.client.get(f'/api/questions/{self.visible.id}/').status_code,
            status.HTTP_200_OK,
        )

    def test_teacher_list_includes_hidden(self):
        self.client.force_authenticate(self.teacher)
        ids = self._list_ids()
        self.assertIn(self.hidden.id, ids)
        self.assertIn(self.visible.id, ids)

    def test_teacher_can_toggle_visibility(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.patch(
            f'/api/questions/{self.visible.id}/',
            {'is_visible': False}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.visible.refresh_from_db()
        self.assertFalse(self.visible.is_visible)

        # 隐藏后学生立刻看不到了
        self.client.force_authenticate(self.student)
        self.assertNotIn(self.visible.id, self._list_ids())

    def test_student_cannot_toggle_visibility(self):
        self.client.force_authenticate(self.student)
        resp = self.client.patch(
            f'/api/questions/{self.visible.id}/',
            {'is_visible': False}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.visible.refresh_from_db()
        self.assertTrue(self.visible.is_visible)

