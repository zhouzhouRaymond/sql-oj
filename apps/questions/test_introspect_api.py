"""老师端「参考 DDL → 期望结构 / 自动探针」接口测试（判题服务用 mock）。"""
from unittest.mock import Mock, patch

import requests
from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from apps.users.models import User


class QuestionIntrospectApiTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='t_introspect', password='x', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='s_introspect', password='x', user_type='student',
        )
        self.url = '/api/questions/introspect/'

    def _mock_response(self, data):
        response = Mock()
        response.raise_for_status = Mock()
        response.json = Mock(return_value=data)
        return response

    @patch('apps.questions.views.requests.post')
    def test_teacher_can_generate_expected_schema_and_probes(self, post):
        post.return_value = self._mock_response({
            'expected_schema': {'tables': {'t': {'columns': []}}},
            'suggested_probes': [{'sql': 'x', 'expect': 'error', 'error_code': '23505'}],
            'error_message': None,
        })
        self.client.force_authenticate(self.teacher)

        response = self.client.post(
            self.url,
            {'reference_sql': 'CREATE TABLE t (id INT PRIMARY KEY);', 'setup_sql': ''},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['expected_schema'], {'tables': {'t': {'columns': []}}})
        self.assertEqual(len(response.data['suggested_probes']), 1)
        _, kwargs = post.call_args
        self.assertEqual(kwargs['json']['sql'], 'CREATE TABLE t (id INT PRIMARY KEY);')
        self.assertTrue(kwargs['json']['suggest_probes'])

    def test_missing_reference_sql_returns_400(self):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(self.url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_student_cannot_use_authoring_endpoint(self):
        self.client.force_authenticate(self.student)
        response = self.client.post(
            self.url, {'reference_sql': 'CREATE TABLE t (id INT);'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch('apps.questions.views.requests.post', side_effect=requests.ConnectionError('down'))
    def test_judge_service_unavailable_returns_503(self, post):
        self.client.force_authenticate(self.teacher)
        response = self.client.post(
            self.url, {'reference_sql': 'CREATE TABLE t (id INT);'}, format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
