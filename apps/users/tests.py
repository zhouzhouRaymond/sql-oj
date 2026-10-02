from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import RefreshToken

from .auth_cookies import REFRESH_COOKIE_NAME
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


class AccountManagementPermissionTests(APITestCase):
    """教师即管理员：所有教师都拥有账号管理功能。"""

    def setUp(self):
        cache.clear()
        self.teacher = User.objects.create_user(
            username='teacher_a', password='pass1234', user_type='teacher',
        )
        self.student = User.objects.create_user(
            username='student_a', password='pass1234', user_type='student',
        )

    def test_teacher_can_list_accounts(self):
        self.client.force_authenticate(self.teacher)
        self.assertEqual(
            self.client.get('/api/users/').status_code, status.HTTP_200_OK
        )

    def test_teacher_can_create_teacher_account(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.post(
            '/api/users/',
            {
                'username': 'teacher_b',
                'password': 'pass1234',
                'user_type': 'teacher',
            },
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            User.objects.get(username='teacher_b').user_type, 'teacher'
        )

    def test_teacher_can_edit_and_disable_account(self):
        self.client.force_authenticate(self.teacher)
        resp = self.client.patch(
            f'/api/users/{self.student.id}/',
            {'is_active': False},
            format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

    def test_any_teacher_can_manage_accounts(self):
        # 另一名普通教师账号同样能管理账号（不存在“只有管理员能管”的限制）
        other = User.objects.create_user(
            username='teacher_c', password='pass1234', user_type='teacher',
        )
        self.client.force_authenticate(other)
        self.assertEqual(
            self.client.get('/api/users/').status_code, status.HTTP_200_OK
        )

    def test_student_cannot_manage_accounts(self):
        self.client.force_authenticate(self.student)
        self.assertEqual(
            self.client.get('/api/users/').status_code,
            status.HTTP_403_FORBIDDEN,
        )
        self.assertEqual(
            self.client.post(
                '/api/users/',
                {'username': 'x', 'password': 'pass1234', 'user_type': 'student'},
                format='json',
            ).status_code,
            status.HTTP_403_FORBIDDEN,
        )


class LoginCookieTests(APITestCase):
    """登录 Cookie（免登录窗口）。

    refresh token 放在 HttpOnly Cookie 里：关闭浏览器后，在「免登录窗口」（默认 7 天，
    可用 LOGIN_REMEMBER_DAYS 调整）内重新打开仍免登录；窗口过期后必须重新登录。
    """

    def setUp(self):
        cache.clear()
        self.password = 'pass1234'
        self.username = 'cookie_stu'
        self.user = User.objects.create_user(
            username=self.username, password=self.password, user_type='student',
        )

    def _login(self):
        return self.client.post(
            '/api/auth/login/',
            {'username': self.username, 'password': self.password},
            format='json',
        )

    def _cookie(self, resp):
        return resp.cookies[REFRESH_COOKIE_NAME]

    def test_login_sets_httponly_cookie_with_remember_window(self):
        resp = self._login()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        cookie = self._cookie(resp)
        self.assertTrue(cookie['httponly'])          # JS 读不到，降低 XSS 窃取风险
        self.assertEqual(cookie['samesite'], 'Lax')   # 跨站请求不携带
        self.assertEqual(cookie['path'], '/api/auth')  # 只随认证请求发送
        window = settings.LOGIN_REMEMBER_DAYS * 24 * 3600
        self.assertLessEqual(int(cookie['max-age']), window)
        self.assertGreater(int(cookie['max-age']), window - 60)
        # 前端据此判断窗口是否过期
        self.assertEqual(resp.data['remember_days'], settings.LOGIN_REMEMBER_DAYS)

    def test_refresh_uses_cookie_only_and_rotates_token(self):
        first = self._login()
        old_cookie = self._cookie(first).value

        # 模拟浏览器：只带 Cookie，请求体不含 refresh
        resp = self.client.post('/api/auth/refresh/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)
        # 轮换：Cookie 里的 refresh token 已更新（免登录窗口顺延）
        new_cookie = self._cookie(resp)
        self.assertNotEqual(new_cookie.value, old_cookie)
        self.assertGreater(int(new_cookie['max-age']), 0)

        # 新 access token 可正常访问
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
        self.assertEqual(
            self.client.get('/api/users/me/').status_code, status.HTTP_200_OK
        )

    def test_refresh_without_cookie_is_rejected(self):
        resp = self.client.post('/api/auth/refresh/', {}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_expired_refresh_token_is_rejected(self):
        """超过免登录窗口（refresh 已过期）后不能再刷新，必须重新登录。"""
        self._login()
        token = RefreshToken.for_user(self.user)
        token.set_exp(
            from_time=timezone.now() - timedelta(days=30),
            lifetime=timedelta(seconds=1),
        )
        resp = self.client.post(
            '/api/auth/refresh/', {'refresh': str(token)}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_renews_remember_window(self):
        """刷新成功后窗口顺延：新 refresh token 的有效期按窗口重新计算。"""
        self._login()
        short = RefreshToken.for_user(self.user)
        short.set_exp(lifetime=timedelta(seconds=60))   # 模拟「即将到期」的 refresh token
        resp = self.client.post(
            '/api/auth/refresh/', {'refresh': str(short)}, format='json'
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        window = settings.LOGIN_REMEMBER_DAYS * 24 * 3600
        self.assertGreater(int(self._cookie(resp)['max-age']), window - 120)

    def test_logout_clears_login_cookie(self):
        login = self._login()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        resp = self.client.post('/api/auth/logout/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(int(self._cookie(resp)['max-age']), 0)

    def test_remember_window_is_configurable(self):
        """窗口长度由 LOGIN_REMEMBER_DAYS 决定（示例：1 天）。"""
        try:
            with self.settings(LOGIN_REMEMBER_DAYS=1):
                api_settings.reload()   # simplejwt 缓存了配置，需重新读取
                max_age = int(self._cookie(self._login())['max-age'])
            self.assertGreater(max_age, 86400 - 60)
            self.assertLessEqual(max_age, 86400)
        finally:
            api_settings.reload()
