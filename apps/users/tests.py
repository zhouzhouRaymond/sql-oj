from django.core.cache import cache
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User


class SingleSessionLoginTests(APITestCase):
    """单点登录：同一账号只能在一个终端在线。"""

    def setUp(self):
        # 清空限流计数缓存，避免各用例之间相互影响
        cache.clear()
        self.password = 'pass1234'
        self.username = 'stu'
        self.user = User.objects.create_user(
            username=self.username,
            password=self.password,
            user_type='student',
        )

    def _login(self):
        return self.client.post(
            '/api/auth/login/',
            {'username': self.username, 'password': self.password},
            format='json',
        )

    def test_login_returns_tokens(self):
        resp = self._login()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)

    def test_second_login_invalidates_first_access_token(self):
        first = self._login()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        old_access = first.data['access']

        # 第二次登录（模拟另一台设备）：应踢掉第一个会话
        second = self._login()
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        new_access = second.data['access']

        # 旧 access token 立即失效
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        self.assertEqual(
            self.client.get('/api/users/me/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        # 新 access token 正常可用
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {new_access}')
        self.assertEqual(
            self.client.get('/api/users/me/').status_code,
            status.HTTP_200_OK,
        )

    def test_second_login_blacklists_first_refresh_token(self):
        first = self._login()
        old_refresh = first.data['refresh']

        self._login()  # 第二次登录踢掉旧会话

        # 旧 refresh token 已被拉黑，无法再换取新 token
        resp = self.client.post(
            '/api/auth/refresh/', {'refresh': old_refresh}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_invalidates_current_token(self):
        resp = self._login()
        access = resp.data['access']
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')

        logout_resp = self.client.post('/api/auth/logout/')
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

        # 登出后原 access token 立即失效
        self.assertEqual(
            self.client.get('/api/users/me/').status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_login_is_rate_limited(self):
        # 默认 10/min：同一 IP 第 11 次尝试应被限流
        last_status = None
        for _ in range(11):
            last_status = self._login().status_code
        self.assertEqual(last_status, status.HTTP_429_TOO_MANY_REQUESTS)
