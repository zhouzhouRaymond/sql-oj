"""登录 Cookie：用 HttpOnly Cookie 承载 refresh token，实现「关闭浏览器后一段时间内免登录」。

设计要点：

- **HttpOnly**：JS 读不到，降低 XSS 窃取风险（前端只持有短时效的 access token）；
- **SameSite=Lax**：跨站请求不携带，避免被第三方页面利用刷新接口；
- **Path=/api/auth**：只随认证相关请求发送，减少暴露面；
- **Max-Age = refresh token 自身剩余有效期**（即 ``settings.LOGIN_REMEMBER_DAYS``，默认 7 天）：
  到点后浏览器自动删除 Cookie，服务端也会因 refresh token 过期拒绝刷新，用户必须重新登录；
- 刷新时会轮换 refresh token（``ROTATE_REFRESH_TOKENS``），Cookie 随之更新，窗口按活跃度顺延。
"""
from django.conf import settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

# 登录 Cookie 名称与作用路径（仅 /api/auth/* 会携带）
REFRESH_COOKIE_NAME = 'sql_oj_refresh'
REFRESH_COOKIE_PATH = '/api/auth'


def refresh_token_max_age(refresh_token: str) -> int:
    """Cookie 有效期（秒）：与 refresh token 自身的剩余寿命保持一致。"""
    try:
        expires_at = RefreshToken(refresh_token)['exp']
        remaining = int((expires_at - timezone.now()).total_seconds())
    except Exception:
        # 解析失败（异常 token）时回退到配置窗口，保证仍能写入 Cookie
        remaining = int(settings.LOGIN_REMEMBER_DAYS) * 24 * 3600
    return max(1, remaining)


def set_refresh_cookie(response, refresh_token: str) -> None:
    """把 refresh token 写入 HttpOnly 登录 Cookie（有效期 = 免登录窗口）。"""
    response.set_cookie(
        REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=refresh_token_max_age(refresh_token),
        path=REFRESH_COOKIE_PATH,
        httponly=True,
        samesite='Lax',
        secure=bool(getattr(settings, 'LOGIN_COOKIE_SECURE', False)),
    )


def clear_refresh_cookie(response) -> None:
    """删除登录 Cookie（登出、刷新失败时调用）。"""
    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def read_refresh_cookie(request):
    """读取登录 Cookie 里的 refresh token；没有则返回 None。"""
    return request.COOKIES.get(REFRESH_COOKIE_NAME) or None
