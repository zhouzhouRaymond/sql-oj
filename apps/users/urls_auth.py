from django.urls import path
from .views import RegisterView, LoginView, LogoutView, RefreshView

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    # 刷新：refresh token 取自 HttpOnly 登录 Cookie（也兼容请求体传 refresh）
    path('refresh/', RefreshView.as_view(), name='auth-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
]
